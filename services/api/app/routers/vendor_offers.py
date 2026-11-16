"""Vendor offers CRUD (W8, flag `bundles`).

Every route resolves the caller's own vendor and re-checks that the offer and
every item belong to it (404 for another vendor's offer, 403 for a foreign
item). The DB guards the same rules (RLS + offer_items_guard). Writes are rate
limited per vendor (`vendor_offers_write`) and leave an audit_log row.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.routers.vendor_orders import _load_vendor_for_owner
from app.schemas.offers import (
    OfferListResponse,
    OfferOut,
    OfferPreviewResponse,
    OfferWriteRequest,
)
from app.services.offers.manage import (
    assert_items_owned,
    assert_within_discount_cap,
    cap_pct,
    load_items_for,
    load_offer_rows,
    load_targets,
    offer_not_found,
    preview_offer,
    require_bundles_enabled,
    targets_for_item_rows,
    to_offer_out,
)
from app.services.offers.store import max_active_offers
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/vendor/offers", tags=["vendor-offers"])

RATE_SCOPE = "vendor_offers_write"
RATE_LIMIT_PER_MINUTE = 30
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _rate_limit(service_client: _ServiceRoleClient, vendor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=RATE_SCOPE,
        key=vendor_id,
        window=timedelta(minutes=1),
        limit=RATE_LIMIT_PER_MINUTE,
        client=service_client.client,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="vendor.offers.errors.rateLimited",
            message="Too many offer changes",
        )


def _vendor_id(service_client: _ServiceRoleClient, user: CurrentUser) -> str:
    require_bundles_enabled(service_client.client)
    vendor = _load_vendor_for_owner(service_client, user.id)
    return str(vendor["id"])


def _own_offer(service_client: _ServiceRoleClient, offer_id: str, vendor_id: str) -> dict[str, Any]:
    if not _UUID_RE.match(offer_id):
        raise offer_not_found()
    rows = load_offer_rows(service_client.client, offer_id=offer_id)
    # Another vendor's offer is indistinguishable from a missing one.
    if not rows or str(rows[0].get("vendor_id")) != vendor_id:
        raise offer_not_found()
    return rows[0]


def _render(service_client: _ServiceRoleClient, rows: list[dict[str, Any]]) -> list[OfferOut]:
    items_by_offer = load_items_for(service_client.client, [str(r["id"]) for r in rows])
    all_items = [item for items in items_by_offer.values() for item in items]
    targets = targets_for_item_rows(service_client.client, all_items)
    return [to_offer_out(row, items_by_offer.get(str(row["id"]), []), targets) for row in rows]


def _validated_targets(
    service_client: _ServiceRoleClient, body: OfferWriteRequest, vendor_id: str
) -> dict[str, dict[str, Any]]:
    targets = load_targets(
        service_client.client,
        [{"kind": item.item_kind, "ref": item.ref_id.lower()} for item in body.items],
    )
    assert_items_owned(targets, body, vendor_id)
    assert_within_discount_cap(body, targets, cap_pct(service_client.client))
    return targets


def _assert_active_cap(
    service_client: _ServiceRoleClient, vendor_id: str, *, exclude_offer_id: str | None
) -> None:
    rows = _rows(
        service_client.client.table("offers")
        .select("id")
        .eq("vendor_id", vendor_id)
        .eq("status", "active")
        .execute()
    )
    active = [r for r in rows if str(r.get("id")) != exclude_offer_id]
    limit = max_active_offers(service_client.client)
    if len(active) >= limit:
        raise AppError(
            code="offers.too_many_active",
            message="Too many active offers",
            http_status=422,
            details={"message_key": "vendor.offers.errors.tooManyActive", "limit": limit},
        )


def _header_payload(body: OfferWriteRequest) -> dict[str, Any]:
    starts = body.starts_at or datetime.now(UTC)
    return {
        "offer_type": body.offer_type,
        "title": body.title.strip(),
        "status": body.status,
        "starts_at": starts.isoformat(),
        "ends_at": body.ends_at.isoformat() if body.ends_at else None,
        "buy_qty": body.buy_qty,
        "get_qty": body.get_qty,
        "bundle_pricing": body.bundle_pricing,
        "addon_percent_off": body.addon_percent_off,
        "bundle_price_ngwee": body.bundle_price_ngwee,
        "buy_n": body.buy_n,
        "pay_m": body.pay_m,
        "gift_stock_total": body.gift_stock_total,
        "max_applications_per_order": body.max_applications_per_order,
        "per_customer_limit": body.per_customer_limit,
    }


def _item_rows(offer_id: str, body: OfferWriteRequest) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(body.items):
        ref = item.ref_id.lower()
        rows.append(
            {
                "offer_id": offer_id,
                "role": item.role,
                "item_kind": item.item_kind,
                "listing_id": ref if item.item_kind == "product" else None,
                "service_id": ref if item.item_kind == "service" else None,
                "event_id": ref if item.item_kind == "event" else None,
                "qty": item.qty,
                "sort_order": index,
            }
        )
    return rows


def _audit(
    service_client: _ServiceRoleClient,
    *,
    actor: str,
    action: str,
    offer_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    service_client.client.table("audit_log").insert(
        {
            "actor": actor,
            "action": action,
            "entity_type": "offer",
            "entity_id": offer_id,
            "before": before,
            "after": after,
        }
    ).execute()


@router.get("", response_model=OfferListResponse)
def list_offers(
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OfferListResponse:
    vendor_id = _vendor_id(service_client, current_user)
    rows = [
        r
        for r in load_offer_rows(service_client.client, vendor_id=vendor_id)
        if r.get("status") != "archived"
    ]
    return OfferListResponse(
        items=_render(service_client, rows),
        max_discount_pct=cap_pct(service_client.client),
        max_active_offers=max_active_offers(service_client.client),
    )


@router.get("/{offer_id}", response_model=OfferOut)
def get_offer(
    offer_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OfferOut:
    vendor_id = _vendor_id(service_client, current_user)
    row = _own_offer(service_client, offer_id, vendor_id)
    return _render(service_client, [row])[0]


@router.post("/preview", response_model=OfferPreviewResponse)
def preview(
    body: OfferWriteRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OfferPreviewResponse:
    vendor_id = _vendor_id(service_client, current_user)
    _rate_limit(service_client, vendor_id)
    targets = load_targets(
        service_client.client,
        [{"kind": item.item_kind, "ref": item.ref_id.lower()} for item in body.items],
    )
    assert_items_owned(targets, body, vendor_id)
    return preview_offer(
        body, vendor_id=vendor_id, targets=targets, cap_pct=cap_pct(service_client.client)
    )


@router.post("", response_model=OfferOut, status_code=201)
def create_offer(
    body: OfferWriteRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OfferOut:
    vendor_id = _vendor_id(service_client, current_user)
    _rate_limit(service_client, vendor_id)
    _validated_targets(service_client, body, vendor_id)
    if body.status == "active":
        _assert_active_cap(service_client, vendor_id, exclude_offer_id=None)
    payload = {
        **_header_payload(body),
        "vendor_id": vendor_id,
        "created_by": current_user.id,
        "updated_by": current_user.id,
    }
    created = _rows(service_client.client.table("offers").insert(payload).execute())
    if not created:
        raise AppError(code="offers.write_failed", message="Offer not saved", http_status=500)
    offer_id = str(created[0]["id"])
    try:
        service_client.client.table("offer_items").insert(_item_rows(offer_id, body)).execute()
    except Exception:
        # No partial offer: the header without items is removed again.
        service_client.client.table("offers").delete().eq("id", offer_id).execute()
        raise
    _audit(
        service_client,
        actor=current_user.id,
        action="offer.create",
        offer_id=offer_id,
        before=None,
        after={**payload, "items": _item_rows(offer_id, body)},
    )
    return _render(service_client, load_offer_rows(service_client.client, offer_id=offer_id))[0]


@router.patch("/{offer_id}", response_model=OfferOut)
def update_offer(
    offer_id: str,
    body: OfferWriteRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OfferOut:
    vendor_id = _vendor_id(service_client, current_user)
    _rate_limit(service_client, vendor_id)
    before = _own_offer(service_client, offer_id, vendor_id)
    if before.get("status") == "archived":
        raise offer_not_found()
    if body.offer_type != before.get("offer_type"):
        raise AppError(
            code="offers.type_immutable",
            message="An offer's type cannot change",
            http_status=422,
            details={"message_key": "vendor.offers.errors.typeImmutable", "field": "offer_type"},
        )
    reserved = int(before.get("gift_stock_reserved") or 0)
    if body.gift_stock_total is not None and body.gift_stock_total < reserved:
        raise AppError(
            code="offers.gift_stock_below_reserved",
            message="Gift stock cannot go below the gifts already reserved",
            http_status=422,
            details={
                "message_key": "vendor.offers.errors.giftStockBelowReserved",
                "field": "gift_stock_total",
                "reserved": reserved,
            },
        )
    _validated_targets(service_client, body, vendor_id)
    if body.status == "active" and before.get("status") != "active":
        _assert_active_cap(service_client, vendor_id, exclude_offer_id=offer_id)
    payload = {**_header_payload(body), "updated_by": current_user.id}
    if body.starts_at is None:
        payload.pop("starts_at")
    service_client.client.table("offers").update(payload).eq("id", offer_id).eq(
        "vendor_id", vendor_id
    ).execute()
    before_items = load_items_for(service_client.client, [offer_id]).get(offer_id, [])
    service_client.client.table("offer_items").delete().eq("offer_id", offer_id).execute()
    service_client.client.table("offer_items").insert(_item_rows(offer_id, body)).execute()
    _audit(
        service_client,
        actor=current_user.id,
        action="offer.update",
        offer_id=offer_id,
        before={**before, "items": before_items},
        after={**payload, "items": _item_rows(offer_id, body)},
    )
    return _render(service_client, load_offer_rows(service_client.client, offer_id=offer_id))[0]


@router.delete("/{offer_id}", response_model=OfferOut)
def archive_offer(
    offer_id: str,
    current_user: Annotated[CurrentUser, Depends(require_role("vendor"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> OfferOut:
    """Soft delete: past orders keep their offer reference and snapshot."""
    vendor_id = _vendor_id(service_client, current_user)
    _rate_limit(service_client, vendor_id)
    before = _own_offer(service_client, offer_id, vendor_id)
    service_client.client.table("offers").update(
        {"status": "archived", "updated_by": current_user.id}
    ).eq("id", offer_id).eq("vendor_id", vendor_id).execute()
    _audit(
        service_client,
        actor=current_user.id,
        action="offer.archive",
        offer_id=offer_id,
        before={"status": before.get("status")},
        after={"status": "archived"},
    )
    return _render(service_client, load_offer_rows(service_client.client, offer_id=offer_id))[0]
