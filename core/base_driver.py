"""
Base driver module for GDO Supermarket Scrapers.

Defines the abstract base classes and shared utility methods for coordinate geocoding,
distance calculations, HTTP session management, and parsing interfaces.
Follows the Strategy Pattern to decouple chain-specific scraping logic from the runner.
"""

import re
import os
import math
import requests
from abc import ABC, abstractmethod
from typing import List, Any, Optional, Dict, Tuple
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("BaseDriver")


class AbstractSupermarketDriver(ABC):
    """
    Abstract base class defining the standard interface for supermarket scrapers.
    Follows the Strategy Pattern to decouple parsing strategies from execution.
    Contains unified helper methods for geocoding, distance, and session initialization.
    """

    # Class-level compiled coordinates detector regex
    COORDINATES_REGEX = re.compile(
        r"^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$"
    )

    @abstractmethod
    def fetch_promotions(self, store_id: str) -> Any:
        """
        Fetches the raw promotion data (JSON, HTML, PDF content, etc.) from the source.

        Args:
            store_id: Identifier of the target supermarket store.

        Returns:
            Raw promotion data.
        """
        pass

    @abstractmethod
    def parse_promotions(self, raw_data: Any, store_id: str) -> List[ProductOffer]:
        """
        Parses raw promotion data into a list of normalized ProductOffer objects.

        Args:
            raw_data: Raw promotion data fetched from the source.
            store_id: Identifier of the target store.

        Returns:
            List of normalized ProductOffer objects.
        """
        pass

    def run_etl(self, store_id: str) -> List[ProductOffer]:
        """
        Executes the full ETL extraction pipeline for the given store.

        Args:
            store_id: Target store identifier.

        Returns:
            List of successfully extracted and validated ProductOffer objects.
        """
        try:
            raw_data = self.fetch_promotions(store_id)
            if not raw_data:
                return []
            return self.parse_promotions(raw_data, store_id)
        except Exception as e:
            logger.error(
                f"Failed to execute ETL process for store {store_id}: {e}",
                exc_info=True,
            )
            return []

    def discover_stores(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Discovers stores matching the given store query or coordinates.
        By default, returns a single placeholder store entry mapping directly to the ID.
        Subclasses should override this to provide proper API store lookup capabilities.

        Args:
            store_id: A city name, coordinates, or store code query.

        Returns:
            A list of discovered store dictionaries containing:
              - 'id': Resolved unique store identifier.
              - 'name': Descriptive name of the store.
              - 'address': Physical address.
              - 'city': City name.
              - 'distance': Distance from search query (if applicable).
        """
        return [
            {
                "id": store_id,
                "name": f"Store {store_id}",
                "address": "Direct Targeting",
                "city": "",
                "distance": None,
            }
        ]

    def discover_flyers(self, store_code: str) -> List[Dict[str, Any]]:
        """
        Discovers active promotional flyer catalogs for the resolved store code.
        Subclasses with visual flyer parsing capabilities should override this.

        Args:
            store_code: Resolved store code.

        Returns:
            A list of flyer dictionaries containing:
              - 'id': Unique flyer catalog identifier (e.g., flyer ID, slug).
              - 'title': Descriptive title of the flyer.
              - 'validity': Human-readable validity period text.
              - 'featured': Boolean indicating if this is a primary featured flyer.
        """
        return []

    # --- SHARED OOP UTILITY METHODS ---

    def _init_session(
        self, headers: Optional[Dict[str, str]] = None
    ) -> requests.Session:
        """
        Initializes a requests.Session with standard browser user-agent headers.

        Args:
            headers: Optional dictionary of headers to override defaults.

        Returns:
            A configured requests.Session object.
        """
        session = requests.Session()
        standard_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            standard_headers.update(headers)
        session.headers.update(standard_headers)
        return session

    def _haversine_distance(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Computes the great-circle distance between two points on the Earth's surface
        using the Haversine formula.

        Args:
            lat1: Latitude of the first point.
            lon1: Longitude of the first point.
            lat2: Latitude of the second point.
            lon2: Longitude of the second point.

        Returns:
            Distance in kilometers.
        """
        R = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c

    def _geocode_location(self, query: str) -> Optional[Tuple[float, float]]:
        """
        Geocodes a city/address query using Photon OSM search API.

        Args:
            query: Location text search query.

        Returns:
            A tuple of (latitude, longitude) or None if geocoding fails.
        """
        logger.info(f"Geocoding '{query}' via Photon OpenStreetMap search...")
        url = f"https://photon.komoot.io/api/?q={query}&limit=1"
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                features = data.get("features", [])
                if features:
                    geom = features[0].get("geometry", {})
                    coords = geom.get("coordinates", [])
                    if len(coords) >= 2:
                        lon, lat = coords[0], coords[1]
                        logger.info(
                            f"Photon resolved '{query}' to coords: ({lat}, {lon})"
                        )
                        return float(lat), float(lon)
            logger.warning(
                f"Photon geocoding failed or returned empty results for '{query}'"
            )
        except Exception as e:
            logger.error(f"Photon geocoding request error: {e}")
        return None

    def _reverse_geocode(
        self, lat: float, lon: float, cache_path: str = "storage/geocode_cache.json"
    ) -> str:
        """
        Reverse geocodes latitude/longitude coordinates to a city name using caching.

        Args:
            lat: Latitude.
            lon: Longitude.
            cache_path: Path to geocode cache JSON file.

        Returns:
            Resolved city/locality name.
        """
        import json

        cache_key = f"{lat},{lon}"
        cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load geocoding cache: {e}")

        if cache_key in cache:
            logger.info(
                f"Geocoding cache hit for coordinates ({lat}, {lon}) -> '{cache[cache_key]}'"
            )
            return cache[cache_key]

        city = None
        # 1. Try OSM Nominatim
        osm_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {"User-Agent": "SupermarketScraper/1.0 (aleemont@example.com)"}
        try:
            res = requests.get(osm_url, headers=headers, timeout=8)
            if res.status_code == 200:
                addr = res.json().get("address", {})
                city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("suburb")
                )
                if city:
                    logger.info(f"Resolved to city: '{city}' via Nominatim")
        except Exception as e:
            logger.warning(f"OSM Nominatim query failed: {e}")

        # 2. Try BigDataCloud reverse geocode client as fallback
        if not city:
            logger.warning("Trying keyless BigDataCloud fallback...")
            bdc_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=it"
            try:
                res = requests.get(
                    bdc_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8
                )
                res.raise_for_status()
                data = res.json()
                city = (
                    data.get("city")
                    or data.get("locality")
                    or data.get("principalSubdivision")
                )
                if city:
                    logger.info(f"Resolved to city: '{city}' via BigDataCloud")
            except Exception as e:
                logger.error(f"BigDataCloud geocoding fallback failed: {e}")

        # Final default fallback if everything fails
        if not city:
            logger.warning(
                "All geocoding lookups failed. Defaulting to 'Cesena' region."
            )
            city = "Cesena"

        # Save to cache
        cache[cache_key] = city
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save geocoding cache: {e}")

        return city


