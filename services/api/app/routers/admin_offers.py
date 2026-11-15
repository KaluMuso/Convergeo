"""Admin oversight of vendor offers (W8): list any offer, pause / unpause it.

An admin pause (`paused_by_admin`) overrides the vendor's own status; the
vendor cannot lift it. Every mutation records exactly one audit_log row.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Protocol

from app.core.admin_audit import AdminAuditRecorder, get_admin_audit_recorder
from app.core.auth import CurrentUser, require_role
from app.deps import get_supabase_client
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.schemas.offers import AdminOfferPauseRequest, OfferOut
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


class AdminOfferListResponse(StrictModel):
    items: list[OfferOut]


def _render(client: Any, rows: list[dict[str, Any]]) -> list[OfferOut]:
    items_by_offer = load_items_for(client, [str(r["id"]) for r in rows])
    targets = targets_for_item_rows(
        client, [item for items in items_by_offer.values() for item in items]
    )
    return [to_offer_out(row, items_by_offer.get(str(row["id"]), []), targets) for row in rows]


def _load(client: Any, offer_id: str) -> dict[str, Any]:
    if not _UUID_RE.match(offer_id):
        raise offer_not_found()
    rows = load_offer_rows(client, offer_id=offer_id)
    if not rows:
        raise offer_not_found()
    return rows[0]


@offers_admin_router.get("", response_model=AdminOfferListResponse)
def admin_list_offers(
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    vendor_id: Annotated[str | None, Query(max_length=36)] = None,
) -> AdminOfferListResponse:
    _ = current_user
    vendor = vendor_id if vendor_id and _UUID_RE.match(vendor_id) else None
    rows = load_offer_rows(service_client.client, vendor_id=vendor)[:200]
    return AdminOfferListResponse(items=_render(service_client.client, rows))


def _set_pause(
    offer_id: str,
    paused: bool,
    body: AdminOfferPauseRequest,
    service_client: _ServiceRoleClient,
    recorder: AdminAuditRecorder,
) -> OfferOut:
    before = _load(service_client.client, offer_id)
    service_client.client.table("offers").update(
        {"paused_by_admin": paused, "admin_note": body.note}
    ).eq("id", offer_id).execute()
    after = _load(service_client.client, offer_id)
    recorder.record(
        action="offer.admin_pause" if paused else "offer.admin_unpause",
        entity_type="offer",
        entity_id=offer_id,
        before={
            "paused_by_admin": before.get("paused_by_admin"),
            "admin_note": before.get("admin_note"),
        },
        after={
            "paused_by_admin": after.get("paused_by_admin"),
            "admin_note": after.get("admin_note"),
        },
    )
    return _render(service_client.client, [after])[0]


@offers_admin_router.post("/{offer_id}/pause", response_model=OfferOut)
def admin_pause_offer(
    offer_id: str,
    body: AdminOfferPauseRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> OfferOut:
    _ = current_user
    return _set_pause(offer_id, True, body, service_client, recorder)


@offers_admin_router.post("/{offer_id}/unpause", response_model=OfferOut)
def admin_unpause_offer(
    offer_id: str,
    body: AdminOfferPauseRequest,
    current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> OfferOut:
    _ = current_user
    return _set_pause(offer_id, False, body, service_client, recorder)


admin_router.include_router(offers_admin_router)
