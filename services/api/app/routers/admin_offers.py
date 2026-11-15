"""Admin oversight of vendor offers (W8): list any offer, pause / unpause it.

An admin pause (`paused_by_admin`) overrides the vendor's own status; the
vendor cannot lift it. Every mutation records exactly one audit_log row.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.schemas.offers import AdminOfferPauseRequest, OfferOut
from app.services.offers.store import offer_is_live
from app.services.offers.manage import (
    load_items_for,
    load_offer_rows,
    offer_not_found,
    targets_for_item_rows,
    to_offer_out,
)
from fastapi import APIRouter, Depends, Query

offers_admin_router = APIRouter(prefix="/offers", tags=["admin-offers"])

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


ADMIN_LIST_LIMIT = 200

AdminStatusFilter = Literal["draft", "active", "paused", "archived"]
AdminStateFilter = Literal["live", "admin_paused", "scheduled", "ended"]
AdminTypeFilter = Literal["bxgy", "bundle", "buy_n_pay_m", "free_gift"]


class AdminOfferOut(OfferOut):
    vendor_name: str | None = None
    admin_note: str | None = None


class AdminOfferListResponse(StrictModel):
    items: list[AdminOfferOut]
    #: More offers matched than ``ADMIN_LIST_LIMIT``; narrow the filters.
    truncated: bool = False


def _vendor_names(client: Any, vendor_ids: list[str]) -> dict[str, str]:
    if not vendor_ids:
        return {}
    response = (
        client.table("vendors").select("id, display_name").in_("id", sorted(vendor_ids)).execute()
    )
    rows = response.data if isinstance(getattr(response, "data", None), list) else []
    return {
        str(row["id"]): str(row["display_name"])
        for row in rows
        if isinstance(row, dict) and row.get("id") and isinstance(row.get("display_name"), str)
    }


def _render(client: Any, rows: list[dict[str, Any]]) -> list[AdminOfferOut]:
    items_by_offer = load_items_for(client, [str(r["id"]) for r in rows])
    targets = targets_for_item_rows(
        client, [item for items in items_by_offer.values() for item in items]
    )
    names = _vendor_names(client, list({str(r["vendor_id"]) for r in rows}))
    return [
        AdminOfferOut(
            **to_offer_out(row, items_by_offer.get(str(row["id"]), []), targets).model_dump(),
            vendor_name=names.get(str(row["vendor_id"])),
            admin_note=row.get("admin_note") if isinstance(row.get("admin_note"), str) else None,
        )
        for row in rows
    ]


def _load(client: Any, offer_id: str) -> dict[str, Any]:
    if not _UUID_RE.match(offer_id):
        raise offer_not_found()
    rows = load_offer_rows(client, offer_id=offer_id)
    if not rows:
        raise offer_not_found()
    return rows[0]


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _matches_state(row: dict[str, Any], state: AdminStateFilter, now: datetime) -> bool:
    if state == "live":
        return offer_is_live(row, now)
    if state == "admin_paused":
        return row.get("paused_by_admin") is True
    starts = _parse_ts(row.get("starts_at"))
    ends = _parse_ts(row.get("ends_at"))
    if state == "scheduled":
        return starts is not None and starts > now
    return ends is not None and ends <= now  # ended


def filter_offer_rows(
    rows: list[dict[str, Any]],
    *,
    status: AdminStatusFilter | None = None,
    state: AdminStateFilter | None = None,
    offer_type: AdminTypeFilter | None = None,
    q: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Pure filter for the admin list (status, derived state, type, title search)."""
    moment = now or datetime.now(UTC)
    needle = (q or "").strip().casefold()
    out: list[dict[str, Any]] = []
    for row in rows:
        if status is not None and row.get("status") != status:
            continue
        if offer_type is not None and row.get("offer_type") != offer_type:
            continue
        if state is not None and not _matches_state(row, state, moment):
            continue
        if needle and needle not in str(row.get("title") or "").casefold():
            continue
        out.append(row)
    return out


@offers_admin_router.get("", response_model=AdminOfferListResponse)
def admin_list_offers(
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    vendor_id: Annotated[str | None, Query(max_length=36)] = None,
    status: Annotated[AdminStatusFilter | None, Query()] = None,
    state: Annotated[AdminStateFilter | None, Query()] = None,
    offer_type: Annotated[AdminTypeFilter | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> AdminOfferListResponse:
    _ = current_user
    vendor = vendor_id if vendor_id and _UUID_RE.match(vendor_id) else None
    rows = filter_offer_rows(
        load_offer_rows(service_client.client, vendor_id=vendor),
        status=status,
        state=state,
        offer_type=offer_type,
        q=q,
    )
    return AdminOfferListResponse(
        items=_render(service_client.client, rows[:ADMIN_LIST_LIMIT]),
        truncated=len(rows) > ADMIN_LIST_LIMIT,
    )


def _set_pause(
    offer_id: str,
    paused: bool,
    body: AdminOfferPauseRequest,
    service_client: _ServiceRoleClient,
    recorder: AdminAuditRecorder,
) -> AdminOfferOut:
    loaded = _load(service_client.client, offer_id)
    # Snapshot before the write: the audit row must record the prior values.
    before = {
        "paused_by_admin": loaded.get("paused_by_admin"),
        "admin_note": loaded.get("admin_note"),
    }
    service_client.client.table("offers").update(
        {"paused_by_admin": paused, "admin_note": body.note}
    ).eq("id", offer_id).execute()
    after = _load(service_client.client, offer_id)
    recorder.record(
        action="offer.admin_pause" if paused else "offer.admin_unpause",
        entity_type="offer",
        entity_id=offer_id,
        before=before,
        after={
            "paused_by_admin": after.get("paused_by_admin"),
            "admin_note": after.get("admin_note"),
        },
    )
    return _render(service_client.client, [after])[0]


@offers_admin_router.post("/{offer_id}/pause", response_model=AdminOfferOut)
def admin_pause_offer(
    offer_id: str,
    body: AdminOfferPauseRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> AdminOfferOut:
    _ = current_user
    return _set_pause(offer_id, True, body, service_client, recorder)


@offers_admin_router.post("/{offer_id}/unpause", response_model=AdminOfferOut)
def admin_unpause_offer(
    offer_id: str,
    body: AdminOfferPauseRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> AdminOfferOut:
    _ = current_user
    return _set_pause(offer_id, False, body, service_client, recorder)


admin_router.include_router(offers_admin_router)
