"""Pay at the door by mobile money (growth blueprint §4, option C; flag ``pay_at_door``).

When the rider arrives with a cash-on-delivery parcel, ops (for the rider) or
the customer asks Lenco for a mobile-money collection (USSD push) of the order
total to Convergeo's Lenco account. The customer's handover code is released
only after a VERIFIED observation of the exact amount: the signed webhook
(``webhook_events`` → ``process_webhook_event`` → :func:`apply_webhook`) or our
own ``GET /collections/status/:reference`` query (:func:`poll_door_payment`).
The phone screen is never trusted.

Money (integer ngwee; Lenco amounts parsed with ``Decimal`` in ``money.py``):

* Success on a payable order → ``door_payment_collected`` under the order's
  ``cod-collect-<order_id>`` key (platform_cash in, cod_receivable cleared).
  Sharing the cash key means cash and mobile money can never both settle one
  order. After the handover code is verified, :func:`on_handover_delivered`
  runs the existing COD drain (commission capture, delivery fee →
  ``delivery_revenue``, release to vendor) via ``confirm_cod_collection``.
* Success that cannot settle (order cancelled, already settled by cash or an
  earlier push, wrong amount/currency) → ``door_payment_exceptions`` row +
  ``door_payment_exception`` posting (platform_cash in, door_payment_suspense
  out) under ``door-exception-<attempt_id>``. The order is never revived; ops
  refunds by payout.

Every step is idempotent: attempts are guarded rows (DB trigger), settlement
is a compare-and-set on ``door_payment_sessions`` (write-once), ledger posts are
keyed, and an exception is unique per attempt — so duplicate webhooks, a
webhook racing a poll, or a retry after a crash all converge on one outcome.

With the flag OFF nothing here changes existing behaviour: handover codes show
as before and :func:`handover_released` is always True.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from app.errors import AppError
from app.services.dispatch.state import DispatchRow, DispatchStatus, fetch_dispatch, json_rows
from app.services.kyc.name_match import detect_momo_operator
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.orders.state import SYSTEM_ACTOR_ID, ActorRole, OrderStatus, sql_uuid
from app.services.payments.base import (
    CollectionStatus,
    InitiateCollectionRequest,
    PaymentProviderError,
    PaymentStrategy,
    ProviderErrorKind,
    ProviderOutcome,
    QueryStatusRequest,
)
from app.services.payments.money import SUPPORTED_CURRENCY, major_str_to_ngwee
from app.services.payments.references import make_order_reference

logger = logging.getLogger(__name__)

PAY_AT_DOOR_FLAG = "pay_at_door"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_ATTEMPT_TTL_SECONDS = 120
DEFAULT_COD_CAP_NGWEE = 50_000
PHONE_RE = re.compile(r"^\+260[79]\d{8}$")
PAYABLE_ORDER_STATUSES = frozenset({OrderStatus.SHIPPED.value})
IN_FLIGHT = frozenset({"initiated", "pushed"})
OPEN_STATUSES = frozenset({"initiated", "pushed", "expired"})
DOOR_ACTOR_GUC = "app.door_actor"
DOOR_NOTE_GUC = "app.door_note"

ActorKind = Literal["customer", "admin", "system"]
ExceptionReason = Literal[
    "order_not_payable", "already_settled", "amount_mismatch", "currency_mismatch"
]

# Allowed attempt transitions (mirrors guard_door_payment_attempts_update()).
ATTEMPT_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("initiated", "pushed"),
        ("initiated", "successful"),
        ("initiated", "failed"),
        ("initiated", "expired"),
        ("pushed", "successful"),
        ("pushed", "failed"),
        ("pushed", "expired"),
        ("expired", "successful"),
        ("expired", "failed"),
    }
)


class DoorPaymentError(AppError):
    """Pay-at-door domain error (``details.message_key`` for the UI)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 409,
        details: dict[str, Any] | None = None,
    ) -> None:
        key = code.removeprefix("door_payment_")
        merged = {"message_key": f"doorPayment.errors.{_camel(key)}", **(details or {})}
        super().__init__(code=code, message=message, http_status=http_status, details=merged)


def _camel(value: str) -> str:
    head, *rest = value.split("_")
    return head + "".join(part.capitalize() for part in rest)


# ---------------------------------------------------------------------------
# Flag + config
# ---------------------------------------------------------------------------


def is_pay_at_door_enabled() -> bool:
    """Kill switch (``feature_flags.pay_at_door``, default OFF). Fails closed."""
    result = run_sql_script(
        "SELECT enabled::text FROM public.feature_flags "
        f"WHERE flag = {sql_literal(PAY_AT_DOOR_FLAG)};"
    )
    if not result.ok or not result.rows:
        return False
    return result.rows[0].lower() in {"t", "true"}


def require_pay_at_door_enabled() -> None:
    if not is_pay_at_door_enabled():
        raise DoorPaymentError(
            "door_payment_disabled",
            "Pay at the door is disabled",
            details={"flag": PAY_AT_DOOR_FLAG},
        )


def _config_int(key: str, default: int) -> int:
    result = run_sql_script(
        f"SELECT value::text FROM public.platform_config WHERE key = {sql_literal(key)};"
    )
    if not result.ok or not result.rows:
        return default
    raw = result.rows[0].strip().strip('"')
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def max_attempts() -> int:
    return max(_config_int("pay_at_door_max_attempts", DEFAULT_MAX_ATTEMPTS), 1)


def attempt_ttl_seconds() -> int:
    return max(_config_int("pay_at_door_attempt_ttl_seconds", DEFAULT_ATTEMPT_TTL_SECONDS), 30)


