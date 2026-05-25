from core.base_pdf_driver import AbstractPdfFlyerDriver
from drivers.conad.layout_segmenter import ConadLayoutSegmenter
from drivers.conad.offer_parser import ConadOfferParser

class ConadSupermarketDriver(AbstractPdfFlyerDriver):
    """
    Concrete scraper driver strategy for Conad.
    Connects the high-level AbstractPdfFlyerDriver engine with Conad-specific
    semantic block text parsing and gutter layout segmentation.
    """

    def __init__(self) -> None:
        self._conad_segmenter = ConadLayoutSegmenter()
        self._conad_parser = ConadOfferParser()

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
