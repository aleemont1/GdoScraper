import re
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ProductOffer:
    """
    Domain model representing a normalized product offer.
    Follows the Single Responsibility Principle by only holding data state.
    """

    offer_id: str
    name: str
    brand: Optional[str]
    weight_or_volume: Optional[str]
    price: Optional[float]
    price_per_unit: Optional[str]
    ean_code: Optional[str]
    image_url: Optional[str]
    category_code: Optional[str]


class CoopPromoParser:
    """
    Responsible for parsing the Server-Driven UI JSON payload from Coop
    into normalized ProductOffer objects.
    """

    def __init__(self) -> None:
        # Regex to extract numeric price values from strings like "1,29 \u20ac"
        self._price_regex = re.compile(r"(\d+,\d{2})\s*€")

    def parse_promo_list(self, json_payload: Dict[str, Any]) -> List[ProductOffer]:
        """
        Parses the entire API response into a list of normalized models.
        """
        parsed_offers = []
        promos_array = json_payload.get("promos", [])

        for raw_promo in promos_array:
            try:
                offer = self._parse_single_promo(raw_promo)
                parsed_offers.append(offer)
            except Exception as e:
                logger.warning(f"Failed to parse a promo item. Error: {e}")

        return parsed_offers

    def _parse_single_promo(self, raw_promo: Dict[str, Any]) -> ProductOffer:
        """
        Extracts data from a single promotional item dictionary.
        """
        offer_id = raw_promo.get("id", "UNKNOWN")
        name = raw_promo.get("desc_promo", "UNKNOWN NAME")
        brand = raw_promo.get("brand")
        weight = raw_promo.get("desc_promo2")
        category_code = raw_promo.get("categoryCode")
        image_url = raw_promo.get("img")

        # Extract the EAN barcode if available
        ean_code = None
        products_array = raw_promo.get("prodotti", [])
        if products_array and len(products_array) > 0:
            ean_code = products_array[0]

        # Parse price and unit price using the layout extraction strategy
        price, price_per_unit = self._extract_price_from_layout(raw_promo)

        return ProductOffer(
            offer_id=offer_id,
            name=name,
            brand=brand,
            weight_or_volume=weight,
            price=price,
            price_per_unit=price_per_unit,
            ean_code=ean_code,
            image_url=image_url,
            category_code=category_code,
        )

    def _extract_price_from_layout(
        self, raw_promo: Dict[str, Any]
    ) -> tuple[Optional[float], Optional[str]]:
        """
        Iterates over the Server-Driven UI layout nodes to find the price and unit price.
        Returns a tuple of (parsed_float_price, unit_price_string).
        """
        layout_keys = ["CXTop", "CXBottom", "SXTop", "SXBottom", "DXTop", "DXBottom"]

        raw_price_str = None
        unit_price_str = None

        for key in layout_keys:
            node = raw_promo.get(key)
            if not node:
                continue

            text_lines = node.get("txt", [])
            for line in text_lines:
                if not line:
                    continue

                # Standardize Euro symbol representations
                line_clean = line.replace("\u20ac", "€")

                # Check for unit price (e.g., "5,16 € al kg")
                if "al kg" in line_clean or "al lt" in line_clean:
                    unit_price_str = line_clean.strip()
                    continue

                # Search for the main price using Regex
                match = self._price_regex.search(line_clean)
                if match:
                    raw_price_str = match.group(1)

        # Convert the Italian comma format "1,29" to a float 1.29
        final_price = None
        if raw_price_str:
            try:
                final_price = float(raw_price_str.replace(",", "."))
            except ValueError:
                logger.debug(
                    f"Could not convert price string to float: {raw_price_str}"
                )

        return final_price, unit_price_str


# Execution entry point for testing the parser
if __name__ == "__main__":
    sample_json = {
        "promos": [
            {
                "id": "223124f82bbb3189a5ca96b552de5635",
                "desc_promo2": "250 g",
                "desc_promo": "TAGLIOLINA LIMONE DI BARI",
                "DXTop": {"txt": [None, "1,29 \u20ac", "5,16 \u20ac al kg"]},
                "categoryCode": "1",
                "prodotti": ["8003007826323"],
                "img": "https://svdgt.coopalleanza3-0.it/imgp/products/26eaf0488f052fc6eb54a4201f8ad84e/8003007826323.jpg",
                "brand": "DI BARI",
            }
        ]
    }

    parser = CoopPromoParser()
    parsed_models = parser.parse_promo_list(sample_json)

    for model in parsed_models:
        print(model)
