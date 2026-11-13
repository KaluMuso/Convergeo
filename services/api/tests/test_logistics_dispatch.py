"""Logistics phase 1 on courier dispatch v1 (real Postgres).

Second attempt / return to shop / restock, combined "handed over + cash"
action, write-once rider cash custody, cash cap, exact-match remittances that
book the COD cash in the ledger, actual courier cost, and the order state
machine's new delivery readiness step.
"""

from __future__ import annotations

import uuid

import pytest
from app.errors import AppError
from app.services.dispatch import service as dispatch_service
from app.services.dispatch.state import DispatchStatus, fetch_dispatch
from app.services.logistics import custody
from app.services.orders.state import ActorRole, OrderEvent, transition_order
from tests import test_courier_dispatch as _dispatch_tests
from tests.rls.conftest import PgConn
from tests.test_courier_dispatch import (
    ADMIN_ID,
    COD_TOTAL_NGWEE,
    SHOP_A,
    _advance_to_picked_up,
    _create,
    _handover_code,
    _make_courier,
    _make_order,
    _order_status,
    _sql_ok,
    _wrong_code,
)
from tests.test_order_creation import _load_ids

# Reuse the courier dispatch suite's real-Postgres fixtures.
db = _dispatch_tests.db
db_url_env = _dispatch_tests.db_url_env
flag_on = _dispatch_tests.flag_on

pytestmark = pytest.mark.usefixtures("flag_on")


def _complete(dispatch_id: str, code: str, cod: int | None, method: str = "cash") -> None:
    dispatch_service.complete_delivery(
        dispatch_id=dispatch_id,
        actor_id=ADMIN_ID,
        handover_code=code,
        pod_photo_public_id=None,
        cod_collected_ngwee=cod,
        cod_collected_method=method,
    )


def _fail(dispatch_id: str, code: str = "customer_unavailable") -> None:
    dispatch_service.transition_dispatch_admin(
        dispatch_id=dispatch_id,
        to_status=DispatchStatus.FAILED,
        actor_id=ADMIN_ID,
        failure_reason="Customer not home",
        failure_code=code,
    )


def _ledger_balanced_for_order(db: PgConn, order_id: str) -> int:
    rows = _sql_ok(
        db,
        "SELECT coalesce(sum(p.amount_ngwee), 0)::text FROM public.ledger_postings p "
        "JOIN public.ledger_transactions t ON t.id = p.transaction_id "
        f"WHERE t.order_id = '{order_id}';",
    )
    return int(rows[0])