def cash_cap_ngwee() -> int:
    """Per-order cash cap (``cod_cap_ngwee``, D12). The per-rider cash limit
    (``courier_cash_cap_ngwee``) is enforced by the logistics custody work."""
    return _config_int("cod_cap_ngwee", DEFAULT_COD_CAP_NGWEE)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DoorSession:
    dispatch_request_id: str
    order_id: str
    amount_ngwee: int
    arrived_at: str | None
    settled_via: str | None
    settled_attempt_id: str | None
    settled_at: str | None


@dataclass(frozen=True, slots=True)
class DoorAttempt:
    id: str
    dispatch_request_id: str
    order_id: str
    amount_ngwee: int
    phone_e164: str
    operator: str
    lenco_reference: str
    provider_reference: str | None
    status: str
    failure_reason: str | None
    observed_amount_ngwee: int | None
    age_seconds: int
    created_at: str


_SESSION_JSON = """json_build_object(
  'dispatch_request_id', s.dispatch_request_id, 'order_id', s.order_id,
  'amount_ngwee', s.amount_ngwee, 'arrived_at', s.arrived_at,
  'settled_via', s.settled_via, 'settled_attempt_id', s.settled_attempt_id,
  'settled_at', s.settled_at
)"""

_ATTEMPT_JSON = """json_build_object(
  'id', a.id, 'dispatch_request_id', a.dispatch_request_id, 'order_id', a.order_id,
  'amount_ngwee', a.amount_ngwee, 'phone_e164', a.phone_e164, 'operator', a.operator,
  'lenco_reference', a.lenco_reference, 'provider_reference', a.provider_reference,
  'status', a.status, 'failure_reason', a.failure_reason,
  'observed_amount_ngwee', a.observed_amount_ngwee,
  'age_seconds', floor(extract(epoch FROM (timezone('utc', now()) - a.created_at)))::int,
  'created_at', a.created_at
)"""


def _session_from(row: dict[str, Any]) -> DoorSession:
    return DoorSession(
        dispatch_request_id=str(row["dispatch_request_id"]),
        order_id=str(row["order_id"]),
        amount_ngwee=int(row["amount_ngwee"]),
        arrived_at=row.get("arrived_at"),
        settled_via=row.get("settled_via"),
        settled_attempt_id=(
            str(row["settled_attempt_id"]) if row.get("settled_attempt_id") else None
        ),
        settled_at=row.get("settled_at"),
    )


def _attempt_from(row: dict[str, Any]) -> DoorAttempt:
    observed = row.get("observed_amount_ngwee")
    return DoorAttempt(
        id=str(row["id"]),
        dispatch_request_id=str(row["dispatch_request_id"]),
        order_id=str(row["order_id"]),
        amount_ngwee=int(row["amount_ngwee"]),
        phone_e164=str(row["phone_e164"]),
        operator=str(row["operator"]),
        lenco_reference=str(row["lenco_reference"]),
        provider_reference=row.get("provider_reference"),
        status=str(row["status"]),
        failure_reason=row.get("failure_reason"),
        observed_amount_ngwee=int(observed) if observed is not None else None,
        age_seconds=int(row.get("age_seconds") or 0),
        created_at=str(row.get("created_at") or ""),
    )


def _actor_sql(actor_id: str) -> str:
    if re.fullmatch(r"[0-9a-fA-F-]{36}", actor_id):
        return sql_uuid(actor_id, "actor_id")
    return "NULL"


def _door_context_sql(*, actor_id: str, note: str) -> str:
    actor = actor_id if re.fullmatch(r"[0-9a-fA-F-]{36}", actor_id) else SYSTEM_ACTOR_ID
    return (
        f"SELECT set_config('{DOOR_ACTOR_GUC}', {sql_literal(actor)}, true);\n"
        f"SELECT set_config('{DOOR_NOTE_GUC}', {sql_literal(note[:500])}, true);\n"
    )


def load_session(dispatch_id: str) -> DoorSession | None:
    rows = json_rows(
        f"SELECT {_SESSION_JSON}::text FROM public.door_payment_sessions s "
        f"WHERE s.dispatch_request_id = {sql_uuid(dispatch_id, 'dispatch_id')};",
        context="door session lookup",
    )
    return _session_from(rows[0]) if rows else None


def list_attempts(dispatch_id: str) -> list[DoorAttempt]:
    rows = json_rows(
        f"SELECT {_ATTEMPT_JSON}::text FROM public.door_payment_attempts a "
        f"WHERE a.dispatch_request_id = {sql_uuid(dispatch_id, 'dispatch_id')} "
        "ORDER BY a.created_at, a.id;",
        context="door attempts lookup",
    )
    return [_attempt_from(row) for row in rows]


def load_attempt_by_reference(reference: str) -> DoorAttempt | None:
    if not reference.startswith("ord-") or len(reference) > 128:
        return None
    result = run_sql_script(
        f"SELECT {_ATTEMPT_JSON}::text FROM public.door_payment_attempts a "
        f"WHERE a.lenco_reference = {sql_literal(reference)};"
    )
    if not result.ok or not result.rows:
        return None
    return _attempt_from(json.loads(result.rows[0]))


def _load_attempt(attempt_id: str) -> DoorAttempt:
    rows = json_rows(
        f"SELECT {_ATTEMPT_JSON}::text FROM public.door_payment_attempts a "
        f"WHERE a.id = {sql_uuid(attempt_id, 'attempt_id')};",
        context="door attempt lookup",
    )
    if not rows:
        raise DoorPaymentError("door_payment_not_found", "Attempt not found", http_status=404)
    return _attempt_from(rows[0])


def _order_status(order_id: str) -> str:
    result = run_sql_script(
        f"SELECT status FROM public.orders WHERE id = {sql_uuid(order_id, 'order_id')};"
    )
    if not result.ok or not result.rows:
        raise DoorPaymentError("door_payment_not_found", "Order not found", http_status=404)
    return result.rows[0]


