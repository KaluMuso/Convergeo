from __future__ import annotations

import pytest
from app.schemas.vendor_listing import VendorListing, VendorListingEvidenceImage
from pydantic import ValidationError


def test_class_d_rejects_new_condition() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            product_class="D",
            condition="new",
            stock_mode="tracked",
            stock_qty=1,
            price_ngwee=10_000,
            evidence_images=[
                VendorListingEvidenceImage(cloudinary_public_id="used/item-1"),
            ],
            defect_notes="Minor scratch on corner panel",
        )
    assert "Class D listings cannot have condition new" in str(exc_info.value)


def test_class_d_requires_evidence_images() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            product_class="D",
            condition="used",
            stock_mode="tracked",
            stock_qty=1,
            price_ngwee=10_000,
            evidence_images=[],
            defect_notes="Minor scratch on corner panel",
        )
    assert "at least one evidence image" in str(exc_info.value)


def test_class_e_requires_lead_time_and_capacity() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            product_class="E",
            condition="new",
            fulfilment_mode="stocked",
            stock_mode="tracked",
            stock_qty=0,
            price_ngwee=25_000,
        )
    assert "made_to_order" in str(exc_info.value)


def test_class_e_valid_shape() -> None:
    listing = VendorListing(
        product_class="E",
        condition="new",
        fulfilment_mode="made_to_order",
        lead_time_days=14,
        vendor_capacity_per_week=5,
        stock_mode="tracked",
        stock_qty=0,
        price_ngwee=25_000,
    )
    assert listing.product_class == "E"
    assert listing.lead_time_days == 14
