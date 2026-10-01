"""Explicit F3 PostgreSQL/PostgREST gate; invoke this file directly in financial CI.

This module intentionally is not named ``test_*.py``: ordinary unit collection
must not turn unavailable infrastructure into a skip/pass.  The financial runner
must invoke this exact path; absent prerequisites then fail at the first assertion.
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from time import sleep
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from app.services.payments.lenco.reconciliation import LencoReconciliationEvidence
from app.services.payments.reconcile import run_daily_reconciliation_report
from app.services.payments.reconciliation_matcher import (
    AccountSnapshot,
    EvidenceOrigin,
    MovementDirection,
    MovementKind,
    ProviderMovement,
    ProviderPage,
)
from app.services.payments.reconciliation_reader import PostgrestReconciliationReader
from app.services.payments.reconciliation_reports import ReconciliationReportStore
from postgrest import SyncPostgrestClient
from postgrest.exceptions import APIError
from tests.lane_d.test_collection_identity_postgrest import _db, _jwt, _service

REPORT_DATE = date(2099, 12, 30)


def _checkout_binding() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[4]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    return head, tree


def _require_stack() -> None:
    missing = [
        name
        for name in (
            "SUPABASE_DB_URL",
            "LANE_D_POSTGREST_URL",
            "LANE_D_JWT_SECRET",
            "F3_REPORT_DATABASE",
            "F3_DISPOSABLE_REPORT_DB",
        )
        if not os.environ.get(name)
    ]
    assert not missing, f"F3 isolated real-stack prerequisites missing: {missing!r}"
    assert os.environ["F3_DISPOSABLE_REPORT_DB"] == "1"
    expected = os.environ["F3_REPORT_DATABASE"]
    assert expected.startswith("f3_report_"), "dedicated F3 report database required"
    sql_target = urlsplit(os.environ["SUPABASE_DB_URL"])
    rest_target = urlsplit(os.environ["LANE_D_POSTGREST_URL"])
    assert sql_target.hostname in ("127.0.0.1", "localhost", "::1")
    assert rest_target.hostname in ("127.0.0.1", "localhost", "::1")
    assert not sql_target.query and not sql_target.fragment
    assert rest_target.scheme == "http" and not rest_target.query and not rest_target.fragment
    assert rest_target.username is None and rest_target.password is None
    assert sql_target.path == f"/{expected}"
    probe = _db().run("select current_database(), current_user")
    assert probe.ok and probe.rows, probe.error
    assert probe.rows[0].split("|")[0] == expected
    schema = _db().run("select to_regclass('public.reconciliation_report_versions')::text")
    assert schema.ok and schema.rows == ["reconciliation_report_versions"], schema.error
    head, tree = _checkout_binding()
    runtime = _db().run(
        "select current_setting('server_version'), "
        "rolname, rolsuper::text, rolbypassrls::text from pg_roles "
        "where rolname in ('authenticator','anon','authenticated','service_role','rls_tester') "
        "order by rolname"
    )
    assert runtime.ok and len(runtime.rows) == 5, runtime.error
    attributes = {row.split("|")[1]: row.split("|")[2:] for row in runtime.rows}
    assert attributes["authenticator"] == ["false", "false"]
    assert attributes["rls_tester"] == ["false", "false"]
    assert attributes["anon"] == ["false", "false"]
    assert attributes["authenticated"] == ["false", "false"]
    print(f"F3_SOURCE head={head} tree={tree}; SQL/REST database={expected}; {runtime.rows!r}")


def _seed() -> dict[str, str]:
    customer_id, checkout_id, payment_id, transaction_id, posting_id = [
        str(uuid4()) for _ in range(5)
    ]
    merchant_reference = f"ord-{payment_id}"
    provider_reference = f"lenco-{payment_id}"
    result = _db().run_script(
        f"""
        BEGIN;
        INSERT INTO auth.users(id,email)
        VALUES ('{customer_id}','f3-{customer_id}@test.invalid');
        INSERT INTO public.checkout_groups(
          id,customer_id,idempotency_key,subtotal_ngwee,delivery_fee_ngwee,
          total_ngwee,status,created_at,updated_at
        ) VALUES (
          '{checkout_id}','{customer_id}','f3-{checkout_id}',30000,0,30000,
          'completed','{REPORT_DATE.isoformat()} 10:00:00+00',
          '{REPORT_DATE.isoformat()} 10:00:00+00'
        );
        INSERT INTO public.payments(
          id,checkout_group_id,provider,rail,lenco_reference,amount_ngwee,status,
          raw,created_at,updated_at
        ) VALUES (
          '{payment_id}','{checkout_id}','lenco','mtn','{merchant_reference}',
          30000,'success','{{"provider_reference":"{provider_reference}"}}',
          '{REPORT_DATE.isoformat()} 12:00:00+00',
          '{REPORT_DATE.isoformat()} 12:00:00+00'
        );
        INSERT INTO public.payment_collection_receipts(
          payment_id,receipt_identity,provider_reference,accepted_at
        ) VALUES (
          '{payment_id}',
          '{{"provider":"lenco","merchant_reference":"{merchant_reference}",
             "provider_reference":"{provider_reference}","currency":"ZMW",
             "amount_ngwee":30000}}',
          '{provider_reference}','{REPORT_DATE.isoformat()} 12:00:00+00'
        );
        INSERT INTO public.ledger_accounts(kind)
        SELECT 'platform_cash'
        WHERE NOT EXISTS (
          SELECT 1 FROM public.ledger_accounts
          WHERE kind='platform_cash' AND vendor_id IS NULL
        );
        INSERT INTO public.ledger_accounts(kind)
        SELECT 'escrow'
        WHERE NOT EXISTS (
          SELECT 1 FROM public.ledger_accounts
          WHERE kind='escrow' AND vendor_id IS NULL
        );
        INSERT INTO public.ledger_transactions(
          id,kind,idempotency_key,checkout_group_id,payment_id,created_at
        ) VALUES (
          '{transaction_id}','charge_received','f3-{transaction_id}',
          '{checkout_id}','{payment_id}','{REPORT_DATE.isoformat()} 12:00:00+00'
        );
        INSERT INTO public.ledger_postings(
          id,transaction_id,account_id,amount_ngwee,created_at
        )
        SELECT '{posting_id}','{transaction_id}',id,30000,
               '{REPORT_DATE.isoformat()} 12:00:00+00'
        FROM public.ledger_accounts
        WHERE kind='platform_cash' AND vendor_id IS NULL;
        INSERT INTO public.ledger_postings(
          transaction_id,account_id,amount_ngwee,created_at
        )
        SELECT '{transaction_id}',id,-30000,
               '{REPORT_DATE.isoformat()} 12:00:00+00'
        FROM public.ledger_accounts
        WHERE kind='escrow' AND vendor_id IS NULL;
        COMMIT;
        """
    )
    assert result.ok, result.error
    return {
        "payment_id": payment_id,
        "transaction_id": transaction_id,
        "merchant_reference": merchant_reference,
        "provider_reference": provider_reference,
    }


class _Provider:
    def __init__(self, evidence: LencoReconciliationEvidence) -> None:
        self._evidence = evidence

    async def collect(self, *, report_date: date) -> LencoReconciliationEvidence:
        assert report_date == REPORT_DATE
        return self._evidence


def _provider(fixture: dict[str, str]) -> LencoReconciliationEvidence:
    observed_at = datetime.fromisoformat(f"{REPORT_DATE.isoformat()}T12:00:00+00:00")
    movement = ProviderMovement(
        movement_id=f"transaction-{fixture['payment_id']}",
        account_id=f"f3-configured-{fixture['payment_id']}",
        currency="ZMW",
        amount_ngwee=30000,
        direction=MovementDirection.CREDIT,
        kind=MovementKind.UNKNOWN,
        observed_at=observed_at,
        provider_reference=fixture["provider_reference"],
        provider_reference_source="transaction.narration",
        evidence_origin=EvidenceOrigin.SYNTHETIC,
    )
    return LencoReconciliationEvidence(
        account=AccountSnapshot(f"f3-configured-{fixture['payment_id']}", "ZMW", 30000, 30000),
        pages=(ProviderPage(1, None, None, 1, 1, (movement,), raw_sha256="a" * 64),),
        account_response_sha256="b" * 64,
        observed_at=observed_at,
        query_from=REPORT_DATE,
        query_to=REPORT_DATE,
    )


@pytest.mark.asyncio
async def test_f3_reader_authorization_linkage_and_immutable_report() -> None:
    _require_stack()
    fixture = _seed()
    service = _service()
    reader = PostgrestReconciliationReader(service, runtime_role="service_role", page_size=1)

    local = reader.collect(report_date=REPORT_DATE)
    assert local.runtime_role == "service_role"
    assert local.unresolved == ()
    assert len(local.movements) == 1
    assert local.movements[0].payment_id == fixture["payment_id"]
    assert local.movements[0].ledger_transaction_id == fixture["transaction_id"]
    assert local.movements[0].ledger_linkage_id == fixture["payment_id"]

    rest_url = os.environ["LANE_D_POSTGREST_URL"]
    for role in ("anon", "authenticated"):
        subject = str(uuid4()) if role == "authenticated" else None
        client = SyncPostgrestClient(
            rest_url,
            headers={"Authorization": f"Bearer {_jwt(role, subject=subject)}"},
        )
        with pytest.raises(APIError):
            client.table("payment_collection_receipts").select("payment_id").execute()

    first = await run_daily_reconciliation_report(
        service,
        report_date=REPORT_DATE,
        provider_adapter=_Provider(_provider(fixture)),  # type: ignore[arg-type]
        local_reader=reader,
        source_version=_checkout_binding()[0],
    )
    replay = await run_daily_reconciliation_report(
        service,
        report_date=REPORT_DATE,
        provider_adapter=_Provider(_provider(fixture)),  # type: ignore[arg-type]
        local_reader=reader,
        source_version=_checkout_binding()[0],
    )
    assert first.created is True
    assert replay.created is False
    assert replay.report_id == first.report_id
    assert first.summary["movement_reconciliation_clean"] is True
    assert first.clean is False and first.certifiable is False

    changed = await run_daily_reconciliation_report(
        service,
        report_date=REPORT_DATE,
        provider_adapter=_Provider(_provider(fixture)),  # type: ignore[arg-type]
        local_reader=reader,
        source_version=_checkout_binding()[0],
        matcher_version="synthetic-reviewed-matcher-v2",
    )
    assert changed.created and changed.report_id != first.report_id
    assert changed.summary["parent_id"] == first.report_id

    persisted = _db().run(
        "select count(*)::text from public.reconciliation_report_versions "
        f"where provider_account_id='f3-configured-{fixture['payment_id']}'"
    )
    assert persisted.ok and persisted.rows == ["2"], persisted.error


def _payload(*, account: str | None = None, day: date = REPORT_DATE) -> dict[str, Any]:
    """Explicit SYNTHETIC_REPORT_INPUT, not a provider-backed receipt/drill."""
    return {
        "provider_account_id": account or f"f3-account-{uuid4()}",
        "currency": "ZMW",
        "report_date": day.isoformat(),
        "cutoff_utc": f"{day.isoformat()}T23:59:59.999999+00:00",
        "source_version": _checkout_binding()[0],
        "schema_version": "20260930170000",
        "matcher_version": "f3-reconciliation-matcher-v1",
        "policy_version": "v0.2-DRAFT-NOT-EFFECTIVE",
        "input_hashes": {
            "account_response_sha256": "a" * 64,
            "transaction_response_sha256s": ["b" * 64],
            "local_source_sha256": "c" * 64,
        },
        "summary": {
            "certifiable": False,
            "clean": False,
            "evidence_origin": "SYNTHETIC_REPORT_INPUT",
        },
        "discrepancies": {"issues": ["fees, opening funds and settlement unresolved"]},
    }


def _append(payload: dict[str, Any], service: SimpleNamespace | None = None) -> dict[str, Any]:
    owned = service is None
    client = (service or _service()).client
    try:
        envelope = _request_report(client, payload)
        row = envelope["report"]
        # Source-bound random identity proves this HTTP service and SQL DB agree.
        found = _db().run(
            "select provider_account_id || '|' || input_fingerprint "
            f"from public.reconciliation_report_versions where id='{row['id']}'::uuid"
        )
        assert found.ok and found.rows == [
            f"{payload['provider_account_id']}|{row['input_fingerprint']}"
        ], found.error
        return envelope
    finally:
        if owned:
            client.session.close()


def _request_report(client: SyncPostgrestClient, payload: dict[str, Any]) -> dict[str, Any]:
    parameters: dict[str, Any] = {"p_report": payload}
    envelope = client.rpc("append_reconciliation_report_version", parameters).execute().data
    assert isinstance(envelope, dict) and isinstance(envelope.get("created"), bool)
    assert isinstance(envelope.get("report"), dict)
    return envelope


def _client(role: str, subject: str | None = None) -> SyncPostgrestClient:
    return SyncPostgrestClient(
        os.environ["LANE_D_POSTGREST_URL"],
        headers={"Authorization": f"Bearer {_jwt(role, subject=subject)}"},
    )


def test_report_versions_role_authority() -> None:
    _require_stack()
    payload = _payload()
    legacy_id = str(uuid4())
    seed_legacy = _db().run(
        "insert into public.reconciliation_reports(id,report_date,summary,discrepancies) "
        f"values ('{legacy_id}','{REPORT_DATE.isoformat()}',"
        '\'{"clean":true,"historical":"unversioned"}\',\'{}\')'
    )
    assert seed_legacy.ok, seed_legacy.error
    legacy_before = _db().run(
        f"select row_to_json(r)::text from public.reconciliation_reports r where id='{legacy_id}'"
    )
    assert legacy_before.ok, legacy_before.error
    envelope = _append(payload)
    assert envelope["report"]["parent_id"] is None
    row_id = envelope["report"]["id"]
    operator = str(uuid4())
    seed = _db().run_script(f"""
        insert into auth.users(id,email) values ('{operator}','f3-{operator}@test.invalid');
        insert into public.user_roles(user_id,role) values ('{operator}','admin');
    """)
    assert seed.ok, seed.error
    for role, subject in (
        ("anon", None),
        ("authenticated", str(uuid4())),
        ("authenticated", operator),
        ("service_role", None),
    ):
        client = _client(role, subject)
        try:
            for mutation in (
                client.table("reconciliation_report_versions").insert(envelope["report"]),
                client.table("reconciliation_report_versions")
                .update({"summary": {}})
                .eq("id", row_id),
                client.table("reconciliation_report_versions").delete().eq("id", row_id),
            ):
                with pytest.raises(APIError) as error:
                    mutation.execute()
                assert error.value.code == "42501"
            if role != "service_role":
                with pytest.raises(APIError) as error:
                    _request_report(client, payload)
                assert error.value.code == "42501"
            if role == "anon":
                with pytest.raises(APIError):
                    client.table("reconciliation_report_versions").select("id").eq(
                        "id", row_id
                    ).execute()
            else:
                rows = (
                    client.table("reconciliation_report_versions")
                    .select("id")
                    .eq("id", row_id)
                    .execute()
                    .data
                )
                assert rows == (
                    [{"id": row_id}] if role == "service_role" or subject == operator else []
                )
        finally:
            client.session.close()
    legacy_after = _db().run(
        f"select row_to_json(r)::text from public.reconciliation_reports r where id='{legacy_id}'"
    )
    assert legacy_after.ok and legacy_after.rows == legacy_before.rows, legacy_after.error


def test_report_versions_concurrent_exact_replay() -> None:
    _require_stack()
    payload = _payload()
    before = _db().run("select count(*)::text from public.ledger_transactions")
    assert before.ok, before.error
    barrier = Barrier(2)

    def worker() -> dict[str, Any]:
        barrier.wait(timeout=10)
        return _append(payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: worker(), range(2)))
    assert sorted(result["created"] for result in results) == [False, True]
    assert results[0]["report"] == results[1]["report"]
    count = _db().run(
        "select count(*)::text from public.reconciliation_report_versions "
        f"where provider_account_id='{payload['provider_account_id']}'"
    )
    assert count.ok and count.rows == ["1"], count.error
    after = _db().run("select count(*)::text from public.ledger_transactions")
    assert after.ok and after.rows == before.rows, after.error


def test_report_versions_changed_inputs_and_historical_replay() -> None:
    _require_stack()
    payload = _payload()
    first = _append(payload)
    second = _append(
        {**payload, "input_hashes": {**payload["input_hashes"], "local_source_sha256": "e" * 64}}
    )
    third = _append({**payload, "matcher_version": "reviewed-matcher-v2"})
    assert first["report"]["version_number"] == 1
    assert second["report"]["version_number"] == 2
    assert third["report"]["version_number"] == 3
    assert second["report"]["parent_id"] == first["report"]["id"]
    assert third["report"]["parent_id"] == second["report"]["id"]
    replay = _append(payload)
    assert replay == {"created": False, "report": first["report"]}
    with pytest.raises(APIError, match="same inputs produced a different report"):
        _append({**payload, "discrepancies": {"issues": ["unexplained new truth"]}})
    service = _service()
    try:
        versions = ReconciliationReportStore(service, runtime_role="service_role").versions(
            account_id=payload["provider_account_id"], currency="ZMW", report_date=REPORT_DATE
        )
        assert [row["id"] for row in versions] == [
            item["report"]["id"] for item in (first, second, third)
        ]
    finally:
        service.client.session.close()


def test_report_versions_partition_links_and_cycle_denial() -> None:
    _require_stack()
    payload = _payload()
    first = _append(payload)["report"]
    other_account = _append({**payload, "provider_account_id": f"f3-other-{uuid4()}"})["report"]
    other_currency = _append({**payload, "currency": "USD"})["report"]
    day = REPORT_DATE + timedelta(days=1)
    other_date = _append(
        {
            **payload,
            "report_date": day.isoformat(),
            "cutoff_utc": f"{day.isoformat()}T23:59:59+00:00",
        }
    )["report"]
    assert len({row["id"] for row in (first, other_account, other_currency, other_date)}) == 4
    assert all(
        row["parent_id"] is None and row["version_number"] == 1
        for row in (first, other_account, other_currency, other_date)
    )
    # Even a privileged SQL fixture cannot create a cross-partition parent or
    # cycle. Exercise constraints using a rollback-only insert of existing shape.
    for parent, parent_number, expected_code in (
        (other_account["id"], 1, "23503"),
        (other_currency["id"], 1, "23503"),
        (other_date["id"], 1, "23503"),
        (first["id"], 2, "23514"),
    ):
        with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
            with pytest.raises(psycopg.Error) as error:
                conn.execute(
                    """
                    insert into public.reconciliation_report_versions
                    select %s::uuid, provider_account_id, currency, report_date, cutoff_utc,
                           2, %s::uuid, %s::bigint, source_version, schema_version, matcher_version,
                           policy_version, input_hashes, %s, summary, discrepancies, created_at
                    from public.reconciliation_report_versions where id=%s
                """,
                    (str(uuid4()), parent, parent_number, "e" * 64, first["id"]),
                )
            assert error.value.sqlstate == expected_code
            conn.rollback()
    immutable = _db().run(
        f"update public.reconciliation_report_versions set summary='{{}}' where id='{first['id']}'"
    )
    assert not immutable.ok and immutable.sqlstate == "55000", immutable.error


def test_report_versions_missing_hashes_and_certification_denied() -> None:
    _require_stack()
    payload = _payload()
    for changed in (
        {**payload, "input_hashes": {}},
        {
            **payload,
            "input_hashes": {**payload["input_hashes"], "transaction_response_sha256s": []},
        },
        {**payload, "source_version": "unbound"},
        {**payload, "summary": {"certifiable": True}},
    ):
        with pytest.raises(APIError) as error:
            _append(changed)
        assert error.value.code == "22023"
    count = _db().run(
        "select count(*)::text from public.reconciliation_report_versions "
        f"where provider_account_id='{payload['provider_account_id']}'"
    )
    assert count.ok and count.rows == ["0"], count.error


def test_report_version_upgrade_preserves_legacy() -> None:
    """Separate pre-tip DB: legacy is inserted BEFORE applying this migration."""
    _require_stack()
    dsn = os.environ.get("F3_REPORT_UPGRADE_DB_URL", "")
    rest_url = os.environ.get("F3_REPORT_UPGRADE_POSTGREST_URL", "")
    expected = os.environ.get("F3_REPORT_UPGRADE_DATABASE", "")
    assert dsn and rest_url and expected, "F3 separate upgrade database/REST binding required"
    assert (
        expected.startswith("f3_report_upgrade_") and expected != os.environ["F3_REPORT_DATABASE"]
    )
    assert urlsplit(dsn).hostname in ("127.0.0.1", "localhost", "::1")
    assert urlsplit(dsn).path == f"/{expected}"
    assert not urlsplit(dsn).query and not urlsplit(dsn).fragment
    assert urlsplit(rest_url).hostname in ("127.0.0.1", "localhost", "::1")
    assert urlsplit(rest_url).scheme == "http" and not urlsplit(rest_url).query
    assert urlsplit(rest_url).username is None and urlsplit(rest_url).password is None
    legacy_id = str(uuid4())
    migration = (
        Path(__file__).resolve().parents[4]
        / "supabase/migrations/20260930170000_reconciliation_report_versions.sql"
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        assert conn.execute("select current_database()").fetchone() == (expected,)
        assert conn.execute(
            "select to_regclass('public.reconciliation_report_versions')"
        ).fetchone() == (None,)
        conn.execute(
            "insert into public.reconciliation_reports(id,report_date,summary,discrepancies) "
            "values (%s,%s,%s::jsonb,%s::jsonb)",
            (legacy_id, REPORT_DATE, '{"clean":true,"historical":"unversioned"}', "{}"),
        )
        old = conn.execute(
            "select row_to_json(r)::text from public.reconciliation_reports r where id=%s",
            (legacy_id,),
        ).fetchone()
        conn.execute(migration.read_text())
        assert (
            conn.execute(
                "select row_to_json(r)::text from public.reconciliation_reports r where id=%s",
                (legacy_id,),
            ).fetchone()
            == old
        )
    client = SyncPostgrestClient(
        rest_url, headers={"Authorization": f"Bearer {_jwt('service_role')}"}
    )
    try:
        # NOTIFY requests a schema-cache reload. Only its bounded PGRST202 race
        # is retried; authorization/SQL failures are never suppressed.
        store = ReconciliationReportStore(
            SimpleNamespace(client=client), runtime_role="service_role"
        )
        legacy = store.legacy(report_date=REPORT_DATE)
        assert len(legacy) == 1 and legacy[0]["report"]["id"] == legacy_id
        assert legacy[0]["provenance"] == "LEGACY_UNVERSIONED_ACCOUNT_UNBOUND"
        payload = _payload()
        for attempt in range(50):
            try:
                envelope = _request_report(client, payload)
                break
            except APIError as error:
                if error.code != "PGRST202" or attempt == 49:
                    raise
                sleep(0.1)
        assert envelope["created"] and envelope["report"]["parent_id"] is None
        with psycopg.connect(dsn) as conn:
            assert (
                conn.execute(
                    "select row_to_json(r)::text from public.reconciliation_reports r where id=%s",
                    (legacy_id,),
                ).fetchone()
                == old
            )
            assert conn.execute(
                "select id::text from public.reconciliation_report_versions"
            ).fetchall() == [(envelope["report"]["id"],)]
    finally:
        client.session.close()
