"""RFQ engagement — accept quote → deposit + balance money spine via escrow (M11-P04).

MONEY-CRITICAL. Integer ngwee everywhere; no float on money.

Commission single-capture invariant
------------------------------------
The platform commission is **12% of the TOTAL job value** (deposit + balance),
snapshotted ONCE onto the accepted order's ``commission_snapshot`` at accept time.

There is exactly ONE order per accepted job. The deposit and (later) balance are
two ``order_items`` on that SAME order whose unit prices sum to the total job value.
Because ``compute_order_commission`` derives commission from the single order-level
snapshot (basis = total job value), the merged escrow-release / COD paths capture
commission EXACTLY ONCE for the whole order — it is never captured on the deposit
leg and never re-captured on the balance leg. Adding the balance item later does not
touch the snapshot, so the single-count and the rate are immune to later changes.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.errors import AppError
from app.services.commissions.engine import compute_order_commission
from app.services.notifications.dedupe import build_dedupe_key
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.stock.claim import sql_uuid

# Deposit percentage is admin-tunable via platform_config; whole-percent integer.
CONFIG_KEY_DEPOSIT_PCT = "service_deposit_pct"
DEFAULT_SERVICE_DEPOSIT_PCT = 50

# Services commission category (0008 seed: ('services', 1200) = 12%).
SERVICE_COMMISSION_CATEGORY = "services"
DEFAULT_SERVICE_COMMISSION_BPS = 1200

ACCEPTABLE_JOB_STATUSES = frozenset({"open", "quoted"})
ACCEPT_OUTBOX_EVENT = "service_quote_accepted"
OUTBOX_CHANNEL = "whatsapp"

# Services are provider-delivered; orders.fulfilment check allows delivery|pickup.
SERVICE_FULFILMENT = "pickup"


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class AcceptResult:
    job_id: str
    quote_id: str
    checkout_group_id: str
    order_id: str
    vendor_id: str
    deposit_order_item_id: str
    total_job_ngwee: int
    deposit_ngwee: int
    balance_ngwee: int
    commission_ngwee: int
    commission_rate_bps: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class BalanceItemResult:
    order_id: str
    balance_order_item_id: str | None
    balance_ngwee: int
    created: bool


def accept_idempotency_key(quote_id: str) -> str:
    """Stable checkout-group idempotency key for accepting one quote."""
    return f"svc-accept-{quote_id}"


def compute_deposit_ngwee(*, total_job_ngwee: int, deposit_pct: int) -> int:
    """Deposit = total * pct%, half-up rounded to integer ngwee (no float)."""
    if total_job_ngwee <= 0:
        msg = "total_job_ngwee must be positive"
        raise ValueError(msg)
    if deposit_pct <= 0 or deposit_pct > 100:
        msg = "deposit_pct must be in 1..100"
        raise ValueError(msg)
    return (total_job_ngwee * deposit_pct + 50) // 100


def build_service_commission_snapshot(
    *,
    total_job_ngwee: int,
    rate_bps: int,
    job_id: str,
    quote_id: str,
) -> dict[str, Any]:
    """Snapshot 12% of the TOTAL job value as a single-line order commission snapshot.

    Basis = total job value (deposit + balance). This is the single source the
    release/COD paths read commission from, guaranteeing one capture for the order.
    """
    return {
        "lines": [
            {
                "listing_id": None,
                "category_key": SERVICE_COMMISSION_CATEGORY,
                "rate_bps": rate_bps,
                "qty": 1,
                "unit_price_ngwee": total_job_ngwee,
                "line_total_ngwee": total_job_ngwee,
                "wholesale": False,
            }
        ],
        "rate_bps": rate_bps,
        "basis": "total_job_value",
        "job_id": job_id,
        "quote_id": quote_id,
    }


def _sql_json(value: Mapping[str, Any]) -> str:
    return sql_literal(json.dumps(value, separators=(",", ":"), sort_keys=True))


def _read_config_int(key: str, default: int) -> int:
    key_sql = sql_literal(key)
    script = f"""
