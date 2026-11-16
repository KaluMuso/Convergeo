"""Unified checkout on real Postgres: event tickets in the cart next to products.

Covers the ticket lane end to end — cart line, capacity hold, offer pricing
across a product and a ticket, separate goods / ticket orders in one checkout,
commission on the discounted price, buyer platform fee, COD refusal, capacity,
voided holds, the one-event rule, cross-vendor offer items, an expired offer,
the per-customer limit counting one checkout as one redemption, and issuance
linking exactly the claimed tickets (no extra ticket minted).

Same disposable database contract as test_offers_order_db.py.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from app.errors import AppError
from app.services.cart.tickets import (
    claim_session_holds,
    load_cart_ticket_lines,
    load_session_holds,
    match_holds,
    put_ticket_line,
    release_session_holds,
    remove_ticket_line,
    ticket_platform_fee_ngwee,
)
from app.services.offers.apply import expand_unified_for_order
from app.services.orders.create import CartLineInput, VendorFulfilmentInput, create_orders_atomic
from app.services.orders.ticket_lane import build_ticket_order
from app.services.stock.claim import claim_reservation
from app.services.tickets.purchase import issue_tickets_for_paid_order
from app.supabase_client import SupabaseServiceClient
from tests import test_offers_order_db as _offers_db
from tests.rls.conftest import PgConn
from tests.test_offers_order_db import CUSTOMER_ID, VENDOR_A, VENDOR_B, _listing, _scalar
from tests.test_order_creation import _insert_checkout_group

# Same disposable-database fixtures as the offers order tests.
db = _offers_db.db
db_url_env = _offers_db.db_url_env
service = _offers_db.service


def _rows(conn: PgConn, sql: str) -> list[dict[str, Any]]:
    result = conn.run(f"SELECT coalesce(json_agg(t), '[]')::text FROM ({sql}) t")
    assert result.ok, result.error
    return list(json.loads("".join(result.rows)))


def _event(
    conn: PgConn,
    *,
    vendor: str = VENDOR_A,
    capacity: int = 50,
    price: int = 15_000,
    fee_payer: str = "organiser",
) -> tuple[str, str, str]:
    event_id, instance_id, type_id = (str(uuid.uuid4()) for _ in range(3))
    result = conn.run(
        f"""
        INSERT INTO public.events (id, organiser_vendor_id, title, slug, status)
        VALUES ('{event_id}', '{vendor}', 'Gig {event_id[:4]}', 'gig-{event_id}', 'published');
        UPDATE public.events SET platform_fee_payer = '{fee_payer}' WHERE id = '{event_id}';
        INSERT INTO public.event_instances (id, event_id, starts_at, capacity)
        VALUES ('{instance_id}', '{event_id}', now() + interval '20 days', {capacity});
        INSERT INTO public.ticket_types (id, event_id, kind, name, price_ngwee)
        VALUES ('{type_id}', '{event_id}', 'fixed', 'GA', {price});
        """
    )
    assert result.ok, result.error
    return event_id, instance_id, type_id


def _cart(conn: PgConn) -> str:
    existing = conn.run(
        f"SELECT id::text FROM public.carts WHERE user_id = '{CUSTOMER_ID}' AND status = 'active'"
    )
    assert existing.ok, existing.error
    if existing.rows:
        cart_id = existing.rows[0]
    else:
        cart_id = str(uuid.uuid4())
        created = conn.run(
            f"INSERT INTO public.carts (id, user_id, status) "
            f"VALUES ('{cart_id}', '{CUSTOMER_ID}', 'active')"
        )
        assert created.ok, created.error
    cleared = conn.run(f"DELETE FROM public.cart_ticket_items WHERE cart_id = '{cart_id}'")
    assert cleared.ok, cleared.error
    return cart_id


def _offer(
    conn: PgConn,
    *,
    offer_type: str,
    items: list[tuple[Any, ...]],
    vendor: str = VENDOR_A,
    extra: dict[str, object] | None = None,
) -> str:
    """items: (role, item_kind, ref_id[, qty])."""
    offer_id = str(uuid.uuid4())
    fields: dict[str, object] = {"offer_type": offer_type, "status": "active", "title": "Combo"}
    fields.update(extra or {})
    cols = ", ".join(["id", "vendor_id", *fields])
    vals = ", ".join(
        [f"'{offer_id}'", f"'{vendor}'"]
        + [f"'{v}'" if isinstance(v, str) else str(v) for v in fields.values()]
    )
    sql = f"INSERT INTO public.offers ({cols}) VALUES ({vals});"
    for index, item in enumerate(items):
        role, kind, ref = item[:3]
        qty = item[3] if len(item) > 3 else 1
        column = {"product": "listing_id", "event": "event_id"}[kind]
        sql += (
            "INSERT INTO public.offer_items "
            f"(offer_id, role, item_kind, {column}, qty, sort_order) "
            f"VALUES ('{offer_id}', '{role}', '{kind}', '{ref}', {qty}, {index});"
        )
    result = conn.run(sql)
    assert result.ok, result.error
    return offer_id


def _checkout(
    conn: PgConn,
    service: SupabaseServiceClient,
    *,
    products: list[tuple[str, int, int]],
    tickets: list[tuple[str, str, int]],
    method: str = "momo",
) -> tuple[str, Callable[[], Any]]:
    """Cart -> session (holds claimed) -> a callable that places the orders."""
    cart_id = _cart(conn)
    for instance_id, type_id, qty in tickets:
        put_ticket_line(
            service,
            customer_id=CUSTOMER_ID,
            cart_id=cart_id,
            instance_id=instance_id,
            ticket_type_id=type_id,
            qty=qty,
        )
    ticket_lines = load_cart_ticket_lines(cart_id)
    cart_lines = [
        CartLineInput(
            cart_item_id=str(uuid.uuid4()),
            listing_id=listing_id,
            vendor_id=VENDOR_A,
            qty=qty,
            unit_price_ngwee=price,
            title_snapshot="Item",
        )
        for listing_id, qty, price in products
    ]
    expanded, priced_tickets, _ = expand_unified_for_order(
        cart_lines, ticket_lines, service.client, customer_id=CUSTOMER_ID
    )
    product_subtotal = sum(line.qty * line.unit_price_ngwee for line in expanded)
    ticket_subtotal = sum(line.total_ngwee for line in priced_tickets)
    fee = ticket_platform_fee_ngwee(priced_tickets)
    session_id = str(uuid.uuid4())
    _insert_checkout_group(
        conn,
        session_id=session_id,
        idempotency_key=f"chk-{session_id}",
        subtotal=product_subtotal + ticket_subtotal,
        delivery_fee=0,
        total=product_subtotal + ticket_subtotal + fee,
    )
    ok = conn.run(
        f"UPDATE public.checkout_groups SET platform_fee_ngwee = {fee} WHERE id = '{session_id}'"
    )
    assert ok.ok, ok.error
    for listing_id, qty, _price in products:
        assert claim_reservation(
            listing_id=listing_id, checkout_group_id=session_id, qty=qty, ttl_minutes=15
        ).claimed
    claim_session_holds(
        service, checkout_group_id=session_id, customer_id=CUSTOMER_ID, lines=ticket_lines
    )

    def place() -> Any:
        holds = match_holds(ticket_lines, load_session_holds(session_id))
        return create_orders_atomic(
            client=service.client,
            customer_id=CUSTOMER_ID,
            session_id=session_id,
            idempotency_key=f"idem-{session_id}",
            payment_method=method,  # type: ignore[arg-type]
            cart_lines=expanded,
            vendor_groups=[
                VendorFulfilmentInput(
                    vendor_id=VENDOR_A,
                    fulfilment="pickup",
                    delivery_zone=None,
                    delivery_fee_ngwee=0,
                    subtotal_ngwee=product_subtotal,
                )
            ]
            if expanded
            else [],
            ticket_order=build_ticket_order(priced_tickets, holds),
        )

    return session_id, place


def _pay(conn: PgConn, session_id: str) -> None:
    payment_id = str(uuid.uuid4())
    total = _scalar(
        conn, f"SELECT total_ngwee::text FROM public.checkout_groups WHERE id = '{session_id}'"
    )
    result = conn.run(
        f"""
        INSERT INTO public.payments (
          id, checkout_group_id, provider, rail, lenco_reference, amount_ngwee, status
        ) VALUES (
          '{payment_id}', '{session_id}', 'lenco', 'mtn', 'pay-{payment_id[:8]}', {total},
          'success'
        );
        """
    )
    assert result.ok, result.error


def _sql_use_counts(
    _client: Any, *, customer_id: str, offer_ids: Any
) -> dict[str, int]:
    """Real redemption counts (the PostgREST test double has no embedded joins)."""
    ids = sorted(set(offer_ids))
    if not ids:
        return {}
    from app.services.stock.claim import run_sql_script

    quoted = ", ".join(f"'{i}'" for i in ids)
    result = run_sql_script(
        "SELECT oi.offer_id::text || '|' || count(DISTINCT o.checkout_group_id)::text "
        "FROM public.order_items oi JOIN public.orders o ON o.id = oi.order_id "
        "LEFT JOIN public.checkout_groups cg ON cg.id = o.checkout_group_id "
        f"WHERE oi.offer_id IN ({quoted}) AND o.customer_id = '{customer_id}' "
        "AND o.status <> 'cancelled' AND coalesce(cg.status, '') NOT IN ('expired', 'abandoned') "
        "GROUP BY oi.offer_id"
    )
    assert result.ok, result.error
    out: dict[str, int] = {}
    for row in result.rows:
        offer_id, _, count = row.rpartition("|")
        out[offer_id] = int(count)
    return out


@pytest.fixture(autouse=True)
def _real_use_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.offers.store.customer_offer_use_counts", _sql_use_counts)


@pytest.fixture(autouse=True)
def _archive_offers_after(db: PgConn) -> Any:
    """Offers are vendor-wide: never leak a live one into another test's cart."""
    yield
    db.run("UPDATE public.offers SET status = 'archived' WHERE status = 'active'")


