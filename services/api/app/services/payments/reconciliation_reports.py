"""Protected, append-only report RPC and explicit legacy provenance reader."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol


class ServiceClient(Protocol):
    @property
    def client(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class PersistedReport:
    row: dict[str, Any]
    created: bool


class ReconciliationReportStore:
    """Service writes only through the serialized RPC; readers still use RLS.

    Callers may read using an operator JWT, but may not persist with that role.
    The database, not the declared Python role, enforces writer/read authority.
    """

    def __init__(self, service: ServiceClient, *, runtime_role: str) -> None:
        self._service = service
        self._runtime_role = runtime_role

    def append(
        self,
        *,
        account_id: str,
        currency: str,
        report_date: date,
        cutoff_utc: datetime,
        source_version: str,
        schema_version: str,
        matcher_version: str,
        policy_version: str,
        input_hashes: dict[str, Any],
        summary: dict[str, Any],
        discrepancies: dict[str, Any],
    ) -> PersistedReport:
        if self._runtime_role != "service_role":
            raise PermissionError("service report writer required")
        if (
            not account_id.strip()
            or not re.fullmatch(r"[A-Z]{3}", currency)
            or not re.fullmatch(r"[0-9a-f]{40}", source_version)
            or not all(value.strip() for value in (schema_version, matcher_version, policy_version))
            or cutoff_utc.tzinfo is None
            or cutoff_utc.astimezone(UTC).date() != report_date
            or summary.get("certifiable") is not False
        ):
            raise ValueError("incomplete/noncertifying reconciliation binding required")
        page_hashes = input_hashes.get("transaction_response_sha256s")
        hashes = [
            input_hashes.get("account_response_sha256"),
            input_hashes.get("local_source_sha256"),
        ]
        if not isinstance(page_hashes, list) or not page_hashes:
            raise ValueError("complete reconciliation input hashes required")
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in [*hashes, *page_hashes]
        ):
            raise ValueError("complete reconciliation input hashes required")
        binding = {
            "provider_account_id": account_id,
            "currency": currency,
            "report_date": report_date.isoformat(),
            "cutoff_utc": cutoff_utc.astimezone(UTC).isoformat(),
            "source_version": source_version,
            "schema_version": schema_version,
            "matcher_version": matcher_version,
            "policy_version": policy_version,
            "input_hashes": input_hashes,
            "summary": summary,
            "discrepancies": discrepancies,
        }
        response = self._service.client.rpc(
            "append_reconciliation_report_version", {"p_report": binding}
        ).execute()
        envelope = response.data
        if not isinstance(envelope, dict) or not isinstance(envelope.get("created"), bool):
            raise RuntimeError("invalid immutable report RPC envelope")
        row = envelope.get("report")
        if not isinstance(row, dict):
            raise RuntimeError("immutable report RPC returned no row")
        for field in (
            "provider_account_id",
            "currency",
            "report_date",
            "source_version",
            "schema_version",
            "matcher_version",
            "policy_version",
            "input_hashes",
        ):
            if row.get(field) != binding[field]:
                raise RuntimeError(f"immutable report RPC binding mismatch: {field}")
        if not row.get("id") or not re.fullmatch(
            r"[0-9a-f]{64}", str(row.get("input_fingerprint", ""))
        ):
            raise RuntimeError("immutable report RPC identity/fingerprint missing")
        try:
            observed_cutoff = datetime.fromisoformat(str(row["cutoff_utc"]))
        except (KeyError, ValueError) as error:
            raise RuntimeError("immutable report RPC cutoff missing/invalid") from error
        if observed_cutoff.tzinfo is None or observed_cutoff != cutoff_utc:
            raise RuntimeError("immutable report RPC binding mismatch: cutoff_utc")
        number = row.get("version_number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise RuntimeError("immutable report RPC version missing/invalid")
        returned_summary = row.get("summary")
        if (
            not isinstance(returned_summary, dict)
            or returned_summary.get("certifiable") is not False
            or returned_summary.get("run_id") != row["id"]
            or returned_summary.get("input_fingerprint") != row["input_fingerprint"]
            or returned_summary.get("version_number") != number
            or returned_summary.get("parent_id") != row.get("parent_id")
            or not isinstance(row.get("discrepancies"), dict)
        ):
            raise RuntimeError("immutable report RPC metadata mismatch")
        return PersistedReport(row=row, created=envelope["created"])

    def versions(
        self, *, account_id: str, currency: str, report_date: date
    ) -> list[dict[str, Any]]:
        # Capture the immutable high-water mark once. Concurrent appends do not
        # change the history being read, and short server-capped pages are not
        # mistaken for the end of that history.
        def scoped() -> Any:
            return (
                self._service.client.table("reconciliation_report_versions")
                .select("*")
                .eq("provider_account_id", account_id)
                .eq("currency", currency)
                .eq("report_date", report_date.isoformat())
            )

        latest = scoped().order("version_number", desc=True).limit(1).execute().data
        if not isinstance(latest, list):
            raise RuntimeError("invalid version reader response")
        if not latest:
            return []
        upper = latest[0].get("version_number")
        if isinstance(upper, bool) or not isinstance(upper, int) or upper < 1:
            raise RuntimeError("invalid version reader high-water mark")
        rows: list[dict[str, Any]] = []
        last = 0
        while last < upper:
            page = (
                scoped()
                .gt("version_number", last)
                .lte("version_number", upper)
                .order("version_number")
                .limit(250)
                .execute()
                .data
            )
            if not isinstance(page, list) or not page:
                raise RuntimeError("incomplete version history")
            for row in page:
                if (
                    not isinstance(row, dict)
                    or row.get("provider_account_id") != account_id
                    or row.get("currency") != currency
                    or row.get("report_date") != report_date.isoformat()
                    or isinstance(row.get("version_number"), bool)
                    or row.get("version_number") != last + 1
                    or row["version_number"] > upper
                ):
                    raise RuntimeError("invalid or incomplete version history")
                rows.append(dict(row))
                last += 1
        return rows

    def legacy(self, *, report_date: date) -> list[dict[str, Any]]:
        response = (
            self._service.client.table("reconciliation_reports")
            .select("*")
            .eq("report_date", report_date.isoformat())
            .execute()
        )
        if not isinstance(response.data, list):
            raise RuntimeError("invalid legacy reader response")
        # Never invent account/source/parent binding from date or current intent.
        return [
            {"provenance": "LEGACY_UNVERSIONED_ACCOUNT_UNBOUND", "report": dict(row)}
            for row in response.data
        ]
