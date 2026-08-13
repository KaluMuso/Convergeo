"""Postgres-backed atomic KYC approval RPC tests (failure injection + concurrency)."""

from __future__ import annotations

import concurrent.futures
import json
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from app.errors import AppError
from app.services.kyc.approve_atomic import approve_kyc_vendor_atomic
from app.services.kyc.state_machine import transition_approve
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)
from tests.test_kyc_state import (
    ADMIN_ID,
    VENDOR_OWNER_ID,
    _ensure_matrix_seed,
    _ServiceWrapper,
)


def _approval_invariant_broken(db: PgConn, *, vendor_id: str, owner_id: str) -> bool:
    """True when active+approved without a legitimate vendor role for the owner."""
    vendor = db.run(
        f"SELECT status FROM public.vendors WHERE id = '{vendor_id}';"
    )
    kyc = db.run(
        f"""
        SELECT status FROM public.kyc_records
        WHERE vendor_id = '{vendor_id}'
        ORDER BY created_at DESC
        LIMIT 1;
        """
    )
    role = db.run(
        f"""
        SELECT 1 FROM public.user_roles
        WHERE user_id = '{owner_id}' AND role = 'vendor';
        """
    )
    if not vendor.ok or not kyc.ok:
        return False
    if not vendor.rows or not kyc.rows:
        return False
    active_approved = vendor.rows[0] == "active" and kyc.rows[0] == "approved"
    has_role = bool(role.ok and role.rows)
    return active_approved and not has_role


def _seed_pending(
    db: PgConn,
    *,
    vendor_id: str,
    kyc_id: str,
    owner_id: str = VENDOR_OWNER_ID,
    momo_matched: bool = True,
    tier: int = 2,
    kyc_status: str = "submitted",
    vendor_status: str = "pending_kyc",
) -> None:
    _ensure_matrix_seed(db)
    slug = f"atomic-{vendor_id[:8]}"
    momo = json.dumps({"matched": momo_matched})
    vendor_result = db.run(
        f"""
        INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status)
        VALUES ('{vendor_id}', '{owner_id}', '{slug}', 'Atomic Vendor', '{vendor_status}');
        """
    )
    assert vendor_result.ok, vendor_result.error
    kyc_result = db.run(
        f"""
        INSERT INTO public.kyc_records (
          id, vendor_id, tier, doc_storage_paths, momo_name_match, status
        ) VALUES (
          '{kyc_id}', '{vendor_id}', {tier}, '{{}}', '{momo}'::jsonb, '{kyc_status}'
        );
        """
    )
    assert kyc_result.ok, kyc_result.error


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    try:
        url = resolve_db_url()
    except FileNotFoundError:
        pytest.skip("psql not available for atomic KYC approval tests")
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    yield conn


def _call_rpc(
    db: PgConn,
    *,
    kyc_id: str,
    tier: int = 2,
    actor_id: str = ADMIN_ID,
    notes: str | None = None,
) -> dict[str, Any]:
    wrapper = _ServiceWrapper(db)
    return approve_kyc_vendor_atomic(
        wrapper,
        actor_id=actor_id,
        kyc_record_id=kyc_id,
        tier=tier,
        reviewer_notes=notes,
    )


