from pydantic import BaseModel, Field
from typing import Optional


class ProductOffer(BaseModel):
    """
    Unified domain model representing a normalized product offer across
    different supermarket chains (e.g., Coop, Conad).
    """

    offer_id: str = Field(..., description="Unique promo identifier from the source")
    supermarket: str = Field(
        ..., description="Supermarket name (e.g., 'COOP', 'CONAD')"
    )
    store_id: str = Field(
        ..., description="Store identifier where this promo is active"
    )
    name: str = Field(..., description="Name/description of the product")
    brand: Optional[str] = Field(None, description="Product brand name")
    weight_or_volume: Optional[str] = Field(
        None, description="E.g., '250 g', '1.5 Litri'"
    )
    price: float = Field(..., description="Active promotional price")
    original_price: Optional[float] = Field(
        None, description="Pre-discount price, if available"
    )
    discount_percentage: Optional[int] = Field(
        None, description="Discount percent value (e.g., 20)"
    )
    price_per_unit: Optional[str] = Field(
        None, description="Normalized unit price (e.g., '€ 5.16 al kg')"
    )
    ean_code: Optional[str] = Field(
        None, description="EAN barcode, vital for cross-referencing"
    )
    image_url: Optional[str] = Field(None, description="Direct link to product image")
    category: Optional[str] = Field(None, description="Category code or name")
    promo_type: str = Field(
        "STANDARD",
        description="E.g., '1+1', 'PERCENTAGE_DISCOUNT', 'PREZZO_SOCIO', 'STANDARD'",
    )
    validity_string: Optional[str] = Field(
        None, description="Raw promotion duration description"
    )
