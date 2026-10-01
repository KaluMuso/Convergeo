"""F1 payout claim, RLS, and ledger checks on isolated PostgreSQL/PostgREST."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from app.errors import AppError
from app.services.payments.base import ProviderOutcome, ProviderResult
from app.services.payouts.obligation import PayoutObservationMismatch, make_obligation
from app.services.payouts.reservation import reserve_payout_row
from app.services.payouts.resolve_check import VendorPayoutProfile
from app.services.payouts.retry import (
    _claim_first_dispatch,
    _complete_verified_payout,
    retry_payout_row,
)
from app.settings import get_settings
from app.supabase_client import SupabaseServiceClient, get_supabase_service_client
from tests.rls.conftest import (
    Persona,
    PgConn,
    RoleSession,
    assert_tester_is_rls_bound,
    ensure_roles,
    grant_tester_access,
    schema_ready,
    seed_matrix_fixtures,
)
from tests.rls.conftest import fixture_ids as fixture_ids


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"F1 real-stack prerequisite missing: {name}")
    return value


@pytest.fixture(scope="module")
def f1_real_db() -> Generator[PgConn, None, None]:
    """Require a pre-migrated disposable database; never skip or rebuild schema."""
    if shutil.which("psql") is None:
        pytest.fail("F1 real-stack prerequisite missing: psql")
    dsn = _required_env("SUPABASE_DB_URL")
    expected_database = _required_env("F1_REAL_STACK_DATABASE")
    parsed = urlsplit(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.path != f"/{expected_database}"
    ):
        pytest.fail("F1 SQL fixture target is not the declared disposable database")
    conn = PgConn(dsn)
    identity = conn.run("SELECT current_database()")
    if not identity.ok or identity.rows != [expected_database]:
        pytest.fail("F1 SQL connection does not match F1_REAL_STACK_DATABASE")
    if not schema_ready(conn):
        pytest.fail("F1 disposable database is not pre-migrated")
    ensure_roles(conn)
    grant_tester_access(conn)
    assert_tester_is_rls_bound(conn)
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture(scope="module")
def f1_service_client(f1_real_db: PgConn) -> Generator[SupabaseServiceClient, None, None]:
    """Use the application factory and prove REST reaches the SQL fixture database."""
    url = _required_env("SUPABASE_URL")
    _required_env("SUPABASE_SERVICE_ROLE_KEY")
    expected_database = _required_env("F1_REAL_STACK_DATABASE")
    expected_group = _required_env("F1_REAL_STACK_GROUP")
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail("F1 real-stack test refuses a non-loopback Supabase target")
    get_supabase_service_client.cache_clear()
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.supabase_url.rstrip("/") == url.rstrip("/")
    service = get_supabase_service_client()
    client = service.client
    rest_url = urlsplit(str(client.rest_url))
    assert rest_url.hostname in {"127.0.0.1", "localhost", "::1"}
    assert rest_url.path.rstrip("/").endswith("/rest/v1")
    rows = (
        client.table("ci_critical_binding_probe")
        .select("group_name,database_name")
        .eq("group_name", expected_group)
        .eq("database_name", expected_database)
        .execute()
        .data
    )
    assert rows == [
        {"group_name": expected_group, "database_name": expected_database}
    ], "application service client and SQL fixtures target different databases"
    yield service
    if client._postgrest is not None:
        client.postgrest.aclose()
    get_supabase_service_client.cache_clear()
    get_settings.cache_clear()


def test_real_postgrest_claim_rls_and_ledger_replay(
    f1_real_db: PgConn,
    f1_service_client: SupabaseServiceClient,
    fixture_ids: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two REST workers claim once; completion posts one balanced ledger entry."""
    monkeypatch.setenv("SUPABASE_DB_URL", f1_real_db.dsn)
    monkeypatch.setenv("LENCO_ACCOUNT_ID", "f1-isolated-debit-account")
    service = f1_service_client
    as_anon = RoleSession(f1_real_db, Persona.ANON)
    as_vendor = RoleSession(f1_real_db, Persona.VENDOR)
    vendor_id = str(fixture_ids["vendors"]["shop_a"])
    payout_id = str(uuid.uuid4())
    reference = f"pay-f1-{uuid.uuid4().hex}"
    phone = "260971123456"
    amount_ngwee = 37_500
    obligation = make_obligation(
        merchant_reference=reference,
        amount_ngwee=amount_ngwee,
        debit_account_id=None,
        destination={"type": "mobile-money", "phone": phone, "operator": "mtn"},
    )
    initial_snapshot = {
        "obligation": obligation,
        "dispatch": {"state": "never_sent"},
    }
    snapshot_json = json.dumps(initial_snapshot, separators=(",", ":")).replace(
        "'", "''"
    )
    insert = f1_real_db.run(
        f"""
        INSERT INTO public.ledger_accounts (kind, vendor_id)
        VALUES ('platform_cash', NULL), ('vendor_payable', '{vendor_id}'::uuid)
        ON CONFLICT DO NOTHING;
        INSERT INTO public.payouts (
          id, vendor_id, amount_ngwee, rail, lenco_reference, status,
          payout_kind, resolve_snapshot
        ) VALUES (
          '{payout_id}'::uuid, '{vendor_id}'::uuid, {amount_ngwee}, 'mtn',
          '{reference}', 'pending', 'vendor',
          '{snapshot_json}'::jsonb
        );
        """
    )
    assert insert.ok, insert.error

    payout_row = {
        "id": payout_id,
        "vendor_id": vendor_id,
        "amount_ngwee": amount_ngwee,
        "rail": "mtn",
        "lenco_reference": reference,
        "status": "pending",
    }
    snapshot = initial_snapshot
    profile = VendorPayoutProfile(
        vendor_id=vendor_id,
        owner_user_id="33333333-3333-3333-3333-333333333333",
        phone=phone,
        operator="mtn",
        legal_name="F1 Isolated Vendor",
        rail="mtn",
    )

    def claim() -> dict[str, Any] | None:
        return _claim_first_dispatch(
            service,
            payout_row=payout_row,
            snapshot=snapshot,
            profile=profile,
            clock=datetime.now(UTC),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _index: claim(), range(2)))
    winners = [claim_snapshot for claim_snapshot in claims if claim_snapshot is not None]
    assert len(winners) == 1
    claimed_snapshot = winners[0]
    assert claimed_snapshot["dispatch"]["state"] == "claimed"

    anon = as_anon.execute(
        f"SELECT count(*)::text FROM public.payouts WHERE id = '{payout_id}'::uuid"
    )
    vendor = as_vendor.execute(
        f"SELECT count(*)::text FROM public.payouts WHERE id = '{payout_id}'::uuid"
    )
    assert anon.ok and anon.rows == ["0"]
    assert vendor.ok and vendor.rows == ["1"]

    observation = ProviderResult(
        requested_reference=reference,
        outcome=ProviderOutcome.SUCCESSFUL,
        reference=reference,
        status="successful",
        amount_major="375.00",
        currency="ZMW",
        provider_reference=f"lenco-{uuid.uuid4().hex}",
        debit_account_id="f1-isolated-debit-account",
        destination={"type": "mobile-money", "phone": phone, "operator": "mtn"},
    )
    processing_row = {**payout_row, "status": "processing"}
    assert (
        _complete_verified_payout(
            service,
            payout_row=processing_row,
            snapshot=claimed_snapshot,
            observation=observation,
            source="f1_real_stack",
        )
        == "completed"
    )
    assert (
        _complete_verified_payout(
            service,
            payout_row=processing_row,
            snapshot=claimed_snapshot,
            observation=observation,
            source="f1_real_stack_replay",
        )
        == "completed"
    )

    accounting = f1_real_db.run(
        f"""
        SELECT
          p.status,
          count(DISTINCT t.id)::text,
          count(lp.id)::text,
          coalesce(sum(lp.amount_ngwee), 0)::text
        FROM public.payouts p
        LEFT JOIN public.ledger_transactions t ON t.payout_id = p.id
        LEFT JOIN public.ledger_postings lp ON lp.transaction_id = t.id
        WHERE p.id = '{payout_id}'::uuid
        GROUP BY p.status;
        """
    )
    assert accounting.ok, accounting.error
    assert accounting.rows == ["paid|1|2|0"]


