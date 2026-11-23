"""Disposable-Postgres contract tests for the Web Push delivery queue (20261113140000).

Reuses the in-app notification DB fixture (``IN_APP_NOTIF_TEST_DATABASE_URL``);
skipped without it. Every case runs in a rolled-back transaction.
"""

from __future__ import annotations

from tests.rls.conftest import PgConn
from tests.test_in_app_notifications_db import CUSTOMER_A, CUSTOMER_B, _as, _tx
from tests.test_in_app_notifications_db import db as in_app_db

db = in_app_db  # re-export the module-scoped disposable-DB fixture

_NEW_NOTIFICATION = f"""
INSERT INTO public.in_app_notifications
  (recipient_user_id, audience, type, i18n_key, params, link_path, dedupe_key)
VALUES
  ('{CUSTOMER_A}', 'customer', 'order_packed', 'notifications.inApp.customer.order_packed',
   '{{"ref":"AAAA1111"}}', '/account/orders/z', 'push-test:a'),
  ('{CUSTOMER_A}', 'vendor', 'rfq_received', 'notifications.inApp.vendor.rfq_received',
   '{{}}', '/rfq', 'push-test:vendor'),
  ('{CUSTOMER_B}', 'customer', 'order_packed', 'notifications.inApp.customer.order_packed',
   '{{"ref":"BBBB1111"}}', '/account/orders/w', 'push-test:b');
"""
_COUNT = "SELECT count(*)::text FROM public.web_push_deliveries;"
_FLAG_ON = "UPDATE public.feature_flags SET enabled = true WHERE flag = 'web_push';"


def test_flag_off_queues_nothing(db: PgConn) -> None:
    assert _tx(db, _NEW_NOTIFICATION + _COUNT)[-1] == "0"


def test_flag_on_queues_one_row_per_matching_subscription(db: PgConn) -> None:
    rows = _tx(
        db,
        _FLAG_ON
        + _NEW_NOTIFICATION
        + """
        SELECT d.recipient_user_id || '|' || n.audience || '|' || d.status || '|' || d.attempts
        FROM public.web_push_deliveries d
        JOIN public.in_app_notifications n ON n.id = d.notification_id;
        """,
    )
    # Only customer A has a (customer-audience) subscription.
    assert [r for r in rows if "|" in r] == [f"{CUSTOMER_A}|customer|pending|0"]


def test_queue_is_unique_per_notification_and_subscription(db: PgConn) -> None:
    rows = _tx(
        db,
        _FLAG_ON
        + _NEW_NOTIFICATION
        + """
        INSERT INTO public.web_push_deliveries (notification_id, subscription_id, recipient_user_id)
        SELECT notification_id, subscription_id, recipient_user_id FROM public.web_push_deliveries
        ON CONFLICT (notification_id, subscription_id) DO NOTHING;
        """
        + _COUNT,
    )
    assert rows[-1] == "1"


def test_deleting_a_subscription_cascades_its_queue(db: PgConn) -> None:
    rows = _tx(
        db,
        _FLAG_ON + _NEW_NOTIFICATION + "DELETE FROM public.web_push_subscriptions;" + _COUNT,
    )
    assert rows[-1] == "0"


def test_queue_is_invisible_to_clients(db: PgConn) -> None:
    ok, rows, error = _as(db, CUSTOMER_A, "SELECT count(*) FROM public.web_push_deliveries;")
    assert not ok and "permission denied" in (error or "").lower(), (rows, error)
