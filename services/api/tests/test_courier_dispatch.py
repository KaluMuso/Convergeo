"""Courier dispatch v1 — state machine, handover code, outbox, authz, n8n tick.

Pure tests (transition table, COD money, message builder) always run. The DB
tests replay the real migrations against Postgres (same harness as
``test_pickup.py``) and skip when no database is reachable.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.errors import AppError
from app.main import create_app
from app.services.dispatch import service as dispatch_service
from app.services.dispatch.message import (
    CourierMessageContext,
    Place,
    build_courier_message,
    cod_line,
    order_reference,
)
from app.services.dispatch.state import (
    TRANSITIONS,
    DispatchStatus,
    DispatchTransitionError,
    allowed_next_statuses,
    assert_transition,
    fetch_dispatch,
    fetch_dispatch_events,
    is_transition_allowed,
)
from app.services.notifications.templates.whatsapp import render_whatsapp_template
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_OWNER = "33333333-3333-3333-3333-333333333333"
VENDOR_B_OWNER = "44444444-4444-4444-4444-444444444444"
ADMIN_ID = "66666666-6666-6666-6666-666666666666"
SHOP_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TOKEN = "valid.jwt.token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# 2 x K450.00 + 1 x K120.50 = K1,020.50 subtotal; + K30.00 Band-A fee.
ITEMS = (("Samsung A15 128GB", 2, 45_000), ("Phone case", 1, 12_050))
SUBTOTAL_NGWEE = 2 * 45_000 + 12_050
DELIVERY_FEE_NGWEE = 3_000
COD_TOTAL_NGWEE = SUBTOTAL_NGWEE + DELIVERY_FEE_NGWEE  # 105_050 -> K1,050.50


# ---------------------------------------------------------------------------
# Pure: transition table
# ---------------------------------------------------------------------------

ALL_PAIRS = [(a, b) for a in DispatchStatus for b in DispatchStatus]


@pytest.mark.parametrize(("frm", "to"), ALL_PAIRS, ids=[f"{a}->{b}" for a, b in ALL_PAIRS])
def test_transition_table_matrix(frm: DispatchStatus, to: DispatchStatus) -> None:
    valid = {
        ("requested", "accepted"),
        ("requested", "cancelled"),
        ("requested", "failed"),
        ("accepted", "picked_up"),
        ("accepted", "cancelled"),
        ("accepted", "failed"),
        ("picked_up", "delivered"),
        ("picked_up", "failed"),
    }
    expected = (frm.value, to.value) in valid
    assert is_transition_allowed(frm, to) is expected
    if expected:
        assert_transition(frm, to)
    else:
        with pytest.raises(DispatchTransitionError) as exc:
            assert_transition(frm, to)
        assert exc.value.http_status == 409
        assert exc.value.code == "dispatch_invalid_transition"


def test_terminal_statuses_have_no_exits() -> None:
    for status in (DispatchStatus.DELIVERED, DispatchStatus.FAILED, DispatchStatus.CANCELLED):
        assert allowed_next_statuses(status) == []
    assert allowed_next_statuses(DispatchStatus.REQUESTED) == [
        DispatchStatus.ACCEPTED,
        DispatchStatus.FAILED,
        DispatchStatus.CANCELLED,
    ]


def test_python_table_matches_sql_guard() -> None:
    migration = next(
        p
        for p in (
            __import__("pathlib").Path(__file__).resolve().parents[3] / "supabase" / "migrations"
        ).glob("*_courier_dispatch_v1.sql")
    )
    sql = migration.read_text(encoding="utf-8")
    allowed_block = sql.split("allowed := ")[1].split(");")[0]
    sql_pairs = set(re.findall(r"\('([a-z_]+)', '([a-z_]+)'\)", allowed_block))
    assert {(a.value, b.value) for a, b in TRANSITIONS} == sql_pairs


# ---------------------------------------------------------------------------
# Pure: COD money (integer ngwee) + courier message
# ---------------------------------------------------------------------------


def test_cod_amount_is_subtotal_plus_fee_in_ngwee() -> None:
    order = {"cod": True, "subtotal_ngwee": SUBTOTAL_NGWEE, "delivery_fee_ngwee": 3_000}
    assert dispatch_service.compute_cod_amount_ngwee(order) == COD_TOTAL_NGWEE
    assert isinstance(dispatch_service.compute_cod_amount_ngwee(order), int)


def test_cod_amount_zero_for_prepaid() -> None:
    order = {"cod": False, "subtotal_ngwee": 50_000, "delivery_fee_ngwee": 3_000}
    assert dispatch_service.compute_cod_amount_ngwee(order) == 0


@pytest.mark.parametrize("bad", [1050.5, "105050", None, True, -1])
def test_cod_amount_rejects_non_integer_ngwee(bad: Any) -> None:
    with pytest.raises(TypeError):
        dispatch_service.compute_cod_amount_ngwee(
            {"cod": True, "subtotal_ngwee": bad, "delivery_fee_ngwee": 0}
        )


def test_cod_line_formats_ngwee_with_format_k() -> None:
    assert cod_line(COD_TOTAL_NGWEE) == "Collect cash on delivery: K1,050.50"
    assert cod_line(1) == "Collect cash on delivery: K0.01"
    assert cod_line(0) == "Prepaid - collect nothing"
    with pytest.raises(TypeError):
        cod_line(1050.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        cod_line(-5)


def _message_ctx(**overrides: Any) -> CourierMessageContext:
    base: dict[str, Any] = {
        "order_id": "30303030-3030-3030-3030-303030303030",
        "courier_name": "TownStar",
        "pickup": Place(
            "Lusaka Electronics", "Kamwala, stand 12", -15.4301, 28.2873, "+260971111111"
        ),
        "dropoff": Place("Jane", "Opposite Woodlands Total", -15.4402, 28.3301, "+260972222222"),
        "items": (("Samsung A15", 2), ("Case", 1)),
        "cod_amount_ngwee": COD_TOTAL_NGWEE,
    }
    base.update(overrides)
    return CourierMessageContext(**base)


def test_message_has_landmarks_gps_items_cod_and_contacts() -> None:
    message = build_courier_message(_message_ctx())
    assert message.order_reference == "ord-30303030"
    assert "Kamwala, stand 12" in message.pickup_line
    assert "https://maps.google.com/?q=-15.430100,28.287300" in message.pickup_line
    assert "Opposite Woodlands Total" in message.dropoff_line
    assert message.items_line == "2 x Samsung A15; 1 x Case"
    assert message.cod_line == "Collect cash on delivery: K1,050.50"
    assert "+260971111111" in message.contacts_line
    assert "+260972222222" in message.contacts_line
    for param in message.whatsapp_params().values():
        assert "\n" not in param and "\t" not in param
    assert "K1,050.50" in message.text


def test_message_renders_through_whatsapp_template_registry() -> None:
    message = build_courier_message(_message_ctx(cod_amount_ngwee=0))
    rendered = render_whatsapp_template(
        "courier_dispatch_request",
        {"to": "+260973333333", "locale": "en", **message.whatsapp_params()},
    )
    assert rendered.body_parameters[4] == "Prepaid - collect nothing"
    assert len(rendered.body_parameters) == 6


def test_order_reference_charset_matches_lenco_reference_rules() -> None:
    ref = order_reference(str(uuid.uuid4()))
    assert re.fullmatch(r"ord-[0-9a-f]{8}", ref)


def test_handover_code_is_six_digits() -> None:
    for _ in range(50):
        code = dispatch_service.generate_handover_code()
        assert re.fullmatch(r"[0-9]{6}", code)


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


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
    if not conn.run("SELECT 1 FROM public.dispatch_requests LIMIT 1").ok:
        pytest.skip("courier dispatch migration not applied to this database")
    seed_matrix_fixtures(conn)
    yield conn


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _set_flag(db: PgConn, enabled: bool) -> None:
    result = db.run(
        "INSERT INTO public.feature_flags (flag, enabled, description) "
        f"VALUES ('courier_dispatch', {str(enabled).lower()}, 'test') "
        f"ON CONFLICT (flag) DO UPDATE SET enabled = {str(enabled).lower()};"
    )
    assert result.ok, result.error


@pytest.fixture
def flag_on(db: PgConn, db_url_env: None) -> Generator[None, None, None]:
    _set_flag(db, True)
    yield
    _set_flag(db, False)


def _sql_ok(db: PgConn, sql: str) -> list[str]:
    result = db.run(sql)
    assert result.ok, result.error
    return result.rows


def _make_courier(db: PgConn, *, zones: tuple[tuple[str, int | None], ...] = ()) -> str:
    courier_id = str(uuid.uuid4())
    _sql_ok(
        db,
        f"""
