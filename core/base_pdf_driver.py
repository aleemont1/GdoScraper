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
    reasoning: str = Field(description="Ragionamento dettagliato step-by-step: leggi il prezzo, identifica il brand/nome/peso, e calcola i confini esatti della sola foto del prodotto (Chain-of-Thought)")
    name: str = Field(description="Nome del prodotto ed eventuale descrizione breve in italiano (es. 'Biscotti Frollini')")
    brand: Optional[str] = Field(None, description="Marca del prodotto se chiaramente indicata (es. 'Mulino Bianco')")
    weight_or_volume: Optional[str] = Field(None, description="Peso, volume o quantità (es. '500g', '6x1.5L')")
    price: float = Field(description="Prezzo in euro dell'offerta in cifre decimali (es. 1.89)")
    original_price: Optional[float] = Field(None, description="Prezzo originale o barrato se indicato (es. 2.49)")
    discount_percentage: Optional[int] = Field(None, description="Percentuale di sconto se indicata (es. 30)")
    category: Optional[str] = Field(None, description="Categoria merceologica del prodotto (es. 'Alimentari', 'Bevande')")
    bbox: List[int] = Field(description="Coordinate rettangolo [ymin, xmin, ymax, xmax] normalizzate da 0 a 1000 che inquadrano la card del prodotto")


class ExtractedOffersList(BaseModel):
    offers: List[ExtractedOffer]


