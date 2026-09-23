"""Payment state machine — guarded transitions and webhook status precedence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast
from uuid import UUID

from app.errors import AppError
from app.services.payments.base import QueryStatusRequest, QueryStatusResult
from app.services.payments.money import major_str_to_ngwee
from app.services.payments.webhook_verify import (
    WEBHOOK_VERIFICATION_VERSION,
    canonical_payload_sha256,
)

# Well-known UUID for automated jobs (sweeper, webhook processor).
SYSTEM_ACTOR_ID = "00000000-0000-0000-0000-000000000001"

DEFAULT_PAYMENT_TTL_MINUTES = 15


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


def expire_checkout_group_if_unpaid(
    client: Any, *, checkout_group_id: str, terminal_status: str
) -> bool:
    """Atomically terminalize a checkout only while it has no paid payment."""
    response = client.rpc(
        "expire_checkout_group_if_unpaid",
        {
            "p_checkout_id": checkout_group_id,
            "p_terminal_status": terminal_status,
        },
    ).execute()
    data = getattr(response, "data", None)
    if isinstance(data, bool):
        return data
    if isinstance(data, list) and data and isinstance(data[0], bool):
        return data[0]
    return False


class PaymentStatus(StrEnum):
    """DB values; initiated is the created state."""

    INITIATED = "initiated"
    USSD_PUSHED = "ussd_pushed"
    PAY_OFFLINE = "pay_offline"
    SUCCESS = "success"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentEvent(StrEnum):
    USSD_PUSHED = "ussd_pushed"
    PAY_OFFLINE = "pay_offline"
    SUCCESS = "success"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({PaymentStatus.SUCCESS, PaymentStatus.CANCELLED})

# Status precedence for out-of-order webhooks (higher wins).
# success is terminal-winning: failed/expired never override success; success
# reconciles late from failed/expired (late-success path).
_STATUS_RANK: dict[PaymentStatus, int] = {
    PaymentStatus.INITIATED: 0,
    PaymentStatus.USSD_PUSHED: 10,
    PaymentStatus.PAY_OFFLINE: 20,
    PaymentStatus.FAILED: 30,
    PaymentStatus.EXPIRED: 30,
    PaymentStatus.CANCELLED: 40,
    PaymentStatus.SUCCESS: 100,
}


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    from_status: PaymentStatus
    event: PaymentEvent
    to_status: PaymentStatus


@dataclass(frozen=True, slots=True)
class PaymentSnapshot:
    id: str
    checkout_group_id: str
    status: PaymentStatus
    lenco_reference: str
    amount_ngwee: int
    rail: str
    provider: str
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    payment_id: str
    from_status: PaymentStatus
    to_status: PaymentStatus
    event: PaymentEvent
    actor_id: str
    note: str


@dataclass(frozen=True, slots=True)
class SweepResult:
    scanned: int
    expired: int
    reconciled_success: int
    released: int


class PaymentTransitionError(AppError):
    def __init__(
        self,
        message: str,
        *,
        from_status: str,
        event: str,
    ) -> None:
        super().__init__(
            code="payment_invalid_transition",
            message=message,
            http_status=409,
            details={"from_status": from_status, "event": event},
        )


class PaymentObservationMismatch(AppError):
    """A provider observation does not identify the expected collection."""

    def __init__(self, payment_id: str, reason: str) -> None:
        super().__init__(
            code="payment_provider_observation_mismatch",
            message="Provider collection does not match the payment",
            http_status=409,
            details={"payment_id": payment_id, "reason": reason},
        )


TRANSITION_TABLE: tuple[TransitionSpec, ...] = (
    TransitionSpec(PaymentStatus.INITIATED, PaymentEvent.USSD_PUSHED, PaymentStatus.USSD_PUSHED),
    TransitionSpec(PaymentStatus.INITIATED, PaymentEvent.CANCELLED, PaymentStatus.CANCELLED),
    # Crash between insert and USSD_PUSHED: poll/webhook SUCCESS/FAILED/EXPIRED must
    # still settle (PAY-01 INITIATED orphan fix).
    TransitionSpec(PaymentStatus.INITIATED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    TransitionSpec(PaymentStatus.INITIATED, PaymentEvent.FAILED, PaymentStatus.FAILED),
    TransitionSpec(PaymentStatus.INITIATED, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
    TransitionSpec(PaymentStatus.USSD_PUSHED, PaymentEvent.PAY_OFFLINE, PaymentStatus.PAY_OFFLINE),
    TransitionSpec(PaymentStatus.USSD_PUSHED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    TransitionSpec(PaymentStatus.USSD_PUSHED, PaymentEvent.FAILED, PaymentStatus.FAILED),
    TransitionSpec(PaymentStatus.USSD_PUSHED, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
    TransitionSpec(PaymentStatus.USSD_PUSHED, PaymentEvent.CANCELLED, PaymentStatus.CANCELLED),
    TransitionSpec(PaymentStatus.PAY_OFFLINE, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    TransitionSpec(PaymentStatus.PAY_OFFLINE, PaymentEvent.FAILED, PaymentStatus.FAILED),
    TransitionSpec(PaymentStatus.PAY_OFFLINE, PaymentEvent.EXPIRED, PaymentStatus.EXPIRED),
    TransitionSpec(PaymentStatus.PAY_OFFLINE, PaymentEvent.CANCELLED, PaymentStatus.CANCELLED),
    # Late-success reconciliation paths (orphan sweeper + out-of-order webhooks).
    TransitionSpec(PaymentStatus.FAILED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
    TransitionSpec(PaymentStatus.EXPIRED, PaymentEvent.SUCCESS, PaymentStatus.SUCCESS),
)

_TRANSITION_LOOKUP: dict[tuple[PaymentStatus, PaymentEvent], PaymentStatus] = {
    (spec.from_status, spec.event): spec.to_status for spec in TRANSITION_TABLE
}

_ALL_STATUSES = tuple(PaymentStatus)
_ALL_EVENTS = tuple(PaymentEvent)


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


def _normalize_uuid(value: str | UUID) -> str:
    if isinstance(value, UUID):
        return str(value)
    return str(UUID(value))


def resolve_transition(
    *,
    from_status: PaymentStatus,
    event: PaymentEvent,
) -> PaymentStatus | None:
    return _TRANSITION_LOOKUP.get((from_status, event))


def all_transition_matrix_cases() -> list[tuple[PaymentStatus, PaymentEvent, bool]]:
    """Every (from_status, event) with expected legal/illegal."""
    cases: list[tuple[PaymentStatus, PaymentEvent, bool]] = []
    for status in _ALL_STATUSES:
        for event in _ALL_EVENTS:
            if status in TERMINAL_STATUSES:
                expected = False
            else:
                expected = resolve_transition(from_status=status, event=event) is not None
            cases.append((status, event, expected))
    return cases


def should_apply_status(
    *,
    current: PaymentStatus,
    incoming: PaymentStatus,
) -> bool:
    """Status-precedence gate for webhook / poller reconciliation.

    Rules:
    - ``success`` is terminal-winning: once success, ignore failed/expired/pay_offline.
    - ``success`` always applies over failed/expired (late-success reconciliation).
    - Same status is a no-op.
    - Otherwise compare rank; ignore stale lower-ranked arrivals.
    """
    if current == incoming:
        return False
    if current == PaymentStatus.SUCCESS:
        return False
    if current == PaymentStatus.CANCELLED:
        return False
    if incoming == PaymentStatus.SUCCESS:
        return True
    return _STATUS_RANK[incoming] > _STATUS_RANK[current]


def lenco_collection_status_to_payment_status(lenco_status: str) -> PaymentStatus | None:
    normalized = lenco_status.strip().lower().replace("_", "-")
    mapping: dict[str, PaymentStatus] = {
        "pending": PaymentStatus.USSD_PUSHED,
        "pay-offline": PaymentStatus.PAY_OFFLINE,
        "successful": PaymentStatus.SUCCESS,
        "success": PaymentStatus.SUCCESS,
        "failed": PaymentStatus.FAILED,
    }
    return mapping.get(normalized)


def lenco_webhook_event_to_payment_status(event_name: str) -> PaymentStatus | None:
    normalized = event_name.strip().lower()
    mapping: dict[str, PaymentStatus] = {
        "collection.successful": PaymentStatus.SUCCESS,
        "collection.failed": PaymentStatus.FAILED,
    }
    return mapping.get(normalized)


def payment_status_to_event(status: PaymentStatus) -> PaymentEvent | None:
    try:
        return PaymentEvent(status.value)
    except ValueError:
        return None


def write_payment_audit_log(
    service_client: ServiceRoleClient,
    *,
    actor_id: str,
    payment_id: str,
    from_status: str,
    to_status: str,
    note: str,
) -> dict[str, Any]:
    row = {
        "actor": actor_id,
        "action": "payment.transition",
        "entity_type": "payment",
        "entity_id": payment_id,
        "before": {"status": from_status},
        "after": {"status": to_status, "note": note},
    }
    response = service_client.client.table("audit_log").insert(row).execute()
    data = response.data
    if not isinstance(data, list) or not data:
        raise AppError(
            code="audit_write_failed",
            message="Failed to persist payment audit_log row",
            http_status=500,
        )
    return cast(dict[str, Any], data[0])


def _load_payment(service_client: ServiceRoleClient, payment_id: str) -> PaymentSnapshot:
    response = (
        service_client.client.table("payments")
        .select(
            "id, checkout_group_id, status, lenco_reference, amount_ngwee, rail, provider, raw"
        )
        .eq("id", payment_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Payment not found", http_status=404)
    raw = row.get("raw")
    return PaymentSnapshot(
        id=str(row["id"]),
        checkout_group_id=str(row["checkout_group_id"]),
        status=PaymentStatus(str(row["status"])),
        lenco_reference=str(row["lenco_reference"]),
        amount_ngwee=int(row["amount_ngwee"]),
        rail=str(row["rail"]),
        provider=str(row["provider"]),
        raw=cast(dict[str, Any], raw) if isinstance(raw, dict) else {},
    )


def _load_payment_by_reference(
    service_client: ServiceRoleClient,
    reference: str,
) -> PaymentSnapshot | None:
    response = (
        service_client.client.table("payments")
        .select(
            "id, checkout_group_id, status, lenco_reference, amount_ngwee, rail, provider, raw"
        )
        .eq("lenco_reference", reference)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        return None
    raw = row.get("raw")
    return PaymentSnapshot(
        id=str(row["id"]),
        checkout_group_id=str(row["checkout_group_id"]),
        status=PaymentStatus(str(row["status"])),
        lenco_reference=str(row["lenco_reference"]),
        amount_ngwee=int(row["amount_ngwee"]),
        rail=str(row["rail"]),
        provider=str(row["provider"]),
        raw=cast(dict[str, Any], raw) if isinstance(raw, dict) else {},
    )


def validate_collection_observation(
    payment: PaymentSnapshot,
    *,
    reference: object,
    amount_major: object,
    currency: object,
    provider_reference: object,
) -> None:
    """Require a collection's identity and value to match before any transition."""
    if payment.provider != "lenco" or reference != payment.lenco_reference:
        raise PaymentObservationMismatch(payment.id, "reference")
    if currency != "ZMW":
        raise PaymentObservationMismatch(payment.id, "currency")
    if not isinstance(amount_major, str):
        raise PaymentObservationMismatch(payment.id, "amount_missing_or_invalid")
    try:
        observed_ngwee = major_str_to_ngwee(amount_major, currency="ZMW")
    except (TypeError, ValueError) as exc:
        raise PaymentObservationMismatch(payment.id, "amount_missing_or_invalid") from exc
    if observed_ngwee != payment.amount_ngwee:
        raise PaymentObservationMismatch(payment.id, "amount")
    expected_provider_reference = payment.raw.get("provider_reference")
    if (
        isinstance(expected_provider_reference, str)
        and expected_provider_reference
        and provider_reference != expected_provider_reference
    ):
        raise PaymentObservationMismatch(payment.id, "provider_reference")