INSERT INTO public.courier_partners (id, name, contact_whatsapp_e164, contact_email)
VALUES ('{courier_id}', 'Courier {courier_id[:8]}', '+260977000001', 'ops@courier.test');
""",
    )
    for zone_key, price in zones:
        _sql_ok(
            db,
            "INSERT INTO public.courier_partner_zones (courier_partner_id, zone_key, price_ngwee) "
            f"VALUES ('{courier_id}', '{zone_key}', {'NULL' if price is None else price});",
        )
    return courier_id


def _make_order(
    db: PgConn,
    *,
    status: str = "processing",
    cod: bool = True,
    fulfilment: str = "delivery",
    customer_id: str = CUSTOMER_ID,
    zone: str = "lusaka_a",
    delivery_consent: bool = True,
) -> str:
    order_id = str(uuid.uuid4())
    group_id = str(uuid.uuid4())
    address_id = str(uuid.uuid4())
    total = COD_TOTAL_NGWEE
    item_rows = ",\n".join(
        f"('{order_id}', 'product', {qty}, {price}, '{title}')" for title, qty, price in ITEMS
    )
    _sql_ok(
        db,
        f"""
BEGIN;
INSERT INTO public.addresses (id, user_id, landmark, lat, lng, phone)
VALUES ('{address_id}', '{customer_id}', 'Opposite Woodlands Total', -15.4402, 28.3301,
        '+260972222222');
