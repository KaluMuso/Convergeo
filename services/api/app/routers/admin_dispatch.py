"""Admin courier dispatch board (courier dispatch v1).

Extends the D16 manual-dispatch model in ``admin_orders.py``: the courier is now
an admin-managed record and each dispatch is a guarded state machine
(``app.services.dispatch``). Every mutation is admin-only, rate limited
(``ratelimit_policies.POLICIES``), Pydantic-validated and audit-logged.

Dispatch actions are gated by the ``courier_dispatch`` flag (default OFF); the
courier directory itself stays editable so ops can prepare before enabling.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from app.core.admin_audit import (
    AdminAuditedRoute,
    AdminAuditRecorder,
    get_admin_audit_recorder,
)
from app.core.auth import CurrentUser, require_role
from app.core.ratelimit import bump_rate_counter, raise_rate_limited
from app.core.ratelimit_policies import SENSITIVE_WRITE
from app.deps import get_supabase_client
from app.routers.admin_base import router as admin_router
from app.schemas.base import StrictModel
from app.services.dispatch import couriers as courier_service
from app.services.dispatch import service as dispatch_service
from app.services.dispatch.message import order_reference
from app.services.dispatch.state import (
    DispatchRow,
    DispatchStatus,
    allowed_next_statuses,
    fetch_dispatch,
    fetch_dispatch_events,
)
from app.services.orders.events import emit_order_lifecycle
from fastapi import APIRouter, Depends
from pydantic import Field

logger = logging.getLogger(__name__)

dispatch_router = APIRouter(
    prefix="/dispatch",
    tags=["admin-dispatch"],
    route_class=AdminAuditedRoute,
)

#: Per-admin ceiling on handover-code attempts (on top of the per-dispatch
#: lockout in the service). Reuses the declared ``write_sensitive`` scope.
HANDOVER_RATE_LIMIT = 10
HANDOVER_RATE_WINDOW = timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ZoneIn(StrictModel):
    zone_key: str = Field(min_length=1, max_length=64)
    price_ngwee: int | None = Field(default=None, ge=0)


class CourierIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    contact_whatsapp_e164: str | None = Field(default=None, max_length=16)
    contact_email: str | None = Field(default=None, max_length=254)
    integration_kind: Literal["manual", "api"] = "manual"
    active: bool = True
    notes: str | None = Field(default=None, max_length=1000)
    zones: list[ZoneIn] = Field(default_factory=list, max_length=50)


class ZoneOut(StrictModel):
    zone_key: str
    price_ngwee: int | None


class CourierOut(StrictModel):
    id: str
    name: str
    contact_whatsapp_e164: str | None
    contact_email: str | None
    integration_kind: str
    active: bool
    notes: str | None
    zones: list[ZoneOut]


_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class CreateDispatchIn(StrictModel):
    order_id: str = Field(pattern=_UUID_PATTERN)
    courier_partner_id: str = Field(pattern=_UUID_PATTERN)
    note: str | None = Field(default=None, max_length=500)
    #: "return" carries a failed delivery back to the shop (logistics phase 1).
    direction: Literal["delivery", "return"] = "delivery"


FailureCode = Literal[
    "customer_unavailable",
    "customer_refused",
    "wrong_address",
    "vendor_not_ready",
    "courier_no_show",
    "damaged",
    "other",
]


class TransitionIn(StrictModel):
    to_status: Literal["accepted", "picked_up", "delivered", "failed", "cancelled"]
    note: str | None = Field(default=None, max_length=500)
    courier_reference: str | None = Field(default=None, max_length=120)
    failure_reason: str | None = Field(default=None, max_length=500)
    failure_code: FailureCode | None = None
    pod_photo_public_id: str | None = Field(default=None, max_length=255)
    cod_collected_ngwee: int | None = Field(default=None, ge=0, le=100_000_000)
    cod_collected_method: Literal["cash", "mobile_money"] | None = None


class CompleteIn(StrictModel):
    """One step: proof of delivery (code or photo) + the rider's cash."""

    handover_code: str | None = Field(
        default=None, min_length=6, max_length=6, pattern=r"^[0-9]{6}$"
    )
    pod_photo_public_id: str | None = Field(default=None, max_length=255)
    cod_collected_ngwee: int | None = Field(default=None, ge=0, le=100_000_000)
    cod_collected_method: Literal["cash", "mobile_money"] | None = None


