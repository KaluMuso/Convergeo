# ruff: noqa: F811
"""Unpaid PREPAID order auto-cancel sweeper (POST /internal/order-jobs/cancel-unpaid)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from tests.rls.conftest import PgConn
from tests.test_order_jobs import (  # noqa: F401  (fixtures re-exported for this module)
    INTERNAL_TOKEN,
    _insert_order,
    db,
    db_url_env,
    jobs_client,
)

PATH = "/internal/order-jobs/cancel-unpaid"
SET_HOURS = (
    "UPDATE public.platform_config SET value = '{}'::jsonb WHERE key = 'unpaid_order_cancel_hours';"
)
HEADERS = {"X-Internal-Token": INTERNAL_TOKEN}


def _place(db: PgConn, *, age_hours: float, cod: bool = False) -> tuple[str, str]:
    order_id, group_id = str(uuid.uuid4()), str(uuid.uuid4())
    _insert_order(db, order_id=order_id, group_id=group_id, status="placed")
    result = db.run(
        f"UPDATE public.orders SET cod = {str(cod).lower()}, "
        f"created_at = now() - interval '{age_hours} hours' WHERE id = '{order_id}';"
    )
    assert result.ok, result.error
    return order_id, group_id


def _pay(db: PgConn, group_id: str, status: str, raw: str = "{}") -> None:
    result = db.run(
        "INSERT INTO public.payments (checkout_group_id, provider, rail, lenco_reference, "
        f"amount_ngwee, status, raw) VALUES ('{group_id}', 'lenco', 'mtn', "
        f"'pay-{uuid.uuid4().hex}', 200000, '{status}', '{raw}'::jsonb);"
    )
    assert result.ok, result.error


def _status(db: PgConn, order_id: str) -> str:
    result = db.run(f"SELECT status FROM public.orders WHERE id = '{order_id}';")
    assert result.ok and result.rows, result.error
    return result.rows[0]


def _run(client: TestClient) -> dict[str, int]:
    response = client.post(PATH, json={"limit": 200}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body: dict[str, int] = response.json()
    return body


@pytest.fixture(autouse=True)
def _isolate(db: PgConn) -> Iterator[None]:
    """Park leftover placed prepaid orders from other tests so counts are exact."""
    db.run("UPDATE public.orders SET created_at = now() WHERE status = 'placed' AND cod = false;")
    yield


@pytest.mark.usefixtures("db_url_env")
class TestCancelUnpaid:
    def test_requires_token(self, jobs_client: TestClient) -> None:
        assert jobs_client.post(PATH, json={}).status_code == 401

    def test_unpaid_prepaid_at_13h_is_cancelled_with_system_audit(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id, _ = _place(db, age_hours=13)
        body = _run(jobs_client)
        assert body["cancelled"] == 1
        assert _status(db, order_id) == "cancelled"
        event = db.run(
            "SELECT actor::text || '|' || to_status || '|' || coalesce(note, '') "
            f"FROM public.order_events WHERE order_id = '{order_id}' "
            "AND to_status = 'cancelled';"
        )
        assert event.ok and event.rows, event.error
        assert event.rows[0].startswith("00000000-0000-0000-0000-000000000001|cancelled|")
        assert "unpaid after 12h" in event.rows[0]

    def test_unpaid_prepaid_at_11h_is_kept(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id, _ = _place(db, age_hours=11)
        assert _run(jobs_client)["cancelled"] == 0
        assert _status(db, order_id) == "placed"

    def test_cod_is_never_touched(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id, _ = _place(db, age_hours=48, cod=True)
        assert _run(jobs_client)["cancelled"] == 0
        assert _status(db, order_id) == "placed"

    @pytest.mark.parametrize(
        "payment_status", ["initiated", "ussd_pushed", "pay_offline", "success"]
    )
    def test_payment_in_flight_or_paid_is_kept_then_rechecked(
        self,
        db: PgConn,
        jobs_client: TestClient,
        payment_status: str,
    ) -> None:
        order_id, group_id = _place(db, age_hours=14)
        _pay(db, group_id, payment_status)
        assert _run(jobs_client)["cancelled"] == 0
        assert _status(db, order_id) == "placed"
        if payment_status == "success":
            return
        # The attempt dies (expired): the next run picks the order up again.
        db.run(
            f"UPDATE public.payments SET status = 'expired' WHERE checkout_group_id = '{group_id}';"
        )
        assert _run(jobs_client)["cancelled"] == 1
        assert _status(db, order_id) == "cancelled"

    def test_second_run_does_nothing(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id, _ = _place(db, age_hours=20)
        assert _run(jobs_client)["cancelled"] == 1
        again = _run(jobs_client)
        assert again["cancelled"] == 0 and again["scanned"] == 0
        assert _status(db, order_id) == "cancelled"
        events = db.run(
            f"SELECT count(*) FROM public.order_events WHERE order_id = '{order_id}' "
            "AND to_status = 'cancelled';"
        )
        assert events.rows[0] == "1"

    def test_window_is_admin_editable(
        self,
        db: PgConn,
        jobs_client: TestClient,
    ) -> None:
        order_id, _ = _place(db, age_hours=13)
        db.run(SET_HOURS.format(24))
        try:
            assert _run(jobs_client)["cancelled"] == 0
            assert _status(db, order_id) == "placed"
        finally:
            db.run(SET_HOURS.format(12))
        assert _run(jobs_client)["cancelled"] == 1