INSERT INTO public.checkout_groups (
  id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
) VALUES ('{group_id}', '{customer_id}', 'dispatch-{group_id}', {SUBTOTAL_NGWEE},
          {DELIVERY_FEE_NGWEE}, {total});
INSERT INTO public.orders (
  id, checkout_group_id, vendor_id, customer_id, status, fulfilment, cod,
  delivery_zone, address_id, delivery_fee_ngwee
) VALUES ('{order_id}', '{group_id}', '{SHOP_A}', '{customer_id}', '{status}',
          '{fulfilment}', {str(cod).lower()}, '{zone}', '{address_id}', {DELIVERY_FEE_NGWEE});
INSERT INTO public.order_items (order_id, item_kind, qty, unit_price_ngwee, title_snapshot)
VALUES {item_rows};
-- Zambia DPA (20261113163100): courier dispatch needs the customer's current consent.
INSERT INTO public.privacy_consents (user_id, purpose, version, granted, source)
VALUES ('{customer_id}', 'delivery_partner_share', '2026-11-13',
        {str(delivery_consent).lower()}, 'checkout');
COMMIT;
""",
    )
    return order_id


def _order_status(db: PgConn, order_id: str) -> str:
    return _sql_ok(db, f"SELECT status FROM public.orders WHERE id = '{order_id}';")[0]


def _handover_code(db: PgConn, dispatch_id: str) -> str:
    return _sql_ok(
        db,
        "SELECT code FROM public.dispatch_handover_codes "
        f"WHERE dispatch_request_id = '{dispatch_id}';",
    )[0]


def _wrong_code(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def _create(db: PgConn, **order_kwargs: Any) -> tuple[str, str, str]:
    order_id = _make_order(db, **order_kwargs)
    courier_id = _make_courier(db)
    result = dispatch_service.create_dispatch(
        order_id=order_id, courier_partner_id=courier_id, actor_id=ADMIN_ID
    )
    return order_id, courier_id, result.dispatch.id


def _advance_to_picked_up(dispatch_id: str) -> None:
    dispatch_service.transition_dispatch_admin(
        dispatch_id=dispatch_id,
        to_status=DispatchStatus.ACCEPTED,
        actor_id=ADMIN_ID,
        courier_reference="TS-1042",
    )
    dispatch_service.transition_dispatch_admin(
        dispatch_id=dispatch_id, to_status=DispatchStatus.PICKED_UP, actor_id=ADMIN_ID
    )


# ---------------------------------------------------------------------------
# DB: state machine
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("flag_on")
class TestDispatchStateMachineDb:
    def test_create_snapshots_cod_and_mints_code(self, db: PgConn) -> None:
        order_id, _courier, dispatch_id = _create(db)
        dispatch = fetch_dispatch(dispatch_id)
        assert dispatch.status is DispatchStatus.REQUESTED
        assert dispatch.cod_amount_ngwee == COD_TOTAL_NGWEE
        assert re.fullmatch(r"[0-9]{6}", _handover_code(db, dispatch_id))
        events = fetch_dispatch_events(dispatch_id)
        assert [(e["from_status"], e["to_status"]) for e in events] == [(None, "requested")]
        assert events[0]["actor"] == ADMIN_ID
        assert _order_status(db, order_id) == "processing"

    def test_prepaid_dispatch_snapshots_zero_cod(self, db: PgConn) -> None:
        order_id = _make_order(db, cod=False)
        _sql_ok(
            db,
            f"""
INSERT INTO public.payments (
  checkout_group_id, provider, rail, amount_ngwee, status, lenco_reference
)
SELECT checkout_group_id, 'lenco', 'mtn', {COD_TOTAL_NGWEE}, 'success',
       'pay-' || substr(md5(id::text), 1, 12)
