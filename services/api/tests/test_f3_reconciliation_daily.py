"""Daily F3 report wiring and immutable input binding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from app.services.payments.lenco.reconciliation import LencoReconciliationEvidence
from app.services.payments.reconcile import run_daily_reconciliation_report
from app.services.payments.reconciliation_matcher import (
    AccountSnapshot,
    EvidenceOrigin,
    LocalMovement,
    MovementDirection,
    MovementKind,
    ProviderMovement,
    ProviderPage,
)
from app.services.payments.reconciliation_reader import LocalReconciliationEvidence
from app.services.payments.reconciliation_reports import ReconciliationReportStore


class _ReportQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._date: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _columns: str) -> _ReportQuery:
        return self

    def eq(self, _column: str, value: str) -> _ReportQuery:
        self._date = value
        return self

    def maybe_single(self) -> _ReportQuery:
        return self

    def insert(self, payload: dict[str, Any]) -> _ReportQuery:
        self._payload = payload
        return self

    def execute(self) -> SimpleNamespace:
        if self._payload is not None:
            row = {**self._payload, "created_at": datetime.now(UTC).isoformat()}
            self._rows.append(row)
            return SimpleNamespace(data=[row])
        rows = [row for row in self._rows if row.get("report_date") == self._date]
        return SimpleNamespace(data=rows[0] if rows else None)


class _Reports:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, name: str) -> _ReportQuery:
        assert name == "reconciliation_reports"
        return _ReportQuery(self.rows)

    def rpc(self, name: str, parameters: dict[str, Any]) -> SimpleNamespace:
        """Transport double ONLY. Concurrent/role/SQL claims use the real module."""
        assert name == "append_reconciliation_report_version"
        payload = parameters["p_report"]
        binding = {
            key: value for key, value in payload.items() if key not in ("summary", "discrepancies")
        }
        fingerprint = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
        for row in self.rows:
            if row["input_fingerprint"] == fingerprint:
                if row["discrepancies"] != payload["discrepancies"]:
                    raise ValueError("same inputs produced a different report")
                return SimpleNamespace(
                    execute=lambda row=row: SimpleNamespace(data={"created": False, "report": row})
                )
        prior = [
            row
            for row in self.rows
            if all(
                row[key] == binding[key]
                for key in ("provider_account_id", "currency", "report_date")
            )
        ]
        parent = prior[-1]["id"] if prior else None
        identity = str(uuid4())
        number = len(prior) + 1
        row = {
            **binding,
            "id": identity,
            "input_fingerprint": fingerprint,
            "version_number": number,
            "parent_id": parent,
            "summary": {
                **payload["summary"],
                "run_id": identity,
                "input_fingerprint": fingerprint,
                "version_number": number,
                "parent_id": parent,
            },
            "discrepancies": payload["discrepancies"],
        }
        self.rows.append(row)
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(data={"created": True, "report": row})
        )


class _Provider:
    def __init__(self, evidence: LencoReconciliationEvidence) -> None:
        self.evidence = evidence

    async def collect(self, *, report_date: date) -> LencoReconciliationEvidence:
        assert report_date == date(2026, 9, 29)
        return self.evidence


class _Reader:
    def __init__(self, evidence: LocalReconciliationEvidence) -> None:
        self.evidence = evidence

    def collect(self, *, report_date: date) -> LocalReconciliationEvidence:
        assert report_date == date(2026, 9, 29)
        return self.evidence


def _evidence() -> tuple[LencoReconciliationEvidence, LocalReconciliationEvidence]:
    observed = datetime.fromisoformat("2026-09-29T12:00:00+00:00")
    movement = ProviderMovement(
        movement_id="provider-txn-1",
        account_id="account-configured",
        currency="ZMW",
        amount_ngwee=30000,
        direction=MovementDirection.CREDIT,
        kind=MovementKind.UNKNOWN,
        observed_at=observed,
        provider_reference="lenco-1",
        provider_reference_source="transaction.narration",
        evidence_origin=EvidenceOrigin.SYNTHETIC,
    )
    provider = LencoReconciliationEvidence(
        account=AccountSnapshot("account-configured", "ZMW", 120000, 125000),
        pages=(ProviderPage(1, None, None, 1, 1, (movement,), raw_sha256="a" * 64),),
        account_response_sha256="b" * 64,
        observed_at=observed,
        query_from=date(2026, 9, 29),
        query_to=date(2026, 9, 29),
    )
    local = LocalReconciliationEvidence(
        movements=(
            LocalMovement(
                local_id="posting-1",
                movement_group="payment:payment-1",
                kind=MovementKind.COLLECTION,
                amount_ngwee=30000,
                provider_reference="lenco-1",
                payment_id="payment-1",
                ledger_transaction_id="ledger-1",
                ledger_linkage_id="payment-1",
            ),
        ),
        pending_transfers=(),
        terminal_transfers=(),
        unresolved=(),
        source_sha256="c" * 64,
        row_counts={"ledger_transactions": 1, "ledger_postings": 1},
        runtime_role="service_role",
    )
    return provider, local


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "explicit", "expected"),
    [
        ({"GIT_SHA": "a" * 40, "API_IMAGE_TAG": "a" * 40}, None, "a" * 40),
        ({"GIT_SHA": "a" * 40, "API_IMAGE_TAG": "b" * 64}, None, "a" * 40),
        ({"GITHUB_SHA": "a" * 40}, None, "a" * 40),
        ({"API_IMAGE_TAG": "a" * 40}, None, "a" * 40),
        ({"GIT_SHA": "b" * 40}, "a" * 40, "a" * 40),
    ],
)
async def test_daily_report_binds_documented_runtime_source(
    monkeypatch: pytest.MonkeyPatch,
    runtime: dict[str, str],
    explicit: str | None,
    expected: str,
) -> None:
    for name in ("GIT_SHA", "GITHUB_SHA", "API_IMAGE_TAG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in runtime.items():
        monkeypatch.setenv(name, value)
    provider, local = _evidence()
    reports = _Reports()
    result = await run_daily_reconciliation_report(
        SimpleNamespace(client=reports),
        report_date=date(2026, 9, 29),
        provider_adapter=_Provider(provider),  # type: ignore[arg-type]
        local_reader=_Reader(local),  # type: ignore[arg-type]
        source_version=explicit,
    )
    assert result.summary["source_version"] == expected
    assert reports.rows[0]["source_version"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime", "explicit", "reason"),
    [
        ({}, None, "full lowercase"),
        ({"GIT_SHA": "unknown", "API_IMAGE_TAG": "a" * 40}, None, "full lowercase"),
        ({"GIT_SHA": "A" * 40}, None, "full lowercase"),
        ({"GIT_SHA": "a" * 7}, None, "full lowercase"),
        ({"GIT_SHA": "a" * 40, "API_IMAGE_TAG": "b" * 40}, None, "conflicting"),
        ({"GIT_SHA": "a" * 40, "GITHUB_SHA": "b" * 40}, None, "conflicting"),
        ({"GIT_SHA": "a" * 40}, "bad", "full lowercase"),
    ],
)
async def test_daily_report_rejects_missing_invalid_or_conflicting_source_before_write(
    monkeypatch: pytest.MonkeyPatch,
    runtime: dict[str, str],
    explicit: str | None,
    reason: str,
) -> None:
    for name in ("GIT_SHA", "GITHUB_SHA", "API_IMAGE_TAG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in runtime.items():
        monkeypatch.setenv(name, value)
    provider, local = _evidence()
    reports = _Reports()
    with pytest.raises(ValueError, match=reason):
        await run_daily_reconciliation_report(
            SimpleNamespace(client=reports),
            report_date=date(2026, 9, 29),
            provider_adapter=_Provider(provider),  # type: ignore[arg-type]
            local_reader=_Reader(local),  # type: ignore[arg-type]
            source_version=explicit,
        )
    assert reports.rows == []


@pytest.mark.asyncio
async def test_daily_report_is_source_bound_noncertifying_and_immutable() -> None:
    provider, local = _evidence()
    reports = _Reports()
    service = SimpleNamespace(client=reports)

    first = await run_daily_reconciliation_report(
        service,
        report_date=date(2026, 9, 29),
        provider_adapter=_Provider(provider),  # type: ignore[arg-type]
        local_reader=_Reader(local),  # type: ignore[arg-type]
        source_version="d" * 40,
    )
    replay = await run_daily_reconciliation_report(
        service,
        report_date=date(2026, 9, 29),
        provider_adapter=_Provider(provider),  # type: ignore[arg-type]
        local_reader=_Reader(local),  # type: ignore[arg-type]
        source_version="d" * 40,
    )

    assert first.created is True
    assert replay.created is False
    assert replay.report_id == first.report_id
    assert replay.summary["run_id"] == first.report_id
    assert len(reports.rows) == 1
    assert first.summary["source_version"] == "d" * 40
    assert first.summary["runtime_role"] == "service_role"
    assert first.summary["movement_reconciliation_clean"] is True
    assert first.clean is False
    assert first.certifiable is False
    assert first.discrepancies["matches"][0]["identity_kind"] == "provider_reference"
    assert "balance_diff_ngwee" not in first.discrepancies
    assert any("statement identity" in issue for issue in first.discrepancies["issues"])

    changed = replace(local, source_sha256="e" * 64)
    updated = await run_daily_reconciliation_report(
        service,
        report_date=date(2026, 9, 29),
        provider_adapter=_Provider(provider),  # type: ignore[arg-type]
        local_reader=_Reader(changed),  # type: ignore[arg-type]
        source_version="d" * 40,
    )
    assert updated.created is True and updated.report_id != first.report_id
    assert updated.summary["parent_id"] == first.report_id
    assert updated.summary["version_number"] == 2
    assert len(reports.rows) == 2
    assert reports.rows[0]["id"] == first.report_id


def _report_arguments() -> dict[str, Any]:
    return {
        "account_id": "configured-account",
        "currency": "ZMW",
        "report_date": date(2026, 9, 29),
        "cutoff_utc": datetime.fromisoformat("2026-09-29T23:59:59+00:00"),
        "source_version": "d" * 40,
        "schema_version": "20260930170000",
        "matcher_version": "matcher-v1",
        "policy_version": "DRAFT_NOT_EFFECTIVE",
        "input_hashes": {
            "account_response_sha256": "a" * 64,
            "transaction_response_sha256s": ["b" * 64],
            "local_source_sha256": "c" * 64,
        },
        "summary": {"certifiable": False, "clean": False},
        "discrepancies": {"issues": ["fees unresolved"]},
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", ""),
        ("currency", "zmw"),
        ("source_version", "unbound"),
        ("schema_version", ""),
        ("matcher_version", ""),
        ("policy_version", ""),
        ("cutoff_utc", datetime(2026, 9, 29)),
        ("cutoff_utc", datetime(2026, 9, 30, tzinfo=UTC)),
        ("summary", {"certifiable": True}),
        (
            "input_hashes",
            {
                "account_response_sha256": "a" * 64,
                "transaction_response_sha256s": [],
                "local_source_sha256": "c" * 64,
            },
        ),
        (
            "input_hashes",
            {
                "account_response_sha256": "a" * 64,
                "transaction_response_sha256s": [None],
                "local_source_sha256": "c" * 64,
            },
        ),
    ],
)
def test_incomplete_bindings_fail_before_write(field: str, value: Any) -> None:
    reports = _Reports()
    arguments = {**_report_arguments(), field: value}
    with pytest.raises(ValueError, match="binding|hashes"):
        ReconciliationReportStore(
            SimpleNamespace(client=reports), runtime_role="service_role"
        ).append(**arguments)
    assert reports.rows == []


def test_operator_is_reader_not_writer() -> None:
    reports = _Reports()
    with pytest.raises(PermissionError, match="service report writer"):
        ReconciliationReportStore(
            SimpleNamespace(client=reports), runtime_role="authenticated"
        ).append(**_report_arguments())
    assert reports.rows == []


def test_report_streams_do_not_replay_or_link_across_accounts_dates_or_currencies() -> None:
    reports = _Reports()
    store = ReconciliationReportStore(SimpleNamespace(client=reports), runtime_role="service_role")
    arguments = _report_arguments()
    first = store.append(**arguments)
    for changed in (
        {**arguments, "account_id": "other-account"},
        {**arguments, "currency": "USD"},
        {
            **arguments,
            "report_date": date(2026, 9, 30),
            "cutoff_utc": datetime(2026, 9, 30, 23, tzinfo=UTC),
        },
    ):
        observed = store.append(**changed)
        assert observed.created and observed.row["version_number"] == 1
        assert observed.row["parent_id"] is None
        assert observed.row["id"] != first.row["id"]
    assert store.append(**arguments).row == first.row


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("cutoff_utc", "2026-09-30T23:59:59+00:00", "cutoff_utc"),
        ("version_number", True, "version missing/invalid"),
        ("summary", {"certifiable": True}, "metadata mismatch"),
        ("discrepancies", None, "metadata mismatch"),
        ("input_fingerprint", "", "identity/fingerprint missing"),
    ],
)
def test_invalid_rpc_observation_cannot_become_bound_report(
    field: str,
    value: Any,
    reason: str,
) -> None:
    reports = _Reports()
    store = ReconciliationReportStore(SimpleNamespace(client=reports), runtime_role="service_role")
    arguments = _report_arguments()
    store.append(**arguments)
    reports.rows[0][field] = value
    client = SimpleNamespace(
        rpc=lambda *_args: SimpleNamespace(
            execute=lambda: SimpleNamespace(data={"created": False, "report": reports.rows[0]})
        )
    )
    with pytest.raises(RuntimeError, match=reason):
        ReconciliationReportStore(
            SimpleNamespace(client=client), runtime_role="service_role"
        ).append(**arguments)


def test_legacy_reader_does_not_invent_binding() -> None:
    legacy = {"id": str(uuid4()), "report_date": "2026-09-29", "summary": {"clean": True}}
    client = SimpleNamespace(
        table=lambda _name: SimpleNamespace(
            select=lambda _fields: SimpleNamespace(
                eq=lambda _key, _value: SimpleNamespace(
                    execute=lambda: SimpleNamespace(data=[legacy])
                )
            )
        )
    )
    rows = ReconciliationReportStore(
        SimpleNamespace(client=client), runtime_role="authenticated"
    ).legacy(report_date=date(2026, 9, 29))
    assert rows == [{"provenance": "LEGACY_UNVERSIONED_ACCOUNT_UNBOUND", "report": legacy}]
    assert "provider_account_id" not in rows[0]


def test_rpc_result_wrong_account_is_rejected() -> None:
    arguments = _report_arguments()
    reports = _Reports()
    response = reports.rpc(
        "append_reconciliation_report_version",
        {
            "p_report": {
                **arguments,
                "provider_account_id": "wrong-account",
                "report_date": "2026-09-29",
                "cutoff_utc": "2026-09-29T23:59:59+00:00",
            }
        },
    )
    client = SimpleNamespace(rpc=lambda *_args: response)
    with pytest.raises(RuntimeError, match="binding mismatch: provider_account_id"):
        ReconciliationReportStore(
            SimpleNamespace(client=client), runtime_role="service_role"
        ).append(**arguments)