def _exception_for(attempt_id: str) -> dict[str, Any] | None:
    rows = json_rows(
        "SELECT json_build_object('id', e.id, 'reason', e.reason, "
        "'ledger_transaction_id', e.ledger_transaction_id, 'status', e.status)::text "
        "FROM public.door_payment_exceptions e "
        f"WHERE e.attempt_id = {sql_uuid(attempt_id, 'attempt_id')};",
        context="door exception lookup",
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Gating (handover code)
# ---------------------------------------------------------------------------


def applies_to(dispatch: DispatchRow) -> bool:
    """Pay at the door covers cash-on-delivery dispatches (something to collect)."""
    return dispatch.cod_amount_ngwee > 0


def handover_released(dispatch: DispatchRow) -> bool:
    """May the customer see / ops verify the handover code for this dispatch?

    Flag off, or nothing to collect (prepaid) → True (unchanged behaviour).
    Flag on and COD → only once the door session is settled (verified mobile
    money, or the cash fallback chosen by ops within the cap).
    """
    if not applies_to(dispatch) or not is_pay_at_door_enabled():
        return True
    session = load_session(dispatch.id)
    return session is not None and session.settled_via is not None


def require_handover_released(dispatch: DispatchRow) -> None:
    if not handover_released(dispatch):
        raise DoorPaymentError(
            "door_payment_required",
            "The order must be paid (mobile money or cash fallback) before handover",
        )


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def _require_door_dispatch(dispatch: DispatchRow) -> None:
    if not applies_to(dispatch):
        raise DoorPaymentError(
            "door_payment_not_applicable", "Order has nothing to collect at the door"
        )
    if dispatch.status is not DispatchStatus.PICKED_UP:
        raise DoorPaymentError(
            "door_payment_not_at_door",
            "The rider must have picked up the parcel",
            details={"dispatch_status": dispatch.status.value},
        )


def ensure_session(dispatch: DispatchRow, *, actor_id: str) -> DoorSession:
    script = f"""
BEGIN;
{_door_context_sql(actor_id=actor_id, note="Door payment session opened")}
INSERT INTO public.door_payment_sessions (dispatch_request_id, order_id, amount_ngwee)
VALUES ({sql_uuid(dispatch.id, "dispatch_id")}, {sql_uuid(dispatch.order_id, "order_id")},
        {int(dispatch.cod_amount_ngwee)})
ON CONFLICT (dispatch_request_id) DO NOTHING;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"door session open failed: {result.error}")
    session = load_session(dispatch.id)
    if session is None:
        raise RuntimeError("door session missing after open")
    return session


def mark_arrived(*, dispatch_id: str, actor_id: str) -> DoorSession:
    """Rider is at the door (recorded by ops for the rider). Write-once."""
    require_pay_at_door_enabled()
    dispatch = fetch_dispatch(dispatch_id)
    _require_door_dispatch(dispatch)
    ensure_session(dispatch, actor_id=actor_id)
    script = f"""
BEGIN;
{_door_context_sql(actor_id=actor_id, note="Rider arrived")}
UPDATE public.door_payment_sessions
SET arrived_at = timezone('utc', now()), arrived_by = {sql_uuid(actor_id, "actor_id")}
WHERE dispatch_request_id = {sql_uuid(dispatch_id, "dispatch_id")} AND arrived_at IS NULL;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"door arrival failed: {result.error}")
    session = load_session(dispatch_id)
    assert session is not None
    return session