FROM public.orders WHERE id = '{order_id}';
""",
        )
        result = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=_make_courier(db), actor_id=ADMIN_ID
        )
        assert result.dispatch.cod_amount_ngwee == 0

    def test_unpaid_prepaid_order_cannot_be_dispatched(self, db: PgConn) -> None:
        order_id = _make_order(db, cod=False)
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=order_id, courier_partner_id=_make_courier(db), actor_id=ADMIN_ID
            )
        assert exc.value.code == "order_payment_required"

    def test_pickup_orders_and_unpacked_orders_rejected(self, db: PgConn) -> None:
        courier = _make_courier(db)
        pickup_order = _make_order(db, fulfilment="pickup")
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=pickup_order, courier_partner_id=courier, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_not_applicable"
        placed = _make_order(db, status="placed")
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=placed, courier_partner_id=courier, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_order_not_ready"

    def test_one_active_dispatch_per_order(self, db: PgConn) -> None:
        order_id, courier_id, _dispatch_id = _create(db)
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=order_id, courier_partner_id=courier_id, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_already_active"
        assert exc.value.http_status == 409

    def test_courier_zone_and_price(self, db: PgConn) -> None:
        order_id = _make_order(db, zone="lusaka_c")
        wrong_zone = _make_courier(db, zones=(("lusaka_a", 2_500),))
        with pytest.raises(AppError) as exc:
            dispatch_service.create_dispatch(
                order_id=order_id, courier_partner_id=wrong_zone, actor_id=ADMIN_ID
            )
        assert exc.value.code == "courier_zone_not_served"
        right_zone = _make_courier(db, zones=(("lusaka_c", 6_000),))
        result = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=right_zone, actor_id=ADMIN_ID
        )
        assert result.dispatch.quoted_price_ngwee == 6_000

    def test_full_lifecycle_moves_order_through_state_machine(self, db: PgConn) -> None:
        order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        assert _order_status(db, order_id) == "shipped"
        assert fetch_dispatch(dispatch_id).courier_reference == "TS-1042"

        result = dispatch_service.verify_handover_code(
            dispatch_id=dispatch_id, code=_handover_code(db, dispatch_id), actor_id=ADMIN_ID
        )
        assert result.order_status == "delivered"
        dispatch = fetch_dispatch(dispatch_id)
        assert dispatch.status is DispatchStatus.DELIVERED
        assert dispatch.delivered_via == "handover_code"
        assert _order_status(db, order_id) == "delivered"

        steps = [(e["from_status"], e["to_status"]) for e in fetch_dispatch_events(dispatch_id)]
        assert steps == [
            (None, "requested"),
            ("requested", "accepted"),
            ("accepted", "picked_up"),
            ("picked_up", "delivered"),
        ]
        order_steps = _sql_ok(
            db,
            "SELECT from_status || '>' || to_status FROM public.order_events "
            f"WHERE order_id = '{order_id}' ORDER BY created_at;",
        )
        assert order_steps == ["processing>shipped", "shipped>delivered"]

    @pytest.mark.parametrize(
        ("path", "target"),
        [
            ((), DispatchStatus.PICKED_UP),
            ((), DispatchStatus.DELIVERED),
            ((DispatchStatus.ACCEPTED,), DispatchStatus.DELIVERED),
            ((DispatchStatus.CANCELLED,), DispatchStatus.ACCEPTED),
            ((DispatchStatus.ACCEPTED, DispatchStatus.PICKED_UP), DispatchStatus.CANCELLED),
        ],
    )
    def test_invalid_transitions_rejected(
        self, db: PgConn, path: tuple[DispatchStatus, ...], target: DispatchStatus
    ) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        for step in path:
            dispatch_service.transition_dispatch_admin(
                dispatch_id=dispatch_id, to_status=step, actor_id=ADMIN_ID
            )
        before = fetch_dispatch(dispatch_id).status
        with pytest.raises(AppError) as exc:
            dispatch_service.transition_dispatch_admin(
                dispatch_id=dispatch_id,
                to_status=target,
                actor_id=ADMIN_ID,
                pod_photo_public_id="pod/abc123",
            )
        assert exc.value.http_status == 409
        assert fetch_dispatch(dispatch_id).status is before

    def test_failed_requires_reason_and_frees_order_for_redispatch(self, db: PgConn) -> None:
        order_id, courier_id, dispatch_id = _create(db)
        with pytest.raises(AppError) as exc:
            dispatch_service.transition_dispatch_admin(
                dispatch_id=dispatch_id, to_status=DispatchStatus.FAILED, actor_id=ADMIN_ID
            )
        assert exc.value.code == "validation_error"
        dispatch_service.transition_dispatch_admin(
            dispatch_id=dispatch_id,
            to_status=DispatchStatus.FAILED,
            actor_id=ADMIN_ID,
            failure_reason="Rider unreachable",
        )
        again = dispatch_service.create_dispatch(
            order_id=order_id, courier_partner_id=courier_id, actor_id=ADMIN_ID
        )
        assert again.dispatch.id != dispatch_id

    def test_pod_photo_delivery_requires_public_id(self, db: PgConn) -> None:
        order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        with pytest.raises(AppError) as exc:
            dispatch_service.transition_dispatch_admin(
                dispatch_id=dispatch_id, to_status=DispatchStatus.DELIVERED, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_pod_required"
        with pytest.raises(AppError):
            dispatch_service.transition_dispatch_admin(
                dispatch_id=dispatch_id,
                to_status=DispatchStatus.DELIVERED,
                actor_id=ADMIN_ID,
                pod_photo_public_id="https://evil.example/x.jpg",
            )
        dispatch_service.transition_dispatch_admin(
            dispatch_id=dispatch_id,
            to_status=DispatchStatus.DELIVERED,
            actor_id=ADMIN_ID,
            pod_photo_public_id="convergeo/pod/ord-1",
        )
        assert fetch_dispatch(dispatch_id).delivered_via == "pod_photo"
        assert _order_status(db, order_id) == "delivered"

    def test_db_guard_rejects_illegal_raw_update(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        result = db.run(
            f"UPDATE public.dispatch_requests SET status = 'delivered', "
            f"delivered_via = 'pod_photo', pod_photo_public_id = 'x' WHERE id = '{dispatch_id}';"
        )
        assert not result.ok
        assert "invalid dispatch transition" in (result.error or "")

    def test_admin_jwt_cannot_write_status_directly(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        claims = '{"sub": "' + ADMIN_ID + '", "role": "authenticated"}'
        result = db.run(
            "BEGIN; SET LOCAL role authenticated; "
            f"SET LOCAL \"request.jwt.claims\" = '{claims}'; "
            f"UPDATE public.dispatch_requests SET status = 'accepted' WHERE id = '{dispatch_id}'; "
            "COMMIT;"
        )
        assert not result.ok
        assert "permission denied" in (result.error or "").lower()
        code = db.run(
            "BEGIN; SET LOCAL role authenticated; "
            f"SET LOCAL \"request.jwt.claims\" = '{claims}'; "
            "SELECT code FROM public.dispatch_handover_codes; COMMIT;"
        )
        assert not code.ok
        assert "permission denied" in (code.error or "").lower()


# ---------------------------------------------------------------------------
# DB: handover code verification, brute force, lockout
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("flag_on")
class TestHandoverCodeDb:
    def test_wrong_code_counts_down_then_locks(self, db: PgConn) -> None:
        order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        code = _handover_code(db, dispatch_id)
        wrong = _wrong_code(code)

        for expected_remaining in (4, 3, 2, 1):
            with pytest.raises(AppError) as exc:
                dispatch_service.verify_handover_code(
                    dispatch_id=dispatch_id, code=wrong, actor_id=ADMIN_ID
                )
            assert exc.value.code == "dispatch_handover_invalid"
            assert exc.value.details["attempts_remaining"] == expected_remaining

        with pytest.raises(AppError) as exc:
            dispatch_service.verify_handover_code(
                dispatch_id=dispatch_id, code=wrong, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_handover_locked"
        assert exc.value.http_status == 429

        # Locked: even the CORRECT code is refused until the lockout expires.
        with pytest.raises(AppError) as exc:
            dispatch_service.verify_handover_code(
                dispatch_id=dispatch_id, code=code, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_handover_locked"
        assert exc.value.details["retry_after"] > 0
        assert fetch_dispatch(dispatch_id).status is DispatchStatus.PICKED_UP
        assert _order_status(db, order_id) == "shipped"

        # Lockout expiry restores verification.
        _sql_ok(
            db,
            "UPDATE public.dispatch_handover_codes SET locked_until = now() - interval '1 minute' "
            f"WHERE dispatch_request_id = '{dispatch_id}';",
        )
        dispatch_service.verify_handover_code(dispatch_id=dispatch_id, code=code, actor_id=ADMIN_ID)
        assert _order_status(db, order_id) == "delivered"

    def test_code_is_single_use(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        code = _handover_code(db, dispatch_id)
        dispatch_service.verify_handover_code(dispatch_id=dispatch_id, code=code, actor_id=ADMIN_ID)
        with pytest.raises(AppError) as exc:
            dispatch_service.verify_handover_code(
                dispatch_id=dispatch_id, code=code, actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_handover_used"

    def test_code_rejected_before_pickup(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        with pytest.raises(AppError) as exc:
            dispatch_service.verify_handover_code(
                dispatch_id=dispatch_id, code=_handover_code(db, dispatch_id), actor_id=ADMIN_ID
            )
        assert exc.value.code == "dispatch_invalid_transition"

    @pytest.mark.parametrize("bad", ["12345", "1234567", "12a456", "", " 12345"])
    def test_malformed_code_is_422_without_counting(self, db: PgConn, bad: str) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        with pytest.raises(AppError) as exc:
            dispatch_service.verify_handover_code(
                dispatch_id=dispatch_id, code=bad, actor_id=ADMIN_ID
            )
        assert exc.value.http_status == 422
        failed = _sql_ok(
            db,
            "SELECT failed_attempts FROM public.dispatch_handover_codes "
            f"WHERE dispatch_request_id = '{dispatch_id}';",
        )
        assert failed == ["0"]

    def test_rate_limiter_runs_before_comparison(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)

        def limiter(actor: str) -> None:
            assert actor == ADMIN_ID
            raise AppError(code="rate_limited", message="slow down", http_status=429)

        with pytest.raises(AppError) as exc:
            dispatch_service.verify_handover_code(
                dispatch_id=dispatch_id,
                code=_wrong_code(_handover_code(db, dispatch_id)),
                actor_id=ADMIN_ID,
                rate_limiter=limiter,
            )
        assert exc.value.code == "rate_limited"
        failed = _sql_ok(
            db,
            "SELECT failed_attempts FROM public.dispatch_handover_codes "
            f"WHERE dispatch_request_id = '{dispatch_id}';",
        )
        assert failed == ["0"]


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


class FakeOutboxTable:
    def __init__(self, store: list[dict[str, Any]]) -> None:
        self._store = store
        self._pending: dict[str, Any] | None = None

    def insert(self, row: dict[str, Any]) -> FakeOutboxTable:
        self._pending = row
        return self

    def select(self, *_args: Any, **_kwargs: Any) -> FakeOutboxTable:
        self._pending = None
        return self

    def eq(self, *_args: Any) -> FakeOutboxTable:
        return self

    def maybe_single(self) -> FakeOutboxTable:
        return self

    def execute(self) -> MagicMock:
        if self._pending is None:
            return MagicMock(data=None)
        row = self._pending
        if any(existing["dedupe_key"] == row["dedupe_key"] for existing in self._store):
            raise APIError({"code": "23505", "message": "duplicate key"})
        self._store.append(row)
        return MagicMock(data=[row])


class FakeOutboxClient:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, _name: str) -> FakeOutboxTable:
        return FakeOutboxTable(self.rows)


@pytest.mark.usefixtures("flag_on")
class TestNotifyCourierDb:
    def test_whatsapp_notify_enqueues_template_with_cod(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        outbox = FakeOutboxClient()
        result = dispatch_service.notify_courier(
            outbox, dispatch_id=dispatch_id, channel="whatsapp"
        )
        assert result.enqueued is True
        assert result.notify_count == 1
        [row] = outbox.rows
        assert row["channel"] == "whatsapp"
        assert row["template"] == "courier_dispatch_request"
        assert row["status"] == "pending"
        assert row["dedupe_key"] == f"courier_dispatch_request:{dispatch_id}:1:whatsapp"
        payload = row["payload"]
        assert payload["to"] == "+260977000001"
        assert payload["cod_amount_ngwee"] == COD_TOTAL_NGWEE
        assert isinstance(payload["cod_amount_ngwee"], int)
        assert payload["cod_line"] == "Collect cash on delivery: K1,050.50"
        assert "Opposite Woodlands Total" in payload["dropoff_line"]
        assert "maps.google.com" in payload["dropoff_line"]
        assert "+260972222222" in payload["contacts_line"]
        assert "2 x Samsung A15 128GB" in payload["items_line"]
        assert "code" not in " ".join(k for k in payload if k != "dispatch_message")
        assert _handover_code(db, dispatch_id) not in payload["dispatch_message"]
        render_whatsapp_template(row["template"], payload)

    def test_renotify_and_email_get_distinct_rows(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        outbox = FakeOutboxClient()
        dispatch_service.notify_courier(outbox, dispatch_id=dispatch_id, channel="whatsapp")
        second = dispatch_service.notify_courier(outbox, dispatch_id=dispatch_id, channel="email")
        assert second.notify_count == 2
        assert [row["channel"] for row in outbox.rows] == ["whatsapp", "email"]
        assert outbox.rows[1]["payload"]["email"] == "ops@courier.test"
        assert fetch_dispatch(dispatch_id).notify_count == 2

    def test_notify_refused_after_pickup(self, db: PgConn) -> None:
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        with pytest.raises(AppError) as exc:
            dispatch_service.notify_courier(
                FakeOutboxClient(), dispatch_id=dispatch_id, channel="whatsapp"
            )
        assert exc.value.http_status == 409

    def test_stale_tick_alerts_founder_once(self, db: PgConn) -> None:
        from app.routers import internal_n8n

        _order_id, _courier, dispatch_id = _create(db)
        _sql_ok(
            db,
            "UPDATE public.dispatch_requests SET requested_at = now() - interval '50 minutes' "
            f"WHERE id = '{dispatch_id}';",
        )
        outbox = FakeOutboxClient()
        wrapper = MagicMock()
        wrapper.client = outbox
        items = internal_n8n.fetch_stale_dispatches(wrapper)
        mine = [item for item in items if item["dispatch_id"] == dispatch_id]
        assert len(mine) == 1 and mine[0]["minutes_waiting"] >= 49
        enqueued, _ = internal_n8n._enqueue_items(
            wrapper,
            event_type="dispatch_stale_alert",
            template="dispatch_stale_alert",
            items=mine,
            entity_key="dispatch_id",
        )
        again, skipped = internal_n8n._enqueue_items(
            wrapper,
            event_type="dispatch_stale_alert",
            template="dispatch_stale_alert",
            items=mine,
            entity_key="dispatch_id",
        )
        assert (enqueued, again, skipped) == (1, 0, 1)
        render_whatsapp_template("dispatch_stale_alert", outbox.rows[0]["payload"])

    def test_stale_tick_silent_when_flag_off(self, db: PgConn) -> None:
        from app.routers import internal_n8n

        _set_flag(db, False)
        wrapper = MagicMock()
        wrapper.client = FakeOutboxClient()
        assert internal_n8n.fetch_stale_dispatches(wrapper) == []


# ---------------------------------------------------------------------------
# HTTP authz
# ---------------------------------------------------------------------------


@pytest.fixture
def http(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, dict[str, str]], None, None]:
    who: dict[str, str] = {"user": CUSTOMER_ID}
    roles = {
        CUSTOMER_ID: frozenset({"customer"}),
        OTHER_CUSTOMER_ID: frozenset({"customer"}),
        VENDOR_A_OWNER: frozenset({"vendor"}),
        VENDOR_B_OWNER: frozenset({"vendor"}),
        ADMIN_ID: frozenset({"admin"}),
    }
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": who["user"], "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: roles.get(uid, frozenset()),
    )
    audit_client = MagicMock()
    audit_client.client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "audit-0001"}]
    )
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: audit_client)
    monkeypatch.setattr("app.routers.admin_dispatch.bump_rate_counter", lambda **_kwargs: (True, 0))
    wrapper = MagicMock()
    wrapper.client = FakeOutboxClient()
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: wrapper
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, who


@pytest.mark.usefixtures("flag_on")
class TestDeliveryAuthzHttp:
    def test_owner_sees_code_other_customer_gets_404(
        self, db: PgConn, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        order_id, _courier, dispatch_id = _create(db)
        code = _handover_code(db, dispatch_id)

        who["user"] = CUSTOMER_ID
        own = client.get(f"/account/orders/{order_id}/delivery", headers=AUTH)
        assert own.status_code == 200, own.text
        body = own.json()
        assert body["enabled"] is True
        assert body["dispatch"]["handover_code"] == code
        assert body["dispatch"]["status"] == "requested"
        assert body["dispatch"]["cod_amount_ngwee"] == COD_TOTAL_NGWEE

        who["user"] = OTHER_CUSTOMER_ID
        other = client.get(f"/account/orders/{order_id}/delivery", headers=AUTH)
        assert other.status_code == 404
        assert code not in other.text

        missing = client.get(f"/account/orders/{uuid.uuid4()}/delivery", headers=AUTH)
        assert missing.status_code == 404
        assert other.json()["error"]["code"] == missing.json()["error"]["code"]

    def test_code_hidden_after_delivery(
        self, db: PgConn, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        dispatch_service.verify_handover_code(
            dispatch_id=dispatch_id, code=_handover_code(db, dispatch_id), actor_id=ADMIN_ID
        )
        who["user"] = CUSTOMER_ID
        body = client.get(f"/account/orders/{order_id}/delivery", headers=AUTH).json()
        assert body["dispatch"]["status"] == "delivered"
        assert body["dispatch"]["handover_code"] is None
        assert [step["status"] for step in body["dispatch"]["timeline"]] == [
            "requested",
            "accepted",
            "picked_up",
            "delivered",
        ]

    def test_vendor_sees_courier_never_code(
        self, db: PgConn, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        order_id, _courier, dispatch_id = _create(db)
        code = _handover_code(db, dispatch_id)
        who["user"] = VENDOR_A_OWNER
        own = client.get(f"/vendor/orders/{order_id}/delivery", headers=AUTH)
        assert own.status_code == 200, own.text
        assert "handover_code" not in own.json()["dispatch"]
        assert code not in own.text
        assert own.json()["dispatch"]["courier_name"].startswith("Courier ")

        who["user"] = VENDOR_B_OWNER
        assert client.get(f"/vendor/orders/{order_id}/delivery", headers=AUTH).status_code == 404

    @pytest.mark.parametrize("user", [VENDOR_A_OWNER, CUSTOMER_ID])
    def test_non_admins_cannot_assign_or_verify(
        self, db: PgConn, http: tuple[TestClient, dict[str, str]], user: str
    ) -> None:
        client, who = http
        order_id = _make_order(db)
        courier_id = _make_courier(db)
        who["user"] = user
        assign = client.post(
            "/admin/dispatch/requests",
            json={"order_id": order_id, "courier_partner_id": courier_id},
            headers=AUTH,
        )
        assert assign.status_code == 403
        assert _sql_ok(
            db, f"SELECT count(*) FROM public.dispatch_requests WHERE order_id = '{order_id}';"
        ) == ["0"]
        couriers = client.post(
            "/admin/dispatch/couriers",
            json={"name": "Rogue", "contact_email": "rogue@x.test"},
            headers=AUTH,
        )
        assert couriers.status_code == 403
        board = client.get("/admin/dispatch/board", headers=AUTH)
        assert board.status_code == 403
        handover = client.post(
            f"/admin/dispatch/requests/{uuid.uuid4()}/handover",
            json={"code": "123456"},
            headers=AUTH,
        )
        assert handover.status_code == 403

    def test_admin_end_to_end_over_http(
        self, db: PgConn, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        who["user"] = ADMIN_ID
        created = client.post(
            "/admin/dispatch/couriers",
            json={
                "name": f"TownStar {uuid.uuid4().hex[:6]}",
                "contact_whatsapp_e164": "+260977123456",
                "zones": [{"zone_key": "lusaka_a", "price_ngwee": 2_500}],
            },
            headers=AUTH,
        )
        assert created.status_code == 201, created.text
        courier_id = created.json()["id"]
        order_id = _make_order(db)

        board = client.get("/admin/dispatch/board", headers=AUTH)
        assert board.status_code == 200
        assert any(row["order_id"] == order_id for row in board.json()["ready_orders"])

        dispatch = client.post(
            "/admin/dispatch/requests",
            json={"order_id": order_id, "courier_partner_id": courier_id},
            headers=AUTH,
        )
        assert dispatch.status_code == 201, dispatch.text
        dispatch_id = dispatch.json()["id"]
        assert dispatch.json()["quoted_price_ngwee"] == 2_500
        assert "handover_code" not in dispatch.text

        message = client.get(f"/admin/dispatch/requests/{dispatch_id}/message", headers=AUTH)
        assert message.status_code == 200
        assert "K1,050.50" in message.json()["text"]

        notify = client.post(
            f"/admin/dispatch/requests/{dispatch_id}/notify",
            json={"channel": "whatsapp"},
            headers=AUTH,
        )
        assert notify.status_code == 200, notify.text
        assert notify.json()["enqueued"] is True

        for status in ("accepted", "picked_up"):
            moved = client.post(
                f"/admin/dispatch/requests/{dispatch_id}/transition",
                json={"to_status": status},
                headers=AUTH,
            )
            assert moved.status_code == 200, moved.text

        wrong = client.post(
            f"/admin/dispatch/requests/{dispatch_id}/handover",
            json={"code": _wrong_code(_handover_code(db, dispatch_id))},
            headers=AUTH,
        )
        assert wrong.status_code == 422
        assert wrong.json()["error"]["details"]["attempts_remaining"] == 4

        ok = client.post(
            f"/admin/dispatch/requests/{dispatch_id}/handover",
            json={"code": _handover_code(db, dispatch_id)},
            headers=AUTH,
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["order_status"] == "delivered"
        assert ok.json()["dispatch"]["status"] == "delivered"

    def test_api_integration_kind_is_reserved(
        self, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        client, who = http
        who["user"] = ADMIN_ID
        response = client.post(
            "/admin/dispatch/couriers",
            json={
                "name": "Yango API",
                "contact_email": "api@yango.test",
                "integration_kind": "api",
            },
            headers=AUTH,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "courier_integration_reserved"

    def test_handover_endpoint_rate_limited(
        self,
        db: PgConn,
        http: tuple[TestClient, dict[str, str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client, who = http
        who["user"] = ADMIN_ID
        calls: list[dict[str, Any]] = []

        def limited(**kwargs: Any) -> tuple[bool, int]:
            calls.append(kwargs)
            return False, 30

        monkeypatch.setattr("app.routers.admin_dispatch.bump_rate_counter", limited)
        _order_id, _courier, dispatch_id = _create(db)
        _advance_to_picked_up(dispatch_id)
        response = client.post(
            f"/admin/dispatch/requests/{dispatch_id}/handover",
            json={"code": _handover_code(db, dispatch_id)},
            headers=AUTH,
        )
        assert response.status_code == 429
        assert calls and calls[0]["scope"] == "write_sensitive"
        assert calls[0]["key"] == f"dispatch_handover:{ADMIN_ID}"
        assert fetch_dispatch(dispatch_id).status is DispatchStatus.PICKED_UP


class TestFlagOffHttp:
    def test_flag_off_blocks_dispatch_and_hides_party_views(
        self, db: PgConn, db_url_env: None, http: tuple[TestClient, dict[str, str]]
    ) -> None:
        _set_flag(db, False)
        client, who = http
        order_id = _make_order(db)
        courier_id = _make_courier(db)
        who["user"] = ADMIN_ID
        response = client.post(
            "/admin/dispatch/requests",
            json={"order_id": order_id, "courier_partner_id": courier_id},
            headers=AUTH,
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "feature_disabled"
        assert client.get("/admin/dispatch/board", headers=AUTH).json()["flag_enabled"] is False

        who["user"] = CUSTOMER_ID
        body = client.get(f"/account/orders/{order_id}/delivery", headers=AUTH).json()
        assert body == {"enabled": False, "dispatch": None}
