"""VendorListing field validation for product-class-specific rules."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.base import NgweeInt, StrictModel

ProductClass = Literal["A", "B", "C", "D", "E"]
ListingCondition = Literal["new", "refurbished", "used"]
SaleUnit = Literal["each", "metre", "kg", "litre", "bag", "sqm"]
FulfilmentMode = Literal["stocked", "made_to_order"]
StockMode = Literal["tracked", "always_available"]
ListingLifecycleStatus = Literal["draft", "active", "paused"]


class VendorListingEvidenceImage(StrictModel):
    """Minimal evidence slot — cloudinary id from the listing image pipeline."""

    cloudinary_public_id: str = Field(min_length=1, max_length=200)


class VendorListing(StrictModel):
    """Validated vendor listing shape for create/update and cart guard checks.

    Class D (unique/used): condition is used; active used listings need evidence.
    Class E (made-to-order): lead time + weekly capacity; stock_qty not enforced.
    """

    product_class: ProductClass = "A"
    status: ListingLifecycleStatus = "active"
    condition: ListingCondition
    sale_unit: SaleUnit = "each"
    unit_step_milli: int = Field(default=1000, ge=1)
    min_steps: int = Field(default=1, ge=1)
    fulfilment_mode: FulfilmentMode = "stocked"
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    vendor_capacity_per_week: int | None = Field(default=None, ge=1, le=9999)
    stock_mode: StockMode
    stock_qty: int | None = Field(default=None, ge=0)
    price_ngwee: NgweeInt
    wholesale: bool = False
    moq: int = Field(default=1, ge=1)
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
        if self.sale_unit == "each" and self.unit_step_milli != 1000:
            raise ValueError("each listings require unit_step_milli equal to 1000")
        if self.sale_unit != "each" and self.wholesale:
            raise ValueError("per-measure wholesale listings are not supported")

        if self.condition == "used":
            if self.defect_notes is None or len(self.defect_notes.strip()) < 10:
                raise ValueError("used listings require defect_notes of at least 10 characters")
            if self.status == "active" and not self.evidence_images:
                raise ValueError("active used listings require at least one evidence image")

        if self.product_class == "D" and self.condition != "used":
            raise ValueError("Class D listings require condition used")

        if self.fulfilment_mode == "made_to_order":
            if self.lead_time_days is None:
                raise ValueError("made-to-order listings require lead_time_days")
        elif self.lead_time_days is not None:
            raise ValueError("lead_time_days is only valid for made-to-order listings")

        if self.product_class == "E":
            if self.fulfilment_mode != "made_to_order":
                raise ValueError("Class E listings require fulfilment_mode made_to_order")
            if self.vendor_capacity_per_week is None:
                raise ValueError("Class E listings require vendor_capacity_per_week")

            minimum_qty = max(self.min_steps, self.moq)
            if self.vendor_capacity_per_week < minimum_qty:
                raise ValueError(
                    "Class E weekly capacity must cover the minimum purchase quantity"
                )

        if self.product_class != "E" and self.vendor_capacity_per_week is not None:
            raise ValueError("vendor_capacity_per_week is only valid for Class E listings")

        if self.stock_mode == "tracked" and self.product_class != "E" and self.stock_qty is None:
            raise ValueError("stock_qty is required when stock_mode is tracked")

        return self
