"""W8 offers on real Postgres: order placement snapshots, gift pool, cancel release,
expired offers, DB guards and RLS.

Uses the same disposable database contract as test_order_creation.py
(``ORDER_TEST_DB_URL`` = a fully migrated database, or a local 5432 Postgres).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator

import pytest
from app.errors import AppError
from app.services.offers.apply import expand_cart_lines_for_order
from app.services.offers.returns_guard import assert_not_offer_gift
from app.services.orders.create import (
    CartLineInput,
    VendorFulfilmentInput,
    create_orders_atomic,
)
from app.services.orders.state import ActorRole, OrderEvent, transition_order
from app.services.stock.claim import claim_reservation
from app.supabase_client import SupabaseServiceClient
from tests.rls.conftest import PgConn, apply_migrations, seed_matrix_fixtures
from tests.test_order_creation import _insert_checkout_group, _load_ids, _PgClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
VENDOR_B_OWNER = "44444444-4444-4444-4444-444444444444"
_DB_NAME = "vergeo5_offers_order_test"


@pytest.fixture(scope="module")
def db() -> Generator[PgConn, None, None]:
    if isolated_url := os.environ.get("ORDER_TEST_DB_URL"):
        conn = PgConn(isolated_url)
        ready = conn.run("SELECT 1 FROM public.offers LIMIT 1")
        assert ready.ok, ready.error
        seed_matrix_fixtures(conn)
    else:
        admin = PgConn("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
        if not admin.run("SELECT 1").ok:
            pytest.skip("Postgres not reachable on 127.0.0.1:5432")
        admin.run(f"DROP DATABASE IF EXISTS {_DB_NAME};")
        admin.run(f"CREATE DATABASE {_DB_NAME};")
        conn = PgConn(f"postgresql://postgres:postgres@127.0.0.1:5432/{_DB_NAME}")
        conn.run("DROP SCHEMA IF EXISTS public CASCADE")
        conn.run("CREATE SCHEMA public")
        conn.run("DROP SCHEMA IF EXISTS auth CASCADE")
        apply_migrations(conn)
        seed_matrix_fixtures(conn)
    ok = conn.run("UPDATE public.feature_flags SET enabled = true WHERE flag = 'bundles';")
    assert ok.ok, ok.error
    yield conn
    conn.run("UPDATE public.feature_flags SET enabled = false WHERE flag = 'bundles';")


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


@pytest.fixture
def service(db: PgConn) -> SupabaseServiceClient:
    return SupabaseServiceClient(_PgClient(db))  # type: ignore[arg-type]


def _scalar(conn: PgConn, sql: str) -> str:
    result = conn.run(sql)
    assert result.ok, result.error
    assert result.rows, sql
    return result.rows[0]


def _listing(conn: PgConn, *, price: int, vendor: str = VENDOR_A, stock: int = 50) -> str:
    listing_id = str(uuid.uuid4())
    product_id = _load_ids()["products"]["phone"]
    result = conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, title_override, price_ngwee, condition, stock_mode,
          stock_qty, status
        ) VALUES (
          '{listing_id}', '{vendor}', '{product_id}', 'Item {listing_id[:4]}', {price},
          'new', 'tracked', {stock}, 'active'
        );
        """
    )
    assert result.ok, result.error
    return listing_id


def _offer(
    conn: PgConn,
    *,
    offer_type: str,
    items: list[tuple[str, str]],
    vendor: str = VENDOR_A,
    extra: dict[str, object] | None = None,
) -> str:
    offer_id = str(uuid.uuid4())
    fields: dict[str, object] = {
        "offer_type": offer_type,
        "status": "active",
        "title": f"Offer {offer_id[:4]}",
    }
    fields.update(extra or {})
    cols = ", ".join(["id", "vendor_id", *fields])
    vals = ", ".join(
        [f"'{offer_id}'", f"'{vendor}'"]
        + [f"'{v}'" if isinstance(v, str) else str(v) for v in fields.values()]
    )
    sql = f"INSERT INTO public.offers ({cols}) VALUES ({vals});"
    for index, (role, listing_id) in enumerate(items):
        sql += (
            "INSERT INTO public.offer_items (offer_id, role, item_kind, listing_id, sort_order) "
            f"VALUES ('{offer_id}', '{role}', 'product', '{listing_id}', {index});"
        )
    result = conn.run(sql)
    assert result.ok, result.error
    return offer_id


