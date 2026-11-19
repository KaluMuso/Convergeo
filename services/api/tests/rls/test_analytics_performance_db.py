"""Performance dashboard on a live (disposable) Postgres: exact funnels and contribution.

Seeds two categories, three products, two vendors and three listings, with product-page
views, add-to-cart lines (some attributed to a clip), clip views, paid / unpaid /
cancelled orders with commission snapshots, a booked Lenco fee, a courier dispatch and a
completed refund, then asserts every scorecard, ranking and contribution figure.
One add-to-cart sits at 22:30 UTC the day before the window (00:30 CAT inside it) to
prove the Lusaka reporting day.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from app.services.analytics import performance
from app.services.analytics.dashboards import Window, rate_bps
from app.services.db import reset_pools
from tests.rls.conftest import PgConn

DAY = date(2024, 2, 20)
NEXT = DAY + timedelta(days=1)
AFTER = DAY + timedelta(days=2)
BEFORE = DAY - timedelta(days=1)
LONG_AGO = DAY - timedelta(days=30)
WINDOW = Window("custom", DAY, NEXT)

P = "ad5b0000-0000-4000-8000-0000000000"  # + two hex digits
SERVICE = 'SET LOCAL "request.jwt.claims" = \'{"role":"service_role"}\';\n'


def u(n: int) -> str:
    return f"{P}{n:02x}"


def ts(day: date, clock: str) -> str:
    return f"'{day.isoformat()} {clock}+00'"


A, B, OWNER = 1, 2, 3
V1, V2 = 0x11, 0x12
C1, C2 = 0x21, 0x22
P1, P2, P3 = 0x31, 0x32, 0x33
L1, L2, L3 = 0x41, 0x42, 0x43
K1, K2 = 0x51, 0x52
COURIER = 0x53


def _cleanup(db: PgConn) -> None:
    like = f"'{P}%'"
    # Dispatch events are append-only by trigger; test rows go with replication triggers off.
    dispatch = db.run_script(
        "BEGIN;\nSET LOCAL session_replication_role = replica;\n"
        "DELETE FROM public.dispatch_request_events WHERE dispatch_request_id IN (SELECT id "
        f"FROM public.dispatch_requests WHERE order_id::text LIKE {like});\n"
        f"DELETE FROM public.dispatch_requests WHERE order_id::text LIKE {like};\nCOMMIT;\n"
    )
    assert dispatch.ok, dispatch.error
    statements = [
        f"DELETE FROM public.courier_partners WHERE id::text LIKE {like}",
        f"DELETE FROM public.refunds WHERE id::text LIKE {like}",
        f"DELETE FROM public.ledger_postings WHERE transaction_id::text LIKE {like}",
        f"DELETE FROM public.ledger_transactions WHERE id::text LIKE {like}",
        f"DELETE FROM public.payments WHERE checkout_group_id::text LIKE {like}",
        f"DELETE FROM public.order_item_products WHERE order_item_id::text LIKE {like}",
        f"DELETE FROM public.order_items WHERE order_id::text LIKE {like}",
        f"DELETE FROM public.order_events WHERE order_id::text LIKE {like}",
        f"DELETE FROM public.orders WHERE id::text LIKE {like}",
        f"DELETE FROM public.checkout_groups WHERE id::text LIKE {like}",
        f"DELETE FROM public.funnel_events WHERE customer_id::text LIKE {like}",
        f"DELETE FROM public.clip_views WHERE clip_id::text LIKE {like}",
        f"DELETE FROM public.video_clips WHERE id::text LIKE {like}",
        f"DELETE FROM public.listing_analytics WHERE listing_id::text LIKE {like}",
        f"DELETE FROM public.search_documents WHERE entity_id::text LIKE {like}",
        f"DELETE FROM public.vendor_listings WHERE id::text LIKE {like}",
        f"DELETE FROM public.products WHERE id::text LIKE {like}",
        f"DELETE FROM public.categories WHERE id::text LIKE {like}",
        f"DELETE FROM public.vendors WHERE id::text LIKE {like}",
        f"DELETE FROM public.user_roles WHERE user_id::text LIKE {like}",
        f"DELETE FROM public.profiles WHERE id::text LIKE {like}",
        f"DELETE FROM auth.users WHERE id::text LIKE {like}",
    ]
    result = db.run_script("BEGIN;\n" + SERVICE + ";\n".join(statements) + ";\nCOMMIT;\n")
    assert result.ok, result.error


def _catalog() -> list[str]:
    sql = []
    for n in (A, B, OWNER):
        sql.append(f"INSERT INTO auth.users (id, email) VALUES ('{u(n)}', 'zz-perf-{n}@x.test')")
        sql.append(
            f"INSERT INTO public.profiles (id, display_name) VALUES ('{u(n)}', 'zz perf {n}') "
            "ON CONFLICT (id) DO NOTHING"
        )
    for n in (V1, V2):
        sql.append(
            "INSERT INTO public.vendors (id, owner_user_id, slug, display_name, status, kyc_tier) "
            f"VALUES ('{u(n)}', '{u(OWNER)}', 'zz-perf-{n}', 'Zz Perf | {n}', 'active', 1)"
        )
    for n, name in ((C1, "Zz Phones"), (C2, "Zz Shoes")):
        sql.append(
            "INSERT INTO public.categories (id, name, slug, path, commission_key) VALUES "
            f"('{u(n)}', '{name}', 'zz-perf-{n}', 'zz_perf_{n}', 'default')"
        )
    for n, cat, name in ((P1, C1, "Zz Phone One"), (P2, C1, "Zz Phone Two"), (P3, C2, "Zz Shoe")):
        sql.append(
            "INSERT INTO public.products (id, name, slug, category_id, status) VALUES "
            f"('{u(n)}', '{name}', 'zz-perf-{n}', '{u(cat)}', 'active')"
        )
    for n, product, vendor in ((L1, P1, V1), (L2, P2, V2), (L3, P3, V1)):
        sql.append(
            "INSERT INTO public.vendor_listings (id, vendor_id, product_id, price_ngwee, "
            f"condition, stock_mode, status) VALUES ('{u(n)}', '{u(vendor)}', '{u(product)}', "
            "10000, 'new', 'always_available', 'draft')"
        )
    return sql


def _views() -> list[str]:
    rows = ((L1, DAY, 100), (L2, NEXT, 40), (L3, DAY, 30), (L3, AFTER, 999))
    sql = [
        "INSERT INTO public.listing_analytics (listing_id, day, pdp_views) VALUES "
        f"('{u(listing)}', '{day.isoformat()}', {views})"
        for listing, day, views in rows
    ]
    sql += [
        f"INSERT INTO public.video_clips (id, vendor_id, caption) VALUES ('{u(K1)}', '{u(V1)}', "
        "'Zz unboxing'), "
        f"('{u(K2)}', '{u(V2)}', NULL)"
    ]
    # K1: 3 views; K2: 25 views (one viewer per day, so spread over profiles A/B/OWNER x days).
    clip_views = [(K1, A, DAY), (K1, B, DAY), (K1, A, NEXT)]
    sql += [
        "INSERT INTO public.clip_views (clip_id, user_id, viewed_on) VALUES "
        f"('{u(clip)}', '{u(user)}', '{day.isoformat()}')"
        for clip, user, day in clip_views
    ]
    sql.append(
        "INSERT INTO public.clip_views (clip_id, user_id, viewed_on) "
        f"SELECT '{u(K2)}', ('{P}' || lpad(to_hex(n), 2, '0'))::uuid, d "
        f"FROM (VALUES ({A}), ({B}), ({OWNER})) v(n), "
        f"(VALUES ('{DAY.isoformat()}'::date), ('{NEXT.isoformat()}'::date)) w(d)"
    )
    return sql


def _cart(customer: int, listing: int, at: str, clip: int | None = None) -> str:
    clip_part = f', "clip_id": "{u(clip)}"' if clip else ""
    return (
        "INSERT INTO public.funnel_events (stage, customer_id, snapshot, created_at) VALUES "
        f"""('cart_add', '{u(customer)}', '{{"lines": [{{"listing_id": "{u(listing)}", """
        f""""qty": 1{clip_part}}}]}}'::jsonb, {at})"""
    )