class AbstractApiSupermarketDriver(AbstractSupermarketDriver):
    """
    Abstract base class for REST API-based supermarket scrapers.
    Encapsulates shared HTTP session management and geocoding config parameters.
    """

    def __init__(
        self, radius: int = 15, choose_store: bool = False, choose_flyer: bool = False
    ) -> None:
        """
        Initializes the API driver.

        Args:
            radius: Research radius in kilometers for store discovery.
            choose_store: Whether the store list requires interactive selection.
            choose_flyer: Whether the flyer list requires interactive selection.
        """
        self.radius = radius
        self.choose_store = choose_store
        self.choose_flyer = choose_flyer
        # Initialize session via parent utility method
        self._session = self._init_session()


class AbstractOfferParser(ABC):
    """
    Abstract base class for parsing semantic GDO fields (name, brand, prices, discounts)
    from isolated cell text blocks.
    """

    def __init__(self) -> None:
        """Initializes regex patterns for parsing prices, discounts, weights, and dates."""
        # Compiled Regex patterns (allowing optional spaces around the decimal comma)
        self._price_decimal = re.compile(r"\b(\d+)\s*,\s*(\d{2})\b")
        self._price_separated = re.compile(r"\b(\d+)\s*€\s*,\s*(\d{2})\b")

        self._one_plus_one = re.compile(
            r"1\s+pezzo\s+€\s*(\d+)\s*,\s*(\d{2})\s+2\s+PEZZI\s*(\d+)\s*€\s*,\s*(\d{2})",
            re.IGNORECASE,
        )

        # Compiled split price pattern: captures euros and cents separated by text/symbols
        self._price_split = re.compile(
            r"\b(\d+)\s*€[^\d,]*,\s*(\d{2})\b", re.IGNORECASE
        )

        self._discount_pct = re.compile(r"-(\d+)\s*%")

        # Unit price patterns supporting spaced commas and flexible units
        self._unit_price_patterns = [
            re.compile(
                r"(?:€\s*/\s*|€\s*al\s*|al\s*|/|€\s*cad\s*|cad\s*)(?:kg|l|lt|pz|cad)\s*(\d+)\s*,\s*(\d{2})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(\d+)\s*,\s*(\d{2})\s*(?:€\s*/\s*|/|€\s*cad\s*|cad\s*|€\s+)(?:kg|l|lt|pz|cad)",
                re.IGNORECASE,
            ),
        ]

        # Weight / Volume patterns
        self._weight_regex = re.compile(
            r"\b(\d+(?:,\d+)?\s*(?:g|kg|ml|l|lt|pz|pezzi|lavaggi|fette))\b",
            re.IGNORECASE,
        )

        # Global flyer validity date pattern
        self._validity_regex = re.compile(
            r"DAL\s+(\d+)\s+(?:AL\s+(\d+)\s+)?([A-Z]+)\s+(\d{4})", re.IGNORECASE
        )

    def de_space_uppercase(self, text: str) -> str:
        """
        Collapses single uppercase letters separated by spaces (e.g. C U O R E -> CUORE),
        excluding standard prepositions/articles.

        Args:
            text: Input text string.

        Returns:
            Normalized text.
        """
        words = text.split()
        if not words:
            return ""

        NO_MERGE = {
            "DI",
            "DA",
            "IN",
            "CON",
            "PER",
            "IL",
            "LA",
            "LO",
            "GLI",
            "LE",
            "UN",
            "UNO",
            "UNA",
            "DEL",
            "DEI",
            "AL",
            "AI",
            "DOP",
            "IGP",
            "DOC",
            "CAD",
        }

        merged_words = []
        for w in words:
            if not merged_words:
                merged_words.append(w)
                continue

            last = merged_words[-1]
            last_clean = re.sub(r"[^\w\s]", "", last).strip()
            w_clean = re.sub(r"[^\w\s]", "", w).strip()

            if (
                last_clean.isupper()
                and w_clean.isupper()
                and last_clean not in NO_MERGE
                and w_clean not in NO_MERGE
                and (len(last_clean) <= 2 or len(w_clean) <= 2)
            ):
                merged_words[-1] = last + w
            else:
                merged_words.append(w)
        return " ".join(merged_words)

    @abstractmethod
    def parse_flyer_validity(self, text: str) -> Optional[str]:
        """
        Scans page text (typically Page 1) to identify global flyer validity.

        Args:
            text: Input text block from flyer first page.

        Returns:
            Flyer validity period string or None.
        """
        pass

    @abstractmethod
    def parse_cell(
        self, text: str, store_id: str, validity_string: Optional[str]
    ) -> ProductOffer:
        """
        Extracts a validated ProductOffer model from a single cell's text block.

        Args:
            text: Cell text block.
            store_id: Supermarket store identifier.
            validity_string: Validity period of the flyer catalog.

        Returns:
            A normalized ProductOffer model.
        """
        pass