SELECT value::text
FROM public.platform_config
WHERE key = {key_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return default
    raw = result.rows[0].strip()
    if raw.isdigit():
        return int(raw)
    if raw.startswith('"') and raw.endswith('"') and raw[1:-1].isdigit():
        return int(raw[1:-1])
    return default


def _read_service_commission_bps() -> int:
    category_sql = sql_literal(SERVICE_COMMISSION_CATEGORY)
    script = f"""
SELECT rate_bps::text
FROM public.commission_rates
WHERE category_key = {category_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows or not result.rows[0].strip().isdigit():
        return DEFAULT_SERVICE_COMMISSION_BPS
    return int(result.rows[0].strip())


def _load_job(job_id: str) -> tuple[str, str] | None:
    """Return (customer_id, status) for a job, or None if missing."""
    job_sql = sql_uuid(job_id, "job_id")
    script = f"""
SELECT customer_id::text || '|' || status
FROM public.jobs
WHERE id = {job_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _load_quote(quote_id: str) -> tuple[str, str, int, str] | None:
    """Return (job_id, provider_vendor_id, amount_ngwee, status) or None if missing."""
    quote_sql = sql_uuid(quote_id, "quote_id")
    script = f"""
SELECT job_id::text || '|' || provider_vendor_id::text
       || '|' || amount_ngwee::text || '|' || status
FROM public.job_quotes
WHERE id = {quote_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    parts = result.rows[0].split("|", 3)
    if len(parts) != 4 or not parts[2].isdigit():
        return None
    return parts[0], parts[1], int(parts[2]), parts[3]


def _parse_snapshot(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _snapshot_total_ngwee(snapshot: Mapping[str, Any]) -> int:
    lines = snapshot.get("lines")
    if not isinstance(lines, list):
        return 0
    total = 0
    for line in lines:
        if isinstance(line, dict):
            total += int(line.get("line_total_ngwee", 0))
    return total


def _load_existing_accept(quote_id: str) -> AcceptResult | None:
    """Idempotent replay: rebuild the AcceptResult from a prior accept, if any."""
    key_sql = sql_literal(accept_idempotency_key(quote_id))
    script = f"""
SELECT
  cg.id::text || '|' || o.id::text || '|' || o.vendor_id::text
  || '|' || oi.id::text || '|' || oi.unit_price_ngwee::text
  || '|' || ois.job_id::text || '|' || o.commission_snapshot::text
FROM public.checkout_groups cg
JOIN public.orders o ON o.checkout_group_id = cg.id
JOIN public.order_items oi ON oi.order_id = o.id AND oi.item_kind = 'service_deposit'
JOIN public.order_item_services ois ON ois.order_item_id = oi.id
WHERE cg.idempotency_key = {key_sql}
LIMIT 1;
"""
    result = run_sql_script(script)
    if not result.ok or not result.rows:
        return None
    # commission_snapshot is JSON (may contain '|'); split off the fixed prefix fields only.
    parts = result.rows[0].split("|", 6)
    if len(parts) != 7:
        return None
    checkout_group_id, order_id, vendor_id, item_id, deposit_raw, job_id, snapshot_raw = parts
    snapshot = _parse_snapshot(snapshot_raw)
    commission = compute_order_commission(snapshot)
    total = _snapshot_total_ngwee(snapshot)
    deposit = int(deposit_raw) if deposit_raw.isdigit() else 0
    return AcceptResult(
        job_id=job_id,
        quote_id=quote_id,
        checkout_group_id=checkout_group_id,
        order_id=order_id,
        vendor_id=vendor_id,
        deposit_order_item_id=item_id,
        total_job_ngwee=total,
        deposit_ngwee=deposit,
        balance_ngwee=total - deposit,
        commission_ngwee=commission.commission_ngwee,
        commission_rate_bps=int(snapshot.get("rate_bps", DEFAULT_SERVICE_COMMISSION_BPS)),
        replayed=True,
    )


def accept_quote(
    service_client: ServiceRoleClient,
    *,
    job_id: str,
    quote_id: str,
    customer_id: str,
) -> AcceptResult:
    """Accept a quote → create the deposit money spine (one order, single snapshot).

    Owner-scoped: only the job's customer may accept. Idempotent per quote via the
    checkout-group idempotency key. The deposit is charged through the standard M08
    checkout/payment path (the returned checkout_group is payable = deposit_ngwee).
    """
    _ = service_client  # DB access via run_sql_script (SUPABASE_DB_URL), like the spine.

    replay = _load_existing_accept(quote_id)
    if replay is not None:
        return replay

    job = _load_job(job_id)
    if job is None:
        raise AppError(code="not_found", message="Job not found", http_status=404)
    job_customer_id, job_status = job
    if job_customer_id != customer_id:
        raise AppError(
            code="forbidden",
            message="Only the job owner may accept a quote",
            http_status=403,
            details={"message_key": "services.accept.errors.notOwner"},
        )
    if job_status not in ACCEPTABLE_JOB_STATUSES:
        raise AppError(
            code="invalid_transition",
            message="Job is not open for acceptance",
            http_status=409,
            details={"status": job_status},
        )

    quote = _load_quote(quote_id)
    if quote is None:
        raise AppError(code="not_found", message="Quote not found", http_status=404)
    quote_job_id, provider_vendor_id, total_job_ngwee, quote_status = quote
    if quote_job_id != job_id:
        raise AppError(
            code="validation_error",
            message="Quote does not belong to this job",
            http_status=422,
            details={"message_key": "services.accept.errors.mismatch"},
        )
    if quote_status != "submitted":
        raise AppError(
            code="invalid_transition",
            message="Only submitted quotes can be accepted",
            http_status=409,
            details={"status": quote_status},
        )

    deposit_pct = _read_config_int(CONFIG_KEY_DEPOSIT_PCT, DEFAULT_SERVICE_DEPOSIT_PCT)
    rate_bps = _read_service_commission_bps()
    deposit_ngwee = compute_deposit_ngwee(
        total_job_ngwee=total_job_ngwee, deposit_pct=deposit_pct
    )
    balance_ngwee = total_job_ngwee - deposit_ngwee
    snapshot = build_service_commission_snapshot(
        total_job_ngwee=total_job_ngwee,
        rate_bps=rate_bps,
        job_id=job_id,
        quote_id=quote_id,
    )
    commission_ngwee = compute_order_commission(snapshot).commission_ngwee

    checkout_group_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    deposit_item_id = str(uuid.uuid4())

    idem_sql = sql_literal(accept_idempotency_key(quote_id))
    cg_sql = sql_uuid(checkout_group_id, "checkout_group_id")
    order_sql = sql_uuid(order_id, "order_id")
    item_sql = sql_uuid(deposit_item_id, "order_item_id")
    vendor_sql = sql_uuid(provider_vendor_id, "vendor_id")
    customer_sql = sql_uuid(customer_id, "customer_id")
    job_sql = sql_uuid(job_id, "job_id")
    quote_sql = sql_uuid(quote_id, "quote_id")
    snapshot_sql = _sql_json(snapshot)

    dedupe_key = build_dedupe_key(ACCEPT_OUTBOX_EVENT, f"{job_id}:{quote_id}", OUTBOX_CHANNEL)
    payload = {
        "job_id": job_id,
        "quote_id": quote_id,
        "vendor_id": provider_vendor_id,
        "order_id": order_id,
        "deposit_ngwee": deposit_ngwee,
        "total_job_ngwee": total_job_ngwee,
    }

    script = f"""
BEGIN;
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
) VALUES (
  {cg_sql}, {customer_sql}, {idem_sql}, {deposit_ngwee}, 0, {deposit_ngwee}, 'pending'
);
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
  delivery_fee_ngwee, cod, commission_snapshot
) VALUES (
  {order_sql}, {cg_sql}, {vendor_sql}, {customer_sql}, 'placed', '{SERVICE_FULFILMENT}',
  0, false, {snapshot_sql}::jsonb
);
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES (
  {item_sql}, {order_sql}, 'service_deposit', 1, {deposit_ngwee}, NULL
);
INSERT INTO public.order_item_services (order_item_id, job_id, quote_id)
VALUES ({item_sql}, {job_sql}, {quote_sql});
UPDATE public.job_quotes SET status = 'accepted'
  WHERE id = {quote_sql} AND status = 'submitted';
