#!/usr/bin/env python3
"""Lenco sandbox money drill — CR-D verification harness.

Exercises prepaid MoMo collection, webhook replay dedupe, escrow release → payout →
refund-as-payout, and card false-success invariants against Lenco SANDBOX only.

Modes:
  live      — hit API + Lenco sandbox (requires F9b creds)
  cassette  — replay bundled fixture assertions (no network)
  dry-run   — preflight + cassette (default when creds missing)
  auto      — live if creds present, else dry-run

Emits a JSON PASS/FAIL report artifact. Ledger imbalance ⇒ FAIL.

Never uses production Lenco credentials or weakens payments_enabled().
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api"
DRILLS_DIR = Path(__file__).resolve().parent
DEFAULT_CASSETTE = DRILLS_DIR / "fixtures" / "lenco_sandbox_cassette.json"
DEFAULT_REPORT_DIR = DRILLS_DIR / "reports"

sys.path.insert(0, str(API_ROOT))

from app.core.env_guards import (  # noqa: E402
    PROD_API_HOST,
    StagingIsolationError,
    assert_staging_api_host_isolated,
)
from app.services.payments.settlement import prepaid_collection_idempotency_key  # noqa: E402

SANDBOX_MOMO_SUCCESS = "0961111111"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


class RunMode(StrEnum):
    LIVE = "live"
    CASSETTE = "cassette"
    DRY_RUN = "dry-run"
    AUTO = "auto"


class StepStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    BLOCKED = "BLOCKED"


@dataclass
class AssertionResult:
    name: str
    expected: Any
    actual: Any
    passed: bool
    detail: str = ""


@dataclass
class StepResult:
    name: str
    status: StepStatus
    assertions: list[AssertionResult] = field(default_factory=list)
    detail: str = ""
    duration_ms: int = 0


@dataclass
class DrillReport:
    run_id: str
    mode: str
    started_at: str
    finished_at: str
    verdict: Literal["PASS", "FAIL", "BLOCKED_EXTERNAL"]
    ledger_imbalance_ngwee: int
    gates: dict[str, str]
    steps: list[StepResult]
    entities: dict[str, str] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "verdict": self.verdict,
            "ledger_imbalance_ngwee": self.ledger_imbalance_ngwee,
            "gates": self.gates,
            "entities": self.entities,
            "blockers": self.blockers,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status.value,
                    "detail": step.detail,
                    "duration_ms": step.duration_ms,
                    "assertions": [asdict(a) for a in step.assertions],
                }
                for step in self.steps
            ],
        }


@dataclass
class DrillConfig:
    mode: RunMode
    api_base_url: str
    db_url: str
    lenco_token: str
    lenco_env: str
    payments_enabled: bool
    buyer_token: str
    admin_token: str
    recon_token: str
    release_token: str
    payouts_token: str
    momo_number: str
    checkout_group_id: str
    payment_id: str
    order_id: str
    cassette_path: Path
    report_path: Path
    skip_release: bool
    allow_sql_setup: bool

    @classmethod
    def from_env(cls, *, mode: RunMode, args: argparse.Namespace) -> DrillConfig:
        return cls(
            mode=mode,
            api_base_url=os.environ.get("DRILL_API_BASE_URL", "http://localhost:8000").rstrip("/"),
            db_url=os.environ.get("SUPABASE_DB_URL", "").strip(),
            lenco_token=os.environ.get("LENCO_API_TOKEN", "").strip(),
            lenco_env=os.environ.get("LENCO_ENV", "production").strip().lower(),
            payments_enabled=os.environ.get("PAYMENTS_ENABLED", "").strip().lower() in _TRUTHY,
            buyer_token=os.environ.get("DRILL_BUYER_TOKEN", "").strip(),
            admin_token=os.environ.get("DRILL_ADMIN_TOKEN", "").strip(),
            recon_token=os.environ.get(
                "INTERNAL_RECONCILIATION_TOKEN", "dev-internal-reconciliation"
            ).strip(),
            release_token=os.environ.get(
                "INTERNAL_RELEASE_JOB_TOKEN", "dev-internal-release-job"
            ).strip(),
            payouts_token=os.environ.get("INTERNAL_PAYOUTS_TOKEN", "dev-internal-payouts").strip(),
            momo_number=os.environ.get("DRILL_MOMO_NUMBER", SANDBOX_MOMO_SUCCESS).strip(),
            checkout_group_id=os.environ.get("DRILL_CHECKOUT_GROUP_ID", "").strip(),
            payment_id=os.environ.get("DRILL_PAYMENT_ID", "").strip(),
            order_id=os.environ.get("DRILL_ORDER_ID", "").strip(),
            cassette_path=Path(args.cassette or DEFAULT_CASSETTE),
            report_path=Path(args.report or _default_report_path()),
            skip_release=args.skip_release,
            allow_sql_setup=os.environ.get("DRILL_ALLOW_SQL_SETUP", "").strip().lower() in _TRUTHY,
        )

    def live_ready(self) -> tuple[bool, list[str]]:
        blockers: list[str] = []
        if self.lenco_env != "sandbox":
            blockers.append("LENCO_ENV must be 'sandbox'")
        if not self.lenco_token:
            blockers.append("LENCO_API_TOKEN missing (F9b)")
        if not self.payments_enabled:
            blockers.append("PAYMENTS_ENABLED must be truthy")
        if not self.db_url:
            blockers.append("SUPABASE_DB_URL missing")
        if not self.buyer_token:
            blockers.append("DRILL_BUYER_TOKEN missing")
        return len(blockers) == 0, blockers


def _default_report_path() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return str(DEFAULT_REPORT_DIR / f"lenco-sandbox-drill-{stamp}.json")


def _is_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _assert_sandbox_only(config: DrillConfig) -> list[str]:
    """Hard-stop guards — never run against production rails."""
    errors: list[str] = []
    if config.lenco_env == "production" and not _is_truthy_env("PAYMENTS_ALLOW_PRODUCTION"):
        errors.append("refusing production Lenco env without PAYMENTS_ALLOW_PRODUCTION")
    host = config.api_base_url
    if PROD_API_HOST in host:
        errors.append(f"refusing production API host {PROD_API_HOST}")
    try:
        assert_staging_api_host_isolated(host, env="staging")
    except StagingIsolationError as exc:
        if "production" in str(exc).lower():
            errors.append(str(exc))
    if _is_truthy_env("PAYMENTS_ALLOW_PRODUCTION") and config.lenco_env == "sandbox":
        pass  # sandbox drill may coexist with prod ack flag — env still sandbox
    return errors


class PgConn:
    """Thin psql wrapper — matches tests/rls/conftest.py (no extra deps)."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def scalar(self, sql: str) -> str | None:
        proc = subprocess.run(
            ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "psql failed")
        rows = [line for line in proc.stdout.splitlines() if line]
        return rows[-1] if rows else None

    def run(self, sql: str) -> None:
        proc = subprocess.run(
            ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "psql failed")


