"""Vendor: shop-wide free-delivery terms (logistics phase 1, who pays delivery).

A vendor can offer free delivery on every order (``free_delivery_all``) and pick how
it travels (``free_delivery_method``): ``platform_courier`` (the zone fee is charged to
the vendor's payable when the order releases) or ``self_delivery`` (the vendor's own
rider; nothing is charged). The pricing rules live in
``app.services.logistics.delivery_pricing`` and snapshot the result on each order at
checkout, so changing these terms never touches an order that already exists.

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
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/vendor/delivery-terms", tags=["vendor-delivery"])

FreeDeliveryMethod = Literal["platform_courier", "self_delivery"]
TERMS_COLUMNS = "id, free_delivery_all, free_delivery_method"


class DeliveryTermsOut(StrictModel):
    free_delivery_all: bool
    free_delivery_method: FreeDeliveryMethod


class DeliveryTermsUpdate(StrictModel):
    free_delivery_all: bool | None = None
    free_delivery_method: FreeDeliveryMethod | None = None


def _terms_from_row(row: dict[str, Any]) -> DeliveryTermsOut:
    method = row.get("free_delivery_method")
    return DeliveryTermsOut(
        free_delivery_all=row.get("free_delivery_all") is True,
        free_delivery_method="self_delivery" if method == "self_delivery" else "platform_courier",
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
    return _terms_from_row(_load_terms(service_client.client, str(vendor["id"])))


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
    before = _terms_from_row(_load_terms(client, vendor_id))

    changes: dict[str, Any] = {}
    if body.free_delivery_all is not None and body.free_delivery_all != before.free_delivery_all:
        changes["free_delivery_all"] = body.free_delivery_all
    if (
        body.free_delivery_method is not None
        and body.free_delivery_method != before.free_delivery_method
    ):
        changes["free_delivery_method"] = body.free_delivery_method
    if not changes:
        return before

    response = client.table("vendors").update(changes).eq("id", vendor_id).execute()
    rows = getattr(response, "data", None)
    row = rows[0] if isinstance(rows, list) and rows else rows
    if not isinstance(row, dict):
        raise AppError(
            code="internal_error", message="Failed to update delivery terms", http_status=500
        )
    after = _terms_from_row({**before.model_dump(), **row})

    return after
