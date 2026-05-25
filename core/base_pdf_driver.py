import os
import glob
import re
import pdfplumber
from datetime import datetime
from abc import abstractmethod
from typing import List, Any, Optional
from core.base_driver import AbstractSupermarketDriver
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("BasePdfDriver")

class AbstractPdfFlyerDriver(AbstractSupermarketDriver):
    """
    Abstract strategy engine for processing geometrical PDF catalog flyers.
    
    Encapsulates file discovery, validity string extraction, page rendering cache,
    and hybrid embedded raster image cropping with dynamic grid-snapping fallbacks.
    
    Subclasses only need to declare the target directory, parser strategies, and layout segmenters.
    """

    def __init__(self) -> None:
        self._resolved_store_id: Optional[str] = None

    @property
    @abstractmethod
    def _supermarket_name(self) -> str:
        """Name of the supermarket chain (e.g. 'CONAD')"""
        pass

    @property
    @abstractmethod
    def _download_subdir(self) -> str:
        """Target filesystem downloads subdirectory (e.g. 'downloads/conad')"""
        pass

    @property
    @abstractmethod
    def _segmenter(self) -> Any:
        """Layout segmenter instance (e.g. BasePdfLayoutSegmenter subclass)"""
        pass

    @property
    @abstractmethod
    def _parser(self) -> Any:
        """Semantic parser instance for isolating product fields from raw text blocks"""
        pass

    def download_flyers(self, store_id: str) -> List[str]:
        """
        Optional hook to download active flyer PDFs from a REST endpoint.
        Returns a list of local file paths of the downloaded PDFs.
        """
        return []

    def fetch_promotions(self, store_id: str) -> Any:
        """
        Locates target PDF catalog files, either dynamically downloading them via REST 
        or scanning the local filesystem.
        """
        # A coordinate string looks like "lat,lon" (contains decimals, digits, and commas)
        is_coord = re.match(r"^\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?\s*$", store_id)
        # An anacanId looks like a 6-digit string or numeric store ID
        is_numeric_store = store_id.isdigit() and len(store_id) >= 4 and not store_id.endswith(".pdf")

        if (is_coord or is_numeric_store) and store_id.lower() not in ("all", "downloads"):
            logger.info(f"Checking for dynamic flyer downloads for store reference: '{store_id}'...")
            downloaded_paths = self.download_flyers(store_id)
            if downloaded_paths:
                logger.info(f"REST Downloader retrieved {len(downloaded_paths)} flyers.")
                return downloaded_paths
            else:
                logger.warning(f"No dynamic flyers could be retrieved via REST. Trying filesystem scan as fallback...")

        pdf_paths: List[str] = []
        downloads_dir = self._download_subdir
        
        # 1. Option: Scrape 'all' files in the download folder
        if store_id.lower() in ("all", "downloads"):
            search_pattern = os.path.join(downloads_dir, "*.pdf")
            pdf_paths = glob.glob(search_pattern)
            logger.info(f"Scanning downloads folder '{downloads_dir}'. Found {len(pdf_paths)} PDF flyers to scrape.")
            
        # 2. Option: direct file path provided
        elif store_id.endswith(".pdf"):
            if os.path.exists(store_id):
                pdf_paths = [store_id]
            else:
                # Try finding it in downloads folder
                fallback_path = os.path.join(downloads_dir, os.path.basename(store_id))
                if os.path.exists(fallback_path):
                    pdf_paths = [fallback_path]
                else:
                    logger.error(f"Target PDF file not found at: {store_id}")
        else:
            # 3. Option: direct store file ID
            search_pattern = os.path.join(downloads_dir, f"*{store_id}*.pdf")
            pdf_paths = glob.glob(search_pattern)
            if not pdf_paths:
                logger.error(f"No PDF flyer matching store ID: '{store_id}' found in '{downloads_dir}'.")
                
        return pdf_paths

    def parse_promotions(self, raw_data: Any, store_id: str) -> List[ProductOffer]:
        """
        Ingests the target PDF files and executes layout segmentation page-by-page,
        normalizing extracted text blocks into product offers with crisp visual previews.
        """
        if not isinstance(raw_data, list):
            logger.error("Invalid raw data structure provided. Expected a list of file paths.")
            return []
            
        # Resolve dynamic coordinate store_id to actual store ID (e.g. anacanId) if set
        active_store_id = self._resolved_store_id or store_id
        logger.info(f"Using store ID: '{active_store_id}' for database and image tagging.")

        all_parsed_offers: List[ProductOffer] = []
        
        for file_path in raw_data:
            if not os.path.exists(file_path):
                continue
                
            logger.info(f"Beginning spatial ETL pipeline on flyer: {os.path.basename(file_path)}")
            
            try:
                with pdfplumber.open(file_path) as pdf:
                    total_pages = len(pdf.pages)
                    logger.info(f"Flyer has {total_pages} pages. Analyzing layout grid...")
                    
                    # 1. Extract Validity String from Page 1
                    validity_string = None
                    if total_pages > 0:
                        first_page = pdf.pages[0]
                        first_page_words = first_page.extract_words()
                        if first_page_words:
                            sorted_words = sorted(first_page_words, key=lambda w: (round(w["top"]/5)*5, w["x0"]))
                            first_page_text = " ".join([w["text"] for w in sorted_words])
                            validity_string = self._parser.parse_flyer_validity(first_page_text)
                            if validity_string:
                                logger.info(f"Flyer validity successfully resolved: '{validity_string}'")
                                
                    # 2. Iterate and segment pages
                    flyer_offers_count = 0
                    for page_idx in range(total_pages):
                        page = pdf.pages[page_idx]
                        
                        # Geometric Column-First Segmentation
                        cells = self._segmenter.segment_page(page)
                        if not cells:
                            continue
                            
                        rendered_page_img = None
                        
                        # Semantic Parsing of Cell Strings
                        for cell in cells:
                            try:
                                offer = self._parser.parse_cell(cell["text"], active_store_id, validity_string)
                                if offer:
                                    # Render the page image once per page on-demand
                                    if rendered_page_img is None:
                                        try:
                                            rendered_page_img = page.to_image(resolution=120).original
                                        except Exception as render_err:
                                            logger.debug(f"Failed to render page image: {render_err}")
                                            rendered_page_img = False  # Mark as failed to avoid retrying
                                            
                                    # Crop and save if rendering succeeded
                                    if rendered_page_img and rendered_page_img is not False:
                                        offer.image_url = self._crop_and_save_card_image_from_cached(
                                            rendered_page_img, 
                                            cell["bbox"], 
                                            page, 
                                            active_store_id, 
                                            offer.offer_id,
                                            col_idx=cell.get("col_idx"),
                                            col_count=cell.get("col_count")
                                        )
                                        
                                    all_parsed_offers.append(offer)
                                    flyer_offers_count += 1
                            except ValueError as parse_err:
                                logger.debug(f"Cell parsing ValueError: {parse_err}")
                                # If it looks like a missed product (contains Euro symbol or pricing keywords)
                                cell_text = cell["text"]
                                if any(kw in cell_text.lower() for kw in ["€", "pezzo", "pezzi", "anziché"]):
                                    self._log_missed_product(
                                        file_path=file_path,
                                        page_idx=page_idx,
                                        reason=str(parse_err),
                                        text=cell_text
                                    )
                            except Exception as parse_err:
                                logger.debug(f"Cell parsing unexpected exception: {parse_err}")
                                
                    logger.info(f"Finished parsing flyer. Extracted {flyer_offers_count} products.")
                    
            except Exception as e:
                logger.error(f"Critical failure while reading PDF {os.path.basename(file_path)}: {e}")
                
        logger.info(f"ETL Scrape completed. Extracted a total of {len(all_parsed_offers)} {self._supermarket_name} products.")
        return all_parsed_offers

    def _crop_and_save_card_image_from_cached(
        self, 
        pil_img: Any, 
        bbox: tuple, 
        page: Any, 
        store_id: str, 
        offer_id: str,
        col_idx: Optional[int] = None,
        col_count: Optional[int] = None
    ) -> Optional[str]:
        """
        Crops the card image using a pre-rendered Pillow image object and saves it locally.
        Uses a perfect uniform grid-snapping algorithm if column metadata is available.
        """
        output_dir = "storage/images"
        os.makedirs(output_dir, exist_ok=True)
        
        file_name = f"{self._supermarket_name}_{store_id}_{offer_id}.png"
        file_path = os.path.join(output_dir, file_name)
        db_url = f"/storage/images/{file_name}"
        
        if os.path.exists(file_path):
            return db_url
            
        try:
            img_w, img_h = pil_img.size
            page_w = float(page.width)
            page_h = float(page.height)
            
            scale_x = img_w / page_w
            scale_y = img_h / page_h
            
            # 1. Try to locate a matching embedded raster image inside this column grid zone and cell vertical range
            best_img = None
            if col_idx is not None and col_count is not None and col_count > 0:
                col_w = page_w / col_count
                grid_x0 = col_idx * col_w
                grid_x1 = (col_idx + 1) * col_w
                
                matching_images = []
                for img in getattr(page, "images", []):
                    img_x0 = img.get("x0", 0)
                    img_x1 = img.get("x1", 0)
                    img_y0 = img.get("top", 0)
                    img_y1 = img.get("bottom", 0)
                    
                    # Horizontal overlap: image center is inside this column
                    img_cx = (img_x0 + img_x1) / 2.0
                    horizontal_match = grid_x0 <= img_cx <= grid_x1
                    
                    # Vertical overlap: image center is close to or inside the vertical range of the cell
                    img_cy = (img_y0 + img_y1) / 2.0
                    vertical_match = bbox[1] - 50 <= img_cy <= bbox[3] + 30
                    
                    # Filter out small graphics/icons
                    is_large = img.get("width", 0) > 20 and img.get("height", 0) > 20
                    
                    if horizontal_match and vertical_match and is_large:
                        matching_images.append(img)
                        
                if matching_images:
                    matching_images.sort(key=lambda img: img.get("width", 0) * img.get("height", 0), reverse=True)
                    best_img = matching_images[0]
            
            if best_img:
                # Perfect Crop: crop exactly to the native embedded product image box
                pad = 2.0
                ix0 = max(0.0, best_img["x0"] - pad)
                iy0 = max(0.0, best_img["top"] - pad)
                ix1 = min(page_w, best_img["x1"] + pad)
                iy1 = min(page_h, best_img["bottom"] + pad)
                
                x0_px = int(ix0 * scale_x)
                x1_px = int(ix1 * scale_x)
                top_px = int(iy0 * scale_y)
                bottom_px = int(iy1 * scale_y)
                
                crop_box = (
                    max(0, x0_px),
                    max(0, top_px),
                    min(img_w, x1_px),
                    min(img_h, bottom_px)
                )
            else:
                # Fallback to perfect uniform grid card column crop
                if col_idx is not None and col_count is not None and col_count > 0:
                    col_w = page_w / col_count
                    x0 = col_idx * col_w
                    x1 = (col_idx + 1) * col_w
                else:
                    x0, x1 = bbox[0], bbox[2]
                    w = x1 - x0
                    if w < 120:
                        x0 = max(0, x0 - 130)
                        x1 = min(page_w, x1 + 15)
                
                x0_px = int(x0 * scale_x)
                x1_px = int(x1 * scale_x)
                top_px = int(bbox[1] * scale_y)
                bottom_px = int(bbox[3] * scale_y)
                
                padding_top = int(15 * scale_y)
                padding_bottom = int(10 * scale_y)
                
                crop_box = (
                    max(0, x0_px),
                    max(0, top_px - padding_top),
                    min(img_w, x1_px),
                    min(img_h, bottom_px + padding_bottom)
                )
            
            cropped_img = pil_img.crop(crop_box)
            cropped_img.save(file_path, "PNG")
            return db_url
        except Exception as e:
            logger.debug(f"Failed to crop from cached image for offer {offer_id}: {e}")
            return None

    def _log_missed_product(self, file_path: str, page_idx: int, reason: str, text: str) -> None:
        """
        Logs skipped parsed cells containing price keywords for manual audit.
        """
        log_file = "storage/missed_products.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        filename = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] FILE: {filename} | PAGE: {page_idx + 1} | REASON: {reason}\n")
                f.write(f"RAW TEXT: {text}\n")
                f.write("-" * 80 + "\n")
        except Exception as e:
            logger.error(f"Failed to write to missed products log: {e}")
