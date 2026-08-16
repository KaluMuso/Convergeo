"""EVT-CANCELLATION-REFUND-JOBS — durable organiser-cancel refund orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.services.db import SqlResult
from app.services.events.refund_jobs import (
    SOURCE_KEY_V1,
    SOURCE_ORGANISER_CANCEL,
    EventRefundJobProcessResult,
    compute_job_retry_backoff_seconds,
    enqueue_organiser_cancel_refund_job,
    load_customer_refund_destination,
    order_ticket_refund_amount_ngwee,
    process_event_refund_job,
    sweep_event_refund_jobs,
    sync_event_refund_job_for_refund,
)
from app.services.refunds.execute import RefundExecutionResult, RefundPhase

EVENT_ID = "e9000000-0000-0000-0000-000000000001"
ORDER_ID = "e9000000-0000-0000-0000-0000000000b1"
CUSTOMER_ID = "e9000000-0000-0000-0000-0000000000e1"
JOB_ID = "e9000000-0000-4000-8000-0000000000a1"
REFUND_ID = "e9000000-0000-4000-8000-0000000000b2"
PAYOUT_ID = "e9000000-0000-4000-8000-0000000000c3"
GROUP_ID = "e9000000-0000-0000-0000-0000000000d1"


@dataclass
class FakeSqlState:
    jobs: dict[str, dict[str, str]] = field(default_factory=dict)
    refunds: dict[str, str] = field(default_factory=dict)
    inserted_jobs: set[tuple[str, str, str, str]] = field(default_factory=set)
    ticket_amount: int = 25_000

    def run(self, script: str) -> SqlResult:
        normalized = " ".join(script.split())
        if "INSERT INTO public.event_refund_jobs" in normalized:
            key = (EVENT_ID, ORDER_ID, SOURCE_ORGANISER_CANCEL, SOURCE_KEY_V1)
            if key in self.inserted_jobs:
                return SqlResult(ok=True, rows=[])
            self.inserted_jobs.add(key)
            self.jobs[JOB_ID] = {
                "id": JOB_ID,
                "event_id": EVENT_ID,
                "order_id": ORDER_ID,
                "customer_id": CUSTOMER_ID,
                "source": SOURCE_ORGANISER_CANCEL,
                "source_key": SOURCE_KEY_V1,
                "amount_ngwee": str(self.ticket_amount),
                "status": "queued",
                "refund_id": "",
                "payout_id": "",
                "attempts": "0",
                "next_retry_at": "",
                "last_error": "",
            }
            return SqlResult(ok=True, rows=[JOB_ID])

        if "ticket refund amount query" in script or (
            "order_items oi" in normalized and "item_kind = 'ticket'" in normalized
        ):
            return SqlResult(ok=True, rows=[str(self.ticket_amount)])

        if normalized.startswith(
            "SELECT id::text, status FROM public.event_refund_jobs WHERE refund_id"
        ):
            for job in self.jobs.values():
                if job.get("refund_id") == REFUND_ID:
                    return SqlResult(ok=True, rows=[f"{job['id']}|{job['status']}"])
            return SqlResult(ok=True, rows=[])

        if normalized.startswith("SELECT status FROM public.refunds WHERE id"):
            status = self.refunds.get(REFUND_ID, "awaiting_payout")
            return SqlResult(ok=True, rows=[status])

        if (
            "UPDATE public.event_refund_jobs" in normalized
            and "status = 'processing'" in normalized
        ):
            job = self.jobs.get(JOB_ID)
            if job and job["status"] == "queued":
                job["status"] = "processing"
                job["attempts"] = str(int(job["attempts"]) + 1)
                return SqlResult(ok=True, rows=[JOB_ID])
            return SqlResult(ok=True, rows=[])

        if "UPDATE public.event_refund_jobs" in normalized and "status = 'completed'" in normalized:
            job_id = JOB_ID
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "completed"
            return SqlResult(ok=True, rows=[])

        if (
            "UPDATE public.event_refund_jobs" in normalized
            and "status = 'manual_review'" in normalized
        ):
            job_id = JOB_ID
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "manual_review"
            return SqlResult(ok=True, rows=[])

        if (
            "UPDATE public.event_refund_jobs" in normalized
            and "status = 'awaiting_payout'" in normalized
        ):
            job_id = JOB_ID
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "awaiting_payout"
                self.jobs[job_id]["refund_id"] = REFUND_ID
                self.jobs[job_id]["payout_id"] = PAYOUT_ID
            return SqlResult(ok=True, rows=[])

        if (
            "UPDATE public.event_refund_jobs" in normalized
            and "status = 'needs_destination'" in normalized
        ):
            job_id = JOB_ID
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = "needs_destination"
            return SqlResult(ok=True, rows=[])

        if normalized.startswith(
            "SELECT id::text, event_id::text, order_id::text, customer_id::text"
        ):
            job = self.jobs.get(JOB_ID)
            if job is None:
                return SqlResult(ok=True, rows=[])
            row = "|".join(
                [
                    job["id"],
                    job["event_id"],
                    job["order_id"],
                    job["customer_id"],
                    job["source"],
                    job["source_key"],
                    job["amount_ngwee"],
                    job["status"],
                    job["refund_id"],
                    job["payout_id"],
                    job["attempts"],
                    job["next_retry_at"],
                    job["last_error"],
                ]
            )
            return SqlResult(ok=True, rows=[row])

        if normalized.startswith("SELECT id::text FROM public.event_refund_jobs WHERE status IN"):
            rows = [
                job["id"]
                for job in self.jobs.values()
                if job["status"] in {"queued", "awaiting_payout"}
            ]
            return SqlResult(ok=True, rows=rows)

        return SqlResult(ok=True, rows=[])


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self, []).select(columns)


class FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = {name: FakeTable(rows) for name, rows in tables.items()}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable([]))


class FakeService:
    def __init__(self, client: FakeClient) -> None:
        self.client = client


def test_compute_job_retry_backoff_seconds_doubles() -> None:
    assert compute_job_retry_backoff_seconds(1) == 120
    assert compute_job_retry_backoff_seconds(2) == 240
    assert compute_job_retry_backoff_seconds(3) == 480


def test_enqueue_and_amount_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    state = FakeSqlState()
    monkeypatch.setattr(
        "app.services.events.refund_jobs.run_sql_script",
        state.run,
    )
    amount = order_ticket_refund_amount_ngwee(ORDER_ID)
    assert amount == 25_000
    assert enqueue_organiser_cancel_refund_job(
        event_id=EVENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        amount_ngwee=amount,
    )
    assert not enqueue_organiser_cancel_refund_job(
        event_id=EVENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        amount_ngwee=amount,
    )


def test_load_customer_refund_destination_resolves_phone_and_rail() -> None:
    service = FakeService(
        FakeClient(
            {
                "profiles": [{"id": CUSTOMER_ID, "phone": "+260971234567"}],
                "orders": [{"id": ORDER_ID, "checkout_group_id": GROUP_ID}],
                "payments": [
                    {
                        "checkout_group_id": GROUP_ID,
                        "status": "success",
                        "rail": "airtel",
                    }
                ],
            }
        )
    )
    destination = load_customer_refund_destination(
        service,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
    )
    assert destination == ("+260971234567", "airtel")


def test_process_job_needs_destination_when_profile_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeSqlState()
    state.jobs[JOB_ID] = {
        "id": JOB_ID,
        "event_id": EVENT_ID,
        "order_id": ORDER_ID,
        "customer_id": CUSTOMER_ID,
        "source": SOURCE_ORGANISER_CANCEL,
        "source_key": SOURCE_KEY_V1,
        "amount_ngwee": "25000",
        "status": "queued",
        "refund_id": "",
        "payout_id": "",
        "attempts": "0",
        "next_retry_at": "",
        "last_error": "",
    }
    monkeypatch.setattr("app.services.events.refund_jobs.run_sql_script", state.run)
    service = FakeService(FakeClient({"profiles": [], "orders": [], "payments": []}))

    outcome = process_event_refund_job(service, JOB_ID)
    assert outcome == EventRefundJobProcessResult(
        JOB_ID,
        "needs_destination",
        "missing_customer_momo",
    )
    assert state.jobs[JOB_ID]["status"] == "needs_destination"


def test_process_job_executes_refund_and_waits_for_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeSqlState()
    state.jobs[JOB_ID] = {
        "id": JOB_ID,
        "event_id": EVENT_ID,
        "order_id": ORDER_ID,
        "customer_id": CUSTOMER_ID,
        "source": SOURCE_ORGANISER_CANCEL,
        "source_key": SOURCE_KEY_V1,
        "amount_ngwee": "25000",
        "status": "queued",
        "refund_id": "",
        "payout_id": "",
        "attempts": "0",
        "next_retry_at": "",
        "last_error": "",
    }
    state.refunds[REFUND_ID] = "awaiting_payout"
    monkeypatch.setattr("app.services.events.refund_jobs.run_sql_script", state.run)

    service = FakeService(
        FakeClient(
            {
                "profiles": [{"id": CUSTOMER_ID, "phone": "+260971234567"}],
                "orders": [{"id": ORDER_ID, "checkout_group_id": GROUP_ID}],
                "payments": [{"checkout_group_id": GROUP_ID, "status": "success", "rail": "mtn"}],
            }
        )
    )

    exec_result = RefundExecutionResult(
        refund_id=REFUND_ID,
        order_id=ORDER_ID,
        lane=1,
        phase=RefundPhase.PRE_RELEASE,
        amount_ngwee=25_000,
        payout_id=PAYOUT_ID,
        lenco_reference="rfd-test",
        ledger_transaction_ids=("ledger-1",),
        breakdown={},
        created=True,
    )

    with patch("app.services.events.refund_jobs.execute_refund", return_value=exec_result):
        outcome = process_event_refund_job(service, JOB_ID)

    assert outcome.outcome == "awaiting_payout"
    assert state.jobs[JOB_ID]["status"] == "awaiting_payout"
    assert state.jobs[JOB_ID]["refund_id"] == REFUND_ID


def test_sync_job_marks_completed_when_refund_provider_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeSqlState()
    state.jobs[JOB_ID] = {
        "id": JOB_ID,
        "event_id": EVENT_ID,
        "order_id": ORDER_ID,
        "customer_id": CUSTOMER_ID,
        "source": SOURCE_ORGANISER_CANCEL,
        "source_key": SOURCE_KEY_V1,
        "amount_ngwee": "25000",
        "status": "awaiting_payout",
        "refund_id": REFUND_ID,
        "payout_id": PAYOUT_ID,
        "attempts": "1",
        "next_retry_at": "",
        "last_error": "",
    }
    state.refunds[REFUND_ID] = "completed"
    monkeypatch.setattr("app.services.events.refund_jobs.run_sql_script", state.run)

    assert sync_event_refund_job_for_refund(FakeService(FakeClient({})), refund_id=REFUND_ID)
    assert state.jobs[JOB_ID]["status"] == "completed"


def test_sweep_processes_candidate_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    state = FakeSqlState()
    state.jobs[JOB_ID] = {
        "id": JOB_ID,
        "event_id": EVENT_ID,
        "order_id": ORDER_ID,
        "customer_id": CUSTOMER_ID,
        "source": SOURCE_ORGANISER_CANCEL,
        "source_key": SOURCE_KEY_V1,
        "amount_ngwee": "25000",
        "status": "queued",
        "refund_id": "",
        "payout_id": "",
        "attempts": "0",
        "next_retry_at": "",
        "last_error": "",
    }
    monkeypatch.setattr("app.services.events.refund_jobs.run_sql_script", state.run)

    with patch(
        "app.services.events.refund_jobs.process_event_refund_job",
        return_value=EventRefundJobProcessResult(JOB_ID, "needs_destination"),
    ):
        result = sweep_event_refund_jobs(FakeService(FakeClient({})), limit=10)

    assert result.scanned == 1
    assert result.needs_destination == 1


def test_tick_requires_internal_token() -> None:
    from app.main import create_app
    from app.services.events.refund_jobs import EventRefundJobSweepResult
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        denied = client.post("/internal/event-refund-jobs/tick")
        assert denied.status_code == 401

        with patch(
            "app.routers.internal_event_refund_jobs.sweep_event_refund_jobs",
            return_value=EventRefundJobSweepResult(
                scanned=1,
                executed=0,
                awaiting_payout=1,
                needs_destination=0,
                manual_review=0,
                completed=0,
                retried=0,
                dead=0,
                skipped=0,
            ),
        ):
            ok = client.post(
                "/internal/event-refund-jobs/tick",
                headers={"X-Internal-Token": "dev-internal-event-refund-jobs"},
            )
        assert ok.status_code == 200
        assert ok.json()["awaiting_payout"] == 1