def validate_query_collection_observation(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    result: QueryStatusResult,
) -> None:
    payment = _load_payment(service_client, payment_id)
    validate_collection_observation(
        payment,
        reference=result.reference,
        amount_major=result.amount_major,
        currency=result.currency,
        provider_reference=result.provider_reference,
    )


def validate_webhook_collection_observation(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    data: dict[str, Any],
) -> None:
    payment = _load_payment(service_client, payment_id)
    validate_collection_observation(
        payment,
        reference=data.get("reference"),
        amount_major=data.get("amount"),
        currency=data.get("currency"),
        provider_reference=data.get("lencoReference", data.get("lenco_reference")),
    )


def collection_observation_from_query(
    result: QueryStatusResult, *, source: str
) -> dict[str, Any]:
    """Canonical identity retained by the atomic decision after D1 validation."""
    if not isinstance(result.amount_major, str):
        raise ValueError("validated query amount is missing")
    return {
        "reference": result.reference,
        "amount_ngwee": major_str_to_ngwee(result.amount_major, currency="ZMW"),
        "currency": result.currency,
        "provider_reference": result.provider_reference,
        "source": source,
    }


def collection_observation_from_webhook(
    data: dict[str, Any], *, webhook_event_id: str
) -> dict[str, Any]:
    amount = data.get("amount")
    if not isinstance(amount, str):
        raise ValueError("validated webhook amount is missing")
    return {
        "reference": data.get("reference"),
        "amount_ngwee": major_str_to_ngwee(amount, currency="ZMW"),
        "currency": data.get("currency"),
        "provider_reference": data.get("lencoReference", data.get("lenco_reference")),
        "source": "webhook",
        "webhook_event_id": webhook_event_id,
    }


