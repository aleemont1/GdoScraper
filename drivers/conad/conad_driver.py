"""
Conad Scraper Strategy Driver.

Automates the REST flyer discovery, downloads PDFs locally, and leverages
geometrical segmentations to normalize product promotions from the PDF layers.
"""

import os
import re
import time
import requests
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.base_pdf_driver import AbstractPdfFlyerDriver
from core.base_pdf_segmenter import BasePdfLayoutSegmenter
from drivers.conad.offer_parser import ConadOfferParser
from utils.logger import setup_logger

logger = setup_logger("ConadDriver")


class ConadSupermarketDriver(AbstractPdfFlyerDriver):
    """
    Concrete scraper driver strategy for Conad.
    Connects the high-level AbstractPdfFlyerDriver engine with Conad-specific
    semantic block text parsing and gutter layout segmentation, and automates
    REST flyer discovery and downloads.
    """

    def __init__(
        self, 
        max_flyers: Optional[int] = None, 
        radius: int = 5, 
        choose_store: bool = False,
        choose_flyer: bool = False,
        parallel: bool = False,
        selected_flyer_slugs: Optional[List[str]] = None
    ) -> None:
        """
        Initializes the Conad driver with scraper configuration options.
        
        Args:
            max_flyers: Maximum number of flyers to download and process.
            radius: Proximity store locator search radius in kilometers.
            choose_store: Unused parameter preserved for interface compliance.
            choose_flyer: Unused parameter preserved for interface compliance.
            parallel: Enable parallel processing of PDF flyers.
            selected_flyer_slugs: Optional list of flyer slugs to target exclusively.
            """
        super().__init__(radius=radius, choose_store=choose_store, choose_flyer=choose_flyer, parallel=parallel)
        self._conad_segmenter = BasePdfLayoutSegmenter()
        self._conad_parser = ConadOfferParser()
        self.max_flyers = max_flyers
        self.radius = radius
        self.choose_store = choose_store
        self.choose_flyer = choose_flyer
        self.selected_flyer_slugs = selected_flyer_slugs

    @property
    def _supermarket_name(self) -> str:
        """Returns the canonical supermarket name."""
        return "CONAD"

    @property
    def _download_subdir(self) -> str:
        """Returns the local subdirectory path where flyers are stored."""
        return "downloads/conad"

    @property
    def _segmenter(self) -> BasePdfLayoutSegmenter:
        """Returns the layout segmenter instance for Conad."""
        return self._conad_segmenter

    @property
    def _parser(self) -> ConadOfferParser:
        """Returns the semantic block parser instance for Conad."""
        return self._conad_parser

    def discover_stores(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Discovers Conad stores matching coordinate values, city search queries, or direct store anacanId.
        
        Args:
            store_id: Coordinates query ('lat,lon'), city/address query, or direct store code query.
            
        Returns:
            A list of discovered store dictionaries.
        """
        lat, lon = None, None
        coords_match = self.COORDINATES_REGEX.match(store_id)
        if coords_match:
            lat = coords_match.group(1)
            lon = coords_match.group(2)
        else:
            coords = self._geocode_location(store_id)
            if coords:
                lat, lon = coords

        if lat is not None and lon is not None:
            logger.info(f"Resolving coordinates ({lat}, {lon}) via Conad POS API (radius: {self.radius}km)...")
            
            url = "https://www.conad.it/api/corporate/it-it.retrievePointOfService.json"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.conad.it",
                "Referer": "https://www.conad.it/ricerca-negozi"
            }
            payload = {
                "latitudine": str(lat),
                "longitudine": str(lon),
                "raggioRicerca": str(self.radius),
                "insegneId": [],
                "serviziId": [],
                "repartiId": [],
                "apertura": []
            }
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=15)
                res.raise_for_status()
                data = res.json()
                stores = data.get("data", [])
                
                stores_list = []
                for s in stores:
                    stores_list.append({
                        "id": str(s.get("anacanId")),
                        "name": s.get("descrizioneInsegna", "CONAD"),
                        "address": s.get("pdvAddress"),
                        "city": s.get("comune"),
                        "distance": float(s.get("distanza", 0))
                    })
                return stores_list
            except Exception as e:
                logger.error(f"Failed to query Conad Point of Service API: {e}")
                
        return [{"id": store_id, "name": f"Conad pdv (anacanId: {store_id})", "address": "Direct Targeting", "city": "", "distance": None}]

    def discover_flyers(self, store_code: str) -> List[Dict[str, Any]]:
        """
        Retrieves active flyers/catalogs for the Conad store anacanId.
        
        Args:
            store_code: Target store code (anacanId).
            
        Returns:
            List of flyer dictionaries.
        """
        flyers_url = f"https://www.conad.it/api/corporate/it-it.flyers.json?anacanId={store_code}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.conad.it/ricerca-negozi"
        }
        try:
            res = requests.get(flyers_url, headers=headers, timeout=15)
            res.raise_for_status()
            data = res.json()
            flyers = data.get("data", [])
            
            current_time_ms = int(time.time() * 1000)
            EXCLUDE_KEYWORDS = ["manuale", "presentatore", "conad card", "conad pay", "regolamento", "informativa", "sanita agevolata", "sanità agevolata", "carta insieme"]
            
            flyers_list = []
            for f in flyers:
                title = f.get("title", "") or ""
                name = f.get("name", "") or ""
                pdf_url = f.get("pdfUrl")
                valid_to = f.get("validTo", 0)
                valid_from = f.get("validFrom", 0)
                
                if not pdf_url:
                    continue
                if not valid_to or current_time_ms > valid_to:
                    continue
                    
                text_to_check = (title + " " + name).lower()
                if any(kw in text_to_check for kw in EXCLUDE_KEYWORDS):
                    continue
                    
                validity_str = ""
                if valid_from and valid_to:
                    try:
                        dt_from = datetime.fromtimestamp(valid_from / 1000.0).strftime('%d/%m/%Y')
                        dt_to = datetime.fromtimestamp(valid_to / 1000.0).strftime('%d/%m/%Y')
                        validity_str = f"DAL {dt_from} AL {dt_to}"
                    except Exception:
                        pass
                        
                flyers_list.append({
                    "id": f.get("slug"),
                    "title": title if title else name,
                    "validity": validity_str,
                    "featured": False
                })
            return flyers_list
        except Exception as e:
            logger.error(f"Failed to query Conad Flyers API for store code {store_code}: {e}")
        return []

    def download_flyers(self, store_id: str) -> List[str]:
        """
        Queries Conad's corporate REST endpoints to automatically resolve coordinates,
        discover active promotional flyers, filter guides/manuals, apply limits,
        and download the PDFs locally non-interactively.
        
        Args:
            store_id: Target store identifier or GPS coordinates query.
            
        Returns:
            List of downloaded flyer PDF local file paths.
        """
        anacan_id = store_id
        coords_match = self.COORDINATES_REGEX.match(store_id)
        if coords_match:
            stores = self.discover_stores(store_id)
            if stores:
                anacan_id = stores[0]["id"]
                
        self._resolved_store_id = anacan_id
        
        active_flyers = []
        flyers_url = f"https://www.conad.it/api/corporate/it-it.flyers.json?anacanId={anacan_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.conad.it/ricerca-negozi"
        }
        try:
            res = requests.get(flyers_url, headers=headers, timeout=15)
            res.raise_for_status()
            data = res.json()
            flyers = data.get("data", [])
            
            current_time_ms = int(time.time() * 1000)
            EXCLUDE_KEYWORDS = ["manuale", "presentatore", "conad card", "conad pay", "regolamento", "informativa", "sanita agevolata", "sanità agevolata", "carta insieme"]
            
            for f in flyers:
                title = f.get("title", "") or ""
                name = f.get("name", "") or ""
                pdf_url = f.get("pdfUrl")
                valid_to = f.get("validTo", 0)
                
                if not pdf_url:
                    continue
                if not valid_to or current_time_ms > valid_to:
                    continue
                    
                text_to_check = (title + " " + name).lower()
                if any(kw in text_to_check for kw in EXCLUDE_KEYWORDS):
                    continue
                    
                active_flyers.append(f)
        except Exception as e:
            logger.error(f"Failed to query Conad Flyers API: {e}")
            return []
            
        selected_flyers = active_flyers
        if self.selected_flyer_slugs:
            selected_flyers = [f for f in active_flyers if f.get("slug") in self.selected_flyer_slugs]
            
        if self.max_flyers is not None and self.max_flyers > 0:
            logger.info(f"Slicing active flyer list to respect limit (max: {self.max_flyers}).")
            selected_flyers = selected_flyers[:self.max_flyers]
            
        downloaded_paths = []
        os.makedirs(self._download_subdir, exist_ok=True)
        
        for flyer in selected_flyers:
            slug = flyer.get("slug", "flyer")
            pdf_url = flyer.get("pdfUrl")
            title = flyer.get("title", "Flyer")
            
            filename = f"conad_{anacan_id}_{slug}.pdf"
            local_path = os.path.join(self._download_subdir, filename)
            
            if os.path.exists(local_path):
                logger.info(f"Flyer PDF already cached locally: '{filename}'. Skipping download.")
                downloaded_paths.append(local_path)
            else:
                logger.info(f"Downloading active flyer: '{title}' to '{filename}'...")
                try:
                    res = requests.get(pdf_url, stream=True, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                    res.raise_for_status()
                    
                    with open(local_path, "wb") as f:
                        for chunk in res.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                
                    logger.info(f"Successfully downloaded: '{filename}'")
                    downloaded_paths.append(local_path)
                except Exception as e:
                    logger.error(f"Failed to download flyer '{title}' from URL {pdf_url}: {e}")
                    
        return downloaded_paths