def _carts() -> list[str]:
    return [
        _cart(A, L1, ts(DAY, "08:00:00"), K1),  # assists O1 and O2
        _cart(A, L1, ts(DAY, "08:30:00")),
        _cart(B, L1, ts(DAY, "09:00:00"), K1),  # B never buys L1
        _cart(B, L1, ts(NEXT, "09:00:00")),
        _cart(B, L2, ts(DAY, "12:00:00")),
        _cart(B, L2, ts(BEFORE, "22:30:00")),  # 00:30 CAT on DAY -> inside
        _cart(B, L3, ts(NEXT, "22:30:00")),  # 00:30 CAT on AFTER -> outside
    ]


def _group(n: int, customer: int, at: str) -> str:
    return (
        "INSERT INTO public.checkout_groups (id, customer_id, idempotency_key, subtotal_ngwee, "
        f"delivery_fee_ngwee, total_ngwee, status, created_at) VALUES ('{u(n)}', '{u(customer)}', "
        f"'zz-perf-{n}', 0, 0, 0, 'completed', {at})"
    )


def _order(
    n: int,
    group: int,
    customer: int,
    vendor: int,
    listing: int,
    *,
    qty: int,
    price: int,
    fee: int,
    rate_bps: int,
    at: str,
    status: str = "delivered",
    fulfilment: str = "delivery",
) -> list[str]:
    snapshot = (
        f'{{"lines": [{{"listing_id": "{u(listing)}", "rate_bps": {rate_bps}, '
        f'"line_total_ngwee": {qty * price}}}]}}'
    )
    return [
        "INSERT INTO public.orders (id, checkout_group_id, vendor_id, customer_id, status, "
        "fulfilment, delivery_fee_ngwee, commission_snapshot, created_at) VALUES "
        f"('{u(n)}', '{u(group)}', '{u(vendor)}', '{u(customer)}', '{status}', '{fulfilment}', "
        f"{fee}, '{snapshot}'::jsonb, {at})",
        "INSERT INTO public.order_items (id, order_id, item_kind, qty, unit_price_ngwee) "
        f"VALUES ('{u(n + 0x40)}', '{u(n)}', 'product', {qty}, {price})",
        "INSERT INTO public.order_item_products (order_item_id, listing_id) VALUES "
        f"('{u(n + 0x40)}', '{u(listing)}')",
    ]


