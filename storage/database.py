import sqlite3
import os
from typing import List
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("DatabaseEngine")

def initialize_db(db_path: str) -> None:
    """
    Initializes the SQLite database with correct schema structures and indexes.
    
    Args:
        db_path: Path to the SQLite database file.
    """
    # Create the directory structure if it doesn't exist
    dir_name = os.path.dirname(db_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create promotions table with a compound primary key for idempotency
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promotions (
                supermarket TEXT,
                store_id TEXT,
                offer_id TEXT,
                name TEXT NOT NULL,
                brand TEXT,
                weight_or_volume TEXT,
                price REAL NOT NULL,
                original_price REAL,
                discount_percentage INTEGER,
                price_per_unit TEXT,
                ean_code TEXT,
                image_url TEXT,
                category TEXT,
                promo_type TEXT,
                validity_string TEXT,
                extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (supermarket, store_id, offer_id)
            );
        """)
        
        # Create indexes to speed up lookup/cross-referencing queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_promotions_ean ON promotions(ean_code);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_promotions_lookup ON promotions(supermarket, store_id);")
        
        conn.commit()
        logger.info(f"Database initialized successfully at: {db_path}")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        conn.close()

def save_offers(db_path: str, offers: List[ProductOffer]) -> int:
    """
    Persists a list of ProductOffer records using SQL UPSERT logic.
    Ensures absolute idempotency of promotions.
    
    Args:
        db_path: Path to the SQLite database file.
        offers: List of validated ProductOffer objects.
        
    Returns:
        The number of records processed.
    """
    if not offers:
        logger.info("No offers to save.")
        return 0
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    upsert_query = """
        INSERT INTO promotions (
            supermarket, store_id, offer_id, name, brand, weight_or_volume,
            price, original_price, discount_percentage, price_per_unit,
            ean_code, image_url, category, promo_type, validity_string
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        ) ON CONFLICT(supermarket, store_id, offer_id) DO UPDATE SET
            name = excluded.name,
            brand = excluded.brand,
            weight_or_volume = excluded.weight_or_volume,
            price = excluded.price,
            original_price = excluded.original_price,
            discount_percentage = excluded.discount_percentage,
            price_per_unit = excluded.price_per_unit,
            ean_code = excluded.ean_code,
            image_url = excluded.image_url,
            category = excluded.category,
            promo_type = excluded.promo_type,
            validity_string = excluded.validity_string,
            extracted_at = CURRENT_TIMESTAMP;
    """
    
    records_written = 0
    try:
        # Construct parameters from our Pydantic objects
        param_list = [
            (
                offer.supermarket,
                offer.store_id,
                offer.offer_id,
                offer.name,
                offer.brand,
                offer.weight_or_volume,
                offer.price,
                offer.original_price,
                offer.discount_percentage,
                offer.price_per_unit,
                offer.ean_code,
                offer.image_url,
                offer.category,
                offer.promo_type,
                offer.validity_string
            )
            for offer in offers
        ]
        
        cursor.executemany(upsert_query, param_list)
        conn.commit()
        records_written = len(offers)
        logger.info(f"Successfully upserted {records_written} promotion offers.")
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error during upsert execution: {e}")
        raise
    finally:
        conn.close()
        
    return records_written
