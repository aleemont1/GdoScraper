import logging
import math
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# Centralized Logging Configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
logger = logging.getLogger("ConadETLPipeline")


# ==========================================
# DOMAIN MODELS
# ==========================================


@dataclass
class BoundingBox:
    """Represents a 2D spatial boundary on a PDF page."""

    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


class WordElement:
    """Represents an extracted word token paired with its physical location."""

    def __init__(self, text: str, bbox: BoundingBox) -> None:
        self.text = text.strip()
        self.bbox = bbox
        self.is_visited = False


@dataclass
class ProductOffer:
    """Final structural model for a normalized supermarket offer."""

    name: str
    promo_price: float
    promo_type: str
    original_price: Optional[float] = None
    discount_percentage: Optional[int] = None
    unit_price: Optional[str] = None


# ==========================================
# GEOMETRIC EXTRACTION LAYER
# ==========================================


class SpatialClusterer:
    """Groups scattered WordElements into logical columns/blocks using distance."""

    def __init__(self, epsilon: float = 65.0) -> None:
        self.epsilon = epsilon

    def _compute_distance(self, word1: WordElement, word2: WordElement) -> float:
        dx = word1.bbox.center_x - word2.bbox.center_x
        dy = word1.bbox.center_y - word2.bbox.center_y
        return math.sqrt(dx * dx + dy * dy)

    def build_clusters(self, words: List[WordElement]) -> List[List[WordElement]]:
        clusters = []
        for word in words:
            if word.is_visited:
                continue

            word.is_visited = True
            neighbors = [
                w
                for w in words
                if w != word and self._compute_distance(word, w) <= self.epsilon
            ]

            current_cluster = [word]
            clusters.append(current_cluster)

            queue = list(neighbors)
            for neighbor in queue:
                if not neighbor.is_visited:
                    neighbor.is_visited = True
                    next_neighbors = [
                        w
                        for w in words
                        if w != neighbor
                        and self._compute_distance(neighbor, w) <= self.epsilon
                    ]
                    queue.extend(next_neighbors)

                if not any(neighbor in c for c in clusters):
                    current_cluster.append(neighbor)

        return clusters


class ProductBlockParser:
    """Orders a spatial cluster top-to-bottom, left-to-right."""

    @staticmethod
    def parse_to_string(cluster: List[WordElement]) -> str:
        sorted_cluster = sorted(
            cluster, key=lambda w: (round(w.bbox.top / 5) * 5, w.bbox.x0)
        )
        return " ".join([w.text for w in sorted_cluster])


class PdfWordExtractor:
    """Handles PDF binary ingestion and vector word tokenization."""

    def get_total_pages(self, file_path: str) -> int:
        """Returns the total number of pages in the PDF document."""
        if not pdfplumber:
            return 0
        try:
            with pdfplumber.open(file_path) as pdf:
                return len(pdf.pages)
        except Exception as e:
            logger.error(f"Failed to read PDF total pages: {e}")
            return 0

    def extract_page_words(self, file_path: str, page_index: int) -> List[WordElement]:
        """Extracts words and bounding boxes for a specific page."""
        if not pdfplumber:
            return []

        word_elements = []
        try:
            with pdfplumber.open(file_path) as pdf:
                if page_index >= len(pdf.pages):
                    return []

                page = pdf.pages[page_index]
                for raw in page.extract_words():
                    bbox = BoundingBox(
                        x0=float(raw["x0"]),
                        top=float(raw["top"]),
                        x1=float(raw["x1"]),
                        bottom=float(raw["bottom"]),
                    )
                    word_elements.append(WordElement(text=raw["text"], bbox=bbox))
        except Exception as e:
            logger.error(f"Critical error during vector extraction: {e}")

        return word_elements


# ==========================================
# SEMANTIC PARSING STRATEGIES (OCP & SRP)
# ==========================================


class AbstractPromoExtractor(ABC):
    """Abstract base class for all promotional extraction strategies."""

    @abstractmethod
    def extract(self, text_block: str) -> List[ProductOffer]:
        pass


class OnePlusOneExtractor(AbstractPromoExtractor):
    """Strategy for handling '1+1' promotions."""

    def __init__(self) -> None:
        self.pattern = re.compile(
            r"(?P<name>.*?)\s+1 pezzo €\s*(?P<single_price>\d+,\d{2})\s+2 PEZZI\s*(?P<promo_euro>\d+)\s*€\s*,(?P<promo_cents>\d{2})(?:\s*€/(?:kg|l|lt|pz)\s*(?P<unit_price>\d+,\d{2}))?",
            re.IGNORECASE | re.DOTALL,
        )

    def extract(self, text_block: str) -> List[ProductOffer]:
        offers = []
        for match in self.pattern.finditer(text_block):
            promo_price = float(
                f"{match.group('promo_euro')}.{match.group('promo_cents')}"
            )
            single_price = float(match.group("single_price").replace(",", "."))
            unit_val = match.group("unit_price")

            offers.append(
                ProductOffer(
                    name=match.group("name").strip(),
                    promo_price=promo_price,
                    promo_type="1+1",
                    original_price=single_price,
                    unit_price=f"€ {unit_val}" if unit_val else None,
                )
            )
        return offers


