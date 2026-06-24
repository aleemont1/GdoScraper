import os
from typing import List, Any

from core.base_pdf_driver import AbstractPdfFlyerDriver
from core.models import ProductOffer
from utils.logger import setup_logger

logger = setup_logger("ManualDriver")


class ManualSupermarketDriver(AbstractPdfFlyerDriver):
    """
    Concrete scraper driver strategy for manually uploaded PDF circular flyers.
    Dynamically routes between vector character analysis (Conad-style) and visual OCR
    (IN's-style) depending on the PDF's text properties.
    """

    def __init__(
        self,
        supermarket_name: str = "MANUAL",
        store_id: str = "MANUAL_STORE",
        parallel: bool = False,
        engine: str = "AUTO",
    ) -> None:
        self._engine = engine.upper().strip()
        use_gemini = self._engine == "GEMINI"
        use_claude = self._engine == "CLAUDE"
        super().__init__(
            parallel=parallel,
            use_gemini=use_gemini,
            use_claude=use_claude,
            engine=self._engine,
        )
        self._custom_supermarket_name = supermarket_name.upper().strip()
        self._resolved_store_id = store_id.strip()

        # Instantiate both Conad and IN's strategy engines for dynamic dispatching
        from core.base_pdf_segmenter import BasePdfLayoutSegmenter
        from drivers.conad.offer_parser import ConadOfferParser
        from drivers.ins.ins_offer_parser import InsOfferParser

        self._conad_segmenter = BasePdfLayoutSegmenter(gutter_min_width=6)
        self._conad_parser = ConadOfferParser()
        self._ins_segmenter = BasePdfLayoutSegmenter()
        self._ins_parser = InsOfferParser()

        self._current_is_vector = False

    @property
    def _supermarket_name(self) -> str:
        return self._custom_supermarket_name

    @property
    def _download_subdir(self) -> str:
        return "downloads/uploaded"

    @property
    def _segmenter(self) -> Any:
        if getattr(self, "_current_is_vector", False):
            return self._conad_segmenter
        return self._ins_segmenter

    @property
    def _parser(self) -> Any:
        if getattr(self, "_current_is_vector", False):
            return self._conad_parser
        return self._ins_parser

    def _parse_single_flyer_file(
        self, file_path: str, store_id: str
    ) -> List[ProductOffer]:
        """
        Pre-detects if the PDF has vector characters and configures the parsing strategy.
        If the user explicitly selected Gemini or Tesseract OCR, we completely bypass vector grid parsing.
        If the vector parsing strategy yields low yields (< 3 offers total OR < 0.6 offers per page)
        due to layout incompatibilities on custom vector circulars, it automatically
        falls back to the robust OCR scanned strategy.
        """
        self._current_is_vector = False
        total_pages = 1

        # Skip vector detection and grid layout parsing if the user explicitly selected a non-AUTO engine
        if self._engine == "AUTO":
            try:
                import pdfplumber

                with pdfplumber.open(file_path) as pdf:
                    total_pages = len(pdf.pages)
                    self._current_is_vector = any(
                        len(p.extract_words()) > 0 for p in pdf.pages
                    )
            except Exception as e:
                logger.error(f"Error pre-detecting PDF vector status: {e}")

        if self._current_is_vector:
            logger.info(
                f"Manual flyer vector detection for '{os.path.basename(file_path)}': "
                f"is_vector=True (trying CONAD-style vector parser, flyer has {total_pages} pages)"
            )
            # Try high-accuracy grid vector parsing first
            offers = super()._parse_single_flyer_file(file_path, store_id)

            # Check yield metrics to verify layout compatibility
            yield_per_page = len(offers) / max(1, total_pages)
            logger.info(
                f"Vector parser completed. Extracted {len(offers)} offers. "
                f"Average yield: {yield_per_page:.2f} offers per page."
            )

            # If the vector segmenter successfully extracted a healthy ratio of promotions, return them
            if len(offers) >= 3 and yield_per_page >= 0.6:
                return offers

            # Otherwise, fall back to robust visual scanned OCR parsing (Tesseract or Gemini)
            logger.warning(
                f"Vector-based parser returned only {len(offers)} offers for {total_pages} pages "
                f"(yield: {yield_per_page:.2f} offers/page). Layout structure is likely incompatible. "
                f"Self-healing: falling back to scanned OCR visual pipeline..."
            )
            self._current_is_vector = False

        logger.info(
            f"Engaging scanned flyer OCR pipeline for manual PDF circular: "
            f"engine={self._engine} (use_gemini={self.use_gemini})"
        )
        return super()._parse_single_flyer_file(file_path, store_id)

    def download_flyers(self, store_id: str) -> List[str]:
        """
        No-op dynamic download hook, since manual flyer files are already saved in downloads/uploaded/
        prior to parsing.
        """
        # If the store_id represents a direct file path, return it
        if store_id.endswith(".pdf") and os.path.exists(store_id):
            return [store_id]

        # Look in our downloads directory
        file_path = os.path.join(self._download_subdir, store_id)
        if os.path.exists(file_path):
            return [file_path]

        # Try generic files matching in downloads/uploaded
        search_pattern = os.path.join(self._download_subdir, f"*{store_id}*.pdf")
        import glob

        matches = glob.glob(search_pattern)
        if matches:
            return matches

        logger.error(f"Manual flyer PDF file not found matching search: '{store_id}'")
        return []
