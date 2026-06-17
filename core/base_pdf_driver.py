"""
Base PDF Driver for GDO Supermarket Scrapers.

Implements AbstractPdfFlyerDriver, providing visual layout segmentation,
image cropping, caching, vector extraction, and visual OCR fallback engines (Gemini and Claude).
"""

import os
import glob
import re
import time
import hashlib
import pdfplumber
from datetime import datetime
from abc import abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from core.base_driver import AbstractSupermarketDriver
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("BasePdfDriver")


class ExtractedOffer(BaseModel):
    """Pydantic model representing an offer extracted via multimodal visual LLMs."""
    reasoning: str = Field(description="Chain-of-Thought reasoning: 1. Describe the packaging visually (e.g. colors, shape, features, graphics). 2. Find the product name, brand, weight and price. 3. Define the precise bounding box enclosing ONLY the packaging/product image itself, excluding price bubbles or text.")
    name: str = Field(description="Name of the product and optional short description in Italian (e.g., 'Biscotti Frollini')")
    brand: Optional[str] = Field(None, description="Brand name of the product if clearly indicated (e.g., 'Mulino Bianco')")
    weight_or_volume: Optional[str] = Field(None, description="Weight, volume, or quantity (e.g., '500g', '6x1.5L')")
    price: float = Field(description="Active promotional price in euros as decimal (e.g., 1.89)")
    original_price: Optional[float] = Field(None, description="Original pre-discount price if indicated (e.g., 2.49)")
    discount_percentage: Optional[int] = Field(None, description="Discount percentage value if indicated (e.g., 30)")
    category: Optional[str] = Field(None, description="Standard product category in Italian (e.g., 'Alimentari', 'Bevande')")
    bbox: List[int] = Field(description="Bounding box coordinates [ymin, xmin, ymax, xmax] normalized from 0 to 1000 framing strictly the product packaging or photo itself, excluding text description blocks, price tags, background clutter, or other products.")


class ExtractedOffersList(BaseModel):
    """Pydantic wrapper for a list of ExtractedOffer objects."""
    offers: List[ExtractedOffer]


class OcrPageWrapper:
    """
    Adapter wrapper that simulates a pdfplumber Page object,
    substituting vector-embedded words with local OCR-extracted words.
    """
    def __init__(self, page: Any, words_list: List[Dict[str, Any]]) -> None:
        """Initializes the OCR page wrapper."""
        self._page = page
        self.width = page.width
        self.height = page.height
        self.images = getattr(page, "images", [])
        self._words = words_list

    def extract_words(self) -> List[Dict[str, Any]]:
        """Returns the local OCR-extracted words list."""
        return self._words


def _parse_single_flyer_worker(driver_class, file_path: str, store_id: str) -> List[ProductOffer]:
    """
    Standalone worker function executed inside an isolated CPU subprocess.
    Instantiates its own concrete driver instance to isolate state and prevent pickling errors.
    """
    driver = driver_class()
    driver._resolved_store_id = store_id
    return driver._parse_single_flyer_file(file_path, store_id)


