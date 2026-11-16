"""Free events (RSVP) + free services (request/accept) — money, abuse, authz paths."""

# Imported pytest fixtures (db, service) are re-bound as test parameters.
# ruff: noqa: F811
from __future__ import annotations

import uuid

import pytest
from app.errors import AppError
from app.services.commissions.engine import (
    FREE_EVENTS_CATEGORY,
    FreeOrderCommissionError,
    capture_order_commission,
    compute_order_commission,
)
from app.services.rfq.free_booking import request_free_booking, transition_free_booking
from app.services.tickets.purchase import MAX_RSVP_TICKETS_PER_USER, rsvp
from tests.rls.conftest import PgConn
from tests.test_ticket_purchase import (  # noqa: F401  (fixtures)
    CUSTOMER_A,
    CUSTOMER_B,
    SHOP_B,
    _insert_event_with_instance,
    _insert_ticket_type,
    _load_order_snapshot,
    _ServiceWrapper,
    _ticket_count,
    db,
    db_url_env,
    service,
)


def _free_event(db: PgConn, *, capacity: int = 10) -> tuple[str, str]:
    event_id, instance_id, tt = (str(uuid.uuid4()) for _ in range(3))
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id, capacity=capacity)
    _insert_ticket_type(
        db, ticket_type_id=tt, event_id=event_id, kind="free_rsvp", name="Free", price_ngwee=0
    )
    return instance_id, tt


def test_rsvp_issues_qr_ticket_and_marks_order_free(db: PgConn, service: _ServiceWrapper) -> None:
    instance_id, tt = _free_event(db)
    result = rsvp(service, customer_id=CUSTOMER_A, instance_id=instance_id, ticket_type_id=tt)
    assert not result.replayed
    assert _ticket_count(db, instance_id=instance_id, order_item_id=result.order_item_id) == 1
    snap = _load_order_snapshot(db, result.order_id)
    assert snap["is_free"] is True and snap["rate_bps"] == 0
    assert compute_order_commission(snap).commission_ngwee == 0
    # No payment intent and no ledger rows for the free order.
    pays = db.run(
        "SELECT count(*) FROM public.payments p JOIN public.orders o "
        f"ON o.checkout_group_id = p.checkout_group_id WHERE o.id = '{result.order_id}'"
    )
    ledger = db.run(
        f"SELECT count(*) FROM public.ledger_transactions WHERE order_id = '{result.order_id}'"
    )
    assert pays.rows == ["0"] and ledger.rows == ["0"]


def test_duplicate_rsvp_is_idempotent(db: PgConn, service: _ServiceWrapper) -> None:
    instance_id, tt = _free_event(db)
    first = rsvp(service, customer_id=CUSTOMER_A, instance_id=instance_id, ticket_type_id=tt)
    again = rsvp(service, customer_id=CUSTOMER_A, instance_id=instance_id, ticket_type_id=tt, qty=2)
    assert again.replayed
    assert again.order_id == first.order_id
    assert again.ticket_ids == first.ticket_ids
    assert _ticket_count(db, instance_id=instance_id) == 1
    rows = db.run(
        f"SELECT count(*) FROM public.event_rsvps WHERE user_id = '{CUSTOMER_A}' "
        f"AND instance_id = '{instance_id}'"
    )
    assert rows.rows == ["1"]


def test_rsvp_over_capacity_rejected_and_anchor_released(
    db: PgConn, service: _ServiceWrapper
) -> None:
    instance_id, tt = _free_event(db, capacity=1)
    rsvp(service, customer_id=CUSTOMER_A, instance_id=instance_id, ticket_type_id=tt)
    with pytest.raises(AppError) as exc:
        rsvp(service, customer_id=CUSTOMER_B, instance_id=instance_id, ticket_type_id=tt)
    assert exc.value.code == "tickets.oversell"
    left = db.run(
        f"SELECT count(*) FROM public.event_rsvps WHERE user_id = '{CUSTOMER_B}' "
        f"AND instance_id = '{instance_id}'"
    )
    assert left.rows == ["0"]  # a failed RSVP does not block a later retry