def _payment(group: int, status: str, at: str) -> str:
    return (
        "INSERT INTO public.payments (id, checkout_group_id, provider, rail, lenco_reference, "
        f"amount_ngwee, status, created_at) VALUES ('{u(group + 0x80)}', '{u(group)}', 'lenco', "
        f"'mtn', 'pay-zzperf-{group}', 100, '{status}', {at})"
    )


def _fee(txn: int, group: int, fee: int, at: str) -> list[str]:
    def account(kind: str) -> str:
        return (
            f"(SELECT id FROM public.ledger_accounts WHERE kind = '{kind}' AND vendor_id IS NULL)"
        )

    return [
        "INSERT INTO public.ledger_transactions (id, kind, idempotency_key, payment_id, "
        f"created_at) VALUES ('{u(txn)}', 'lenco_fee', 'zz-perf-{txn}', '{u(group + 0x80)}', {at})",
        "INSERT INTO public.ledger_postings (transaction_id, account_id, amount_ngwee, created_at) "
        f"VALUES ('{u(txn)}', {account('fees')}, {fee}, {at}), "
        f"('{u(txn)}', {account('platform_cash')}, {-fee}, {at})",
    ]


def _commerce() -> list[str]:
    day, nxt = ts(DAY, "10:00:00"), ts(NEXT, "10:00:00")
    return [
        # G61/O1: A buys 1 x L1 (10,000) + 2,000 delivery; 10% commission; fee 250;
        # courier 1,500 -> 1,000 + 2,000 - 250 - 1,500 = 1,250.
        _group(0x61, A, day),
        *_order(0x01, 0x61, A, V1, L1, qty=1, price=10_000, fee=2_000, rate_bps=1000, at=day),
        _payment(0x61, "success", day),
        *_fee(0x71, 0x61, 250, day),
        "INSERT INTO public.courier_partners (id, name, contact_email) VALUES "
        f"('{u(COURIER)}', 'zz perf courier', 'zz@x.test')",
        # Consent is a dispatch-time guard, not what this report measures.
        "ALTER TABLE public.dispatch_requests "
        "DISABLE TRIGGER dispatch_requests_require_delivery_consent",
        "INSERT INTO public.dispatch_requests (order_id, courier_partner_id, status, "
        f"quoted_price_ngwee) VALUES ('{u(0x01)}', '{u(COURIER)}', 'requested', 1500)",
        "ALTER TABLE public.dispatch_requests "
        "ENABLE TRIGGER dispatch_requests_require_delivery_consent",
        # G62/O2: A buys 2 x L1 (20,000), pickup; commission 2,000; no booked fee;
        # 10,000 refunded -> loss 2,000 * 10,000 / 20,000 = 1,000 -> contribution 1,000.
        _group(0x62, A, nxt),
        *_order(
            0x02,
            0x62,
            A,
            V1,
            L1,
            qty=2,
            price=10_000,
            fee=0,
            rate_bps=1000,
            at=nxt,
            fulfilment="pickup",
        ),
        _payment(0x62, "success", nxt),
        "INSERT INTO public.refunds (id, order_id, lane, amount_ngwee, status, source_key) "
        f"VALUES ('{u(0x72)}', '{u(0x02)}', 1, 10000, 'completed', 'zz-perf-72')",
        # G63: O3 (B, L2, 5,000 + 1,000 delivery, 5% -> 250, no dispatch) and cancelled O4
        # (L3, 5,000). Fee 200 shared by value: 200 * 6,000 / 11,000 = 109.
        # Contribution 250 + 1,000 - 109 = 1,141.
        _group(0x63, B, day),
        *_order(0x03, 0x63, B, V2, L2, qty=1, price=5_000, fee=1_000, rate_bps=500, at=day),
        *_order(
            0x04,
            0x63,
            B,
            V1,
            L3,
            qty=1,
            price=5_000,
            fee=0,
            rate_bps=500,
            at=day,
            status="cancelled",
        ),
        _payment(0x63, "success", day),
        *_fee(0x73, 0x63, 200, day),
        # G65/O5: payment failed -> not an order.
        _group(0x65, B, day),
        *_order(0x05, 0x65, B, V1, L3, qty=1, price=5_000, fee=0, rate_bps=500, at=day),
        _payment(0x65, "failed", day),
        # G66/O6: B's paid order long before the window -> B is a returning customer.
        _group(0x66, B, ts(LONG_AGO, "10:00:00")),
        *_order(
            0x06,
            0x66,
            B,
            V2,
            L2,
            qty=1,
            price=5_000,
            fee=0,
            rate_bps=500,
            at=ts(LONG_AGO, "10:00:00"),
        ),
        _payment(0x66, "success", ts(LONG_AGO, "10:00:00")),
    ]