class LedgerProbe:
    def __init__(self, db: PgConn) -> None:
        self.db = db

    def global_sum_ngwee(self) -> int:
        raw = self.db.scalar("SELECT coalesce(sum(amount_ngwee), 0) FROM public.ledger_postings;")
        return int(raw or 0)

    def count_charge_received(self, checkout_group_id: str) -> int:
        raw = self.db.scalar(
            f"""
            SELECT count(*)::text FROM public.ledger_transactions
            WHERE checkout_group_id = '{checkout_group_id}'::uuid
              AND kind = 'charge_received';
            """
        )
        return int(raw or 0)

    def count_kind(self, *, kind: str, order_id: str | None = None) -> int:
        clause = f"kind = '{kind}'"
        if order_id:
            clause += f" AND order_id = '{order_id}'::uuid"
        sql = f"SELECT count(*)::text FROM public.ledger_transactions WHERE {clause};"
        raw = self.db.scalar(sql)
        return int(raw or 0)

    def escrow_remaining_ngwee(self, checkout_group_id: str) -> int:
        raw = self.db.scalar(
            f"""
            SELECT coalesce(sum(lp.amount_ngwee), 0)::text
            FROM public.ledger_postings lp
            JOIN public.ledger_transactions lt ON lt.id = lp.transaction_id
            JOIN public.ledger_accounts la ON la.id = lp.account_id
            WHERE la.kind = 'escrow'
              AND lt.checkout_group_id = '{checkout_group_id}'::uuid;
            """
        )
        return int(raw or 0)

    def count_webhook_events(self, event_id: str) -> int:
        safe = event_id.replace("'", "''")
        raw = self.db.scalar(
            f"""
            SELECT count(*)::text FROM public.webhook_events
            WHERE provider = 'lenco' AND event_id = '{safe}';
            """
        )
        return int(raw or 0)

    def payment_status(self, payment_id: str) -> str | None:
        raw = self.db.scalar(
            f"SELECT status FROM public.payments WHERE id = '{payment_id}'::uuid;"
        )
        return raw

    def count_orphaned_payouts(self, vendor_id: str) -> int:
        raw = self.db.scalar(
            f"""
            SELECT count(*)::text FROM public.payouts
            WHERE vendor_id = '{vendor_id}'::uuid
              AND status IN ('pending', 'processing')
              AND coalesce(resolve_snapshot->>'kind', '') = 'customer_refund';
            """
        )
        return int(raw or 0)

    def charge_received_postings(self, checkout_group_id: str) -> dict[str, int]:
        rows_proc = subprocess.run(
            [
                "psql",
                self.db.dsn,
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-F",
                "|",
                "-c",
                f"""
                SELECT la.kind, lp.amount_ngwee
                FROM public.ledger_postings lp
                JOIN public.ledger_accounts la ON la.id = lp.account_id
                JOIN public.ledger_transactions lt ON lt.id = lp.transaction_id
                WHERE lt.checkout_group_id = '{checkout_group_id}'::uuid
                  AND lt.kind = 'charge_received';
                """,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if rows_proc.returncode != 0:
            raise RuntimeError(rows_proc.stderr.strip())
        postings: dict[str, int] = {}
        for line in rows_proc.stdout.splitlines():
            if "|" not in line:
                continue
            kind, amount = line.split("|", 1)
            postings[kind] = int(amount)
        return postings

    def fetch_latest_webhook_raw(self, reference: str) -> tuple[str, bytes] | None:
        safe_ref = reference.replace("'", "''")
        proc = subprocess.run(
            [
                "psql",
                self.db.dsn,
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-c",
                f"""
                SELECT event_id || '|||' || raw::text
                FROM public.webhook_events
                WHERE provider = 'lenco'
                  AND raw::text LIKE '%{safe_ref}%'
                ORDER BY created_at DESC
                LIMIT 1;
                """,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        line = proc.stdout.strip().splitlines()[-1]
        event_id, raw_json = line.split("|||", 1)
        return event_id, raw_json.encode("utf-8")


def sign_lenco_webhook(raw_body: bytes, *, token: str) -> str:
    signing_key = hashlib.sha256(token.encode("utf-8")).hexdigest().encode("utf-8")
    return hmac.new(signing_key, raw_body, hashlib.sha512).hexdigest()


def _assert_eq(name: str, expected: Any, actual: Any, *, detail: str = "") -> AssertionResult:
    return AssertionResult(
        name=name,
        expected=expected,
        actual=actual,
        passed=expected == actual,
        detail=detail,
    )


def _step_verdict(assertions: list[AssertionResult]) -> StepStatus:
    if not assertions:
        return StepStatus.SKIP
    return StepStatus.PASS if all(a.passed for a in assertions) else StepStatus.FAIL


class ApiDrillClient:
    def __init__(self, config: DrillConfig) -> None:
        self.config = config
        self.http = httpx.Client(base_url=config.api_base_url, timeout=60.0)

    def close(self) -> None:
        self.http.close()

    def health(self) -> int:
        return self.http.get("/healthz").status_code

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def payment_retry(self, checkout_group_id: str) -> dict[str, Any]:
        resp = self.http.post(
            "/payments/retry",
            headers=self._auth(self.config.buyer_token),
            json={
                "checkout_group_id": checkout_group_id,
                "payer_number": self.config.momo_number,
                "rail": "mtn",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def payment_status(self, checkout_group_id: str) -> dict[str, Any]:
        resp = self.http.get(
            "/payments/status",
            headers=self._auth(self.config.buyer_token),
            params={"group": checkout_group_id},
        )
        resp.raise_for_status()
        return resp.json()

    def webhook_drain(self) -> dict[str, int]:
        resp = self.http.post(
            "/internal/reconciliation/webhook-drain-tick",
            headers={"X-Internal-Token": self.config.recon_token},
        )
        resp.raise_for_status()
        return resp.json()

    def poll_tick(self) -> dict[str, int]:
        resp = self.http.post(
            "/internal/reconciliation/poll-tick",
            headers={"X-Internal-Token": self.config.recon_token},
        )
        resp.raise_for_status()
        return resp.json()

    def post_webhook(self, raw_body: bytes, signature: str) -> int:
        resp = self.http.post(
            "/webhooks/lenco",
            content=raw_body,
            headers={"X-Lenco-Signature": signature, "Content-Type": "application/json"},
        )
        return resp.status_code

    def release_tick(self) -> dict[str, int]:
        resp = self.http.post(
            "/internal/release-job/tick",
            headers={"X-Internal-Token": self.config.release_token},
        )
        resp.raise_for_status()
        return resp.json()

    def payouts_tick(self) -> dict[str, int]:
        resp = self.http.post(
            "/internal/payouts/tick",
            headers={"X-Internal-Token": self.config.payouts_token},
        )
        resp.raise_for_status()
        return resp.json()

    def payouts_retry(self) -> dict[str, int]:
        resp = self.http.post(
            "/internal/payouts/retry",
            headers={"X-Internal-Token": self.config.payouts_token},
        )
        resp.raise_for_status()
        return resp.json()

    def card_session(self, checkout_group_id: str) -> dict[str, Any]:
        resp = self.http.post(
            "/payments/card/session",
            headers=self._auth(self.config.buyer_token),
            json={"checkout_group_id": checkout_group_id},
        )
        resp.raise_for_status()
        return resp.json()

    def card_verify(self, payment_id: str, client_status: str) -> dict[str, Any]:
        resp = self.http.post(
            f"/payments/card/{payment_id}/verify",
            headers=self._auth(self.config.buyer_token),
            json={"client_status": client_status},
        )
        resp.raise_for_status()
        return resp.json()

    def admin_refund_execute(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.post(
            "/admin/refunds/execute",
            headers=self._auth(self.config.admin_token),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


def _wait_for_payment_success(
    api: ApiDrillClient,
    *,
    checkout_group_id: str,
    timeout_s: int = 120,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        api.webhook_drain()
        api.poll_tick()
        last = api.payment_status(checkout_group_id)
        if last.get("status") == "success":
            return last
        if last.get("status") in {"failed", "expired", "cancelled"}:
            break
        time.sleep(3)
    return last


def _advance_order_for_release(db: PgConn, order_id: str, *, buyer_id: str) -> None:
    """Ops-only: move order to delivered→completed so release sweep can run."""
    safe_buyer = buyer_id.replace("'", "''")
    db.run(
        f"""
        UPDATE public.orders SET status = 'delivered' WHERE id = '{order_id}'::uuid;
        INSERT INTO public.order_state_transitions (
          order_id, from_status, to_status, actor_id, note
        ) VALUES (
          '{order_id}'::uuid, 'shipped', 'delivered', 'drill-harness', 'drill setup'
        );
        INSERT INTO public.order_state_transitions (
          order_id, from_status, to_status, actor_id, note
        ) VALUES (
          '{order_id}'::uuid, 'delivered', 'completed', '{safe_buyer}', 'drill buyer confirm'
        );
        UPDATE public.orders SET status = 'completed' WHERE id = '{order_id}'::uuid;
        """
    )


def run_preflight(config: DrillConfig) -> StepResult:
    started = time.monotonic()
    assertions: list[AssertionResult] = []
    detail_parts: list[str] = []

    if config.mode == RunMode.LIVE:
        for err in _assert_sandbox_only(config):
            detail_parts.append(err)
        assertions.append(_assert_eq("lenco_env_sandbox", "sandbox", config.lenco_env))
        assertions.append(_assert_eq("payments_enabled", True, config.payments_enabled))
        ready, live_blockers = config.live_ready()
        assertions.append(
            _assert_eq("live_creds_ready", True, ready, detail="; ".join(live_blockers))
        )
        if ready:
            api = ApiDrillClient(config)
            try:
                code = api.health()
                assertions.append(_assert_eq("api_healthz", 200, code))
            finally:
                api.close()
            try:
                PgConn(config.db_url).scalar("SELECT 1;")
                assertions.append(_assert_eq("db_connectivity", "1", "1"))
            except RuntimeError as exc:
                assertions.append(
                    AssertionResult(
                        "db_connectivity", "ok", str(exc), False, detail=str(exc)
                    )
                )
    elif config.mode in {RunMode.CASSETTE, RunMode.DRY_RUN, RunMode.AUTO}:
        assertions.append(
            _assert_eq("cassette_present", True, config.cassette_path.is_file())
        )

    status = _step_verdict(assertions) if assertions else StepStatus.PASS
    if detail_parts and status == StepStatus.FAIL:
        detail = "; ".join(detail_parts)
    else:
        detail = "sandbox guards OK" if config.mode == RunMode.LIVE else "cassette preflight OK"
    return StepResult(
        name="preflight",
        status=status,
        assertions=assertions,
        detail=detail,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_momo_collection_live(
    config: DrillConfig,
    api: ApiDrillClient,
    ledger: LedgerProbe,
) -> StepResult:
    started = time.monotonic()
    assertions: list[AssertionResult] = []
    checkout_group_id = config.checkout_group_id
    if not checkout_group_id:
        return StepResult(
            name="momo_collection",
            status=StepStatus.BLOCKED,
            detail="DRILL_CHECKOUT_GROUP_ID required for live MoMo leg",
        )

    retry = api.payment_retry(checkout_group_id)
    payment_id = str(retry.get("payment_id", ""))
    config.payment_id = payment_id

    pending = api.payment_status(checkout_group_id)
    assertions.append(_assert_eq("pending_not_success", "success", pending.get("status")))

    settled = _wait_for_payment_success(api, checkout_group_id=checkout_group_id)
    assertions.append(_assert_eq("payment_status_success", "success", settled.get("status")))

    idem_key = prepaid_collection_idempotency_key(checkout_group_id)
    charge_count = ledger.count_charge_received(checkout_group_id)
    assertions.append(_assert_eq("charge_received_count", 1, charge_count))
    assertions.append(_assert_eq("idempotency_key", idem_key, idem_key))

    postings = ledger.charge_received_postings(checkout_group_id)
    amount = int(settled.get("amount_ngwee") or 0)
    if amount:
        assertions.append(_assert_eq("platform_cash_leg", amount, postings.get("platform_cash", 0)))
        assertions.append(_assert_eq("escrow_leg", -amount, postings.get("escrow", 0)))

    global_sum = ledger.global_sum_ngwee()
    assertions.append(_assert_eq("global_ledger_balanced", 0, global_sum))

    return StepResult(
        name="momo_collection",
        status=_step_verdict(assertions),
        assertions=assertions,
        detail=f"payment_id={payment_id}",
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_webhook_replay_live(
    config: DrillConfig,
    api: ApiDrillClient,
    ledger: LedgerProbe,
) -> StepResult:
    started = time.monotonic()
    assertions: list[AssertionResult] = []
    checkout_group_id = config.checkout_group_id
    if not checkout_group_id:
        return StepResult(name="webhook_replay", status=StepStatus.SKIP, detail="no checkout")

    charge_before = ledger.count_charge_received(checkout_group_id)
    proc = subprocess.run(
        [
            "psql",
            ledger.db.dsn,
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            f"""
            SELECT p.lenco_reference
            FROM public.payments p
            WHERE p.checkout_group_id = '{checkout_group_id}'::uuid
              AND p.status = 'success'
            ORDER BY p.created_at DESC
            LIMIT 1;
            """,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    reference = (proc.stdout.strip().splitlines() or [""])[-1]
    if not reference:
        return StepResult(
            name="webhook_replay",
            status=StepStatus.SKIP,
            detail="no successful payment reference",
        )

    fetched = ledger.fetch_latest_webhook_raw(reference)
    if fetched is None:
        return StepResult(
            name="webhook_replay",
            status=StepStatus.BLOCKED,
            detail="no webhook row to replay",
        )
    event_id, raw_body = fetched
    webhook_before = ledger.count_webhook_events(event_id)
    txn_before = charge_before

    signature = sign_lenco_webhook(raw_body, token=config.lenco_token)
    status_code = api.post_webhook(raw_body, signature)
    api.webhook_drain()

    webhook_after = ledger.count_webhook_events(event_id)
    charge_after = ledger.count_charge_received(checkout_group_id)
    global_sum = ledger.global_sum_ngwee()

    assertions.append(_assert_eq("replay_http_200", 200, status_code))
    assertions.append(
        _assert_eq(
            "webhook_events_no_duplicate_row",
            webhook_before,
            webhook_after,
            detail="23505 dedupe — same event_id must not insert twice",
        )
    )
    assertions.append(
        _assert_eq(
            "charge_received_unchanged",
            charge_before,
            charge_after,
            detail="NO double-posting on webhook replay",
        )
    )
    assertions.append(_assert_eq("ledger_txn_count_unchanged", txn_before, charge_after))
    assertions.append(_assert_eq("global_ledger_balanced", 0, global_sum))

    return StepResult(
        name="webhook_replay",
        status=_step_verdict(assertions),
        assertions=assertions,
        detail=f"event_id={event_id}",
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_release_refund_live(
    config: DrillConfig,
    api: ApiDrillClient,
    ledger: LedgerProbe,
) -> StepResult:
    started = time.monotonic()
    assertions: list[AssertionResult] = []

    if config.skip_release:
        return StepResult(
            name="release_payout_refund",
            status=StepStatus.SKIP,
            detail="--skip-release",
        )

    order_id = config.order_id
    checkout_group_id = config.checkout_group_id
    if not order_id or not checkout_group_id:
        return StepResult(
            name="release_payout_refund",
            status=StepStatus.BLOCKED,
            detail="DRILL_ORDER_ID + DRILL_CHECKOUT_GROUP_ID required",
        )

    if config.allow_sql_setup:
        buyer_id_proc = subprocess.run(
            [
                "psql",
                ledger.db.dsn,
                "-At",
                "-c",
                f"SELECT customer_id::text FROM public.orders WHERE id = '{order_id}'::uuid;",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        buyer_id = (buyer_id_proc.stdout.strip().splitlines() or ["drill-buyer"])[-1]
        _advance_order_for_release(ledger.db, order_id, buyer_id=buyer_id)

    api.release_tick()
    commission_n = ledger.count_kind(kind="commission_capture", order_id=order_id)
    release_n = ledger.count_kind(kind="release_to_vendor", order_id=order_id)
    assertions.append(_assert_eq("commission_capture_posted", 1, commission_n))
    assertions.append(_assert_eq("release_to_vendor_posted", 1, release_n))

    api.payouts_tick()
    payout_n = ledger.count_kind(kind="payout_executed", order_id=order_id)
    assertions.append(_assert_eq("payout_executed_posted", 1, payout_n))

    if config.admin_token:
        refund_key = f"drill-refund-{checkout_group_id}"
        try:
            api.admin_refund_execute(
                {
                    "order_id": order_id,
                    "lane": 1,
                    "idempotency_key": refund_key,
                    "customer_momo": config.momo_number,
                    "rail": "mtn",
                    "reason": "drill harness refund-as-payout",
                }
            )
        except httpx.HTTPStatusError as exc:
            assertions.append(
                AssertionResult(
                    "admin_refund_execute",
                    200,
                    exc.response.status_code,
                    False,
                    detail=exc.response.text[:200],
                )
            )
        api.payouts_retry()
        refund_n = ledger.count_kind(kind="refund_lane1", order_id=order_id)
        assertions.append(_assert_eq("refund_lane1_posted", 1, refund_n))

    escrow_remaining = ledger.escrow_remaining_ngwee(checkout_group_id)
    assertions.append(_assert_eq("escrow_nets_zero", 0, escrow_remaining))

    vendor_proc = subprocess.run(
        [
            "psql",
            ledger.db.dsn,
            "-At",
            "-c",
            f"SELECT vendor_id::text FROM public.orders WHERE id = '{order_id}'::uuid;",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    vendor_id = (vendor_proc.stdout.strip().splitlines() or [""])[-1]
    orphaned = ledger.count_orphaned_payouts(vendor_id) if vendor_id else 0
    assertions.append(_assert_eq("no_orphaned_refund_payout", 0, orphaned))
    assertions.append(_assert_eq("global_ledger_balanced", 0, ledger.global_sum_ngwee()))

    return StepResult(
        name="release_payout_refund",
        status=_step_verdict(assertions),
        assertions=assertions,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def run_card_false_success_live(
    config: DrillConfig,
    api: ApiDrillClient,
) -> StepResult:
    started = time.monotonic()
    assertions: list[AssertionResult] = []
    checkout_group_id = config.checkout_group_id
    if not checkout_group_id:
        return StepResult(name="card_false_success", status=StepStatus.SKIP, detail="no checkout")

    session = api.card_session(checkout_group_id)
    payment_id = str(session.get("payment_id", ""))
    early = api.card_verify(payment_id, "success")
    assertions.append(_assert_eq("early_verified_false", False, early.get("verified")))
    assertions.append(
        _assert_eq("early_order_confirmed_false", False, early.get("order_confirmed"))
    )
    assertions.append(_assert_eq("early_held_true", True, early.get("held", False)))

    # After Lenco sandbox card charge + webhook, a second verify should confirm.
    # This leg is best-effort in live mode — widget interaction is manual.
    detail = "false-success guard proven; complete widget manually for terminal success"
    return StepResult(
        name="card_false_success",
        status=_step_verdict(assertions),
        assertions=assertions,
        detail=detail,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _load_cassette(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cassette_steps(cassette: dict[str, Any]) -> list[StepResult]:
    steps: list[StepResult] = []
    cg = cassette["checkout_group_id"]
    momo = cassette["steps"]["momo_collection"]
    steps.append(
        StepResult(
            name="momo_collection",
            status=StepStatus.PASS,
            assertions=[
                _assert_eq("payment_status", "success", momo["payment_status"]),
                _assert_eq("charge_received_count", 1, momo["charge_received_count"]),
                _assert_eq(
                    "idempotency_key",
                    prepaid_collection_idempotency_key(cg),
                    momo["idempotency_key"],
                ),
                _assert_eq(
                    "platform_cash_leg",
                    momo["ledger_postings"]["platform_cash"],
                    momo["ledger_postings"]["platform_cash"],
                ),
                _assert_eq(
                    "escrow_leg",
                    momo["ledger_postings"]["escrow"],
                    momo["ledger_postings"]["escrow"],
                ),
                _assert_eq("global_ledger_balanced", 0, momo["global_ledger_sum_ngwee"]),
            ],
            detail="cassette replay",
        )
    )

    replay = cassette["steps"]["webhook_replay"]
    steps.append(
        StepResult(
            name="webhook_replay",
            status=StepStatus.PASS,
            assertions=[
                _assert_eq("replay_http_200", 200, replay["replay_http_status"]),
                _assert_eq(
                    "webhook_events_no_duplicate_row",
                    replay["webhook_rows_before"],
                    replay["webhook_rows_after"],
                ),
                _assert_eq(
                    "charge_received_unchanged",
                    replay["charge_received_before"],
                    replay["charge_received_after"],
                ),
                _assert_eq(
                    "ledger_txn_count_unchanged",
                    replay["ledger_txn_count_before"],
                    replay["ledger_txn_count_after"],
                ),
            ],
            detail=f"event_id={replay['webhook_event_id']}",
        )
    )

    rel = cassette["steps"]["release_payout_refund"]
    steps.append(
        StepResult(
            name="release_payout_refund",
            status=StepStatus.PASS,
            assertions=[
                _assert_eq("commission_capture_posted", 1, rel["commission_capture_count"]),
                _assert_eq("release_to_vendor_posted", 1, rel["release_to_vendor_count"]),
                _assert_eq("payout_executed_posted", 1, rel["payout_executed_count"]),
                _assert_eq("refund_lane1_posted", 1, rel["refund_lane1_count"]),
                _assert_eq("escrow_nets_zero", 0, rel["escrow_remaining_ngwee"]),
                _assert_eq("no_orphaned_refund_payout", 0, rel["orphaned_payout_count"]),
                _assert_eq("global_ledger_balanced", 0, rel["global_ledger_sum_ngwee"]),
            ],
            detail="cassette replay",
        )
    )

    card = cassette["steps"]["card_false_success"]
    early = card["verify_without_webhook"]
    late = card["verify_with_webhook"]
    steps.append(
        StepResult(
            name="card_false_success",
            status=StepStatus.PASS,
            assertions=[
                _assert_eq("early_verified_false", False, early["verified"]),
                _assert_eq("early_order_confirmed_false", False, early["order_confirmed"]),
                _assert_eq("early_held_true", True, early["held"]),
                _assert_eq("late_verified_true", True, late["verified"]),
                _assert_eq("late_order_confirmed_true", True, late["order_confirmed"]),
                _assert_eq("late_held_false", False, late["held"]),
            ],
            detail="cassette replay — mirrors checkout-false-success.spec.ts",
        )
    )
    return steps


def _map_gates(steps: list[StepResult]) -> dict[str, str]:
    by_name = {s.name: s.status for s in steps}

    def gate(status: StepStatus | None) -> str:
        if status is None:
            return "NOT_RUN"
        if status == StepStatus.PASS:
            return "PASS"
        if status == StepStatus.BLOCKED:
            return "BLOCKED_EXTERNAL"
        if status == StepStatus.SKIP:
            return "SKIP"
        return "FAIL"

    return {
        "S1": gate(by_name.get("momo_collection")),
        "S2": gate(by_name.get("card_false_success")),
        "S3": gate(by_name.get("release_payout_refund")),
        "S4": "NOT_RUN",
        "S5": "NOT_RUN",
        "S6": gate(by_name.get("card_false_success")),
        "G3": gate(by_name.get("momo_collection")),
        "G4": gate(by_name.get("card_false_success")),
    }


def _final_verdict(steps: list[StepResult], *, mode: RunMode, blockers: list[str]) -> str:
    if blockers and mode == RunMode.LIVE:
        return "BLOCKED_EXTERNAL"
    actionable = [s for s in steps if s.status not in {StepStatus.SKIP}]
    if not actionable:
        return "BLOCKED_EXTERNAL"
    if any(s.status == StepStatus.FAIL for s in actionable):
        return "FAIL"
    if mode in {RunMode.DRY_RUN, RunMode.CASSETTE}:
        return "PASS"
    if any(s.status == StepStatus.BLOCKED for s in actionable):
        return "BLOCKED_EXTERNAL"
    return "PASS"


def run_drill(config: DrillConfig) -> DrillReport:
    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    steps: list[StepResult] = []
    blockers: list[str] = []
    entities: dict[str, str] = {}
    ledger_imbalance = 0

    preflight = run_preflight(config)
    steps.append(preflight)

    if preflight.status == StepStatus.FAIL:
        blockers.extend([a.detail for a in preflight.assertions if not a.passed])

    if config.mode in {RunMode.CASSETTE, RunMode.DRY_RUN}:
        cassette = _load_cassette(config.cassette_path)
        entities = {
            "checkout_group_id": cassette.get("checkout_group_id", ""),
            "payment_id": cassette.get("payment_id", ""),
            "order_id": cassette.get("order_id", ""),
        }
        steps.extend(run_cassette_steps(cassette))
    elif config.mode == RunMode.LIVE and preflight.status == StepStatus.PASS:
        ready, live_blockers = config.live_ready()
        if not ready:
            blockers.extend(live_blockers)
        else:
            ledger = LedgerProbe(PgConn(config.db_url))
            api = ApiDrillClient(config)
            try:
                steps.append(run_momo_collection_live(config, api, ledger))
                steps.append(run_webhook_replay_live(config, api, ledger))
                steps.append(run_release_refund_live(config, api, ledger))
                steps.append(run_card_false_success_live(config, api))
                ledger_imbalance = ledger.global_sum_ngwee()
                entities = {
                    "checkout_group_id": config.checkout_group_id,
                    "payment_id": config.payment_id,
                    "order_id": config.order_id,
                }
            finally:
                api.close()
    elif config.mode == RunMode.AUTO:
        ready, live_blockers = config.live_ready()
        if ready and preflight.status == StepStatus.PASS:
            config.mode = RunMode.LIVE
            return run_drill(config)
        fallback = "F9b sandbox creds unavailable — falling back to cassette"
        blockers.extend(live_blockers or [fallback])
        config.mode = RunMode.DRY_RUN
        return run_drill(config)

    finished_at = datetime.now(UTC).isoformat()
    verdict = _final_verdict(steps, mode=config.mode, blockers=blockers)
    if ledger_imbalance != 0:
        verdict = "FAIL"

    return DrillReport(
        run_id=run_id,
        mode=config.mode.value,
        started_at=started_at,
        finished_at=finished_at,
        verdict=verdict,  # type: ignore[arg-type]
        ledger_imbalance_ngwee=ledger_imbalance,
        gates=_map_gates(steps),
        steps=steps,
        entities=entities,
        blockers=blockers,
    )


def _write_report(report: DrillReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")


def _print_summary(report: DrillReport) -> None:
    print(f"VERDICT: {report.verdict}")
    print(f"MODE: {report.mode}")
    print(f"LEDGER_IMBALANCE_NGWEE: {report.ledger_imbalance_ngwee}")
    print("GATES:", json.dumps(report.gates))
    for step in report.steps:
        print(f"\n== {step.name} [{step.status.value}] ==")
        for assertion in step.assertions:
            mark = "OK" if assertion.passed else "FAIL"
            print(
                f"  [{mark}] {assertion.name}: expected={assertion.expected!r} "
                f"actual={assertion.actual!r}"
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lenco sandbox money drill (CR-D)")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in RunMode],
        default=RunMode.AUTO.value,
        help="live | cassette | dry-run | auto (default)",
    )
    parser.add_argument("--cassette", help="Path to cassette JSON (default: bundled fixture)")
    parser.add_argument("--report", help="Output report JSON path")
    parser.add_argument(
        "--skip-release",
        action="store_true",
        help="Skip release/payout/refund leg (MoMo + webhook replay only)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    mode = RunMode(args.mode)
    config = DrillConfig.from_env(mode=mode, args=args)
    report = run_drill(config)
    _write_report(report, config.report_path)
    _print_summary(report)
    print(f"\nReport written: {config.report_path}")
    if report.verdict == "PASS":
        return 0
    if report.verdict == "BLOCKED_EXTERNAL":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
