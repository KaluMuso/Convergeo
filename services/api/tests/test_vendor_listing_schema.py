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
    assert "Class D listings require condition used" in str(exc_info.value)


def test_class_d_rejects_refurbished_condition() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            product_class="D",
            condition="refurbished",
            stock_mode="tracked",
            stock_qty=1,
            price_ngwee=10_000,
            defect_notes="Minor scratch on corner panel",
        )
    assert "Class D listings require condition used" in str(exc_info.value)


def test_draft_class_d_can_be_created_before_evidence_upload() -> None:
    listing = VendorListing(
        product_class="D",
        status="draft",
        condition="used",
        stock_mode="tracked",
        stock_qty=1,
        price_ngwee=10_000,
        evidence_images=[],
        defect_notes="Minor scratch on corner panel",
    )
    assert listing.status == "draft"


def test_active_used_listing_requires_evidence_images() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            product_class="D",
            status="active",
            condition="used",
            stock_mode="tracked",
            stock_qty=1,
            price_ngwee=10_000,
            evidence_images=[],
            defect_notes="Minor scratch on corner panel",
        )
    assert "active used listings require at least one evidence image" in str(exc_info.value)


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


def test_legacy_non_class_e_made_to_order_shape_remains_valid() -> None:
    listing = VendorListing(
        product_class="A",
        condition="new",
        fulfilment_mode="made_to_order",
        lead_time_days=14,
        stock_mode="always_available",
        price_ngwee=25_000,
    )
    assert listing.fulfilment_mode == "made_to_order"


def test_class_e_capacity_must_cover_minimum_purchase() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            product_class="E",
            condition="new",
            min_steps=4,
            moq=6,
            fulfilment_mode="made_to_order",
            lead_time_days=14,
            vendor_capacity_per_week=5,
            stock_mode="tracked",
            stock_qty=0,
            price_ngwee=25_000,
        )
    assert "capacity must cover the minimum purchase quantity" in str(exc_info.value)


def test_per_measure_listing_accepts_integer_milli_increment() -> None:
    listing = VendorListing(
        condition="new",
        sale_unit="metre",
        unit_step_milli=500,
        min_steps=2,
        stock_mode="tracked",
        stock_qty=10,
        price_ngwee=25_000,
    )
    assert listing.unit_step_milli == 500
    assert listing.min_steps == 2


def test_each_listing_rejects_non_whole_increment() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            condition="new",
            sale_unit="each",
            unit_step_milli=500,
            stock_mode="tracked",
            stock_qty=10,
            price_ngwee=25_000,
        )
    assert "unit_step_milli equal to 1000" in str(exc_info.value)


def test_per_measure_wholesale_is_deferred() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VendorListing(
            condition="new",
            sale_unit="kg",
            unit_step_milli=250,
            stock_mode="tracked",
            stock_qty=10,
            price_ngwee=25_000,
            wholesale=True,
        )
    assert "per-measure wholesale listings are not supported" in str(exc_info.value)