class TestCombinedCompleteAndCustody:
    def test_code_and_cash_in_one_step(self, db: PgConn) -> None:
        order_id, courier_id, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        _complete(dispatch_id, _handover_code(db, dispatch_id), COD_TOTAL_NGWEE)

        dispatch = fetch_dispatch(dispatch_id)
        assert dispatch.status is DispatchStatus.DELIVERED
        assert dispatch.delivered_via == "handover_code"
        assert dispatch.cod_collected_ngwee == COD_TOTAL_NGWEE
        assert dispatch.cod_collected_method == "cash"
        assert dispatch.cod_collected_at is not None
        assert _order_status(db, order_id) == "delivered"
        held = custody.custody_summary()
        mine = next(r for r in held if r["courier_partner_id"] == courier_id)
        assert mine["held_ngwee"] == COD_TOTAL_NGWEE

    @pytest.mark.parametrize(
        ("cod", "expected"),
        [
            (None, "dispatch_cod_required"),
            (COD_TOTAL_NGWEE - 100, "dispatch_cod_mismatch"),
            (COD_TOTAL_NGWEE + 1, "dispatch_cod_mismatch"),
        ],
    )
    def test_wrong_or_missing_cash_changes_nothing(
        self, db: PgConn, cod: int | None, expected: str
    ) -> None:
        order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        code = _handover_code(db, dispatch_id)
        with pytest.raises(AppError) as exc:
            _complete(dispatch_id, code, cod)
        assert exc.value.code == expected
        dispatch = fetch_dispatch(dispatch_id)
        assert dispatch.status is DispatchStatus.PICKED_UP
        assert dispatch.cod_collected_ngwee is None
        assert _order_status(db, order_id) == "shipped"
        # The code was not consumed: the correct cash still completes it.
        _complete(dispatch_id, code, COD_TOTAL_NGWEE, "mobile_money")
        assert fetch_dispatch(dispatch_id).cod_collected_method == "mobile_money"

    def test_wrong_code_records_no_cash(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        with pytest.raises(AppError) as exc:
            _complete(dispatch_id, _wrong_code(_handover_code(db, dispatch_id)), COD_TOTAL_NGWEE)
        assert exc.value.code == "dispatch_handover_invalid"
        assert fetch_dispatch(dispatch_id).cod_collected_ngwee is None

    def test_prepaid_job_refuses_cash(self, db: PgConn) -> None:
        order_id = _make_order(db, cod=False)
        _sql_ok(
            db,
            "INSERT INTO public.payments (checkout_group_id, provider, rail, amount_ngwee, "
            "status, lenco_reference) SELECT checkout_group_id, 'lenco', 'mtn', 1, 'success', "
            f"'pay-{uuid.uuid4().hex[:12]}' FROM public.orders WHERE id = '{order_id}';",
        )
        courier = _make_courier(db)
        created = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=courier, actor_id=ADMIN_ID
        )
        _advance_to_picked_up(created.dispatch.id)
        with pytest.raises(AppError) as exc:
            _complete(created.dispatch.id, _handover_code(db, created.dispatch.id), 500)
        assert exc.value.code == "dispatch_cod_not_expected"

    def test_custody_is_write_once_in_the_database(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        _complete(dispatch_id, _handover_code(db, dispatch_id), COD_TOTAL_NGWEE)
        result = db.run(
            "UPDATE public.dispatch_requests SET cod_collected_ngwee = 1 "
            f"WHERE id = '{dispatch_id}';"
        )
        assert not result.ok
        assert "write-once" in (result.error or "")

    def test_complete_needs_exactly_one_proof(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        with pytest.raises(AppError) as exc:
            dispatch_service.complete_delivery(
                dispatch_id=dispatch_id,
                actor_id=ADMIN_ID,
                handover_code=None,
                pod_photo_public_id=None,
                cod_collected_ngwee=COD_TOTAL_NGWEE,
                cod_collected_method="cash",
            )
        assert exc.value.code == "validation_error"


class TestCashCapAndRemittance:
    def test_cap_blocks_new_cash_job_until_remitted_and_ledger_books(self, db: PgConn) -> None:
        courier = _make_courier(db)
        # The COD path books against the shop's ledger accounts (seeded by migrations
        # in production; created here for an isolated run).
        _sql_ok(
            db,
            "INSERT INTO public.ledger_accounts (kind, vendor_id) "
            f"SELECT k, '{SHOP_A}'::uuid FROM unnest(ARRAY['vendor_payable', 'cod_receivable']) k "
            "WHERE NOT EXISTS (SELECT 1 FROM public.ledger_accounts a "
            f"WHERE a.kind = k AND a.vendor_id = '{SHOP_A}'::uuid);",
        )
        first_order = _make_order(db)
        # Test-owner fixture: give the order a purchase-time commission snapshot.
        _sql_ok(
            db,
            "UPDATE public.orders SET commission_snapshot = jsonb_build_object('lines', "
            "jsonb_build_array(jsonb_build_object('listing_id', gen_random_uuid(), "
            "'category_key', 'default', 'rate_bps', 800, 'qty', 1, "
            f"'unit_price_ngwee', {COD_TOTAL_NGWEE - 3_000}, "
            f"'line_total_ngwee', {COD_TOTAL_NGWEE - 3_000}))) WHERE id = '{first_order}';",
        )
        first = dispatch_service.create_dispatch(
            order_id=first_order, courier_partner_id=courier, actor_id=ADMIN_ID
        ).dispatch.id
        _advance_to_picked_up(first)
        _complete(first, _handover_code(db, first), COD_TOTAL_NGWEE)

        # K1,050.50 held + K1,050.50 more > K1,500 cap.
        second_order = _make_order(db)
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=second_order, courier_partner_id=courier, actor_id=ADMIN_ID
            )
        assert exc.value.code == "courier_cash_cap_exceeded"
        assert exc.value.details["held_ngwee"] == COD_TOTAL_NGWEE

        # Remittance must match the recorded cash exactly.
        with pytest.raises(AppError) as mismatch:
            custody.record_remittance(
                courier_partner_id=courier,
                amount_ngwee=COD_TOTAL_NGWEE - 50,
                method="mobile_money",
                reference=f"MM-{uuid.uuid4().hex[:8]}",
                dispatch_ids=[first],
                actor_id=ADMIN_ID,
            )
        assert mismatch.value.code == "remittance_mismatch"
        assert mismatch.value.details["expected_ngwee"] == COD_TOTAL_NGWEE
        assert fetch_dispatch(first).remittance_id is None

        reference = f"MM-{uuid.uuid4().hex[:8]}"
        result = custody.record_remittance(
            courier_partner_id=courier,
            amount_ngwee=COD_TOTAL_NGWEE,
            method="mobile_money",
            reference=reference,
            dispatch_ids=[first],
            actor_id=ADMIN_ID,
        )
        assert fetch_dispatch(first).remittance_id == result.remittance_id
        assert result.bookings[first_order] in {"booked", "already_booked"}
        assert _order_status(db, first_order) == "completed"
        assert _ledger_balanced_for_order(db, first_order) == 0
        cash = _sql_ok(
            db,
            "SELECT coalesce(sum(p.amount_ngwee),0)::text FROM public.ledger_postings p "
            "JOIN public.ledger_transactions t ON t.id = p.transaction_id "
            "JOIN public.ledger_accounts a ON a.id = p.account_id "
            f"WHERE t.order_id = '{first_order}' AND a.kind = 'platform_cash';",
        )
        assert int(cash[0]) == COD_TOTAL_NGWEE

        # Same reference twice is refused; already-remitted jobs cannot be reused.
        with pytest.raises(AppError) as dup:
            custody.record_remittance(
                courier_partner_id=courier,
                amount_ngwee=COD_TOTAL_NGWEE,
                method="mobile_money",
                reference=reference,
                dispatch_ids=[first],
                actor_id=ADMIN_ID,
            )
        assert dup.value.code in {"remittance_duplicate", "remittance_jobs_invalid"}

        # Cash handed in: the courier may take a new cash job.
        dispatch_service.create_dispatch(
            order_id=second_order, courier_partner_id=courier, actor_id=ADMIN_ID
        )

    def test_remittance_refuses_another_couriers_job(self, db: PgConn) -> None:
        _order_id, courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        _complete(dispatch_id, _handover_code(db, dispatch_id), COD_TOTAL_NGWEE)
        with pytest.raises(AppError) as exc:
            custody.record_remittance(
                courier_partner_id=_make_courier(db),
                amount_ngwee=COD_TOTAL_NGWEE,
                method="mobile_money",
                reference=f"MM-{uuid.uuid4().hex[:8]}",
                dispatch_ids=[dispatch_id],
                actor_id=ADMIN_ID,
            )
        assert exc.value.code == "remittance_jobs_invalid"
        assert courier  # the real courier still holds the cash
        assert fetch_dispatch(dispatch_id).remittance_id is None


class TestSecondAttemptAndReturn:
    def test_two_attempts_then_return_cancels_and_restocks(self, db: PgConn) -> None:
        listing_id = str(uuid.uuid4())
        product_id = _load_ids()["products"]["phone"]
        _sql_ok(
            db,
            "INSERT INTO public.vendor_listings (id, vendor_id, product_id, price_ngwee, "
            "condition, stock_mode, stock_qty, status) VALUES "
            f"('{listing_id}', '{SHOP_A}', '{product_id}', 45000, 'new', 'tracked', 5, 'active');",
        )
        order_id, courier, first = _create(db)
        item = _sql_ok(
            db, f"SELECT id FROM public.order_items WHERE order_id = '{order_id}' LIMIT 1;"
        )[0]
        _sql_ok(
            db,
            "INSERT INTO public.order_item_stock_consumption "
            "(order_item_id, order_id, listing_id, listing_qty, variant_qty) VALUES "
            f"('{item}', '{order_id}', '{listing_id}', 2, 0);",
        )
        _advance_to_picked_up(first)
        _fail(first)
        assert _order_status(db, order_id) == "shipped"

        second = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=courier, actor_id=ADMIN_ID
        ).dispatch
        assert second.attempt_no == 2
        _advance_to_picked_up(second.id)
        _fail(second.id, "customer_refused")

        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=order_id, courier_partner_id=courier, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_attempts_exhausted"

        ret = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=courier, actor_id=ADMIN_ID, direction="return"
        ).dispatch
        assert ret.direction == "return" and ret.cod_amount_ngwee == 0
        dispatch_service.transition_dispatch_admin(
            dispatch_id=ret.id, to_status=DispatchStatus.ACCEPTED, actor_id=ADMIN_ID
        )
        # A return is never "delivered" by photo; only the shop's acknowledgement closes it.
        with pytest.raises(AppError):
            dispatch_service.transition_dispatch_admin(
                dispatch_id=ret.id,
                to_status=DispatchStatus.PICKED_UP,
                actor_id=ADMIN_ID,
            )
            dispatch_service.transition_dispatch_admin(
                dispatch_id=ret.id,
                to_status=DispatchStatus.DELIVERED,
                actor_id=ADMIN_ID,
                pod_photo_public_id="convergeo/pod/x",
            )
        stock_before = int(
            _sql_ok(db, f"SELECT stock_qty FROM public.vendor_listings WHERE id='{listing_id}';")[0]
        )
        result = dispatch_service.acknowledge_return(
            dispatch_id=ret.id, actor_id=ADMIN_ID, note="Shop has it back", full_admin=True
        )
        assert result.order_status == "cancelled"
        assert fetch_dispatch(ret.id).delivered_via == "vendor_ack"
        stock_after = int(
            _sql_ok(db, f"SELECT stock_qty FROM public.vendor_listings WHERE id='{listing_id}';")[0]
        )
        assert stock_after == stock_before + 2
        # A second acknowledgement does nothing more.
        with pytest.raises(AppError):
            dispatch_service.acknowledge_return(
                dispatch_id=ret.id, actor_id=ADMIN_ID, note="again", full_admin=True
            )

    def test_return_needs_a_failed_delivery(self, db: PgConn) -> None:
        order_id, courier, dispatch_id = _create(db)
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=order_id, courier_partner_id=courier, actor_id=ADMIN_ID, direction="return"
            )
        assert exc.value.code in {"dispatch_already_active", "dispatch_return_not_allowed"}
        assert dispatch_id

    def test_shipped_cancel_without_return_ack_restocks_nothing(self, db: PgConn) -> None:
        # The DB trigger only restocks shipped -> cancelled on the explicit return path.
        listing_id = str(uuid.uuid4())
        product_id = _load_ids()["products"]["phone"]
        _sql_ok(
            db,
            "INSERT INTO public.vendor_listings (id, vendor_id, product_id, price_ngwee, "
            "condition, stock_mode, stock_qty, status) VALUES "
            f"('{listing_id}', '{SHOP_A}', '{product_id}', 45000, 'new', 'tracked', 5, 'active');",
        )
        order_id = _make_order(db, status="shipped")
        item = _sql_ok(
            db, f"SELECT id FROM public.order_items WHERE order_id = '{order_id}' LIMIT 1;"
        )[0]
        _sql_ok(
            db,
            "INSERT INTO public.order_item_stock_consumption "
            "(order_item_id, order_id, listing_id, listing_qty, variant_qty) VALUES "
            f"('{item}', '{order_id}', '{listing_id}', 3, 0);",
        )
        transition_order(
            order_id=order_id,
            event=OrderEvent.CANCEL,
            actor_role=ActorRole.ADMIN,
            actor_id=ADMIN_ID,
            note="Lost in transit",
        )
        stock = _sql_ok(
            db, f"SELECT stock_qty FROM public.vendor_listings WHERE id='{listing_id}';"
        )
        assert int(stock[0]) == 5