def _seed(db: PgConn) -> None:
    statements = _catalog() + _views() + _carts() + _commerce()
    result = db.run_script("BEGIN;\n" + SERVICE + ";\n".join(statements) + ";\nCOMMIT;\n")
    assert result.ok, result.error


@pytest.fixture
def live(db: PgConn, monkeypatch: pytest.MonkeyPatch) -> Generator[PgConn, None, None]:
    monkeypatch.setenv("SUPABASE_DB_URL", db.dsn)
    _cleanup(db)
    _seed(db)
    yield db
    _cleanup(db)
    reset_pools()


def _by_id(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in items}


def test_product_scorecards_rank_top_bottom_and_gems(live: PgConn) -> None:
    card = performance.scorecard("products", WINDOW, finance=True)
    assert card["entities"] == 3
    assert [item["id"] for item in card["top"]] == [u(P1), u(P2)]
    # Bottom: views >= 20, lowest view->order first: P3 (0), P1 (2/100), P2 (1/40).
    assert [item["id"] for item in card["bottom"]] == [u(P3), u(P1), u(P2)]
    assert [item["id"] for item in card["hidden_gems"]] == [u(P1)]
    p1 = _by_id(card["top"])[u(P1)]
    assert p1 == {
        "id": u(P1),
        "name": "Zz Phone One",
        "views": 100,
        "carts": 4,
        "orders": 2,
        "units": 3,
        "customers": 1,
        "repeat_customers": 1,
        "view_to_cart_bps": 400,
        "cart_to_order_bps": 5_000,
        "view_to_order_bps": 200,
        "repeat_rate_bps": 10_000,
        "item_sales_ngwee": 30_000,
        "contribution_ngwee": 2_250,
        "contribution_per_order_ngwee": 1_125,
    }
    p2 = _by_id(card["top"])[u(P2)]
    # The 22:30 UTC cart the evening before is 00:30 CAT inside the window.
    assert (p2["views"], p2["carts"], p2["orders"], p2["contribution_ngwee"]) == (40, 2, 1, 1_141)
    p3 = _by_id(card["bottom"])[u(P3)]
    assert (p3["views"], p3["carts"], p3["orders"], p3["view_to_order_bps"]) == (30, 0, 0, 0)


