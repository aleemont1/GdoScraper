import os
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Any, Optional

from core.base_pdf_driver import AbstractPdfFlyerDriver
from drivers.ins.ins_layout_segmenter import InsLayoutSegmenter
from drivers.ins.ins_offer_parser import InsOfferParser
from utils.logger import setup_logger

logger = setup_logger("INSDriver")


class INSSupermarketDriver(AbstractPdfFlyerDriver):
    """
    Concrete scraper driver strategy for IN's Mercato.
    Supports geocoding POS coords, BeautifulSoup web crawling for the PDF flyer,
    and inherits standard/OCR visual flyer processing dynamically from AbstractPdfFlyerDriver.
    """

    def __init__(
        self,
        max_flyers: Optional[int] = None,
        parallel: bool = False,
        use_gemini: bool = False
    ) -> None:
        super().__init__(parallel=parallel, use_gemini=use_gemini)
        self._ins_segmenter = InsLayoutSegmenter()
        self._ins_parser = InsOfferParser()
        self.max_flyers = max_flyers

    @property
    def _supermarket_name(self) -> str:
        return "INS"

    @property
    def _download_subdir(self) -> str:
        return "downloads/ins"

    @property
    def _segmenter(self) -> InsLayoutSegmenter:
        return self._ins_segmenter

    @property
    def _parser(self) -> InsOfferParser:
        return self._ins_parser

    def _resolve_coordinates_to_city(self, store_id: str) -> str:
        """
        Geocodes latitude/longitude coordinates to a city name using OpenStreetMap (Nominatim)
        and BigDataCloud as a keyless public fallback.
        """
        coords_match = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$", store_id)
        if not coords_match:
            return store_id  # Not coordinates, treat as direct text

        lat = coords_match.group(1)
        lon = coords_match.group(2)

        # 1. Try OpenStreetMap Nominatim first
        osm_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        headers = {
            "User-Agent": "SupermarketScraper/1.0 (aleemont@example.com)"
        }
        logger.info(f"Geocoding coordinates ({lat}, {lon}) via OpenStreetMap Nominatim...")
        try:
            res = requests.get(osm_url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                addr = data.get("address", {})
                city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb")
                if city:
                    logger.info(f"Resolved to city: '{city}' via Nominatim")
                    return city
            logger.warning(f"OSM Nominatim returned status code {res.status_code}. Trying keyless BigDataCloud fallback...")
        except Exception as e:
            logger.warning(f"OSM Nominatim query failed: {e}. Trying keyless BigDataCloud fallback...")

        # 2. Try BigDataCloud reverse geocode client as fallback
        bdc_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=it"
        try:
            res = requests.get(bdc_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            res.raise_for_status()
            data = res.json()
            city = data.get("city") or data.get("locality") or data.get("principalSubdivision")
            if city:
                logger.info(f"Resolved to city: '{city}' via BigDataCloud")
                return city
        except Exception as e:
            logger.error(f"BigDataCloud geocoding fallback failed: {e}")

        # Final default fallback if everything fails
        logger.warning("All geocoding lookups failed. Defaulting to 'Cesena' region.")
        return "Cesena"

    def download_flyers(self, store_id: str) -> List[str]:
        """
        Crawls the IN's website store/region spans to resolve the target PDF URL,
        downloads it, and stores it locally.
        """
        # Resolve GPS coordinates to city name
        city_query = self._resolve_coordinates_to_city(store_id)
        logger.info(f"Searching IN's Mercato flyer for store location matching: '{city_query}'")

        # 1. Fetch the volantino entrypoint page
        url = "https://www.insmercato.it/volantino/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to crawl IN's volantino entrypoint URL: {e}")
            return []

        # 2. Parse WordPress JavaScript configuration block variables
        soup = BeautifulSoup(res.text, "html.parser")
        all_stores_div = soup.find("div", class_=lambda c: c and "all-stores" in c)
        
        if not all_stores_div:
            logger.error("Could not locate hidden 'all-stores' container in the IN's page.")
            return []

        default_url = all_stores_div.get("data-default-url")
        current_flyer = str(all_stores_div.get("data-current-flyer", "2"))
        
        if current_flyer == "2":
            edition_path = all_stores_div.get("data-edition-two")
        else:
            edition_path = all_stores_div.get("data-edition-one")

        if not default_url or not edition_path:
            logger.error("Missing critical WordPress CDN parameters in WordPress store selector.")
            return []

        logger.info(f"CDN Base URL: {default_url} | Edition Path: {edition_path}")

        # 3. Iterate over store spans to find matching city name
        spans = soup.find_all("span", class_="store-option")
        store_code = None
        matched_span = None

        for s in spans:
            loc = s.get("data-location", "") or ""
            addr = s.get("data-address", "") or ""
            text_to_search = (loc + " " + addr).lower()
            
            if city_query.lower() in text_to_search:
                matched_span = s
                break

        # Fallback substring search
        if not matched_span:
            clean_city = re.sub(r"[^\w\s]", "", city_query).strip()
            for s in spans:
                loc = s.get("data-location", "") or ""
                addr = s.get("data-address", "") or ""
                if any(part.lower() in (loc + " " + addr).lower() for part in clean_city.split()):
                    matched_span = s
                    break

        if matched_span:
            logger.info(f"Matched IN's store span: {matched_span.attrs}")
            if current_flyer == "2":
                store_code = matched_span.get("data-code-two")
            else:
                store_code = matched_span.get("data-code-one")
        else:
            logger.warning(f"No specific store matched city '{city_query}'. Defaulting to 'E-Campagna-OF' (Cesena region).")
            store_code = "E-Campagna-OF"

        if not store_code:
            logger.error("Failed to extract a valid store edition code from span.")
            return []

        # 4. Construct PDF Download URL
        pdf_url = f"{default_url}/{edition_path}/pdf/volantino-{store_code}.pdf"
        logger.info(f"Target PDF URL constructed: {pdf_url}")

        # Save downloaded ID for visual cropping files mapping
        self._resolved_store_id = store_code

        # 5. Download the PDF flyer locally
        filename = f"ins_{store_code}.pdf"
        os.makedirs(self._download_subdir, exist_ok=True)
        local_path = os.path.join(self._download_subdir, filename)

        if os.path.exists(local_path):
            logger.info(f"IN's flyer PDF already cached locally: '{filename}'. Skipping download.")
            return [local_path]

        logger.info(f"Downloading IN's flyer PDF to '{filename}'...")
        try:
            res = requests.get(pdf_url, stream=True, headers=headers, timeout=30)
            res.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"Successfully downloaded IN's flyer: '{filename}'")
            return [local_path]
        except Exception as e:
            logger.error(f"Failed to download IN's flyer PDF: {e}")
            return []