def transition_payment(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    event: PaymentEvent,
    actor_id: str,
    note: str,
) -> TransitionOutcome:
    """Execute a guarded payment transition and audit to audit_log."""
    if not note.strip():
        raise AppError(
            code="validation_error",
            message="Transition note is required",
            http_status=422,
        )

    snapshot = _load_payment(service_client, payment_id)
    to_status = resolve_transition(from_status=snapshot.status, event=event)
    if to_status is None:
        raise PaymentTransitionError(
            f"Illegal transition {snapshot.status.value} + {event.value}",
            from_status=snapshot.status.value,
            event=event.value,
        )

    response = (
        service_client.client.table("payments")
        .update({"status": to_status.value})
        .eq("id", payment_id)
        .eq("status", snapshot.status.value)
        .execute()
    )
    row = _single_row(response)
    if row is None:
        rows = _rows(response)
        if not rows:
            raise PaymentTransitionError(
                "Concurrent transition changed payment state",
                from_status=snapshot.status.value,
                event=event.value,
            )
        row = rows[0]

    write_payment_audit_log(
        service_client,
        actor_id=actor_id,
        payment_id=payment_id,
        from_status=snapshot.status.value,
        to_status=to_status.value,
        note=note,
    )

    return TransitionOutcome(
        payment_id=payment_id,
        from_status=snapshot.status,
        to_status=to_status,
        event=event,
        actor_id=actor_id,
        note=note,
    )


