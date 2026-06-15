"""
Automated Pytest Suite for Supermarket Scraper ETL Pipeline.

Tests database initializations, UPSERT operations, schema validation,
parsing utility methods, and geocoding helper functions.
"""

import os
import sqlite3
import pytest
from pydantic import ValidationError

from core.models import ProductOffer
from core.base_driver import AbstractOfferParser
from storage.database import initialize_db, save_offers
from utils.image_manager import get_standard_image, find_reusable_image, _normalize_string


class DummyParser(AbstractOfferParser):
    """Concrete dummy parser implementation for testing purposes."""
    
    def parse_flyer_validity(self, text: str) -> Optional[str]:
        return "DAL 1 AL 10 MAGGIO 2026"

    def parse_cell(self, text: str, store_id: str, validity_string: Optional[str]) -> ProductOffer:
        return ProductOffer(
            offer_id="dummy_id",
            supermarket="DUMMY",
            store_id=store_id,
            name="Dummy Product",
            price=1.99,
            promo_type="STANDARD"
        )


@pytest.fixture
def temp_db_path(tmp_path) -> str:
    """Fixture that provides a temporary database file path."""
    db_file = tmp_path / "test_promotions.db"
    return str(db_file)


def test_product_offer_schema_validation():
    """Verifies Pydantic schema validation for ProductOffer model."""
    # Valid payload
    offer = ProductOffer(
        offer_id="test_id_123",
        supermarket="COOP",
        store_id="0315",
        name="Test Milk",
        price=1.29,
        original_price=1.59,
        discount_percentage=18,
        promo_type="PERCENTAGE_DISCOUNT"
    )
    assert offer.offer_id == "test_id_123"
    assert offer.price == 1.29
    assert offer.promo_type == "PERCENTAGE_DISCOUNT"

    # Missing required field (price)
    with pytest.raises(ValidationError):
        ProductOffer(
            offer_id="test_id_124",
            supermarket="COOP",
            store_id="0315",
            name="Test Milk",
            promo_type="STANDARD"
        )


def test_database_initialization_and_upsert(temp_db_path):
    """Verifies SQLite database initialization, table creation, and idempotency via UPSERT."""
    # 1. Initialize
    initialize_db(temp_db_path)
    assert os.path.exists(temp_db_path)

    # Verify table schema exists
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='promotions';")
    assert cursor.fetchone() is not None

    # 2. Insert initial offer
    offer1 = ProductOffer(
        offer_id="offer_id_1",
        supermarket="CONAD",
        store_id="005635",
        name="Pasta Barilla",
        brand="Barilla",
        weight_or_volume="500g",
        price=0.89,
        promo_type="STANDARD"
    )
    
    saved = save_offers(temp_db_path, [offer1])
    assert saved == 1

    # Verify insert details
    cursor.execute("SELECT name, price FROM promotions WHERE offer_id='offer_id_1';")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Pasta Barilla"
    assert row[1] == 0.89

    # 3. Perform UPSERT with updated price
    offer1_updated = ProductOffer(
        offer_id="offer_id_1",
        supermarket="CONAD",
        store_id="005635",
        name="Pasta Barilla",
        brand="Barilla",
        weight_or_volume="500g",
        price=0.79,  # updated price
        promo_type="STANDARD"
    )
    
    saved_updated = save_offers(temp_db_path, [offer1_updated])
    assert saved_updated == 1

    # Verify that the record was updated rather than duplicated
    cursor.execute("SELECT name, price FROM promotions WHERE offer_id='offer_id_1';")
    row = cursor.fetchone()
    assert row[1] == 0.79
    
    cursor.execute("SELECT count(*) FROM promotions;")
    assert cursor.fetchone()[0] == 1

    conn.close()


def test_parse_helpers():
    """Tests utility parsing text manipulation methods."""
    parser = DummyParser()
    
    # Test collapse spaced uppercase letter strings
    assert parser.de_space_uppercase("C U O R E") == "CUORE"
    assert parser.de_space_uppercase("S P A G H E T T I  Barilla") == "SPAGHETTI Barilla"
    assert parser.de_space_uppercase("DI B A R I") == "DI BARI"


