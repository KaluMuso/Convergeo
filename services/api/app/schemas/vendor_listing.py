"""VendorListing field validation for product-class-specific rules."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.errors import field_value_error
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

    Class D (unique / one-of-a-kind): any condition; active used listings need evidence.
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
            raise field_value_error(
                "unit_step_milli",
                "each listings require unit_step_milli equal to 1000",
                "unit_step_each",
            )
        if self.sale_unit != "each" and self.wholesale:
            raise field_value_error(
                "wholesale",
                "per-measure wholesale listings are not supported",
                "wholesale_measure",
            )

        if self.condition == "used":
            if self.defect_notes is None or len(self.defect_notes.strip()) < 10:
                raise field_value_error(
                    "defect_notes",
                    "used listings require defect_notes of at least 10 characters",
                    "defect_notes_required",
                )
            if self.status == "active" and not self.evidence_images:
                raise field_value_error(
                    "evidence_images",
                    "active used listings require at least one evidence image",
                    "evidence_required",
                )

        # Class D (unique / one-of-a-kind) may be new, refurbished or used: a
        # brand-new handmade or one-off item is a legitimate standalone offer.
        # Only `used` carries extra duties (defect notes + photo evidence above).

        if self.fulfilment_mode == "made_to_order":
            if self.lead_time_days is None:
                raise field_value_error(
                    "lead_time_days",
                    "made-to-order listings require lead_time_days",
                    "lead_time_required",
                )
        elif self.lead_time_days is not None:
            raise field_value_error(
                "lead_time_days",
                "lead_time_days is only valid for made-to-order listings",
                "lead_time_not_allowed",
            )

        if self.product_class == "E":
            if self.fulfilment_mode != "made_to_order":
                raise field_value_error(
                    "fulfilment_mode",
                    "Class E listings require fulfilment_mode made_to_order",
                    "class_e_made_to_order",
                )
            if self.vendor_capacity_per_week is None:
                raise field_value_error(
                    "vendor_capacity_per_week",
                    "Class E listings require vendor_capacity_per_week",
                    "capacity_required",
                )

            minimum_qty = max(self.min_steps, self.moq)
            if self.vendor_capacity_per_week < minimum_qty:
                raise field_value_error(
                    "vendor_capacity_per_week",
                    "Class E weekly capacity must cover the minimum purchase quantity",
                    "capacity_too_low",
                )

        if self.product_class != "E" and self.vendor_capacity_per_week is not None:
            raise field_value_error(
                "vendor_capacity_per_week",
                "vendor_capacity_per_week is only valid for Class E listings",
                "capacity_not_allowed",
            )

        if self.stock_mode == "tracked" and self.product_class != "E" and self.stock_qty is None:
            raise field_value_error(
                "stock_qty",
                "stock_qty is required when stock_mode is tracked",
                "stock_qty_required",
            )

        return self
