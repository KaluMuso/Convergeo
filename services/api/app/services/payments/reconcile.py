"""Payment reconciliation poller and daily Lenco-vs-ledger report."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol, cast

import httpx
from app.services.ledger.engine import account_balance_ngwee, resolve_account_id
from app.services.ledger.templates import AccountRef
from app.services.orders.audit import run_sql_script, sql_literal
from app.services.payments.base import QueryStatusRequest, QueryStatusResult
from app.services.payments.lenco.config import get_api_token, get_base_url
from app.services.payments.money import major_str_to_ngwee
from app.services.payments.state import (
    SYSTEM_ACTOR_ID,
    PaymentStatus,
    apply_payment_status,
    lenco_collection_status_to_payment_status,
)

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
        payment_id = str(payment["id"])
        reference = str(payment["lenco_reference"])
        current_status = PaymentStatus(str(payment["status"]))

        try:
            query_result: QueryStatusResult = await query_status(
                QueryStatusRequest(reference=reference)
            )
        except Exception:
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
        )
        if outcome is None:
            unchanged += 1
        else:
            updated += 1
            if outcome.to_status == current_status:
                unchanged += 1
                updated -= 1

    return PollResult(
        scanned=len(pending),
        updated=updated,
        unchanged=unchanged,
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
    report_date: date,
    summary: dict[str, Any],
    discrepancies: dict[str, Any],
) -> tuple[str, bool]:
    existing = _load_existing_report(service_client, report_date)
    if existing is not None:
        return str(existing["id"]), False

    row = {
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
    fetch_account: Any = fetch_lenco_primary_account,
    fetch_transactions: Any = fetch_lenco_transactions,
) -> DailyReportResult:
    """Compare Lenco balance/transactions vs ledger; persist reconciliation_reports row."""
    target_date = report_date or (datetime.now(UTC).date() - timedelta(days=1))

    existing = _load_existing_report(service_client, target_date)
    if existing is not None:
        existing_summary = cast(dict[str, Any], existing.get("summary", {}))
        existing_discrepancies = cast(dict[str, Any], existing.get("discrepancies", {}))
        return DailyReportResult(
            report_id=str(existing["id"]),
            report_date=target_date,
            created=False,
            summary=existing_summary,
            discrepancies=existing_discrepancies,
            clean=not _has_discrepancies(existing_discrepancies),
        )

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

    summary: dict[str, Any] = {
        "report_date": target_date.isoformat(),
        "lenco_balance_ngwee": lenco_account.available_balance_ngwee,
        "lenco_ledger_balance_ngwee": lenco_account.ledger_balance_ngwee,
        "ledger_platform_cash_ngwee": ledger_balance,
        "lenco_transaction_count": len(lenco_rows),
        "ledger_transaction_count": len(ledger_rows),
        "clean": not diff.has_discrepancies,
    }

    discrepancies: dict[str, Any] = {
        "balance_diff_ngwee": diff.balance_diff_ngwee,
        "orphaned_lenco": list(diff.orphaned_lenco),
        "ledger_only": list(diff.ledger_only),
        "ngwee_mismatches": list(diff.ngwee_mismatches),
    }

    report_id, created = _persist_report(
        service_client,
        report_date=target_date,
        summary=summary,
        discrepancies=discrepancies,
    )

    return DailyReportResult(
        report_id=report_id,
        report_date=target_date,
        created=created,
        summary=summary,
        discrepancies=discrepancies,
        clean=not diff.has_discrepancies,
    )


def _has_discrepancies(discrepancies: dict[str, Any]) -> bool:
    if int(discrepancies.get("balance_diff_ngwee", 0)) != 0:
        return True
    for key in ("orphaned_lenco", "ledger_only", "ngwee_mismatches"):
        value = discrepancies.get(key)
        if isinstance(value, list) and value:
            return True
    return False
