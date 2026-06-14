"""
Coop Alleanza 3.0 Scraper Strategy Driver.

Fetches promotional offers dynamically from Coop APIs, resolves store locations
via geocoding or coordinate proximity search, and parses the response structure.
"""

import re
import requests
from typing import Dict, Any, List, Optional, Tuple
from core.base_driver import AbstractApiSupermarketDriver
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("CoopDriver")


class CoopSupermarketDriver(AbstractApiSupermarketDriver):
    """
    Supermarket scraper driver for Coop Alleanza 3.0.
    Fetches dynamic promotional data via REST API endpoints and parses
    Server-Driven UI layout nodes into normalized domain models.
    """

    def __init__(
        self,
        base_url: str = "https://svdgt.coopalleanza3-0.it",
        radius: int = 15,
        choose_store: bool = False,
        choose_flyer: bool = False,
        selected_flyer_ids: Optional[List[str]] = None
    ) -> None:
        """
        Initializes the Coop driver with configuration and request session details.
        
        Args:
            base_url: Base domain URL of the Coop API server.
            radius: Proximity search radius in kilometers.
            choose_store: Unused parameter preserved for interface compliance.
            choose_flyer: Unused parameter preserved for interface compliance.
            selected_flyer_ids: Optional list of flyer IDs to target exclusively.
        """
        super().__init__(radius=radius, choose_store=choose_store, choose_flyer=choose_flyer)
        self._base_url = base_url.rstrip("/")
        self._resolved_store_code: Optional[str] = None
        self.selected_flyer_ids = selected_flyer_ids
        
        # Override referer & origin specific to Coop
        self._session.headers.update({
            "Origin": "https://www.coop.it",
            "Referer": "https://www.coop.it/ricerca-negozi"
        })
        
        # Compiled Regex patterns
        self._price_regex = re.compile(r"(\d+,\d{2})\s*€")
        self._discount_regex = re.compile(r"(\d+)\s*%")

    def _fetch_csrf_token(self) -> None:
        """Attempts to retrieve a session CSRF token from coop.it."""
        try:
            res = self._session.get("https://www.coop.it/session/token", timeout=10)
            if res.status_code == 200:
                token = res.text.strip()
                if token:
                    self._session.headers.update({"X-Csrf-Token": token})
                    logger.debug("Successfully retrieved CSRF token.")
        except Exception as e:
            logger.warning(f"Failed to fetch session CSRF token: {e}")

    def _search_stores_by_coords(self, lat: float, lon: float) -> List[Dict[str, Any]]:
        """
        Queries the Coop store search API using coordinates.
        
        Args:
            lat: Latitude.
            lon: Longitude.
            
        Returns:
            List of store dictionaries from Coop search API.
        """
        search_url = "https://www.coop.it/api/esb/storelocator/searchStores?_format=form"
        payload = {"coords": {"latitude": lat, "longitude": lon}, "storeName": None}
        try:
            res = self._session.post(search_url, json=payload, timeout=12)
            res.raise_for_status()
            data = res.json()
            return data.get("payload", {}).get("stores", [])
        except Exception as e:
            logger.error(f"Failed to query Coop store locator search stores API: {e}")
        return []

    def _resolve_store_details_by_db_id(self, db_id: int) -> Tuple[Optional[str], str]:
        """
        Resolves the store details via getStoreDetail API.
        
        Args:
            db_id: Database unique identifier for Coop store.
            
        Returns:
            A tuple of (store_code, store_name).
        """
        detail_url = "https://www.coop.it/api/esb/storelocator/getStoreDetail?_format=form"
        payload = {"storeId": [db_id]}
        try:
            res = self._session.post(detail_url, json=payload, timeout=12)
            res.raise_for_status()
            data = res.json()
            stores = data.get("payload", {}).get("stores", [])
            if stores:
                store = stores[0]
                code = store.get("codicePDVCooperativa")
                name = store.get("name", "Coop Store")
                if code is not None:
                    return str(code).zfill(4), name
                return None, name
        except Exception as e:
            logger.error(f"Failed to resolve Coop store details for ID {db_id}: {e}")
        return None, "Coop Store"

    def _fetch_leaflets_for_store(self, store_code: str) -> List[Dict[str, Any]]:
        """
        Retrieves active flyer leaflet metadata for the given store code.
        
        Args:
            store_code: Canonical 4-digit store code.
            
        Returns:
            List of leaflets.
        """
        leaflets_url = f"{self._base_url}/apim/leaflets/{store_code}"
        try:
            res = self._session.get(leaflets_url, timeout=12)
            res.raise_for_status()
            data = res.json()
            return data.get("leaflets", [])
        except Exception as e:
            logger.error(f"Failed to retrieve flyer leaflets list from Coop API: {e}")
        return []

    def _fetch_promos_for_leaflet(self, leaflet_id: str, store_code: str) -> List[Dict[str, Any]]:
        """
        Retrieves promotion items for the specified leaflet ID and store code.
        
        Args:
            leaflet_id: Leaflet catalog identifier.
            store_code: Target store code.
            
        Returns:
            List of promo items.
        """
        promos_url = f"{self._base_url}/apim/{leaflet_id}/{store_code}/promos"
        try:
            res = self._session.get(promos_url, timeout=15)
            res.raise_for_status()
            data = res.json()
            return data.get("promos", [])
        except Exception as e:
            logger.error(f"Failed to retrieve promotions list from Coop API: {e}")
        return []

    def discover_stores(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Discovers Coop stores matching the query coordinates or location name.
        
        Args:
            store_id: Coordinates query ('lat,lon') or city name query.
            
        Returns:
            A list of discovered store dictionaries.
        """
        self._fetch_csrf_token()
        
        # Check if coordinates (lat, lon)
        coords_match = self.COORDINATES_REGEX.match(store_id)
        lat, lon = None, None
        
        if coords_match:
            lat = float(coords_match.group(1))
            lon = float(coords_match.group(2))
        elif store_id.isdigit():
            if len(store_id) <= 4:
                # Direct code: return it directly
                return [{"id": store_id.zfill(4), "name": f"Coop Code: {store_id}", "address": "", "city": "", "distance": 0.0}]
            else:
                code, name = self._resolve_store_details_by_db_id(int(store_id))
                if code:
                    return [{"id": code, "name": name, "address": "", "city": "", "distance": 0.0}]
                return [{"id": store_id, "name": name, "address": "", "city": "", "distance": None}]
        else:
            coords = self._geocode_location(store_id)
            if coords:
                lat, lon = coords
                
        if lat is not None and lon is not None:
            stores = self._search_stores_by_coords(lat, lon)
            stores_list = []
            for s in stores:
                coop_db_id = s.get("id")
                stores_list.append({
                    "id": str(coop_db_id),
                    "name": s.get("name"),
                    "address": s.get("address"),
                    "city": s.get("city"),
                    "distance": float(s.get("distance", 0)) / 1000.0 if s.get("distance") is not None else 0.0
                })
            return stores_list
            
        return [{"id": store_id, "name": f"Coop Store {store_id}", "address": "", "city": "", "distance": None}]

    def discover_flyers(self, store_code: str) -> List[Dict[str, Any]]:
        """
        Retrieves active flyers/leaflets for the store code.
        
        Args:
            store_code: Target store code.
            
        Returns:
            List of flyer dictionaries.
        """
        leaflets = self._fetch_leaflets_for_store(store_code)
        flyers = []
        for lf in leaflets:
            flyers.append({
                "id": str(lf.get("id")),
                "title": lf.get("titolo", "Coop Flyer"),
                "validity": lf.get("pretty_name_validita", ""),
                "featured": bool(lf.get("featured"))
            })
        return flyers

    def fetch_promotions(self, store_id: str) -> Any:
        """
        Fetches promotions for the resolved store ID (or store code) and selected flyers.
        Contains absolutely no console prompts or user interaction.
        
        Args:
            store_id: Target store identifier or resolved code.
            
        Returns:
            List of raw promotion items.
        """
        self._fetch_csrf_token()
        store_code = store_id
        
        if store_id.isdigit() and len(store_id) > 4:
            code, _ = self._resolve_store_details_by_db_id(int(store_id))
            if code:
                store_code = code
        elif not store_id.isdigit() or len(store_id) <= 4:
            coords_match = self.COORDINATES_REGEX.match(store_id)
            lat, lon = None, None
            if coords_match:
                lat = float(coords_match.group(1))
                lon = float(coords_match.group(2))
            else:
                coords = self._geocode_location(store_id)
                if coords:
                    lat, lon = coords
            
            if lat is not None and lon is not None:
                stores = self._search_stores_by_coords(lat, lon)
                if stores:
                    coop_db_id = stores[0].get("id")
                    code, _ = self._resolve_store_details_by_db_id(coop_db_id)
                    if code:
                        store_code = code
                        
        if not store_code:
            logger.error(f"Could not resolve store code for store reference: {store_id}")
            return []
            
        self._resolved_store_code = store_code
        
        leaflets = self._fetch_leaflets_for_store(store_code)
        if not leaflets:
            logger.warning(f"No flyer leaflets found for store: {store_code}")
            return []
            
        selected_leaflets = leaflets
        if self.selected_flyer_ids:
            selected_leaflets = [lf for lf in leaflets if str(lf.get("id")) in self.selected_flyer_ids]
            
        all_promos = []
        for lf in selected_leaflets:
            leaf_id = lf.get("id")
            leaf_title = lf.get("titolo")
            logger.info(f"Fetching promos for flyer: '{leaf_title}' (ID: {leaf_id})")
            promos = self._fetch_promos_for_leaflet(leaf_id, store_code)
            all_promos.extend(promos)
            
        return all_promos

    def parse_promotions(self, raw_data: Any, store_id: str) -> List[ProductOffer]:
        """
        Parses raw items into normalized validated Pydantic ProductOffer models.
        
        Args:
            raw_data: A list of raw promo item dicts.
            store_id: The active store identifier.
            
        Returns:
            A list of validated ProductOffer objects.
        """
        if not isinstance(raw_data, list):
            logger.error("Invalid raw data structure provided. Expected a list of dictionaries.")
            return []
            
        parsed_offers: List[ProductOffer] = []
        
        for idx, item in enumerate(raw_data):
            try:
                offer = self._parse_single_item(item, store_id)
                if offer:
                    parsed_offers.append(offer)
            except Exception as e:
                logger.warning(f"Error parsing raw item at index {idx}: {e}")
                
        logger.info(f"Parsed {len(parsed_offers)} out of {len(raw_data)} Coop promo items.")
        return parsed_offers

    def _parse_single_item(self, item: Dict[str, Any], store_id: str) -> Optional[ProductOffer]:
        """Parses a single raw promo item dictionary."""
        actual_store_id = getattr(self, "_resolved_store_code", None) or store_id
        offer_id = item.get("id")
        if not offer_id:
            logger.warning("Skipping promo item missing unique ID.")
            return None
            
        name = item.get("desc_promo")
        if not name:
            logger.warning(f"Skipping promo item {offer_id} missing descriptive name.")
            return None
            
        brand = item.get("brand")
        weight = item.get("desc_promo2")
        category = item.get("categoryCode")
        image_url = item.get("img")
        validity = item.get("promo_pretty_name_validita")
        
        ean_code = None
        products = item.get("prodotti", [])
        if products and isinstance(products, list):
            ean_code = str(products[0])
            
        price, original_price, discount_percent, unit_price = self._parse_pricing_layout(item)
        
        if price is None:
            logger.debug(f"Skipping offer {offer_id} ('{name}') because no valid price could be parsed.")
            return None
            
        promo_type = "STANDARD"
        collezioni = item.get("collezioni") or []
        
        is_soci = "soci" in collezioni
        if not is_soci:
            layout_keys = ["CXTop", "CXBottom", "SXTop", "SXBottom", "DXTop", "DXBottom"]
            for k in layout_keys:
                node = item.get(k)
                if node and isinstance(node, dict):
                    txt_lines = node.get("txt") or []
                    for line in txt_lines:
                        if line and any(w in line.lower() for w in ["socio", "soci"]):
                            is_soci = True
                            break
                            
        if is_soci:
            promo_type = "PREZZO_SOCIO"
        elif discount_percent is not None:
            promo_type = "PERCENTAGE_DISCOUNT"
        elif original_price is not None:
            promo_type = "DISCOUNT"

        return ProductOffer(
            offer_id=offer_id,
            supermarket="COOP",
            store_id=actual_store_id,
            name=name,
            brand=brand,
            weight_or_volume=weight,
            price=price,
            original_price=original_price,
            discount_percentage=discount_percent,
            price_per_unit=unit_price,
            ean_code=ean_code,
            image_url=image_url,
            category=category,
            promo_type=promo_type,
            validity_string=validity
        )

    def _parse_pricing_layout(
        self, item: Dict[str, Any]
    ) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[str]]:
        """
        Scans layout keys and extracts prices, discount percentages, and unit pricing.
        Uses GDO heuristics: if two prices exist, the smaller is the promo price.
        
        Returns:
            Tuple: (promo_price, original_price, discount_percentage, unit_price)
        """
        layout_keys = ["CXTop", "CXBottom", "SXTop", "SXBottom", "DXTop", "DXBottom"]
        
        prices_found: List[float] = []
        discount_percent: Optional[int] = None
        unit_price_str: Optional[str] = None
        
        for key in layout_keys:
            node = item.get(key)
            if not node or not isinstance(node, dict):
                continue
                
            text_lines = node.get("txt") or []
            for line in text_lines:
                if not line or not isinstance(line, str):
                    continue
                    
                line_clean = line.replace("\u20ac", "€").strip()
                
                if "al kg" in line_clean or "al lt" in line_clean or "al pz" in line_clean:
                    unit_price_str = line_clean
                    continue
                    
                disc_match = self._discount_regex.search(line_clean)
                if disc_match and "%" in line_clean:
                    discount_percent = int(disc_match.group(1))
                    
                price_matches = self._price_regex.findall(line_clean)
                for price_str in price_matches:
                    try:
                        price_float = float(price_str.replace(",", "."))
                        if price_float not in prices_found:
                            prices_found.append(price_float)
                    except ValueError:
                        pass
                        
        promo_price: Optional[float] = None
        original_price: Optional[float] = None
        
        if len(prices_found) == 1:
            promo_price = prices_found[0]
        elif len(prices_found) >= 2:
            sorted_prices = sorted(prices_found)
            promo_price = sorted_prices[0]
            original_price = sorted_prices[1]
            
            if discount_percent is None and original_price > 0:
                discount_percent = int(round((1.0 - (promo_price / original_price)) * 100))
                
        return promo_price, original_price, discount_percent, unit_price_str
