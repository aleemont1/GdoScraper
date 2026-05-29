import os
from typing import List, Any, Optional

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
        parallel: bool = False,
        use_gemini: bool = False
    ) -> None:
        super().__init__(parallel=parallel, use_gemini=use_gemini)
        self._custom_supermarket_name = supermarket_name.upper().strip()
        
        # Instantiate both Conad and IN's strategy engines for dynamic dispatching
        from drivers.conad.layout_segmenter import ConadLayoutSegmenter
        from drivers.conad.offer_parser import ConadOfferParser
        from drivers.ins.ins_layout_segmenter import InsLayoutSegmenter
        from drivers.ins.ins_offer_parser import InsOfferParser
        
        self._conad_segmenter = ConadLayoutSegmenter()
        self._conad_parser = ConadOfferParser()
        self._ins_segmenter = InsLayoutSegmenter()
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

    def _parse_single_flyer_file(self, file_path: str, store_id: str) -> List[ProductOffer]:
        """
        Pre-detects if the PDF has vector characters and configures the parsing strategy.
        """
        self._current_is_vector = False
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                self._current_is_vector = any(len(p.extract_words()) > 0 for p in pdf.pages)
        except Exception as e:
            logger.error(f"Error pre-detecting PDF vector status: {e}")
            
        logger.info(
            f"Manual flyer vector detection for '{os.path.basename(file_path)}': "
            f"is_vector={self._current_is_vector} (dispatching "
            f"{'CONAD-style vector' if self._current_is_vector else 'INS-style scanned'} parser)"
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