UPDATE public.jobs SET status = 'accepted'
  WHERE id = {job_sql} AND status IN ('open', 'quoted');
INSERT INTO public.notification_outbox (dedupe_key, channel, template, payload, status)
VALUES ({sql_literal(dedupe_key)}, '{OUTBOX_CHANNEL}', {sql_literal(ACCEPT_OUTBOX_EVENT)},
  {_sql_json(payload)}::jsonb, 'pending')
ON CONFLICT (dedupe_key) DO NOTHING;
COMMIT;
"""
    result = run_sql_script(script)
    if not result.ok:
        if "duplicate key value violates unique constraint" in (result.error or ""):
            replay = _load_existing_accept(quote_id)
            if replay is not None:
                return replay
        raise AppError(
            code="internal_error",
            message="Failed to accept quote",
            http_status=500,
            details={"error": result.error},
        )

    return AcceptResult(
        job_id=job_id,
        quote_id=quote_id,
        checkout_group_id=checkout_group_id,
        order_id=order_id,
        vendor_id=provider_vendor_id,
        deposit_order_item_id=deposit_item_id,
        total_job_ngwee=total_job_ngwee,
        deposit_ngwee=deposit_ngwee,
        balance_ngwee=balance_ngwee,
        commission_ngwee=commission_ngwee,
        commission_rate_bps=rate_bps,
        replayed=False,
    )


def create_balance_item(order_id: str) -> BalanceItemResult:
    """Create the ``service_balance`` order item at completion (for M11-P05).

    Balance = total job value (snapshot basis) − deposit, computed on the SAME order.
    Does NOT touch the commission snapshot: commission stays a single capture on the
    total. Idempotent — a second call returns the existing balance item.
    """
    order_sql = sql_uuid(order_id, "order_id")

    existing = run_sql_script(
        f"""
