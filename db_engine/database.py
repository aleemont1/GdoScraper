import sqlite3
import os
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("DatabaseEngine")

class BaseStorage(ABC):
    """Abstract base class defining the database storage interface."""

    @abstractmethod
    def initialize(self) -> None:
        """Initializes the database storage schema and connection."""
        pass

    @abstractmethod
    def save_offers(self, offers: List[ProductOffer]) -> int:
        """Persists a list of ProductOffer records idempotently (UPSERT)."""
        pass

    @abstractmethod
    def get_offers(self) -> List[Dict[str, Any]]:
        """Retrieves all promotional offers sorted by extracted timestamp."""
        pass

    @abstractmethod
    def get_stats(self) -> List[Dict[str, Any]]:
        """Retrieves aggregated statistics partitioned by supermarket store."""
        pass

    @abstractmethod
    def update_offer(self, supermarket: str, store_id: str, offer_id: str, fields: Dict[str, Any]) -> bool:
        """Updates specific columns of a single offer targeted by compound key."""
        pass

    @abstractmethod
    def delete_offer(self, supermarket: str, store_id: str, offer_id: str) -> bool:
        """Deletes a single offer targeted by compound key."""
        pass

    @abstractmethod
    def find_reusable_images(self, supermarket: str) -> List[Dict[str, Any]]:
        """Scans records in the store with valid image links to support reuse."""
        pass

    @abstractmethod
    def clear_all(self) -> bool:
        """Deletes all promotional offers from the database."""
        pass


class SQLiteStorage(BaseStorage):
    """SQLite implementation of the GDO Scraper storage engine."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("DB_PATH", "storage/promotions.db")

    def initialize(self) -> None:
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
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
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_promotions_ean ON promotions(ean_code);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_promotions_lookup ON promotions(supermarket, store_id);")
            conn.commit()
            logger.info(f"SQLite database initialized at: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
            raise
        finally:
            conn.close()

    def save_offers(self, offers: List[ProductOffer]) -> int:
        if not offers:
            return 0
        conn = sqlite3.connect(self.db_path, timeout=30.0)
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
        try:
            param_list = [
                (
                    o.supermarket, o.store_id, o.offer_id, o.name, o.brand, o.weight_or_volume,
                    o.price, o.original_price, o.discount_percentage, o.price_per_unit,
                    o.ean_code, o.image_url, o.category, o.promo_type, o.validity_string
                )
                for o in offers
            ]
            cursor.executemany(upsert_query, param_list)
            conn.commit()
            return len(offers)
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"SQLite upsert error: {e}")
            raise
        finally:
            conn.close()

    def get_offers(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    supermarket, store_id, offer_id, name, brand, weight_or_volume,
                    price, original_price, discount_percentage, price_per_unit,
                    ean_code, image_url, category, promo_type, validity_string, extracted_at
                FROM promotions 
                ORDER BY extracted_at DESC, supermarket ASC, name ASC;
            """)
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"SQLite query error: {e}")
            return []
        finally:
            conn.close()

    def get_stats(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    supermarket, store_id, COUNT(*) as total_offers,
                    MIN(price) as min_price, MAX(price) as max_price
                FROM promotions
                GROUP BY supermarket, store_id
                ORDER BY total_offers DESC;
            """)
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"SQLite query error: {e}")
            return []
        finally:
            conn.close()

    def update_offer(self, supermarket: str, store_id: str, offer_id: str, fields: Dict[str, Any]) -> bool:
        if not fields:
            return False
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # Build update query dynamically
        set_clauses = []
        params = []
        for key, val in fields.items():
            set_clauses.append(f"{key} = ?")
            params.append(val)
        
        set_clauses.append("extracted_at = CURRENT_TIMESTAMP")
        query = f"UPDATE promotions SET {', '.join(set_clauses)} WHERE supermarket = ? AND store_id = ? AND offer_id = ?;"
        params.extend([supermarket, store_id, offer_id])
        
        try:
            cursor.execute(query, params)
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"SQLite update error: {e}")
            raise
        finally:
            conn.close()

    def delete_offer(self, supermarket: str, store_id: str, offer_id: str) -> bool:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM promotions WHERE supermarket = ? AND store_id = ? AND offer_id = ?;", (supermarket, store_id, offer_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"SQLite delete error: {e}")
            raise
        finally:
            conn.close()

    def find_reusable_images(self, supermarket: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT image_url, name 
                FROM promotions 
                WHERE supermarket = ? 
                  AND image_url IS NOT NULL 
                  AND image_url != '' 
                  AND image_url NOT LIKE '%standard_images%';
            """, (supermarket,))
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"SQLite query error: {e}")
            return []
        finally:
            conn.close()

    def clear_all(self) -> bool:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM promotions;")
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"SQLite clear all error: {e}")
            return False
        finally:
            conn.close()


