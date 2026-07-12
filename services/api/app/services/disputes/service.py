"""Dispute lifecycle service — open, respond, escalate, resolve with M08 ledger dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from app.errors import AppError
from app.services.disputes.state import (
    TERMINAL_STATUSES,
    ActorRole,
    DisputeEvent,
    DisputeStatus,
    DisputeTransitionError,
    ServiceRoleClient,
    load_dispute_by_order,
    load_dispute_snapshot,
    resolve_transition,
    transition_dispute,
    write_dispute_audit_log,
)
from app.services.escrow.release import evaluate_and_release
from app.services.refunds.config import load_restocking_fee_bps
from app.services.refunds.execute import execute_refund
from app.services.refunds.math import compute_lane2_refund, restocking_fee_ngwee

CustomerRail = Literal["mtn", "airtel", "zamtel"]
ResolveDecision = Literal["resolved_refund", "resolved_release", "resolved_partial"]


@dataclass(frozen=True, slots=True)
class DisputeRecord:
    id: str
    order_id: str
    opener_user_id: str
    status: str
    evidence_paths: list[str]
    vendor_response: str | None
    admin_decision: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class OpenDisputeResult:
    dispute_id: str
    order_id: str
    status: str
    created: bool


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return [cast(dict[str, Any], row) for row in data if isinstance(row, dict)]
    return []


def _single_row(response: Any) -> dict[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return cast(dict[str, Any], data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return cast(dict[str, Any], first)
    return None


def _serialize_dispute(row: dict[str, Any]) -> DisputeRecord:
    evidence = row.get("evidence_paths")
    paths = [str(path) for path in evidence] if isinstance(evidence, list) else []
    return DisputeRecord(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        opener_user_id=str(row["opener_user_id"]),
        status=str(row["status"]),
        evidence_paths=paths,
        vendor_response=(
            str(row["vendor_response"]) if row.get("vendor_response") is not None else None
        ),
        admin_decision=(
            str(row["admin_decision"]) if row.get("admin_decision") is not None else None
        ),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


def _load_dispute_row(service_client: ServiceRoleClient, dispute_id: str) -> DisputeRecord:
    response = (
        service_client.client.table("disputes")
        .select(
            "id, order_id, opener_user_id, status, evidence_paths, "
            "vendor_response, admin_decision, created_at, updated_at"
        )
        .eq("id", dispute_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)
    return _serialize_dispute(row)


def _load_order_row(service_client: ServiceRoleClient, order_id: str) -> dict[str, Any]:
    response = (
        service_client.client.table("orders")
        .select("id, customer_id, vendor_id, status")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    return row


def _assert_customer_owns_order(order_row: dict[str, Any], customer_id: str) -> None:
    if str(order_row.get("customer_id")) != customer_id:
        raise AppError(code="not_found", message="Order not found", http_status=404)


def _assert_vendor_owns_order(order_row: dict[str, Any], vendor_id: str) -> None:
    if str(order_row.get("vendor_id")) != vendor_id:
        raise AppError(code="not_found", message="Order not found", http_status=404)


def _order_item_total_ngwee(service_client: ServiceRoleClient, order_id: str) -> int:
    response = (
        service_client.client.table("order_items")
        .select("qty, unit_price_ngwee")
        .eq("order_id", order_id)
        .execute()
    )
    total = 0
    for row in _rows(response):
        qty = row.get("qty", 0)
        unit = row.get("unit_price_ngwee", 0)
        if isinstance(qty, int) and isinstance(unit, int):
            total += qty * unit
    return total


def _lane2_return_transport_for_partial(
    service_client: ServiceRoleClient,
    *,
    order_id: str,
    partial_refund_ngwee: int,
) -> int:
    response = (
        service_client.client.table("orders")
        .select("delivery_fee_ngwee")
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    delivery_row = _single_row(response)
    if delivery_row is None:
        raise AppError(code="not_found", message="Order not found", http_status=404)

    item_total = _order_item_total_ngwee(service_client, order_id)
    delivery_fee = int(delivery_row.get("delivery_fee_ngwee", 0))

    restocking_bps = load_restocking_fee_bps(service_client)
    restocking = restocking_fee_ngwee(item_ngwee=item_total, restocking_fee_bps=restocking_bps)
    outbound = max(0, delivery_fee)
    return_transport = item_total - outbound - restocking - partial_refund_ngwee
    if return_transport < 0:
        raise AppError(
            code="validation_error",
            message="Partial refund amount exceeds refundable balance",
            http_status=422,
            details={
                "partial_refund_ngwee": partial_refund_ngwee,
                "item_ngwee": item_total,
                "delivery_fee_ngwee": outbound,
                "restocking_fee_ngwee": restocking,
            },
        )

    preview = compute_lane2_refund(
        item_ngwee=item_total,
        outbound_delivery_ngwee=outbound,
        return_transport_ngwee=return_transport,
        restocking_fee_bps=restocking_bps,
    )
    if preview.refund_ngwee != partial_refund_ngwee:
        raise AppError(
            code="validation_error",
            message="Could not compute lane-2 partial refund split",
            http_status=422,
        )
    return return_transport


def open_dispute(
    service_client: ServiceRoleClient,
    *,
    order_id: str,
    opener_user_id: str,
    evidence_paths: list[str] | None = None,
    note: str = "Customer opened dispute",
) -> OpenDisputeResult:
    """Open a dispute for an order; idempotent when a non-terminal dispute already exists."""
    order_row = _load_order_row(service_client, order_id)
    _assert_customer_owns_order(order_row, opener_user_id)

    existing = load_dispute_by_order(service_client, order_id)
    if existing is not None and existing.status.value not in TERMINAL_STATUSES:
        return OpenDisputeResult(
            dispute_id=existing.id,
            order_id=order_id,
            status=existing.status.value,
            created=False,
        )

    paths = list(evidence_paths or [])
    insert_row = {
        "order_id": order_id,
        "opener_user_id": opener_user_id,
        "evidence_paths": paths,
        "status": DisputeStatus.OPEN.value,
    }
    response = service_client.client.table("disputes").insert(insert_row).execute()
    row = _single_row(response)
    if row is None:
        rows = _rows(response)
        row = rows[0] if rows else None
    if row is None or not row.get("id"):
        raise AppError(
            code="internal_error",
            message="Could not create dispute",
            http_status=500,
        )

    dispute_id = str(row["id"])
    write_dispute_audit_log(
        service_client,
        actor_id=opener_user_id,
        dispute_id=dispute_id,
        from_status="",
        to_status=DisputeStatus.OPEN.value,
        note=note,
    )
    return OpenDisputeResult(
        dispute_id=dispute_id,
        order_id=order_id,
        status=DisputeStatus.OPEN.value,
        created=True,
    )


def vendor_respond(
    service_client: ServiceRoleClient,
    *,
    dispute_id: str,
    vendor_id: str,
    vendor_user_id: str,
    response_text: str,
    evidence_paths: list[str] | None = None,
) -> DisputeRecord:
    snapshot = load_dispute_snapshot(service_client, dispute_id)
    if snapshot is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)

    order_row = _load_order_row(service_client, snapshot.order_id)
    _assert_vendor_owns_order(order_row, vendor_id)

    current = _load_dispute_row(service_client, dispute_id)
    merged_paths = list(current.evidence_paths)
    for path in evidence_paths or []:
        if path not in merged_paths:
            merged_paths.append(path)

    transition_dispute(
        service_client,
        dispute_id=dispute_id,
        event=DisputeEvent.VENDOR_RESPOND,
        actor_role=ActorRole.VENDOR,
        actor_id=vendor_user_id,
        note="Vendor submitted dispute response",
        extra_updates={
            "vendor_response": response_text,
            "evidence_paths": merged_paths,
        },
    )
    return _load_dispute_row(service_client, dispute_id)


def escalate_to_review(
    service_client: ServiceRoleClient,
    *,
    dispute_id: str,
    admin_user_id: str,
    note: str,
) -> DisputeRecord:
    transition_dispute(
        service_client,
        dispute_id=dispute_id,
        event=DisputeEvent.ESCALATE,
        actor_role=ActorRole.ADMIN,
        actor_id=admin_user_id,
        note=note,
    )
    return _load_dispute_row(service_client, dispute_id)


def resolve(
    service_client: ServiceRoleClient,
    *,
    dispute_id: str,
    admin_user_id: str,
    decision: ResolveDecision,
    admin_decision: str,
    customer_momo: str,
    customer_rail: CustomerRail = "mtn",
    partial_refund_ngwee: int | None = None,
) -> DisputeRecord:
    """Resolve a dispute and dispatch the matching M08 ledger outcome."""
    snapshot = load_dispute_snapshot(service_client, dispute_id)
    if snapshot is None:
        raise AppError(code="not_found", message="Dispute not found", http_status=404)

    event_map: dict[ResolveDecision, DisputeEvent] = {
        "resolved_refund": DisputeEvent.RESOLVE_REFUND,
        "resolved_release": DisputeEvent.RESOLVE_RELEASE,
        "resolved_partial": DisputeEvent.RESOLVE_PARTIAL,
    }
    event = event_map[decision]

    if decision == "resolved_partial":
        if partial_refund_ngwee is None or partial_refund_ngwee <= 0:
            raise AppError(
                code="validation_error",
                message="partial_refund_ngwee is required for partial resolution",
                http_status=422,
            )

    # Move money BEFORE committing the terminal status, so a thrown refund/release
    # leaves the dispute in `under_review` and re-drivable — not stuck resolved-but-
    # unpaid. Pre-check the guard here (transition_dispute re-checks + optimistic-locks
    # on commit); execute_refund threads this idempotency_key into post_transaction +
    # the payout reference and is backstopped by the refunds(order_id) partial unique
    # index (0032), so a retry collapses to one ledger drain + one payout.
    if (
        resolve_transition(
            from_status=snapshot.status, event=event, actor_role=ActorRole.ADMIN
        )
        is None
    ):
        raise DisputeTransitionError(
            "Dispute cannot be resolved from its current state",
            from_status=snapshot.status.value,
            event=event.value,
            actor_role=ActorRole.ADMIN.value,
        )

    order_id = snapshot.order_id
    if decision == "resolved_refund":
        execute_refund(
            service_client=service_client,
            order_id=order_id,
            lane=1,
            customer_rail=customer_rail,
            customer_momo=customer_momo,
            dispute_id=dispute_id,
            idempotency_key=f"dispute-{dispute_id}-refund",
        )
    elif decision == "resolved_release":
        evaluate_and_release(service_client, order_id)
    else:
        return_transport = _lane2_return_transport_for_partial(
            service_client,
            order_id=order_id,
            partial_refund_ngwee=partial_refund_ngwee or 0,
        )
        refund_result = execute_refund(
            service_client=service_client,
            order_id=order_id,
            lane=2,
            return_transport_ngwee=return_transport,
            customer_rail=customer_rail,
            customer_momo=customer_momo,
            dispute_id=dispute_id,
            idempotency_key=f"dispute-{dispute_id}-partial",
        )
        # Close the TOCTOU: execute_refund re-reads item/delivery/bps independently of
        # the back-solve snapshot. Assert the executed amount is exactly the admin
        # decision before committing the resolution (still re-drivable if this raises).
        if refund_result.amount_ngwee != partial_refund_ngwee:
            raise AppError(
                code="partial_refund_amount_drift",
                message="Executed partial refund did not match the decided amount",
                http_status=409,
                details={
                    "decided_ngwee": partial_refund_ngwee,
                    "executed_ngwee": refund_result.amount_ngwee,
                },
            )
        evaluate_and_release(service_client, order_id)

    transition_dispute(
        service_client,
        dispute_id=dispute_id,
        event=event,
        actor_role=ActorRole.ADMIN,
        actor_id=admin_user_id,
        note=admin_decision,
        extra_updates={"admin_decision": admin_decision},
    )

    return _load_dispute_row(service_client, dispute_id)


def get_dispute_for_party(
    service_client: ServiceRoleClient,
    *,
    dispute_id: str,
    user_id: str,
    is_admin: bool,
    vendor_id: str | None = None,
) -> DisputeRecord:
    record = _load_dispute_row(service_client, dispute_id)
    if is_admin:
        return record

    order_row = _load_order_row(service_client, record.order_id)
    customer_id = str(order_row.get("customer_id"))
    order_vendor_id = str(order_row.get("vendor_id"))

    if user_id == customer_id:
        return record
    if vendor_id is not None and vendor_id == order_vendor_id:
        return record

    raise AppError(code="not_found", message="Dispute not found", http_status=404)


def list_vendor_disputes(
    service_client: ServiceRoleClient,
    *,
    vendor_id: str,
) -> list[DisputeRecord]:
    orders_response = (
        service_client.client.table("orders")
        .select("id")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    order_ids = [str(row["id"]) for row in _rows(orders_response)]
    if not order_ids:
        return []

    response = (
        service_client.client.table("disputes")
        .select(
            "id, order_id, opener_user_id, status, evidence_paths, "
            "vendor_response, admin_decision, created_at, updated_at"
        )
        .in_("order_id", order_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return [_serialize_dispute(row) for row in _rows(response)]
