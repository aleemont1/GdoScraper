import re
from typing import Dict, Any, List, Tuple
from utils.logger import setup_logger

logger = setup_logger("BasePdfLayoutSegmenter")


class BasePdfLayoutSegmenter:
    """
    Generalized PDF layout segmenter that decomposes catalog flyer pages into discrete
    product cells using Column-First Grid Alignment and Low-Gutter Block Pairing.

    This solver is completely supermarket-agnostic and can be configured or subclassed
    by different scraper drivers.
    """

    def __init__(
        self,
        gutter_min_height: int = 4,
        gutter_min_width: int = 12,
        price_indicators: List[str] = None,
    ) -> None:
        self.gutter_min_height = gutter_min_height
        self.gutter_min_width = gutter_min_width
        self.price_indicators = price_indicators or [
            "€",
            "pezzo",
            "pezzi",
            "anziché",
            "anzichè",
        ]
        self._price_decimal = re.compile(r"\b\d+\s*,\s*\d{2}\b")

    def _is_price_block(self, text: str) -> bool:
        """
        Classifies whether a vertical text block contains price keywords or values.
        """
        return any(kw in text.lower() for kw in self.price_indicators) or bool(
            self._price_decimal.search(text)
        )

    def segment_page(self, page: Any) -> List[Dict[str, Any]]:
        """
        Decomposes a page into cell dictionaries with uniform grid column metadata
        to support perfect visual card/raster cropping.

        Returns:
            A list of cells, each containing:
              - 'bbox': (col_x0, cell_y0, col_x1, cell_y1) coordinates in PDF points.
              - 'text': Sorted, space-joined text block content.
              - 'col_idx': Vertical column index (0-based) on the page.
              - 'col_count': Total columns detected on this page.
        """
        width = float(page.width)
        height = float(page.height)

        words = page.extract_words()
        if not words:
            return []

        logger.debug(
            f"Segmenting page of size {width:.1f} x {height:.1f} with {len(words)} words."
        )

        # 1. Project middle vertical region words onto X-axis to find vertical column boundaries
        # Excludes standard page headers (top 100pt) and footers (bottom 80pt)
        middle_words = [
            w for w in words if 100 <= (w["top"] + w["bottom"]) / 2.0 <= height - 80
        ]
        if not middle_words:
            middle_words = words

        x_bins = [0] * int(width + 2)
        for w in middle_words:
            x0 = max(0, int(w["x0"]))
            x1 = min(int(width), int(w["x1"]))
            for x in range(x0, x1 + 1):
                x_bins[x] += 1

        in_col = False
        col_ranges: List[Tuple[int, int]] = []
        col_start = 0
        consecutive_empty = 0

        for x in range(int(width)):
            is_empty = x_bins[x] == 0
            if not in_col:
                if not is_empty:
                    in_col = True
                    col_start = x
            else:
                if is_empty:
                    consecutive_empty += 1
                    if consecutive_empty >= self.gutter_min_width:
                        col_end = x - consecutive_empty
                        if col_end - col_start > 30:  # Ignore spurious narrow blocks
                            col_ranges.append((col_start, col_end))
                        in_col = False
                        consecutive_empty = 0
                else:
                    consecutive_empty = 0

        if in_col:
            col_ranges.append((col_start, int(width)))

        # Fallback to single page-wide column
        if not col_ranges:
            col_ranges = [(0, int(width))]

        C = len(col_ranges)
        logger.debug(f"Detected columns count: C={C} | Ranges: {col_ranges}")

        cells: List[Dict[str, Any]] = []

        # 2. Segment each column independently
        for col_idx, (col_x0, col_x1) in enumerate(col_ranges):
            # Isolate words belonging to this column (using a 20pt coordinate buffer)
            col_words = []
            for w in words:
                cx = (w["x0"] + w["x1"]) / 2.0
                if col_x0 - 20 <= cx <= col_x1 + 20:
                    col_words.append(w)

            if not col_words:
                continue

            # Project column words onto Y-axis to locate vertical gutters inside the column
            y_bins = [0] * int(height + 2)
            for w in col_words:
                top = max(0, int(w["top"]))
                bottom = min(int(height), int(w["bottom"]))
                for y in range(top, bottom + 1):
                    y_bins[y] += 1

            # Find small text blocks
            in_block = False
            block_start = 0
            con_empty = 0

            blocks: List[Tuple[int, int]] = []
            for y in range(int(height)):
                is_empty = y_bins[y] == 0
                if not in_block:
                    if not is_empty:
                        in_block = True
                        block_start = y
                else:
                    if is_empty:
                        con_empty += 1
                        if con_empty >= self.gutter_min_height:
                            block_end = y - con_empty
                            if block_end - block_start > 5:
                                blocks.append((block_start, block_end))
                            in_block = False
                            con_empty = 0
                    else:
                        con_empty = 0

            if in_block:
                blocks.append((block_start, int(height)))

            # 3. Classify blocks and alternate-pair descriptions and prices
            pending_desc: Dict[str, Any] = None

            for b_y0, b_y1 in blocks:
                b_words = [
                    w
                    for w in col_words
                    if b_y0 <= (w["top"] + w["bottom"]) / 2.0 <= b_y1
                ]
                if not b_words:
                    continue

                sorted_words = sorted(
                    b_words, key=lambda w: (round(w["top"] / 3) * 3, w["x0"])
                )
                b_text = " ".join([w["text"] for w in sorted_words]).strip()
                if len(b_text) < 4:
                    continue

                is_price = self._is_price_block(b_text)

                if is_price:
                    if pending_desc:
                        card_bbox = (col_x0, pending_desc["y0"], col_x1, b_y1)
                        card_text = f"{pending_desc['text']} {b_text}"
                        cells.append(
                            {
                                "bbox": card_bbox,
                                "text": card_text,
                                "col_idx": col_idx,
                                "col_count": C,
                            }
                        )
                        pending_desc = None
                    else:
                        # Self-contained card containing both description and price
                        cells.append(
                            {
                                "bbox": (col_x0, b_y0, col_x1, b_y1),
                                "text": b_text,
                                "col_idx": col_idx,
                                "col_count": C,
                            }
                        )
                else:
                    if pending_desc:
                        pending_desc["text"] = f"{pending_desc['text']} {b_text}"
                        pending_desc["y1"] = b_y1
                    else:
                        pending_desc = {"y0": b_y0, "y1": b_y1, "text": b_text}

            if pending_desc:
                cells.append(
                    {
                        "bbox": (
                            col_x0,
                            pending_desc["y0"],
                            col_x1,
                            pending_desc["y1"],
                        ),
                        "text": pending_desc["text"],
                        "col_idx": col_idx,
                        "col_count": C,
                    }
                )

        return cells