class AbstractPdfFlyerDriver(AbstractSupermarketDriver):
    """
    Abstract strategy engine for processing geometrical PDF catalog flyers.
    
    Encapsulates file discovery, validity string extraction, page rendering cache,
    and hybrid embedded raster image cropping with dynamic grid-snapping fallbacks.
    Also houses the dynamic scanned-brochure OCR visual parsing fallback strategies.
    
    Subclasses only need to declare the target directory, parser strategies, and layout segmenters.
    """

    def __init__(
        self, 
        parallel: bool = False, 
        use_gemini: bool = False,
        use_claude: bool = False,
        engine: str = "AUTO",
        radius: int = 5,
        choose_store: bool = False,
        choose_flyer: bool = False
    ) -> None:
        """Initializes the Abstract PDF Flyer Driver."""
        self._resolved_store_id: Optional[str] = None
        self.parallel = parallel
        self.radius = radius
        self.choose_store = choose_store
        self.choose_flyer = choose_flyer
        
        # Unify engine parameter and legacy booleans
        self.engine = engine.upper().strip()
        if use_gemini:
            self.engine = "GEMINI"
        elif use_claude:
            self.engine = "CLAUDE"
            
        self.use_gemini = (self.engine == "GEMINI")
        self.use_claude = (self.engine == "CLAUDE")
        self._current_is_vector: Optional[bool] = None

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
        """Semantic parser instance for isolating product fields from text blocks"""
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
        is_pdf = store_id.lower().endswith(".pdf")
        is_special = store_id.lower() in ("all", "downloads")

        if not is_pdf and not is_special:
            logger.info(f"Checking for dynamic flyer downloads for store reference: '{store_id}'...")
            downloaded_paths = self.download_flyers(store_id)
            if downloaded_paths:
                logger.info(f"REST Downloader retrieved {len(downloaded_paths)} flyers.")
                return downloaded_paths
            else:
                logger.warning("No flyers retrieved via REST. Trying filesystem scan as fallback...")

        pdf_paths: List[str] = []
        downloads_dir = self._download_subdir
        
        if store_id.lower() in ("all", "downloads"):
            search_pattern = os.path.join(downloads_dir, "*.pdf")
            pdf_paths = glob.glob(search_pattern)
            logger.info(f"Scanning downloads folder '{downloads_dir}'. Found {len(pdf_paths)} PDF flyers to scrape.")
            
        elif store_id.endswith(".pdf"):
            if os.path.exists(store_id):
                pdf_paths = [store_id]
            else:
                fallback_path = os.path.join(downloads_dir, os.path.basename(store_id))
                if os.path.exists(fallback_path):
                    pdf_paths = [fallback_path]
                else:
                    logger.error(f"Target PDF file not found at: {store_id}")
        else:
            search_pattern = os.path.join(downloads_dir, f"*{store_id}*.pdf")
            pdf_paths = glob.glob(search_pattern)
            if not pdf_paths:
                logger.error(f"No PDF flyer matching store ID: '{store_id}' found in '{downloads_dir}'.")
                
        return pdf_paths

    def parse_promotions(self, raw_data: Any, store_id: str) -> List[ProductOffer]:
        """
        Ingests the target PDF files and executes layout segmentation page-by-page,
        normalizing extracted text blocks into product offers with visual previews.
        Supports sequential and parallel multiprocessing modes.
        """
        if not isinstance(raw_data, list):
            logger.error("Invalid raw data structure provided. Expected a list of file paths.")
            return []
            
        # Determine store ID, filtering out any raw file path strings
        active_store_id = self._resolved_store_id
        if not active_store_id or active_store_id.endswith(".pdf") or "/" in active_store_id or "\\" in active_store_id:
            active_store_id = store_id
            
        if not active_store_id or active_store_id.endswith(".pdf") or "/" in active_store_id or "\\" in active_store_id:
            active_store_id = "MANUAL_STORE"
            
        logger.info(f"Using store ID: '{active_store_id}' for database and image tagging.")

        all_parsed_offers: List[ProductOffer] = []
        
        if self.parallel and len(raw_data) > 1:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            
            max_workers = min(len(raw_data), multiprocessing.cpu_count())
            logger.info(f"Initiating MULTIPROCESS PARALLEL parsing on {max_workers} processes (one process per flyer)...")
            
            driver_class = self.__class__
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_parse_single_flyer_worker, driver_class, file_path, active_store_id)
                    for file_path in raw_data
                ]
                
                for idx, future in enumerate(futures):
                    try:
                        offers = future.result()
                        all_parsed_offers.extend(offers)
                        logger.info(f"Parallel Worker #{idx+1} finished. Extracted {len(offers)} offers.")
                    except Exception as err:
                        logger.error(f"Parallel worker #{idx+1} failed with exception: {err}", exc_info=True)
        else:
            logger.info("Initiating SEQUENTIAL flyer parsing...")
            for file_path in raw_data:
                offers = self._parse_single_flyer_file(file_path, active_store_id)
                all_parsed_offers.extend(offers)
                
        logger.info(f"ETL Scrape completed. Extracted a total of {len(all_parsed_offers)} {self._supermarket_name} products.")
        return all_parsed_offers

    def _parse_single_flyer_file(self, file_path: str, store_id: str) -> List[ProductOffer]:
        """
        Core dynamic spatial ETL logic for parsing a single flyer PDF.
        Automatically detects vector vs scanned layout structure and routes accordingly.
        """
        if not os.path.exists(file_path):
            return []
            
        logger.info(f"Beginning spatial ETL pipeline on flyer: {os.path.basename(file_path)}")
        parsed_offers: List[ProductOffer] = []
        total_pages = 0
        has_vector_text = False
        
        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Flyer has {total_pages} pages.")
                
                # Dynamic Vector vs Scanned Layout Detection
                if self._current_is_vector is not None:
                    has_vector_text = self._current_is_vector
                elif self.engine != "AUTO":
                    has_vector_text = False
                else:
                    has_vector_text = any(len(p.extract_words()) > 0 for p in pdf.pages)
                
                # --- STRATEGY A: Vector-Based PDF Parsing ---
                if has_vector_text:
                    logger.info("Vector-based PDF circular detected. Engaging high-accuracy text grid segmenter...")
                    
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
                                
                    # 2. Segment and parse page cells
                    flyer_offers_count = 0
                    for page_idx in range(total_pages):
                        page = pdf.pages[page_idx]
                        
                        cells = self._segmenter.segment_page(page)
                        if not cells:
                            continue
                            
                        rendered_page_img = None
                        page_offers = []
                        
                        for cell in cells:
                            try:
                                offer = self._parser.parse_cell(cell["text"], store_id, validity_string)
                                if offer:
                                    # Instantiate card rendering on-demand
                                    if rendered_page_img is None:
                                        try:
                                            rendered_page_img = page.to_image(resolution=120).original
                                        except Exception as render_err:
                                            logger.debug(f"Failed to render page image: {render_err}")
                                            rendered_page_img = False
                                            
                                    if rendered_page_img and rendered_page_img is not False:
                                        offer.image_url = self._crop_and_save_card_image_from_cached(
                                            rendered_page_img, 
                                            cell["bbox"], 
                                            page, 
                                            store_id, 
                                            offer.offer_id,
                                            col_idx=cell.get("col_idx"),
                                            col_count=cell.get("col_count"),
                                            product_name=offer.name
                                        )
                                        
                                    offer.supermarket = self._supermarket_name
                                    page_offers.append(offer)
                            except ValueError as parse_err:
                                logger.debug(f"Cell parsing ValueError: {parse_err}")
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
                                
                        if self.use_claude and os.environ.get("ANTHROPIC_API_KEY"):
                            if rendered_page_img is None or rendered_page_img is False:
                                try:
                                    rendered_page_img = page.to_image(resolution=120).original
                                except Exception as render_err:
                                    logger.error(f"Failed to render page image for Claude visual audit: {render_err}")
                                    rendered_page_img = False
                                    
                            if rendered_page_img and rendered_page_img is not False:
                                page_offers = self._audit_and_self_heal_page_via_claude(
                                    rendered_page_img,
                                    store_id,
                                    page_idx,
                                    page_offers,
                                    validity_string,
                                    page=page
                                )
                                
                        for offer in page_offers:
                            parsed_offers.append(offer)
                            flyer_offers_count += 1
                            
                    logger.info(f"Finished parsing vector flyer {os.path.basename(file_path)}. Extracted {flyer_offers_count} products.")
                
                # --- STRATEGY B: Scanned PDF / Image-Only Brochure Parsing ---
                else:
                    logger.info("Scanned/Flat-image brochure detected. Engaging OCR visual extraction fallback...")
                    
                    prompt = (
                        "<role>\n"
                        "You are a state-of-the-art visual document analysis agent and expert OCR data extractor specializing in Italian GDO (Grande Distribuzione Organizzata) promotional flyers/circulars.\n"
                        "</role>\n\n"
                        "<task>\n"
                        "Carefully inspect the provided flyer page image. Your objective is to extract every commercial product promotion (offer) displayed on the page.\n"
                        "For each detected offer, perform step-by-step chain-of-thought reasoning to identify the product details and crop coordinates, and return the structured data.\n"
                        "</task>\n\n"
                        "<instructions>\n"
                        "For each promotional item on the flyer page, follow these logical steps:\n"
                        "1. **Identify Promotion Region**: Locate the distinct graphical cell, box, or region containing the product and its price.\n"
                        "2. **Extract Price Details**:\n"
                        "   - Read the price numbers carefully. Note that euros and cents are often formatted with different font sizes (e.g., a large '1' and a small superscript '49' means 1.49). Combine them correctly.\n"
                        "   - Ignore \"al kg\" or \"al litro\" unit prices if a total package price is also shown; prioritize the package selling price.\n"
                        "   - If a discount percentage (e.g., '-30%', 'Sconto 40%') is displayed, extract the percentage number as an integer.\n"
                        "   - Look for any original pre-discount price (often crossed out) and extract it.\n"
                        "3. **Extract Textual Details (in Italian)**:\n"
                        "   - Identify the **Product Name** (e.g., 'Passata di pomodoro', 'Frollini con gocce di cioccolato'). Write it in Title Case. Exclude weight, volume, and brand names.\n"
                        "   - Identify the **Brand** (e.g., 'Barilla', 'Mulino Bianco', 'Granarolo'). If no brand is specified, leave it null.\n"
                        "   - Identify the **Format/Weight/Volume** (e.g., '500 g', '1.5 Litri', 'confezione da 4 pezzi'). Normalize the unit text if possible.\n"
                        "4. **Determine Product Category**: Map the product to one of these standard Italian departments:\n"
                        "   - 'Alimentari' (Dry groceries, pasta, canned food, snacks)\n"
                        "   - 'Surgelati' (Frozen food)\n"
                        "   - 'Bevande' (Water, sodas, juices, alcohol/wine/beer)\n"
                        "   - 'Ortofrutta' (Fresh fruits and vegetables)\n"
                        "   - 'Macelleria' (Fresh meat and poultry)\n"
                        "   - 'Pescheria' (Fresh fish and seafood)\n"
                        "   - 'Gastronomia' (Deli, cheese, cured meats, ready meals)\n"
                        "   - 'Latticini e Freschi' (Yogurt, milk, butter, fresh pasta)\n"
                        "   - 'Igiene Casa' (Detergents, cleaning products, paper towels)\n"
                        "   - 'Cura Persona' (Shampoo, soap, cosmetics, baby care)\n"
                        "   - 'Pet Food' (Dog/cat food, pet care)\n"
                        "   - 'No Food' (Electronics, clothing, housewares)\n"
                        "5. **Frame Bounding Box (`bbox`)**:\n"
                        "   - Locate the boundary of the **PRODUCT PHOTO or packaging image ONLY**.\n"
                        "   - If the product illustration shows multiple items, packages, or color variants grouped together (e.g. three pasta boxes of different shapes, two colored lanterns, or a set of coffee cups), frame the **entire group of items** in a single bounding box rather than choosing just one.\n"
                        "   - Do **NOT** include the surrounding text descriptions, price tags/bubbles, brand logos (unless on the package), or adjacent items.\n"
                        "   - Calculate normalized coordinates `[ymin, xmin, ymax, xmax]` from `0` to `1000` using the red-labeled light grid overlaid on the page as a reference ruler.\n"
                        "   - Add a tiny safety margin of 2-3% around the product packaging to prevent tight cropping.\n"
                        "</instructions>\n\n"
                        "<validation_rules>\n"
                        "- **No duplicates**: Do not extract the same product card multiple times on the same page.\n"
                        "- **Strict Bounding Boxes**: The bounding box coordinates must be integers in range `[0, 1000]`. Ensure `ymin < ymax` and `xmin < xmax`.\n"
                        "- **Accurate parsing**: Do not hallucinate brand names or package details if they are not explicitly printed on the flyer page.\n"
                        "</validation_rules>"
                    )
                    
                    # Engine B.1: Gemini Multimodal Visual OCR
                    if self.use_gemini:
                        model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-pro")
                        logger.info(f"Using Gemini {model_name} visual parsing API...")
                        from google import genai
                        from google.genai import types
                        from PIL import Image
                        import json
                        
                        if not os.environ.get("GEMINI_API_KEY"):
                            raise ValueError(
                                "GEMINI_API_KEY environment variable is missing. "
                                "Please configure your API key or run without the '--use-gemini' flag."
                            )
                            
                        client = genai.Client()
                        
                        for page_idx in range(total_pages):
                            page = pdf.pages[page_idx]
                            logger.info(f"Processing Page {page_idx + 1}/{total_pages} via Gemini...")
                            
                            try:
                                pil_img = page.to_image(resolution=120).original
                                from utils.image_manager import draw_coordinate_grid
                                grid_pil_img = draw_coordinate_grid(pil_img)
                            except Exception as render_err:
                                logger.error(f"Failed to render page {page_idx + 1}: {render_err}")
                                continue
                                
                            try:
                                response = None
                                max_retries = 3
                                retry_backoff = 3
                                for attempt in range(max_retries):
                                    try:
                                        response = client.models.generate_content(
                                            model=model_name,
                                            contents=[grid_pil_img, prompt],
                                            config=types.GenerateContentConfig(
                                                response_mime_type="application/json",
                                                response_schema=ExtractedOffersList,
                                                temperature=0.1
                                            ),
                                        )
                                        break
                                    except Exception as api_err:
                                        if attempt == max_retries - 1:
                                            raise api_err
                                        logger.warning(
                                            f"Gemini API call failed (attempt {attempt + 1}/{max_retries}): {api_err}. "
                                            f"Retrying in {retry_backoff} seconds..."
                                        )
                                        time.sleep(retry_backoff)
                                        retry_backoff *= 2
                                        
                                data = json.loads(response.text)
                                offers = data.get("offers", [])
                                logger.info(f"Page {page_idx + 1}: Extracted {len(offers)} offers from Gemini.")
                                
                                for idx, o in enumerate(offers):
                                    name = o.get("name")
                                    price = o.get("price")
                                    if not name or price is None:
                                        continue
                                        
                                    brand = o.get("brand")
                                    weight = o.get("weight_or_volume")
                                    orig_price = o.get("original_price")
                                    discount = o.get("discount_percentage")
                                    bbox = o.get("bbox")
                                    category = o.get("category")
                                    
                                    payload_str = f"{self._supermarket_name}:{store_id}:ALL:{name}:{price:.2f}"
                                    offer_id = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:32]
                                    
                                    image_url = self._extract_and_save_product_image(name, bbox, pil_img, store_id, offer_id, page=page)
                                            
                                    offer = ProductOffer(
                                        offer_id=offer_id,
                                        supermarket=self._supermarket_name,
                                        store_id=store_id,
                                        name=name.capitalize(),
                                        brand=brand,
                                        weight_or_volume=weight,
                                        price=price,
                                        original_price=orig_price,
                                        discount_percentage=discount,
                                        price_per_unit=None,
                                        ean_code=None,
                                        image_url=image_url,
                                        category=category,
                                        promo_type="STANDARD",
                                        validity_string=None
                                    )
                                    parsed_offers.append(offer)
                            except Exception as page_api_err:
                                logger.error(f"Gemini page parsing failed: {page_api_err}")
                                continue
                                
                    # Engine B.2: Claude Haiku 4.5 Multimodal Visual OCR
                    elif self.use_claude:
                        parsed_offers = self._parse_scanned_flyer_via_claude(file_path, store_id)
                                
                    # Engine B.3: Local Offline Tesseract OCR (Default Fallback)
                    else:
                        import shutil
                        if not shutil.which("tesseract"):
                            raise RuntimeError(
                                "\n" + "="*80 + "\n"
                                "Tesseract OCR command-line tool is not installed on this system.\n"
                                "To run completely offline, please install Tesseract:\n"
                                "  - Linux (Ubuntu/Debian): 'sudo apt install tesseract-ocr tesseract-ocr-ita'\n"
                                "  - macOS: 'brew install tesseract tesseract-lang'\n"
                                "  - Conda: 'conda install -c conda-forge tesseract'\n"
                                "Alternatively, if you prefer to use Gemini's Free Tier visual OCR API,\n"
                                "run the command with the '--use-gemini' flag.\n"
                                + "="*80
                            )
                            
                        import pytesseract
                        logger.info("Using local Tesseract OCR offline engine...")
                        
                        validity_string = None
                        if total_pages > 0:
                            first_page = pdf.pages[0]
                            try:
                                pil_img = first_page.to_image(resolution=120).original
                                ocr_data = pytesseract.image_to_data(pil_img, lang="ita", output_type=pytesseract.Output.DICT)
                                tokens = [t for t in ocr_data["text"] if t and t.strip()]
                                first_page_text = " ".join(tokens)
                                validity_string = self._parser.parse_flyer_validity(first_page_text)
                                if validity_string:
                                    logger.info(f"Flyer validity resolved offline: '{validity_string}'")
                            except Exception as e:
                                logger.debug(f"Offline validity date extraction error: {e}")
                                
                        for page_idx in range(total_pages):
                            page = pdf.pages[page_idx]
                            logger.info(f"Segmenting Page {page_idx + 1}/{total_pages} offline...")
                            
                            try:
                                pil_img = page.to_image(resolution=120).original
                                w_px, h_px = pil_img.size
                                page_w = float(page.width)
                                page_h = float(page.height)
                                
                                scale_x = page_w / w_px
                                scale_y = page_h / h_px
                                
                                ocr_data = pytesseract.image_to_data(pil_img, lang="ita", output_type=pytesseract.Output.DICT)
                                ocr_words = []
                                
                                for idx in range(len(ocr_data["text"])):
                                    w_text = ocr_data["text"][idx]
                                    conf = ocr_data["conf"][idx]
                                    
                                    if w_text and w_text.strip() and int(conf) > 30:
                                        left = ocr_data["left"][idx]
                                        top = ocr_data["top"][idx]
                                        width = ocr_data["width"][idx]
                                        height = ocr_data["height"][idx]
                                        
                                        x0 = left * scale_x
                                        top_val = top * scale_y
                                        x1 = (left + width) * scale_x
                                        bottom = (top + height) * scale_y
                                        
                                        ocr_words.append({
                                            "x0": x0,
                                            "x1": x1,
                                            "top": top_val,
                                            "bottom": bottom,
                                            "text": w_text.strip()
                                        })
                                        
                                ocr_page = OcrPageWrapper(page, ocr_words)
                                cells = self._segmenter.segment_page(ocr_page)
                                
                                for cell in cells:
                                    try:
                                        offer = self._parser.parse_cell(cell["text"], store_id, validity_string)
                                        if offer:
                                            offer.image_url = self._crop_and_save_card_image_from_cached(
                                                pil_img,
                                                cell["bbox"],
                                                ocr_page,
                                                store_id,
                                                offer.offer_id,
                                                col_idx=cell.get("col_idx"),
                                                col_count=cell.get("col_count"),
                                                product_name=offer.name
                                            )
                                            offer.supermarket = self._supermarket_name
                                            parsed_offers.append(offer)
                                    except ValueError as parse_err:
                                        logger.debug(f"Cell parsing ValueError: {parse_err}")
                                    except Exception as parse_err:
                                        logger.debug(f"Cell parsing unexpected exception: {parse_err}")
                            except Exception as ocr_page_err:
                                logger.error(f"Failed to segment page {page_idx + 1} offline: {ocr_page_err}")
                                
        except Exception as e:
            logger.error(f"Critical failure while reading PDF {os.path.basename(file_path)}: {e}")
            
        if total_pages > 0:
            yield_per_page = len(parsed_offers) / max(1, total_pages)
            is_claude_already = (self.engine == "CLAUDE" or (has_vector_text is False and self.engine == "AUTO" and not self.use_gemini and self.use_claude))
            
            if (len(parsed_offers) < 3 or yield_per_page < 0.6) and not is_claude_already:
                logger.warning(
                    f"Yield threshold check failed: extracted {len(parsed_offers)} offers from {total_pages} pages "
                    f"(yield: {yield_per_page:.2f} offers/page). "
                    f"Self-healing: automatically triggering visual OCR fallback via Anthropic Claude API..."
                )
                claude_offers = self._parse_scanned_flyer_via_claude(file_path, store_id)
                if claude_offers:
                    logger.info(f"Self-healing complete. Claude API successfully extracted {len(claude_offers)} offers.")
                    parsed_offers = claude_offers
            
        return parsed_offers

    def _crop_and_save_card_image_from_cached(
        self, 
        pil_img: Any, 
        bbox: tuple, 
        page: Any, 
        store_id: str, 
        offer_id: str,
        col_idx: Optional[int] = None,
        col_count: Optional[int] = None,
        product_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Crops the card image using a pre-rendered Pillow image object and saves it locally.
        Uses a uniform grid-snapping algorithm if column metadata is available.
        """
        from utils.image_manager import get_standard_image, find_reusable_image, post_process_image_background
        
        if product_name:
            std_url = get_standard_image(product_name)
            if std_url:
                return std_url
            
            reusable_url = find_reusable_image(self._supermarket_name, product_name)
            if reusable_url:
                return reusable_url

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
            
            best_img = None
            if bbox and len(bbox) >= 3:
                grid_x0 = bbox[0]
                grid_x1 = bbox[2]
            elif col_idx is not None and col_count is not None and col_count > 0:
                col_w = page_w / col_count
                grid_x0 = col_idx * col_w
                grid_x1 = (col_idx + 1) * col_w
            else:
                grid_x0 = 0
                grid_x1 = page_w
                
            if grid_x0 is not None and grid_x1 is not None:
                matching_images = []
                for img in getattr(page, "images", []):
                    img_x0 = img.get("x0", 0)
                    img_x1 = img.get("x1", 0)
                    img_y0 = img.get("top", 0)
                    img_y1 = img.get("bottom", 0)
                    
                    img_cx = (img_x0 + img_x1) / 2.0
                    horizontal_match = grid_x0 <= img_cx <= grid_x1
                    
                    img_cy = (img_y0 + img_y1) / 2.0
                    vertical_match = bbox[1] - 50 <= img_cy <= bbox[3] + 30
                    
                    is_large = img.get("width", 0) > 20 and img.get("height", 0) > 20
                    
                    if horizontal_match and vertical_match and is_large:
                        matching_images.append(img)
                        
                if matching_images:
                    matching_images.sort(key=lambda img: img.get("width", 0) * img.get("height", 0), reverse=True)
                    best_img = matching_images[0]
            
            if best_img:
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
                if bbox and len(bbox) >= 3:
                    x0 = bbox[0]
                    x1 = bbox[2]
                elif col_idx is not None and col_count is not None and col_count > 0:
                    col_w = page_w / col_count
                    x0 = col_idx * col_w
                    x1 = (col_idx + 1) * col_w
                else:
                    x0 = 0
                    x1 = page_w
                
                # Apply margin safeguards if bounds are narrow
                w = x1 - x0
                if w < 120 and bbox and len(bbox) >= 3:
                    x0 = max(0.0, bbox[0] - 130)
                    x1 = min(page_w, bbox[2] + 15)
                
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
            cropped_img = post_process_image_background(cropped_img)
            cropped_img.save(file_path, "PNG")
            return db_url
        except Exception as e:
            logger.debug(f"Failed to crop from cached image for offer {offer_id}: {e}")
            return None

    def _log_missed_product(self, file_path: str, page_idx: int, reason: str, text: str) -> None:
        """Logs skipped parsed cells containing price keywords for manual audit."""
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

    def _extract_and_save_product_image(
        self,
        name: str,
        bbox: Optional[List[int]],
        pil_img: Any,
        store_id: str,
        offer_id: str,
        page: Optional[Any] = None
    ) -> Optional[str]:
        """
        Extracts a product image using a standard lookup or crops it from the page image.
        
        Args:
            name: Product name.
            bbox: Bounding box coordinates [ymin, xmin, ymax, xmax] normalized from 0 to 1000.
            pil_img: PIL Image object of the flyer page.
            store_id: Store identifier.
            offer_id: Unique offer hash.
            page: pdfplumber Page object (optional, for snapping to native PDF raster images).
            
        Returns:
            The image URL/path or None.
        """
        from utils.image_manager import get_standard_image, find_reusable_image, post_process_image_background
        image_url = get_standard_image(name)
        if not image_url:
            image_url = find_reusable_image(self._supermarket_name, name)
            
        if not image_url and bbox and len(bbox) == 4 and pil_img:
            w_px, h_px = pil_img.size
            page_w = float(page.width) if page else None
            page_h = float(page.height) if page else None
            
            best_img = None
            if page and page_w and page_h:
                ymin, xmin, ymax, xmax = bbox
                # Convert normalized bbox [0, 1000] to PDF points
                bbox_x0 = (xmin / 1000.0) * page_w
                bbox_y0 = (ymin / 1000.0) * page_h
                bbox_x1 = (xmax / 1000.0) * page_w
                bbox_y1 = (ymax / 1000.0) * page_h
                
                matching_images = []
                for img in getattr(page, "images", []):
                    img_x0 = img.get("x0", 0)
                    img_x1 = img.get("x1", 0)
                    img_y0 = img.get("top", 0)
                    img_y1 = img.get("bottom", 0)
                    
                    img_w = img.get("width", 0)
                    img_h = img.get("height", 0)
                    if img_w <= 20 or img_h <= 20:
                        continue # ignore small decoration icons
                        
                    # Calculate intersection over the image area
                    x_left = max(bbox_x0, img_x0)
                    y_top = max(bbox_y0, img_y0)
                    x_right = min(bbox_x1, img_x1)
                    y_bottom = min(bbox_y1, img_y1)
                    
                    if x_right > x_left and y_bottom > y_top:
                        intersection_area = (x_right - x_left) * (y_bottom - y_top)
                        img_area = img_w * img_h
                        overlap_ratio = intersection_area / img_area
                        
                        # Also check if image center is within or very close to bbox
                        img_cx = (img_x0 + img_x1) / 2.0
                        img_cy = (img_y0 + img_y1) / 2.0
                        center_match = (bbox_x0 - 20) <= img_cx <= (bbox_x1 + 20) and (bbox_y0 - 20) <= img_cy <= (bbox_y1 + 20)
                        
                        if overlap_ratio > 0.4 or center_match:
                            matching_images.append((img, overlap_ratio))
                            
                if matching_images:
                    matching_images.sort(key=lambda item: (item[1], item[0]["width"] * item[0]["height"]), reverse=True)
                    best_img = matching_images[0][0]
                    logger.info(f"Snapping VLM bbox for '{name}' to native PDF raster image coordinate box: x0={best_img['x0']:.1f}, top={best_img['top']:.1f}")

            if best_img and page_w and page_h:
                scale_x = w_px / page_w
                scale_y = h_px / page_h
                pad = 2.0
                ix0 = max(0.0, best_img["x0"] - pad)
                iy0 = max(0.0, best_img["top"] - pad)
                ix1 = min(page_w, best_img["x1"] + pad)
                iy1 = min(page_h, best_img["bottom"] + pad)
                
                crop_box = (
                    max(0, int(ix0 * scale_x)),
                    max(0, int(iy0 * scale_y)),
                    min(w_px, int(ix1 * scale_x)),
                    min(h_px, int(iy1 * scale_y))
                )
            else:
                ymin, xmin, ymax, xmax = bbox
                px_x0 = int((xmin / 1000.0) * w_px)
                px_y0 = int((ymin / 1000.0) * h_px)
                px_x1 = int((xmax / 1000.0) * w_px)
                px_y1 = int((ymax / 1000.0) * h_px)
                
                box_w = px_x1 - px_x0
                box_w = max(1, box_w)
                box_h = px_y1 - px_y0
                box_h = max(1, box_h)
                pad_x = int(box_w * 0.03)  # Refined 3% safety margin
                pad_y = int(box_h * 0.03)
                
                crop_box = (
                    max(0, px_x0 - pad_x),
                    max(0, px_y0 - pad_y),
                    min(w_px, px_x1 + pad_x),
                    min(h_px, px_y1 + pad_y)
                )
            
            os.makedirs("storage/images", exist_ok=True)
            file_name = f"{self._supermarket_name}_{store_id}_{offer_id}.png"
            file_path = os.path.join("storage/images", file_name)
            
            try:
                cropped = pil_img.crop(crop_box)
                cropped = post_process_image_background(cropped)
                cropped.save(file_path, "PNG")
                image_url = f"/storage/images/{file_name}"
            except Exception as crop_err:
                logger.debug(f"Pillow crop error: {crop_err}")
                
        return image_url

    def _parse_scanned_flyer_via_claude(self, file_path: str, store_id: str) -> List[ProductOffer]:
        """Executes scanned flyer OCR visual parsing using Anthropic's Claude API as a fallback."""
        import anthropic
        import base64
        import io
        import hashlib
        from PIL import Image
        
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("Cannot run Claude self-healing fallback because ANTHROPIC_API_KEY is not configured.")
            return []
            
        logger.info("Engaging Anthropic Claude Sonnet API for scanned flyer visual parsing fallback...")
        client = anthropic.Anthropic()
        
        prompt = (
            "<role>\n"
            "You are a state-of-the-art visual document analysis agent and expert OCR data extractor specializing in Italian GDO (Grande Distribuzione Organizzata) promotional flyers/circulars.\n"
            "</role>\n\n"
            "<task>\n"
            "Carefully inspect the provided flyer page image. Your objective is to extract every commercial product promotion (offer) displayed on the page.\n"
            "For each detected offer, perform step-by-step chain-of-thought reasoning to identify the product details and crop coordinates, and return the structured data.\n"
            "</task>\n\n"
            "<instructions>\n"
            "For each promotional item on the flyer page, follow these logical steps:\n"
            "1. **Identify Promotion Region**: Locate the distinct graphical cell, box, or region containing the product and its price.\n"
            "2. **Extract Price Details**:\n"
            "   - Read the price numbers carefully. Note that euros and cents are often formatted with different font sizes (e.g., a large '1' and a small superscript '49' means 1.49). Combine them correctly.\n"
            "   - Ignore \"al kg\" or \"al litro\" unit prices if a total package price is also shown; prioritize the package selling price.\n"
            "   - If a discount percentage (e.g., '-30%', 'Sconto 40%') is displayed, extract the percentage number as an integer.\n"
            "   - Look for any original pre-discount price (often crossed out) and extract it.\n"
            "3. **Extract Textual Details (in Italian)**:\n"
            "   - Identify the **Product Name** (e.g., 'Passata di pomodoro', 'Frollini con gocce di cioccolato'). Write it in Title Case. Exclude weight, volume, and brand names.\n"
            "   - Identify the **Brand** (e.g., 'Barilla', 'Mulino Bianco', 'Granarolo'). If no brand is specified, leave it null.\n"
            "   - Identify the **Format/Weight/Volume** (e.g., '500 g', '1.5 Litri', 'confezione da 4 pezzi'). Normalize the unit text if possible.\n"
            "4. **Determine Product Category**: Map the product to one of these standard Italian departments:\n"
            "   - 'Alimentari' (Dry groceries, pasta, canned food, snacks)\n"
            "   - 'Surgelati' (Frozen food)\n"
            "   - 'Bevande' (Water, sodas, juices, alcohol/wine/beer)\n"
            "   - 'Ortofrutta' (Fresh fruits and vegetables)\n"
            "   - 'Macelleria' (Fresh meat and poultry)\n"
            "   - 'Pescheria' (Fresh fish and seafood)\n"
            "   - 'Gastronomia' (Deli, cheese, cured meats, ready meals)\n"
            "   - 'Latticini e Freschi' (Yogurt, milk, butter, fresh pasta)\n"
            "   - 'Igiene Casa' (Detergents, cleaning products, paper towels)\n"
            "   - 'Cura Persona' (Shampoo, soap, cosmetics, baby care)\n"
            "   - 'Pet Food' (Dog/cat food, pet care)\n"
            "   - 'No Food' (Electronics, clothing, housewares)\n"
            "5. **Frame Bounding Box (`bbox`)**:\n"
            "   - Locate the boundary of the **PRODUCT PHOTO or packaging image ONLY**.\n"
            "   - If the product illustration shows multiple items, packages, or color variants grouped together (e.g. three pasta boxes of different shapes, two colored lanterns, or a set of coffee cups), frame the **entire group of items** in a single bounding box rather than choosing just one.\n"
            "   - Do **NOT** include the surrounding text descriptions, price tags/bubbles, brand logos (unless on the package), or adjacent items.\n"
            "   - Calculate normalized coordinates `[ymin, xmin, ymax, xmax]` from `0` to `1000` using the red-labeled light grid overlaid on the page as a reference ruler.\n"
            "   - Add a tiny safety margin of 2-3% around the product packaging to prevent tight cropping.\n"
            "</instructions>\n\n"
            "<validation_rules>\n"
            "- **No duplicates**: Do not extract the same product card multiple times on the same page.\n"
            "- **Strict Bounding Boxes**: The bounding box coordinates must be integers in range `[0, 1000]`. Ensure `ymin < ymax` and `xmin < xmax`.\n"
            "- **Accurate parsing**: Do not hallucinate brand names or package details if they are not explicitly printed on the flyer page.\n"
            "</validation_rules>"
        )
        
        tool_schema = {
            "name": "extract_offers",
            "description": "Extracts the list of commercial offers from the promotional flyer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "offers": {
                        "type": "array",
                        "description": "List of all offers found on the flyer page.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reasoning": {
                                    "type": "string",
                                    "description": "Chain-of-Thought reasoning: 1. Describe the packaging visually (e.g. colors, shape, features, graphics). 2. Find the product name, brand, weight and price. 3. Define the precise bounding box enclosing ONLY the packaging/product image itself, excluding price bubbles or text."
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Name of the product in Title Case, in Italian. Exclude brand and weight."
                                },
                                "brand": {
                                    "type": "string",
                                    "description": "Product brand (e.g., 'Mulino Bianco'). Leave null if not specified."
                                },
                                "weight_or_volume": {
                                    "type": "string",
                                    "description": "Format, weight or volume of the product (e.g., '500g', '1L', '6 pieces'). Leave null if not specified."
                                },
                                "price": {
                                    "type": "number",
                                    "description": "Decimal price of the offer (e.g., 1.99 or 0.85)."
                                },
                                "original_price": {
                                    "type": "number",
                                    "description": "Original pre-discount price if visible, otherwise null."
                                },
                                "discount_percentage": {
                                    "type": "integer",
                                    "description": "Discount percentage (e.g., 30 or 50). Leave null if not indicated."
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Standard Italian product category (e.g., 'Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Igiene Casa', 'Cura Persona')."
                                },
                                "bbox": {
                                    "type": "array",
                                    "description": "Product bounding box [ymin, xmin, ymax, xmax] normalized from 0 to 1000 framing strictly the product packaging or photo itself, excluding text description blocks, price tags, background clutter, or other products.",
                                    "items": {
                                        "type": "integer"
                                    }
                                }
                            },
                            "required": ["reasoning", "name", "price", "bbox"]
                        }
                    }
                },
                "required": ["offers"]
            }
        }
        
        claude_offers: List[ProductOffer] = []
        
        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                for page_idx in range(total_pages):
                    page = pdf.pages[page_idx]
                    logger.info(f"[Self-Healing] Processing Page {page_idx + 1}/{total_pages} via Claude...")
                    
                    try:
                        pil_img = page.to_image(resolution=120).original
                        from utils.image_manager import draw_coordinate_grid
                        grid_pil_img = draw_coordinate_grid(pil_img)
                    except Exception as render_err:
                        logger.error(f"Failed to render page {page_idx + 1} during fallback: {render_err}")
                        continue
                        
                    buffered = io.BytesIO()
                    grid_pil_img.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    
                    try:
                        response = None
                        max_retries = 3
                        retry_backoff = 3
                        for attempt in range(max_retries):
                            try:
                                response = client.messages.create(
                                    model=os.environ.get("CLAUDE_MODEL_NAME", "claude-3-5-sonnet-latest"),
                                    max_tokens=4000,
                                    temperature=0.1,
                                    system="You are an expert visual data extractor for Italian GDO promotional flyers.",
                                    messages=[
                                        {
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "image",
                                                    "source": {
                                                        "type": "base64",
                                                        "media_type": "image/png",
                                                        "data": img_base64
                                                    }
                                                },
                                                {
                                                    "type": "text",
                                                    "text": prompt
                                                }
                                            ]
                                        }
                                    ],
                                    tools=[tool_schema],
                                    tool_choice={"type": "tool", "name": "extract_offers"}
                                )
                                break
                            except Exception as api_err:
                                if attempt == max_retries - 1:
                                    raise api_err
                                logger.warning(
                                    f"Claude API call failed (attempt {attempt + 1}/{max_retries}): {api_err}. "
                                    f"Retrying in {retry_backoff} seconds..."
                                )
                                time.sleep(retry_backoff)
                                retry_backoff *= 2
                                
                        if not response:
                            continue
                            
                        tool_use = next(block for block in response.content if block.type == "tool_use")
                        offers = tool_use.input.get("offers", [])
                        logger.info(f"[Self-Healing] Page {page_idx + 1}: Extracted {len(offers)} offers from Claude.")
                        
                        for o in offers:
                            name = o.get("name")
                            price = o.get("price")
                            if not name or price is None:
                                continue
                                
                            brand = o.get("brand")
                            weight = o.get("weight_or_volume")
                            orig_price = o.get("original_price")
                            discount = o.get("discount_percentage")
                            bbox = o.get("bbox")
                            category = o.get("category")
                            
                            payload_str = f"{self._supermarket_name}:{store_id}:ALL:{name}:{price:.2f}"
                            offer_id = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:32]
                            
                            image_url = self._extract_and_save_product_image(name, bbox, pil_img, store_id, offer_id, page=page)
                                    
                            offer = ProductOffer(
                                offer_id=offer_id,
                                supermarket=self._supermarket_name,
                                store_id=store_id,
                                name=name.capitalize(),
                                brand=brand,
                                weight_or_volume=weight,
                                price=price,
                                original_price=orig_price,
                                discount_percentage=discount,
                                price_per_unit=None,
                                ean_code=None,
                                image_url=image_url,
                                category=category,
                                promo_type="STANDARD",
                                validity_string=None
                            )
                            claude_offers.append(offer)
                    except Exception as page_api_err:
                        logger.error(f"[Self-Healing] Claude page parsing failed: {page_api_err}")
                        continue
        except Exception as e:
            logger.error(f"[Self-Healing] Fallback execution failed: {e}")
            
        return claude_offers

    def _audit_and_self_heal_page_via_claude(
        self,
        pil_img: Any,
        store_id: str,
        page_idx: int,
        initial_offers: List[ProductOffer],
        validity_string: Optional[str] = None,
        page: Optional[Any] = None
    ) -> List[ProductOffer]:
        """
        Visually audits the vector-extracted offers of a page using Claude.
        Corrects names/prices, splits conflated items, adds missing items, 
        and extracts high-accuracy bounding boxes for product illustrations.
        """
        import anthropic
        import base64
        import io
        import json
        import hashlib
        
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("ANTHROPIC_API_KEY not set. Skipping Claude visual audit.")
            return initial_offers
            
        logger.info(f"[Visual Audit] Auditing Page {page_idx + 1} with Claude...")
        client = anthropic.Anthropic()
        
        # Serialize initial vector offers
        simplified_offers = []
        for o in initial_offers:
            simplified_offers.append({
                "id": o.offer_id,
                "name": o.name,
                "brand": o.brand or "",
                "weight_or_volume": o.weight_or_volume or "",
                "price": o.price,
                "original_price": o.original_price or None,
                "discount_percentage": o.discount_percentage or None,
                "promo_type": o.promo_type
            })
            
        # Encode image with grid overlay to base64
        from utils.image_manager import draw_coordinate_grid
        grid_pil_img = draw_coordinate_grid(pil_img)
        buffered = io.BytesIO()
        grid_pil_img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        prompt = (
            "<role>\n"
            "You are an expert data QA auditor and visual inspector for Italian GDO promotional flyers.\n"
            "</role>\n\n"
            "<task>\n"
            "You are provided with:\n"
            "1. An image of a flyer page.\n"
            "2. A list of structured product offers extracted from the page's PDF vector text layer.\n\n"
            "Your goal is to perform a visual audit of the page, reconcile the vector-extracted list against what is actually printed on the page, correct any errors, add missing items, delete non-product items, split conflated text elements, and calculate precise bounding boxes for product photos.\n"
            "</task>\n\n"
            "<input_data>\n"
            "<vector_extracted_offers>\n"
            f"{json.dumps(simplified_offers, indent=2)}\n"
            "</vector_extracted_offers>\n"
            "</input_data>\n\n"
            "<audit_instructions>\n"
            "For each item displayed visually on the page, audit the extracted list using these rules:\n"
            "1. **Verification & Bounding Box Update**:\n"
            "   - If a product on the page is correctly listed, verify its details (name, brand, weight, price).\n"
            "   - Add/update its `bbox` to frame **ONLY the product package or photo itself** (excluding text, prices, or bubbles).\n"
            "2. **Correction**:\n"
            "   - Correct misaligned prices (e.g. if the vector parser grabbed a unit price, e.g., '1,20 €/kg', instead of the package sale price, e.g., '2,40 €').\n"
            "   - Fix misidentified brands or misspelled names.\n"
            "3. **Splitting Conflated Offers**:\n"
            "   - If the vector-extracted text merged two distinct offers into a single item (e.g. 'Pasta Barilla / Olio Monini' with a single price), split them into two separate offers with their correct respective prices and package photos.\n"
            "4. **Adding Missing Offers**:\n"
            "   - If a product is visually in promotion on the page but absent from the vector list, add it as a new offer.\n"
            "5. **Deletion**:\n"
            "   - If an item in the vector list is a coupon, legal disclaimer, store logo, page header, or banner rather than a concrete product offer, delete/exclude it.\n"
            "6. **Promotion Type Classification**:\n"
            "   - Classify `promo_type` strictly using these rules:\n"
            "     - `1+1`: For \"1+1\", \"Prendi 2 paghi 1\", or similar offers.\n"
            "     - `PERCENTAGE_DISCOUNT`: If a discount percentage (e.g., \"30% di sconto\", \"-40%\") is prominently featured.\n"
            "     - `DISCOUNT`: For \"Prezzo speciale\", \"Sottocosto\", \"Offerta speciale\", or flat discount/value-cut promotions.\n"
            "     - `STANDARD`: For standard promotional pricing without explicit discount markings.\n"
            "7. **Bounding Box System**:\n"
            "   - Use normalized coordinates `[ymin, xmin, ymax, xmax]` in range `[0, 1000]`.\n"
            "   - A red-labeled light grid is overlaid on the image to help you read coordinates exactly.\n"
            "   - If the product illustration shows multiple items, packages, or color variants grouped together (e.g. three pasta boxes of different shapes, two colored lanterns, or a set of coffee cups), frame the **entire group of items** in a single bounding box rather than choosing just one.\n"
            "   - Frame ONLY the visual product package/photo with a tiny 2-3% safety margin.\n"
            "8. **Map to Input Offer ID (`original_id`)**:\n"
            "   - If an audited offer matches or corrects an item from the input `<vector_extracted_offers>` list, map it back to that item's `id` inside the `original_id` field.\n"
            "   - If the offer is newly added or split from another item (representing a different physical item on the page), set `original_id` to null or omit it.\n"
            "</audit_instructions>\n\n"
            "<validation_rules>\n"
            "- **Product Name (name)**: Clean Title Case in Italian (e.g., 'Caffè macinato'). No brand or weight in the name field.\n"
            "- **Brand (brand)**: Extract only the actual brand name. Null if not specified.\n"
            "- **Category (category)**: Map to a standard department ('Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Pescheria', 'Gastronomia', 'Latticini e Freschi', 'Igiene Casa', 'Cura Persona', 'Pet Food', 'No Food').\n"
            "- **No Hallucinations**: Every output offer must correspond to a real, visible item on the page.\n"
            "</validation_rules>"
        )
        
        tool_schema = {
            "name": "extract_offers",
            "description": "Extracts the verified and audited list of commercial offers from the promotional flyer page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "offers": {
                        "type": "array",
                        "description": "List of all audited offers found on the flyer page.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reasoning": {
                                    "type": "string",
                                    "description": "Describe the product packaging visually and explain any correction, split, addition or verification made."
                                },
                                "original_id": {
                                    "type": "string",
                                    "description": "The unique 'id' of the matching product from the input <vector_extracted_offers> list, or null/absent if this is a newly added or split offer."
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Name of the product in Title Case, in Italian. Exclude brand and weight."
                                },
                                "brand": {
                                    "type": "string",
                                    "description": "Product brand. Leave null if not specified."
                                },
                                "weight_or_volume": {
                                    "type": "string",
                                    "description": "Format, weight or volume of the product (e.g., '500g', '1.5L'). Leave null if not specified."
                                },
                                "price": {
                                    "type": "number",
                                    "description": "Decimal selling price of the offer."
                                },
                                "original_price": {
                                    "type": "number",
                                    "description": "Original pre-discount price if visible, otherwise null."
                                },
                                "discount_percentage": {
                                    "type": "integer",
                                    "description": "Discount percentage. Leave null if not indicated."
                                },
                                "promo_type": {
                                    "type": "string",
                                    "description": "Type of promotion. E.g. 'STANDARD', '1+1', 'DISCOUNT', 'PERCENTAGE_DISCOUNT'."
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Standard Italian product category."
                                },
                                "bbox": {
                                    "type": "array",
                                    "description": "Product bounding box [ymin, xmin, ymax, xmax] normalized from 0 to 1000 framing strictly the packaging or photo itself.",
                                    "items": {
                                        "type": "integer"
                                    }
                                }
                            },
                            "required": ["reasoning", "name", "price", "bbox"]
                        }
                    }
                },
                "required": ["offers"]
            }
        }
        
        audited_offers: List[ProductOffer] = []
        try:
            response = None
            max_retries = 3
            retry_backoff = 3
            for attempt in range(max_retries):
                try:
                    response = client.messages.create(
                        model=os.environ.get("CLAUDE_MODEL_NAME", "claude-3-5-sonnet-latest"),
                        max_tokens=4000,
                        temperature=0.1,
                        system="You are an expert data auditor for Italian GDO promotional flyers.",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/png",
                                            "data": img_base64
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        tools=[tool_schema],
                        tool_choice={"type": "tool", "name": "extract_offers"}
                    )
                    break
                except Exception as api_err:
                    if attempt == max_retries - 1:
                        raise api_err
                    logger.warning(f"Claude API failed (attempt {attempt+1}/{max_retries}): {api_err}. Retrying...")
                    time.sleep(retry_backoff)
                    retry_backoff *= 2
                    
            if response:
                tool_use = next(block for block in response.content if block.type == "tool_use")
                offers_data = tool_use.input.get("offers", [])
                logger.info(f"[Visual Audit] Page {page_idx + 1}: Claude verified {len(offers_data)} offers.")
                
                initial_offers_by_id = {init_o.offer_id: init_o for init_o in initial_offers}
                
                for o in offers_data:
                    name = o.get("name")
                    price = o.get("price")
                    if not name or price is None:
                        continue
                        
                    brand = o.get("brand")
                    weight = o.get("weight_or_volume")
                    orig_price = o.get("original_price")
                    discount = o.get("discount_percentage")
                    bbox = o.get("bbox")
                    category = o.get("category")
                    
                    promo_type = o.get("promo_type", "STANDARD")
                    payload_str = f"{self._supermarket_name}:{store_id}:{validity_string or 'ALL'}:{name}:{price:.2f}"
                    offer_id = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:32]
                    
                    original_id = o.get("original_id")
                    matched_initial_offer = initial_offers_by_id.get(original_id) if original_id else None
                    
                    if not matched_initial_offer:
                        # Try exact match on name (case-insensitive) and price as fallback
                        for init_o in initial_offers:
                            if init_o.name.lower() == name.lower() and init_o.price == price:
                                matched_initial_offer = init_o
                                break
                                
                    image_url = None
                    if matched_initial_offer and matched_initial_offer.image_url:
                        # Reuse the high-quality image parsed directly from vector layers
                        image_url = matched_initial_offer.image_url
                        logger.info(f"[Visual Audit] Reusing high-quality vector-extracted image for: '{name}'")
                    else:
                        # Fallback to cropping from page using Claude's bounding box
                        image_url = self._extract_and_save_product_image(name, bbox, pil_img, store_id, offer_id, page=page)
                            
                    offer = ProductOffer(
                        offer_id=offer_id,
                        supermarket=self._supermarket_name,
                        store_id=store_id,
                        name=name.capitalize(),
                        brand=brand,
                        weight_or_volume=weight,
                        price=price,
                        original_price=orig_price,
                        discount_percentage=discount,
                        price_per_unit=None,
                        ean_code=None,
                        image_url=image_url,
                        category=category,
                        promo_type=promo_type,
                        validity_string=validity_string
                    )
                    audited_offers.append(offer)
        except Exception as err:
            logger.error(f"[Visual Audit] Claude verification failed for page {page_idx + 1}: {err}")
            return initial_offers
            
        return audited_offers