class PercentageDiscountExtractor(AbstractPromoExtractor):
    """Strategy for handling standard percentage discounts."""

    def __init__(self) -> None:
        self.pattern = re.compile(
            r"(?P<name>.*?)\s+€\s*(?P<old_price>\d+,\d{2})\s*-(?P<discount>\d+)\s*%\s*(?P<promo_euro>\d+)\s*€\s*,(?P<promo_cents>\d{2})(?:\s*€/(?:kg|l|lt|pz)\s*(?P<unit_price>\d+,\d{2}))?",
            re.IGNORECASE | re.DOTALL,
        )

    def extract(self, text_block: str) -> List[ProductOffer]:
        offers = []
        for match in self.pattern.finditer(text_block):
            promo_price = float(
                f"{match.group('promo_euro')}.{match.group('promo_cents')}"
            )
            old_price = float(match.group("old_price").replace(",", "."))
            unit_val = match.group("unit_price")

            offers.append(
                ProductOffer(
                    name=match.group("name").strip(),
                    promo_price=promo_price,
                    promo_type="PERCENTAGE_DISCOUNT",
                    original_price=old_price,
                    discount_percentage=int(match.group("discount")),
                    unit_price=f"€ {unit_val}" if unit_val else None,
                )
            )
        return offers


class FreshWeightExtractor(AbstractPromoExtractor):
    """Strategy for handling fresh counter items priced by weight."""

    def __init__(self) -> None:
        self.pattern = re.compile(
            r"(?P<name>.*?)\s+(?P<promo_euro>\d+)\s*€\s*,(?P<promo_cents>\d{2})\s*al kg",
            re.IGNORECASE | re.DOTALL,
        )

    def extract(self, text_block: str) -> List[ProductOffer]:
        offers = []
        for match in self.pattern.finditer(text_block):
            promo_price = float(
                f"{match.group('promo_euro')}.{match.group('promo_cents')}"
            )

            offers.append(
                ProductOffer(
                    name=match.group("name").strip(),
                    promo_price=promo_price,
                    promo_type="FRESH_WEIGHT",
                    unit_price="€/kg",
                )
            )
        return offers


class MasterRegexOrchestrator:
    """Routes text blocks through various extraction strategies."""

    def __init__(self) -> None:
        self.strategies: List[AbstractPromoExtractor] = [
            OnePlusOneExtractor(),
            PercentageDiscountExtractor(),
            FreshWeightExtractor(),
        ]

    def process_text_block(self, text: str) -> List[ProductOffer]:
        all_extracted_offers = []
        clean_text = text.replace("\n", " ")

        for strategy in self.strategies:
            offers = strategy.extract(clean_text)
            if offers:
                all_extracted_offers.extend(offers)

        return all_extracted_offers


# ==========================================
# EXECUTION ORCHESTRATION
# ==========================================

if __name__ == "__main__":
    TARGET_PDF_PATH = "downloads/conad/v-56578793_20260523.pdf"

    extractor = PdfWordExtractor()
    clusterer = SpatialClusterer(
        epsilon=65.0
    )  # Epsilon bumped slightly to test large grids
    orchestrator = MasterRegexOrchestrator()

    if os.path.exists(TARGET_PDF_PATH):
        logger.info("Starting Full-Document ETL Pipeline...")

        # Determine total pages dynamically
        total_pages = extractor.get_total_pages(TARGET_PDF_PATH)
        logger.info(
            f"Detected {total_pages} pages in the document. Beginning full traversal."
        )

        final_database_entries = []

        for page_index in range(total_pages):
            logger.info(f"--- Processing Page {page_index + 1} of {total_pages} ---")
            extracted_words = extractor.extract_page_words(TARGET_PDF_PATH, page_index)

            if extracted_words:
                grouped_clusters = clusterer.build_clusters(extracted_words)

                for cluster in grouped_clusters:
                    if len(cluster) < 3:
                        continue

                    column_text = ProductBlockParser.parse_to_string(cluster)
                    products_in_column = orchestrator.process_text_block(column_text)
                    final_database_entries.extend(products_in_column)

        # Output Results
        print("\n" + "=" * 70)
        print(" FULL DOCUMENT DATA EXTRACTION RESULTS")
        print("=" * 70)
        for idx, prod in enumerate(final_database_entries, start=1):
            print(f"{idx}. [{prod.promo_type}] {prod.name}")

            if prod.promo_type == "PERCENTAGE_DISCOUNT":
                print(
                    f"   Price: €{prod.promo_price:.2f} (Was: €{prod.original_price:.2f} | Discount: -{prod.discount_percentage}%)"
                )
            elif prod.promo_type == "1+1":
                print(
                    f"   Price: 2 for €{prod.promo_price:.2f} (Single: €{prod.original_price:.2f})"
                )
            else:
                print(f"   Price: €{prod.promo_price:.2f} {prod.unit_price or ''}")

            print("-" * 50)

        print(f"\nTOTAL PRODUCTS EXTRACTED: {len(final_database_entries)}")
    else:
        logger.error(f"Target file not found at {TARGET_PDF_PATH}.")
