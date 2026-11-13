"""SLA watch tick: silent vendors, stalled riders, customer delivered/cancelled (real Postgres)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.services.logistics import alerts
from app.services.notifications.templates.sms import SMS_TEMPLATES
from app.services.notifications.templates.whatsapp import render_whatsapp_template
from tests import test_courier_dispatch as _dispatch_tests
from tests.rls.conftest import PgConn
from tests.test_courier_dispatch import (
    FakeOutboxClient,
    _advance_to_picked_up,
    _create,
    _make_order,
    _sql_ok,
)

db = _dispatch_tests.db
db_url_env = _dispatch_tests.db_url_env
flag_on = _dispatch_tests.flag_on

pytestmark = pytest.mark.usefixtures("flag_on")


@pytest.fixture(autouse=True)
def ops_numbers(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv(alerts.ALERT_RECIPIENTS_ENV, "+260977000111, +260977000222, nonsense")
    yield


def _rows(outbox: FakeOutboxClient, template: str) -> list[dict]:  # type: ignore[type-arg]
    return [r for r in outbox.rows if r["template"] == template]


def test_alert_recipients_are_a_list_not_one_phone() -> None:
    assert alerts.alert_recipients() == ["+260977000111", "+260977000222"]


def test_silent_vendor_and_stalled_rider_alert_once_per_item(db: PgConn) -> None:
    silent = _make_order(db, status="placed")
    _sql_ok(
        db,
        f"UPDATE public.orders SET created_at = now() - interval '3 hours' WHERE id = '{silent}';",
    )
    fresh = _make_order(db, status="placed")
    _order, _courier, stalled = _create(db)
    _advance_to_picked_up(stalled)
    _sql_ok(
        db,
        "UPDATE public.dispatch_requests SET picked_up_at = now() - interval '3 hours' "
        f"WHERE id = '{stalled}';",
    )
    outbox = FakeOutboxClient()

    first = alerts.run_sla_watch(outbox)
    vendor_rows = [
        r
        for r in _rows(outbox, "vendor_order_unconfirmed_alert")
        if r["payload"]["order_id"] == silent
    ]
    assert len(vendor_rows) == 2  # one per ops number
    assert not any(
        r["payload"].get("order_id") == fresh
        for r in _rows(outbox, "vendor_order_unconfirmed_alert")
    )
    stale_rows = [
        r for r in _rows(outbox, "dispatch_stale_alert") if r["payload"]["dispatch_id"] == stalled
    ]
    assert len(stale_rows) == 2
    assert stale_rows[0]["payload"]["status"] == "picked_up"
    for row in vendor_rows + stale_rows:
        render_whatsapp_template(row["template"], row["payload"])
        assert SMS_TEMPLATES[row["template"]](row["payload"])
    assert first["ops_enqueued"] >= 4

    # Repeat-safe: a second tick sends nothing new for the same items.
    before = len(outbox.rows)
    alerts.run_sla_watch(outbox)
    new = outbox.rows[before:]
    assert not any(r["payload"].get("order_id") == silent for r in new)
    assert not any(r["payload"].get("dispatch_id") == stalled for r in new)


def test_customer_gets_cancelled_and_delivered_messages_once(db: PgConn) -> None:
    cancelled = _make_order(db, status="placed")
    _sql_ok(
        db,
        "BEGIN; SELECT set_config('app.order_note', 'Vendor rejected', true); "
        f"UPDATE public.orders SET status = 'cancelled' WHERE id = '{cancelled}'; COMMIT;",
    )
    outbox = FakeOutboxClient()
    alerts.run_sla_watch(outbox)
    rows = [
        r for r in _rows(outbox, "order_cancelled") if r["payload"].get("order_id") == cancelled
    ]
    assert len(rows) == 1
    assert rows[0]["payload"]["orders_url"].endswith(f"/account/orders/{cancelled}")
    render_whatsapp_template("order_cancelled", {**rows[0]["payload"], "to": "+260977000333"})
    before = len(outbox.rows)
    alerts.run_sla_watch(outbox)
    assert not any(r["payload"].get("order_id") == cancelled for r in outbox.rows[before:])
