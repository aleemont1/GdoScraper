import re
import requests
from typing import Dict, Any, List, Optional, Tuple
from core.base_driver import AbstractSupermarketDriver
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("CoopDriver")

class CoopSupermarketDriver(AbstractSupermarketDriver):
    """
    Supermarket scraper driver for Coop Alleanza 3.0.
    Fetches dynamic promotional data via REST API endpoints and parses
    Server-Driven UI layout nodes into normalized domain models.
    """

    def __init__(self, base_url: str = "https://svdgt.coopalleanza3-0.it") -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        
        # Configure standard headers to simulate a real browser request
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.coopalleanza3-0.it",
            "Referer": "https://www.coopalleanza3-0.it/",
        })
        
        # Compiled Regex patterns
        self._price_regex = re.compile(r"(\d+,\d{2})\s*€")
        self._discount_regex = re.compile(r"(\d+)\s*%")

    def fetch_promotions(self, store_id: str) -> Any:
        """
        Fetches promotional offers for the given store.
        Note: The Coop API returns the entire catalog of promotions in a single request.
        
        Args:
            store_id: The Coop store identifier (e.g., '0315').
            
        Returns:
            A list of raw promotional item dictionaries.
        """
        endpoint = f"{self._base_url}/apim/P2611IS/{store_id}/promos"
        logger.info(f"Fetching promotions from Coop API for store: {store_id}")
        
        try:
            # Query the endpoint directly; it returns the whole catalog
            response = self._session.get(endpoint, timeout=15)
            
            # Check for HTTP errors (e.g. 404 store not found, or 401/403 blocks)
            response.raise_for_status()
            data = response.json()
            
            promos_list = data.get("promos", [])
            logger.info(f"Successfully retrieved {len(promos_list)} raw promotional items.")
            return promos_list
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network request failed for store {store_id}: {e}")
        except ValueError as e:
            logger.error(f"Failed to parse JSON response for store {store_id}: {e}")
            
        return []

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
            store_id=store_id,
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
