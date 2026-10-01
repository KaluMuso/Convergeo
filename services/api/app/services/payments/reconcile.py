"""Payment reconciliation poller and daily Lenco-vs-ledger report."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol, cast
from uuid import uuid4

import httpx
from app.services.escrow.release_accounting import build_release_accounting_day_totals
from app.services.ledger.engine import account_balance_ngwee, resolve_account_id
from app.services.ledger.templates import AccountRef
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.payments.base import ProviderOutcome, QueryStatusRequest, QueryStatusResult
from app.services.payments.lenco.config import get_api_token, get_base_url
from app.services.payments.lenco.reconciliation import LencoReconciliationAdapter
from app.services.payments.money import major_str_to_ngwee
from app.services.payments.reconciliation_matcher import (
    collect_provider_pages,
    match_movements,
)
from app.services.payments.reconciliation_reader import PostgrestReconciliationReader
from app.services.payments.reconciliation_reports import ReconciliationReportStore
from app.services.payments.state import (
    SYSTEM_ACTOR_ID,
    PaymentStatus,
    PaymentTransitionError,
    apply_payment_status,
    collection_observation_from_query,
    lenco_collection_status_to_payment_status,
    process_webhook_event,
    validate_query_collection_observation,
)

logger = logging.getLogger(__name__)

# Non-terminal payment states polled every ~30 min (closes lost-webhook gaps).
NON_TERMINAL_POLL_STATUSES: tuple[str, ...] = (
    PaymentStatus.INITIATED.value,
    PaymentStatus.USSD_PUSHED.value,
    PaymentStatus.PAY_OFFLINE.value,
    "pending",  # legacy rows pre-0016
)

DEFAULT_POLL_AGE_MINUTES = 2
_LENCO_REF_RE = re.compile(r"(?:/|\s)([A-Za-z0-9._-]+)\s*$")
_CLIENT_REF_RE = re.compile(r"^(ord|pay|rfd)-[-._A-Za-z0-9]+$")


class ServiceRoleClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class PollResult:
    scanned: int
    updated: int
    unchanged: int
    errors: int


@dataclass(frozen=True, slots=True)
class DrainResult:
    scanned: int
    applied: int
    skipped: int
    errors: int


# Cap the batch so one tick can't scan an unbounded backlog. Ordered oldest-first
# so a stuck (error) row can never starve newer webhooks within the same batch.
DEFAULT_WEBHOOK_DRAIN_LIMIT = 200


@dataclass(frozen=True, slots=True)
class LencoAccountSnapshot:
    account_id: str
    available_balance_ngwee: int
    ledger_balance_ngwee: int


@dataclass(frozen=True, slots=True)
class LencoTransactionRow:
    id: str
    amount_ngwee: int
    txn_type: str
    narration: str
    reference: str | None
    datetime: str


@dataclass(frozen=True, slots=True)
class LedgerDayRow:
    transaction_id: str
    kind: str
    payment_id: str | None
    lenco_reference: str | None
    amount_ngwee: int
    created_at: str


@dataclass(frozen=True, slots=True)
class ReconciliationDiff:
    balance_diff_ngwee: int
    orphaned_lenco: tuple[dict[str, Any], ...]
    ledger_only: tuple[dict[str, Any], ...]
    ngwee_mismatches: tuple[dict[str, Any], ...]

    @property
    def has_discrepancies(self) -> bool:
        return (
            self.balance_diff_ngwee != 0
            or bool(self.orphaned_lenco)
            or bool(self.ledger_only)
            or bool(self.ngwee_mismatches)
        )


@dataclass(frozen=True, slots=True)
class DailyReportResult:
    report_id: str
    report_date: date
    created: bool
    summary: dict[str, Any]
    discrepancies: dict[str, Any]
    clean: bool
    certifiable: bool = False
    input_fingerprint: str | None = None


class ImmutableReportConflict(RuntimeError):
    """An immutable daily report already exists for different observed inputs."""


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


def extract_lenco_reference(narration: str) -> str | None:
    """Best-effort parse of Lenco narration tail (e.g. 'Transfer / 240730006')."""
    match = _LENCO_REF_RE.search(narration.strip())
    if match is None:
        return None
    token = match.group(1)
    if _CLIENT_REF_RE.match(token):
        return token
    return token


def _day_bounds(report_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(report_date, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


async def _lenco_get(path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {get_api_token()}"}
    async with httpx.AsyncClient(
        base_url=get_base_url(),
        timeout=30.0,
    ) as client:
        response = await client.get(path, headers=headers, params=params)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        msg = "unexpected Lenco response envelope"
        raise TypeError(msg)
    if body.get("status") is False:
        msg = str(body.get("message", "Lenco request failed"))
        raise RuntimeError(msg)
    return cast(dict[str, Any], body)


async def fetch_lenco_primary_account() -> LencoAccountSnapshot:
    """Return the first Lenco merchant account (platform settlement account)."""
    envelope = await _lenco_get("/accounts")
    data = envelope.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError("Lenco accounts response missing data")

    account = cast(dict[str, Any], data[0])
    account_id = str(account["id"])
    available = major_str_to_ngwee(str(account.get("availableBalance", "0")))
    ledger = major_str_to_ngwee(str(account.get("ledgerBalance", "0")))
    return LencoAccountSnapshot(
        account_id=account_id,
        available_balance_ngwee=available,
        ledger_balance_ngwee=ledger,
    )


async def fetch_lenco_transactions(
    *,
    account_id: str,
    report_date: date,
) -> list[LencoTransactionRow]:
    start, end = _day_bounds(report_date)
    params = {
        "accountId": account_id,
        "from": start.date().isoformat(),
        "to": (end - timedelta(seconds=1)).date().isoformat(),
    }
    envelope = await _lenco_get("/transactions", params=params)
    data = envelope.get("data")
    if not isinstance(data, list):
        return []

    rows: list[LencoTransactionRow] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_amount = str(item.get("amount", "0"))
        signed = major_str_to_ngwee(raw_amount)
        txn_type = str(item.get("type", "")).lower()
        if txn_type == "debit":
            signed = -abs(signed)
        elif txn_type == "credit":
            signed = abs(signed)
        narration = str(item.get("narration", ""))
        rows.append(
            LencoTransactionRow(
                id=str(item.get("id", "")),
                amount_ngwee=signed,
                txn_type=txn_type,
                narration=narration,
                reference=extract_lenco_reference(narration),
                datetime=str(item.get("datetime", "")),
            )
        )
    return rows


def fetch_ledger_platform_cash_balance_ngwee() -> int:
    account_id = resolve_account_id(AccountRef("platform_cash"))
    return account_balance_ngwee(account_id)


def fetch_ledger_day_rows(report_date: date) -> list[LedgerDayRow]:
    start, end = _day_bounds(report_date)
    start_sql = sql_literal(start.isoformat())
    end_sql = sql_literal(end.isoformat())
    script = f"""