def test_real_postgres_reservation_lock_prevents_double_dispatch_capacity(
    f1_real_db: PgConn,
    fixture_ids: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The advisory transaction lock serializes balance check plus reservation."""
    monkeypatch.setenv("SUPABASE_DB_URL", f1_real_db.dsn)
    vendor_id = str(fixture_ids["vendors"]["shop_b"])
    release_id = str(uuid.uuid4())
    release_key = f"f1-real-release-{uuid.uuid4().hex}"
    seeded = f1_real_db.run(
        f"""
        INSERT INTO public.ledger_accounts (kind, vendor_id)
        VALUES ('platform_cash', NULL), ('vendor_payable', '{vendor_id}'::uuid)
        ON CONFLICT DO NOTHING;
        WITH tx AS (
          INSERT INTO public.ledger_transactions (id, kind, idempotency_key)
          VALUES ('{release_id}'::uuid, 'release_to_vendor', '{release_key}')
          RETURNING id
        ), accounts AS (
          SELECT
            (SELECT id FROM public.ledger_accounts
             WHERE kind = 'platform_cash' AND vendor_id IS NULL LIMIT 1) AS cash_id,
            (SELECT id FROM public.ledger_accounts
             WHERE kind = 'vendor_payable' AND vendor_id = '{vendor_id}'::uuid
             LIMIT 1) AS payable_id
        )
        INSERT INTO public.ledger_postings (transaction_id, account_id, amount_ngwee)
        SELECT tx.id, accounts.cash_id, 100000 FROM tx, accounts
        UNION ALL
        SELECT tx.id, accounts.payable_id, -100000 FROM tx, accounts;
        """
    )
    assert seeded.ok, seeded.error

    def reserve(index: int) -> str:
        payout_id = str(uuid.uuid4())
        reference = f"pay-f1-lock-{index}-{uuid.uuid4().hex}"
        try:
            reserve_payout_row(
                payout_id=payout_id,
                vendor_id=vendor_id,
                amount_ngwee=60_000,
                rail="mtn",
                lenco_reference=reference,
                resolve_snapshot={
                    "obligation": make_obligation(
                        merchant_reference=reference,
                        amount_ngwee=60_000,
                        debit_account_id="f1-isolated-debit-account",
                        destination={
                            "type": "mobile-money",
                            "phone": "260971654321",
                            "operator": "mtn",
                        },
                    ),
                    "dispatch": {"state": "claimed"},
                },
                status="processing",
            )
        except AppError as exc:
            assert exc.code == "insufficient_released_balance"
            return "rejected"
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, range(2)))
    assert sorted(outcomes) == ["rejected", "reserved"]
    reserved = f1_real_db.run(
        f"""
        SELECT coalesce(sum(amount_ngwee), 0)::text
        FROM public.payouts
        WHERE vendor_id = '{vendor_id}'::uuid
          AND lenco_reference LIKE 'pay-f1-lock-%'
          AND status = 'processing';
        """
    )
    assert reserved.ok and reserved.rows == ["60000"]


@pytest.mark.parametrize("outcome", list(ProviderOutcome))
def test_real_postgrest_historical_pending_never_posts_again(
    f1_real_db: PgConn,
    f1_service_client: SupabaseServiceClient,
    fixture_ids: dict[str, Any],
    outcome: ProviderOutcome,
) -> None:
    """Real REST persistence; only the external provider result is synthetic.

    An old pending transfer may have been accepted before its status write.
    No marker or new immutable obligation may be fabricated for that row.
    """
    payout_id = str(uuid.uuid4())
    reference = f"pay-legacy-{uuid.uuid4().hex}"
    vendor_id = str(fixture_ids["vendors"]["shop_a"])
    snapshot: dict[str, Any] = {"matched": True, "retry_attempts": 0}
    row: dict[str, Any] = {
        "id": payout_id,
        "vendor_id": vendor_id,
        "amount_ngwee": 37_500,
        "rail": "mtn",
        "lenco_reference": reference,
        "status": "pending",
        "payout_kind": "vendor",
        "resolve_snapshot": snapshot,
    }
    f1_service_client.client.table("payouts").insert(row).execute()
    observation = ProviderResult(
        requested_reference=reference,
        outcome=outcome,
        reference=reference,
        provider_reference=f"provider-{payout_id}",
        status=outcome.value,
        amount_major="375.00",
        currency="ZMW",
        debit_account_id="f1-isolated-debit-account",
        destination={"type": "mobile-money", "phone": "260971123456", "operator": "mtn"},
    )
    query = AsyncMock(return_value=observation)
    post = AsyncMock(side_effect=AssertionError("historical transfer was re-sent"))

    class SyntheticStatusQuerier:
        async def query_transfer_status(self, reference: str) -> ProviderResult:
            result = await query(reference)
            assert isinstance(result, ProviderResult)
            return result

    async def retry_historical_payout() -> str:
        return await retry_payout_row(
            f1_service_client,
            row,
            query_transfer_status=SyntheticStatusQuerier(),
            initiate_momo_payout=post,
            initiate_bank_payout=post,
        )

    if outcome == ProviderOutcome.SUCCESSFUL:
        # Missing historical evidence is held, not inferred from today's profile.
        with pytest.raises(PayoutObservationMismatch, match="does not match"):
            asyncio.run(retry_historical_payout())
    else:
        asyncio.run(retry_historical_payout())
    query.assert_awaited_once_with(reference)
    post.assert_not_awaited()
    after = (
        f1_service_client.client.table("payouts")
        .select("status,resolve_snapshot")
        .eq("id", payout_id)
        .single()
        .execute()
        .data
    )
    assert isinstance(after, dict), "Expected one persisted payout object"
    assert after["status"] == "processing"
    after_snapshot = after["resolve_snapshot"]
    assert isinstance(after_snapshot, dict), "Expected a persisted resolve snapshot"
    assert "obligation" not in after_snapshot
    dispatch = after_snapshot["dispatch"]
    assert isinstance(dispatch, dict), "Expected a persisted dispatch object"
    assert dispatch["state"] != "never_sent"
    result = f1_real_db.run(
        "SELECT count(*)::text FROM public.ledger_transactions "
        f"WHERE payout_id='{payout_id}';"
    )
    assert result.ok and result.rows == ["0"], result.error
