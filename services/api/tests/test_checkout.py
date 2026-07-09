from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.checkout import (
    compute_group_delivery_fee_ngwee,
    resolve_delivery_zone,
)
from app.services.stock.claim import claim_reservation
from app.supabase_client import get_supabase_service_client
from fastapi.testclient import TestClient
from tests.rls.conftest import (
    PgConn,
    apply_migrations,
    resolve_db_url,
    schema_ready,
    seed_matrix_fixtures,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "demo"
CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VALID_TOKEN = "valid-test-token"


def _load_ids() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES_DIR / "ids.json").read_text()))


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


@pytest.fixture
def db_url_env(db: PgConn) -> Generator[None, None, None]:
    import os

    previous = os.environ.get("SUPABASE_DB_URL")
    os.environ["SUPABASE_DB_URL"] = db.dsn
    yield
    if previous is None:
        os.environ.pop("SUPABASE_DB_URL", None)
    else:
        os.environ["SUPABASE_DB_URL"] = previous


def _current_user() -> CurrentUser:
    return CurrentUser(id=CUSTOMER_ID, roles=frozenset({"customer"}), token=VALID_TOKEN)


def _make_client(service_override: object | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _current_user
    if service_override is not None:
        def _override_service() -> Generator[object, None, None]:
            yield service_override

        app.dependency_overrides[get_supabase_client] = _override_service
    return TestClient(app, raise_server_exceptions=False)


def _mock_profile_execute(phone: str | None) -> MagicMock:
    profile_table = MagicMock()
    chain = profile_table.select.return_value.eq.return_value.maybe_single.return_value
    chain.execute.return_value = MagicMock(data={"phone": phone})
    return profile_table


def _mock_cart_tables(
    cart_id: str,
    cart_items: list[dict[str, Any]],
) -> MagicMock:
    mock_client = MagicMock()

    def table_side_effect(name: str) -> MagicMock:
        table = MagicMock()
        if name == "carts":
            carts_chain = (
                table.select.return_value.eq.return_value.eq.return_value.limit.return_value
            )
            carts_chain.execute.return_value = MagicMock(
                data=[{"id": cart_id, "user_id": CUSTOMER_ID, "status": "active"}]
            )
        elif name == "cart_items":
            table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=cart_items
            )
        elif name == "checkout_groups":
            update_chain = MagicMock()
            update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
            table.update.return_value = update_chain
        return table

    mock_client.table.side_effect = table_side_effect
    return mock_client


def _insert_checkout_group(
    conn: PgConn,
    *,
    session_id: str,
    idem_suffix: str,
    status: str,
) -> None:
    conn.run(
        f"""
        INSERT INTO public.checkout_groups (
          id, customer_id, idempotency_key,
          subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
        ) VALUES (
          '{session_id}', '{CUSTOMER_ID}', '{idem_suffix}-{session_id}',
          10000, 0, 10000, '{status}'
        );
        """
    )


def _insert_cart_with_items(
    conn: PgConn,
    *,
    cart_id: str,
    items: list[tuple[str, int, int]],
) -> None:
    conn.run(
        f"""
        INSERT INTO public.carts (id, user_id, status)
        VALUES ('{cart_id}', '{CUSTOMER_ID}', 'active')
        ON CONFLICT (id) DO NOTHING;
        """
    )
    for listing_id, qty, unit_price in items:
        item_id = str(uuid.uuid4())
        conn.run(
            f"""
            INSERT INTO public.cart_items (
              id, cart_id, listing_id, qty, unit_price_ngwee, wholesale
            ) VALUES (
              '{item_id}', '{cart_id}', '{listing_id}', {qty}, {unit_price}, false
            );
            """
        )


