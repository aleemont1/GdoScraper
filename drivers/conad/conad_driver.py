import os
import re
import time
import requests
from typing import List, Optional
from core.base_pdf_driver import AbstractPdfFlyerDriver
from drivers.conad.layout_segmenter import ConadLayoutSegmenter
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
        parallel: bool = False
    ) -> None:
        super().__init__(parallel=parallel)
        self._conad_segmenter = ConadLayoutSegmenter()
        self._conad_parser = ConadOfferParser()
        self.max_flyers = max_flyers
        self.radius = radius
        self.radius = radius
        self.choose_store = choose_store

    @property
    def _supermarket_name(self) -> str:
        return "CONAD"

    @property
    def _download_subdir(self) -> str:
        return "downloads/conad"

    @property
    def _segmenter(self) -> ConadLayoutSegmenter:
        return self._conad_segmenter

    @property
    def _parser(self) -> ConadOfferParser:
        return self._conad_parser

    def download_flyers(self, store_id: str) -> List[str]:
        """
        Queries Conad's corporate REST endpoints to automatically resolve coordinates,
        discover active promotional flyers, filter guides/manuals, apply limits,
        and download the PDFs locally.
        """
        # 1. Detect if store_id represents coordinates (lat, lon)
        coords_match = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$", store_id)
        
        anacan_id = None
        if coords_match:
            lat = coords_match.group(1)
            lon = coords_match.group(2)
            logger.info(f"Resolving coordinates ({lat}, {lon}) via Conad Point of Service API (radius: {self.radius}km)...")
            
            url = "https://www.conad.it/api/corporate/it-it.retrievePointOfService.json"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.conad.it",
                "Referer": "https://www.conad.it/ricerca-negozi"
            }
            payload = {
                "latitudine": lat,
                "longitudine": lon,
                "raggioRicerca": str(self.radius),
                "insegneId": [],
                "serviziId": [],
                "repartiId": [],
                "apertura": []
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                stores = data.get("data", [])
                
                if not stores:
                    logger.warning(f"No Conad stores found within {self.radius}km around ({lat}, {lon}).")
                    return []
                
                # Dynamic terminal selector if requested and multiple stores are found
                if self.choose_store and len(stores) > 1:
                    print(f"\nDiscovered {len(stores)} Conad stores within {self.radius} km:")
                    for idx, s in enumerate(stores):
                        print(f"  {idx+1}) {s.get('descrizioneInsegna', 'CONAD')} - {s.get('pdvAddress')} [{s.get('distanza')} km] (anacanId: {s.get('anacanId')})")
                    
                    selected_idx = 0
                    while True:
                        try:
                            user_input = input(f"Select a store [1-{len(stores)}] (Enter to default to closest store): ").strip()
                            if not user_input:
                                selected_idx = 0
                                break
                            val = int(user_input)
                            if 1 <= val <= len(stores):
                                selected_idx = val - 1
                                break
                            else:
                                print(f"Please enter a number between 1 and {len(stores)}.")
                        except ValueError:
                            print("Invalid input. Please enter a valid integer.")
                        except (KeyboardInterrupt, EOFError):
                            print("\nSelection interrupted. Defaulting to closest store.")
                            selected_idx = 0
                            break
                    
                    target_store = stores[selected_idx]
                else:
                    target_store = stores[0]
                    
                logger.info(f"Target Store Resolved: {target_store.get('descrizioneInsegna')} - {target_store.get('pdvAddress')} (Distance: {target_store.get('distanza')} km)")
                anacan_id = target_store.get("anacanId")
                
            except Exception as e:
                logger.error(f"Failed to query Conad Point of Service API: {e}")
                return []
        else:
            # direct anacanId search
            anacan_id = store_id
            logger.info(f"Using direct store anacanId: '{anacan_id}'")

        if not anacan_id:
            logger.error("Could not resolve a valid store anacanId.")
            return []

        # Store resolved store ID for DB and visual crops labeling
        self._resolved_store_id = anacan_id

        # 2. Retrieve flyers list for the anacanId
        logger.info(f"Fetching promotional flyer catalogs for store anacanId: '{anacan_id}'...")
        flyers_url = f"https://www.conad.it/api/corporate/it-it.flyers.json?anacanId={anacan_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.conad.it/ricerca-negozi"
        }
        
        active_flyers = []
        try:
            response = requests.get(flyers_url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            flyers = data.get("data", [])
            
            if not flyers:
                logger.warning(f"No flyer catalogs found for store anacanId: '{anacan_id}'.")
                return []
                
            # Filter active flyers and exclude guides/manuals
            current_time_ms = int(time.time() * 1000)
            EXCLUDE_KEYWORDS = ["manuale", "presentatore", "conad card", "conad pay", "regolamento", "informativa", "sanita agevolata", "sanità agevolata", "carta insieme"]
            
            for flyer in flyers:
                title = flyer.get("title", "") or ""
                name = flyer.get("name", "") or ""
                pdf_url = flyer.get("pdfUrl")
                valid_to = flyer.get("validTo", 0)
                
                if not pdf_url:
                    continue
                    
                # Verify that the flyer is currently valid
                if not valid_to or current_time_ms > valid_to:
                    continue
                    
                # Apply informative document exclusions
                text_to_check = (title + " " + name).lower()
                if any(kw in text_to_check for kw in EXCLUDE_KEYWORDS):
                    continue
                    
                active_flyers.append(flyer)
                
            logger.info(f"Discovered {len(active_flyers)} active promotional flyer catalogs (filtered out manuals/expired documents).")
            
        except Exception as e:
            logger.error(f"Failed to query Conad Flyers API: {e}")
            return []

        # 3. Apply maximum download limits
        if self.max_flyers is not None and self.max_flyers > 0:
            logger.info(f"Slicing active flyer list to respect CLI limit (max: {self.max_flyers}).")
            active_flyers = active_flyers[:self.max_flyers]

        # 4. Download and cache flyers locally
        downloaded_paths = []
        os.makedirs(self._download_subdir, exist_ok=True)
        
        for flyer in active_flyers:
            slug = flyer.get("slug", "flyer")
            pdf_url = flyer.get("pdfUrl")
            title = flyer.get("title", "Flyer")
            
            # Construct a clean, deterministic local filename
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
