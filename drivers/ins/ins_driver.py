import os
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Any, Optional, Dict

from core.base_pdf_driver import AbstractPdfFlyerDriver
from core.base_pdf_segmenter import BasePdfLayoutSegmenter
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
        use_gemini: bool = False,
        use_claude: bool = False,
        engine: str = "AUTO",
    ) -> None:
        super().__init__(
            parallel=parallel,
            use_gemini=use_gemini,
            use_claude=use_claude,
            engine=engine,
        )
        self._ins_segmenter = BasePdfLayoutSegmenter()
        self._ins_parser = InsOfferParser()
        self.max_flyers = max_flyers

    @property
    def _supermarket_name(self) -> str:
        return "INS"

    @property
    def _download_subdir(self) -> str:
        return "downloads/ins"

    @property
    def _segmenter(self) -> BasePdfLayoutSegmenter:
        return self._ins_segmenter

    @property
    def _parser(self) -> InsOfferParser:
        return self._ins_parser

    def _resolve_coordinates_to_city(self, store_id: str) -> str:
        """
        Geocodes latitude/longitude coordinates to a city name using caching and parent's geocoder.
        """
        coords_match = self.COORDINATES_REGEX.match(store_id)
        if not coords_match:
            return store_id  # Not coordinates, treat as direct text

        lat = float(coords_match.group(1))
        lon = float(coords_match.group(2))
        return self._reverse_geocode(lat, lon)

    def discover_stores(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Crawls the wordpress volantino page to find IN's Mercato stores matching coordinates or text query.
        """
        city_query = self._resolve_coordinates_to_city(store_id)

        url = "https://www.insmercato.it/volantino/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            res.encoding = "utf-8"
        except Exception as e:
            logger.error(f"Failed to crawl IN's volantino entrypoint URL: {e}")
            return []

        soup = BeautifulSoup(res.text, "html.parser")
        spans = soup.find_all("span", class_="store-option")

        stores_list = []

        ignore_words = {
            "di",
            "del",
            "della",
            "dei",
            "degli",
            "da",
            "dal",
            "in",
            "con",
            "su",
            "per",
            "tra",
            "fra",
            "la",
            "il",
            "i",
            "gli",
            "le",
            "un",
            "una",
            "uno",
        }
        query_words = [
            w.lower()
            for w in re.split(r"[^\w\s]", city_query)
            if w.strip() and w.lower() not in ignore_words
        ]
        query_terms = []
        for qw in query_words:
            query_terms.extend([term for term in qw.split() if len(term) > 1])

        for s in spans:
            loc = s.get("data-location", "") or ""
            addr = s.get("data-address", "") or ""
            code_one = s.get("data-code-one", "") or ""
            code_two = s.get("data-code-two", "") or ""

            code = code_two if code_two else code_one
            if not code:
                code = "E-Campagna-OF"

            if store_id.strip().upper() in (code_one.upper(), code_two.upper()):
                stores_list.append(
                    {
                        "id": code,
                        "name": f"IN's {loc}",
                        "address": addr,
                        "city": loc,
                        "distance": 0.0,
                    }
                )
                continue

            search_space = (loc + " " + addr).lower()
            if any(term in search_space for term in query_terms):
                stores_list.append(
                    {
                        "id": code,
                        "name": f"IN's {loc}",
                        "address": addr,
                        "city": loc,
                        "distance": None,
                    }
                )

        if not stores_list:
            for s in spans[:30]:
                loc = s.get("data-location", "") or ""
                addr = s.get("data-address", "") or ""
                code = (
                    s.get("data-code-two") or s.get("data-code-one") or "E-Campagna-OF"
                )
                stores_list.append(
                    {
                        "id": code,
                        "name": f"IN's {loc}",
                        "address": addr,
                        "city": loc,
                        "distance": None,
                    }
                )

        return stores_list

    def _resolve_flyer_pdf_url(self, store_id: str) -> Optional[str]:
        """
        Crawls the IN's website to resolve the target flyer PDF URL for a store/region.
        """
        # Resolve GPS coordinates to city name
        city_query = self._resolve_coordinates_to_city(store_id)
        logger.info(
            f"Searching IN's Mercato flyer for store location matching: '{city_query}'"
        )

        # 1. Fetch the volantino entrypoint page
        url = "https://www.insmercato.it/volantino/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            res.encoding = "utf-8"
        except Exception as e:
            logger.error(f"Failed to crawl IN's volantino entrypoint URL: {e}")
            return None

        # 2. Parse WordPress JavaScript configuration block variables
        soup = BeautifulSoup(res.text, "html.parser")
        all_stores_div = soup.find("div", class_=lambda c: c and "all-stores" in c)

        if not all_stores_div:
            logger.error(
                "Could not locate hidden 'all-stores' container in the IN's page."
            )
            return None

        default_url = all_stores_div.get("data-default-url")
        current_flyer = str(all_stores_div.get("data-current-flyer", "2"))

        if current_flyer == "2":
            edition_path = all_stores_div.get("data-edition-two")
        else:
            edition_path = all_stores_div.get("data-edition-one")

        if not default_url or not edition_path:
            logger.error(
                "Missing critical WordPress CDN parameters in WordPress store selector."
            )
            return None

        logger.info(f"CDN Base URL: {default_url} | Edition Path: {edition_path}")

        # 3. Iterate over store spans to find matching location or direct store code
        spans = soup.find_all("span", class_="store-option")
        store_code = None
        matched_span = None

        # 3.1 Check for direct code match first
        for s in spans:
            code_one = s.get("data-code-one", "") or ""
            code_two = s.get("data-code-two", "") or ""
            if store_id.strip().upper() in (code_one.upper(), code_two.upper()):
                matched_span = s
                logger.info(f"Direct IN's store code matched: {store_id}")
                break

        # 3.2 If no direct code match, find the best text matching span by counting overlapping words
        if not matched_span:
            ignore_words = {
                "di",
                "del",
                "della",
                "dei",
                "degli",
                "da",
                "dal",
                "in",
                "con",
                "su",
                "per",
                "tra",
                "fra",
                "la",
                "il",
                "i",
                "gli",
                "le",
                "un",
                "una",
                "uno",
            }
            query_words = [
                w.lower()
                for w in re.split(r"[^\w\s]", city_query)
                if w.strip() and w.lower() not in ignore_words
            ]
            query_terms = []
            for qw in query_words:
                query_terms.extend([term for term in qw.split() if len(term) > 1])

            best_match_count = 0
            for s in spans:
                loc = s.get("data-location", "") or ""
                addr = s.get("data-address", "") or ""
                search_space = (loc + " " + addr).lower()

                match_count = sum(1 for term in query_terms if term in search_space)
                if match_count > best_match_count:
                    best_match_count = match_count
                    matched_span = s

        if matched_span:
            logger.info(f"Matched IN's store span: {matched_span.attrs}")
            if current_flyer == "2":
                store_code = matched_span.get("data-code-two")
            else:
                store_code = matched_span.get("data-code-one")
        else:
            logger.warning(
                f"No specific store matched city '{city_query}'. Defaulting to 'E-Campagna-OF' (Cesena region)."
            )
            store_code = "E-Campagna-OF"

        if not store_code:
            logger.error("Failed to extract a valid store edition code from span.")
            return None

        # 4. Construct PDF Download URL
        pdf_url = f"{default_url}/{edition_path}/pdf/volantino-{store_code}.pdf"
        logger.info(f"Target PDF URL constructed: {pdf_url}")
        self._resolved_store_id = store_code
        return pdf_url

    def discover_flyers(self, store_code: str) -> List[Dict[str, Any]]:
        """
        Returns the single active flyer catalog for the INS store code.
        """
        pdf_url = None
        try:
            pdf_url = self._resolve_flyer_pdf_url(store_code)
        except Exception as e:
            logger.error(f"Failed to resolve INS flyer PDF URL: {e}")

        return [
            {
                "id": store_code,
                "title": f"IN's Flyer Circular ({store_code})",
                "validity": "Active Circular",
                "featured": True,
                "pdf_url": pdf_url,
            }
        ]

    def download_flyers(self, store_id: str) -> List[str]:
        """
        Crawls the IN's website store/region spans to resolve the target PDF URL,
        downloads it, and stores it locally.
        """
        pdf_url = self._resolve_flyer_pdf_url(store_id)
        if not pdf_url:
            logger.error("Could not construct IN's target PDF URL.")
            return []

        store_code = self._resolved_store_id or "E-Campagna-OF"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        # 5. Download the PDF flyer locally
        filename = f"ins_{store_code}.pdf"
        os.makedirs(self._download_subdir, exist_ok=True)
        local_path = os.path.join(self._download_subdir, filename)

        if os.path.exists(local_path):
            logger.info(
                f"IN's flyer PDF already cached locally: '{filename}'. Skipping download."
            )
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