def test_rsvp_per_user_cap(db: PgConn, service: _ServiceWrapper) -> None:
    instance_id, tt = _free_event(db)
    with pytest.raises(AppError) as exc:
        rsvp(
            service,
            customer_id=CUSTOMER_A,
            instance_id=instance_id,
            ticket_type_id=tt,
            qty=MAX_RSVP_TICKETS_PER_USER + 1,
        )
    assert exc.value.code == "tickets.rsvp_cap"


def test_free_tier_with_price_rejected_by_db(db: PgConn) -> None:
    event_id, instance_id = str(uuid.uuid4()), str(uuid.uuid4())
    _insert_event_with_instance(db, event_id=event_id, instance_id=instance_id)
    res = db.run(
        "INSERT INTO public.ticket_types (event_id, kind, name, price_ngwee) "
        f"VALUES ('{event_id}', 'free_rsvp', 'Bad', 5000)"
    )
    assert not res.ok and "ticket_types_free_rsvp_price_chk" in (res.error or "")


def test_commission_on_free_order_refused(db: PgConn, service: _ServiceWrapper) -> None:
    instance_id, tt = _free_event(db)
    result = rsvp(service, customer_id=CUSTOMER_B, instance_id=instance_id, ticket_type_id=tt)
    snap = _load_order_snapshot(db, result.order_id)
    with pytest.raises(FreeOrderCommissionError):
        capture_order_commission(
            order_id=result.order_id, commission_snapshot=snap, idempotency_key_prefix="t"
        )
    # DB backstop: no ledger transaction and no payment intent for a free order.
    led = db.run(
        "INSERT INTO public.ledger_transactions (kind, order_id) "
        f"VALUES ('commission_capture', '{result.order_id}')"
    )
    assert not led.ok and "cannot carry ledger" in (led.error or "")
    pay = db.run(
        "INSERT INTO public.payments (checkout_group_id, provider, rail, lenco_reference, "
        f"amount_ngwee) VALUES ('{result.checkout_group_id}', 'lenco', 'mtn', "
        f"'pay-free-{result.order_id[:8]}', 100)"
    )
    assert not pay.ok and "no payment intent" in (pay.error or "")


def test_mixed_free_and_paid_lines_price_correctly() -> None:
    snap = {
        "lines": [
            {"category_key": FREE_EVENTS_CATEGORY, "rate_bps": 0, "line_total_ngwee": 0},
            {"category_key": "event_tickets", "rate_bps": 500, "line_total_ngwee": 10_001},
        ]
    }
    result = compute_order_commission(snap)
    assert result.gross_ngwee == 10_001
    assert result.commission_ngwee == 500  # floor(10_001 * 500 / 10_000)
    assert isinstance(result.commission_ngwee, int)


# --------------------------------------------------------------------------- #
# Free services
# --------------------------------------------------------------------------- #


def _vendor_owner(db: PgConn) -> str:
    return db.run(f"SELECT owner_user_id FROM public.vendors WHERE id = '{SHOP_B}'").rows[0]


def _free_service(db: PgConn) -> str:
    sid = str(uuid.uuid4())
    res = db.run(
        "INSERT INTO public.services (id, vendor_id, category, title, status, is_free) "
        f"VALUES ('{sid}', '{SHOP_B}', 'events', 'Free clinic', 'active', true)"
    )
    assert res.ok, res.error
    return sid


def test_free_service_with_price_rejected_by_db(db: PgConn) -> None:
    res = db.run(
        "INSERT INTO public.services (vendor_id, category, title, is_free, from_price_ngwee) "
        f"VALUES ('{SHOP_B}', 'events', 'Bad', true, 1000)"
    )
    assert not res.ok and "services_free_price_check" in (res.error or "")


