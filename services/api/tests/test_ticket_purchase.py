from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any, cast

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.services.commissions.engine import FREE_EVENTS_CATEGORY, compute_order_commission
from app.services.tickets.purchase import (
    EVENT_TICKETS_CATEGORY,
    EVENT_TICKETS_RATE_BPS,
    _link_claimed_tickets,
    add_ticket_to_checkout,
    issue_tickets_for_paid_order,
    release_stale_ticket_claims,
    release_ticket_claim,
    rsvp,
)
from app.services.tickets.qr import extract_pin_for_holder
from fastapi.testclient import TestClient
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
    def __init__(self, client: Any) -> None:
        self.client = client


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

    class _Client:
        def table(self, name: str) -> Any:
            raise RuntimeError("use SQL fixtures in this module")

    return _ServiceWrapper(_Client())


def _insert_event_with_instance(
    conn: PgConn,
    *,
    event_id: str,
    instance_id: str,
    organiser_vendor_id: str = SHOP_B,
    capacity: int = 10,
    status: str = "published",
) -> str:
    slug = f"evt-{event_id[:8]}"
    conn.run(
        f"""
        INSERT INTO public.events (
          id, organiser_vendor_id, title, slug, venue, lat, lng, status
        ) VALUES (
          '{event_id}', '{organiser_vendor_id}', 'Purchase Event', '{slug}',
          'Lusaka Showgrounds', -15.4167, 28.2833, '{status}'
        )
        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;
        """
    )
    conn.run(
        f"""
        INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
        VALUES (
          '{instance_id}', '{event_id}', '2026-12-01T18:00:00Z', {capacity}
        )
        ON CONFLICT (id) DO UPDATE SET capacity = EXCLUDED.capacity;
        """
    )
    return event_id


def _insert_ticket_type(
    conn: PgConn,
    *,
    ticket_type_id: str,
    event_id: str,
    kind: str = "fixed",
    name: str = "GA",
    price_ngwee: int = 50_000,
    qty_cap: int | None = None,
    attendee_named: bool = False,
) -> str:
    qty_sql = "NULL" if qty_cap is None else str(qty_cap)
    named_sql = "true" if attendee_named else "false"
    conn.run(
        f"""
        INSERT INTO public.ticket_types (
          id, event_id, kind, name, price_ngwee, qty_cap, attendee_named
        ) VALUES (
          '{ticket_type_id}', '{event_id}', '{kind}', '{name}', {price_ngwee}, {qty_sql},
          {named_sql}
        )
        ON CONFLICT (id) DO UPDATE
          SET kind = EXCLUDED.kind,
              price_ngwee = EXCLUDED.price_ngwee,
              qty_cap = EXCLUDED.qty_cap,
              attendee_named = EXCLUDED.attendee_named;
        """
    )
    return ticket_type_id


def _holder_names(conn: PgConn, *, order_item_id: str) -> list[str]:
    result = conn.run(
        f"""
        SELECT coalesce(holder_name, '') FROM public.tickets
        WHERE order_item_id = '{order_item_id}' AND status <> 'void'
        ORDER BY created_at, id;
        """
    )
    assert result.ok
    return [row for row in result.rows]


def _ticket_count(conn: PgConn, *, instance_id: str, order_item_id: str | None = None) -> int:
    extra = ""
    if order_item_id is not None:
        extra = f" AND order_item_id = '{order_item_id}'"
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.tickets
        WHERE instance_id = '{instance_id}' AND status <> 'void'{extra};
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _void_ticket_count(conn: PgConn, instance_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.tickets
        WHERE instance_id = '{instance_id}' AND status = 'void';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


def _insert_success_payment(conn: PgConn, *, checkout_group_id: str, amount_ngwee: int) -> None:
    payment_id = str(uuid.uuid4())
    conn.run(
        f"""
        INSERT INTO public.payments (
          id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
        ) VALUES (
          '{payment_id}', '{checkout_group_id}', 'lenco', 'mtn',
          'pay-{payment_id[:8]}', {amount_ngwee}, 'success'
        );
        """
    )


def _load_order_snapshot(conn: PgConn, order_id: str) -> dict[str, Any]:
    result = conn.run(
        f"SELECT commission_snapshot::text FROM public.orders WHERE id = '{order_id}';"
    )
    assert result.ok and result.rows
    return cast(dict[str, Any], json.loads(result.rows[0]))


def _paid_checkout_fixture(conn: PgConn) -> dict[str, str]:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(conn, event_id=event_id, instance_id=instance_id, capacity=5)
    _insert_ticket_type(
        conn,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        kind="fixed",
        price_ngwee=20_000,
    )
    return {
        "event_id": event_id,
        "instance_id": instance_id,
        "ticket_type_id": ticket_type_id,
    }


def test_failure_release_frees_claimed_capacity(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=2,
    )
    assert len(checkout.claimed_ticket_ids) == 2
    assert _ticket_count(db, instance_id=fixture["instance_id"]) == 2

    released = release_ticket_claim(service, checkout_group_id=checkout.checkout_group_id)
    assert released.voided_count == 2
    assert _ticket_count(db, instance_id=fixture["instance_id"]) == 0
    assert _void_ticket_count(db, fixture["instance_id"]) == 2

    # Capacity is available again after release.
    second = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_B,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=2,
    )
    assert len(second.claimed_ticket_ids) == 2