def _place(
    conn: PgConn,
    service: SupabaseServiceClient,
    lines: list[tuple[str, int, int]],
) -> tuple[str, list[CartLineInput]]:
    """Price with offers, claim holds and place one COD pickup order; return session."""
    cart = [
        CartLineInput(
            cart_item_id=str(uuid.uuid4()),
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            qty=qty,
            unit_price_ngwee=price,
            title_snapshot="Item",
        )
        for listing_id, qty, price in lines
    ]
    expanded, _ = expand_cart_lines_for_order(cart, service.client, customer_id=CUSTOMER_ID)
    subtotal = sum(line.qty * line.unit_price_ngwee for line in expanded)
    session_id = str(uuid.uuid4())
    _insert_checkout_group(
        conn,
        session_id=session_id,
        idempotency_key=f"chk-{session_id}",
        subtotal=subtotal,
        delivery_fee=0,
        total=subtotal,
    )
    for listing_id, qty, _price in lines:
        assert claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=qty, ttl_minutes=15
        ).claimed
    create_orders_atomic(
        client=service.client,
        customer_id=CUSTOMER_ID,
        session_id=session_id,
        idempotency_key=f"idem-{session_id}",
        payment_method="cod",
        cart_lines=expanded,
        vendor_groups=[
            VendorFulfilmentInput(
                vendor_id=VENDOR_A,
                fulfilment="pickup",
                delivery_zone=None,
                delivery_fee_ngwee=0,
                subtotal_ngwee=subtotal,
            )
        ],
    )
    return session_id, expanded


def _order_id(conn: PgConn, session_id: str) -> str:
    return _scalar(
        conn, f"SELECT id::text FROM public.orders WHERE checkout_group_id='{session_id}'"
    )


