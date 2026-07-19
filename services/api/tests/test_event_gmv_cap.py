"""VF-P06 / BG-3 — Tier-1 organiser per-event paid GMV fraud cap."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.events.gmv_cap import (
    AUDIT_ACTION,
    CONFIG_KEY,
    DEFAULT_CAP_NGWEE,
    enforce_organiser_t1_gmv_cap,
    event_paid_gmv_ngwee,
    load_organiser_t1_event_gmv_cap_ngwee,
)
from app.services.kyc.eligibility import VendorKycEligibility
from app.services.tickets.purchase import add_ticket_to_checkout, rsvp
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_A = "11111111-1111-1111-1111-111111111111"
CUSTOMER_B = "22222222-2222-2222-2222-222222222222"
SHOP_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _ServiceWrapper:
    def __init__(self) -> None:
        class _Client:
            def table(self, name: str) -> Any:
                raise RuntimeError("use SQL fixtures in this module")

        self.client = _Client()


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    url = resolve_db_url()
    conn = PgConn(url)
    if not conn.run("SELECT 1").ok:
        pytest.skip(f"Postgres not reachable at {url}")
    if not schema_ready(conn):
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
    seed_matrix_fixtures(conn)
    # Ensure the VF-P06 config key exists even when the DB was bootstrapped
    # before migration 0060 (module-scoped schema_ready short-circuits).
    conn.run(
        f"""
        INSERT INTO public.platform_config (key, value, description) VALUES (
          '{CONFIG_KEY}',
          '{DEFAULT_CAP_NGWEE}'::jsonb,
          'Tier-1 organiser per-event paid ticket GMV cap in ngwee'
        )
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """
    )
    yield conn


@pytest.fixture(autouse=True)
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture
def service(db: PgConn) -> _ServiceWrapper:
    del db
    return _ServiceWrapper()


def _service_role_sql(body: str) -> str:
    """Wrap writes so 0058 lifecycle guards allow published event seeds."""
    return f"""
BEGIN;
SET LOCAL role service_role;
SET LOCAL "request.jwt.claims" = '{{"role":"service_role"}}';
{body}
COMMIT;
"""


def _insert_event_with_instance(
    conn: PgConn,
    *,
    event_id: str,
    instance_id: str,
    organiser_vendor_id: str = SHOP_B,
    capacity: int = 100,
) -> None:
    slug = f"gmv-{event_id[:8]}"
    result = conn.run(
        _service_role_sql(
            f"""
INSERT INTO public.events (
  id, organiser_vendor_id, title, slug, venue, lat, lng, status
) VALUES (
  '{event_id}', '{organiser_vendor_id}', 'GMV Cap Event', '{slug}',
  'Lusaka Showgrounds', -15.4167, 28.2833, 'published'
)
ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
VALUES (
  '{instance_id}', '{event_id}', '2026-12-01T18:00:00Z', {capacity}
)
ON CONFLICT (id) DO UPDATE SET capacity = EXCLUDED.capacity;
"""
        )
    )
    assert result.ok, result.error


def _insert_ticket_type(
    conn: PgConn,
    *,
    ticket_type_id: str,
    event_id: str,
    kind: str = "fixed",
    price_ngwee: int = 50_000,
    name: str = "GA",
) -> None:
    result = conn.run(
        _service_role_sql(
            f"""
INSERT INTO public.ticket_types (
  id, event_id, kind, name, price_ngwee, attendee_named
) VALUES (
  '{ticket_type_id}', '{event_id}', '{kind}', '{name}', {price_ngwee}, false
)
ON CONFLICT (id) DO UPDATE
  SET kind = EXCLUDED.kind, price_ngwee = EXCLUDED.price_ngwee;
"""
        )
    )
    assert result.ok, result.error


def _insert_success_payment(conn: PgConn, *, checkout_group_id: str, amount_ngwee: int) -> None:
    payment_id = str(uuid.uuid4())
    result = conn.run(
        _service_role_sql(
            f"""
INSERT INTO public.payments (
  id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
) VALUES (
  '{payment_id}', '{checkout_group_id}', 'lenco', 'mtn',
  'pay-{payment_id[:8]}', {amount_ngwee}, 'success'
);
"""
        )
    )
    assert result.ok, result.error


def _seed_approved_kyc(conn: PgConn, *, vendor_id: str, tier: int) -> None:
    kyc_id = str(uuid.uuid4())
    result = conn.run(
        _service_role_sql(
            f"""