class ReturnAckIn(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class CostIn(StrictModel):
    actual_cost_ngwee: int = Field(ge=0, le=5_000_000)


class NotifyIn(StrictModel):
    channel: Literal["whatsapp", "email"] = "whatsapp"


class HandoverIn(StrictModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class DispatchOut(StrictModel):
    id: str
    order_id: str
    order_reference: str
    courier_partner_id: str
    courier_name: str
    status: str
    allowed_next: list[str]
    courier_reference: str | None
    cod_amount_ngwee: int
    quoted_price_ngwee: int | None
    pod_photo_public_id: str | None
    delivered_via: str | None
    failure_reason: str | None
    notify_count: int
    last_notified_at: str | None
    requested_at: str
    accepted_at: str | None
    picked_up_at: str | None
    delivered_at: str | None
    failed_at: str | None
    cancelled_at: str | None
    vendor_name: str = ""
    order_status: str = ""
    delivery_zone: str | None = None
    handover_locked: bool = False
    direction: str = "delivery"
    attempt_no: int = 1
    failure_code: str | None = None
    actual_cost_ngwee: int | None = None
    cod_collected_ngwee: int | None = None
    cod_collected_method: str | None = None
    remitted: bool = False


class ReadyOrderOut(StrictModel):
    order_id: str
    order_reference: str
    status: str
    vendor_name: str
    delivery_zone: str | None
    cod: bool
    cod_amount_ngwee: int
    subtotal_ngwee: int
    delivery_fee_ngwee: int
    item_count: int
    created_at: str
    last_failed_reason: str | None
    checkout_group_id: str | None = None
    group_key: str | None = None
    dropoff_landmark: str | None = None
    ready_at: str | None = None
    deliver_together: bool = True
    pickup_label: str | None = None
    pickup_area: str | None = None
    multi_branch: bool = False
    delivery_attempts: int = 0


class DeliveryZoneOut(StrictModel):
    zone_key: str
    label: str
    fee_ngwee: int


class BoardOut(StrictModel):
    flag_enabled: bool
    ready_orders: list[ReadyOrderOut]
    dispatches: list[DispatchOut]
    couriers: list[CourierOut]
    zones: list[DeliveryZoneOut]


class DispatchEventOut(StrictModel):
    id: str
    actor: str | None
    from_status: str | None
    to_status: str
    note: str | None
    created_at: str


class DispatchDetailOut(StrictModel):
    dispatch: DispatchOut
    events: list[DispatchEventOut]


class MessageOut(StrictModel):
    dispatch_id: str
    text: str
    whatsapp_to: str | None
    email_to: str | None


class NotifyOut(StrictModel):
    dispatch_id: str
    channel: str
    enqueued: bool
    notify_count: int
    text: str


class TransitionOut(StrictModel):
    dispatch: DispatchOut
    order_status: str | None


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _courier_out(row: dict[str, Any]) -> CourierOut:
    zones = [
        ZoneOut(zone_key=str(zone["zone_key"]), price_ngwee=zone.get("price_ngwee"))
        for zone in (row.get("zones") or [])
        if isinstance(zone, dict)
    ]
    return CourierOut(
        id=str(row["id"]),
        name=str(row["name"]),
        contact_whatsapp_e164=row.get("contact_whatsapp_e164"),
        contact_email=row.get("contact_email"),
        integration_kind=str(row["integration_kind"]),
        active=bool(row["active"]),
        notes=row.get("notes"),
        zones=zones,
    )


def _dispatch_out(
    dispatch: DispatchRow,
    *,
    courier_name: str,
    vendor_name: str = "",
    order_status: str = "",
    delivery_zone: str | None = None,
    handover_locked: bool = False,
) -> DispatchOut:
    return DispatchOut(
        id=dispatch.id,
        order_id=dispatch.order_id,
        order_reference=order_reference(dispatch.order_id),
        courier_partner_id=dispatch.courier_partner_id,
        courier_name=courier_name,
        status=dispatch.status.value,
        allowed_next=[status.value for status in allowed_next_statuses(dispatch.status)],
        courier_reference=dispatch.courier_reference,
        cod_amount_ngwee=dispatch.cod_amount_ngwee,
        quoted_price_ngwee=dispatch.quoted_price_ngwee,
        pod_photo_public_id=dispatch.pod_photo_public_id,
        delivered_via=dispatch.delivered_via,
        failure_reason=dispatch.failure_reason,
        notify_count=dispatch.notify_count,
        last_notified_at=dispatch.last_notified_at,
        requested_at=dispatch.requested_at,
        accepted_at=dispatch.accepted_at,
        picked_up_at=dispatch.picked_up_at,
        delivered_at=dispatch.delivered_at,
        failed_at=dispatch.failed_at,
        cancelled_at=dispatch.cancelled_at,
        vendor_name=vendor_name,
        order_status=order_status,
        delivery_zone=delivery_zone,
        handover_locked=handover_locked,
        direction=dispatch.direction,
        attempt_no=dispatch.attempt_no,
        failure_code=dispatch.failure_code,
        actual_cost_ngwee=dispatch.actual_cost_ngwee,
        cod_collected_ngwee=dispatch.cod_collected_ngwee,
        cod_collected_method=dispatch.cod_collected_method,
        remitted=dispatch.remittance_id is not None,
    )


def _opt(value: Any) -> str | None:
    return str(value) if value is not None else None


def _is_full_admin(user: CurrentUser) -> bool:
    return bool(user.roles.intersection({"admin", "superadmin"}))


def _courier_input(body: CourierIn) -> courier_service.CourierInput:
    return courier_service.CourierInput(
        name=body.name,
        contact_whatsapp_e164=body.contact_whatsapp_e164,
        contact_email=body.contact_email,
        integration_kind=body.integration_kind,
        active=body.active,
        notes=body.notes,
        zones=tuple(
            courier_service.ZoneInput(zone_key=zone.zone_key, price_ngwee=zone.price_ngwee)
            for zone in body.zones
        ),
    )


def _dispatch_detail_out(dispatch_id: str) -> DispatchOut:
    dispatch = fetch_dispatch(dispatch_id)
    courier = courier_service.get_courier(dispatch.courier_partner_id)
    return _dispatch_out(dispatch, courier_name=str(courier.get("name") or ""))


def enforce_handover_rate_limit(actor_id: str) -> None:
    allowed, retry_after = bump_rate_counter(
        scope=SENSITIVE_WRITE.scope,
        key=f"dispatch_handover:{actor_id}",
        window=HANDOVER_RATE_WINDOW,
        limit=HANDOVER_RATE_LIMIT,
    )
    if not allowed:
        raise_rate_limited(
            retry_after=retry_after,
            message_key="admin.dispatch.errors.rateLimited",
            message="Too many handover attempts",
        )


# ---------------------------------------------------------------------------
# Board + couriers
# ---------------------------------------------------------------------------


@dispatch_router.get("/board", response_model=BoardOut)
def get_board(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> BoardOut:
    snapshot = dispatch_service.board_snapshot()
    return BoardOut(
        flag_enabled=dispatch_service.is_courier_dispatch_enabled(),
        ready_orders=[
            ReadyOrderOut(
                order_id=str(row["order_id"]),
                order_reference=str(row["order_reference"]),
                status=str(row["status"]),
                vendor_name=str(row.get("vendor_name") or ""),
                delivery_zone=row.get("delivery_zone"),
                cod=bool(row.get("cod")),
                cod_amount_ngwee=int(row["cod_amount_ngwee"]),
                subtotal_ngwee=int(row.get("subtotal_ngwee") or 0),
                delivery_fee_ngwee=int(row.get("delivery_fee_ngwee") or 0),
                item_count=int(row.get("item_count") or 0),
                created_at=str(row["created_at"]),
                last_failed_reason=row.get("last_failed_reason"),
                checkout_group_id=_opt(row.get("checkout_group_id")),
                group_key=(
                    f"{row.get('checkout_group_id')}:{row.get('address_id')}"
                    if row.get("checkout_group_id")
                    else None
                ),
                dropoff_landmark=_opt(row.get("dropoff_landmark")),
                ready_at=_opt(row.get("ready_at")),
                deliver_together=row.get("deliver_together") is not False,
                pickup_label=_opt(row.get("pickup_label")),
                pickup_area=_opt(row.get("pickup_area")),
                multi_branch=int(row.get("pickup_branch_count") or 0) > 1,
                delivery_attempts=int(row.get("delivery_attempts") or 0),
            )
            for row in snapshot["ready_orders"]
        ],
        dispatches=[
            _dispatch_out(
                item["dispatch"],
                courier_name=item["courier_name"],
                vendor_name=item["vendor_name"],
                order_status=item["order_status"],
                delivery_zone=item["delivery_zone"],
                handover_locked=item["handover_locked"],
            )
            for item in snapshot["dispatches"]
        ],
        couriers=[_courier_out(row) for row in courier_service.list_couriers()],
        zones=[
            DeliveryZoneOut(
                zone_key=str(zone["zone_key"]),
                label=str(zone.get("label") or zone["zone_key"]),
                fee_ngwee=int(zone.get("fee_ngwee") or 0),
            )
            for zone in snapshot["zones"]
        ],
    )


@dispatch_router.get("/couriers", response_model=list[CourierOut])
def list_couriers(
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> list[CourierOut]:
    return [_courier_out(row) for row in courier_service.list_couriers()]


@dispatch_router.post("/couriers", response_model=CourierOut, status_code=201)
def create_courier(
    body: CourierIn,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> CourierOut:
    created = courier_service.create_courier(_courier_input(body))
    recorder.record(
        action="admin.dispatch.courier.create",
        entity_type="courier_partner",
        entity_id=str(created["id"]),
        before=None,
        after={"name": created["name"], "active": created["active"], "zones": created["zones"]},
    )
    return _courier_out(created)


@dispatch_router.patch("/couriers/{courier_id}", response_model=CourierOut)
def update_courier(
    courier_id: UUID,
    body: CourierIn,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> CourierOut:
    before = courier_service.get_courier(str(courier_id))
    updated = courier_service.update_courier(str(courier_id), _courier_input(body))
    recorder.record(
        action="admin.dispatch.courier.update",
        entity_type="courier_partner",
        entity_id=str(courier_id),
        before={"name": before["name"], "active": before["active"], "zones": before["zones"]},
        after={"name": updated["name"], "active": updated["active"], "zones": updated["zones"]},
    )
    return _courier_out(updated)


# ---------------------------------------------------------------------------
# Dispatch requests
# ---------------------------------------------------------------------------


@dispatch_router.post("/requests", response_model=DispatchOut, status_code=201)
def create_dispatch(
    body: CreateDispatchIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> DispatchOut:
    dispatch_service.require_courier_dispatch_enabled()
    result = dispatch_service.create_dispatch(
        order_id=body.order_id.lower(),
        courier_partner_id=body.courier_partner_id.lower(),
        actor_id=admin.id,
        note=(body.note or "").strip() or "Dispatch requested",
        direction=body.direction,
    )
    recorder.record(
        action="admin.dispatch.request.create",
        entity_type="dispatch_request",
        entity_id=result.dispatch.id,
        before=None,
        after={
            "order_id": result.dispatch.order_id,
            "courier_partner_id": result.dispatch.courier_partner_id,
            "status": result.dispatch.status.value,
            "cod_amount_ngwee": result.dispatch.cod_amount_ngwee,
            "direction": result.dispatch.direction,
            "attempt_no": result.dispatch.attempt_no,
        },
    )
    return _dispatch_out(result.dispatch, courier_name=result.courier_name)


@dispatch_router.get("/requests/{dispatch_id}", response_model=DispatchDetailOut)
def get_dispatch(
    dispatch_id: UUID,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> DispatchDetailOut:
    dispatch = _dispatch_detail_out(str(dispatch_id))
    events = [
        DispatchEventOut(
            id=str(row["id"]),
            actor=str(row["actor"]) if row.get("actor") else None,
            from_status=row.get("from_status"),
            to_status=str(row["to_status"]),
            note=row.get("note"),
            created_at=str(row["created_at"]),
        )
        for row in fetch_dispatch_events(str(dispatch_id))
    ]
    return DispatchDetailOut(dispatch=dispatch, events=events)


@dispatch_router.get("/requests/{dispatch_id}/message", response_model=MessageOut)
def get_dispatch_message(
    dispatch_id: UUID,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
) -> MessageOut:
    """Plain-text courier message for the "Copy message" (paste into WhatsApp) fallback."""
    _dispatch, courier, message = dispatch_service.build_dispatch_message(str(dispatch_id))
    return MessageOut(
        dispatch_id=str(dispatch_id),
        text=message.text,
        whatsapp_to=courier.get("contact_whatsapp_e164"),
        email_to=courier.get("contact_email"),
    )


@dispatch_router.post("/requests/{dispatch_id}/notify", response_model=NotifyOut)
def notify_courier(
    dispatch_id: UUID,
    body: NotifyIn,
    _admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> NotifyOut:
    dispatch_service.require_courier_dispatch_enabled()
    result = dispatch_service.notify_courier(
        service_client.client,
        dispatch_id=str(dispatch_id),
        channel=body.channel,
    )
    recorder.record(
        action="admin.dispatch.request.notify",
        entity_type="dispatch_request",
        entity_id=str(dispatch_id),
        before=None,
        after={
            "channel": result.channel,
            "enqueued": result.enqueued,
            "notify_count": result.notify_count,
        },
    )
    return NotifyOut(
        dispatch_id=str(dispatch_id),
        channel=result.channel,
        enqueued=result.enqueued,
        notify_count=result.notify_count,
        text=result.message.text,
    )


def _emit_shipped_best_effort(service_client: Any, dispatch_id: str) -> None:
    """Tell the customer the rider has the parcel + their handover code."""
    try:
        dispatch = fetch_dispatch(dispatch_id)
        view = dispatch_service.party_dispatch_view(dispatch.order_id, include_handover_code=True)
        owners = dispatch_service.order_owner_and_vendor(dispatch.order_id)
        if view is None or owners is None:
            return
        code = view.get("handover_code")
        tracking = f"Courier: {view.get('courier_name') or 'our rider'}."
        if code:
            tracking += f" Give the rider your handover code {code} on delivery."
        emit_order_lifecycle(
            service_client.client,
            event="order_shipped",
            order_row={
                "id": dispatch.order_id,
                "customer_id": owners[0],
                "vendor_id": owners[1],
            },
            extra={"tracking_info": tracking},
        )
    except Exception:
        logger.warning(
            "Courier pickup customer notification failed",
            extra={"dispatch_id": dispatch_id},
            exc_info=True,
        )


@dispatch_router.post("/requests/{dispatch_id}/transition", response_model=TransitionOut)
def transition_dispatch(
    dispatch_id: UUID,
    body: TransitionIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    service_client: Annotated[Any, Depends(get_supabase_client)],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> TransitionOut:
    dispatch_service.require_courier_dispatch_enabled()
    result = dispatch_service.transition_dispatch_admin(
        dispatch_id=str(dispatch_id),
        to_status=DispatchStatus(body.to_status),
        actor_id=admin.id,
        note=body.note,
        courier_reference=body.courier_reference,
        failure_reason=body.failure_reason,
        pod_photo_public_id=body.pod_photo_public_id,
        failure_code=body.failure_code,
        cod_collected_ngwee=body.cod_collected_ngwee,
        cod_collected_method=body.cod_collected_method,
    )
    recorder.record(
        action="admin.dispatch.request.transition",
        entity_type="dispatch_request",
        entity_id=str(dispatch_id),
        before={"status": result.transition.from_status.value},
        after={
            "status": result.transition.to_status.value,
            "order_status": result.order_status,
            "courier_reference": body.courier_reference,
            "failure_code": body.failure_code,
            "cod_collected_ngwee": body.cod_collected_ngwee,
        },
    )
    if result.transition.to_status is DispatchStatus.PICKED_UP:
        _emit_shipped_best_effort(service_client, str(dispatch_id))
    return TransitionOut(
        dispatch=_dispatch_detail_out(str(dispatch_id)),
        order_status=result.order_status,
    )


@dispatch_router.post("/requests/{dispatch_id}/handover", response_model=TransitionOut)
def verify_handover(
    dispatch_id: UUID,
    body: HandoverIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> TransitionOut:
    """Enter the code the rider received from the customer → delivered (single use)."""
    dispatch_service.require_courier_dispatch_enabled()
    result = dispatch_service.verify_handover_code(
        dispatch_id=str(dispatch_id),
        code=body.code,
        actor_id=admin.id,
        rate_limiter=enforce_handover_rate_limit,
    )
    # The code itself is never written to the audit log.
    recorder.record(
        action="admin.dispatch.request.handover",
        entity_type="dispatch_request",
        entity_id=str(dispatch_id),
        before={"status": DispatchStatus.PICKED_UP.value},
        after={"status": DispatchStatus.DELIVERED.value, "order_status": result.order_status},
    )
    return TransitionOut(
        dispatch=_dispatch_detail_out(str(dispatch_id)),
        order_status=result.order_status,
    )


@dispatch_router.post("/requests/{dispatch_id}/complete", response_model=TransitionOut)
def complete_dispatch(
    dispatch_id: UUID,
    body: CompleteIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> TransitionOut:
    """One action: confirm the handover code (or photo) AND record the rider's cash."""
    dispatch_service.require_courier_dispatch_enabled()
    result = dispatch_service.complete_delivery(
        dispatch_id=str(dispatch_id),
        actor_id=admin.id,
        handover_code=body.handover_code,
        pod_photo_public_id=body.pod_photo_public_id,
        cod_collected_ngwee=body.cod_collected_ngwee,
        cod_collected_method=body.cod_collected_method,
        rate_limiter=enforce_handover_rate_limit,
    )
    # The code itself is never written to the audit log.
    recorder.record(
        action="admin.dispatch.request.complete",
        entity_type="dispatch_request",
        entity_id=str(dispatch_id),
        before={"status": DispatchStatus.PICKED_UP.value},
        after={
            "status": DispatchStatus.DELIVERED.value,
            "order_status": result.order_status,
            "delivered_via": result.delivered_via,
            "cod_collected_ngwee": result.cod_collected_ngwee,
            "cod_collected_method": body.cod_collected_method,
        },
    )
    return TransitionOut(
        dispatch=_dispatch_detail_out(str(dispatch_id)),
        order_status=result.order_status,
    )


@dispatch_router.post("/requests/{dispatch_id}/returned", response_model=TransitionOut)
def acknowledge_return(
    dispatch_id: UUID,
    body: ReturnAckIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> TransitionOut:
    """The shop has the returned goods back: close the return, cancel, restock."""
    dispatch_service.require_courier_dispatch_enabled()
    result = dispatch_service.acknowledge_return(
        dispatch_id=str(dispatch_id),
        actor_id=admin.id,
        note=body.note or "",
        full_admin=_is_full_admin(admin),
    )
    recorder.record(
        action="admin.dispatch.request.returned",
        entity_type="dispatch_request",
        entity_id=str(dispatch_id),
        before={"order_status": "shipped"},
        after={"status": DispatchStatus.DELIVERED.value, "order_status": result.order_status},
    )
    return TransitionOut(
        dispatch=_dispatch_detail_out(str(dispatch_id)),
        order_status=result.order_status,
    )


@dispatch_router.patch("/requests/{dispatch_id}/cost", response_model=DispatchOut)
def record_cost(
    dispatch_id: UUID,
    body: CostIn,
    admin: Annotated[CurrentUser, Depends(require_role("admin"))],
    recorder: Annotated[AdminAuditRecorder, Depends(get_admin_audit_recorder)],
) -> DispatchOut:
    """What the courier actually charged for this job (feeds the margin report)."""
    before = fetch_dispatch(str(dispatch_id))
    updated = dispatch_service.record_actual_cost(
        dispatch_id=str(dispatch_id), cost_ngwee=body.actual_cost_ngwee, actor_id=admin.id
    )
    recorder.record(
        action="admin.dispatch.request.cost",
        entity_type="dispatch_request",
        entity_id=str(dispatch_id),
        before={"actual_cost_ngwee": before.actual_cost_ngwee},
        after={"actual_cost_ngwee": updated.actual_cost_ngwee},
    )
    return _dispatch_detail_out(str(dispatch_id))


admin_router.include_router(dispatch_router)