class OcrPageWrapper:
    """
    Adapter wrapper that simulates a pdfplumber Page object,
    substituting vector-embedded words with local OCR-extracted words.
    """
    def __init__(self, page: Any, words_list: List[Dict[str, Any]]) -> None:
        self._page = page
        self.width = page.width
        self.height = page.height
        self.images = getattr(page, "images", [])
        self._words = words_list

    def extract_words(self) -> List[Dict[str, Any]]:
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
        engine: str = "AUTO"
    ) -> None:
        self._resolved_store_id: Optional[str] = None
        self.parallel = parallel
        
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
        is_coord = re.match(r"^\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?\s*$", store_id)
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
        normalizing extracted text blocks into product offers with crisp visual previews.
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
                
                # Dynamic Vector vs Scanned Layout Detection (with optional driver override)
                if self._current_is_vector is not None:
                    has_vector_text = self._current_is_vector
                elif self.engine != "AUTO":
                    # If a specific OCR engine (Gemini, Claude, Tesseract) is selected, completely skip vector grid parsing
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
                                    parsed_offers.append(offer)
                                    flyer_offers_count += 1
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
                                
                    logger.info(f"Finished parsing vector flyer {os.path.basename(file_path)}. Extracted {flyer_offers_count} products.")
                
                # --- STRATEGY B: Scanned PDF / Image-Only Brochure Parsing ---
                else:
                    logger.info("Scanned/Flat-image brochure detected. Engaging OCR visual extraction fallback...")
                    
                    # Engine B.1: Gemini 2.5 Flash Multimodal Visual OCR
                    if self.use_gemini:
                        logger.info("Using Gemini 2.5 Flash visual parsing API...")
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
                        
                        prompt = (
                            "Ruolo: Sei un estrattore esperto di dati visivi e OCR per i volantini promozionali della GDO (Grande Distribuzione Organizzata) italiana.\n"
                            "Task: Analizza attentamente l'immagine di questa pagina di volantino del supermercato ed estrai in modo accurato tutte le offerte commerciali.\n\n"
                            "Fasi per ciascuna offerta (ragionamento step-by-step):\n"
                            "1. Localizza visivamente una specifica scheda/sezione promozionale di prodotto.\n"
                            "2. Leggi il prezzo (es. '1,49' -> convertilo in float 1.49) ed eventuali sconti (es. '-30%'). Se il prezzo ha euro e centesimi separati o rimpiccioliti, uniscili correttamente.\n"
                            "3. Identifica il testo descrittivo del prodotto in italiano, isolando il nome (name), la marca (brand, es. 'Bio', 'Valis') e il formato/peso (weight_or_volume, es. '400 g', '1,5 L', 'confezione da 4 pezzi').\n"
                            "4. Identifica i confini della FOTO del prodotto o del suo packaging. Lascia un comodo margine di sicurezza (un bordo o 'breathing room' extra di circa il 5-8%) attorno al prodotto per evitare che le estremità, i tappi o le etichette vengano tagliati.\n"
                            "5. Calcola le coordinate normalizzate [ymin, xmin, ymax, xmax] da 0 a 1000 per l'immagine del prodotto.\n\n"
                            "Regole di validazione:\n"
                            "- Nome prodotto (name): Scrivilo in Title Case pulito (es. 'Biscotti frollini integrali'). Non includere pesi o marche qui.\n"
                            "- Marca (brand): Estrai solo il brand reale (se indicato). Se assente, lascia null.\n"
                            "- Categoria (category): Mappa il prodotto in un reparto italiano standard (es. 'Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Igiene Casa', 'Cura Persona').\n"
                            "- Rettangolo (bbox): Deve inquadrare la foto dell'articolo promozionale lasciando un piccolo margine di sicurezza del 5-8% su tutti i lati nel sistema normalizzato 0-1000 (ymin alto, xmin sinistra, ymax basso, xmax destra)."
                        )
                        
                        for page_idx in range(total_pages):
                            page = pdf.pages[page_idx]
                            logger.info(f"Processing Page {page_idx + 1}/{total_pages} via Gemini...")
                            
                            try:
                                pil_img = page.to_image(resolution=120).original
                            except Exception as render_err:
                                logger.error(f"Failed to render page {page_idx + 1}: {render_err}")
                                continue
                                
                            try:
                                # Generation call wrapped in robust exponential backoff loop
                                response = None
                                max_retries = 3
                                retry_backoff = 3
                                for attempt in range(max_retries):
                                    try:
                                        response = client.models.generate_content(
                                            model='gemini-2.5-flash',
                                            contents=[pil_img, prompt],
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
                                    
                                    # 1. Check for standard catalog or fuzzy reusable images
                                    from utils.image_manager import get_standard_image, find_reusable_image, post_process_image_background
                                    image_url = get_standard_image(name)
                                    if not image_url:
                                        image_url = find_reusable_image(self._supermarket_name, name)
                                        
                                    if not image_url and bbox and len(bbox) == 4:
                                        ymin, xmin, ymax, xmax = bbox
                                        w_px, h_px = pil_img.size
                                        
                                        px_x0 = int((xmin / 1000.0) * w_px)
                                        px_y0 = int((ymin / 1000.0) * h_px)
                                        px_x1 = int((xmax / 1000.0) * w_px)
                                        px_y1 = int((ymax / 1000.0) * h_px)
                                        
                                        # Calculate safety margin padding of 6%
                                        box_w = px_x1 - px_x0
                                        box_h = px_y1 - px_y0
                                        pad_x = int(box_w * 0.06)
                                        pad_y = int(box_h * 0.06)
                                        
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
                                            # Apply white background auto-trimmer post-processing
                                            cropped = post_process_image_background(cropped)
                                            cropped.save(file_path, "PNG")
                                            image_url = f"/storage/images/{file_name}"
                                        except Exception as crop_err:
                                            logger.debug(f"Pillow crop error: {crop_err}")
                                            
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
                        logger.info("Using Anthropic Claude Haiku 4.5 visual parsing API...")
                        import anthropic
                        import base64
                        from PIL import Image
                        import io
                        
                        if not os.environ.get("ANTHROPIC_API_KEY"):
                            raise ValueError(
                                "ANTHROPIC_API_KEY environment variable is missing. "
                                "Please configure your API key or run with a different parsing engine."
                            )
                            
                        client = anthropic.Anthropic()
                        
                        prompt = (
                            "Ruolo: Sei un estrattore esperto di dati visivi e OCR per i volantini promozionali della GDO (Grande Distribuzione Organizzata) italiana.\n"
                            "Task: Analizza attentamente l'immagine di questa pagina di volantino del supermercato ed estrai in modo accurato tutte le offerte commerciali.\n\n"
                            "Fasi per ciascuna offerta (ragionamento step-by-step):\n"
                            "1. Localizza visivamente una specifica scheda/sezione promozionale di prodotto.\n"
                            "2. Leggi il prezzo (es. '1,49' -> convertilo in float 1.49) ed eventuali sconti (es. '-30%'). Se il prezzo ha euro e centesimi separati o rimpiccioliti, uniscili correttamente.\n"
                            "3. Identifica il testo descrittivo del prodotto in italiano, isolando il nome (name), la marca (brand, es. 'Bio', 'Valis') e il formato/peso (weight_or_volume, es. '400 g', '1,5 L', 'confezione da 4 pezzi').\n"
                            "4. Identifica i confini della FOTO del prodotto o del suo packaging. Lascia un comodo margine di sicurezza (un bordo o 'breathing room' extra di circa il 5-8%) attorno al prodotto per evitare che le estremità, i tappi o le etichette vengano tagliati.\n"
                            "5. Calcola le coordinate normalizzate [ymin, xmin, ymax, xmax] da 0 a 1000 per l'immagine del prodotto.\n\n"
                            "Regole di validazione:\n"
                            "- Nome prodotto (name): Scrivilo in Title Case pulito (es. 'Biscotti frollini integrali'). Non includere pesi o marche qui.\n"
                            "- Marca (brand): Estrai solo il brand reale (se indicato). Se assente, lascia null.\n"
                            "- Categoria (category): Mappa il prodotto in un reparto italiano standard (es. 'Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Igiene Casa', 'Cura Persona').\n"
                            "- Rettangolo (bbox): Deve inquadrare la foto dell'articolo promozionale lasciando un piccolo margine di sicurezza del 5-8% su tutti i lati nel sistema normalizzato 0-1000 (ymin alto, xmin sinistra, ymax basso, xmax destra)."
                        )
                        
                        tool_schema = {
                            "name": "extract_offers",
                            "description": "Estrae l'elenco delle offerte commerciali dal volantino promozionale.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "offers": {
                                        "type": "array",
                                        "description": "Lista di tutte le offerte trovate nella pagina del volantino.",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "reasoning": {
                                                    "type": "string",
                                                    "description": "Ragionamento dettagliato step-by-step per identificare l'offerta e il suo box visivo."
                                                },
                                                "name": {
                                                    "type": "string",
                                                    "description": "Nome del prodotto in Title Case, in italiano. Escludere peso e marca."
                                                },
                                                "brand": {
                                                    "type": "string",
                                                    "description": "Marca del prodotto (es. 'Mulino Bianco'). Lasciare null se non specificato."
                                                },
                                                "weight_or_volume": {
                                                    "type": "string",
                                                    "description": "Formato, peso o volume del prodotto (es. '500g', '1L', '6 pezzi'). Lasciare null se non specificato."
                                                },
                                                "price": {
                                                    "type": "number",
                                                    "description": "Prezzo decimale dell'offerta (es. 1.99 o 0.85)."
                                                },
                                                "original_price": {
                                                    "type": "number",
                                                    "description": "Prezzo barrato/originale se visibile, altrimenti null."
                                                },
                                                "discount_percentage": {
                                                    "type": "integer",
                                                    "description": "Percentuale di sconto (es. 30 o 50). Lasciare null se non indicata."
                                                },
                                                "category": {
                                                    "type": "string",
                                                    "description": "Categoria merceologica in italiano (es. 'Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Igiene Casa', 'Cura Persona')."
                                                },
                                                "bbox": {
                                                    "type": "array",
                                                    "description": "Rettangolo di delimitazione del prodotto [ymin, xmin, ymax, xmax] normalizzato da 0 a 1000.",
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
                        
                        for page_idx in range(total_pages):
                            page = pdf.pages[page_idx]
                            logger.info(f"Processing Page {page_idx + 1}/{total_pages} via Claude...")
                            
                            try:
                                pil_img = page.to_image(resolution=120).original
                            except Exception as render_err:
                                logger.error(f"Failed to render page {page_idx + 1}: {render_err}")
                                continue
                                
                            # Convert PIL image to base64 PNG
                            buffered = io.BytesIO()
                            pil_img.save(buffered, format="PNG")
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
                                            system="Sei un estrattore esperto di dati visivi per volantini promozionali della GDO italiana.",
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
                                    
                                # Parse the tool invocation inputs
                                tool_use = next(block for block in response.content if block.type == "tool_use")
                                offers = tool_use.input.get("offers", [])
                                logger.info(f"Page {page_idx + 1}: Extracted {len(offers)} offers from Claude.")
                                
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
                                    
                                    # 1. Check for standard catalog or fuzzy reusable images
                                    from utils.image_manager import get_standard_image, find_reusable_image, post_process_image_background
                                    image_url = get_standard_image(name)
                                    if not image_url:
                                        image_url = find_reusable_image(self._supermarket_name, name)
                                        
                                    if not image_url and bbox and len(bbox) == 4:
                                        ymin, xmin, ymax, xmax = bbox
                                        w_px, h_px = pil_img.size
                                        
                                        px_x0 = int((xmin / 1000.0) * w_px)
                                        px_y0 = int((ymin / 1000.0) * h_px)
                                        px_x1 = int((xmax / 1000.0) * w_px)
                                        px_y1 = int((ymax / 1000.0) * h_px)
                                        
                                        # Calculate safety margin padding of 6%
                                        box_w = px_x1 - px_x0
                                        box_h = px_y1 - px_y0
                                        pad_x = int(box_w * 0.06)
                                        pad_y = int(box_h * 0.06)
                                        
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
                                            # Apply white background auto-trimmer post-processing
                                            cropped = post_process_image_background(cropped)
                                            cropped.save(file_path, "PNG")
                                            image_url = f"/storage/images/{file_name}"
                                        except Exception as crop_err:
                                            logger.debug(f"Pillow crop error: {crop_err}")
                                            
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
                                logger.error(f"Claude page parsing failed: {page_api_err}")
                                continue
                                
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
                        
                        # Validity String offline resolution
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
                                
                        # Parse pages with Tesseract coordinate translation
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
            
        # Self-healing hit-rate fallback check
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
        Uses a perfect uniform grid-snapping algorithm if column metadata is available.
        """
        from utils.image_manager import get_standard_image, find_reusable_image, post_process_image_background
        
        if product_name:
            # 1. Standard product catalog match
            std_url = get_standard_image(product_name)
            if std_url:
                return std_url
            
            # 2. Fuzzy semantic image reuse
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
            
            # Locate matching embedded native raster image in column vertical bounds
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
                # Tight, isolated crop centered exactly on the native visual package image
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
                # Fallback to perfect uniform column vertical card grid crop
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
            # Apply white background auto-trimmer post-processing
            cropped_img = post_process_image_background(cropped_img)
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

    def _parse_scanned_flyer_via_claude(self, file_path: str, store_id: str) -> List[ProductOffer]:
        """
        Executes scanned flyer OCR visual parsing using Anthropic's Claude API as a fallback.
        """
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
            "Ruolo: Sei un estrattore esperto di dati visivi e OCR per i volantini promozionali della GDO (Grande Distribuzione Organizzata) italiana.\n"
            "Task: Analizza attentamente l'immagine di questa pagina di volantino del supermercato ed estrai in modo accurato tutte le offerte commerciali.\n\n"
            "Fasi per ciascuna offerta (ragionamento step-by-step):\n"
            "1. Localizza visivamente una specifica scheda/sezione promozionale di prodotto.\n"
            "2. Leggi il prezzo (es. '1,49' -> convertilo in float 1.49) ed eventuali sconti (es. '-30%'). Se il prezzo ha euro e centesimi separati o rimpiccioliti, uniscili correttamente.\n"
            "3. Identifica il testo descrittivo del prodotto in italiano, isolando il nome (name), la marca (brand, es. 'Bio', 'Valis') e il formato/peso (weight_or_volume, es. '400 g', '1,5 L', 'confezione da 4 pezzi').\n"
            "4. Identifica i confini della FOTO del prodotto o del suo packaging. Lascia un comodo margine di sicurezza (un bordo o 'breathing room' extra di circa il 5-8%) attorno al prodotto per evitare che le estremità, i tappi o le etichette vengano tagliati.\n"
            "5. Calcola le coordinate normalizzate [ymin, xmin, ymax, xmax] da 0 a 1000 per l'immagine del prodotto.\n\n"
            "Regole di validazione:\n"
            "- Nome prodotto (name): Scrivilo in Title Case pulito (es. 'Biscotti frollini integrali'). Non includere pesi o marche qui.\n"
            "- Marca (brand): Estrai solo il brand reale (se indicato). Se assente, lascia null.\n"
            "- Categoria (category): Mappa il prodotto in un reparto italiano standard (es. 'Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Igiene Casa', 'Cura Persona').\n"
            "- Rettangolo (bbox): Deve inquadrare la foto dell'articolo promozionale lasciando un piccolo margine di sicurezza del 5-8% su tutti i lati nel sistema normalizzato 0-1000 (ymin alto, xmin sinistra, ymax basso, xmax destra)."
        )
        
        tool_schema = {
            "name": "extract_offers",
            "description": "Estrae l'elenco delle offerte commerciali dal volantino promozionale.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "offers": {
                        "type": "array",
                        "description": "Lista di tutte le offerte trovate nella pagina del volantino.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reasoning": {
                                    "type": "string",
                                    "description": "Ragionamento dettagliato step-by-step per identificare l'offerta e il suo box visivo."
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Nome del prodotto in Title Case, in italiano. Escludere peso e marca."
                                },
                                "brand": {
                                    "type": "string",
                                    "description": "Marca del prodotto (es. 'Mulino Bianco'). Lasciare null se non specificato."
                                },
                                "weight_or_volume": {
                                    "type": "string",
                                    "description": "Formato, peso o volume del prodotto (es. '500g', '1L', '6 pezzi'). Lasciare null se non specificato."
                                },
                                "price": {
                                    "type": "number",
                                    "description": "Prezzo decimale dell'offerta (es. 1.99 o 0.85)."
                                },
                                "original_price": {
                                    "type": "number",
                                    "description": "Prezzo barrato/originale se visibile, altrimenti null."
                                },
                                "discount_percentage": {
                                    "type": "integer",
                                    "description": "Percentuale di sconto (es. 30 o 50). Lasciare null se non indicata."
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Categoria merceologica in italiano (es. 'Alimentari', 'Surgelati', 'Bevande', 'Ortofrutta', 'Macelleria', 'Igiene Casa', 'Cura Persona')."
                                },
                                "bbox": {
                                    "type": "array",
                                    "description": "Rettangolo di delimitazione del prodotto [ymin, xmin, ymax, xmax] normalizzato da 0 a 1000.",
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
                    except Exception as render_err:
                        logger.error(f"Failed to render page {page_idx + 1} during fallback: {render_err}")
                        continue
                        
                    buffered = io.BytesIO()
                    pil_img.save(buffered, format="PNG")
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
                                    system="Sei un estrattore esperto di dati visivi per volantini promozionali della GDO italiana.",
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
                            
                            image_url = None
                            from utils.image_manager import get_standard_image, find_reusable_image, post_process_image_background
                            image_url = get_standard_image(name)
                            if not image_url:
                                image_url = find_reusable_image(self._supermarket_name, name)
                                
                            if not image_url and bbox and len(bbox) == 4:
                                ymin, xmin, ymax, xmax = bbox
                                w_px, h_px = pil_img.size
                                
                                px_x0 = int((xmin / 1000.0) * w_px)
                                px_y0 = int((ymin / 1000.0) * h_px)
                                px_x1 = int((xmax / 1000.0) * w_px)
                                px_y1 = int((ymax / 1000.0) * h_px)
                                
                                box_w = px_x1 - px_x0
                                box_h = px_y1 - px_y0
                                pad_x = int(box_w * 0.06)
                                pad_y = int(box_h * 0.06)
                                
                                crop_box = (
                                    max(0, px_x0 - pad_x),
                                    max(0, px_y0 - pad_y),
                                    min(w_px, px_x1 + pad_x),
                                    min(h_px, px_y1 + pad_y)
                                )
                                
                                os.makedirs("storage/images", exist_ok=True)
                                file_name = f"{self._supermarket_name}_{store_id}_{offer_id}.png"
                                img_path = os.path.join("storage/images", file_name)
                                
                                try:
                                    cropped = pil_img.crop(crop_box)
                                    cropped = post_process_image_background(cropped)
                                    cropped.save(img_path, "PNG")
                                    image_url = f"/storage/images/{file_name}"
                                except Exception as crop_err:
                                    logger.debug(f"Pillow crop error: {crop_err}")
                                    
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
