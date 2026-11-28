"""Vendor: shop-wide free-delivery terms (logistics phase 1, who pays delivery).

A vendor can offer free delivery on every order (``free_delivery_all``) and pick how
it travels (``free_delivery_method``): ``platform_courier`` (the zone fee is charged to
the vendor's payable when the order releases) or ``self_delivery`` (the vendor's own
rider; nothing is charged). The pricing rules live in
``app.services.logistics.delivery_pricing`` and snapshot the result on each order at
checkout, so changing these terms never touches an order that already exists.

A vendor also sets the smallest basket that qualifies for their free delivery
(``free_delivery_min_ngwee``, default K300). They may raise it but never go below the
platform floor (``platform_config.vendor_free_delivery_min_floor_ngwee``, K300 unless
the founder changes it); pricing re-applies the floor at checkout.

Money-adjacent: rate limited, and every change is audit-logged by a database trigger
(migration 20261128120000) in the same transaction as the UPDATE, so it can never land unlogged.
Per-listing "free delivery" and shipping weight live on ``PATCH /vendor/listings/{id}``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import SENSITIVE_WRITE
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_profile import require_vendor_owner
from app.schemas.base import StrictModel
from app.services.logistics.delivery_pricing import (
    DEFAULT_VENDOR_FREE_MIN_FLOOR_NGWEE,
    FREE_MIN_FLOOR_KEY,
    _config_int,
)
from fastapi import APIRouter, Depends
from pydantic import Field

router = APIRouter(prefix="/vendor/delivery-terms", tags=["vendor-delivery"])

FreeDeliveryMethod = Literal["platform_courier", "self_delivery"]
TERMS_COLUMNS = "id, free_delivery_all, free_delivery_method, free_delivery_min_ngwee"
#: Sanity ceiling (K1,000,000) so a typo cannot make free delivery unreachable by accident.
MAX_FREE_MIN_NGWEE = 100_000_000


class ZoneFeeOut(StrictModel):
    zone_key: str
    label: str
    fee_ngwee: int


class DeliveryTermsOut(StrictModel):
    free_delivery_all: bool
    free_delivery_method: FreeDeliveryMethod
    #: Smallest vendor basket (ngwee) that qualifies for this vendor's free delivery.
    free_delivery_min_ngwee: int
    #: Platform floor the minimum may not go below (ngwee).
    min_floor_ngwee: int
    #: Delivery fee per band the vendor pays when a courier delivers a free order.
    zone_fees: list[ZoneFeeOut]


class DeliveryTermsUpdate(StrictModel):
    free_delivery_all: bool | None = None
    free_delivery_method: FreeDeliveryMethod | None = None
    free_delivery_min_ngwee: int | None = Field(default=None, ge=0, le=MAX_FREE_MIN_NGWEE)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _load_floor(client: Any) -> int:
    rows = _rows(
        client.table("platform_config").select("key, value").eq("key", FREE_MIN_FLOOR_KEY).execute()
    )
    return _config_int(rows, FREE_MIN_FLOOR_KEY, DEFAULT_VENDOR_FREE_MIN_FLOOR_NGWEE)


def _load_zone_fees(client: Any) -> list[ZoneFeeOut]:
    rows = _rows(
        client.table("delivery_zones")
        .select("zone_key, label, fee_ngwee")
        .eq("active", True)
        .order("fee_ngwee")
        .execute()
    )
    return [
        ZoneFeeOut(
            zone_key=str(r["zone_key"]), label=str(r["label"]), fee_ngwee=int(r["fee_ngwee"])
        )
        for r in rows
        if isinstance(r.get("fee_ngwee"), int) and r.get("zone_key") and r.get("label")
    ]


def _terms_from_row(
    row: dict[str, Any], *, floor: int, zone_fees: list[ZoneFeeOut]
) -> DeliveryTermsOut:
    method = row.get("free_delivery_method")
    stored = row.get("free_delivery_min_ngwee")
    minimum = stored if isinstance(stored, int) and not isinstance(stored, bool) else floor
    return DeliveryTermsOut(
        free_delivery_all=row.get("free_delivery_all") is True,
        free_delivery_method="self_delivery" if method == "self_delivery" else "platform_courier",
        free_delivery_min_ngwee=max(minimum, floor),
        min_floor_ngwee=floor,
        zone_fees=zone_fees,
    )


def _load_terms(client: Any, vendor_id: str) -> dict[str, Any]:
    response = (
        client.table("vendors").select(TERMS_COLUMNS).eq("id", vendor_id).maybe_single().execute()
    )
    data = getattr(response, "data", None)
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise AppError(
            code="forbidden",
            message="Authenticated user does not own a vendor profile",
            http_status=403,
            details={"message_key": "vendor.errors.not_found"},
        )
    return data


def _limit(client: Any, user_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=SENSITIVE_WRITE.scope,
        key=f"delivery-terms:{user_id}",
        window=SENSITIVE_WRITE.window,
        limit=SENSITIVE_WRITE.limit,
        client=client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after, message_key="vendor.deliveryTerms.errors.rateLimited"
        )


# Plain ``def`` for the read: the Supabase client is synchronous (see vendor_extras).
@router.get("", response_model=DeliveryTermsOut)
def get_delivery_terms(
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> DeliveryTermsOut:
    client: Any = service_client.client
    return _terms_from_row(
        _load_terms(client, str(vendor["id"])),
        floor=_load_floor(client),
        zone_fees=_load_zone_fees(client),
    )


@router.patch("", response_model=DeliveryTermsOut)
async def update_delivery_terms(
    body: DeliveryTermsUpdate,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    vendor: Annotated[dict[str, Any], Depends(require_vendor_owner)],
    service_client: Annotated[Any, Depends(get_supabase_client)],
) -> DeliveryTermsOut:
    client: Any = service_client.client
    _limit(client, current_user.id)
    vendor_id = str(vendor["id"])
    floor = _load_floor(client)
    zone_fees = _load_zone_fees(client)
    if body.free_delivery_min_ngwee is not None and body.free_delivery_min_ngwee < floor:
        raise AppError(
            code="validation_error",
            message="free_delivery_min_ngwee is below the platform minimum",
            http_status=422,
            details={
                "message_key": "vendor.deliveryTerms.errors.minBelowFloor",
                "min_floor_ngwee": floor,
            },
        )
    before = _terms_from_row(_load_terms(client, vendor_id), floor=floor, zone_fees=zone_fees)

    changes: dict[str, Any] = {}
    if body.free_delivery_all is not None and body.free_delivery_all != before.free_delivery_all:
        changes["free_delivery_all"] = body.free_delivery_all
    if (
        body.free_delivery_method is not None
        and body.free_delivery_method != before.free_delivery_method
    ):
        changes["free_delivery_method"] = body.free_delivery_method
    if (
        body.free_delivery_min_ngwee is not None
        and body.free_delivery_min_ngwee != before.free_delivery_min_ngwee
    ):
        changes["free_delivery_min_ngwee"] = body.free_delivery_min_ngwee
    if not changes:
        return before

    response = client.table("vendors").update(changes).eq("id", vendor_id).execute()
    rows = getattr(response, "data", None)
    row = rows[0] if isinstance(rows, list) and rows else rows
    if not isinstance(row, dict):
        raise AppError(
            code="internal_error", message="Failed to update delivery terms", http_status=500
        )
    return _terms_from_row(
        {**before.model_dump(exclude={"zone_fees", "min_floor_ngwee"}), **row},
        floor=floor,
        zone_fees=zone_fees,
    )
