"""Service packages — RLS and database invariants (20261113045000).

Live Postgres (``supabase db reset`` first), same harness as the other RLS suites.
"""

from __future__ import annotations

import uuid

from tests.rls.conftest import PgConn, RoleSession

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # ids.json vendors.shop_a
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"  # ids.json vendors.shop_b


def _seed_service(db: PgConn, *, vendor_id: str, status: str = "active") -> str:
    service_id = str(uuid.uuid4())
    result = db.run(
        f"""
        BEGIN;
        INSERT INTO public.services (id, vendor_id, category, title, status)
        VALUES ('{service_id}', '{vendor_id}', 'printing-creative', 'Logo design', '{status}');
        COMMIT;
        """
    )
    assert result.ok, result.error
    return service_id


def _seed_package(
    db: PgConn, *, service_id: str, vendor_id: str, tier: str = "basic", status: str = "active"
) -> str:
    package_id = str(uuid.uuid4())
    result = db.run(
        f"""
        BEGIN;
        INSERT INTO public.service_packages
          (id, service_id, vendor_id, tier, name, price_ngwee, delivery_days, status)
        VALUES ('{package_id}', '{service_id}', '{vendor_id}', '{tier}', 'Starter', 75000, 3,
                '{status}');
        COMMIT;
        """
    )
    assert result.ok, result.error
    return package_id


def _cleanup(db: PgConn, service_id: str) -> None:
    db.run(f"BEGIN; DELETE FROM public.services WHERE id = '{service_id}'; COMMIT;")


def test_service_packages_forces_rls(db: PgConn) -> None:
    result = db.run(
        "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'public.service_packages'::regclass"
    )
    assert result.ok and result.rows == ["t"]


def test_anon_sees_active_packages_of_active_services_only(
    db: PgConn, as_anon: RoleSession
) -> None:
    live = _seed_service(db, vendor_id=VENDOR_A)
    draft = _seed_service(db, vendor_id=VENDOR_A, status="draft")
    try:
        visible = _seed_package(db, service_id=live, vendor_id=VENDOR_A)
        archived = _seed_package(
            db, service_id=live, vendor_id=VENDOR_A, tier="premium", status="archived"
        )
        hidden = _seed_package(db, service_id=draft, vendor_id=VENDOR_A)
        result = as_anon.execute(
            "SELECT id FROM public.service_packages "
            f"WHERE id IN ('{visible}', '{archived}', '{hidden}')"
        )
        assert result.ok, result.error
        assert result.rows == [visible]
    finally:
        _cleanup(db, live)
        _cleanup(db, draft)


def test_a_fourth_package_is_impossible(db: PgConn) -> None:
    service_id = _seed_service(db, vendor_id=VENDOR_A)
    try:
        _seed_package(db, service_id=service_id, vendor_id=VENDOR_A, tier="basic")
        dup = db.run(
            f"""
            BEGIN;
            INSERT INTO public.service_packages
              (service_id, vendor_id, tier, name, delivery_days)
            VALUES ('{service_id}', '{VENDOR_A}', 'basic', 'Again', 2);
            COMMIT;
            """
        )
        bad_tier = db.run(
            f"""
            BEGIN;
            INSERT INTO public.service_packages
              (service_id, vendor_id, tier, name, delivery_days)
            VALUES ('{service_id}', '{VENDOR_A}', 'deluxe', 'Deluxe', 2);
            COMMIT;
            """
        )
        assert not dup.ok and not bad_tier.ok
    finally:
        _cleanup(db, service_id)


def test_a_package_cannot_claim_another_vendors_service(db: PgConn) -> None:
    service_id = _seed_service(db, vendor_id=VENDOR_A)
    try:
        result = db.run(
            f"""
            BEGIN;
            INSERT INTO public.service_packages
              (service_id, vendor_id, tier, name, delivery_days)
            VALUES ('{service_id}', '{VENDOR_B}', 'basic', 'Hijack', 2);
            COMMIT;
            """
        )
        assert not result.ok
    finally:
        _cleanup(db, service_id)


def test_clients_have_no_write_grant(db: PgConn) -> None:
    result = db.run(
        """
        SELECT count(*)::int FROM information_schema.role_table_grants
         WHERE table_schema = 'public' AND table_name = 'service_packages'
           AND grantee IN ('anon', 'authenticated')
           AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE');
        """
    )
    assert result.ok and result.rows == ["0"]


def test_money_is_a_bigint_and_must_be_positive(db: PgConn) -> None:
    result = db.run(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'service_packages' AND column_name = 'price_ngwee'"
    )
    assert result.ok and result.rows == ["bigint"]
    service_id = _seed_service(db, vendor_id=VENDOR_A)
    try:
        zero = db.run(
            f"""
            BEGIN;
            INSERT INTO public.service_packages
              (service_id, vendor_id, tier, name, price_ngwee, delivery_days)
            VALUES ('{service_id}', '{VENDOR_A}', 'basic', 'Free', 0, 2);
            COMMIT;
            """
        )
        assert not zero.ok
    finally:
        _cleanup(db, service_id)