@pytest.mark.usefixtures("db_url_env")
class TestUnifiedCheckout:
    def test_mixed_cart_places_goods_and_ticket_orders_with_offer_across_both(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing = _listing(db, price=40_000)
        event_id, instance_id, type_id = _event(db, price=15_050, fee_payer="buyer")
        offer_id = _offer(
            db,
            offer_type="bundle",
            items=[("anchor", "product", listing), ("addon", "event", event_id, 2)],
            extra={"bundle_pricing": "addon_percent_off", "addon_percent_off": 33},
        )
        session_id, place = _checkout(
            db, service, products=[(listing, 1, 40_000)], tickets=[(instance_id, type_id, 2)]
        )
        place()

        orders = _rows(
            db,
            "SELECT id::text, vendor_id::text, order_lane, cod, platform_fee_ngwee, "
            "delivery_fee_ngwee, commission_snapshot FROM public.orders "
            f"WHERE checkout_group_id = '{session_id}' ORDER BY order_lane",
        )
        assert [o["order_lane"] for o in orders] == ["goods", "ticket"]
        assert {o["vendor_id"] for o in orders} == {VENDOR_A}
        goods, ticket = orders
        assert not ticket["cod"]
        items = _rows(
            db,
            "SELECT oi.order_id::text, oi.item_kind, oi.qty, oi.unit_price_ngwee, "
            "oi.list_unit_price_ngwee, oi.offer_discount_ngwee, oi.offer_id::text, "
            "oit.instance_id::text AS instance_id "
            "FROM public.order_items oi "
            "LEFT JOIN public.order_item_tickets oit ON oit.order_item_id = oi.id "
            f"WHERE oi.order_id IN ('{goods['id']}', '{ticket['id']}')",
        )
        ticket_items = [i for i in items if i["order_id"] == ticket["id"]]
        goods_items = [i for i in items if i["order_id"] == goods["id"]]
        assert {i["item_kind"] for i in ticket_items} == {"ticket"}
        assert {i["instance_id"] for i in ticket_items} == {instance_id}
        assert sum(i["qty"] for i in ticket_items) == 2
        assert {i["item_kind"] for i in goods_items} == {"product"}
        # 33% off the 2-ticket add-on: floor(30100 * 33 / 100) = 9933 off -> 20167,
        # split into whole-ngwee order lines 10083 x 1 + 10084 x 1 (exact sum).
        ticket_paid = sum(i["qty"] * i["unit_price_ngwee"] for i in ticket_items)
        assert ticket_paid == 30_100 - 9_933
        assert sorted(i["unit_price_ngwee"] for i in ticket_items) == [10_083, 10_084]
        assert sum(i["offer_discount_ngwee"] for i in ticket_items) == 9_933
        assert all(i["offer_id"] == offer_id for i in ticket_items)
        assert all(i["list_unit_price_ngwee"] == 15_050 for i in ticket_items)
        # Anchor keeps its price in percent mode.
        assert sum(i["qty"] * i["unit_price_ngwee"] for i in goods_items) == 40_000
        # Ticket commission snapshot is on what was paid; buyer fee on the same.
        snap = ticket["commission_snapshot"]
        assert snap["category_key"] == "event_tickets"
        assert snap["fee_payer"] == "buyer"
        assert sum(line["line_total_ngwee"] for line in snap["lines"]) == ticket_paid
        assert len(snap["ticket_claim_ids"]) == 2
        assert ticket["platform_fee_ngwee"] == snap["platform_fee_ngwee"] > 0
        # The checkout total is what the orders collect (escrow reconciles).
        total = int(
            _scalar(
                db, f"SELECT total_ngwee::text FROM public.checkout_groups WHERE id='{session_id}'"
            )
        )
        assert total == 40_000 + ticket_paid + ticket["platform_fee_ngwee"]
        holds = _rows(
            db,
            "SELECT status, order_id::text FROM public.checkout_ticket_holds "
            f"WHERE checkout_group_id = '{session_id}'",
        )
        assert holds == [{"status": "consumed", "order_id": ticket["id"]}]

        # Issuance after payment links exactly the claims and mints nothing
        # extra; QR secrets are set.
        _pay(db, session_id)
        outcome = issue_tickets_for_paid_order(service, ticket["id"])
        assert outcome.issued_count == 2
        tickets = _rows(
            db,
            "SELECT t.id::text, t.order_item_id::text, t.qr_secret IS NOT NULL AS has_qr "
            "FROM public.tickets t JOIN public.order_items oi ON oi.id = t.order_item_id "
            f"WHERE oi.order_id = '{ticket['id']}' AND t.status <> 'void'",
        )
        assert sorted(t["id"] for t in tickets) == sorted(snap["ticket_claim_ids"])
        assert all(t["has_qr"] for t in tickets)
        per_item: dict[str, int] = {}
        for t in tickets:
            per_item[t["order_item_id"]] = per_item.get(t["order_item_id"], 0) + 1
        assert len(per_item) == len(ticket_items) == 2  # split line: claims shared out
        live = int(
            _scalar(
                db,
                "SELECT count(*)::text FROM public.tickets "
                f"WHERE instance_id = '{instance_id}' AND status <> 'void'",
            )
        )
        assert live == 2
        # Idempotent: a second run issues nothing.
        assert issue_tickets_for_paid_order(service, ticket["id"]).issued_count == 0

    def test_cod_is_refused_when_the_cart_has_tickets(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing = _listing(db, price=10_000)
        _event_id, instance_id, type_id = _event(db, price=5_000)
        session_id, place = _checkout(
            db,
            service,
            products=[(listing, 1, 10_000)],
            tickets=[(instance_id, type_id, 1)],
            method="cod",
        )
        with pytest.raises(AppError) as excinfo:
            place()
        assert excinfo.value.code == "checkout.cod_not_allowed"
        assert (
            _scalar(
                db,
                f"SELECT count(*)::text FROM public.orders WHERE checkout_group_id='{session_id}'",
            )
            == "0"
        )

    def test_tickets_only_checkout_places_one_ticket_order(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        _event_id, instance_id, type_id = _event(db, price=7_500, vendor=VENDOR_B)
        session_id, place = _checkout(
            db, service, products=[], tickets=[(instance_id, type_id, 2)]
        )
        result = place()
        assert [o.vendor_id for o in result.orders] == [VENDOR_B]
        lane = _scalar(
            db, f"SELECT order_lane FROM public.orders WHERE checkout_group_id='{session_id}'"
        )
        assert lane == "ticket"

    def test_capacity_is_never_oversold_and_failed_claim_leaves_no_hold(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        _event_id, instance_id, type_id = _event(db, capacity=2)
        cart_id = _cart(db)
        put_ticket_line(
            service,
            customer_id=CUSTOMER_ID,
            cart_id=cart_id,
            instance_id=instance_id,
            ticket_type_id=type_id,
            qty=3,
        )
        lines = load_cart_ticket_lines(cart_id)
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idempotency_key=f"chk-{session_id}",
            subtotal=45_000,
            delivery_fee=0,
            total=45_000,
        )
        with pytest.raises(AppError) as excinfo:
            claim_session_holds(
                service, checkout_group_id=session_id, customer_id=CUSTOMER_ID, lines=lines
            )
        assert excinfo.value.code == "tickets.oversell"
        assert (
            _scalar(
                db,
                "SELECT count(*)::text FROM public.tickets "
                f"WHERE instance_id = '{instance_id}' AND status <> 'void'",
            )
            == "0"
        )
        assert load_session_holds(session_id) == []

    def test_voided_hold_refuses_placement_without_partial_orders(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        listing = _listing(db, price=10_000)
        _event_id, instance_id, type_id = _event(db)
        session_id, place = _checkout(
            db, service, products=[(listing, 1, 10_000)], tickets=[(instance_id, type_id, 2)]
        )
        # The stale-claim sweeper voided the claims after the session started.
        ok = db.run(
            "UPDATE public.tickets SET status = 'void' "
            f"WHERE instance_id = '{instance_id}' AND order_item_id IS NULL"
        )
        assert ok.ok, ok.error
        with pytest.raises(AppError) as excinfo:
            place()
        assert excinfo.value.code == "checkout.reservation_expired"
        assert excinfo.value.http_status == 410
        assert (
            _scalar(
                db,
                f"SELECT count(*)::text FROM public.orders WHERE checkout_group_id='{session_id}'",
            )
            == "0"
        )

    def test_released_session_voids_its_claims_once(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        _event_id, instance_id, type_id = _event(db)
        session_id, _place = _checkout(
            db, service, products=[], tickets=[(instance_id, type_id, 2)]
        )
        assert release_session_holds(session_id) == 2
        assert release_session_holds(session_id) == 0
        assert (
            _scalar(
                db,
                "SELECT count(*)::text FROM public.tickets "
                f"WHERE instance_id = '{instance_id}' AND status <> 'void'",
            )
            == "0"
        )

    def test_cart_holds_tickets_for_one_event_instance_only(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        _e1, instance_1, type_1 = _event(db)
        _e2, instance_2, type_2 = _event(db)
        cart_id = _cart(db)
        line_id = put_ticket_line(
            service,
            customer_id=CUSTOMER_ID,
            cart_id=cart_id,
            instance_id=instance_1,
            ticket_type_id=type_1,
            qty=1,
        )
        with pytest.raises(AppError) as excinfo:
            put_ticket_line(
                service,
                customer_id=CUSTOMER_ID,
                cart_id=cart_id,
                instance_id=instance_2,
                ticket_type_id=type_2,
                qty=1,
            )
        assert excinfo.value.code == "cart.tickets_one_event"
        # Same line again sets the quantity (upsert), it does not duplicate.
        put_ticket_line(
            service,
            customer_id=CUSTOMER_ID,
            cart_id=cart_id,
            instance_id=instance_1,
            ticket_type_id=type_1,
            qty=4,
        )
        lines = load_cart_ticket_lines(cart_id)
        assert [(line.id, line.qty) for line in lines] == [(line_id, 4)]
        # A type from another event never pairs with this instance.
        mismatch = db.run(
            "INSERT INTO public.cart_ticket_items (cart_id, ticket_type_id, instance_id, "
            f"event_id, qty) VALUES ('{cart_id}', '{type_2}', '{instance_1}', "
            f"(SELECT event_id FROM public.ticket_types WHERE id = '{type_2}'), 1)"
        )
        assert not mismatch.ok and "CART_TICKET_EVENT_MISMATCH" in (mismatch.error or "")
        assert remove_ticket_line(customer_id=CUSTOMER_ID, cart_id=cart_id, line_id=line_id)
        assert load_cart_ticket_lines(cart_id) == []

    def test_offer_on_another_vendors_event_is_refused(self, db: PgConn) -> None:
        listing = _listing(db, price=10_000)
        event_b, _instance, _type = _event(db, vendor=VENDOR_B)
        offer_id = str(uuid.uuid4())
        ok = db.run(
            "INSERT INTO public.offers (id, vendor_id, offer_type, status, title, buy_n, pay_m) "
            f"VALUES ('{offer_id}', '{VENDOR_A}', 'buy_n_pay_m', 'active', 'x', 2, 1);"
            "INSERT INTO public.offer_items (offer_id, role, item_kind, listing_id) "
            f"VALUES ('{offer_id}', 'eligible', 'product', '{listing}');"
        )
        assert ok.ok, ok.error
        refused = db.run(
            "INSERT INTO public.offer_items (offer_id, role, item_kind, event_id) "
            f"VALUES ('{offer_id}', 'eligible', 'event', '{event_b}')"
        )
        assert not refused.ok and "OFFER_ITEM_CROSS_VENDOR" in (refused.error or "")

    def test_offer_expired_before_placement_refuses_ticket_order(
        self, db: PgConn, service: SupabaseServiceClient
    ) -> None:
        event_id, instance_id, type_id = _event(db, price=10_000)
        offer_id = _offer(
            db,
            offer_type="buy_n_pay_m",
            items=[("eligible", "event", event_id)],
            extra={"buy_n": 2, "pay_m": 1},
        )
        session_id, place = _checkout(
            db, service, products=[], tickets=[(instance_id, type_id, 2)]
        )
        ok = db.run(
            f"UPDATE public.offers SET ends_at = now() - interval '1 second', "
            f"starts_at = now() - interval '1 day' WHERE id = '{offer_id}'"
        )
        assert ok.ok, ok.error
        with pytest.raises(AppError) as excinfo:
            place()
        assert excinfo.value.code == "offers.expired"
        assert (
            _scalar(
                db,
                f"SELECT count(*)::text FROM public.orders WHERE checkout_group_id='{session_id}'",
            )
            == "0"
        )

    def test_per_customer_limit_counts_a_mixed_checkout_once(
        self, db: PgConn, service: SupabaseServiceClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Price every checkout with the offer (two tabs), see test_offers_order_db.
        monkeypatch.setattr(
            "app.services.offers.store.customer_offer_use_counts",
            lambda *_args, **_kwargs: {},
        )
        listing = _listing(db, price=20_000, stock=10)
        event_id, instance_id, type_id = _event(db, price=10_000)
        _offer(
            db,
            offer_type="bundle",
            items=[("anchor", "product", listing), ("addon", "event", event_id)],
            extra={
                "bundle_pricing": "addon_percent_off",
                "addon_percent_off": 50,
                "per_customer_limit": 2,
            },
        )
        _, first = _checkout(
            db, service, products=[(listing, 1, 20_000)], tickets=[(instance_id, type_id, 1)]
        )
        first()  # one checkout, two orders (goods + ticket) -> one redemption
        _, second = _checkout(
            db, service, products=[(listing, 1, 20_000)], tickets=[(instance_id, type_id, 1)]
        )
        second()  # second redemption: still within the limit of 2
        _, third = _checkout(
            db, service, products=[(listing, 1, 20_000)], tickets=[(instance_id, type_id, 1)]
        )
        with pytest.raises(AppError) as excinfo:
            third()
        assert excinfo.value.code == "offers.limit_reached"