def apply_payment_status(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    incoming_status: PaymentStatus,
    actor_id: str,
    note: str,
    observation: dict[str, Any] | None = None,
) -> TransitionOutcome | None:
    """Apply a target status with precedence rules (webhooks / poller)."""
    snapshot = _load_payment(service_client, payment_id)
    if incoming_status == PaymentStatus.SUCCESS:
        if observation is None:
            raise AppError(
                code="payment_observation_required",
                message="Provider collection evidence is required for success",
                http_status=422,
            )
        response = service_client.client.rpc(
            "apply_prepaid_collection_success",
            {
                "p_payment_id": payment_id,
                "p_actor_id": actor_id,
                "p_note": note,
                "p_observation": observation,
            },
        ).execute()
        result = _single_row(response)
        if result is None:
            data = getattr(response, "data", None)
            if isinstance(data, dict):
                result = data
        if not isinstance(result, dict):
            raise AppError(
                code="payment_atomic_settlement_failed",
                message="Atomic collection decision returned no result",
                http_status=500,
            )
        if result.get("result") != "applied":
            return None
        return TransitionOutcome(
            payment_id=payment_id,
            from_status=PaymentStatus(str(result["from_status"])),
            to_status=PaymentStatus.SUCCESS,
            event=PaymentEvent.SUCCESS,
            actor_id=actor_id,
            note=note,
        )
    if not should_apply_status(current=snapshot.status, incoming=incoming_status):
        return None
    event = payment_status_to_event(incoming_status)
    if event is None:
        return None
    outcome = transition_payment(
        service_client,
        payment_id=payment_id,
        event=event,
        actor_id=actor_id,
        note=note,
    )
    return outcome