class SupabaseStorage(BaseStorage):
    """Supabase implementation of the GDO Scraper storage engine via direct REST API calls."""

    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.environ.get("SUPABASE_KEY", "").strip()
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def initialize(self) -> None:
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables must be set for Supabase storage engine.")
        try:
            res = requests.get(f"{self.url}/rest/v1/promotions?limit=1", headers=self.headers, timeout=10)
            if res.status_code not in (200, 201, 404):
                logger.warning(f"Supabase connection test returned status code {res.status_code}. Details: {res.text}")
            else:
                logger.info("Supabase storage engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            raise

    def save_offers(self, offers: List[ProductOffer]) -> int:
        if not offers:
            return 0
        
        payload = []
        for o in offers:
            payload.append({
                "supermarket": o.supermarket,
                "store_id": o.store_id,
                "offer_id": o.offer_id,
                "name": o.name,
                "brand": o.brand,
                "weight_or_volume": o.weight_or_volume,
                "price": o.price,
                "original_price": o.original_price,
                "discount_percentage": o.discount_percentage,
                "price_per_unit": o.price_per_unit,
                "ean_code": o.ean_code,
                "image_url": o.image_url,
                "category": o.category,
                "promo_type": o.promo_type,
                "validity_string": o.validity_string
            })
            
        headers = self.headers.copy()
        headers["Prefer"] = "resolution=merge-duplicates"
        
        try:
            res = requests.post(f"{self.url}/rest/v1/promotions", headers=headers, json=payload, timeout=30)
            if res.status_code not in (200, 201):
                raise Exception(f"Supabase returned error: {res.status_code} - {res.text}")
            return len(offers)
        except Exception as e:
            logger.error(f"Failed to save offers to Supabase: {e}")
            raise

    def get_offers(self) -> List[Dict[str, Any]]:
        try:
            res = requests.get(
                f"{self.url}/rest/v1/promotions?order=extracted_at.desc,supermarket.asc,name.asc",
                headers=self.headers,
                timeout=30
            )
            if res.status_code != 200:
                raise Exception(f"Supabase returned error: {res.status_code} - {res.text}")
            return res.json()
        except Exception as e:
            logger.error(f"Failed to fetch offers from Supabase: {e}")
            return []

    def get_stats(self) -> List[Dict[str, Any]]:
        offers = self.get_offers()
        if not offers:
            return []
            
        breakdown = {}
        for o in offers:
            key = (o.get("supermarket"), o.get("store_id"))
            price = o.get("price")
            if price is None:
                continue
            try:
                price = float(price)
            except ValueError:
                continue
                
            if key not in breakdown:
                breakdown[key] = {
                    "supermarket": key[0],
                    "store_id": key[1],
                    "total_offers": 0,
                    "min_price": price,
                    "max_price": price
                }
            item = breakdown[key]
            item["total_offers"] += 1
            item["min_price"] = min(item["min_price"], price)
            item["max_price"] = max(item["max_price"], price)
            
        return sorted(breakdown.values(), key=lambda x: x["total_offers"], reverse=True)

    def update_offer(self, supermarket: str, store_id: str, offer_id: str, fields: Dict[str, Any]) -> bool:
        url = f"{self.url}/rest/v1/promotions?supermarket=eq.{supermarket}&store_id=eq.{store_id}&offer_id=eq.{offer_id}"
        from datetime import datetime, timezone
        payload = fields.copy()
        payload["extracted_at"] = datetime.now(timezone.utc).isoformat()
        
        try:
            res = requests.patch(url, headers=self.headers, json=payload, timeout=30)
            if res.status_code not in (200, 204):
                raise Exception(f"Supabase returned error: {res.status_code} - {res.text}")
            return True
        except Exception as e:
            logger.error(f"Failed to update offer in Supabase: {e}")
            raise

    def delete_offer(self, supermarket: str, store_id: str, offer_id: str) -> bool:
        url = f"{self.url}/rest/v1/promotions?supermarket=eq.{supermarket}&store_id=eq.{store_id}&offer_id=eq.{offer_id}"
        try:
            res = requests.delete(url, headers=self.headers, timeout=30)
            if res.status_code not in (200, 204):
                raise Exception(f"Supabase returned error: {res.status_code} - {res.text}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete offer in Supabase: {e}")
            raise

    def find_reusable_images(self, supermarket: str) -> List[Dict[str, Any]]:
        url = f"{self.url}/rest/v1/promotions?supermarket=eq.{supermarket}"
        try:
            res = requests.get(url, headers=self.headers, timeout=30)
            if res.status_code != 200:
                raise Exception(f"Supabase returned error: {res.status_code} - {res.text}")
            rows = res.json()
            return [
                r for r in rows 
                if r.get("image_url") and r.get("image_url") != "" and "standard_images" not in r.get("image_url")
            ]
        except Exception as e:
            logger.error(f"Failed to fetch images from Supabase: {e}")
            return []

    def clear_all(self) -> bool:
        url = f"{self.url}/rest/v1/promotions?supermarket=not.is.null"
        try:
            res = requests.delete(url, headers=self.headers, timeout=30)
            if res.status_code not in (200, 204):
                raise Exception(f"Supabase returned error: {res.status_code} - {res.text}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear all promotions in Supabase: {e}")
            return False


def get_storage(db_path: Optional[str] = None) -> BaseStorage:
    """Factory function returning the active storage engine based on environment variable setting."""
    engine = os.environ.get("DB_ENGINE", "sqlite").lower().strip()
    if engine == "supabase":
        return SupabaseStorage()
    return SQLiteStorage(db_path=db_path)


def initialize_db(db_path: str) -> None:
    """Wrapper function maintaining backward-compatibility with database schema setup callers."""
    storage = get_storage(db_path=db_path)
    storage.initialize()


def save_offers(db_path: str, offers: List[ProductOffer]) -> int:
    """Wrapper function maintaining backward-compatibility with offer save callers."""
    storage = get_storage(db_path=db_path)
    return storage.save_offers(offers)