def test_rsvp_issues_immediately_capped_zero_commission(
    db: PgConn, service: _ServiceWrapper
) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=1)
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        kind="free_rsvp",
        name="Free RSVP",
        price_ngwee=0,
    )

    result = rsvp(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=1,
    )
    assert _ticket_count(db, instance_id=instance_id, order_item_id=result.order_item_id) == 1

    snapshot = _load_order_snapshot(db, result.order_id)
    assert snapshot["category_key"] == FREE_EVENTS_CATEGORY
    assert snapshot["rate_bps"] == 0
    commission = compute_order_commission(snapshot)
    assert commission.commission_ngwee == 0

    with pytest.raises(AppError) as exc_info:
        rsvp(
            service,
            customer_id=CUSTOMER_B,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            qty=1,
        )
    assert exc_info.value.code == "tickets.oversell"


def test_idempotent_issuance_on_webhook_replay(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=3,
    )
    _insert_success_payment(db, checkout_group_id=checkout.checkout_group_id, amount_ngwee=60_000)

    first = issue_tickets_for_paid_order(service, checkout.order_id)
    assert first.issued_count == 3
    assert (
        _ticket_count(db, instance_id=fixture["instance_id"], order_item_id=checkout.order_item_id)
        == 3
    )

    second = issue_tickets_for_paid_order(service, checkout.order_id)
    assert second.skipped is True
    assert second.issued_count == 0
    assert (
        _ticket_count(db, instance_id=fixture["instance_id"], order_item_id=checkout.order_item_id)
        == 3
    )


def test_commission_snapshot_paid_five_percent(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=2,
    )
    snapshot = checkout.commission_snapshot
    assert snapshot["category_key"] == EVENT_TICKETS_CATEGORY
    assert snapshot["rate_bps"] == EVENT_TICKETS_RATE_BPS
    commission = compute_order_commission(snapshot)
    assert commission.commission_ngwee == 2_000  # 5% of 40_000


def test_commission_snapshot_free_zero_percent(db: PgConn, service: _ServiceWrapper) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        kind="free_rsvp",
        price_ngwee=0,
    )
    result = rsvp(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=2,
    )
    snapshot = result.commission_snapshot
    assert snapshot["rate_bps"] == 0
    assert compute_order_commission(snapshot).commission_ngwee == 0


def _ticket_secrets_for_item(
    conn: PgConn, order_item_id: str
) -> list[tuple[str | None, str | None]]:
    result = conn.run(
        f"""
        SELECT qr_secret, pin_hash FROM public.tickets
        WHERE order_item_id = '{order_item_id}' AND status <> 'void'
        ORDER BY created_at;
        """
    )
    assert result.ok
    return [(row.split("|")[0] or None, row.split("|")[1] or None) for row in result.rows]


def test_issued_paid_tickets_have_secrets(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=2,
    )
    _insert_success_payment(db, checkout_group_id=checkout.checkout_group_id, amount_ngwee=40_000)
    issue_tickets_for_paid_order(service, checkout.order_id)

    secrets = _ticket_secrets_for_item(db, checkout.order_item_id)
    assert len(secrets) == 2
    for qr_secret, pin_hash in secrets:
        assert qr_secret
        assert pin_hash
        assert "$" in pin_hash