def test_category_and_vendor_rollups(live: PgConn) -> None:
    cats = _by_id(performance.scorecard("categories", WINDOW, finance=True)["bottom"])
    c1 = cats[u(C1)]
    assert c1["name"] == "Zz Phones"
    assert (c1["views"], c1["carts"], c1["orders"], c1["units"]) == (140, 6, 3, 4)
    assert (c1["customers"], c1["repeat_customers"], c1["repeat_rate_bps"]) == (2, 1, 5_000)
    assert c1["item_sales_ngwee"] == 35_000 and c1["contribution_ngwee"] == 3_391
    assert (cats[u(C2)]["views"], cats[u(C2)]["orders"]) == (30, 0)

    vendors = _by_id(performance.scorecard("vendors", WINDOW, finance=True)["bottom"])
    # Labels never carry the psql field separator.
    assert vendors[u(V1)]["name"] == f"Zz Perf / {V1}"
    assert (vendors[u(V1)]["views"], vendors[u(V1)]["carts"], vendors[u(V1)]["orders"]) == (
        130,
        4,
        2,
    )
    assert (vendors[u(V2)]["views"], vendors[u(V2)]["carts"], vendors[u(V2)]["orders"]) == (
        40,
        2,
        1,
    )


def test_clip_scorecards_use_clip_views_and_assisted_orders(live: PgConn) -> None:
    card = performance.scorecard("clips", WINDOW, finance=True)
    k1 = _by_id(card["top"])[u(K1)]
    assert str(k1["name"]).startswith(f"Zz Perf / {V1}: Zz unboxing")
    # 3 views; 2 clip-attributed carts (A and B); A's O1 and O2 are clip-assisted.
    assert (k1["views"], k1["carts"], k1["orders"], k1["units"]) == (3, 2, 2, 3)
    assert (k1["customers"], k1["repeat_customers"]) == (1, 1)
    assert k1["contribution_ngwee"] == 2_250
    # K2 has 6 views (< MIN_VIEWS) and no sales: not in bottom yet.
    assert u(K2) not in _by_id(card["bottom"])
    assert card["entities"] == 2


def test_funnel_totals_repeat_and_returning(live: PgConn) -> None:
    funnel = performance.funnel_totals(WINDOW)
    # Views/carts/orders here are platform-wide; other suites leave nothing on these days.
    assert funnel["views"] == 170
    assert funnel["carts"] == 6
    assert (funnel["orders"], funnel["customers"]) == (3, 2)
    assert funnel["repeat_customers"] == 1 and funnel["repeat_rate_bps"] == 5_000
    assert funnel["returning_customers"] == 1 and funnel["returning_rate_bps"] == 5_000
    assert funnel["view_to_order_bps"] == rate_bps(3, 170)


def test_contribution_after_fee_courier_and_refunds(live: PgConn) -> None:
    block = performance.contribution(WINDOW)
    assert block == {
        "orders": 3,
        "items_ngwee": 35_000,
        "delivery_fee_ngwee": 3_000,
        "commission_ngwee": 3_250,
        "payment_fee_ngwee": 359,
        "courier_cost_ngwee": 1_500,
        "refunded_ngwee": 10_000,
        "refund_loss_ngwee": 1_000,
        "contribution_ngwee": 3_391,
        "negative_orders": 0,
        "fee_unbooked_orders": 1,
        "courier_cost_unknown_orders": 1,
        "contribution_per_order_ngwee": 1_130,
        "margin_bps": rate_bps(3_391, 38_000),
    }


def test_counts_only_without_finance(live: PgConn) -> None:
    payload = performance.build_performance(WINDOW, include_money=False)
    assert payload["finance_visible"] is False
    assert payload["contribution"] is None
    for grain in performance.GRAINS:
        for ranking in ("top", "bottom", "hidden_gems"):
            for item in payload[grain][ranking]:
                assert item["item_sales_ngwee"] is None
                assert item["contribution_ngwee"] is None
                assert item["contribution_per_order_ngwee"] is None
    assert payload["products"]["top"][0]["orders"] == 2
