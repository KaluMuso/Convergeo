"""Vendor editor API for listing variants (colour / size / storage options).

GET  /vendor/listings/{id}/variants  -> current option groups + variants
PUT  /vendor/listings/{id}/variants  -> replace them atomically

Authz: vendor role + the listing must belong to the caller's vendor. Writes go
through ``public.vendor_replace_listing_variants`` (service role only), which
keeps group/value/variant ids stable across edits so carts and orders stay
linked, archives ordered variants instead of deleting them, and re-syncs a
tracked listing's stock pool to the sum of its active variants.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_listings_manage import (
    _assert_listing_editable,
    _assert_listing_owned_by_vendor,
    _load_listing,
    _load_vendor_for_owner,
)
from app.schemas.base import NgweeInt, StrictModel
from app.services.kyc.state_machine import ServiceRoleClient
from app.services.listings.variants import (
    EMPTY_SET,
    MAX_OPTION_GROUPS,
    MAX_VALUES_PER_GROUP,
    MAX_VARIANTS,
    GroupSpec,
    ListingVariantSet,
    VariantSpec,
    load_variant_sets,
    validate_variant_payload,
)
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/vendor/listings", tags=["vendor-listing-variants"])

VariantStatus = Literal["active", "archived"]
GroupDisplay = Literal["pill", "swatch"]


class OptionValueIn(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    swatch_hex: str | None = Field(default=None, max_length=7)


class OptionGroupIn(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    display: GroupDisplay = "pill"
    values: list[OptionValueIn] = Field(min_length=1, max_length=MAX_VALUES_PER_GROUP)


class VariantIn(StrictModel):
    #: One value label per group, in group order.
    options: list[str] = Field(min_length=1, max_length=MAX_OPTION_GROUPS)
    sku: str | None = Field(default=None, max_length=120)
    stock_qty: int | None = Field(default=None, ge=0, le=1_000_000)
    #: Override in ngwee; None inherits the listing price.
    price_ngwee: NgweeInt | None = None
    compare_at_ngwee: NgweeInt | None = None
    image_public_id: str | None = Field(default=None, max_length=255)
    status: VariantStatus = "active"


class VariantsReplaceRequest(StrictModel):
    groups: list[OptionGroupIn] = Field(default_factory=list, max_length=MAX_OPTION_GROUPS)
    variants: list[VariantIn] = Field(default_factory=list, max_length=MAX_VARIANTS)


class OptionValueOut(StrictModel):
    id: str
    label: str
    swatch_hex: str | None = None


class OptionGroupOut(StrictModel):
    id: str
    name: str
    display: str
    values: list[OptionValueOut]


class VariantOut(StrictModel):
    id: str
    options: list[str]
    sku: str | None = None
    stock_qty: int | None = None
    price_ngwee: int | None = None
    compare_at_ngwee: int | None = None
    image_public_id: str | None = None
    status: str


class VariantsResponse(StrictModel):
    listing_id: str
    listing_price_ngwee: int
    stock_mode: str
    groups: list[OptionGroupOut]
    variants: list[VariantOut]


def _to_response(listing: dict[str, Any], variant_set: ListingVariantSet) -> VariantsResponse:
    label_by_value = {
        value.id: value.label for group in variant_set.groups for value in group.values
    }
    group_of_value = {
        value.id: index for index, group in enumerate(variant_set.groups) for value in group.values
    }
    variants: list[VariantOut] = []
    for variant in variant_set.variants:
        ordered = sorted(
            (value_id for value_id in variant.option_value_ids if value_id in group_of_value),
            key=lambda value_id: group_of_value[value_id],
        )
        if len(ordered) != len(variant_set.groups) and variant.active:
            continue
        variants.append(
            VariantOut(
                id=variant.id,
                options=[label_by_value[value_id] for value_id in ordered],
                sku=variant.sku,
                stock_qty=variant.stock_qty,
                price_ngwee=variant.price_ngwee,
                compare_at_ngwee=variant.compare_at_ngwee,
                image_public_id=variant.image_public_id,
                status=variant.status,
            )
        )
    return VariantsResponse(
        listing_id=str(listing["id"]),
        listing_price_ngwee=int(listing.get("price_ngwee") or 0),
        stock_mode=str(listing.get("stock_mode") or "tracked"),
        groups=[
            OptionGroupOut(
                id=group.id,
                name=group.name,
                display=group.display,
                values=[
                    OptionValueOut(id=value.id, label=value.label, swatch_hex=value.swatch_hex)
                    for value in group.values
                ],
            )
            for group in variant_set.groups
        ],
        variants=variants,
    )


def _owned_listing(
    service_client: ServiceRoleClient, user_id: str, listing_id: str
) -> dict[str, Any]:
    vendor = _load_vendor_for_owner(service_client, user_id)
    listing = _load_listing(service_client, listing_id)
    _assert_listing_owned_by_vendor(listing, str(vendor["id"]), listing_id=listing_id)
    return listing


def _variant_set(service_client: ServiceRoleClient, listing_id: str) -> ListingVariantSet:
    return load_variant_sets(service_client.client, [listing_id]).get(listing_id, EMPTY_SET)


@router.get("/{listing_id}/variants", response_model=VariantsResponse)
async def get_listing_variants(
    listing_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VariantsResponse:
    listing = _owned_listing(service_client, current_user.id, listing_id)
    return _to_response(listing, _variant_set(service_client, listing_id))


@router.put("/{listing_id}/variants", response_model=VariantsResponse)
async def replace_listing_variants(
    listing_id: str,
    body: VariantsReplaceRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[ServiceRoleClient, Depends(get_supabase_client)],
) -> VariantsResponse:
    listing = _owned_listing(service_client, current_user.id, listing_id)
    _assert_listing_editable(listing, listing_id=listing_id)

    image_ids = [
        str(image["cloudinary_public_id"])
        for image in (listing.get("listing_images") or [])
        if isinstance(image, dict) and image.get("cloudinary_public_id")
    ]
    groups = [
        GroupSpec(
            name=group.name.strip(),
            display=group.display,
            values=tuple((value.label.strip(), value.swatch_hex) for value in group.values),
        )
        for group in body.groups
    ]
    variants = [
        VariantSpec(
            options=tuple(option.strip() for option in variant.options),
            sku=variant.sku.strip() if variant.sku and variant.sku.strip() else None,
            stock_qty=variant.stock_qty,
            price_ngwee=variant.price_ngwee,
            compare_at_ngwee=variant.compare_at_ngwee,
            image_public_id=variant.image_public_id or None,
            status=variant.status,
        )
        for variant in body.variants
    ]
    validate_variant_payload(groups, variants, listing=listing, listing_image_ids=image_ids)

    payload_groups = [
        {
            "name": group.name,
            "display": group.display,
            "values": [{"label": label, "swatch_hex": swatch} for label, swatch in group.values],
        }
        for group in groups
    ]
    payload_variants = [
        {
            "options": list(variant.options),
            "sku": variant.sku,
            "stock_qty": variant.stock_qty,
            "price_ngwee": variant.price_ngwee,
            "compare_at_ngwee": variant.compare_at_ngwee,
            "image_public_id": variant.image_public_id,
            "status": variant.status,
        }
        for variant in variants
    ]
    try:
        service_client.client.rpc(
            "vendor_replace_listing_variants",
            {
                "p_listing_id": listing_id,
                "p_groups": payload_groups,
                "p_variants": payload_variants,
            },
        ).execute()
    except AppError:
        raise
    except Exception as exc:  # PostgREST surfaces DB check violations as APIError
        message = str(exc)
        reason = "duplicateSku" if "listing_sku_unique" in message else "saveFailed"
        raise AppError(
            code="variants.invalid",
            message="Variant options could not be saved",
            http_status=422,
            details={
                "field": "variants",
                "reason": reason,
                "message_key": f"vendor.listings.variants.errors.{reason}",
            },
        ) from exc

    refreshed = _load_listing(service_client, listing_id)
    return _to_response(refreshed, _variant_set(service_client, listing_id))
