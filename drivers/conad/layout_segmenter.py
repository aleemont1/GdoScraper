from core.base_pdf_segmenter import BasePdfLayoutSegmenter

class ConadLayoutSegmenter(BasePdfLayoutSegmenter):
    """
    Concrete layout segmenter for Conad, inheriting the generalized Column-First Grid Solver.
    """

    def __init__(self, gutter_min_height: int = 4, gutter_min_width: int = 12) -> None:
        super().__init__(
            gutter_min_height=gutter_min_height,
            gutter_min_width=gutter_min_width,
            price_indicators=["€", "pezzo", "pezzi", "anziché", "anzichè"]
        )