@pytest.mark.usefixtures("db")
class TestApproveKycVendorAtomic:
    def test_happy_path_writes_role_and_audit(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id)

        result = _call_rpc(db, kyc_id=kyc_id)
        assert result["vendor"]["status"] == "active"
        assert result["kyc_record"]["status"] == "approved"
        assert result["vendor_role"]["outcome"] == "granted"

        audit = db.run(
            f"""
            SELECT count(*)::text FROM public.audit_log
            WHERE entity_id = '{kyc_id}' AND action = 'kyc.approve';
            """
        )
        assert audit.ok and audit.rows == ["1"]
        assert not _approval_invariant_broken(
            db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
        )

    def test_momo_mismatch_rejects_without_partial_state(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id, momo_matched=False)

        with pytest.raises(AppError) as exc:
            _call_rpc(db, kyc_id=kyc_id)
        assert exc.value.code == "kyc_name_match_required"
        assert not _approval_invariant_broken(
            db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
        )

    def test_invalid_tier_rejects_without_partial_state(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id, tier=2)

        with pytest.raises(AppError) as exc:
            _call_rpc(db, kyc_id=kyc_id, tier=3)
        assert exc.value.code == "validation_error"
        assert not _approval_invariant_broken(
            db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
        )

    def test_rejected_kyc_cannot_approve(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id, kyc_status="rejected")

        with pytest.raises(AppError) as exc:
            _call_rpc(db, kyc_id=kyc_id)
        assert exc.value.code == "kyc_invalid_transition"
        assert not _approval_invariant_broken(
            db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
        )

    def test_duplicate_approval_is_idempotent(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id)
        first = _call_rpc(db, kyc_id=kyc_id)
        second = _call_rpc(db, kyc_id=kyc_id)
        assert first["vendor_role"]["outcome"] == "granted"
        assert second["vendor_role"]["outcome"] == "already_present"
        counted = db.run(
            f"""
            SELECT count(*)::text FROM public.user_roles
            WHERE user_id = '{VENDOR_OWNER_ID}' AND role = 'vendor';
            """
        )
        assert counted.ok and counted.rows == ["1"]

    def test_role_grant_failure_rolls_back_all_mutations(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id)
        trigger = db.run(
            """
            CREATE OR REPLACE FUNCTION public.test_block_vendor_role_insert()
            RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.role = 'vendor' THEN
                RAISE EXCEPTION 'forced role insert failure'
                  USING ERRCODE = '22023', MESSAGE = 'vendor_role_grant_failed';
              END IF;
              RETURN NEW;
            END;
            $$;
            CREATE TRIGGER test_block_vendor_role_trg
              BEFORE INSERT ON public.user_roles
              FOR EACH ROW
              EXECUTE FUNCTION public.test_block_vendor_role_insert();
            """
        )
        assert trigger.ok, trigger.error
        try:
            with pytest.raises(AppError):
                _call_rpc(db, kyc_id=kyc_id)
            assert not _approval_invariant_broken(
                db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
            )
            vendor = db.run(f"SELECT status FROM public.vendors WHERE id = '{vendor_id}';")
            kyc = db.run(f"SELECT status FROM public.kyc_records WHERE id = '{kyc_id}';")
            assert vendor.ok and vendor.rows == ["pending_kyc"]
            assert kyc.ok and kyc.rows == ["submitted"]
            audit = db.run(
                f"SELECT count(*)::text FROM public.audit_log WHERE entity_id = '{kyc_id}';"
            )
            assert audit.ok and audit.rows == ["0"]
        finally:
            db.run(
                "DROP TRIGGER IF EXISTS test_block_vendor_role_trg ON public.user_roles;"
            )
            db.run("DROP FUNCTION IF EXISTS public.test_block_vendor_role_insert();")

    def test_audit_failure_rolls_back_all_mutations(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id)
        trigger = db.run(
            """
            CREATE OR REPLACE FUNCTION public.test_block_kyc_audit_insert()
            RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.action = 'kyc.approve' THEN
                RAISE EXCEPTION 'forced audit insert failure'
                  USING ERRCODE = '22023', MESSAGE = 'audit_write_failed';
              END IF;
              RETURN NEW;
            END;
            $$;
            CREATE TRIGGER test_block_kyc_audit_trg
              BEFORE INSERT ON public.audit_log
              FOR EACH ROW
              EXECUTE FUNCTION public.test_block_kyc_audit_insert();
            """
        )
        assert trigger.ok, trigger.error
        try:
            with pytest.raises(AppError):
                _call_rpc(db, kyc_id=kyc_id)
            assert not _approval_invariant_broken(
                db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
            )
            vendor = db.run(f"SELECT status FROM public.vendors WHERE id = '{vendor_id}';")
            kyc = db.run(f"SELECT status FROM public.kyc_records WHERE id = '{kyc_id}';")
            assert vendor.ok and vendor.rows == ["pending_kyc"]
            assert kyc.ok and kyc.rows == ["submitted"]
        finally:
            db.run(
                "DROP TRIGGER IF EXISTS test_block_kyc_audit_trg ON public.audit_log;"
            )
            db.run("DROP FUNCTION IF EXISTS public.test_block_kyc_audit_insert();")

    def test_concurrent_rpc_exactly_one_commit(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id)
        wrapper = _ServiceWrapper(db)
        LOSER_CODES = frozenset({"kyc_transition_conflict", "kyc_invalid_transition"})

        def approve() -> object:
            try:
                return approve_kyc_vendor_atomic(
                    wrapper,
                    actor_id=ADMIN_ID,
                    kyc_record_id=kyc_id,
                    tier=2,
                )
            except AppError as exc:
                if exc.code in LOSER_CODES:
                    return None
                raise

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: approve(), range(2)))

        outcomes = [
            str(result["vendor_role"]["outcome"])
            for result in results
            if result is not None
        ]
        assert outcomes.count("granted") == 1
        assert all(outcome in ("granted", "already_present") for outcome in outcomes)
        assert not _approval_invariant_broken(
            db, vendor_id=vendor_id, owner_id=VENDOR_OWNER_ID
        )

    def test_transition_approve_uses_rpc_path(self, db: PgConn) -> None:
        vendor_id = str(uuid.uuid4())
        kyc_id = str(uuid.uuid4())
        _seed_pending(db, vendor_id=vendor_id, kyc_id=kyc_id)
        wrapper = _ServiceWrapper(db)
        result = transition_approve(
            actor_id=ADMIN_ID,
            vendor_id=vendor_id,
            kyc_record_id=kyc_id,
            tier=2,
            service_client=wrapper,
        )
        assert result["vendor_role"]["outcome"] == "granted"
        audit = db.run(
            f"""
            SELECT count(*)::text FROM public.audit_log
            WHERE entity_id = '{kyc_id}' AND action = 'kyc.approve';
            """
        )
        assert audit.ok and audit.rows == ["1"]