def test_free_service_request_accept_flow_and_authz(db: PgConn) -> None:
    sid = _free_service(db)
    key = uuid.uuid4().hex
    first = request_free_booking(service_id=sid, customer_id=CUSTOMER_A, idempotency_key=key)
    assert first.status == "requested" and not first.replayed
    replay = request_free_booking(service_id=sid, customer_id=CUSTOMER_A, idempotency_key=key)
    assert replay.replayed and replay.id == first.id
    with pytest.raises(AppError) as dup:
        request_free_booking(service_id=sid, customer_id=CUSTOMER_A, idempotency_key=key + "x")
    assert dup.value.http_status == 409

    # Customer cannot accept their own request; another user cannot either.
    for actor in (CUSTOMER_A, CUSTOMER_B):
        with pytest.raises(AppError) as forbidden:
            transition_free_booking(booking_id=first.id, to="accepted", actor_id=actor)
        assert forbidden.value.http_status == 403

    accepted = transition_free_booking(
        booking_id=first.id, to="accepted", actor_id=_vendor_owner(db)
    )
    assert accepted.status == "accepted"
    with pytest.raises(AppError) as again:
        transition_free_booking(booking_id=first.id, to="declined", actor_id=_vendor_owner(db))
    assert again.value.http_status == 409
    audit = db.run(
        f"SELECT count(*) FROM public.audit_log WHERE entity_id = '{first.id}'"
    )
    assert audit.rows == ["1"]
    # No order / quote / payment is ever created for a free service.
    jobs = db.run(f"SELECT count(*) FROM public.jobs WHERE customer_id = '{CUSTOMER_A}' "
                  "AND description LIKE '%Free clinic%'")
    assert jobs.rows == ["0"]


def test_raw_status_update_blocked(db: PgConn) -> None:
    sid = _free_service(db)
    b = request_free_booking(
        service_id=sid, customer_id=CUSTOMER_B, idempotency_key=uuid.uuid4().hex
    )
    res = db.run(
        f"UPDATE public.service_free_bookings SET status = 'accepted' WHERE id = '{b.id}'"
    )
    assert not res.ok


def test_paid_service_cannot_use_free_request(db: PgConn) -> None:
    sid = str(uuid.uuid4())
    db.run(
        "INSERT INTO public.services (id, vendor_id, category, title, status) "
        f"VALUES ('{sid}', '{SHOP_B}', 'events', 'Paid', 'active')"
    )
    with pytest.raises(AppError) as exc:
        request_free_booking(
            service_id=sid, customer_id=CUSTOMER_A, idempotency_key=uuid.uuid4().hex
        )
    assert exc.value.http_status == 409


def test_rls_isolation_free_bookings_and_rsvps(db: PgConn, service: _ServiceWrapper) -> None:
    sid = _free_service(db)
    b = request_free_booking(
        service_id=sid, customer_id=CUSTOMER_A, idempotency_key=uuid.uuid4().hex
    )
    mine = db.run_as(
        "authenticated",
        f"SELECT count(*) FROM public.service_free_bookings WHERE id = '{b.id}';",
        user_id=CUSTOMER_A,
    )
    other = db.run_as(
        "authenticated",
        f"SELECT count(*) FROM public.service_free_bookings WHERE id = '{b.id}';",
        user_id=CUSTOMER_B,
    )
    vendor = db.run_as(
        "authenticated",
        f"SELECT count(*) FROM public.service_free_bookings WHERE id = '{b.id}';",
        user_id=_vendor_owner(db),
    )
    assert mine.rows[-1:] == ["1"] and other.rows[-1:] == ["0"] and vendor.rows[-1:] == ["1"]
    write = db.run_as(
        "authenticated",
        f"UPDATE public.service_free_bookings SET note = 'x' WHERE id = '{b.id}' RETURNING id;",
        user_id=CUSTOMER_A,
    )
    assert not write.ok or write.rows[-1:] != [b.id]
    anon = db.run_as("anon", "SELECT count(*) FROM public.event_rsvps;")
    assert not anon.ok
