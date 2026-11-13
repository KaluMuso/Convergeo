"""Founder analytics dashboards on a live (disposable) Postgres: exact aggregates.

Seeds a fixed past window (Lusaka days DAY and DAY+1) with accounts, vendors, KYC,
checkouts, orders, payments, ledger postings, refunds, reviews, RFQs, events and tickets
whose counts and ngwee totals are known, then asserts every dashboard figure. Rows are
also placed on both sides of the Lusaka midnight boundary (22:00 UTC) to prove the
reporting day is Africa/Lusaka, not UTC. Totals that span all time are asserted as deltas
so rows from other suites do not matter.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from app.services.analytics import dashboards
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

DAY = date(2025, 3, 10)
NEXT = DAY + timedelta(days=1)
AFTER = DAY + timedelta(days=2)
BEFORE = DAY - timedelta(days=1)
WINDOW = dashboards.Window("custom", DAY, NEXT)

P = "ad5a0000-0000-4000-8000-0000000000"  # + two hex digits
SERVICE = 'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'


def u(n: int) -> str:
    return f"{P}{n:02x}"


def ts(day: date, clock: str) -> str:
    return f"'{day.isoformat()} {clock}+00'"


# accounts 0x01..0x06, vendors 0x11..0x13, groups 0x21.., orders 0x31.., items 0x41..
CUSTOMERS = {
    1: ts(DAY, "12:00:00"),
    2: ts(DAY, "13:00:00"),
    3: ts(DAY, "14:00:00"),  # profile deleted -> not a registered customer
    4: ts(BEFORE, "23:30:00"),  # 01:30 CAT on DAY -> counts on DAY
    5: ts(NEXT, "22:30:00"),  # 00:30 CAT on AFTER -> outside the window
}
OWNER = 6
VENDORS = {
    0x11: ("active", ts(DAY, "10:00:00")),
    0x12: ("pending_kyc", ts(NEXT, "21:59:59")),  # 23:59:59 CAT on NEXT -> inside
    0x13: ("draft", ts(NEXT, "22:00:00")),  # 00:00 CAT on AFTER -> outside
}


def _cleanup(db: PgConn) -> None:
    like = f"'{P}%'"
    statements = [
        f"DELETE FROM public.tickets WHERE id::text LIKE {like}",
        f"DELETE FROM public.ticket_types WHERE id::text LIKE {like}",
        f"DELETE FROM public.event_instances WHERE id::text LIKE {like}",
        f"DELETE FROM public.events WHERE id::text LIKE {like}",
        f"DELETE FROM public.rfq_threads WHERE id::text LIKE {like}",
        f"DELETE FROM public.job_quotes WHERE id::text LIKE {like}",
        f"DELETE FROM public.jobs WHERE id::text LIKE {like}",
        f"DELETE FROM public.services WHERE id::text LIKE {like}",
        f"DELETE FROM public.reviews WHERE id::text LIKE {like}",
        f"DELETE FROM public.review_aggregates WHERE entity_id::text LIKE {like}",
        f"DELETE FROM public.refunds WHERE id::text LIKE {like}",
        f"DELETE FROM public.ledger_postings WHERE transaction_id::text LIKE {like}",
        f"DELETE FROM public.ledger_transactions WHERE id::text LIKE {like}",
        f"DELETE FROM public.payments WHERE checkout_group_id::text LIKE {like}",
        f"DELETE FROM public.order_items WHERE order_id::text LIKE {like}",
        f"DELETE FROM public.order_events WHERE order_id::text LIKE {like}",
        f"DELETE FROM public.orders WHERE id::text LIKE {like}",
        f"DELETE FROM public.checkout_groups WHERE id::text LIKE {like}",
        f"DELETE FROM public.kyc_records WHERE id::text LIKE {like}",
        f"DELETE FROM public.search_documents WHERE entity_id::text LIKE {like}",
        f"DELETE FROM public.vendors WHERE id::text LIKE {like}",
        f"DELETE FROM public.user_roles WHERE user_id::text LIKE {like}",
        f"DELETE FROM public.profiles WHERE id::text LIKE {like}",
        f"DELETE FROM auth.users WHERE id::text LIKE {like}",
    ]
    result = db.run_script("BEGIN;\n" + SERVICE + ";\n".join(statements) + ";\nCOMMIT;\n")
    assert result.ok, result.error


def _accounts() -> list[str]:
    sql = []
    for n in [*CUSTOMERS, OWNER]:
        sql.append(f"INSERT INTO auth.users (id, email) VALUES ('{u(n)}', 'zz-dash-{n}@x.test')")
        deleted = "now()" if n == 3 else "NULL"
        sql.append(
            "INSERT INTO public.profiles (id, display_name, deleted_at) VALUES "
            f"('{u(n)}', 'zz dash {n}', {deleted}) ON CONFLICT (id) DO UPDATE SET "
            "deleted_at = EXCLUDED.deleted_at"
        )
    for n, at in CUSTOMERS.items():
        sql.append(
            "INSERT INTO public.user_roles (user_id, role, created_at) VALUES "
            f"('{u(n)}', 'customer', {at}) ON CONFLICT (user_id, role) "
            "DO UPDATE SET created_at = EXCLUDED.created_at"
        )
    return sql


def _vendors() -> list[str]:
    sql = []
    for n, (status, at) in VENDORS.items():
        sql.append(
            "INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, "
            f"kyc_tier, created_at) VALUES ('{u(n)}', '{u(OWNER)}', 'zz-dash-{n}', "
            f"'=Zz Dash {n}', '{status}', 1, {at})"
        )
    # V11: approved after 2 h on DAY. V12: submitted on NEXT, still pending.
    # V13: rejected decision at 22:30 UTC on NEXT = AFTER in Lusaka -> outside.
    sql += [
        "INSERT INTO public.kyc_records (id, vendor_id, tier, status, created_at, reviewed_at) "
        f"VALUES ('{u(0x14)}', '{u(0x11)}', 1, 'approved', {ts(DAY, '08:00:00')}, "
        f"{ts(DAY, '10:00:00')})",
        "INSERT INTO public.kyc_records (id, vendor_id, tier, status, created_at) "
        f"VALUES ('{u(0x15)}', '{u(0x12)}', 1, 'submitted', {ts(NEXT, '09:00:00')})",
        "INSERT INTO public.kyc_records (id, vendor_id, tier, status, created_at, reviewed_at) "
        f"VALUES ('{u(0x16)}', '{u(0x13)}', 1, 'rejected', {ts(BEFORE, '09:00:00')}, "
        f"{ts(NEXT, '22:30:00')})",
    ]
    return sql


def _group(n: int, customer: int, total: int, at: str) -> str:
    return (
        "INSERT INTO public.checkout_groups (id, customer_id, idempotency_key, subtotal_ngwee, "
        f"delivery_fee_ngwee, total_ngwee, status, created_at) VALUES ('{u(n)}', '{u(customer)}', "
        f"'zz-dash-{n}', {total}, 0, {total}, 'completed', {at})"
    )


def _order(n: int, group: int, customer: int, status: str, fee: int, at: str) -> str:
    return (
        "INSERT INTO public.orders (id, checkout_group_id, vendor_id, customer_id, status, "
        f"fulfilment, delivery_fee_ngwee, created_at) VALUES ('{u(n)}', '{u(group)}', "
        f"'{u(0x11)}', '{u(customer)}', '{status}', 'delivery', {fee}, {at})"
    )


def _item(n: int, order: int, kind: str, qty: int, price: int) -> str:
    return (
        "INSERT INTO public.order_items (id, order_id, item_kind, qty, unit_price_ngwee) "
        f"VALUES ('{u(n)}', '{u(order)}', '{kind}', {qty}, {price})"
    )


def _payment(group: int, ref: str, amount: int, status: str, at: str) -> str:
    return (
        "INSERT INTO public.payments (checkout_group_id, provider, rail, lenco_reference, "
        f"amount_ngwee, status, created_at) VALUES ('{u(group)}', 'lenco', 'mtn', "
        f"'pay-zzdash-{ref}', {amount}, '{status}', {at})"
    )


def _commerce() -> list[str]:
    noon, next_noon = ts(DAY, "12:00:00"), ts(NEXT, "12:00:00")
    return [
        # G21 / O31: 2 x 10,000 + 1,500 delivery, paid (customer 1, DAY).
        _group(0x21, 1, 21_500, noon),
        _order(0x31, 0x21, 1, "delivered", 1_500, noon),
        _item(0x41, 0x31, "product", 2, 10_000),
        _payment(0x21, "21-fail", 21_500, "failed", noon),
        _payment(0x21, "21-ok", 21_500, "success", noon),
        # G22 / O32: paid then cancelled (customer 2, DAY).
        _group(0x22, 2, 5_000, noon),
        _order(0x32, 0x22, 2, "cancelled", 0, noon),
        _item(0x42, 0x32, "product", 1, 5_000),
        _payment(0x22, "22-ok", 5_000, "success", noon),
        # G23 / O33: payment failed (customer 2, NEXT).
        _group(0x23, 2, 999, next_noon),
        _order(0x33, 0x23, 2, "placed", 0, next_noon),
        _item(0x43, 0x33, "product", 1, 999),
        _payment(0x23, "23-fail", 999, "failed", next_noon),
        # G24 / O34: service deposit 3,000, paid (customer 1, NEXT).
        _group(0x24, 1, 3_000, next_noon),
        _order(0x34, 0x24, 1, "confirmed", 0, next_noon),
        _item(0x44, 0x34, "service_deposit", 1, 3_000),
        _payment(0x24, "24-ok", 3_000, "success", next_noon),
        # G25 / O35: paid at 22:30 UTC on NEXT = AFTER in Lusaka -> outside the window.
        _group(0x25, 4, 7_000, ts(NEXT, "22:30:00")),
        _order(0x35, 0x25, 4, "delivered", 0, ts(NEXT, "22:30:00")),
        _item(0x45, 0x35, "product", 1, 7_000),
        _payment(0x25, "25-ok", 7_000, "success", ts(NEXT, "22:30:00")),
    ]


def _account_id(kind: str) -> str:
    return f"(SELECT id FROM public.ledger_accounts WHERE kind = '{kind}' AND vendor_id IS NULL)"


def _txn(n: int, at: str, legs: list[tuple[str, int]]) -> list[str]:
    sql = [
        "INSERT INTO public.ledger_transactions (id, kind, idempotency_key, created_at) "
        f"VALUES ('{u(n)}', 'zz_dash', 'zz-dash-{n}', {at})"
    ]
    for kind, amount in legs:
        sql.append(
            "INSERT INTO public.ledger_postings (transaction_id, account_id, amount_ngwee, "
            f"created_at) VALUES ('{u(n)}', {_account_id(kind)}, {amount}, {at})"
        )
    return sql


def _ledger() -> list[str]:
    return [
        # DAY: commission 2,000 and delivery 1,500 captured from escrow; Lenco fee 300.
        *_txn(0x51, ts(DAY, "15:00:00"), [("escrow", 2_000), ("commission_revenue", -2_000)]),
        *_txn(0x52, ts(DAY, "15:00:00"), [("escrow", 1_500), ("delivery_revenue", -1_500)]),
        *_txn(0x53, ts(DAY, "15:00:00"), [("fees", 300), ("platform_cash", -300)]),
        # NEXT 21:00 UTC (23:00 CAT): 500 commission reversed by a refund.
        *_txn(0x54, ts(NEXT, "21:00:00"), [("commission_revenue", 500), ("escrow", -500)]),
        # NEXT 22:00 UTC = AFTER 00:00 CAT -> outside.
        *_txn(0x55, ts(NEXT, "22:00:00"), [("escrow", 9_999), ("commission_revenue", -9_999)]),
        # Refunds: one completed (4,000), one pending, one failed; one outside.
        "INSERT INTO public.refunds (id, order_id, lane, amount_ngwee, status, source_key, "
        f"created_at) VALUES ('{u(0x61)}', '{u(0x32)}', 1, 4_000, 'completed', 'zz-dash-61', "
        f"{ts(DAY, '16:00:00')})".replace("4_000", "4000"),
        "INSERT INTO public.refunds (id, order_id, lane, amount_ngwee, status, source_key, "
        f"created_at) VALUES ('{u(0x62)}', '{u(0x31)}', 1, 1000, 'pending', 'zz-dash-62', "
        f"{ts(NEXT, '16:00:00')})",
        "INSERT INTO public.refunds (id, order_id, lane, amount_ngwee, status, source_key, "
        f"created_at) VALUES ('{u(0x63)}', '{u(0x31)}', 1, 1000, 'failed', 'zz-dash-63', "
        f"{ts(NEXT, '17:00:00')})",
        "INSERT INTO public.refunds (id, order_id, lane, amount_ngwee, status, source_key, "
        f"created_at) VALUES ('{u(0x64)}', '{u(0x31)}', 1, 777, 'completed', 'zz-dash-64', "
        f"{ts(NEXT, '23:00:00')})",
    ]


def _reviews() -> list[str]:
    return [
        "ALTER TABLE public.reviews DISABLE TRIGGER reviews_validate_verified_purchase",
        "INSERT INTO public.reviews (id, order_item_id, rating, status, created_at) VALUES "
        f"('{u(0x71)}', '{u(0x41)}', 4, 'published', {ts(DAY, '18:00:00')})",
        "INSERT INTO public.reviews (id, order_item_id, rating, status, created_at) VALUES "
        f"('{u(0x72)}', '{u(0x44)}', 5, 'published', {ts(NEXT, '18:00:00')})",
        "INSERT INTO public.reviews (id, order_item_id, rating, status, created_at) VALUES "
        f"('{u(0x73)}', '{u(0x42)}', 1, 'removed', {ts(NEXT, '18:00:00')})",
        "ALTER TABLE public.reviews ENABLE TRIGGER reviews_validate_verified_purchase",
    ]


def _services_events() -> list[str]:
    day, nxt = ts(DAY, "09:00:00"), ts(NEXT, "09:00:00")
    return [
        "INSERT INTO public.services (id, vendor_id, category, title, status) VALUES "
        f"('{u(0x81)}', '{u(0x11)}', 'plumbing', 'zz dash service', 'active')",
        "INSERT INTO public.jobs (id, customer_id, category, description, created_at) VALUES "
        f"('{u(0x82)}', '{u(1)}', 'plumbing', 'zz job one', {day})",
        "INSERT INTO public.jobs (id, customer_id, category, description, created_at) VALUES "
        f"('{u(0x83)}', '{u(2)}', 'plumbing', 'zz job two', {nxt})",
        "INSERT INTO public.job_quotes (id, job_id, provider_vendor_id, amount_ngwee, status, "
        f"created_at) VALUES ('{u(0x84)}', '{u(0x82)}', '{u(0x11)}', 5000, 'accepted', {day})",
        "INSERT INTO public.job_quotes (id, job_id, provider_vendor_id, amount_ngwee, status, "
        f"created_at) VALUES ('{u(0x85)}', '{u(0x83)}', '{u(0x11)}', 6000, 'submitted', {nxt})",
        "INSERT INTO public.rfq_threads (id, customer_id, vendor_id, service_id, "
        "requested_details, status, quote_price_ngwee, quote_valid_until, quoted_at, created_at) "
        f"VALUES ('{u(0x86)}', '{u(1)}', '{u(0x11)}', '{u(0x81)}', 'zz details', 'quoted', 4000, "
        f"{ts(AFTER, '09:00:00')}, {nxt}, {day})",
        "INSERT INTO public.events (id, organiser_vendor_id, title, slug, status) VALUES "
        f"('{u(0x91)}', '{u(0x11)}', 'zz dash event', 'zz-dash-event', 'published')",
        "INSERT INTO public.event_instances (id, event_id, starts_at, ends_at, capacity) VALUES "
        f"('{u(0x92)}', '{u(0x91)}', {ts(DAY, '16:00:00')}, {ts(DAY, '20:00:00')}, 100)",
        "INSERT INTO public.ticket_types (id, event_id, kind, name, price_ngwee) VALUES "
        f"('{u(0x93)}', '{u(0x91)}', 'fixed', 'zz GA', 10000)",
        *[
            "INSERT INTO public.tickets (id, instance_id, ticket_type_id, holder_user_id, status, "
            f"checked_in_at, created_at) VALUES ('{u(n)}', '{u(0x92)}', '{u(0x93)}', '{u(1)}', "
            f"'{status}', {checked}, {ts(DAY, '11:00:00')})"
            for n, status, checked in (
                (0x94, "checked_in", ts(DAY, "17:00:00")),
                (0x95, "checked_in", ts(DAY, "17:05:00")),
                (0x96, "issued", "NULL"),
                (0x97, "void", "NULL"),
            )
        ],
    ]


def _seed(db: PgConn) -> None:
    statements = _accounts() + _vendors() + _commerce() + _ledger() + _reviews()
    statements += _services_events()
    result = db.run_script("BEGIN;\n" + SERVICE + ";\n".join(statements) + ";\nCOMMIT;\n")
    assert result.ok, result.error


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    yield db
    _cleanup(db)
    reset_pools()


def test_registrations_by_lusaka_day_and_totals_as_deltas(live: PgConn) -> None:
    before = dashboards.registration_totals()
    _seed(live)
    after = dashboards.registration_totals()
    # Customers 1, 2, 4, 5 and the vendor owner 6 (sign-up grants every account the
    # customer role); 3 is deleted. Vendors 11, 12, 13; one active.
    assert after["customers"] - before["customers"] == 5
    assert after["vendors"] - before["vendors"] == 3
    assert after["active_vendors"] - before["active_vendors"] == 1

    users = dashboards.build_users(WINDOW, activity_enabled=False)
    assert users["daily"] == [
        {"day": DAY.isoformat(), "customers": 3, "vendors": 1},  # 1, 2 and 4 (23:30 UTC)
        {"day": NEXT.isoformat(), "customers": 0, "vendors": 1},  # 12 at 21:59:59 UTC
    ]
    assert users["new"] == {"customers": 3, "vendors": 2}
    assert users["previous_new"] == {"customers": 0, "vendors": 0}
    assert users["activity"] == {"enabled": False}


def test_retention_cohorts_count_paid_not_cancelled_orders(live: PgConn) -> None:
    _seed(live)
    cohorts = dashboards.retention_cohorts(date(2025, 4, 30), months=2)
    march, april = cohorts
    # Paid, not cancelled, through 30 Apr: customer 1 (O31, O34) and customer 4 (O35).
    assert march["cohort"] == "2025-03" and march["size"] == 2
    assert march["retained"] == [2, 0]
    assert march["retained_bps"] == [10_000, 0]
    assert march["small_sample"] is True
    assert april["retained"] == [0, None]


def test_growth_counts(live: PgConn) -> None:
    _seed(live)
    growth = dashboards.build_growth(WINDOW)
    assert growth["totals"] == {
        "customers": 3,
        "vendors": 2,
        "listings": 0,
        "checkouts_started": 4,
        "orders_placed": 4,
        "orders_paid": 3,  # O31, O32 (later cancelled), O34
    }
    assert growth["checkout_to_paid_bps"] == 7_500


def test_revenue_from_ledger_not_order_value(live: PgConn) -> None:
    _seed(live)
    revenue = dashboards.build_revenue(WINDOW)
    assert revenue["platform_revenue"] == {
        "commission_ngwee": 1_500,  # 2,000 captured - 500 reversed; 9,999 is outside
        "delivery_ngwee": 1_500,
        "total_ngwee": 3_000,
        "processing_fees_ngwee": 300,
    }
    orders = revenue["orders"]
    assert orders["placed"] == 4
    assert orders["paid"] == 3
    assert orders["cancelled"] == 1
    assert orders["paid_then_cancelled"] == 1
    assert orders["paid_order_value_ngwee"] == 21_500 + 3_000  # cancelled O32 excluded
    assert revenue["take_rate_bps"] == 1_224  # 3,000 / 24,500
    assert revenue["refunds"] == {
        "requested": 3,
        "completed": 1,
        "completed_ngwee": 4_000,
        "open": 1,
        "failed": 1,
    }
    by_day = {d["day"]: d for d in revenue["daily"]}
    assert by_day[DAY.isoformat()]["commission_ngwee"] == 2_000
    assert by_day[NEXT.isoformat()]["commission_ngwee"] == -500


def test_vendor_metrics_and_money_gate(live: PgConn) -> None:
    _seed(live)
    out = dashboards.build_vendors(WINDOW, include_money=True)
    assert out["kyc"]["submitted"] == 2  # 14 (DAY) and 15 (NEXT); 16 was BEFORE
    assert out["kyc"]["approved"] == 1 and out["kyc"]["rejected"] == 0
    assert out["kyc"]["avg_decision_hours"] == 2
    assert out["vendors"]["new"] == 2
    assert out["vendors"]["selling"] == 1
    assert out["ratings"] == {"reviews": 2, "avg_x100": 450}
    top = [row for row in out["top"] if row["vendor_id"] == u(0x11)]
    assert top == [
        {
            "vendor_id": u(0x11),
            "name": "=Zz Dash 17",
            "paid_orders": 2,
            "item_sales_ngwee": 23_000,
            "rating_count": 2,
            "rating_avg_x100": 450,
        }
    ]
    hidden = dashboards.build_vendors(WINDOW, include_money=False)
    assert all(row["item_sales_ngwee"] is None for row in hidden["top"])
    assert hidden["finance_visible"] is False


def test_services_and_events(live: PgConn) -> None:
    _seed(live)
    out = dashboards.build_services_events(WINDOW)
    services = out["services"]
    assert services["jobs_posted"] == 2
    assert services["quotes_submitted"] == 2
    assert services["quotes_accepted"] == 1
    assert services["rfq_opened"] == 1
    assert services["rfq_quoted"] == 1
    assert services["bookings"] == 1 and services["bookings_paid"] == 1
    events = out["events"]
    assert events["instances"] == 1
    assert events["tickets_sold"] == 3  # the void ticket is not sold
    assert events["check_ins"] == 2
    assert events["check_in_rate_bps"] == 6_667
    by_day = {d["day"]: d for d in out["daily"]}
    assert by_day[DAY.isoformat()] == {
        "day": DAY.isoformat(),
        "jobs_posted": 1,
        "rfq_opened": 1,
        "tickets_sold": 3,
        "check_ins": 2,
    }


def test_single_lusaka_day_window_excludes_the_previous_utc_evening(live: PgConn) -> None:
    _seed(live)
    after_only = dashboards.build_growth(dashboards.Window("custom", AFTER, AFTER))
    # Customer 5 (22:30 UTC on NEXT) and vendor 13 (22:00 UTC on NEXT) land on AFTER.
    assert after_only["totals"]["customers"] == 1
    assert after_only["totals"]["vendors"] == 1
    assert after_only["totals"]["orders_paid"] == 1  # O35