SELECT
  t.id::text AS transaction_id,
  t.kind,
  t.payment_id::text AS payment_id,
  p.lenco_reference,
  lp.amount_ngwee::text AS amount_ngwee,
  t.created_at::text AS created_at
FROM public.ledger_transactions t
JOIN public.ledger_postings lp ON lp.transaction_id = t.id
JOIN public.ledger_accounts la ON la.id = lp.account_id
LEFT JOIN public.payments p ON p.id = t.payment_id
WHERE la.kind = 'platform_cash'
  AND t.created_at >= {start_sql}::timestamptz
  AND t.created_at < {end_sql}::timestamptz
ORDER BY t.created_at ASC;
"""
    result = run_sql_script(script)
    if not result.ok:
        raise RuntimeError(f"ledger day query failed: {result.error}")

    rows: list[LedgerDayRow] = []
    for raw in result.rows:
        parts = raw.split("|")
        if len(parts) < 6:
            continue
        txn_id, kind, payment_id, lenco_ref, amount_s, created_at = parts[:6]
        rows.append(
            LedgerDayRow(
                transaction_id=txn_id,
                kind=kind,
                payment_id=payment_id if payment_id and payment_id != "" else None,
                lenco_reference=lenco_ref if lenco_ref and lenco_ref != "" else None,
                amount_ngwee=int(amount_s),
                created_at=created_at,
            )
        )
    return rows


def build_reconciliation_diff(
    *,
    lenco_balance_ngwee: int,
    ledger_balance_ngwee: int,
    lenco_rows: list[LencoTransactionRow],
    ledger_rows: list[LedgerDayRow],
) -> ReconciliationDiff:
    """Ngwee-exact diff: balance delta, orphaned Lenco, ledger-only, amount mismatches."""
    balance_diff = lenco_balance_ngwee - ledger_balance_ngwee

    lenco_by_ref: dict[str, LencoTransactionRow] = {}
    for lenco_row in lenco_rows:
        if lenco_row.reference:
            lenco_by_ref.setdefault(lenco_row.reference, lenco_row)

    ledger_by_ref: dict[str, LedgerDayRow] = {}
    for ledger_row in ledger_rows:
        if ledger_row.lenco_reference:
            ledger_by_ref.setdefault(ledger_row.lenco_reference, ledger_row)

    lenco_refs = set(lenco_by_ref)
    ledger_refs = set(ledger_by_ref)

    orphaned = tuple(
        {
            "lenco_transaction_id": lenco_by_ref[ref].id,
            "reference": ref,
            "amount_ngwee": lenco_by_ref[ref].amount_ngwee,
            "narration": lenco_by_ref[ref].narration,
        }
        for ref in sorted(lenco_refs - ledger_refs)
    )

    ledger_only = tuple(
        {
            "ledger_transaction_id": ledger_by_ref[ref].transaction_id,
            "reference": ref,
            "amount_ngwee": ledger_by_ref[ref].amount_ngwee,
            "kind": ledger_by_ref[ref].kind,
        }
        for ref in sorted(ledger_refs - lenco_refs)
    )

    mismatches: list[dict[str, Any]] = []
    for ref in sorted(lenco_refs & ledger_refs):
        lenco_amt = lenco_by_ref[ref].amount_ngwee
        ledger_amt = ledger_by_ref[ref].amount_ngwee
        if lenco_amt != ledger_amt:
            mismatches.append(
                {
                    "reference": ref,
                    "lenco_amount_ngwee": lenco_amt,
                    "ledger_amount_ngwee": ledger_amt,
                    "diff_ngwee": lenco_amt - ledger_amt,
                }
            )

    return ReconciliationDiff(
        balance_diff_ngwee=balance_diff,
        orphaned_lenco=orphaned,
        ledger_only=ledger_only,
        ngwee_mismatches=tuple(mismatches),
    )


def _fetch_non_terminal_payments(
    service_client: ServiceRoleClient,
    *,
    older_than_minutes: int,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    response = (
        service_client.client.table("payments")
        .select("id, status, lenco_reference, updated_at")
        .in_("status", list(NON_TERMINAL_POLL_STATUSES))
        .lt("updated_at", cutoff.isoformat())
        .execute()
    )
    return _rows(response)


async def poll_non_terminal_payments(
    service_client: ServiceRoleClient,
    *,
    query_status: Any,
    older_than_minutes: int = DEFAULT_POLL_AGE_MINUTES,
) -> PollResult:
    """Re-query Lenco for non-terminal payments and drive M08-P04 transitions."""
    pending = _fetch_non_terminal_payments(
        service_client,
        older_than_minutes=older_than_minutes,
    )
    updated = 0
    unchanged = 0
    errors = 0

    for payment in pending:
        payment_id = str(payment.get("id", ""))
        # Per-payment isolation: one bad payment (illegal/unexpected transition or
        # any error) is logged and skipped so the tick reconciles the rest of the
        # batch instead of aborting on the first poison pill.
        try:
            reference = str(payment["lenco_reference"])
            current_status = PaymentStatus(str(payment["status"]))

            try:
                query_result: QueryStatusResult = await query_status(
                    QueryStatusRequest(reference=reference)
                )
            except Exception:
                logger.exception(
                    "reconciliation poll: Lenco re-query failed for payment %s",
                    payment_id,
                )
                errors += 1
                continue

            if query_result.outcome == ProviderOutcome.NOT_FOUND:
                logger.warning(
                    "reconciliation poll: provider has no collection for payment %s "
                    "(requested_reference=%s)",
                    payment_id,
                    query_result.requested_reference,
                )
                errors += 1
                continue

            validate_query_collection_observation(
                service_client,
                payment_id=payment_id,
                result=query_result,
            )

            if query_result.status is None:
                logger.warning(
                    "reconciliation poll: provider status missing for payment %s",
                    payment_id,
                )
                errors += 1
                continue
            incoming = lenco_collection_status_to_payment_status(query_result.status)
            if incoming is None:
                unchanged += 1
                continue

            outcome = apply_payment_status(
                service_client,
                payment_id=payment_id,
                incoming_status=incoming,
                actor_id=SYSTEM_ACTOR_ID,
                note="Reconciliation poller re-query",
                observation=(
                    collection_observation_from_query(
                        query_result, source="poller"
                    )
                    if incoming in (PaymentStatus.SUCCESS, PaymentStatus.FAILED)
                    else None
                ),
            )
            if outcome is None:
                unchanged += 1
            else:
                updated += 1
                if outcome.to_status == current_status:
                    unchanged += 1
                    updated -= 1
        except PaymentTransitionError as exc:
            # The state machine has no edge for the status Lenco reports from the
            # payment's current status. Not a valid guarded transition — surface
            # it as a reconciliation anomaly for admin/alert and skip rather than
            # raw-UPDATE around the guard. (INITIATED→SUCCESS/FAILED/EXPIRED is
            # legal since PAY-01; poison cases are typically provider/query errors.)
            logger.warning(
                "reconciliation anomaly: illegal transition for payment %s "
                "(from_status=%s event=%s) — skipping",
                payment_id,
                exc.details.get("from_status"),
                exc.details.get("event"),
            )
            errors += 1
            continue
        except Exception:
            logger.exception(
                "reconciliation poll: unexpected error for payment %s — skipping",
                payment_id,
            )
            errors += 1
            continue

    return PollResult(
        scanned=len(pending),
        updated=updated,
        unchanged=unchanged,
        errors=errors,
    )


def _fetch_pending_webhook_events(
    service_client: ServiceRoleClient,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Unprocessed Lenco webhook rows, oldest first (uses provider+processed_at idx)."""
    response = (
        service_client.client.table("webhook_events")
        .select("id, provider, processed_at")
        .eq("provider", "lenco")
        .is_("processed_at", "null")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return _rows(response)


def drain_pending_webhook_events(
    service_client: ServiceRoleClient,
    *,
    limit: int = DEFAULT_WEBHOOK_DRAIN_LIMIT,
) -> DrainResult:
    """Consume stored Lenco webhook rows and drive the payment state machine.

    The webhook endpoint (M08-P02) only verifies + persists each event to
    ``webhook_events`` and fast-acks; this drain applies them via
    ``process_webhook_event`` so the MoMo/USSD push path confirms from the
    webhook we already hold — seconds after receipt on the next tick — instead
    of waiting on the slower re-query poller. Idempotent: each row is marked
    ``processed_at`` by ``process_webhook_event`` and skipped next tick.

    Per-row isolation mirrors the reconciliation poller: an anomalous row (e.g.
    a webhook status with no legal transition from the payment's current state)
    is logged and counted, never aborting the batch. Such a row is left
    unprocessed so the re-query poller and admin monitoring still see it rather
    than it being silently swallowed.
    """
    pending = _fetch_pending_webhook_events(service_client, limit=limit)
    applied = 0
    skipped = 0
    errors = 0

    for event in pending:
        webhook_event_id = str(event.get("id", ""))
        try:
            outcome = process_webhook_event(
                service_client,
                webhook_event_id=webhook_event_id,
            )
        except PaymentTransitionError as exc:
            # Webhook status has no legal edge from the payment's current state
            # (e.g. a row stuck at INITIATED now reporting success/failed). A
            # reconciliation anomaly, not a valid guarded transition — surface it
            # and skip rather than raw-UPDATE around the state-machine guard.
            logger.warning(
                "webhook drain anomaly: illegal transition for webhook_event %s "
                "(from_status=%s event=%s) — skipping",
                webhook_event_id,
                exc.details.get("from_status"),
                exc.details.get("event"),
            )
            errors += 1
            continue
        except Exception:
            logger.exception(
                "webhook drain: unexpected error for webhook_event %s — skipping",
                webhook_event_id,
            )
            errors += 1
            continue

        if outcome is None:
            skipped += 1
        else:
            applied += 1

    return DrainResult(
        scanned=len(pending),
        applied=applied,
        skipped=skipped,
        errors=errors,
    )


def _load_existing_report(
    service_client: ServiceRoleClient,
    report_date: date,
) -> dict[str, Any] | None:
    response = (
        service_client.client.table("reconciliation_reports")
        .select("id, report_date, summary, discrepancies, created_at")
        .eq("report_date", report_date.isoformat())
        .maybe_single()
        .execute()
    )
    return _single_row(response)


def _persist_report(
    service_client: ServiceRoleClient,
    *,
    report_id: str,
    report_date: date,
    summary: dict[str, Any],
    discrepancies: dict[str, Any],
) -> tuple[str, bool]:
    existing = _load_existing_report(service_client, report_date)
    if existing is not None:
        existing_summary = existing.get("summary")
        if not isinstance(existing_summary, dict):
            raise ImmutableReportConflict(
                f"existing report for {report_date.isoformat()} has no versioned summary"
            )
        expected = summary.get("input_fingerprint")
        observed = existing_summary.get("input_fingerprint")
        if not expected or observed != expected:
            raise ImmutableReportConflict(
                "immutable reconciliation report already exists for different or "
                f"unversioned inputs on {report_date.isoformat()}"
            )
        return str(existing["id"]), False

    row = {
        "id": report_id,
        "report_date": report_date.isoformat(),
        "summary": summary,
        "discrepancies": discrepancies,
    }
    response = service_client.client.table("reconciliation_reports").insert(row).execute()
    inserted = _single_row(response)
    if inserted is None:
        rows = _rows(response)
        if not rows:
            raise RuntimeError("failed to persist reconciliation report")
        inserted = rows[0]
    return str(inserted["id"]), True


async def run_daily_reconciliation_report(
    service_client: ServiceRoleClient,
    *,
    report_date: date | None = None,
    fetch_account: Any | None = None,
    fetch_transactions: Any | None = None,
    provider_adapter: LencoReconciliationAdapter | None = None,
    local_reader: PostgrestReconciliationReader | None = None,
    source_version: str | None = None,
    schema_version: str = "20260930170000-reconciliation-report-versions",
    matcher_version: str = "f3-reconciliation-matcher-v1",
    policy_version: str = "financial-policy-addendum-v0.2-draft-non-effective",
) -> DailyReportResult:
    """Persist one immutable, evidence-bound daily reconciliation run.

    The legacy fetch callables remain solely as a compatibility seam for the
    accepted daily-report tests.  Normal execution uses the documented Lenco
    adapter and protected PostgREST reader below.
    """
    target_date = report_date or (datetime.now(UTC).date() - timedelta(days=1))

    existing = (
        _load_existing_report(service_client, target_date)
        if fetch_account is not None or fetch_transactions is not None
        else None
    )
    if existing is not None and (fetch_account is not None or fetch_transactions is not None):
        existing_summary = cast(dict[str, Any], existing.get("summary", {}))
        existing_discrepancies = cast(dict[str, Any], existing.get("discrepancies", {}))
        return DailyReportResult(
            report_id=str(existing["id"]),
            report_date=target_date,
            created=False,
            summary=existing_summary,
            discrepancies=existing_discrepancies,
            clean=not _has_discrepancies(existing_discrepancies),
            certifiable=bool(existing_summary.get("certifiable", False)),
            input_fingerprint=cast(
                str | None, existing_summary.get("input_fingerprint")
            ),
        )

    if fetch_account is None and fetch_transactions is None:
        configured_account_id = os.environ.get("LENCO_ACCOUNT_ID", "").strip()
        adapter = provider_adapter or LencoReconciliationAdapter(
            configured_account_id=configured_account_id,
        )
        reader = local_reader or PostgrestReconciliationReader(
            service_client,
            runtime_role="service_role",
        )
        owns_adapter = provider_adapter is None
        try:
            provider_evidence = await adapter.collect(report_date=target_date)
        finally:
            if owns_adapter:
                await adapter.aclose()
        local_evidence = reader.collect(report_date=target_date)
        cutoff = datetime.combine(target_date, time.max, tzinfo=UTC)
        provider_collection = collect_provider_pages(
            provider_evidence.pages,
            configured_account_id=provider_evidence.account.account_id,
            currency=provider_evidence.account.currency,
            cutoff_utc=cutoff,
        )
        match_report = match_movements(
            provider_collection.movements,
            local_evidence.movements,
        )

        # /transactions supplies running-balance movements, but it does not
        # document a statement identity, opening funds, fee/reversal objects or
        # settlement positions.  Keep these gaps explicit instead of coercing
        # absent provider facts to zero or comparing provider liquidity to the
        # unrelated platform_cash liability/accounting balance.
        provider_fact_gaps = (
            "provider statement identity and opening-funds basis are undocumented",
            "transaction fee and reversal objects are not present in the documented feed",
            "settled, unsettled and disputed positions require separate provider evidence",
            "provider transaction ordering stability is undocumented",
        )
        provider_origins = sorted(
            {row.evidence_origin.value for row in provider_collection.movements}
        )
        source = source_version or os.environ.get("GITHUB_SHA", "").strip() or "unbound"
        source_binding_issues = (
            ()
            if re.fullmatch(r"[0-9a-f]{40}", source)
            else ("source commit is missing or not a full lowercase SHA",)
        )
        issues = tuple(
            [
                *provider_collection.issues,
                *local_evidence.unresolved,
                *provider_fact_gaps,
                *source_binding_issues,
            ]
        )
        raw_inputs = {
            "source_version": source,
            "schema_version": schema_version,
            "matcher_version": matcher_version,
            "policy_version": policy_version,
            "configured_account_id": provider_evidence.account.account_id,
            "currency": provider_evidence.account.currency,
            "report_date": target_date.isoformat(),
            "cutoff_utc": cutoff.isoformat(),
            "account_response_sha256": provider_evidence.account_response_sha256,
            "transaction_response_sha256s": list(
                provider_evidence.transaction_response_sha256s
            ),
            "provider_evidence_origins": provider_origins,
            "provider_query_from": provider_evidence.query_from.isoformat(),
            "provider_query_to": provider_evidence.query_to.isoformat(),
            "page_numbers": list(provider_collection.observed_page_numbers),
            "page_stop_reason": provider_collection.stop_reason,
            "local_source_sha256": local_evidence.source_sha256,
            "local_row_counts": local_evidence.row_counts,
            "runtime_role": local_evidence.runtime_role,
        }
        movement_reconciliation_clean = (
            provider_collection.complete
            and match_report.exact
            and not local_evidence.unresolved
        )
        summary = {
            "report_version": "f3-reconciliation-report-v1",
            "source_version": source,
            "schema_version": schema_version,
            "matcher_version": matcher_version,
            "policy_version": policy_version,
            "report_date": target_date.isoformat(),
            "cutoff_utc": cutoff.isoformat(),
            "configured_account_id": provider_evidence.account.account_id,
            "currency": provider_evidence.account.currency,
            "provider_available_balance_ngwee": (
                provider_evidence.account.available_balance_ngwee
            ),
            "provider_ledger_balance_ngwee": provider_evidence.account.ledger_balance_ngwee,
            "provider_movement_count": len(provider_collection.movements),
            "provider_late_movement_count": len(provider_collection.late_movements),
            "provider_evidence_origins": provider_origins,
            "provider_reference_sources": sorted(
                {
                    row.provider_reference_source
                    for row in provider_collection.movements
                    if row.provider_reference_source
                }
            ),
            "provider_query_from": provider_evidence.query_from.isoformat(),
            "provider_query_to": provider_evidence.query_to.isoformat(),
            "local_movement_count": len(local_evidence.movements),
            "page_numbers": list(provider_collection.observed_page_numbers),
            "page_stop_reason": provider_collection.stop_reason,
            "account_response_sha256": provider_evidence.account_response_sha256,
            "transaction_response_sha256s": list(
                provider_evidence.transaction_response_sha256s
            ),
            "local_source_sha256": local_evidence.source_sha256,
            "local_row_counts": local_evidence.row_counts,
            "runtime_role": local_evidence.runtime_role,
            "movement_reconciliation_clean": movement_reconciliation_clean,
            "clean": movement_reconciliation_clean and not issues,
            # The 24-scenario provider drill and unresolved statement facts are
            # separate acceptance evidence; a source daily run cannot certify it.
            "certifiable": False,
        }
        discrepancies = {
            "issues": list(issues),
            "duplicate_provider_movement_ids": list(provider_collection.duplicate_ids),
            "late_provider_movement_ids": [
                row.movement_id for row in provider_collection.late_movements
            ],
            "matches": [
                {
                    "provider_movement_id": row.provider_movement_id,
                    "local_movement_group": row.local_movement_group,
                    "identity_kind": row.identity_kind,
                    "provider_amount_ngwee": row.provider_amount_ngwee,
                    "local_amount_ngwee": row.local_amount_ngwee,
                    "difference_ngwee": row.difference_ngwee,
                }
                for row in match_report.matches
            ],
            "provider_unmatched": [
                {"identity": row.identity, "reason": row.reason}
                for row in match_report.provider_unmatched
            ],
            "local_unmatched": [
                {"identity": row.identity, "reason": row.reason}
                for row in match_report.local_unmatched
            ],
            "ambiguous": [
                {
                    "identity": row.identity,
                    "reason": row.reason,
                    "candidates": list(row.candidates),
                }
                for row in match_report.ambiguous
            ],
            "pending_transfers": list(local_evidence.pending_transfers),
            "terminal_transfers": list(local_evidence.terminal_transfers),
        }
        persisted = ReconciliationReportStore(
            service_client, runtime_role=local_evidence.runtime_role,
        ).append(
            account_id=provider_evidence.account.account_id,
            currency=provider_evidence.account.currency,
            report_date=target_date,
            cutoff_utc=cutoff,
            source_version=source,
            schema_version=schema_version,
            matcher_version=matcher_version,
            policy_version=policy_version,
            input_hashes=raw_inputs,
            summary=summary,
            discrepancies=discrepancies,
        )
        preserved_summary = cast(dict[str, Any], persisted.row["summary"])
        preserved_discrepancies = cast(dict[str, Any], persisted.row["discrepancies"])
        return DailyReportResult(
            report_id=str(persisted.row["id"]),
            report_date=target_date,
            created=persisted.created,
            summary=preserved_summary,
            discrepancies=preserved_discrepancies,
            clean=bool(preserved_summary["clean"]),
            certifiable=False,
            input_fingerprint=str(persisted.row["input_fingerprint"]),
        )

    if fetch_account is None or fetch_transactions is None:
        raise ValueError("fetch_account and fetch_transactions must be supplied together")

    lenco_account = await fetch_account()
    lenco_rows = await fetch_transactions(
        account_id=lenco_account.account_id,
        report_date=target_date,
    )
    ledger_balance = fetch_ledger_platform_cash_balance_ngwee()
    ledger_rows = fetch_ledger_day_rows(target_date)

    diff = build_reconciliation_diff(
        lenco_balance_ngwee=lenco_account.available_balance_ngwee,
        ledger_balance_ngwee=ledger_balance,
        lenco_rows=lenco_rows,
        ledger_rows=ledger_rows,
    )

    release_accounting = build_release_accounting_day_totals(
        report_date=target_date.isoformat()
    )
    legacy_summary: dict[str, Any] = {
        "report_date": target_date.isoformat(),
        "lenco_balance_ngwee": lenco_account.available_balance_ngwee,
        "lenco_ledger_balance_ngwee": lenco_account.ledger_balance_ngwee,
        "ledger_platform_cash_ngwee": ledger_balance,
        "lenco_transaction_count": len(lenco_rows),
        "ledger_transaction_count": len(ledger_rows),
        "clean": not diff.has_discrepancies,
        # Escrow release accounting (gross / commission / net) — integer ngwee.
        # commission + vendor_released should equal gross for fully settled orders
        # on the day (refunds excluded from these three totals).
        "release_gross_collected_ngwee": release_accounting["gross_collected_ngwee"],
        "release_commission_captured_ngwee": release_accounting[
            "commission_captured_ngwee"
        ],
        "release_vendor_net_ngwee": release_accounting["vendor_released_ngwee"],
    }

    legacy_discrepancies: dict[str, Any] = {
        "balance_diff_ngwee": diff.balance_diff_ngwee,
        "orphaned_lenco": list(diff.orphaned_lenco),
        "ledger_only": list(diff.ledger_only),
        "ngwee_mismatches": list(diff.ngwee_mismatches),
    }

    report_id, created = _persist_report(
        service_client,
        report_id=str(uuid4()),
        report_date=target_date,
        summary=legacy_summary,
        discrepancies=legacy_discrepancies,
    )

    return DailyReportResult(
        report_id=report_id,
        report_date=target_date,
        created=created,
        summary=legacy_summary,
        discrepancies=legacy_discrepancies,
        clean=not diff.has_discrepancies,
    )


def _has_discrepancies(discrepancies: dict[str, Any]) -> bool:
    issues = discrepancies.get("issues")
    if isinstance(issues, list) and issues:
        return True
    if int(discrepancies.get("balance_diff_ngwee", 0)) != 0:
        return True
    for key in (
        "orphaned_lenco",
        "ledger_only",
        "ngwee_mismatches",
        "provider_unmatched",
        "local_unmatched",
        "ambiguous",
    ):
        value = discrepancies.get(key)
        if isinstance(value, list) and value:
            return True
    return False