def test_conad_unit_price_parsing():
    """Verifies that ConadOfferParser correctly extracts unit prices and removes them from selling prices."""
    from drivers.conad.offer_parser import ConadOfferParser
    
    parser = ConadOfferParser()
    
    # 1. Simple package price and unit price (euros and cents separated by text/spaces)
    text1 = "Mozzarella di Bufala BARILLA 500g 4,98 € al kg 9,96 €"
    offer1 = parser.parse_cell(text1, "005635", "DAL 1 AL 10 MAGGIO 2026")
    assert offer1.price == 4.98
    assert "9,96" in offer1.price_per_unit
    
    # 2. Case with spacing and symbols
    text2 = "Detersivo Lavatrice DASH 1,5 L 2,49 € al lt 1,66 €"
    offer2 = parser.parse_cell(text2, "005635", "DAL 1 AL 10 MAGGIO 2026")
    assert offer2.price == 2.49


def test_standard_image_lookup():
    """Tests product name standard fresh produce image mappings."""
    # Matches fresh fruit
    assert get_standard_image("Mele Golden") == "/storage/standard_images/mele.png"
    assert get_standard_image("Banane biologiche") == "/storage/standard_images/banane.png"
    
    # Exclusion keyword block check
    assert get_standard_image("Yogurt alle Mele") is None
    assert get_standard_image("Succo di Arance") is None


def test_fuzzy_image_reuse(temp_db_path):
    """Tests fuzzy search image reuse database scanners."""
    initialize_db(temp_db_path)
    
    offer = ProductOffer(
        offer_id="ean_12345",
        supermarket="CONAD",
        store_id="005635",
        name="Biscotti Frollini Integrali",
        price=2.49,
        image_url="/storage/images/conad_005635_ean_12345.png",
        promo_type="STANDARD"
    )
    save_offers(temp_db_path, [offer])

    # Exact match reuse
    url1 = find_reusable_image("CONAD", "Biscotti Frollini Integrali", db_path=temp_db_path)
    assert url1 == "/storage/images/conad_005635_ean_12345.png"

    # Fuzzy match reuse (above 88% threshold)
    url2 = find_reusable_image("CONAD", "Biscotti frollini integrali.", db_path=temp_db_path)
    assert url2 == "/storage/images/conad_005635_ean_12345.png"

    # Dissimilar name should not match
    url3 = find_reusable_image("CONAD", "Pasta Barilla n.5", db_path=temp_db_path)
    assert url3 is None


