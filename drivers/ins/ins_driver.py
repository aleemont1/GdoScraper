import os
import re
import time
import hashlib
import requests
import shutil
import pdfplumber
from bs4 import BeautifulSoup
from typing import List, Any, Optional, Dict
from pydantic import BaseModel, Field

from core.base_pdf_driver import AbstractPdfFlyerDriver
from core.models import ProductOffer
from drivers.ins.ins_layout_segmenter import InsLayoutSegmenter
from drivers.ins.ins_offer_parser import InsOfferParser
from utils.logger import setup_logger

logger = setup_logger("INSDriver")


class ExtractedOffer(BaseModel):
    name: str = Field(description="Nome del prodotto ed eventuale descrizione breve (es. 'Biscotti Frollini')")
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

    def to_image(self, resolution: int = 120) -> Any:
        return self._page.to_image(resolution=resolution)


class INSSupermarketDriver(AbstractPdfFlyerDriver):
    """
    Concrete scraper driver strategy for IN's Mercato.
    Supports geocoding POS coords, BeautifulSoup web crawling for the PDF flyer,
    and a dual-engine OCR pipeline (Offline Tesseract by default or Gemini Free Tier explicitly).
    """

    def __init__(
        self,
        max_flyers: Optional[int] = None,
        parallel: bool = False,
        use_gemini: bool = False
    ) -> None:
        super().__init__(parallel=parallel)
        self._ins_segmenter = InsLayoutSegmenter()
        self._ins_parser = InsOfferParser()
        self.max_flyers = max_flyers
        self.use_gemini = use_gemini

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
        
        # Determine current edition path
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
            # Let's clean the city name (e.g. remove "provincia", spaces etc)
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

    def _parse_single_flyer_file(self, file_path: str, store_id: str) -> List[ProductOffer]:
        if not os.path.exists(file_path):
            return []

        logger.info(f"Beginning IN's flyer parsing: {os.path.basename(file_path)}")
        parsed_offers: List[ProductOffer] = []

        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Flyer has {total_pages} pages.")

                # A. Engine B: Gemini API Structured Multimodal visual OCR
                if self.use_gemini:
                    logger.info("Using Gemini 2.5 Flash visual parsing API...")
                    from google import genai
                    from google.genai import types
                    from PIL import Image
                    import json

                    # Check for Gemini key in environment
                    if not os.environ.get("GEMINI_API_KEY"):
                        raise ValueError(
                            "GEMINI_API_KEY environment variable is missing. "
                            "Please configure your API key or run without the '--use-gemini' flag."
                        )

                    client = genai.Client()

                    prompt = (
                        "Sei un assistente visivo di estrema precisione. Analizza questa pagina di volantino promozionale ed estrai "
                        "tutte le offerte commerciali di prodotti presenti. Per ciascun prodotto, estrai tutti i dati "
                        "strutturati richiesti dallo schema JSON. In particolare, identifica la bounding box visuale [ymin, xmin, ymax, xmax] "
                        "del SOLO prodotto fisico/confezione/foto (escludendo testi descrittivi, prezzi ed elementi grafici di sfondo degli "
                        "altri prodotti per evitare ritagli sporchi o sovrapposizioni). Il rettangolo deve inquadrare in modo "
                        "estremamente millimetrico e centrato la foto del prodotto associato all'offerta. "
                        "Le coordinate della bounding box devono essere normalizzate da 0 a 1000, dove ymin corrisponde al "
                        "bordo superiore (0 in alto, 1000 in basso) e xmin al bordo sinistro (0 a sinistra, 1000 a destra)."
                    )

                    # Iterate pages
                    for page_idx in range(total_pages):
                        page = pdf.pages[page_idx]
                        logger.info(f"Processing Page {page_idx + 1}/{total_pages} via Gemini...")

                        try:
                            pil_img = page.to_image(resolution=120).original
                        except Exception as render_err:
                            logger.error(f"Failed to render page {page_idx + 1}: {render_err}")
                            continue

                        # Save a temporary file
                        temp_dir = "downloads/ins_temp"
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_img_path = os.path.join(temp_dir, f"page_{page_idx}.png")
                        pil_img.save(temp_img_path)

                        try:
                            # Send request to Gemini API
                            response = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=[pil_img, prompt],
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    response_schema=ExtractedOffersList,
                                    temperature=0.1
                                ),
                            )

                            if os.path.exists(temp_img_path):
                                os.remove(temp_img_path)

                            # Parse JSON output
                            data = json.loads(response.text)
                            offers = data.get("offers", [])
                            logger.info(f"Page {page_idx + 1}: Extracted {len(offers)} offers from Gemini.")

                            # Process promotions
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

                                # Make ID
                                payload_str = f"INS:{store_id}:ALL:{name}:{price:.2f}"
                                offer_id = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()[:32]

                                image_url = None
                                if bbox and len(bbox) == 4:
                                    ymin, xmin, ymax, xmax = bbox
                                    w_px, h_px = pil_img.size

                                    px_x0 = int((xmin / 1000.0) * w_px)
                                    px_y0 = int((ymin / 1000.0) * h_px)
                                    px_x1 = int((xmax / 1000.0) * w_px)
                                    px_y1 = int((ymax / 1000.0) * h_px)

                                    crop_box = (
                                        max(0, px_x0),
                                        max(0, px_y0),
                                        min(w_px, px_x1),
                                        min(h_px, px_y1)
                                    )

                                    os.makedirs("storage/images", exist_ok=True)
                                    file_name = f"INS_{store_id}_{offer_id}.png"
                                    file_path = os.path.join("storage/images", file_name)
                                    
                                    try:
                                        cropped = pil_img.crop(crop_box)
                                        cropped.save(file_path, "PNG")
                                        image_url = f"/storage/images/{file_name}"
                                    except Exception as crop_err:
                                        logger.debug(f"Pillow crop error: {crop_err}")

                                offer = ProductOffer(
                                    offer_id=offer_id,
                                    supermarket="INS",
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
                            if os.path.exists(temp_img_path):
                                os.remove(temp_img_path)
                            continue

                # B. Engine A: Local Offline Pytesseract OCR (Default)
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

                    # 1. Extract Validity String from Page 1
                    validity_string = None
                    if total_pages > 0:
                        first_page = pdf.pages[0]
                        try:
                            pil_img = first_page.to_image(resolution=120).original
                            ocr_data = pytesseract.image_to_data(pil_img, lang="ita", output_type=pytesseract.Output.DICT)
                            
                            # Join tokens to parse dates
                            tokens = []
                            for text_val in ocr_data["text"]:
                                if text_val and text_val.strip():
                                    tokens.append(text_val)
                            first_page_text = " ".join(tokens)
                            validity_string = self._parser.parse_flyer_validity(first_page_text)
                            if validity_string:
                                logger.info(f"Flyer validity resolved offline: '{validity_string}'")
                        except Exception as e:
                            logger.debug(f"Offline validity date extraction error: {e}")

                    # 2. Iterate pages and run the Column-First segmenter
                    for page_idx in range(total_pages):
                        page = pdf.pages[page_idx]
                        logger.info(f"Segmenting Page {page_idx + 1}/{total_pages} offline...")

                        try:
                            # Render high-res image
                            pil_img = page.to_image(resolution=120).original
                            w_px, h_px = pil_img.size
                            page_w = float(page.width)
                            page_h = float(page.height)

                            scale_x = page_w / w_px
                            scale_y = page_h / h_px

                            # Local Tesseract OCR
                            ocr_data = pytesseract.image_to_data(pil_img, lang="ita", output_type=pytesseract.Output.DICT)

                            # Scale Tesseract pixel bounding boxes into pdfplumber points
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

                            # Create adapter page wrapper
                            ocr_page = OcrPageWrapper(page, ocr_words)

                            # Execute standard segmenter and cell pairing completely offline!
                            cells = self._segmenter.segment_page(ocr_page)

                            # Parse semantic product cells
                            for cell in cells:
                                try:
                                    offer = self._parser.parse_cell(cell["text"], store_id, validity_string)
                                    if offer:
                                        # Crop card from the pre-rendered page image
                                        offer.image_url = self._crop_and_save_card_image_from_cached(
                                            pil_img,
                                            cell["bbox"],
                                            ocr_page,
                                            store_id,
                                            offer.offer_id,
                                            col_idx=cell.get("col_idx"),
                                            col_count=cell.get("col_count")
                                        )
                                        parsed_offers.append(offer)
                                except ValueError as parse_err:
                                    logger.debug(f"Cell skipped: {parse_err}")
                                except Exception as parse_err:
                                    logger.debug(f"Cell exception: {parse_err}")

                        except Exception as page_err:
                            logger.error(f"Error processing page {page_idx + 1} offline: {page_err}")
                            continue

        except Exception as e:
            logger.error(f"Critical failure during IN's flyer scraping: {e}")
            raise e

        logger.info(f"Finished parsing IN's flyer. Extracted a total of {len(parsed_offers)} promotions.")
        return parsed_offers