INSERT INTO public.kyc_records (
  id, vendor_id, tier, status, reviewed_at, decision_reason
) VALUES (
  '{kyc_id}', '{vendor_id}', {tier}, 'approved',
  timezone('utc', now()), 'test approval'
)
ON CONFLICT (id) DO NOTHING;
UPDATE public.vendors
SET kyc_tier = {tier}
WHERE id = '{vendor_id}';
"""
        )
    )
    assert result.ok, result.error


def _clear_vendor_kyc(conn: PgConn, *, vendor_id: str) -> None:
    result = conn.run(
        _service_role_sql(
            f"""
DELETE FROM public.kyc_records WHERE vendor_id = '{vendor_id}';
UPDATE public.vendors SET kyc_tier = 1 WHERE id = '{vendor_id}';
"""
        )
    )
    assert result.ok, result.error


def _audit_count(conn: PgConn, *, event_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.audit_log
        WHERE entity_type = 'event'
          AND entity_id = '{event_id}'
          AND action = '{AUDIT_ACTION}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _t1_eligibility(vendor_id: str = SHOP_B) -> VendorKycEligibility:
    return VendorKycEligibility(
        vendor_id=vendor_id,
        vendor_status="active",
        stored_kyc_tier=1,
        effective_tier=1,
        kyc_record_id=str(uuid.uuid4()),
        kyc_record_status="approved",
        is_auditable_approved=True,
        orphaned_tier=False,
        can_wholesale=False,
        can_organise_events=True,
        is_directory_verified=False,
        preferred_badge=False,
    )


def _t2_eligibility(vendor_id: str = SHOP_B) -> VendorKycEligibility:
    return VendorKycEligibility(
        vendor_id=vendor_id,
        vendor_status="active",
        stored_kyc_tier=2,
        effective_tier=2,
        kyc_record_id=str(uuid.uuid4()),
        kyc_record_status="approved",
        is_auditable_approved=True,
        orphaned_tier=False,
        can_wholesale=True,
        can_organise_events=True,
        is_directory_verified=True,
        preferred_badge=False,
    )


def test_load_cap_defaults_to_k20k(db: PgConn) -> None:
    del db
    assert load_organiser_t1_event_gmv_cap_ngwee() == DEFAULT_CAP_NGWEE
    assert DEFAULT_CAP_NGWEE == 2_000_000


def test_t1_under_cap_paid_checkout_ok(
    db: PgConn, service: _ServiceWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.events.gmv_cap.resolve_vendor_eligibility",
        lambda *_a, **_k: _t1_eligibility(),
    )
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    _insert_ticket_type(
        db, ticket_type_id=ticket_type_id, event_id=event_id, price_ngwee=100_000
    )

    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=2,
    )
    assert checkout.subtotal_ngwee == 200_000
    assert len(checkout.claimed_ticket_ids) == 2


def test_t1_over_cap_rejected_and_audited(
    db: PgConn, service: _ServiceWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.events.gmv_cap.resolve_vendor_eligibility",
        lambda *_a, **_k: _t1_eligibility(),
    )
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    # Unit price such that one ticket alone exceeds K20,000.
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        price_ngwee=DEFAULT_CAP_NGWEE + 1,
    )

    with pytest.raises(AppError) as exc_info:
        add_ticket_to_checkout(
            service,
            customer_id=CUSTOMER_A,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            qty=1,
        )
    assert exc_info.value.code == "organiser_gmv_cap_exceeded"
    assert exc_info.value.http_status == 403
    assert _audit_count(db, event_id=event_id) == 1

    # No spine / claim rows created on reject.
    orders = db.run(
        f"""
        SELECT count(*)::text
        FROM public.orders o
        INNER JOIN public.order_items oi ON oi.order_id = o.id
        INNER JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id
        INNER JOIN public.ticket_types tt ON tt.id = oit.ticket_type_id
        WHERE tt.event_id = '{event_id}';
        """
    )
    assert orders.ok and orders.rows and int(orders.rows[0]) == 0


def test_t1_over_cap_with_existing_paid_gmv(
    db: PgConn, service: _ServiceWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.events.gmv_cap.resolve_vendor_eligibility",
        lambda *_a, **_k: _t1_eligibility(),
    )
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    _insert_ticket_type(
        db, ticket_type_id=ticket_type_id, event_id=event_id, price_ngwee=500_000
    )

    first = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=3,  # 1_500_000
    )
    _insert_success_payment(
        db, checkout_group_id=first.checkout_group_id, amount_ngwee=1_500_000
    )
    assert event_paid_gmv_ngwee(event_id) == 1_500_000

    with pytest.raises(AppError) as exc_info:
        add_ticket_to_checkout(
            service,
            customer_id=CUSTOMER_B,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            qty=2,  # would project to 2_500_000
        )
    assert exc_info.value.code == "organiser_gmv_cap_exceeded"
    assert exc_info.value.http_status == 403
    assert exc_info.value.details["current_gmv_ngwee"] == 1_500_000
    assert exc_info.value.details["additional_ngwee"] == 1_000_000
    assert _audit_count(db, event_id=event_id) >= 1


def test_t2_uncapped(
    db: PgConn, service: _ServiceWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.events.gmv_cap.resolve_vendor_eligibility",
        lambda *_a, **_k: _t2_eligibility(),
    )
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        price_ngwee=DEFAULT_CAP_NGWEE + 50_000,
    )

    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=1,
    )
    assert checkout.subtotal_ngwee == DEFAULT_CAP_NGWEE + 50_000
    assert _audit_count(db, event_id=event_id) == 0


def test_free_rsvp_unaffected(
    db: PgConn, service: _ServiceWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Free RSVP must not consult / trip the paid GMV cap."""
    called: list[str] = []

    def _boom(*_a: Any, **_k: Any) -> None:
        called.append("enforce")
        raise AssertionError("GMV cap must not run for free RSVP")

    monkeypatch.setattr(
        "app.services.tickets.purchase.enforce_organiser_t1_gmv_cap",
        _boom,
    )
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=5)
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        kind="free_rsvp",
        price_ngwee=0,
        name="Free RSVP",
    )

    result = rsvp(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=1,
    )
    assert result.order_id
    assert called == []