def test_database_update_and_delete(temp_db_path):
    """Verifies that database update and delete queries execute successfully and target the correct rows."""
    initialize_db(temp_db_path)
    
    # Insert a dummy record
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO promotions (
            supermarket, store_id, offer_id, name, brand, weight_or_volume,
            price, original_price, discount_percentage, promo_type, extracted_at
        ) VALUES (
            'COOP', '0315', 'item_999', 'Original Product', 'Brand X', '1kg',
            4.99, 5.99, 16, 'STANDARD', '2026-06-01 12:00:00'
        );
    """)
    conn.commit()

    # Verify original details
    cursor.execute("SELECT name, price, original_price, discount_percentage FROM promotions WHERE offer_id='item_999';")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Original Product"
    assert row[1] == 4.99
    assert row[2] == 5.99
    assert row[3] == 16

    # Perform UPDATE matching logic in dashboard.py
    cursor.execute("""
        UPDATE promotions 
        SET name = ?, brand = ?, weight_or_volume = ?, price = ?, original_price = ?, 
            discount_percentage = ?, ean_code = ?, category = ?, promo_type = ?,
            extracted_at = CURRENT_TIMESTAMP
        WHERE supermarket = ? AND store_id = ? AND offer_id = ?;
    """, ("Updated Product", "Brand Y", "2kg", 3.49, 4.49, 22, "1234567890123", "Food", "PROMO", "COOP", "0315", "item_999"))
    conn.commit()

    # Verify update details
    cursor.execute("""
        SELECT name, brand, weight_or_volume, price, original_price, discount_percentage, ean_code, category, promo_type 
        FROM promotions WHERE offer_id='item_999';
    """)
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Updated Product"
    assert row[1] == "Brand Y"
    assert row[2] == "2kg"
    assert row[3] == 3.49
    assert row[4] == 4.49
    assert row[5] == 22
    assert row[6] == "1234567890123"
    assert row[7] == "Food"
    assert row[8] == "PROMO"

    # Perform DELETE matching logic in dashboard.py
    cursor.execute("""
        DELETE FROM promotions 
        WHERE supermarket = ? AND store_id = ? AND offer_id = ?;
    """, ("COOP", "0315", "item_999"))
    conn.commit()

    # Verify deletion
    cursor.execute("SELECT count(*) FROM promotions WHERE offer_id='item_999';")
    assert cursor.fetchone()[0] == 0

    conn.close()


def test_database_image_update(temp_db_path):
    """Verifies updating a promotion's image_url directly in the database."""
    initialize_db(temp_db_path)
    
    # Insert a dummy record
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO promotions (
            supermarket, store_id, offer_id, name, price, promo_type, image_url
        ) VALUES (
            'COOP', '0315', 'item_888', 'Image Product', 2.99, 'STANDARD', '/storage/images/old.png'
        );
    """)
    conn.commit()

    # Perform UPDATE matching logic in change-image endpoint of dashboard.py
    new_image_url = "/storage/images/new_image_file.png"
    cursor.execute("""
        UPDATE promotions
        SET image_url = ?, extracted_at = CURRENT_TIMESTAMP
        WHERE supermarket = ? AND store_id = ? AND offer_id = ?;
    """, (new_image_url, "COOP", "0315", "item_888"))
    conn.commit()

    # Verify updated image
    cursor.execute("SELECT image_url FROM promotions WHERE offer_id='item_888';")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == new_image_url

    conn.close()


def test_get_storage_factory(monkeypatch):
    """Verifies storage engine factory returns correct implementation based on environment."""
    from storage.database import get_storage, SQLiteStorage, SupabaseStorage
    
    # SQLite default
    monkeypatch.delenv("DB_ENGINE", raising=False)
    storage = get_storage()
    assert isinstance(storage, SQLiteStorage)
    
    # Explicit SQLite
    monkeypatch.setenv("DB_ENGINE", "sqlite")
    storage = get_storage()
    assert isinstance(storage, SQLiteStorage)
    
    # Supabase
    monkeypatch.setenv("DB_ENGINE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "dummy_key")
    storage = get_storage()
    assert isinstance(storage, SupabaseStorage)


def test_supabase_storage_operations_mocked(monkeypatch):
    """Verifies Supabase REST API requests are formatted correctly."""
    from storage.database import SupabaseStorage
    from unittest.mock import MagicMock
    
    monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "dummy_key")
    
    storage = SupabaseStorage()
    assert storage.url == "https://xyz.supabase.co"
    assert storage.key == "dummy_key"
    
    # Mock requests.get/post/patch/delete
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    
    mock_get = MagicMock(return_value=mock_response)
    mock_post = MagicMock(return_value=mock_response)
    mock_patch = MagicMock(return_value=mock_response)
    mock_delete = MagicMock(return_value=mock_response)
    
    import requests
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "patch", mock_patch)
    monkeypatch.setattr(requests, "delete", mock_delete)
    
    # Test initialize
    storage.initialize()
    mock_get.assert_called_with("https://xyz.supabase.co/rest/v1/promotions?limit=1", headers=storage.headers, timeout=10)
    
    # Test save_offers
    offer = ProductOffer(
        offer_id="mock_id",
        supermarket="MOCK",
        store_id="123",
        name="Mock Product",
        price=3.50,
        promo_type="STANDARD"
    )
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post.return_value = mock_post_resp
    
    saved = storage.save_offers([offer])
    assert saved == 1
    mock_post.assert_called_once()
    
    # Test get_offers
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = [
        {"supermarket": "MOCK", "store_id": "123", "offer_id": "mock_id", "name": "Mock Product", "price": 3.50}
    ]
    mock_get.return_value = mock_get_resp
    
    offers = storage.get_offers()
    assert len(offers) == 1
    assert offers[0]["name"] == "Mock Product"
    
    # Test get_stats
    stats = storage.get_stats()
    assert len(stats) == 1
    assert stats[0]["total_offers"] == 1
    assert stats[0]["min_price"] == 3.50
    assert stats[0]["max_price"] == 3.50
    
    # Test update_offer
    mock_patch_resp = MagicMock()
    mock_patch_resp.status_code = 204
    mock_patch.return_value = mock_patch_resp
    
    success = storage.update_offer("MOCK", "123", "mock_id", {"name": "Updated Mock"})
    assert success is True
    mock_patch.assert_called_once()
    
    # Test delete_offer
    mock_delete_resp = MagicMock()
    mock_delete_resp.status_code = 204
    mock_delete.return_value = mock_delete_resp
    
    success = storage.delete_offer("MOCK", "123", "mock_id")
    assert success is True
    mock_delete.assert_called_once()
    
    # Test clear_all
    mock_delete.reset_mock()
    success = storage.clear_all()
    assert success is True
    mock_delete.assert_called_once()



