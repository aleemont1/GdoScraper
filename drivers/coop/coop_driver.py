import re
import requests
import sys
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
        choose_flyer: bool = False
    ) -> None:
        """
        Initializes the Coop driver with configuration and request session details.
        """
        super().__init__(radius=radius, choose_store=choose_store, choose_flyer=choose_flyer)
        self._base_url = base_url.rstrip("/")
        self._resolved_store_code: Optional[str] = None
        
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
        """Queries the Coop store search API using coordinates."""
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
        """Resolves the store detail details via getStoreDetail API, returning (store_code, name)."""
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
                # format as 4-digit store code if numeric
                if code is not None:
                    return str(code).zfill(4), name
                return None, name
        except Exception as e:
            logger.error(f"Failed to resolve Coop store details for ID {db_id}: {e}")
        return None, "Coop Store"

    def _fetch_leaflets_for_store(self, store_code: str) -> List[Dict[str, Any]]:
        """Retrieves active flyer leaflet metadata for the given store code."""
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
        """Retrieves promotion items for the specified leaflet ID and store code."""
        promos_url = f"{self._base_url}/apim/{leaflet_id}/{store_code}/promos"
        try:
            res = self._session.get(promos_url, timeout=15)
            res.raise_for_status()
            data = res.json()
            return data.get("promos", [])
        except Exception as e:
            logger.error(f"Failed to retrieve promotions list from Coop API: {e}")
        return []

    def fetch_promotions(self, store_id: str) -> Any:
        """
        Interactively resolves Coop store ID (from coords, city name, or direct ID),
        discovers available flyers, prompts for flyer selection if requested,
        and retrieves promotional data via APIs.
        """
        self._fetch_csrf_token()
        
        store_code = None
        store_name_resolved = "Unknown Coop Store"
        
        # Check coordinates first
        coords_match = self.COORDINATES_REGEX.match(store_id)
        
        lat, lon = None, None
        
        if coords_match:
            lat = float(coords_match.group(1))
            lon = float(coords_match.group(2))
        elif store_id.isdigit() and len(store_id) <= 4:
            store_code = store_id.zfill(4)
            logger.info(f"Using direct Coop store code: '{store_code}'")
        elif store_id.isdigit() and len(store_id) > 4:
            coop_db_id = int(store_id)
            logger.info(f"Using direct Coop database store ID: {coop_db_id}")
            store_code, store_name_resolved = self._resolve_store_details_by_db_id(coop_db_id)
        else:
            coords = self._geocode_location(store_id)
            if coords:
                lat, lon = coords
            else:
                logger.error(f"Could not resolve city or location '{store_id}' to coordinates.")
                return []
                
        # Search stores by coordinates if coordinates were resolved or passed
        if lat is not None and lon is not None:
            stores = self._search_stores_by_coords(lat, lon)
            if not stores:
                logger.error(f"No Coop stores found within {self.radius}km around ({lat}, {lon})")
                return []
                
            selected_store = None
            if self.choose_store and len(stores) > 1:
                if not sys.stdin.isatty():
                    logger.warning("Non-interactive terminal detected. Defaulting to the closest Coop store.")
                    selected_store = stores[0]
                else:
                    print(f"\nDiscovered {len(stores)} Coop stores within {self.radius} km:")
                    selected_store = self._prompt_selection(
                        stores,
                        display_func=lambda s: f"{s.get('name')} - {s.get('address')}, {s.get('city')} [{s.get('distance')} m]",
                        prompt="Select a store"
                    )
            else:
                selected_store = stores[0]
                
            coop_db_id = selected_store.get("id")
            logger.info(f"Target Store Resolved: {selected_store.get('name')} - {selected_store.get('address')} (Distance: {selected_store.get('distance')} m)")
            store_code, store_name_resolved = self._resolve_store_details_by_db_id(coop_db_id)
            
        if not store_code:
            logger.error("Could not resolve a valid Coop store code.")
            return []
            
        # Cache canonical store code
        self._resolved_store_code = store_code
        
        # 2. Retrieve active leaflets
        leaflets = self._fetch_leaflets_for_store(store_code)
        if not leaflets:
            logger.warning(f"No promotional leaflets found for store: {store_name_resolved} (code: {store_code})")
            return []
            
        # 3. Filter/Choose leaflets
        selected_leaflets = []
        if self.choose_flyer and len(leaflets) > 1:
            if not sys.stdin.isatty():
                logger.warning("Non-interactive terminal detected. Defaulting to the first flyer to prevent massive automated downloads.")
                selected_leaflets = leaflets[:1]
            else:
                print(f"\nAvailable promotional flyers for {store_name_resolved} ({store_code}):")
                for idx, lf in enumerate(leaflets):
                    featured_str = " (Featured)" if lf.get("featured") else ""
                    print(f"  {idx+1}) {lf.get('titolo')}{featured_str} [Validity: {lf.get('pretty_name_validita')}] (ID: {lf.get('id')})")
                
                while True:
                    try:
                        user_input = input(f"Select flyer(s) to scrape (comma-separated indices, e.g. 1,3 or 'all', default: all): ").strip()
                        if not user_input or user_input.lower() == "all":
                            selected_leaflets = leaflets
                            break
                        
                        indices = [int(i.strip()) for i in user_input.split(",") if i.strip().isdigit()]
                        valid_indices = [i - 1 for i in indices if 0 <= i - 1 < len(leaflets)]
                        if valid_indices:
                            selected_leaflets = [leaflets[i] for i in valid_indices]
                            break
                        else:
                            print("Invalid selection. Please try again.")
                    except ValueError:
                        print("Invalid input format. Use numbers separated by commas.")
                    except (KeyboardInterrupt, EOFError):
                        print("\nSelection interrupted. Defaulting to all flyers.")
                        selected_leaflets = leaflets
                        break
        else:
            selected_leaflets = leaflets
            
        # 4. Fetch promos for each selected leaflet
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
        """
        Parses a single promotion item dictionary.
        """
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
        
        # Check EAN code inside the products list
        ean_code = None
        products = item.get("prodotti", [])
        if products and isinstance(products, list):
            ean_code = str(products[0])
            
        # Pricing layout scanner
        price, original_price, discount_percent, unit_price = self._parse_pricing_layout(item)
        
        if price is None:
            logger.debug(f"Skipping offer {offer_id} ('{name}') because no valid price could be parsed.")
            return None
            
        # Determine promotion classification type
        promo_type = "STANDARD"
        collezioni = item.get("collezioni") or []
        
        # Check for price for members ("soci")
        is_soci = "soci" in collezioni
        if not is_soci:
            # Check if any layout node explicitly states it's for Coop Members
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
                
                # Extract unit price (e.g. "5,16 € al kg" or "10,00 € al lt")
                if "al kg" in line_clean or "al lt" in line_clean or "al pz" in line_clean:
                    unit_price_str = line_clean
                    continue
                    
                # Extract discount percentage (e.g. "sconto 30%" or "-30%")
                disc_match = self._discount_regex.search(line_clean)
                if disc_match and "%" in line_clean:
                    discount_percent = int(disc_match.group(1))
                    
                # Extract generic prices
                price_matches = self._price_regex.findall(line_clean)
                for price_str in price_matches:
                    try:
                        price_float = float(price_str.replace(",", "."))
                        if price_float not in prices_found:
                            prices_found.append(price_float)
                    except ValueError:
                        pass
                        
        # GDO price resolving logic
        promo_price: Optional[float] = None
        original_price: Optional[float] = None
        
        if len(prices_found) == 1:
            promo_price = prices_found[0]
        elif len(prices_found) >= 2:
            # GDO Heuristic: Smaller price is the promo price, larger is original pre-discount price
            sorted_prices = sorted(prices_found)
            promo_price = sorted_prices[0]
            original_price = sorted_prices[1]
            
            # Recalculate discount percent if missing
            if discount_percent is None and original_price > 0:
                discount_percent = int(round((1.0 - (promo_price / original_price)) * 100))
                
        return promo_price, original_price, discount_percent, unit_price_str