def _insert_tracked_listing(
    conn: PgConn,
    *,
    listing_id: str,
    vendor_id: str,
    stock_qty: int,
    price_ngwee: int = 10_000,
) -> None:
    ids = _load_ids()
    conn.run(
        f"""
        INSERT INTO public.vendor_listings (
          id, vendor_id, product_id, price_ngwee, condition, stock_mode, stock_qty, status
        ) VALUES (
          '{listing_id}', '{vendor_id}', '{ids["products"]["phone"]}', {price_ngwee},
          'new', 'tracked', {stock_qty}, 'active'
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def _reservation_count(conn: PgConn, checkout_group_id: str) -> int:
    result = conn.run(
        f"""
        SELECT count(*)::text FROM public.stock_reservations
        WHERE checkout_group_id = '{checkout_group_id}';
        """
    )
    assert result.ok and result.rows
    return int(result.rows[0])


class TestZoneResolution:
    def test_central_lusaka_resolves_band_a(self) -> None:
        assert resolve_delivery_zone(lat=-15.4167, lng=28.2833) == "lusaka_a"

    def test_mid_ring_resolves_band_b(self) -> None:
        assert resolve_delivery_zone(lat=-15.35, lng=28.33) == "lusaka_b"

    def test_outer_ring_resolves_band_c(self) -> None:
        assert resolve_delivery_zone(lat=-15.28, lng=28.40) == "lusaka_c"

    def test_outside_zones_returns_none_pickup_only(self) -> None:
        assert resolve_delivery_zone(lat=-12.97, lng=28.63) is None
        assert resolve_delivery_zone(lat=None, lng=None, landmark="Ndola city centre") is None

    def test_landmark_fallback_for_lusaka(self) -> None:
        zone = resolve_delivery_zone(
            lat=None,
            lng=None,
            landmark="East Park Mall, Lusaka",
        )
        assert zone == "lusaka_a"


class TestFeeMath:
    def test_band_a_fee_exact(self) -> None:
        fee = compute_group_delivery_fee_ngwee(
            subtotal_ngwee=15_000,
            zone_key="lusaka_a",
            zone_fees={"lusaka_a": 3000, "lusaka_b": 4500, "lusaka_c": 6500},
            free_delivery_threshold_ngwee=20_000,
        )
        assert fee == 3000

    def test_band_b_fee_exact(self) -> None:
        fee = compute_group_delivery_fee_ngwee(
            subtotal_ngwee=15_000,
            zone_key="lusaka_b",
            zone_fees={"lusaka_a": 3000, "lusaka_b": 4500, "lusaka_c": 6500},
            free_delivery_threshold_ngwee=20_000,
        )
        assert fee == 4500

    def test_band_c_fee_exact(self) -> None:
        fee = compute_group_delivery_fee_ngwee(
            subtotal_ngwee=15_000,
            zone_key="lusaka_c",
            zone_fees={"lusaka_a": 3000, "lusaka_b": 4500, "lusaka_c": 6500},
            free_delivery_threshold_ngwee=20_000,
        )
        assert fee == 6500

    def test_free_delivery_at_threshold(self) -> None:
        fee = compute_group_delivery_fee_ngwee(
            subtotal_ngwee=20_000,
            zone_key="lusaka_a",
            zone_fees={"lusaka_a": 3000},
            free_delivery_threshold_ngwee=20_000,
        )
        assert fee == 0

    def test_pickup_has_zero_fee(self) -> None:
        fee = compute_group_delivery_fee_ngwee(
            subtotal_ngwee=50_000,
            zone_key=None,
            zone_fees={"lusaka_a": 3000},
            free_delivery_threshold_ngwee=20_000,
        )
        assert fee == 0


class TestMixedDeliveryPickup:
    def test_mixed_groups_compute_separate_fees(self, db: PgConn, db_url_env: None) -> None:
        listing_a = str(uuid.uuid4())
        listing_b = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_a, vendor_id=VENDOR_A, stock_qty=5)
        _insert_tracked_listing(
            db, listing_id=listing_b, vendor_id=VENDOR_B, stock_qty=5, price_ngwee=25_000
        )

        cart_id = str(uuid.uuid4())
        _insert_cart_with_items(
            db,
            cart_id=cart_id,
            items=[
                (listing_a, 1, 10_000),
                (listing_b, 1, 25_000),
            ],
        )

        session_id = str(uuid.uuid4())
        db.run(
            f"""
            INSERT INTO public.checkout_groups (
              id, customer_id, idempotency_key, subtotal_ngwee, delivery_fee_ngwee, total_ngwee
            ) VALUES (
              '{session_id}', '{CUSTOMER_ID}', 'mixed-{session_id}', 35000, 0, 35000
            );
            """
        )

        cart_items = [
            {
                "id": str(uuid.uuid4()),
                "listing_id": listing_a,
                "qty": 1,
                "unit_price_ngwee": 10_000,
                "wholesale": False,
            },
            {
                "id": str(uuid.uuid4()),
                "listing_id": listing_b,
                "qty": 1,
                "unit_price_ngwee": 25_000,
                "wholesale": False,
            },
        ]

        client = _make_client(get_supabase_service_client())
        with patch("app.routers.checkout.get_user_client") as mock_user_client:
            mock_user_client.return_value = _mock_cart_tables(cart_id, cart_items)

            response = client.post(
                "/checkout/steps/fulfilment",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={
                    "session_id": session_id,
                    "address": {
                        "landmark": "Woodlands Stage 2, Lusaka",
                        "lat": -15.4167,
                        "lng": 28.2833,
                    },
                    "groups": [
                        {"vendor_id": VENDOR_A, "fulfilment": "delivery"},
                        {"vendor_id": VENDOR_B, "fulfilment": "pickup"},
                    ],
                },
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["delivery_fee_ngwee"] == 3000
        assert payload["subtotal_ngwee"] == 35_000
        assert payload["total_ngwee"] == 38_000
        groups = {group["vendor_id"]: group for group in payload["groups"]}
        assert groups[VENDOR_A]["delivery_fee_ngwee"] == 3000
        assert groups[VENDOR_B]["delivery_fee_ngwee"] == 0
        assert groups[VENDOR_B]["fulfilment"] == "pickup"


class TestGuestOtpContactFlow:
    def test_contact_step_requires_phone_for_new_guest(self) -> None:
        service = MagicMock()
        service.client.table.return_value = _mock_profile_execute(None)
        client = _make_client(service)

        missing = client.post(
            "/checkout/steps/contact",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={},
        )
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "checkout.phone_required"

    def test_contact_step_saves_phone_after_otp(self) -> None:
        service = MagicMock()
        profile_table = _mock_profile_execute(None)
        update_chain = MagicMock()
        profile_table.update.return_value.eq.return_value = update_chain
        service.client.table.return_value = profile_table
        client = _make_client(service)

        response = client.post(
            "/checkout/steps/contact",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={"phone": "971000099"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["verified"] is True
        assert payload["phone"] == "+260971000099"
        assert payload["skipped"] is False

    def test_contact_step_skips_for_logged_in_with_phone(self) -> None:
        service = MagicMock()
        service.client.table.return_value = _mock_profile_execute("+260971000001")
        client = _make_client(service)

        response = client.post(
            "/checkout/steps/contact",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            json={},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["skipped"] is True
        assert payload["verified"] is True


class TestReservationClaimOnSessionInit:
    def test_session_init_claims_reservations(self, db: PgConn, db_url_env: None) -> None:
        listing_id = str(uuid.uuid4())
        _insert_tracked_listing(db, listing_id=listing_id, vendor_id=VENDOR_A, stock_qty=3)
        cart_id = str(uuid.uuid4())
        _insert_cart_with_items(db, cart_id=cart_id, items=[(listing_id, 2, 10_000)])

        client = _make_client()
        captured_group_ids: list[str] = []

        def fake_claim(**kwargs: object) -> object:
            group_id = str(kwargs["checkout_group_id"])
            captured_group_ids.append(group_id)
            return claim_reservation(
                listing_id=str(kwargs["listing_id"]),
                checkout_group_id=group_id,
                qty=int(str(kwargs["qty"])),
                ttl_minutes=int(str(kwargs["ttl_minutes"])),
            )

        cart_items = [
            {
                "id": str(uuid.uuid4()),
                "listing_id": listing_id,
                "qty": 2,
                "unit_price_ngwee": 10_000,
                "wholesale": False,
            }
        ]

        with (
            patch("app.routers.checkout.get_user_client") as mock_user_client,
            patch("app.routers.checkout.claim_reservation", side_effect=fake_claim),
        ):
            service = MagicMock()

            def service_table(name: str) -> MagicMock:
                table = MagicMock()
                if name == "checkout_groups":
                    insert_chain = MagicMock()

                    def insert_row(payload: dict[str, object]) -> MagicMock:
                        group_id = str(payload["id"])
                        customer_id = payload["customer_id"]
                        idem = payload["idempotency_key"]
                        subtotal = payload["subtotal_ngwee"]
                        delivery = payload["delivery_fee_ngwee"]
                        total = payload["total_ngwee"]
                        status = payload["status"]
                        db.run(
                            f"""
                            INSERT INTO public.checkout_groups (
                              id, customer_id, idempotency_key,
                              subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status
                            ) VALUES (
                              '{group_id}', '{customer_id}', '{idem}',
                              {subtotal}, {delivery}, {total}, '{status}'
                            );
                            """
                        )
                        return MagicMock(execute=MagicMock(return_value=MagicMock(data=[payload])))

                    insert_chain.insert.side_effect = insert_row
                    table.insert = insert_chain.insert
                elif name == "delivery_zones":
                    table.select.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[
                            {"zone_key": "lusaka_a", "label": "Band A", "fee_ngwee": 3000},
                        ]
                    )
                elif name == "platform_config":
                    config_chain = (
                        table.select.return_value.eq.return_value.maybe_single.return_value
                    )
                    config_chain.execute.return_value = MagicMock(data={"value": 20000})
                elif name == "vendors":
                    table.select.return_value.in_.return_value.execute.return_value = MagicMock(
                        data=[{"id": VENDOR_A, "display_name": "Shop A"}]
                    )
                elif name == "vendor_locations":
                    locations_chain = table.select.return_value.in_.return_value
                    locations_chain.execute.return_value = MagicMock(data=[])
                elif name == "profiles":
                    profile_chain = (
                        table.select.return_value.eq.return_value.maybe_single.return_value
                    )
                    profile_chain.execute.return_value = MagicMock(
                        data={"phone": "+260971000001"}
                    )
                return table

            service.client.table.side_effect = service_table
            mock_user_client.return_value = _mock_cart_tables(cart_id, cart_items)

            client = _make_client(service)
            response = client.post(
                "/checkout/session",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

        assert response.status_code == 200, response.text
        payload = response.json()
        session_id = payload["session_id"]
        assert payload["reservation_ttl_min"] == 15
        assert len(payload["reservations"]) == 1
        assert payload["reservations"][0]["claimed"] is True
        assert session_id in captured_group_ids
        assert _reservation_count(db, session_id) == 1

        overflow = claim_reservation(
            listing_id=listing_id,
            checkout_group_id=str(uuid.uuid4()),
            qty=2,
            ttl_minutes=15,
        )
        assert overflow.claimed is False


class TestExpiryReturnsCartNotice:
    def test_expired_session_status_returns_notice(self, db: PgConn, db_url_env: None) -> None:
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idem_suffix="exp",
            status="expired",
        )

        client = _make_client(get_supabase_service_client())
        response = client.get(
            f"/checkout/session/{session_id}",
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["expired"] is True
        assert payload["redirect_notice_key"] == "checkout.checkout.reservationExpired"

    def test_fulfilment_on_expired_session_returns_410(self, db: PgConn, db_url_env: None) -> None:
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idem_suffix="exp2",
            status="pending",
        )
        db.run(
            f"""
            INSERT INTO public.stock_reservations (
              listing_id, checkout_group_id, qty, expires_at
            ) VALUES (
              '{_load_ids()["listings"]["phone_a"]}', '{session_id}', 1,
              timezone('utc', now()) - interval '1 minute'
            );
            """
        )

        client = _make_client(get_supabase_service_client())
        with patch("app.routers.checkout.get_user_client") as mock_user_client:
            mock_user_client.return_value = MagicMock()

            response = client.post(
                "/checkout/steps/fulfilment",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={
                    "session_id": session_id,
                    "address": {"landmark": "Woodlands"},
                    "groups": [{"vendor_id": VENDOR_A, "fulfilment": "pickup"}],
                },
            )

        assert response.status_code == 410
        error = response.json()["error"]
        assert error["code"] == "checkout.reservation_expired"
        assert error["details"]["redirect_to"] == "cart"
        assert error["details"]["notice_key"] == "checkout.checkout.reservationExpired"

    def test_outside_zone_rejects_delivery(self, db: PgConn, db_url_env: None) -> None:
        session_id = str(uuid.uuid4())
        _insert_checkout_group(
            db,
            session_id=session_id,
            idem_suffix="zone",
            status="pending",
        )
        future = "timezone('utc', now()) + interval '10 minutes'"
        listing_id = _load_ids()["listings"]["phone_a"]
        db.run(
            f"""
            INSERT INTO public.stock_reservations (
              listing_id, checkout_group_id, qty, expires_at
            ) VALUES ('{listing_id}', '{session_id}', 1, {future});
            """
        )

        cart_id = str(uuid.uuid4())
        cart_items = [
            {
                "id": str(uuid.uuid4()),
                "listing_id": listing_id,
                "qty": 1,
                "unit_price_ngwee": 10_000,
                "wholesale": False,
            }
        ]
        client = _make_client(get_supabase_service_client())
        with patch("app.routers.checkout.get_user_client") as mock_user_client:
            mock_user_client.return_value = _mock_cart_tables(cart_id, cart_items)

            response = client.post(
                "/checkout/steps/fulfilment",
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                json={
                    "session_id": session_id,
                    "address": {
                        "landmark": "Ndola city centre",
                        "lat": -12.97,
                        "lng": 28.63,
                    },
                    "groups": [{"vendor_id": VENDOR_A, "fulfilment": "delivery"}],
                },
            )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "checkout.outside_delivery_zone"