def test_enforce_uses_auditable_cap_tier_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Orphaned vendors.kyc_tier=2 must still be capped (cap_tier_for_quotas → 1)."""
    orphan = VendorKycEligibility(
        vendor_id=SHOP_B,
        vendor_status="active",
        stored_kyc_tier=2,
        effective_tier=None,
        kyc_record_id=None,
        kyc_record_status=None,
        is_auditable_approved=False,
        orphaned_tier=True,
        can_wholesale=False,
        can_organise_events=False,
        is_directory_verified=False,
        preferred_badge=False,
    )
    monkeypatch.setattr(
        "app.services.events.gmv_cap.resolve_vendor_eligibility",
        lambda *_a, **_k: orphan,
    )
    monkeypatch.setattr(
        "app.services.events.gmv_cap.load_organiser_t1_event_gmv_cap_ngwee",
        lambda: DEFAULT_CAP_NGWEE,
    )
    monkeypatch.setattr(
        "app.services.events.gmv_cap.event_paid_gmv_ngwee",
        lambda _event_id: DEFAULT_CAP_NGWEE,
    )
    audit_calls: list[dict[str, Any]] = []

    def _audit(service: Any, **kwargs: Any) -> None:
        del service
        audit_calls.append(kwargs)

    monkeypatch.setattr("app.services.events.gmv_cap._write_cap_reject_audit", _audit)

    with pytest.raises(AppError) as exc_info:
        enforce_organiser_t1_gmv_cap(
            MagicMock(),
            organiser_vendor_id=SHOP_B,
            event_id=str(uuid.uuid4()),
            additional_ngwee=1,
        )
    assert exc_info.value.code == "organiser_gmv_cap_exceeded"
    assert exc_info.value.details["cap_tier"] == 1
    assert len(audit_calls) == 1


def test_t2_sql_eligibility_path_uncapped(db: PgConn, service: _ServiceWrapper) -> None:
    """End-to-end via SQL eligibility (no monkeypatch) — approved T2 is uncapped."""
    _seed_approved_kyc(db, vendor_id=SHOP_B, tier=2)
    try:
        event_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        ticket_type_id = str(uuid.uuid4())
        _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
        _insert_ticket_type(
            db,
            ticket_type_id=ticket_type_id,
            event_id=event_id,
            price_ngwee=DEFAULT_CAP_NGWEE + 1,
        )
        checkout = add_ticket_to_checkout(
            service,
            customer_id=CUSTOMER_A,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            qty=1,
        )
        assert checkout.subtotal_ngwee == DEFAULT_CAP_NGWEE + 1
    finally:
        _clear_vendor_kyc(db, vendor_id=SHOP_B)


def test_config_key_present_after_migration_seed(db: PgConn) -> None:
    result = db.run(
        f"SELECT value::text FROM public.platform_config WHERE key = '{CONFIG_KEY}';"
    )
    assert result.ok and result.rows
    assert json.loads(result.rows[0]) == DEFAULT_CAP_NGWEE