def _settle_cas(
    *, dispatch_id: str, via: Literal["mobile_money", "cash"], attempt_id: str | None, actor_id: str
) -> bool:
    """Write-once settlement, only while the order is still payable. True if won."""
    attempt_sql = sql_uuid(attempt_id, "attempt_id") if attempt_id else "NULL"
    statuses = ", ".join(sql_literal(s) for s in sorted(PAYABLE_ORDER_STATUSES))
    rows = json_rows(
        f"""
BEGIN;
{_door_context_sql(actor_id=actor_id, note=f"Settled at the door ({via})")}
UPDATE public.door_payment_sessions s
SET settled_via = {sql_literal(via)}, settled_attempt_id = {attempt_sql},
    settled_at = timezone('utc', now()),
    settled_by = {_actor_sql(actor_id)}
WHERE s.dispatch_request_id = {sql_uuid(dispatch_id, "dispatch_id")}
  AND s.settled_via IS NULL
  AND EXISTS (SELECT 1 FROM public.orders o WHERE o.id = s.order_id AND o.status IN ({statuses}))
RETURNING json_build_object('ok', true)::text;
COMMIT;
""",
        context="door settlement",
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# Attempt transitions
# ---------------------------------------------------------------------------


def _transition_attempt(
    attempt: DoorAttempt,
    to_status: str,
    *,
    actor_id: str,
    note: str,
    failure_reason: str | None = None,
    observed_amount_ngwee: int | None = None,
    observation_source: str | None = None,
    provider_reference: str | None = None,
) -> bool:
    """CAS from the attempt's current status. False when it moved on meanwhile."""
    if (attempt.status, to_status) not in ATTEMPT_TRANSITIONS:
        return False
    sets = [f"status = {sql_literal(to_status)}"]
    if failure_reason is not None:
        sets.append(f"failure_reason = {sql_literal(failure_reason[:200])}")
    if observed_amount_ngwee is not None:
        sets.append(f"observed_amount_ngwee = {int(observed_amount_ngwee)}")
    if observation_source is not None:
        sets.append(f"observation_source = {sql_literal(observation_source)}")
    if provider_reference:
        sets.append(
            f"provider_reference = coalesce(provider_reference, "
            f"{sql_literal(provider_reference[:128])})"
        )
    rows = json_rows(
        f"""
BEGIN;
{_door_context_sql(actor_id=actor_id, note=note)}
UPDATE public.door_payment_attempts
SET {", ".join(sets)}
WHERE id = {sql_uuid(attempt.id, "attempt_id")} AND status = {sql_literal(attempt.status)}
RETURNING json_build_object('ok', true)::text;
COMMIT;
""",
        context="door attempt transition",
    )
    return bool(rows)


# ---------------------------------------------------------------------------
# Observations (webhook + status query) — the only way to "paid"
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObservationOutcome:
    attempt_id: str
    attempt_status: str
    settled: bool
    exception_reason: str | None


def _incoming_status(raw_status: object) -> str | None:
    if not isinstance(raw_status, str):
        return None
    normalized = raw_status.strip().lower()
    if normalized == CollectionStatus.SUCCESSFUL.value:
        return "successful"
    if normalized == CollectionStatus.FAILED.value:
        return "failed"
    if normalized in {CollectionStatus.PENDING.value, CollectionStatus.PAY_OFFLINE.value}:
        return "pushed"
    return None


def _observed_ngwee(amount_major: object, currency: object) -> tuple[int | None, bool]:
    """(ngwee, currency_ok). Decimal-only parse; anything unparseable → None."""
    currency_ok = isinstance(currency, str) and currency.upper() == SUPPORTED_CURRENCY
    if not currency_ok:
        return None, False  # never read a foreign amount as ngwee
    if isinstance(amount_major, bool) or not isinstance(amount_major, (str, int)):
        return None, currency_ok
    try:
        return major_str_to_ngwee(str(amount_major).strip()), currency_ok
    except (TypeError, ValueError):
        return None, currency_ok


def apply_observation(
    *,
    reference: str,
    raw_status: object,
    amount_major: object,
    currency: object,
    provider_reference: object,
    source: Literal["webhook", "status_query", "initiation"],
    failure_reason: str | None = None,
) -> ObservationOutcome | None:
    """Drive one attempt from a verified provider observation. Idempotent.

    Returns ``None`` when ``reference`` is not a door-payment attempt.
    """
    attempt = load_attempt_by_reference(reference)
    if attempt is None:
        return None
    incoming = _incoming_status(raw_status)
    provider_ref = provider_reference if isinstance(provider_reference, str) else None

    observed, currency_ok = _observed_ngwee(amount_major, currency)
    if incoming == "pushed" and attempt.status == "initiated":
        _transition_attempt(
            attempt, "pushed", actor_id=SYSTEM_ACTOR_ID, note=f"Lenco {source}: pending"
        )
    elif incoming == "failed" and attempt.status in OPEN_STATUSES:
        _transition_attempt(
            attempt,
            "failed",
            actor_id=SYSTEM_ACTOR_ID,
            note=f"Lenco {source}: failed",
            failure_reason=failure_reason or "provider_failed",
            observation_source=source,
            provider_reference=provider_ref,
        )
    elif incoming == "successful" and attempt.status in OPEN_STATUSES:
        _transition_attempt(
            attempt,
            "successful",
            actor_id=SYSTEM_ACTOR_ID,
            note=f"Lenco {source}: successful",
            observed_amount_ngwee=observed,
            observation_source=source,
            provider_reference=provider_ref,
        )

    attempt = _load_attempt(attempt.id)
    if attempt.status == "successful":
        # Duplicate / late observations converge here: the decision is made once
        # and every later call only heals a ledger post a crash interrupted. A
        # non-success observation never undoes a success.
        return _settle_or_except(
            attempt, currency_ok=currency_ok if incoming == "successful" else True
        )
    return ObservationOutcome(attempt.id, attempt.status, False, None)


def _settle_or_except(attempt: DoorAttempt, *, currency_ok: bool) -> ObservationOutcome:
    """Decide (once) whether a successful attempt settles its order. Idempotent."""
    session = load_session(attempt.dispatch_request_id)
    if session is not None and session.settled_attempt_id == attempt.id:
        _book_collection(attempt)
        return ObservationOutcome(attempt.id, attempt.status, True, None)
    existing = _exception_for(attempt.id)
    if existing is not None:
        _book_exception(attempt, str(existing["id"]))
        return ObservationOutcome(attempt.id, attempt.status, False, str(existing["reason"]))

    reason: ExceptionReason | None = None
    if not currency_ok:
        reason = "currency_mismatch"
    elif attempt.observed_amount_ngwee is None or (
        attempt.observed_amount_ngwee != attempt.amount_ngwee
    ):
        # Partial (or over-) payments never settle an order.
        reason = "amount_mismatch"
    elif _settle_cas(
        dispatch_id=attempt.dispatch_request_id,
        via="mobile_money",
        attempt_id=attempt.id,
        actor_id=SYSTEM_ACTOR_ID,
    ):
        _book_collection(attempt)
        return ObservationOutcome(attempt.id, attempt.status, True, None)
    else:
        latest = load_session(attempt.dispatch_request_id)
        if latest is not None and latest.settled_attempt_id == attempt.id:
            _book_collection(attempt)
            return ObservationOutcome(attempt.id, attempt.status, True, None)
        reason = (
            "already_settled"
            if latest is not None and latest.settled_via is not None
            else "order_not_payable"
        )
    exception_id = _open_exception(attempt, reason)
    _book_exception(attempt, exception_id)
    logger.warning(
        "door payment exception",
        extra={"alert": "door_payment_exception", "attempt_id": attempt.id, "reason": reason},
    )
    return ObservationOutcome(attempt.id, attempt.status, False, reason)


def collection_idempotency_key(order_id: str) -> str:
    # Shared with cash COD (payments/cod.py): one collection per order, ever.
    return f"cod-collect-{order_id}"


def exception_idempotency_key(attempt_id: str) -> str:
    return f"door-exception-{attempt_id}"


def _order_vendor(order_id: str) -> str:
    result = run_sql_script(
        f"SELECT vendor_id::text FROM public.orders WHERE id = {sql_uuid(order_id, 'order_id')};"
    )
    if not result.ok or not result.rows:
        raise RuntimeError("order vendor lookup failed")
    return result.rows[0]


def _book_collection(attempt: DoorAttempt) -> str:
    from app.services.payments.cod import receivable_idempotency_key, record_cod_receivable

    if _transaction_id(receivable_idempotency_key(attempt.order_id)) is None:
        record_cod_receivable(order_id=attempt.order_id)
    posted = post_transaction(
        idempotency_key=collection_idempotency_key(attempt.order_id),
        template=LedgerTemplate.DOOR_PAYMENT_COLLECTED,
        order_id=attempt.order_id,
        collected_ngwee=attempt.amount_ngwee,
        vendor_id=_order_vendor(attempt.order_id),
    )
    if posted.kind != LedgerTemplate.DOOR_PAYMENT_COLLECTED.value:
        # Cash was booked for this order outside the door flow: money twice.
        logger.error(
            "door payment settled an order whose collection was booked as %s",
            posted.kind,
            extra={"alert": "door_payment_double_collection", "attempt_id": attempt.id},
        )
    return posted.id


def _transaction_id(idempotency_key: str) -> str | None:
    result = run_sql_script(
        "SELECT id::text FROM public.ledger_transactions "
        f"WHERE idempotency_key = {sql_literal(idempotency_key)};"
    )
    return result.rows[0] if result.ok and result.rows else None


def _open_exception(attempt: DoorAttempt, reason: ExceptionReason) -> str:
    observed = (
        str(int(attempt.observed_amount_ngwee))
        if attempt.observed_amount_ngwee is not None
        else "NULL"
    )
    rows = json_rows(
        f"""
WITH ins AS (
  INSERT INTO public.door_payment_exceptions (
    attempt_id, order_id, reason, expected_amount_ngwee, observed_amount_ngwee
  ) VALUES (
    {sql_uuid(attempt.id, "attempt_id")}, {sql_uuid(attempt.order_id, "order_id")},
    {sql_literal(reason)}, {int(attempt.amount_ngwee)}, {observed}
  )
  ON CONFLICT (attempt_id) DO NOTHING
  RETURNING id
)
SELECT json_build_object('id', id)::text FROM ins
UNION ALL
SELECT json_build_object('id', e.id)::text FROM public.door_payment_exceptions e
WHERE e.attempt_id = {sql_uuid(attempt.id, "attempt_id")}
LIMIT 1;
""",
        context="door exception open",
    )
    if not rows:
        raise RuntimeError("door exception insert failed")
    _audit(
        action="door_payment.exception.opened",
        entity_id=str(rows[0]["id"]),
        after={"attempt_id": attempt.id, "order_id": attempt.order_id, "reason": reason},
    )
    return str(rows[0]["id"])


def _book_exception(attempt: DoorAttempt, exception_id: str) -> str | None:
    """Suspense booking of money actually received (ZMW, parseable, > 0)."""
    received = attempt.observed_amount_ngwee
    if received is None or received <= 0:
        return None
    exc = _exception_for(attempt.id)
    if exc is not None and exc.get("reason") == "currency_mismatch":
        return None  # not ZMW ngwee: ops books by hand after Lenco confirms
    posted = post_transaction(
        idempotency_key=exception_idempotency_key(attempt.id),
        template=LedgerTemplate.DOOR_PAYMENT_EXCEPTION,
        order_id=attempt.order_id,
        received_ngwee=received,
    )
    run_sql_script(
        "UPDATE public.door_payment_exceptions "
        f"SET ledger_transaction_id = {sql_uuid(posted.id, 'transaction_id')} "
        f"WHERE id = {sql_uuid(exception_id, 'exception_id')} AND ledger_transaction_id IS NULL;"
    )
    return posted.id


def _audit(
    *, action: str, entity_id: str, after: dict[str, Any], actor_id: str | None = None
) -> None:
    actor = (
        sql_uuid(actor_id, "actor_id")
        if actor_id and re.fullmatch(r"[0-9a-fA-F-]{36}", actor_id)
        else "NULL"
    )
    result = run_sql_script(
        "INSERT INTO public.audit_log (actor, action, entity_type, entity_id, before, after) "
        f"VALUES ({actor}, {sql_literal(action)}, 'door_payment', "
        f"{sql_uuid(entity_id, 'entity_id')}, NULL, {sql_literal(json.dumps(after))}::jsonb);"
    )
    if not result.ok:
        raise RuntimeError(f"door audit failed: {result.error}")


def apply_webhook(*, event_name: str, data: dict[str, Any]) -> ObservationOutcome | None:
    """Verified (``process_webhook_event`` checked the signature proof) Lenco event."""
    reference = data.get("reference")
    if not isinstance(reference, str):
        return None
    raw_status: object = data.get("status")
    if event_name == "collection.successful":
        raw_status = "successful"
    elif event_name == "collection.failed":
        raw_status = "failed"
    elif not event_name.startswith("collection."):
        return None  # transfer events are never evidence a collection was paid
    reason = data.get("reasonForFailure")
    return apply_observation(
        reference=reference,
        raw_status=raw_status,
        amount_major=data.get("amount"),
        currency=data.get("currency"),
        provider_reference=data.get("lencoReference", data.get("lenco_reference")),
        source="webhook",
        failure_reason=str(reason)[:200] if reason else None,
    )


def is_door_reference(reference: object) -> bool:
    return isinstance(reference, str) and load_attempt_by_reference(reference) is not None


# ---------------------------------------------------------------------------
# Request / poll / cash fallback
# ---------------------------------------------------------------------------


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("260"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    candidate = f"+260{digits}"
    if not PHONE_RE.fullmatch(candidate):
        raise DoorPaymentError(
            "door_payment_invalid_phone",
            "Enter a Zambian mobile number",
            http_status=422,
        )
    return candidate


def _operator_for(phone_e164: str) -> Literal["mtn", "airtel"]:
    operator = detect_momo_operator(phone_e164)
    if operator not in ("mtn", "airtel"):
        raise DoorPaymentError(
            "door_payment_operator_unsupported",
            "Only MTN and Airtel numbers can receive the payment prompt",
            http_status=422,
            details={"operator": operator},
        )
    return operator


def _default_phone(order_id: str) -> str | None:
    result = run_sql_script(
        "SELECT coalesce(a.phone, pr.phone, '') FROM public.orders o "
        "LEFT JOIN public.addresses a ON a.id = o.address_id "
        "LEFT JOIN public.profiles pr ON pr.id = o.customer_id "
        f"WHERE o.id = {sql_uuid(order_id, 'order_id')};"
    )
    if not result.ok or not result.rows or not result.rows[0].strip():
        return None
    return result.rows[0].strip()


async def _refresh_open_attempts(
    attempts: list[DoorAttempt], strategy: PaymentStrategy
) -> list[DoorAttempt]:
    """Query Lenco for open attempts; expire unanswered prompts past the TTL."""
    ttl = attempt_ttl_seconds()
    changed = False
    for attempt in attempts:
        if attempt.status not in OPEN_STATUSES:
            continue
        await _query_and_apply(attempt, strategy)
        changed = True
        current = _load_attempt(attempt.id)
        if current.status in IN_FLIGHT and current.age_seconds >= ttl:
            _transition_attempt(
                current,
                "expired",
                actor_id=SYSTEM_ACTOR_ID,
                note="Prompt not answered in time",
                failure_reason="timeout",
            )
    if not changed or not attempts:
        return attempts
    return list_attempts(attempts[0].dispatch_request_id)


async def _query_and_apply(attempt: DoorAttempt, strategy: PaymentStrategy) -> None:
    try:
        result = await strategy.query_status(QueryStatusRequest(reference=attempt.lenco_reference))
    except PaymentProviderError:
        logger.info("door payment status query failed", extra={"attempt_id": attempt.id})
        return
    if result.outcome == ProviderOutcome.NOT_FOUND:
        return
    if result.reference not in (None, attempt.lenco_reference):
        logger.error(
            "door payment status query returned another reference",
            extra={"alert": "door_payment_reference_mismatch", "attempt_id": attempt.id},
        )
        return
    apply_observation(
        reference=attempt.lenco_reference,
        raw_status=result.status,
        amount_major=result.amount_major,
        currency=result.currency,
        provider_reference=result.provider_reference,
        source="status_query",
        failure_reason=result.failure_reason,
    )


@dataclass(frozen=True, slots=True)
class DoorStatus:
    enabled: bool
    applies: bool
    dispatch_id: str | None
    state: str
    amount_ngwee: int
    arrived: bool
    settled_via: str | None
    attempts_used: int
    attempts_allowed: int
    latest_attempt_status: str | None
    latest_failure_reason: str | None
    can_request: bool
    cash_allowed: bool
    exception_open: bool


def _status_from(
    dispatch: DispatchRow, session: DoorSession | None, attempts: list[DoorAttempt]
) -> DoorStatus:
    allowed = max_attempts()
    latest = attempts[-1] if attempts else None
    settled_via = session.settled_via if session else None
    arrived = bool(session and session.arrived_at)
    in_flight = latest is not None and latest.status in IN_FLIGHT
    exception_open = any(
        _exception_for(a.id) is not None for a in attempts if a.status == "successful"
    )
    if settled_via == "mobile_money":
        state = "paid"
    elif settled_via == "cash":
        state = "cash"
    elif dispatch.status is not DispatchStatus.PICKED_UP:
        state = "not_at_door"
    elif not arrived:
        state = "awaiting_arrival"
    elif in_flight:
        state = "pending"
    elif latest is not None and latest.status in {"failed", "expired"}:
        state = "failed"
    else:
        state = "awaiting_payment"
    can_request = state in {"awaiting_payment", "failed"} and len(attempts) < allowed
    cash_allowed = (
        settled_via is None
        and dispatch.status is DispatchStatus.PICKED_UP
        and not in_flight
        and dispatch.cod_amount_ngwee <= cash_cap_ngwee()
    )
    return DoorStatus(
        enabled=True,
        applies=True,
        dispatch_id=dispatch.id,
        state=state,
        amount_ngwee=dispatch.cod_amount_ngwee,
        arrived=arrived,
        settled_via=settled_via,
        attempts_used=len(attempts),
        attempts_allowed=allowed,
        latest_attempt_status=latest.status if latest else None,
        latest_failure_reason=latest.failure_reason if latest else None,
        can_request=can_request,
        cash_allowed=cash_allowed,
        exception_open=exception_open,
    )


def disabled_status(*, enabled: bool, applies: bool = False) -> DoorStatus:
    return DoorStatus(
        enabled=enabled,
        applies=applies,
        dispatch_id=None,
        state="not_applicable",
        amount_ngwee=0,
        arrived=False,
        settled_via=None,
        attempts_used=0,
        attempts_allowed=0,
        latest_attempt_status=None,
        latest_failure_reason=None,
        can_request=False,
        cash_allowed=False,
        exception_open=False,
    )


def door_status(dispatch: DispatchRow) -> DoorStatus:
    if not applies_to(dispatch):
        return disabled_status(enabled=True)
    return _status_from(dispatch, load_session(dispatch.id), list_attempts(dispatch.id))


async def poll_door_payment(*, dispatch_id: str, strategy: PaymentStrategy) -> DoorStatus:
    """Network-loss safe: re-query Lenco for open attempts and return the state."""
    require_pay_at_door_enabled()
    dispatch = fetch_dispatch(dispatch_id)
    if not applies_to(dispatch):
        return disabled_status(enabled=True)
    await _refresh_open_attempts(list_attempts(dispatch_id), strategy)
    return door_status(dispatch)


async def request_door_payment(
    *,
    dispatch_id: str,
    actor_id: str,
    actor_role: ActorKind,
    phone: str | None,
    strategy: PaymentStrategy,
) -> DoorStatus:
    """Send the mobile-money prompt for the exact order total (server-computed)."""
    require_pay_at_door_enabled()
    dispatch = fetch_dispatch(dispatch_id)
    _require_door_dispatch(dispatch)
    if actor_role == "admin":
        # Ops pressing "Request payment" for the rider means the rider is there.
        session = mark_arrived(dispatch_id=dispatch_id, actor_id=actor_id)
    else:
        session = ensure_session(dispatch, actor_id=actor_id)
    if session.arrived_at is None:
        raise DoorPaymentError(
            "door_payment_awaiting_arrival", "Wait until the rider is at your door"
        )
    if session.settled_via is not None:
        raise DoorPaymentError(
            "door_payment_already_settled",
            "This order is already paid",
            details={"settled_via": session.settled_via},
        )
    if _order_status(dispatch.order_id) not in PAYABLE_ORDER_STATUSES:
        raise DoorPaymentError("door_payment_order_not_payable", "Order can no longer be paid")

    attempts = await _refresh_open_attempts(list_attempts(dispatch_id), strategy)
    refreshed = load_session(dispatch_id)
    if refreshed is not None and refreshed.settled_via is not None:
        return door_status(dispatch)  # a late answer to an earlier prompt paid it
    in_flight = [a for a in attempts if a.status in IN_FLIGHT]
    if in_flight:
        raise DoorPaymentError(
            "door_payment_in_flight",
            "A payment prompt is already waiting on the phone",
            details={"retry_after": max(attempt_ttl_seconds() - in_flight[-1].age_seconds, 1)},
        )
    if len(attempts) >= max_attempts():
        raise DoorPaymentError(
            "door_payment_attempts_exhausted",
            "Too many prompts; use the cash fallback or return the parcel",
            details={"attempts_allowed": max_attempts()},
        )

    raw_phone = phone or _default_phone(dispatch.order_id)
    if not raw_phone:
        raise DoorPaymentError(
            "door_payment_invalid_phone", "Enter a Zambian mobile number", http_status=422
        )
    phone_e164 = normalize_phone(raw_phone)
    operator = _operator_for(phone_e164)

    attempt_id = str(uuid.uuid4())
    # The session snapshot (= dispatch COD snapshot) is the amount; never the client.
    amount_ngwee = int(session.amount_ngwee)
    reference = make_order_reference(dispatch.order_id, attempt=attempt_id)
    insert = run_sql_script(
        f"""
BEGIN;
{_door_context_sql(actor_id=actor_id, note=f"Prompt requested by {actor_role}")}
INSERT INTO public.door_payment_attempts (
  id, dispatch_request_id, order_id, amount_ngwee, phone_e164, operator,
  lenco_reference, initiated_by, initiated_role
) VALUES (
  {sql_uuid(attempt_id, "attempt_id")}, {sql_uuid(dispatch_id, "dispatch_id")},
  {sql_uuid(dispatch.order_id, "order_id")}, {amount_ngwee},
  {sql_literal(phone_e164)}, {sql_literal(operator)}, {sql_literal(reference)},
  {_actor_sql(actor_id)}, {sql_literal(actor_role)}
);
COMMIT;
"""
    )
    if not insert.ok:
        if "door_payment_attempts_one_in_flight_per_order" in (insert.error or ""):
            raise DoorPaymentError(
                "door_payment_in_flight", "A payment prompt is already waiting on the phone"
            )
        raise RuntimeError(f"door attempt insert failed: {insert.error}")

    attempt = _load_attempt(attempt_id)
    try:
        collection = await strategy.initiate_collection(
            InitiateCollectionRequest(
                reference=reference,
                amount_ngwee=attempt.amount_ngwee,
                phone=phone_e164,
                operator=operator,
            )
        )
    except PaymentProviderError as exc:
        if exc.dispatch_may_have_succeeded or exc.kind is ProviderErrorKind.TRANSPORT:
            # Response lost: the reference is durable, the poll/webhook decides.
            return door_status(dispatch)
        _transition_attempt(
            attempt,
            "failed",
            actor_id=SYSTEM_ACTOR_ID,
            note="Lenco refused the prompt",
            failure_reason=exc.code,
        )
        return door_status(dispatch)

    if collection.status in {CollectionStatus.PENDING, CollectionStatus.PAY_OFFLINE}:
        _transition_attempt(
            attempt,
            "pushed",
            actor_id=SYSTEM_ACTOR_ID,
            note="Prompt sent",
            provider_reference=collection.provider_reference,
        )
    else:
        # Never trust an initiation body for a final status: ask Lenco.
        await _query_and_apply(attempt, strategy)
    return door_status(dispatch)


def settle_with_cash(*, dispatch_id: str, actor_id: str) -> DoorStatus:
    """Cash fallback chosen at the door (ops for the rider), within the cash cap.

    Releases the handover code. The cash itself is booked later by ops through
    the existing COD confirmation once the rider remits it.
    """
    require_pay_at_door_enabled()
    dispatch = fetch_dispatch(dispatch_id)
    _require_door_dispatch(dispatch)
    cap = cash_cap_ngwee()
    if dispatch.cod_amount_ngwee > cap:
        raise DoorPaymentError(
            "door_payment_cash_over_cap",
            "Order total is above the cash limit",
            details={"cap_ngwee": cap, "amount_ngwee": dispatch.cod_amount_ngwee},
        )
    session = mark_arrived(dispatch_id=dispatch_id, actor_id=actor_id)
    if session.settled_via is not None:
        raise DoorPaymentError(
            "door_payment_already_settled",
            "This order is already paid",
            details={"settled_via": session.settled_via},
        )
    if any(a.status in IN_FLIGHT for a in list_attempts(dispatch_id)):
        raise DoorPaymentError(
            "door_payment_in_flight",
            "A payment prompt is still waiting; check its status first",
        )
    if not _settle_cas(dispatch_id=dispatch_id, via="cash", attempt_id=None, actor_id=actor_id):
        latest = load_session(dispatch_id)
        if latest is not None and latest.settled_via is not None:
            raise DoorPaymentError(
                "door_payment_already_settled",
                "This order is already paid",
                details={"settled_via": latest.settled_via},
            )
        raise DoorPaymentError("door_payment_order_not_payable", "Order can no longer be paid")
    return door_status(dispatch)


def on_handover_delivered(*, dispatch_id: str, order_id: str) -> None:
    """After the handover code is verified: drain a mobile-money settlement.

    Runs the existing COD release (commission, delivery fee → delivery_revenue,
    vendor net) exactly as for confirmed cash. Cash settlements wait for ops'
    remittance confirmation as before. Failures are logged; ops can heal with
    the (idempotent) COD confirmation endpoint.
    """
    session = load_session(dispatch_id)
    if session is None or session.settled_via != "mobile_money":
        return
    from app.services.payments.cod import confirm_cod_collection

    try:
        confirm_cod_collection(
            order_id=order_id,
            actor_id=SYSTEM_ACTOR_ID,
            note="[pay-at-door] mobile money confirmed by Lenco; handover verified",
            actor_role=ActorRole.ADMIN,
        )
    except Exception:
        logger.exception(
            "pay-at-door release after handover failed",
            extra={"alert": "door_payment_release_failed", "order_id": order_id},
        )


# ---------------------------------------------------------------------------
# Admin read models
# ---------------------------------------------------------------------------


def board_states(dispatch_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Compact per-dispatch door payment state for the dispatch board."""
    if not dispatch_ids:
        return {}
    ids = ", ".join(sql_uuid(d, "dispatch_id") for d in dispatch_ids)
    rows = json_rows(
        f"""
SELECT json_build_object(
  'dispatch_id', s.dispatch_request_id,
  'arrived', s.arrived_at IS NOT NULL,
  'settled_via', s.settled_via,
  'attempts', (SELECT count(*) FROM public.door_payment_attempts a
               WHERE a.dispatch_request_id = s.dispatch_request_id),
  'latest_status', (SELECT a.status FROM public.door_payment_attempts a
                    WHERE a.dispatch_request_id = s.dispatch_request_id
                    ORDER BY a.created_at DESC, a.id DESC LIMIT 1),
  'exception_open', EXISTS (SELECT 1 FROM public.door_payment_exceptions e
                            JOIN public.door_payment_attempts a ON a.id = e.attempt_id
                            WHERE a.dispatch_request_id = s.dispatch_request_id
                              AND e.status = 'open')
)::text
FROM public.door_payment_sessions s
WHERE s.dispatch_request_id IN ({ids});
""",
        context="door board states",
    )
    return {str(row["dispatch_id"]): row for row in rows}


def board_state_label(row: dict[str, Any] | None) -> str | None:
    if row is None:
        return None
    if row.get("exception_open"):
        return "exception"
    settled = row.get("settled_via")
    if settled == "mobile_money":
        return "paid"
    if settled == "cash":
        return "cash"
    latest = row.get("latest_status")
    if latest in IN_FLIGHT:
        return "pending"
    if latest in {"failed", "expired"}:
        return "failed"
    return "arrived" if row.get("arrived") else None


def list_open_exceptions(limit: int = 100) -> list[dict[str, Any]]:
    return json_rows(
        f"""
SELECT json_build_object(
  'id', e.id, 'attempt_id', e.attempt_id, 'order_id', e.order_id, 'reason', e.reason,
  'expected_amount_ngwee', e.expected_amount_ngwee,
  'observed_amount_ngwee', e.observed_amount_ngwee,
  'ledger_transaction_id', e.ledger_transaction_id, 'created_at', e.created_at
)::text
FROM public.door_payment_exceptions e
WHERE e.status = 'open'
ORDER BY e.created_at ASC
LIMIT {int(limit)};
""",
        context="door exceptions list",
    )


def resolve_exception(*, exception_id: str, actor_id: str, note: str) -> None:
    """Close an exception after ops refunded (payout) or otherwise settled it."""
    if not note.strip():
        raise DoorPaymentError(
            "door_payment_resolution_note_required", "A note is required", http_status=422
        )
    rows = json_rows(
        f"""
UPDATE public.door_payment_exceptions
SET status = 'resolved', resolved_at = timezone('utc', now()),
    resolved_by = {sql_uuid(actor_id, "actor_id")},
    resolution_note = {sql_literal(note.strip()[:1000])}
WHERE id = {sql_uuid(exception_id, "exception_id")} AND status = 'open'
RETURNING json_build_object('id', id)::text;
""",
        context="door exception resolve",
    )
    if not rows:
        raise DoorPaymentError(
            "door_payment_not_found", "Open exception not found", http_status=404
        )
    _audit(
        action="door_payment.exception.resolved",
        entity_id=exception_id,
        after={"note": note.strip()[:1000]},
        actor_id=actor_id,
    )


async def poll_open_attempts(strategy: PaymentStrategy, *, limit: int = 50) -> int:
    """Reconciliation tick: close webhook gaps for open door attempts."""
    rows = json_rows(
        f"SELECT {_ATTEMPT_JSON}::text FROM public.door_payment_attempts a "
        "WHERE a.status IN ('initiated', 'pushed', 'expired') "
        "AND a.created_at > timezone('utc', now()) - interval '2 days' "
        f"ORDER BY a.updated_at ASC LIMIT {int(limit)};",
        context="door open attempts",
    )
    for row in rows:
        try:
            await _query_and_apply(_attempt_from(row), strategy)
        except Exception:
            logger.exception("door attempt poll failed", extra={"attempt_id": row.get("id")})
    return len(rows)