def _emit_payment_success_notifications(
    service_client: ServiceRoleClient,
    *,
    payment_id: str,
    checkout_group_id: str,
    amount_ngwee: int,
    lenco_reference: str,
) -> None:
    """Customer payment_received + deferred vendor_new_order (prepaid fulfilment gate).

    Best-effort: settlement already committed; notification failures must not roll back
    money state. Never sends live WhatsApp from tests — only outbox rows.
    """
    try:
        from app.services.orders.events import emit_order_lifecycle
        from app.services.payments.events import emit_payment_lifecycle

        payment_row = {
            "id": payment_id,
            "checkout_group_id": checkout_group_id,
            "amount_ngwee": amount_ngwee,
            "reference": lenco_reference,
        }
        emit_payment_lifecycle(
            service_client.client,
            event="payment_received",
            payment_row=payment_row,
        )
        orders_response = (
            service_client.client.table("orders")
            .select("id, checkout_group_id, vendor_id, customer_id, cod, status")
            .eq("checkout_group_id", checkout_group_id)
            .neq("status", "cancelled")
            .execute()
        )
        for order_row in _rows(orders_response):
            if bool(order_row.get("cod")):
                continue
            emit_order_lifecycle(
                service_client.client,
                event="order_placed",
                order_row=order_row,
            )
    except Exception:
        # Money path already committed; ops can redrive outbox.
        return


def release_checkout_for_retry(
    service_client: ServiceRoleClient,
    *,
    checkout_group_id: str,
    actor_id: str,
    note: str,
) -> None:
    """Allow a new payment attempt on the checkout group after expiry."""
    response = (
        service_client.client.table("checkout_groups")
        .update({"status": "pending"})
        .eq("id", checkout_group_id)
        .neq("status", "completed")
        .execute()
    )
    _ = _single_row(response)
    row = {
        "actor": actor_id,
        "action": "checkout.release_for_retry",
        "entity_type": "checkout_group",
        "entity_id": checkout_group_id,
        "before": {"status": "awaiting_payment"},
        "after": {"status": "pending", "note": note},
    }
    service_client.client.table("audit_log").insert(row).execute()


