"""
Dpiù (D+ Discount Supermarket) Scraper Strategy Driver.

Uses REST API integrations with dynamic JWT OAuth2 token retrieval
and geocoding store locator resolution.
"""

import os
import re
import base64
import hashlib
import requests
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from core.base_driver import AbstractApiSupermarketDriver
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("DpiuDriver")


def decrypt_cryptojs_aes(ciphertext_b64: str, passphrase: str) -> str:
    """
    Decrypts standard OpenSSL/CryptoJS AES-256-CBC encrypted strings.
    Uses EVP_BytesToKey to derive the key and IV from the salt and passphrase.
    
    Args:
        ciphertext_b64: Encrypted text encoded in Base64.
        passphrase: Encryption secret key.
        
    Returns:
        Decrypted plain text string.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    data = base64.b64decode(ciphertext_b64)
    if data[:8] != b"Salted__":
        raise ValueError("Invalid ciphertext format: missing Salted__ prefix")
        
    salt = data[8:16]
    ciphertext = data[16:]
    
    passphrase_bytes = passphrase.encode("utf-8")
    
    # OpenSSL EVP_BytesToKey key derivation (key=32 bytes, iv=16 bytes)
    d_1 = hashlib.md5(passphrase_bytes + salt).digest()
    d_2 = hashlib.md5(d_1 + passphrase_bytes + salt).digest()
    d_3 = hashlib.md5(d_2 + passphrase_bytes + salt).digest()
    
    key = d_1 + d_2
    iv = d_3
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()
    
    # PKCS7 Unpadding
    pad_len = decrypted_padded[-1]
    decrypted = decrypted_padded[:-pad_len]
    
    return decrypted.decode("utf-8")


class DpiuSupermarketDriver(AbstractApiSupermarketDriver):
    """
    Concrete scraper driver strategy for Dpiù (D+ discount supermarket).
    Uses clean REST API integrations, dynamic JWT Bearer token generation,
    and a local Haversine-based GPS store lookup.
    """

    def __init__(
        self,
        max_flyers: Optional[int] = None,
        radius: int = 15,
        choose_store: bool = False,
        choose_flyer: bool = False
    ) -> None:
        """
        Initializes the Dpiù driver.
        
        Args:
            max_flyers: Limit on maximum flyers to retrieve.
            radius: Radius in kilometers for coordinate store matching.
            choose_store: Unused parameter preserved for interface compliance.
            choose_flyer: Unused parameter preserved for interface compliance.
        """
        super().__init__(radius=radius, choose_store=choose_store, choose_flyer=choose_flyer)
        self.max_flyers = max_flyers
        
        # Configure headers specific to Dpiù
        self._session.headers.update({
            "Origin": "https://dpiu.maxidi.it",
            "Referer": "https://dpiu.maxidi.it/"
        })
        
        self._weight_regex = re.compile(
            r"\b(\d+(?:,\d+)?\s*(?:g|kg|ml|l|lt|pz|pezzi|lavaggi|fette))\b",
            re.IGNORECASE
        )

    def _get_authorization_data(self) -> str:
        """
        Fetches Dpiù website landing page and extracts the encrypted authorization string.
        
        Returns:
            Encrypted authorization string.
        """
        url = "https://dpiu.maxidi.it/"
        logger.info("Fetching Dpiù landing page to extract security headers...")
        try:
            res = self._session.get(url, timeout=15)
            res.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.text, "html.parser")
            meta = soup.find("meta", attrs={"name": "_authorization_data"})
            if not meta:
                raise ValueError("Could not find meta tag _authorization_data in Dpiù website HTML")
            
            val = meta.get("content", "")
            logger.info("Successfully extracted encrypted authorization token.")
            return val
        except Exception as e:
            logger.error(f"Failed to query Dpiù landing page: {e}")
            raise e

    def _get_bearer_token(self) -> str:
        """
        Decrypts the client credentials and trades them for a JWT Bearer token at /oauth/token.
        
        Returns:
            JWT token string.
        """
        try:
            encrypted_auth = self._get_authorization_data()
            passphrase = "$InterlacedIt0!"
            credential = decrypt_cryptojs_aes(encrypted_auth, passphrase)
            
            basic_auth_val = base64.b64encode(credential.encode("utf-8")).decode("utf-8")
            
            token_url = "https://dpiu.maxidi.it/digitalflyer/oauth/token"
            headers = {
                "Authorization": f"Basic {basic_auth_val}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            payload = {
                "grant_type": "client_credentials",
                "scope": "read write"
            }
            
            logger.info("Exchanging decrypted credentials for OAuth2 JWT token...")
            res = self._session.post(token_url, data=payload, headers=headers, timeout=10)
            res.raise_for_status()
            
            token = res.json()["access_token"]
            logger.info("OAuth2 Bearer token successfully generated.")
            return token
        except Exception as e:
            logger.error(f"OAuth2 authentication flow failed: {e}")
            raise e

    def discover_stores(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Discovers physical stores matching GPS coordinates, city, or partial address.
        
        Args:
            store_id: Coordinates query ('lat,lon') or text search query.
            
        Returns:
            A list of discovered store dictionaries.
        """
        try:
            token = self._get_bearer_token()
        except Exception as e:
            logger.error(f"Failed to authenticate for store discovery: {e}")
            return []
            
        lat, lon = None, None
        coords_match = self.COORDINATES_REGEX.match(store_id)
        if coords_match:
            lat = float(coords_match.group(1))
            lon = float(coords_match.group(2))
        else:
            # If store_id looks like a direct store alias, return it immediately
            if store_id.lower().startswith("d-"):
                return [{
                    "id": store_id.lower(),
                    "name": f"Dpiù Store {store_id}",
                    "address": "",
                    "city": "",
                    "distance": None
                }]
            coords = self._geocode_location(store_id)
            if coords:
                lat, lon = coords
                
        url = "https://dpiu.maxidi.it/digitalflyer/api/maxidi/dpiu/stores?size=500"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = self._session.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            stores = res.json()
        except Exception as e:
            logger.error(f"Failed to query Dpiù stores API: {e}")
            return []
            
        stores_list = []
        if lat is not None and lon is not None:
            for s in stores:
                gps = s.get("gpsCoordinates")
                if gps and isinstance(gps, dict):
                    s_lat = gps.get("latitude")
                    s_lon = gps.get("longitude")
                    if s_lat is not None and s_lon is not None:
                        dist = self._haversine_distance(lat, lon, float(s_lat), float(s_lon))
                        s["distance"] = dist
                        stores_list.append(s)
            stores_list.sort(key=lambda x: x.get("distance", float("inf")))
            
            return [{
                "id": s.get("alias", ""),
                "name": s.get("name", "Dpiù Store"),
                "address": s.get("address", ""),
                "city": s.get("city", ""),
                "distance": s.get("distance")
            } for s in stores_list if s.get("distance", float("inf")) <= self.radius]
        else:
            matching = []
            for s in stores:
                alias = s.get("alias", "")
                name = s.get("name", "")
                address = s.get("address", "")
                city = s.get("city", "")
                
                if (store_id.lower() in alias.lower() or 
                    store_id.lower() in name.lower() or 
                    store_id.lower() in address.lower() or 
                    store_id.lower() in city.lower()):
                    matching.append({
                        "id": alias,
                        "name": name,
                        "address": address,
                        "city": city,
                        "distance": None
                    })
            return matching

    def discover_flyers(self, store_code: str) -> List[Dict[str, Any]]:
        """
        Retrieves active promotions list/flyers for the store code.
        """
        return [{
            "id": store_code,
            "title": f"All Active Promotions for {store_code}",
            "validity": "Current Catalog",
            "featured": True
        }]

    def _resolve_store_alias(self, store_id: str, bearer_token: str) -> str:
        """
        Resolves direct store alias, coordinates, or city name, and matches
        to the closest/first Dpiù physical store.
        Contains absolutely no console prompts or user interaction.
        
        Args:
            store_id: Search query or coordinates.
            bearer_token: Valid JWT token for authentication.
            
        Returns:
            Resolved Dpiù store alias string.
        """
        lat, lon = None, None

        coords_match = self.COORDINATES_REGEX.match(store_id)
        if coords_match:
            lat = float(coords_match.group(1))
            lon = float(coords_match.group(2))
        else:
            if store_id.lower().startswith("d-"):
                return store_id.lower()
            coords = self._geocode_location(store_id)
            if coords:
                lat, lon = coords

        url = "https://dpiu.maxidi.it/digitalflyer/api/maxidi/dpiu/stores?size=500"
        headers = {"Authorization": f"Bearer {bearer_token}"}
        
        try:
            res = self._session.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            stores = res.json()
        except Exception as e:
            logger.error(f"Failed to query Dpiù stores API: {e}")
            stores = []

        if not stores:
            return "d-cesena"

        if lat is not None and lon is not None:
            stores_with_distance = []
            for s in stores:
                gps = s.get("gpsCoordinates")
                if gps and isinstance(gps, dict):
                    s_lat = gps.get("latitude")
                    s_lon = gps.get("longitude")
                    if s_lat is not None and s_lon is not None:
                        dist = self._haversine_distance(lat, lon, float(s_lat), float(s_lon))
                        s["distance"] = dist
                        stores_with_distance.append(s)

            stores_with_distance.sort(key=lambda x: x.get("distance", float("inf")))
            if stores_with_distance:
                alias = stores_with_distance[0].get("alias", "d-cesena")
                logger.info(f"Resolved store alias to closest store: '{alias}'")
                return alias

        for s in stores:
            alias = s.get("alias", "")
            if alias.lower() == store_id.lower():
                return alias

        for s in stores:
            name = s.get("name", "")
            address = s.get("address", "")
            city = s.get("city", "")
            if (store_id.lower() in name.lower() or 
                store_id.lower() in address.lower() or 
                store_id.lower() in city.lower()):
                alias = s.get("alias", "d-cesena")
                logger.info(f"Resolved store alias via search: '{alias}'")
                return alias

        return store_id

    def fetch_promotions(self, store_id: str) -> Any:
        """
        Authenticates and retrieves all raw promotion active catalog structures and elements
        for the resolved store alias.
        
        Args:
            store_id: Target store coordinates, query, or alias.
            
        Returns:
            Dictionary payload containing resolved store ID and active product listings.
        """
        try:
            token = self._get_bearer_token()
            self._session.headers.update({"Authorization": f"Bearer {token}"})
        except Exception as e:
            logger.error(f"Could not authenticate Dpiù scraper: {e}")
            return None

        store_alias = self._resolve_store_alias(store_id, token)

        promos_url = f"https://dpiu.maxidi.it/digitalflyer/api/maxidi/dpiu/stores/{store_alias}/promotions"
        logger.info(f"Fetching active promotions list for store: {store_alias}")
        
        try:
            res = self._session.get(promos_url, timeout=15)
            res.raise_for_status()
            promos = res.json()
            
            if not promos:
                logger.warning(f"No promotions found for store: {store_alias}")
                return []
                
            active_promos = [p for p in promos if not p.get("hidden", False)]
            logger.info(f"Found {len(active_promos)} active Dpiù promotions.")
            
            if self.max_flyers is not None and self.max_flyers > 0:
                logger.info(f"Limiting flyer scrapes to max: {self.max_flyers}")
                active_promos = active_promos[:self.max_flyers]
                
            all_products_raw = []
            
            for p in active_promos:
                promo_alias = p.get("alias")
                logger.info(f"Scraping products for flyer promotion: '{p.get('description')}' (Alias: {promo_alias})")
                
                page = 0
                size = 100
                while True:
                    url = (
                        f"https://dpiu.maxidi.it/digitalflyer/api/maxidi/dpiu/promotions/{promo_alias}"
                        f"/stores/{store_alias}/products?size={size}&page={page}"
                    )
                    logger.debug(f"GET {url}")
                    p_res = self._session.get(url, timeout=15)
                    p_res.raise_for_status()
                    p_data = p_res.json()
                    
                    elements = p_data.get("elements", [])
                    all_products_raw.extend(elements)
                    logger.info(f"Retrieved {len(elements)} products from Page {page + 1}.")
                    
                    if p_data.get("last", True) or not elements:
                        break
                    page += 1
                    
            logger.info(f"ETL Extraction complete. Discovered {len(all_products_raw)} raw Dpiù product elements.")
            return {"store_id": store_alias, "products": all_products_raw}
            
        except Exception as e:
            logger.error(f"Failed to extract Dpiù REST API promotions: {e}")
            return None

    def parse_promotions(self, raw_data: Any, store_id: str) -> List[ProductOffer]:
        """
        Parses raw product items into normalized validated Pydantic ProductOffer models.
        
        Args:
            raw_data: Payload dictionary containing store_id and raw product listings.
            store_id: Supermarket store identifier.
            
        Returns:
            A list of validated ProductOffer objects.
        """
        if not raw_data or not isinstance(raw_data, dict):
            logger.error("Invalid raw data structure provided. Expected a dictionary containing store_id and products list.")
            return []
            
        active_store_id = raw_data.get("store_id", store_id)
        products_list = raw_data.get("products", [])
        
        parsed_offers: List[ProductOffer] = []
        
        for idx, item in enumerate(products_list):
            try:
                offer = self._parse_single_product(item, active_store_id)
                if offer:
                    parsed_offers.append(offer)
            except Exception as e:
                logger.warning(f"Error parsing Dpiù raw item at index {idx}: {e}")
                
        logger.info(f"Successfully normalized and validated {len(parsed_offers)} out of {len(products_list)} Dpiù product offers.")
        return parsed_offers

    def _parse_property(self, properties: List[Dict[str, Any]], code: str) -> Optional[Any]:
        """Helper method to extract the first value of a property from the list by its code."""
        for prop in properties:
            if prop.get("code") == code:
                vals = prop.get("values")
                if vals and isinstance(vals, list):
                    return vals[0]
                elif prop.get("content") is not None:
                    return prop.get("content")
        return None

    def _parse_single_product(self, item: Dict[str, Any], store_id: str) -> Optional[ProductOffer]:
        """Converts a single Dpiù product JSON element into a standard validated ProductOffer model."""
        description = item.get("description", "") or ""
        properties = item.get("properties", [])
        
        title = self._parse_property(properties, "TITLE") or ""
        brand = self._parse_property(properties, "BRANDS") or title
        
        clean_desc = " ".join(description.split())
        
        if not clean_desc:
            logger.debug("Skipping product missing description.")
            return None
            
        ean_code = self._parse_property(properties, "EAN")
        if ean_code:
            ean_code = str(ean_code).strip()
            
        weight_str = None
        weight_match = self._weight_regex.search(clean_desc)
        if weight_match:
            weight_str = weight_match.group(1).strip()
        else:
            dimension = self._parse_property(properties, "DIMENSION")
            m_unit = self._parse_property(properties, "MEASURE-UNIT")
            if dimension is not None:
                weight_str = f"{dimension} {str(m_unit or '').lower()}".strip()

        name_str = clean_desc
        if brand:
            name_str = re.sub(r"\b" + re.escape(brand) + r"\b", "", name_str, flags=re.IGNORECASE)
        if weight_str:
            name_str = re.sub(re.escape(weight_str), "", name_str, flags=re.IGNORECASE)
            
        name_str = re.sub(r"[,\.\:\;\_\#\-\*]", "", name_str)
        name_str = " ".join(name_str.split()).strip().capitalize()
        
        if not name_str:
            name_str = clean_desc.replace("\n", " ").strip()

        price = self._parse_property(properties, "END-PRICE")
        if price is None:
            logger.debug(f"Skipping product '{name_str}' because final price is missing.")
            return None
            
        price = float(price)
        original_price = self._parse_property(properties, "INITIAL-PRICE")
        if original_price is not None:
            original_price = float(original_price)
            if original_price <= price:
                original_price = None
                
        discount_percent = self._parse_property(properties, "DISCOUNT-RATE")
        if discount_percent is not None:
            discount_percent = int(float(discount_percent))
        elif original_price and original_price > 0:
            discount_percent = int(round((1.0 - (price / original_price)) * 100))

        unit_price = self._parse_property(properties, "END-KG-LT-PRICE")
        unit_price_str = None
        if unit_price is not None:
            m_unit = str(self._parse_property(properties, "MEASURE-UNIT") or "KG").lower()
            unit_price_str = f"€/{m_unit} {float(unit_price):.2f}"

        promo_code = self._parse_property(properties, "DISCOUNT") or "STANDARD"
        promo_type = "STANDARD"
        if promo_code == "UPU" or "1+1" in clean_desc or "bogo" in clean_desc.lower():
            promo_type = "1+1"
        elif discount_percent:
            promo_type = "PERCENTAGE_DISCOUNT"

        start_date_raw = self._parse_property(properties, "START-DATE-VALIDITY")
        end_date_raw = self._parse_property(properties, "END-DATE-VALIDITY")
        validity_string = None
        
        if start_date_raw and end_date_raw:
            try:
                s_dt = datetime.strptime(str(start_date_raw)[:8], "%Y%m%d")
                e_dt = datetime.strptime(str(end_date_raw)[:8], "%Y%m%d")
                validity_string = f"DAL {s_dt.strftime('%d/%m/%Y')} AL {e_dt.strftime('%d/%m/%Y')}"
            except Exception:
                pass

        category = self._parse_property(properties, "DEPARTMENT")

        image_url = None
        for prop in properties:
            if prop.get("code") == "IMAGES":
                vals = prop.get("values", [])
                if vals and isinstance(vals, list):
                    img = vals[0]
                    u_id = img.get("uniqueId")
                    f_name = img.get("name")
                    if u_id and f_name:
                        image_url = f"https://dpiu.maxidi.it/digitalflyer/api/files/{u_id}/{f_name}"
                        break

        unique_payload = f"DPIU:{store_id}:{validity_string or 'ALL'}:{name_str}:{price:.2f}"
        offer_id = hashlib.sha256(unique_payload.encode("utf-8")).hexdigest()[:32]

        return ProductOffer(
            offer_id=offer_id,
            supermarket="DPIU",
            store_id=store_id,
            name=name_str,
            brand=brand if brand else None,
            weight_or_volume=weight_str,
            price=price,
            original_price=original_price,
            discount_percentage=discount_percent,
            price_per_unit=unit_price_str,
            ean_code=ean_code,
            image_url=image_url,
            category=category,
            promo_type=promo_type,
            validity_string=validity_string
        )
