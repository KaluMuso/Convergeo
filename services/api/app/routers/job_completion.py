"""Service job completion → confirm → single escrow release (M11-P05).

MONEY-CRITICAL. Integer ngwee everywhere; no float on money.

Completion flow (mirrors the merged order confirm/auto-confirm of M09-P06/P10):

  provider marks complete  →  customer confirms (or 48h auto-confirm)  →
  balance leg (``create_balance_item``, M11-P04) + balance settlement (M08
  CHARGE_RECEIVED) + escrow release, all EXACTLY ONCE via the order engine's
  ``release-{order_id}`` idempotency key.

Single-release / single-capture invariants
-------------------------------------------
There is exactly ONE order per accepted job (M11-P04). This router NEVER
re-snapshots or re-captures commission: it reuses ``create_balance_item`` (which
leaves the commission snapshot untouched) and posts the vendor release via
``compute_release_amounts`` from that single snapshot (fail-closed on invalid
snapshots, active refunds, and open disputes). The release ledger post is keyed
by ``release_idempotency_key(order_id)`` — the SAME key the product escrow engine
uses — so a double-confirm, a retry, or the background release sweeper can never
post a second release. The service order sits at ``placed`` until confirm flips it
straight to ``completed`` (unlocking the verified-engagement review); it is never
placed into a product-sweeper-eligible status before confirm, so the sweeper never
releases un-confirmed service work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

from app.core.auth import CurrentUser, get_current_user
from app.core.internal_token import InternalTokenMisconfigured, resolve_internal_token
from app.core.ratelimit import bump_rate_counter, get_client_ip, raise_rate_limited
from app.deps import get_supabase_client
from app.errors import AppError
from app.schemas.base import StrictModel
from app.services.commissions.engine import capture_order_commission
from app.services.escrow.order_money_gate import (
    OrderMoneyGateError,
    claim_release_gate,
)
from app.services.escrow.release import release_idempotency_key
from app.services.escrow.release_accounting import (
    ReleaseAccountingError,
    compute_release_amounts,
    order_has_open_dispute,
    release_blocked_reason,
)
from app.services.ledger.engine import post_transaction
from app.services.ledger.templates import LedgerTemplate
from app.services.orders.audit import (
    ORDER_ACTOR_GUC,
    ORDER_NOTE_GUC,
    run_sql_script,
    sql_literal,
)
from app.services.rfq.engagement import create_balance_item
from app.services.stock.claim import sql_uuid
from fastapi import APIRouter, Depends, Request
from pydantic import Field

router = APIRouter(tags=["job-completion"])

# Provider-marked-complete is recorded on the append-only audit_log; its timestamp
# anchors the auto-confirm window (never a schema/migration).
PROVIDER_COMPLETE_ACTION = "job.provider_completed"
CONFIRM_ACTION = "job.confirmed"

# Auto-confirm window (hours) — admin-tunable via platform_config, default 48h.
CONFIG_KEY_AUTOCONFIRM_HOURS = "job_autoconfirm_hours"
DEFAULT_JOB_AUTOCONFIRM_HOURS = 48

# Service orders only ever complete (never a delivery 'delivered' hop); review is
# unlocked once the order is completed — the same gate reviews.py enforces.
REVIEW_UNLOCK_STATUSES = frozenset({"completed"})

# The service order lives at 'placed' between accept and confirm.
PENDING_ORDER_STATUS = "placed"
COMPLETED_ORDER_STATUS = "completed"

SYSTEM_ACTOR_ID = "00000000-0000-0000-0000-000000000001"

_AUTOCONFIRM_TOKEN_ENV = "INTERNAL_JOB_COMPLETION_TOKEN"
_DEFAULT_AUTOCONFIRM_TOKEN = "dev-internal-job-completion"  # noqa: S105 (dev default)

DEFAULT_BATCH_LIMIT = 50
MAX_BATCH_LIMIT = 200


class _ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkCompleteResult:
    job_id: str
    order_id: str
    marked: bool  # False when the provider had already marked this job complete.


@dataclass(frozen=True, slots=True)
class ConfirmResult:
    job_id: str
    order_id: str
    status: str
    already_confirmed: bool
    balance_ngwee: int
    balance_created: bool
    released: bool
    release_created: bool
    net_ngwee: int


@dataclass(frozen=True, slots=True)
class AutoConfirmResult:
    scanned: int
    confirmed: int
    skipped: int


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _read_config_int(key: str, default: int) -> int:
    key_sql = sql_literal(key)
    result = run_sql_script(
        f"SELECT value::text FROM public.platform_config WHERE key = {key_sql} LIMIT 1;"
    )
    if not result.ok or not result.rows:
        return default
    raw = result.rows[0].strip()
    if raw.isdigit():
        return int(raw)
    if raw.startswith('"') and raw.endswith('"') and raw[1:-1].isdigit():
        return int(raw[1:-1])
    return default


# ---------------------------------------------------------------------------
# Order / job lookups
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ServiceOrder:
    order_id: str
    status: str
    customer_id: str
    vendor_id: str
    delivery_fee_ngwee: int


def _load_service_order(job_id: str) -> _ServiceOrder | None:
    """Resolve the single order backing a service job (via the deposit leg)."""
    job_sql = sql_uuid(job_id, "job_id")
    result = run_sql_script(
        f"""