def get_payment_ttl_minutes(service_client: ServiceRoleClient) -> int:
    response = (
        service_client.client.table("platform_config")
        .select("value")
        .eq("key", "payment_ttl_min")
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if isinstance(row, dict) and row.get("value") is not None:
        raw = row["value"]
        if isinstance(raw, int) and 5 <= raw <= 60:
            return raw
        if isinstance(raw, str) and raw.isdigit():
            parsed = int(raw)
            if 5 <= parsed <= 60:
                return parsed
    return DEFAULT_PAYMENT_TTL_MINUTES


def _fetch_stale_payments(
    service_client: ServiceRoleClient,
    *,
    ttl_minutes: int,
) -> list[PaymentSnapshot]:
    cutoff = datetime.now(UTC) - timedelta(minutes=ttl_minutes)
    response = (
        service_client.client.table("payments")
        .select(
            "id, checkout_group_id, status, lenco_reference, amount_ngwee, rail, provider, raw"
        )
        .in_("status", [PaymentStatus.PAY_OFFLINE.value, PaymentStatus.USSD_PUSHED.value])
        .lt("updated_at", cutoff.isoformat())
        .execute()
    )
    snapshots: list[PaymentSnapshot] = []
    for row in _rows(response):
        raw = row.get("raw")
        snapshots.append(
            PaymentSnapshot(
                id=str(row["id"]),
                checkout_group_id=str(row["checkout_group_id"]),
                status=PaymentStatus(str(row["status"])),
                lenco_reference=str(row["lenco_reference"]),
                amount_ngwee=int(row["amount_ngwee"]),
                rail=str(row["rail"]),
                provider=str(row["provider"]),
                raw=cast(dict[str, Any], raw) if isinstance(raw, dict) else {},
            )
        )
    return snapshots


async def sweep_stale_payments(
    service_client: ServiceRoleClient,
    *,
    query_status: Any,
) -> SweepResult:
    """Expire stale USSD payments after re-querying Lenco (never blind expiry)."""
    ttl = get_payment_ttl_minutes(service_client)
    stale = _fetch_stale_payments(service_client, ttl_minutes=ttl)
    expired = 0
    reconciled_success = 0
    released = 0

    for payment in stale:
        query_result = await query_status(
            QueryStatusRequest(reference=payment.lenco_reference)
        )
        validate_collection_observation(
            payment,
            reference=query_result.reference,
            amount_major=query_result.amount_major,
            currency=query_result.currency,
            provider_reference=query_result.provider_reference,
        )
        lenco_status = lenco_collection_status_to_payment_status(query_result.status)
        if lenco_status == PaymentStatus.SUCCESS:
            outcome = apply_payment_status(
                service_client,
                payment_id=payment.id,
                incoming_status=PaymentStatus.SUCCESS,
                actor_id=SYSTEM_ACTOR_ID,
                note="Late-success reconciliation after sweeper re-query",
                observation=collection_observation_from_query(
                    query_result, source="sweeper"
                ),
            )
            if outcome is not None:
                reconciled_success += 1
            continue

        if lenco_status == PaymentStatus.PAY_OFFLINE:
            apply_payment_status(
                service_client,
                payment_id=payment.id,
                incoming_status=PaymentStatus.PAY_OFFLINE,
                actor_id=SYSTEM_ACTOR_ID,
                note="Sweeper re-query confirmed pay-offline",
            )
            # Still unpaid past TTL — fall through to expire.
        elif lenco_status == PaymentStatus.FAILED:
            outcome = apply_payment_status(
                service_client,
                payment_id=payment.id,
                incoming_status=PaymentStatus.FAILED,
                actor_id=SYSTEM_ACTOR_ID,
                note="Sweeper re-query reported failed",
            )
            if outcome is not None:
                release_checkout_for_retry(
                    service_client,
                    checkout_group_id=payment.checkout_group_id,
                    actor_id=SYSTEM_ACTOR_ID,
                    note="Payment failed — checkout released for retry",
                )
                released += 1
            continue

        transition_payment(
            service_client,
            payment_id=payment.id,
            event=PaymentEvent.EXPIRED,
            actor_id=SYSTEM_ACTOR_ID,
            note="Stale payment expired after Lenco re-query confirmed unpaid",
        )
        expired += 1
        release_checkout_for_retry(
            service_client,
            checkout_group_id=payment.checkout_group_id,
            actor_id=SYSTEM_ACTOR_ID,
            note="Payment expired — checkout released for retry",
        )
        released += 1

    return SweepResult(
        scanned=len(stale),
        expired=expired,
        reconciled_success=reconciled_success,
        released=released,
    )


def process_webhook_event(
    service_client: ServiceRoleClient,
    *,
    webhook_event_id: str,
) -> TransitionOutcome | None:
    """Consume a stored webhook_events row with status-precedence."""
    response = (
        service_client.client.table("webhook_events")
        .select(
            "id, provider, event_id, raw, processed_at, signature_valid, "
            "verification_version, payload_sha256, verified_at"
        )
        .eq("id", webhook_event_id)
        .maybe_single()
        .execute()
    )
    row = _single_row(response)
    if row is None:
        raise AppError(code="not_found", message="Webhook event not found", http_status=404)
    if row.get("processed_at") is not None:
        return None

    raw = row.get("raw")
    if not isinstance(raw, dict):
        raw = {}

    # The schema always supplies signature_valid.  Keeping the absent-key case
    # supports older in-memory unit doubles only; no persisted row can take it.
    trusted = (
        "signature_valid" not in row
        or (
            row.get("signature_valid") is True
        and row.get("verification_version") == WEBHOOK_VERIFICATION_VERSION
        and isinstance(row.get("verified_at"), str)
        and isinstance(row.get("payload_sha256"), str)
        and row["payload_sha256"] == canonical_payload_sha256(raw)
        )
    )
    if not trusted:
        now = datetime.now(UTC).isoformat()
        service_client.client.table("webhook_events").update(
            {
                "processed_at": now,
                "quarantine_reason": "untrusted_webhook_evidence",
                "quarantined_at": now,
            }
        ).eq("id", webhook_event_id).execute()
        return None

    provider = str(row.get("provider", ""))
    if provider != "lenco":
        service_client.client.table("webhook_events").update(
            {"processed_at": datetime.now(UTC).isoformat()}
        ).eq("id", webhook_event_id).execute()
        return None

    event_name = str(raw.get("event", ""))
    data = raw.get("data")
    if not isinstance(data, dict):
        data = {}

    reference = data.get("reference")
    if not isinstance(reference, str):
        service_client.client.table("webhook_events").update(
            {
                "processed_at": datetime.now(UTC).isoformat(),
                "quarantine_reason": "missing_merchant_reference",
                "quarantined_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", webhook_event_id).execute()
        return None

    payment = _load_payment_by_reference(service_client, reference)
    if payment is None:
        service_client.client.table("webhook_events").update(
            {
                "processed_at": datetime.now(UTC).isoformat(),
                "quarantine_reason": "unknown_merchant_reference",
                "quarantined_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", webhook_event_id).execute()
        return None

    # A transfer event can carry a status and even a matching-looking reference;
    # it is never evidence that a collection was paid.
    incoming = lenco_webhook_event_to_payment_status(event_name)
    if incoming is None and event_name.startswith("collection."):
        collection_status = data.get("status")
        if isinstance(collection_status, str):
            incoming = lenco_collection_status_to_payment_status(collection_status)

    outcome: TransitionOutcome | None = None
    if incoming is not None:
        validate_collection_observation(
            payment,
            reference=reference,
            amount_major=data.get("amount"),
            currency=data.get("currency"),
            provider_reference=data.get("lencoReference", data.get("lenco_reference")),
        )
        outcome = apply_payment_status(
            service_client,
            payment_id=payment.id,
            incoming_status=incoming,
            actor_id=SYSTEM_ACTOR_ID,
            note=f"Webhook {event_name} ({row.get('event_id', '')})",
            observation=(
                collection_observation_from_webhook(
                    data, webhook_event_id=webhook_event_id
                )
                if incoming == PaymentStatus.SUCCESS
                else None
            ),
        )

    service_client.client.table("webhook_events").update(
        {"processed_at": datetime.now(UTC).isoformat()}
    ).eq("id", webhook_event_id).execute()
    return outcome


def count_payment_audit_events(service_client: ServiceRoleClient, payment_id: str) -> int:
    response = (
        service_client.client.table("audit_log")
        .select("id", count="exact")
        .eq("entity_type", "payment")
        .eq("entity_id", payment_id)
        .execute()
    )
    count = getattr(response, "count", None)
    if isinstance(count, int):
        return count
    return len(_rows(response))


def fetch_latest_payment_audit(
    service_client: ServiceRoleClient,
    payment_id: str,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("audit_log")
        .select("actor, action, before, after, at")
        .eq("entity_type", "payment")
        .eq("entity_id", payment_id)
        .order("at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return rows[0] if rows else None