class TestCostAndReadiness:
    def test_cost_recorded_only_after_collection(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        with pytest.raises(AppError) as exc:
            dispatch_service.record_actual_cost(
                dispatch_id=dispatch_id, cost_ngwee=4_000, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_cost_not_allowed"
        _advance_to_picked_up(dispatch_id)
        updated = dispatch_service.record_actual_cost(
            dispatch_id=dispatch_id, cost_ngwee=4_000, actor_id=ADMIN_ID
        )
        assert updated.actual_cost_ngwee == 4_000
        for bad in (-1, 1.5, True):
            with pytest.raises(AppError):
                dispatch_service.record_actual_cost(
                    dispatch_id=dispatch_id,
                    cost_ngwee=bad,  # type: ignore[arg-type]
                    actor_id=ADMIN_ID,
                )

    def test_ready_for_collection_then_rider_pickup_ships(self, db: PgConn) -> None:
        order_id = _make_order(db, status="processing")
        transition_order(
            order_id=order_id,
            event=OrderEvent.READY_FOR_COLLECTION,
            actor_role=ActorRole.ADMIN,
            actor_id=ADMIN_ID,
            note="Parcel sealed",
        )
        assert _order_status(db, order_id) == "ready"
        ready_at = _sql_ok(
            db, f"SELECT ready_at IS NOT NULL FROM public.orders WHERE id='{order_id}';"
        )
        assert ready_at[0] in {"t", "true"}
        board = dispatch_service.board_snapshot()
        assert any(row["order_id"] == order_id for row in board["ready_orders"])
        courier = _make_courier(db)
        dispatch_id = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=courier, actor_id=ADMIN_ID
        ).dispatch.id
        _advance_to_picked_up(dispatch_id)
        assert _order_status(db, order_id) == "shipped"

    def test_vendor_self_delivery_is_not_platform_dispatched(self, db: PgConn) -> None:
        order_id = _make_order(db)
        _sql_ok(
            db,
            "UPDATE public.orders SET delivery_fee_ngwee = 0, delivery_funding = 'vendor_self' "
            f"WHERE id = '{order_id}';",
        )
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=order_id, courier_partner_id=_make_courier(db), actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_vendor_self_delivery"
        board = dispatch_service.board_snapshot()
        assert all(row["order_id"] != order_id for row in board["ready_orders"])


LOGISTICS_USER = "22222222-2222-2222-2222-222222222222"


def _grant_rbac(db: PgConn, key: str, permissions: list[str]) -> None:
    perms = ", ".join(f"'{p}'" for p in permissions)
    _sql_ok(
        db,
        "INSERT INTO public.admin_roles (key, name, permissions) "
        f"VALUES ('{key}', 'Test {key}', ARRAY[{perms}]::text[]) "
        "ON CONFLICT (key) DO UPDATE SET permissions = EXCLUDED.permissions;",
    )
    _sql_ok(
        db,
        "INSERT INTO public.user_roles (user_id, role) "
        f"VALUES ('{LOGISTICS_USER}', '{key}') ON CONFLICT DO NOTHING;",
    )


class TestLimitedLogisticsLogin:
    def test_db_accepts_new_permissions_and_resolves_them(self, db: PgConn) -> None:
        _grant_rbac(db, "rbac_logistics_ops", ["logistics.manage"])
        rows = _sql_ok(
            db,
            f"SELECT public.has_admin_permission('{LOGISTICS_USER}', 'logistics.manage')::text, "
            f"public.has_admin_permission('{LOGISTICS_USER}', 'cod.reconcile')::text, "
            f"public.has_admin_permission('{ADMIN_ID}', 'cod.reconcile')::text;",
        )
        assert rows[0].split("|") == ["true", "false", "true"]
        bad = db.run(
            "INSERT INTO public.admin_roles (key, name, permissions) "
            "VALUES ('rbac_bad_perm', 'Bad', ARRAY['logistics.everything']::text[]);"
        )
        assert not bad.ok

    def test_logistics_operator_moves_parcels_but_cannot_cancel_or_refund(self, db: PgConn) -> None:
        _grant_rbac(db, "rbac_logistics_ops", ["logistics.manage"])
        order_id = _make_order(db, status="processing")
        transition_order(
            order_id=order_id,
            event=OrderEvent.SHIP,
            actor_role=ActorRole.ADMIN,
            actor_id=LOGISTICS_USER,
            note="[courier-dispatch] picked_up",
        )
        assert _order_status(db, order_id) == "shipped"
        with pytest.raises(AppError) as exc:
            transition_order(
                order_id=order_id,
                event=OrderEvent.CANCEL,
                actor_role=ActorRole.ADMIN,
                actor_id=LOGISTICS_USER,
                note="not allowed",
            )
        assert exc.value.code == "forbidden"
        assert _order_status(db, order_id) == "shipped"

    def test_finance_only_role_cannot_drive_logistics_events(self, db: PgConn) -> None:
        _sql_ok(
            db,
            f"DELETE FROM public.user_roles WHERE user_id = '{LOGISTICS_USER}' "
            "AND role LIKE 'rbac_%';",
        )
        _grant_rbac(db, "rbac_finance_view", ["finance.read"])
        order_id = _make_order(db, status="processing")
        with pytest.raises(AppError) as exc:
            transition_order(
                order_id=order_id,
                event=OrderEvent.SHIP,
                actor_role=ActorRole.ADMIN,
                actor_id=LOGISTICS_USER,
                note="no",
            )
        assert exc.value.code == "forbidden"
        _sql_ok(
            db,
            f"DELETE FROM public.user_roles WHERE user_id = '{LOGISTICS_USER}' "
            "AND role LIKE 'rbac_%';",
        )


def test_route_inventory_gives_logistics_dispatch_but_not_money() -> None:
    from app.core.auth import admin_permission_for_request

    assert admin_permission_for_request("/admin/dispatch/board", "GET") == "logistics.manage"
    assert (
        admin_permission_for_request("/admin/dispatch/requests/{dispatch_id}/complete", "POST")
        == "logistics.manage"
    )
    assert (
        admin_permission_for_request("/admin/logistics/cash/remittances", "POST") == "cod.reconcile"
    )
    # Escrow / refunds / COD confirmation stay full-admin (not in the inventory).
    for method, path in (
        ("POST", "/admin/orders/{order_id}/cod/confirm-collection"),
        ("POST", "/admin/refunds/{refund_id}/approve"),
        ("POST", "/admin/payouts/run"),
    ):
        assert admin_permission_for_request(path, method) is None