SELECT id::text || '|' || unit_price_ngwee::text
FROM public.order_items
WHERE order_id = {order_sql} AND item_kind = 'service_balance'
LIMIT 1;
"""
    )
    if existing.ok and existing.rows:
        row_parts = existing.rows[0].split("|", 1)
        balance_item_id = row_parts[0]
        balance = int(row_parts[1]) if len(row_parts) == 2 and row_parts[1].isdigit() else 0
        return BalanceItemResult(
            order_id=order_id,
            balance_order_item_id=balance_item_id,
            balance_ngwee=balance,
            created=False,
        )

    order = run_sql_script(
        f"""
SELECT commission_snapshot::text
FROM public.orders
WHERE id = {order_sql}
LIMIT 1;
"""
    )
    if not order.ok or not order.rows:
        raise AppError(code="not_found", message="Order not found", http_status=404)
    snapshot = _parse_snapshot(order.rows[0])
    total = _snapshot_total_ngwee(snapshot)

    deposit_row = run_sql_script(
        f"""
SELECT coalesce(sum(unit_price_ngwee * qty), 0)::text
FROM public.order_items
WHERE order_id = {order_sql} AND item_kind = 'service_deposit';
"""
    )
    deposit = (
        int(deposit_row.rows[0])
        if deposit_row.ok and deposit_row.rows and deposit_row.rows[0].isdigit()
        else 0
    )
    balance = total - deposit
    if balance <= 0:
        # 100% deposit — nothing left to invoice at completion.
        return BalanceItemResult(
            order_id=order_id,
            balance_order_item_id=None,
            balance_ngwee=0,
            created=False,
        )

    link = run_sql_script(
        f"""
SELECT ois.job_id::text || '|' || ois.quote_id::text
FROM public.order_item_services ois
JOIN public.order_items oi ON oi.id = ois.order_item_id
WHERE oi.order_id = {order_sql} AND oi.item_kind = 'service_deposit'
LIMIT 1;
"""
    )
    job_link = "NULL"
    quote_link = "NULL"
    if link.ok and link.rows:
        link_parts = link.rows[0].split("|", 1)
        if len(link_parts) == 2:
            job_link = sql_uuid(link_parts[0], "job_id")
            quote_link = sql_uuid(link_parts[1], "quote_id")

    balance_item_id = str(uuid.uuid4())
    item_sql = sql_uuid(balance_item_id, "order_item_id")
    result = run_sql_script(
        f"""
BEGIN;
INSERT INTO public.order_items (
  id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
) VALUES (
  {item_sql}, {order_sql}, 'service_balance', 1, {balance}, NULL
);
INSERT INTO public.order_item_services (order_item_id, job_id, quote_id)
VALUES ({item_sql}, {job_link}, {quote_link});
COMMIT;
"""
    )
    if not result.ok:
        raise AppError(
            code="internal_error",
            message="Failed to create balance item",
            http_status=500,
            details={"error": result.error},
        )
    return BalanceItemResult(
        order_id=order_id,
        balance_order_item_id=balance_item_id,
        balance_ngwee=balance,
        created=True,
    )