@pytest.mark.usefixtures("db_url_env")
class TestOfferOrders:
    def test_bundle_order_lines_carry_frozen_discount_and_sum_exactly(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        anchor = _listing(db, price=10_000)
        addon1 = _listing(db, price=1_001)
        addon2 = _listing(db, price=2_003)
        offer_id = _offer(
            db,
            offer_type="bundle",
            items=[("anchor", anchor), ("addon", addon1), ("addon", addon2)],
            extra={"bundle_pricing": "addon_percent_off", "addon_percent_off": 75},
        )
        session_id, _ = _place(
            db, service, [(anchor, 1, 10_000), (addon1, 2, 1_001), (addon2, 1, 2_003)]
        )
        order_id = _order_id(db, session_id)
        rows = [
            json.loads(r)
            for r in db.run(
                "SELECT row_to_json(t)::text FROM (SELECT qty, unit_price_ngwee, "
                "list_unit_price_ngwee, offer_discount_ngwee, offer_id::text, is_offer_gift, "
                f"offer_snapshot FROM public.order_items WHERE order_id='{order_id}') t"
            ).rows
        ]
        paid = sum(r["qty"] * r["unit_price_ngwee"] for r in rows)
        discount = sum(r["offer_discount_ngwee"] for r in rows)
        list_total = 10_000 + 2 * 1_001 + 2_003
        # one set: addon1 x1 + addon2 x1 at 75% off -> floor(3004 * 0.75) = 2253 off
        assert discount == (1_001 + 2_003) * 75 // 100
        assert paid == list_total - discount
        assert paid == int(
            _scalar(
                db,
                f"SELECT subtotal_ngwee::text FROM public.checkout_groups WHERE id='{session_id}'",
            )
        )
        assert all(r["offer_id"] == offer_id for r in rows)
        assert all(r["offer_snapshot"]["addon_percent_off"] == 75 for r in rows)
        # Commission snapshot lines are on what was paid (discounted unit prices).
        snapshot = json.loads(
            _scalar(
                db, f"SELECT commission_snapshot::text FROM public.orders WHERE id='{order_id}'"
            )
        )
        assert sum(line["line_total_ngwee"] for line in snapshot["lines"]) == paid
        # Changing the live offer later never changes the stored order pricing.
        db.run(f"UPDATE public.offers SET addon_percent_off = 10 WHERE id='{offer_id}'")
        again = int(
            _scalar(
                db,
                "SELECT sum(qty * unit_price_ngwee)::text FROM public.order_items "
                f"WHERE order_id='{order_id}'",
            )
        )
        assert again == paid

    def test_gift_reserved_never_oversold_and_released_on_cancel(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        trigger = _listing(db, price=20_000)
        gift = _listing(db, price=4_000)
        offer_id = _offer(
            db,
            offer_type="free_gift",
            items=[("trigger", trigger), ("reward", gift)],
            extra={"gift_stock_total": 1},
        )
        first, expanded = _place(db, service, [(trigger, 1, 20_000)])
        assert [line.is_offer_gift for line in expanded] == [False, True]
        order_id = _order_id(db, first)
        assert (
            _scalar(
                db, f"SELECT gift_stock_reserved::text FROM public.offers WHERE id='{offer_id}'"
            )
            == "1"
        )
        gift_item = _scalar(
            db,
            "SELECT id::text || '|' || unit_price_ngwee::text || '|' || "
            "list_unit_price_ngwee::text || '|' || (offer_parent_item_id IS NOT NULL)::text "
            f"FROM public.order_items WHERE order_id='{order_id}' AND is_offer_gift",
        )
        gift_item_id, unit, ref, has_parent = gift_item.split("|")
        assert (unit, ref, has_parent) == ("0", "4000", "true")
        # The gift cannot be returned / refunded on its own.
        with pytest.raises(AppError) as exc:
            assert_not_offer_gift(service, gift_item_id)
        assert exc.value.code == "returns.offer_gift_not_returnable"

        # Pool empty: pricing no longer offers the gift.
        cart = [
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=trigger,
                vendor_id=VENDOR_A,
                qty=1,
                unit_price_ngwee=20_000,
                title_snapshot=None,
            )
        ]
        priced_lines, _ = expand_cart_lines_for_order(cart, service.client, customer_id=CUSTOMER_ID)
        assert not any(line.is_offer_gift for line in priced_lines)

        # A stale cart that still carries the gift is refused in-tx (no oversell),
        # and the whole order rolls back.
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=20_000,
            delivery_fee=0,
            total=20_000,
        )
        assert claim_reservation(
            listing_id=trigger, checkout_group_id=session_id, qty=1, ttl_minutes=15
        ).claimed
        with pytest.raises(AppError) as exc:
            create_orders_atomic(
                client=service.client,
                customer_id=CUSTOMER_ID,
                session_id=session_id,
                idempotency_key=f"idem-{session_id}",
                payment_method="cod",
                cart_lines=[
                    expanded[0].__class__(
                        **{
                            **{
                                f: getattr(expanded[0], f) for f in expanded[0].__dataclass_fields__
                            },
                            "cart_item_id": str(uuid.uuid4()),
                        }
                    ),
                    expanded[1],
                ],
                vendor_groups=[VendorFulfilmentInput(VENDOR_A, "pickup", None, 0, 20_000)],
            )
        assert exc.value.code == "offers.gift_out_of_stock"
        assert (
            _scalar(
                db,
                f"SELECT count(*)::text FROM public.orders WHERE checkout_group_id='{session_id}'",
            )
            == "0"
        )
        assert (
            _scalar(
                db, f"SELECT gift_stock_reserved::text FROM public.offers WHERE id='{offer_id}'"
            )
            == "1"
        )

        # Cancelling the first order returns the gift to the pool exactly once.
        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.CUSTOMER,
            actor_id=CUSTOMER_ID,
            note="test",
        )
        assert (
            _scalar(
                db, f"SELECT gift_stock_reserved::text FROM public.offers WHERE id='{offer_id}'"
            )
            == "0"
        )
        assert (
            _scalar(
                db, f"SELECT status FROM public.offer_gift_reservations WHERE order_id='{order_id}'"
            )
            == "released"
        )
        assert (
            _scalar(
                db,
                "SELECT count(*)::text FROM public.audit_log WHERE "
                f"action='order.offer_gifts_released' AND entity_id='{order_id}'",
            )
            == "1"
        )

    def test_unpaid_checkout_expiry_returns_the_gift_once(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        trigger = _listing(db, price=15_000)
        gift = _listing(db, price=3_000)
        offer_id = _offer(
            db,
            offer_type="bxgy",
            items=[("trigger", trigger), ("reward", gift)],
            extra={"buy_qty": 1, "get_qty": 1, "gift_stock_total": 3},
        )
        session_id, expanded = _place(db, service, [(trigger, 1, 15_000)])
        assert any(line.is_offer_gift for line in expanded)
        reserved = f"SELECT gift_stock_reserved::text FROM public.offers WHERE id='{offer_id}'"
        assert _scalar(db, reserved) == "1"
        expire = f"SELECT public.expire_checkout_group_if_unpaid('{session_id}', 'expired')::text"
        assert _scalar(db, expire) == "true"
        assert _scalar(db, reserved) == "0"
        # A second terminal transition is refused and releases nothing more.
        assert _scalar(db, expire) == "false"
        assert _scalar(db, reserved) == "0"
        order_id = _order_id(db, session_id)
        audits = (
            "SELECT count(*)::text FROM public.audit_log WHERE "
            f"action='order.offer_gifts_released_unpaid' AND entity_id='{order_id}'"
        )
        assert _scalar(db, audits) == "1"

    def test_offer_expired_between_pricing_and_placement_is_refused(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        a = _listing(db, price=3_000)
        offer_id = _offer(
            db, offer_type="buy_n_pay_m", items=[("eligible", a)], extra={"buy_n": 3, "pay_m": 2}
        )
        cart = [
            CartLineInput(
                cart_item_id=str(uuid.uuid4()),
                listing_id=a,
                vendor_id=VENDOR_A,
                qty=3,
                unit_price_ngwee=3_000,
                title_snapshot=None,
            )
        ]
        expanded, priced = expand_cart_lines_for_order(
            cart, service.client, customer_id=CUSTOMER_ID
        )
        assert priced is not None and priced.savings_ngwee == 3_000
        db.run(f"UPDATE public.offers SET status='paused' WHERE id='{offer_id}'")
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=6_000,
            delivery_fee=0,
            total=6_000,
        )
        assert claim_reservation(
            listing_id=a, checkout_group_id=session_id, qty=3, ttl_minutes=15
        ).claimed
        with pytest.raises(AppError) as exc:
            create_orders_atomic(
                client=service.client,
                customer_id=CUSTOMER_ID,
                session_id=session_id,
                idempotency_key=f"idem-{session_id}",
                payment_method="cod",
                cart_lines=expanded,
                vendor_groups=[VendorFulfilmentInput(VENDOR_A, "pickup", None, 0, 6_000)],
            )
        assert exc.value.code == "offers.expired"

    def test_flag_off_prices_at_list(self, db: PgConn, service: SupabaseServiceClient) -> None:
        a = _listing(db, price=3_000)
        _offer(
            db, offer_type="buy_n_pay_m", items=[("eligible", a)], extra={"buy_n": 2, "pay_m": 1}
        )
        db.run("UPDATE public.feature_flags SET enabled = false WHERE flag = 'bundles'")
        try:
            cart = [
                CartLineInput(
                    cart_item_id=str(uuid.uuid4()),
                    listing_id=a,
                    vendor_id=VENDOR_A,
                    qty=2,
                    unit_price_ngwee=3_000,
                    title_snapshot=None,
                )
            ]
            expanded, priced = expand_cart_lines_for_order(
                cart, service.client, customer_id=CUSTOMER_ID
            )
            assert priced is None and expanded == cart
        finally:
            db.run("UPDATE public.feature_flags SET enabled = true WHERE flag = 'bundles'")


class TestOfferGuardsAndRls:
    def test_offer_item_from_another_vendor_is_refused(self, db: PgConn) -> None:
        mine = _listing(db, price=1_000)
        theirs = _listing(db, price=1_000, vendor=VENDOR_B)
        offer_id = _offer(
            db, offer_type="buy_n_pay_m", items=[("eligible", mine)], extra={"buy_n": 2, "pay_m": 1}
        )
        result = db.run(
            "INSERT INTO public.offer_items (offer_id, role, item_kind, listing_id) "
            f"VALUES ('{offer_id}', 'eligible', 'product', '{theirs}')"
        )
        assert not result.ok
        assert "OFFER_ITEM_CROSS_VENDOR" in (result.error or "")

    def test_gift_line_price_rules(self, db: PgConn) -> None:
        # A non-gift line still cannot be priced 0.
        order = _scalar(db, "SELECT id::text FROM public.orders LIMIT 1")
        result = db.run(
            "INSERT INTO public.order_items (order_id, item_kind, qty, unit_price_ngwee) "
            f"VALUES ('{order}', 'product', 1, 0)"
        )
        assert not result.ok
        assert "order_items_unit_price_ngwee_check" in (result.error or "")

    def _as(self, db: PgConn, uid: str | None, sql: str) -> object:
        if uid is None:
            pre = (
                "SET LOCAL ROLE anon; "
                "DO $$ BEGIN PERFORM set_config('request.jwt.claims', '', true); END $$;"
            )
        else:
            claims = json.dumps({"sub": uid, "role": "authenticated"})
            pre = (
                "SET LOCAL ROLE authenticated; "
                f"DO $$ BEGIN PERFORM set_config('request.jwt.claims', '{claims}', true); END $$;"
            )
        return db.run(f"BEGIN; {pre} {sql}; COMMIT;")

    def test_vendor_cannot_touch_another_vendors_offer_and_cannot_move_gift_pool(
        self, db: PgConn
    ) -> None:
        mine = _listing(db, price=1_000)
        gift = _listing(db, price=500)
        offer_id = _offer(
            db,
            offer_type="free_gift",
            items=[("trigger", mine), ("reward", gift)],
            extra={"gift_stock_total": 5, "status": "draft"},
        )
        # Vendor B: zero rows visible / updated (RLS), so the title is unchanged.
        res = self._as(
            db, VENDOR_B_OWNER, f"UPDATE public.offers SET title='hijack' WHERE id='{offer_id}'"
        )
        assert getattr(res, "ok", False)
        assert _scalar(db, f"SELECT title FROM public.offers WHERE id='{offer_id}'") != "hijack"
        res = self._as(db, VENDOR_B_OWNER, f"DELETE FROM public.offers WHERE id='{offer_id}'")
        assert _scalar(db, f"SELECT count(*)::text FROM public.offers WHERE id='{offer_id}'") == "1"
        # Owner may edit their offer but never the server-managed gift counter.
        res = self._as(
            db,
            VENDOR_A_OWNER,
            f"UPDATE public.offers SET gift_stock_reserved=0, title='ok' WHERE id='{offer_id}'",
        )
        assert getattr(res, "ok", False)  # value unchanged -> allowed
        res = self._as(
            db,
            VENDOR_A_OWNER,
            f"UPDATE public.offers SET gift_stock_reserved=3 WHERE id='{offer_id}'",
        )
        assert not getattr(res, "ok", True)
        res = self._as(
            db,
            VENDOR_A_OWNER,
            f"UPDATE public.offers SET paused_by_admin=false, vendor_id='{VENDOR_B}' "
            f"WHERE id='{offer_id}'",
        )
        assert not getattr(res, "ok", True)

    def test_public_reads_only_live_offers(self, db: PgConn) -> None:
        mine = _listing(db, price=1_000)
        draft = _offer(
            db,
            offer_type="buy_n_pay_m",
            items=[("eligible", mine)],
            extra={"buy_n": 2, "pay_m": 1, "status": "draft"},
        )
        live = _offer(
            db, offer_type="buy_n_pay_m", items=[("eligible", mine)], extra={"buy_n": 3, "pay_m": 2}
        )
        res = self._as(
            db,
            None,
            f"SELECT id::text FROM public.offers WHERE id IN ('{draft}', '{live}')",
        )
        assert getattr(res, "ok", False), getattr(res, "error", None)
        assert getattr(res, "rows", []) == [live]
        res = self._as(
            db,
            None,
            "SELECT offer_id::text FROM public.offer_items "
            f"WHERE offer_id IN ('{draft}', '{live}')",
        )
        assert getattr(res, "rows", []) == [live]
        # The owner sees its draft.
        res = self._as(
            db, VENDOR_A_OWNER, f"SELECT id::text FROM public.offers WHERE id = '{draft}'"
        )
        assert getattr(res, "rows", []) == [draft]
        # Clients never see gift reservations.
        res = self._as(db, VENDOR_A_OWNER, "SELECT 1 FROM public.offer_gift_reservations")
        assert not getattr(res, "ok", True)