SELECT o.id::text || '|' || o.status || '|' || o.customer_id::text
       || '|' || o.vendor_id::text || '|' || o.delivery_fee_ngwee::text
FROM public.orders o
JOIN public.order_items oi ON oi.order_id = o.id AND oi.item_kind = 'service_deposit'
JOIN public.order_item_services ois ON ois.order_item_id = oi.id
WHERE ois.job_id = {job_sql}
LIMIT 1;
"""
    )
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|", 4)
    if len(parts) != 5 or not parts[4].strip().isdigit():
        return None
    return _ServiceOrder(
        order_id=parts[0],
        status=parts[1],
        customer_id=parts[2],
        vendor_id=parts[3],
        delivery_fee_ngwee=int(parts[4]),
    )


def _vendor_owner_user_id(vendor_id: str) -> str | None:
    vendor_sql = sql_uuid(vendor_id, "vendor_id")
    result = run_sql_script(
        f"SELECT owner_user_id::text FROM public.vendors WHERE id = {vendor_sql} LIMIT 1;"
    )
    if not result.ok or not result.rows:
        return None
    return result.rows[0].strip() or None


def _parse_ts(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    # psql renders "2026-07-11 12:00:00+00"; normalise the space and tz for fromisoformat.
    normalized = value.strip().replace(" ", "T", 1).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _provider_marked_at(job_id: str) -> datetime | None:
    """Earliest provider-complete marker timestamp for the job, or None."""
    job_sql = sql_uuid(job_id, "job_id")
    action_sql = sql_literal(PROVIDER_COMPLETE_ACTION)
    result = run_sql_script(
        f"""
SELECT min(al.at)::text
FROM public.audit_log al
WHERE al.entity_type = 'job'
  AND al.entity_id = {job_sql}
  AND al.action = {action_sql};
"""
    )
    if not result.ok or not result.rows:
        return None
    return _parse_ts(result.rows[0])


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _record_audit(*, actor_id: str | None, action: str, job_id: str, after: str) -> None:
    actor_sql = sql_uuid(actor_id, "actor") if actor_id else "NULL"
    job_sql = sql_uuid(job_id, "job_id")
    run_sql_script(
        f"""
