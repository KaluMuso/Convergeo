"""VendorListing field validation for product-class-specific rules."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.base import NgweeInt, StrictModel

ProductClass = Literal["A", "B", "C", "D", "E"]
ListingCondition = Literal["new", "refurbished", "used"]
FulfilmentMode = Literal["stocked", "made_to_order"]
StockMode = Literal["tracked", "always_available"]


class VendorListingEvidenceImage(StrictModel):
    """Minimal evidence slot — cloudinary id from the listing image pipeline."""

    cloudinary_public_id: str = Field(min_length=1, max_length=200)


class VendorListing(StrictModel):
    """Validated vendor listing shape for create/update and cart guard checks.

    Class D (unique/used): condition cannot be new; at least one evidence image.
    Class E (made-to-order): lead time + weekly capacity; stock_qty not enforced.
    """

    product_class: ProductClass = "A"
    condition: ListingCondition
    fulfilment_mode: FulfilmentMode = "stocked"
    lead_time_days: int | None = None
    vendor_capacity_per_week: int | None = Field(default=None, ge=1, le=9999)
    stock_mode: StockMode
    stock_qty: int | None = Field(default=None, ge=0)
    price_ngwee: NgweeInt
    evidence_images: list[VendorListingEvidenceImage] = Field(default_factory=list)
    defect_notes: str | None = None

    @field_validator("price_ngwee")
    @classmethod
    def price_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            msg = "price_ngwee must be greater than zero"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_product_class_rules(self) -> VendorListing:
        if self.product_class == "D":
            if self.condition == "new":
                raise ValueError("Class D listings cannot have condition new")
            if not self.evidence_images:
                raise ValueError("Class D listings require at least one evidence image")
            if self.defect_notes is None or len(self.defect_notes.strip()) < 10:
                raise ValueError("Class D listings require defect_notes of at least 10 characters")

        if self.product_class == "E":
            if self.fulfilment_mode != "made_to_order":
                raise ValueError("Class E listings require fulfilment_mode made_to_order")
            if self.lead_time_days is None or not 1 <= self.lead_time_days <= 365:
                raise ValueError("Class E listings require lead_time_days between 1 and 365")
            if self.vendor_capacity_per_week is None:
                raise ValueError("Class E listings require vendor_capacity_per_week")

        if self.product_class != "E" and self.vendor_capacity_per_week is not None:
            raise ValueError("vendor_capacity_per_week is only valid for Class E listings")

        if self.stock_mode == "tracked" and self.product_class != "E" and self.stock_qty is None:
            raise ValueError("stock_qty is required when stock_mode is tracked")

        return self