def test_rsvp_tickets_have_secrets(db: PgConn, service: _ServiceWrapper) -> None:
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
    )
    result = rsvp(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=1,
    )
    secrets = _ticket_secrets_for_item(db, result.order_item_id)
    assert len(secrets) == 1
    qr_secret, pin_hash = secrets[0]
    assert qr_secret
    assert pin_hash
    assert extract_pin_for_holder(pin_hash, ticket_id=result.ticket_ids[0]) is not None


def test_link_claimed_tickets_rowcount_skips_void_claim(db: PgConn) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    order_item_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    _insert_ticket_type(db, ticket_type_id=ticket_type_id, event_id=event_id)

    valid_id = str(uuid.uuid4())
    void_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    db.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee,
          total_ngwee, status
        ) VALUES (
          '{group_id}', '{CUSTOMER_A}', 'link-{order_item_id[:8]}', 0, 0, 0, 'pending'
        );
        INSERT INTO public.orders (
          id, checkout_group_id, vendor_id, customer_id, status, fulfilment,
          delivery_fee_ngwee, cod, commission_snapshot
        ) VALUES (
          '{order_id}', '{group_id}', '{SHOP_B}', '{CUSTOMER_A}', 'placed', 'pickup',
          0, false, '{{}}'::jsonb
        );
        INSERT INTO public.order_items (
          id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot
        ) VALUES (
          '{order_item_id}', '{order_id}', 'ticket', 1, 1000, 'GA'
        );
        INSERT INTO public.order_item_tickets (order_item_id, ticket_type_id, instance_id)
        VALUES ('{order_item_id}', '{ticket_type_id}', '{instance_id}');
        """
    )
    for ticket_id, status in ((valid_id, "issued"), (void_id, "void")):
        db.run(
            f"""
            INSERT INTO public.tickets (
              id, instance_id, ticket_type_id, holder_user_id, status
            ) VALUES (
              '{ticket_id}', '{instance_id}', '{ticket_type_id}', '{CUSTOMER_A}', '{status}'
            );
            """
        )

    linked = _link_claimed_tickets(order_item_id, (valid_id, void_id))
    assert linked == 1

    row = db.run(
        f"""
        SELECT qr_secret, pin_hash, order_item_id::text
        FROM public.tickets WHERE id = '{valid_id}';
        """
    )
    assert row.ok and row.rows
    parts = row.rows[0].split("|")
    assert parts[0]
    assert parts[1]
    assert parts[2] == order_item_id


def test_under_issue_guard_inserts_shortfall(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=2,
    )
    void_id = checkout.claimed_ticket_ids[0]
    db.run(f"UPDATE public.tickets SET status = 'void' WHERE id = '{void_id}';")
    _insert_success_payment(db, checkout_group_id=checkout.checkout_group_id, amount_ngwee=40_000)

    issued = issue_tickets_for_paid_order(service, checkout.order_id)
    assert issued.issued_count == 1
    assert (
        _ticket_count(db, instance_id=fixture["instance_id"], order_item_id=checkout.order_item_id)
        == 2
    )
    secrets = _ticket_secrets_for_item(db, checkout.order_item_id)
    assert len(secrets) == 2
    assert all(qr and pin for qr, pin in secrets)


def test_release_stale_claims_frees_capacity(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=1,
    )
    claim_id = checkout.claimed_ticket_ids[0]
    db.run(
        f"""
        UPDATE public.tickets
        SET created_at = timezone('utc', now()) - interval '20 minutes'
        WHERE id = '{claim_id}';
        """
    )
    assert _ticket_count(db, instance_id=fixture["instance_id"]) == 1

    first = release_stale_ticket_claims(service, ttl_minutes=15)
    assert first.voided_count == 1
    assert _ticket_count(db, instance_id=fixture["instance_id"]) == 0

    second = release_stale_ticket_claims(service, ttl_minutes=15)
    assert second.voided_count == 0

    revived = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_B,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=1,
    )
    assert len(revived.claimed_ticket_ids) == 1


def test_release_stale_claims_skips_paid_ticket(db: PgConn, service: _ServiceWrapper) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=1,
    )
    _insert_success_payment(db, checkout_group_id=checkout.checkout_group_id, amount_ngwee=20_000)
    issue_tickets_for_paid_order(service, checkout.order_id)
    db.run(
        f"""
        UPDATE public.tickets
        SET created_at = timezone('utc', now()) - interval '20 minutes'
        WHERE order_item_id = '{checkout.order_item_id}';
        """
    )
    released = release_stale_ticket_claims(service, ttl_minutes=15)
    assert released.voided_count == 0
    assert (
        _ticket_count(db, instance_id=fixture["instance_id"], order_item_id=checkout.order_item_id)
        == 1
    )


def test_issue_tick_http_issues_paid_order(
    db: PgConn, service: _ServiceWrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _paid_checkout_fixture(db)
    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=fixture["instance_id"],
        ticket_type_id=fixture["ticket_type_id"],
        qty=2,
    )
    _insert_success_payment(db, checkout_group_id=checkout.checkout_group_id, amount_ngwee=40_000)
    monkeypatch.setenv("INTERNAL_TICKETS_ISSUE_TOKEN", "test-issue-token")

    app = create_app()

    class _Client:
        def table(self, name: str) -> Any:
            raise RuntimeError("unexpected supabase table access")

    app.dependency_overrides[get_supabase_client] = lambda: _ServiceWrapper(_Client())

    with TestClient(app) as client:
        unauthorized = client.post("/internal/tickets/issue-tick")
        assert unauthorized.status_code == 401

        first = client.post(
            "/internal/tickets/issue-tick",
            headers={"X-Internal-Token": "test-issue-token"},
        )
        assert first.status_code == 200
        assert (
            _ticket_count(
                db,
                instance_id=fixture["instance_id"],
                order_item_id=checkout.order_item_id,
            )
            == 2
        )

        second = client.post(
            "/internal/tickets/issue-tick",
            headers={"X-Internal-Token": "test-issue-token"},
        )
        assert second.status_code == 200
        assert (
            _ticket_count(
                db,
                instance_id=fixture["instance_id"],
                order_item_id=checkout.order_item_id,
            )
            == 2
        )

    secrets = _ticket_secrets_for_item(db, checkout.order_item_id)
    assert len(secrets) == 2
    assert all(qr and pin for qr, pin in secrets)


# --- M10-P11: per-attendee names ------------------------------------------


def test_paid_checkout_captures_and_assigns_attendee_names(
    db: PgConn, service: _ServiceWrapper
) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=5)
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        kind="fixed",
        price_ngwee=20_000,
        attendee_named=True,
    )

    checkout = add_ticket_to_checkout(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=2,
        attendee_names=["Alice Banda", "Bob Phiri"],
    )
    _insert_success_payment(
        db, checkout_group_id=checkout.checkout_group_id, amount_ngwee=checkout.subtotal_ngwee
    )
    issue_tickets_for_paid_order(service, checkout.order_id)

    assert sorted(_holder_names(db, order_item_id=checkout.order_item_id)) == [
        "Alice Banda",
        "Bob Phiri",
    ]


def test_named_ticket_requires_attendee_names(db: PgConn, service: _ServiceWrapper) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=5)
    _insert_ticket_type(
        db, ticket_type_id=ticket_type_id, event_id=event_id, attendee_named=True
    )

    with pytest.raises(AppError) as exc:
        add_ticket_to_checkout(
            service,
            customer_id=CUSTOMER_A,
            instance_id=instance_id,
            ticket_type_id=ticket_type_id,
            qty=1,
        )
    assert exc.value.http_status == 422
    assert exc.value.code == "tickets.attendee_names_required"


def test_rsvp_captures_attendee_names(db: PgConn, service: _ServiceWrapper) -> None:
    event_id = str(uuid.uuid4())
    instance_id = str(uuid.uuid4())
    ticket_type_id = str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=3)
    _insert_ticket_type(
        db,
        ticket_type_id=ticket_type_id,
        event_id=event_id,
        kind="free_rsvp",
        name="Free RSVP",
        price_ngwee=0,
        attendee_named=True,
    )

    result = rsvp(
        service,
        customer_id=CUSTOMER_A,
        instance_id=instance_id,
        ticket_type_id=ticket_type_id,
        qty=2,
        attendee_names=["Chanda Mumba", "Dalitso Zulu"],
    )
    assert sorted(_holder_names(db, order_item_id=result.order_item_id)) == [
        "Chanda Mumba",
        "Dalitso Zulu",
    ]