INSERT INTO public.audit_log (actor, action, entity_type, entity_id, after)
VALUES ({actor_sql}, {sql_literal(action)}, 'job', {job_sql}, {sql_literal(after)}::jsonb);
"""
    )


def _complete_order(order_id: str, *, actor_id: str, is_system: bool) -> None:
    """Flip the service order placed → completed (server-controlled status update).

    Guarded by ``guard_orders_status_update`` (the service connection is permitted).
    The audit trigger (0014) writes the placed→completed ``order_events`` row from the
    transaction-local ``app.order_actor``/``app.order_note`` GUCs. Because each
    ``run_sql_script`` spawns its OWN psql process, the GUCs are primed in the SAME
    script (and transaction) as the UPDATE — otherwise the trigger falls back to a
    NULL ``auth.uid()`` and records a NULL actor (#8). The idempotent ``status =
    placed`` guard makes a re-run a safe no-op.
    """
    order_sql = sql_uuid(order_id, "order_id")
    note = "service job auto-confirmed" if is_system else "service job confirmed by customer"
    run_sql_script(
        f"""
BEGIN;
SELECT set_config('{ORDER_ACTOR_GUC}', {sql_literal(actor_id)}, true);
SELECT set_config('{ORDER_NOTE_GUC}', {sql_literal(note)}, true);
UPDATE public.orders
SET status = '{COMPLETED_ORDER_STATUS}'
WHERE id = {order_sql} AND status = '{PENDING_ORDER_STATUS}';
COMMIT;
"""
    )


def _complete_job(job_id: str) -> None:
    job_sql = sql_uuid(job_id, "job_id")
    run_sql_script(
        f"""
UPDATE public.jobs SET status = 'completed'
WHERE id = {job_sql} AND status = 'accepted';
"""
    )


def _order_gross_ngwee(order_id: str, delivery_fee_ngwee: int) -> int:
    order_sql = sql_uuid(order_id, "order_id")
    result = run_sql_script(
        f"""
SELECT coalesce(sum(qty * unit_price_ngwee), 0)::text
FROM public.order_items
WHERE order_id = {order_sql};
"""
    )
    subtotal = int(result.rows[0]) if result.ok and result.rows and result.rows[0].isdigit() else 0
    return subtotal + int(delivery_fee_ngwee)


def _load_commission_snapshot(order_id: str) -> dict[str, Any]:
    import json

    order_sql = sql_uuid(order_id, "order_id")
    result = run_sql_script(
        f"SELECT commission_snapshot::text FROM public.orders WHERE id = {order_sql} LIMIT 1;"
    )
    if not result.ok or not result.rows or not result.rows[0].strip():
        return {}
    try:
        loaded = json.loads(result.rows[0])
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _settle_balance(order_id: str, balance_ngwee: int) -> None:
    """Settle the balance collection into escrow via the M08 CHARGE_RECEIVED template.

    Idempotent on ``charge-balance-{order_id}`` so a retried/auto confirm never
    double-credits. Skipped for 100%-deposit jobs (balance == 0).
    """
    if balance_ngwee <= 0:
        return
    post_transaction(
        idempotency_key=f"charge-balance-{order_id}",
        template=LedgerTemplate.CHARGE_RECEIVED,
        order_id=order_id,
        gross_ngwee=balance_ngwee,
    )


def _assert_service_release_allowed(*, order_id: str, status: str) -> None:
    """Fail closed when refund/dispute/cancel state blocks vendor release."""
    blocked = release_blocked_reason(status=status, order_id=order_id)
    if blocked is not None:
        raise AppError(
            code="release_blocked",
            message="Service escrow release is blocked for this order",
            http_status=409,
            details={"reason": blocked},
        )
    try:
        if order_has_open_dispute(order_id):
            raise AppError(
                code="release_blocked",
                message="Service escrow release is held while a dispute is open",
                http_status=409,
                details={"reason": "dispute_open"},
            )
    except ReleaseAccountingError as exc:
        raise AppError(
            code="release_blocked",
            message="Service escrow release cannot verify dispute status",
            http_status=503,
            details={"reason": str(exc) if str(exc) else "dispute_lookup_failed"},
        ) from exc


def _require_service_release_amounts(
    *, order_id: str, delivery_fee_ngwee: int
) -> tuple[dict[str, Any], int]:
    """Load snapshot + net; fail closed before any confirm-side money movement."""
    gross = _order_gross_ngwee(order_id, delivery_fee_ngwee)
    snapshot = _load_commission_snapshot(order_id)
    try:
        amounts = compute_release_amounts(
            order_id=order_id,
            gross_ngwee=gross,
            commission_snapshot=snapshot,
        )
    except ReleaseAccountingError as exc:
        raise AppError(
            code="invalid_commission_snapshot",
            message="Service escrow release requires a usable commission snapshot",
            http_status=409,
            details={"reason": str(exc) if str(exc) else "invalid_commission_snapshot"},
        ) from exc
    return snapshot, amounts.net_ngwee


def _release_service_order(order_id: str, vendor_id: str, net_ngwee: int) -> tuple[bool, int]:
    """Post the single vendor release for the whole order. Returns (created, net_ngwee).

    Reuses the order engine's ``release-{order_id}`` idempotency key — the release is
    posted at most once for the order no matter how many times confirm runs.
    """
    posted = post_transaction(
        idempotency_key=release_idempotency_key(order_id),
        template=LedgerTemplate.RELEASE_TO_VENDOR,
        order_id=order_id,
        net_ngwee=net_ngwee,
        vendor_id=vendor_id,
    )
    return posted.created, net_ngwee


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def mark_job_complete(job_id: str, provider_user_id: str) -> MarkCompleteResult:
    """Provider marks a job complete. Provider-scoped; idempotent (no double marker)."""
    order = _load_service_order(job_id)
    if order is None:
        raise AppError(code="not_found", message="Job order not found", http_status=404)

    owner = _vendor_owner_user_id(order.vendor_id)
    if owner is None or owner != provider_user_id:
        raise AppError(
            code="forbidden",
            message="Only the assigned provider may mark this job complete",
            http_status=403,
            details={"message_key": "services.completion.errors.notProvider"},
        )

    if _provider_marked_at(job_id) is not None:
        return MarkCompleteResult(job_id=job_id, order_id=order.order_id, marked=False)

    _record_audit(
        actor_id=provider_user_id,
        action=PROVIDER_COMPLETE_ACTION,
        job_id=job_id,
        after='{"status":"provider_completed"}',
    )
    return MarkCompleteResult(job_id=job_id, order_id=order.order_id, marked=True)


def confirm_job_completion(
    job_id: str,
    *,
    actor_id: str,
    is_system: bool = False,
) -> ConfirmResult:
    """Confirm completion → balance leg + settlement + single release.

    Customer-scoped for interactive confirm; ``is_system`` skips ownership for the
    auto-confirm tick. Double-confirm is an idempotent no-op (order already completed
    → no second balance leg, no second release).
    """
    order = _load_service_order(job_id)
    if order is None:
        raise AppError(code="not_found", message="Job order not found", http_status=404)

    if not is_system and order.customer_id != actor_id:
        raise AppError(
            code="forbidden",
            message="Only the job owner may confirm completion",
            http_status=403,
            details={"message_key": "services.completion.errors.notOwner"},
        )

    # Idempotent no-op — already confirmed/completed.
    if order.status == COMPLETED_ORDER_STATUS:
        return ConfirmResult(
            job_id=job_id,
            order_id=order.order_id,
            status=COMPLETED_ORDER_STATUS,
            already_confirmed=True,
            balance_ngwee=0,
            balance_created=False,
            released=False,
            release_created=False,
            net_ngwee=0,
        )

    if order.status != PENDING_ORDER_STATUS:
        raise AppError(
            code="invalid_transition",
            message="Job cannot be confirmed from its current state",
            http_status=409,
            details={"status": order.status},
        )

    if _provider_marked_at(job_id) is None:
        raise AppError(
            code="invalid_transition",
            message="Provider has not marked this job complete yet",
            http_status=409,
            details={"message_key": "services.completion.errors.notMarked"},
        )

    # These steps run as independent psql processes (no enclosing transaction), so
    # ordering must preserve the net invariant on any partial failure:
    #   an order can NEVER be 'completed' unless its vendor RELEASE has posted.
    # The release, balance leg, and settlement are each idempotent (keyed by
    # order_id), so a partial failure leaves the order at 'placed' and a re-run —
    # interactive retry or the auto-confirm tick — safely re-drives to completion
    # with the release posted exactly once. The release therefore precedes the
    # placed→completed flip; nothing between them can strand escrow.
    #
    # 0. Fail closed on cancel/refund/dispute/invalid snapshot before any money movement.
    _assert_service_release_allowed(order_id=order.order_id, status=order.status)
    snapshot, net_ngwee = _require_service_release_amounts(
        order_id=order.order_id, delivery_fee_ngwee=order.delivery_fee_ngwee
    )
    # 0b. D17 single-drain claim before capture/release (blocks concurrent refund).
    try:
        claim_release_gate(order.order_id)
    except OrderMoneyGateError as exc:
        raise AppError(
            code="release_blocked",
            message="Service escrow release is blocked for this order",
            http_status=409 if exc.code == "order_refunded" else 503,
            details={"reason": exc.code},
        ) from exc
    # 1. Balance leg on the SAME order (idempotent; commission snapshot untouched).
    balance = create_balance_item(order.order_id)
    # 2. Settle the balance collection into escrow (M08 charge; idempotent).
    _settle_balance(order.order_id, balance.balance_ngwee)
    # 2b. Capture platform commission from escrow BEFORE the release (idempotent;
    #     mirrors COD/product capture-then-release) so commission_revenue is recognized
    #     and escrow drains to net. Single snapshot — never re-captured across legs.
    capture_order_commission(
        order_id=order.order_id,
        commission_snapshot=snapshot,
        idempotency_key_prefix=release_idempotency_key(order.order_id),
    )
    # 3. Release the whole order to the vendor EXACTLY ONCE — BEFORE completing, so
    #    completion implies the vendor has been paid (no stranded escrow).
    release_created, net_ngwee = _release_service_order(order.order_id, order.vendor_id, net_ngwee)
    # 4. Complete the order (unlocks the verified-engagement review); audited with the
    #    real confirming actor via the app.order_actor/app.order_note GUCs.
    _complete_order(order.order_id, actor_id=actor_id, is_system=is_system)
    # 5. Complete the job.
    _complete_job(job_id)
    _record_audit(
        actor_id=None if is_system else actor_id,
        action=CONFIRM_ACTION,
        job_id=job_id,
        after='{"status":"completed"}',
    )

    return ConfirmResult(
        job_id=job_id,
        order_id=order.order_id,
        status=COMPLETED_ORDER_STATUS,
        already_confirmed=False,
        balance_ngwee=balance.balance_ngwee,
        balance_created=balance.created,
        released=True,
        release_created=release_created,
        net_ngwee=net_ngwee,
    )


def job_review_unlocked(job_id: str) -> bool:
    """True once the service order is completed — the verified-engagement review gate."""
    order = _load_service_order(job_id)
    return order is not None and order.status in REVIEW_UNLOCK_STATUSES


def _list_auto_confirm_due(*, now: datetime, limit: int) -> list[tuple[str, str]]:
    """(job_id, order_id) pairs whose auto-confirm window has elapsed and still 'placed'."""
    hours = _read_config_int(CONFIG_KEY_AUTOCONFIRM_HOURS, DEFAULT_JOB_AUTOCONFIRM_HOURS)
    deadline = now - timedelta(hours=hours)
    deadline_sql = sql_literal(deadline.astimezone(UTC).isoformat())
    action_sql = sql_literal(PROVIDER_COMPLETE_ACTION)
    result = run_sql_script(
        f"""
SELECT DISTINCT ois.job_id::text || '|' || o.id::text
FROM public.audit_log al
JOIN public.order_item_services ois ON ois.job_id = al.entity_id
JOIN public.order_items oi ON oi.id = ois.order_item_id AND oi.item_kind = 'service_deposit'
JOIN public.orders o ON o.id = oi.order_id
WHERE al.entity_type = 'job'
  AND al.action = {action_sql}
  AND al.at <= {deadline_sql}::timestamptz
  AND o.status = '{PENDING_ORDER_STATUS}'
ORDER BY 1
LIMIT {int(limit)};
"""
    )
    if not result.ok:
        return []
    pairs: list[tuple[str, str]] = []
    for row in result.rows:
        parts = row.split("|", 1)
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def auto_confirm_due_jobs(
    *, now: datetime | None = None, limit: int = DEFAULT_BATCH_LIMIT
) -> AutoConfirmResult:
    """Confirm every job whose provider-complete window has elapsed. Idempotent."""
    effective_now = now or datetime.now(UTC)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=UTC)

    due = _list_auto_confirm_due(now=effective_now, limit=limit)
    confirmed = 0
    skipped = 0
    for job_id, _order_id in due:
        result = confirm_job_completion(job_id, actor_id=SYSTEM_ACTOR_ID, is_system=True)
        if result.already_confirmed:
            skipped += 1
        else:
            confirmed += 1
    return AutoConfirmResult(scanned=len(due), confirmed=confirmed, skipped=skipped)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def _rate_limit(
    request: Request,
    user_id: str,
    service_client: _ServiceRoleClient,
    *,
    scope: str,
) -> None:
    ip = get_client_ip(request)
    allowed_ip, retry_ip = bump_rate_counter(
        scope=f"{scope}_ip",
        key=ip,
        window=timedelta(minutes=1),
        limit=30,
        client=service_client.client,
    )
    if not allowed_ip:
        raise_rate_limited(
            retry_after=retry_ip,
            message_key="services.completion.errors.rateLimited",
            message="Too many completion requests",
        )
    allowed_user, retry_user = bump_rate_counter(
        scope=f"{scope}_user",
        key=user_id,
        window=timedelta(minutes=1),
        limit=10,
        client=service_client.client,
    )
    if not allowed_user:
        raise_rate_limited(
            retry_after=retry_user,
            message_key="services.completion.errors.rateLimited",
            message="Too many completion requests",
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class MarkCompleteResponse(StrictModel):
    job_id: str
    order_id: str
    marked: bool


class ConfirmResponse(StrictModel):
    job_id: str
    order_id: str
    status: str
    already_confirmed: bool
    balance_ngwee: int
    released: bool


class BatchJobRequest(StrictModel):
    limit: int = Field(default=DEFAULT_BATCH_LIMIT, ge=1, le=MAX_BATCH_LIMIT)


class AutoConfirmResponse(StrictModel):
    scanned: int
    confirmed: int
    skipped: int


# ---------------------------------------------------------------------------
# Internal auto-confirm guard
# ---------------------------------------------------------------------------


def _expected_autoconfirm_token() -> str:
    try:
        return resolve_internal_token(
            _AUTOCONFIRM_TOKEN_ENV,
            dev_default=_DEFAULT_AUTOCONFIRM_TOKEN,
        )
    except InternalTokenMisconfigured as exc:
        raise AppError(
            code="configuration_error",
            message=str(exc),
            http_status=503,
        ) from exc


async def require_autoconfirm_token(request: Request) -> None:
    expected = _expected_autoconfirm_token()
    provided = request.headers.get("X-Internal-Token")
    if not provided or provided != expected:
        raise AppError(
            code="unauthorized",
            message="Invalid or missing internal job completion token",
            http_status=401,
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/complete", response_model=MarkCompleteResponse)
async def mark_complete(
    job_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> MarkCompleteResponse:
    """Provider marks the job complete (starts the customer-confirm / auto-confirm clock)."""
    _rate_limit(request, current_user.id, service_client, scope="job_complete")
    result = mark_job_complete(job_id, current_user.id)
    return MarkCompleteResponse(
        job_id=result.job_id, order_id=result.order_id, marked=result.marked
    )


@router.post("/jobs/{job_id}/confirm", response_model=ConfirmResponse)
async def confirm_completion(
    job_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service_client: Annotated[_ServiceRoleClient, Depends(get_supabase_client)],
) -> ConfirmResponse:
    """Customer confirms completion → balance settlement + single escrow release."""
    _rate_limit(request, current_user.id, service_client, scope="job_confirm")
    result = confirm_job_completion(job_id, actor_id=current_user.id, is_system=False)
    return ConfirmResponse(
        job_id=result.job_id,
        order_id=result.order_id,
        status=result.status,
        already_confirmed=result.already_confirmed,
        balance_ngwee=result.balance_ngwee,
        released=result.released,
    )


@router.post(
    "/internal/job-completion/auto-confirm",
    response_model=AutoConfirmResponse,
    dependencies=[Depends(require_autoconfirm_token)],
)
async def auto_confirm_batch(body: BatchJobRequest | None = None) -> AutoConfirmResponse:
    """Cron tick: auto-confirm every job past its provider-complete window."""
    request = body or BatchJobRequest()
    result = auto_confirm_due_jobs(limit=request.limit)
    return AutoConfirmResponse(
        scanned=result.scanned, confirmed=result.confirmed, skipped=result.skipped
    )
