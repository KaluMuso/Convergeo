from __future__ import annotations

import copy
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.notifications.adapters.base import FailureKind, NoopAdapter, SendResult
from app.services.notifications.dedupe import (
    build_dedupe_key,
    enqueue_outbox_row,
    is_pending_dispatch,
)
from app.services.notifications.dispatcher import (
    NotificationDispatcher,
    compute_backoff_seconds,
    resolve_channel,
)
from app.supabase_client import SupabaseServiceClient
from fastapi.testclient import TestClient


class _FakeQuery:
    def __init__(self, store: InMemoryOutboxStore, table: str) -> None:
        self._store = store
        self._table = table
        self._operation = "select"
        self._filters: list[tuple[str, str, Any]] = []
        self._or_filter: str | None = None
        self._order: str | None = None
        self._limit: int | None = None
        self._payload: dict[str, Any] | None = None
        self._single = False

    def select(self, *_columns: str) -> _FakeQuery:
        self._operation = "select"
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> _FakeQuery:
        self._operation = "insert"
        if isinstance(payload, list):
            self._payload = payload[0]
        else:
            self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        self._operation = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def or_(self, expression: str) -> _FakeQuery:
        self._or_filter = expression
        return self

    def order(self, column: str) -> _FakeQuery:
        self._order = column
        return self

    def limit(self, value: int) -> _FakeQuery:
        self._limit = value
        return self

    def maybe_single(self) -> _FakeQuery:
        self._single = True
        return self

    def execute(self) -> MagicMock:
        if self._table == "notification_outbox":
            if self._operation == "insert":
                assert self._payload is not None
                row = self._store.insert_outbox(self._payload)
                return MagicMock(data=[row] if row else None)
            if self._operation == "update":
                assert self._payload is not None
                updated = self._store.update_outbox(self._filters, self._payload)
                return MagicMock(data=updated)
            rows = self._store.select_outbox(
                filters=self._filters,
                or_filter=self._or_filter,
                order=self._order,
                limit=self._limit,
                single=self._single,
            )
            if self._single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)

        if self._table == "profiles":
            rows = self._store.select_profiles(self._filters, single=self._single)
            if self._single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)

        raise AssertionError(f"Unexpected table: {self._table}")


class InMemoryOutboxStore:
    def __init__(self) -> None:
        self.outbox: dict[str, dict[str, Any]] = {}
        self.profiles: dict[str, dict[str, Any]] = {}
        self.user_emails: dict[str, str] = {}
        self.last_pending_query: dict[str, Any] | None = None
        # Mirror the supabase client's auth.admin surface used by lookup_user_email.
        self.auth = SimpleNamespace(
            admin=SimpleNamespace(get_user_by_id=self._get_user_by_id)
        )

    def _get_user_by_id(self, user_id: str) -> SimpleNamespace:
        email = self.user_emails.get(user_id)
        return SimpleNamespace(user=SimpleNamespace(email=email) if email is not None else None)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)

    def insert_outbox(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        dedupe_key = payload["dedupe_key"]
        if any(row["dedupe_key"] == dedupe_key for row in self.outbox.values()):
            return None
        row_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        row = {
            "id": row_id,
            "dedupe_key": dedupe_key,
            "channel": payload["channel"],
            "template": payload.get("template"),
            "payload": copy.deepcopy(payload.get("payload", {})),
            "status": payload.get("status", "pending"),
            "attempts": payload.get("attempts", 0),
            "next_retry_at": payload.get("next_retry_at"),
            "created_at": now,
            "updated_at": now,
        }
        self.outbox[row_id] = row
        return copy.deepcopy(row)

    def update_outbox(
        self,
        filters: list[tuple[str, str, Any]],
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for _row_id, row in self.outbox.items():
            if not self._matches(row, filters):
                continue
            row.update(copy.deepcopy(payload))
            row["updated_at"] = datetime.now(UTC).isoformat()
            updated.append(copy.deepcopy(row))
        return updated

    def select_outbox(
        self,
        *,
        filters: list[tuple[str, str, Any]],
        or_filter: str | None,
        order: str | None,
        limit: int | None,
        single: bool,
    ) -> list[dict[str, Any]]:
        if or_filter is not None:
            self.last_pending_query = {
                "filters": list(filters),
                "or_filter": or_filter,
                "order": order,
                "limit": limit,
            }

        rows = [copy.deepcopy(row) for row in self.outbox.values() if self._matches(row, filters)]
        if or_filter is not None:
            now_iso = or_filter.split("next_retry_at.lte.")[-1]
            now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            rows = [
                row
                for row in rows
                if row.get("next_retry_at") is None
                or _parse_ts(row["next_retry_at"]) <= now
            ]

        if order:
            rows.sort(key=lambda row: row.get(order) or "")

        if limit is not None:
            rows = rows[:limit]

        if single:
            return rows[:1]
        return rows

    def select_profiles(
        self,
        filters: list[tuple[str, str, Any]],
        *,
        single: bool,
    ) -> list[dict[str, Any]]:
        rows = [
            copy.deepcopy(row)
            for row in self.profiles.values()
            if self._matches({"id": row["id"], **row}, filters)
        ]
        if single:
            return rows[:1]
        return rows

    @staticmethod
    def _matches(row: dict[str, Any], filters: list[tuple[str, str, Any]]) -> bool:
        for op, column, value in filters:
            if op != "eq":
                raise AssertionError(f"Unsupported filter op: {op}")
            if row.get(column) != value:
                return False
        return True


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@pytest.fixture
def store() -> InMemoryOutboxStore:
    return InMemoryOutboxStore()


@pytest.fixture
def noop() -> NoopAdapter:
    return NoopAdapter()


@pytest.fixture
def dispatcher(store: InMemoryOutboxStore, noop: NoopAdapter) -> NotificationDispatcher:
    service = SupabaseServiceClient(MagicMock())
    service._client = store  # type: ignore[assignment]
    return NotificationDispatcher(
        service,
        {"whatsapp": noop, "sms": noop, "email": noop},
        batch_size=10,
        max_attempts=3,
        backoff_base_seconds=60,
        channel_pace_seconds={"whatsapp": 0, "sms": 0, "email": 0},
    )


def _seed_row(
    store: InMemoryOutboxStore,
    *,
    event_type: str,
    entity_id: str,
    channel: str = "whatsapp",
    payload: dict[str, Any] | None = None,
    attempts: int = 0,
    next_retry_at: str | None = None,
) -> dict[str, Any]:
    row = enqueue_outbox_row(
        store,
        event_type=event_type,
        entity_id=entity_id,
        channel=channel,
        template="order_confirmed",
        payload=payload or {"recipient_id": "user-1", "entity_id": entity_id},
    )
    assert row is not None
    row_id = row["id"]
    store.outbox[row_id]["attempts"] = attempts
    store.outbox[row_id]["next_retry_at"] = next_retry_at
    return store.outbox[row_id]


@pytest.mark.asyncio
async def test_crash_mid_batch_replay_no_double_send(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    _seed_row(store, event_type="order_confirmed", entity_id="ord-1")
    _seed_row(store, event_type="order_confirmed", entity_id="ord-2")
    _seed_row(store, event_type="order_confirmed", entity_id="ord-3")

    original_mark_sent = dispatcher.mark_sent
    sent_count = 0

    def crash_after_two(row_id: str) -> bool:
        nonlocal sent_count
        result = original_mark_sent(row_id)
        if result:
            sent_count += 1
            if sent_count == 2:
                raise RuntimeError("crash mid-batch")
        return result

    dispatcher.mark_sent = crash_after_two  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="crash mid-batch"):
        await dispatcher.run_batch()

    assert len(noop.sent) == 2
    sent_rows = [row for row in store.outbox.values() if row["status"] == "sent"]
    assert len(sent_rows) == 2

    stats = await dispatcher.run_batch()
    assert stats.sent == 1
    assert len(noop.sent) == 3
    dedupe_keys = {message.dedupe_key for message in noop.sent}
    assert len(dedupe_keys) == 3


def test_dedupe_collision_honored(store: InMemoryOutboxStore) -> None:
    first = enqueue_outbox_row(
        store,
        event_type="payment_received",
        entity_id="pay-1",
        channel="whatsapp",
        template="payment_received",
        payload={"recipient_id": "user-1"},
    )
    duplicate = enqueue_outbox_row(
        store,
        event_type="payment_received",
        entity_id="pay-1",
        channel="whatsapp",
        template="payment_received",
        payload={"recipient_id": "user-1"},
    )
    assert first is not None
    assert duplicate is None
    assert len(store.outbox) == 1


def test_build_dedupe_key_format() -> None:
    assert build_dedupe_key("order_confirmed", "ord-99", "sms") == "order_confirmed:ord-99:sms"


@pytest.mark.asyncio
async def test_backoff_schedule_increments_attempts_and_next_retry_at(
    store: InMemoryOutboxStore,
    dispatcher: NotificationDispatcher,
) -> None:
    failing = NoopAdapter(
        failures={
            build_dedupe_key("order_shipped", "ord-7", "whatsapp"): SendResult(
                success=False,
                failure_kind=FailureKind.RETRYABLE,
                message="upstream timeout",
            )
        }
    )
    dispatcher._adapters["whatsapp"] = failing

    row = _seed_row(store, event_type="order_shipped", entity_id="ord-7")
    now = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    stats = await dispatcher.run_batch(now=now)
    assert stats.retried == 1

    updated = store.outbox[row["id"]]
    assert updated["attempts"] == 1
    assert updated["status"] == "pending"
    assert updated["next_retry_at"] == (now + timedelta(seconds=60)).isoformat()

    updated["next_retry_at"] = (now - timedelta(seconds=1)).isoformat()
    stats = await dispatcher.run_batch(now=now + timedelta(seconds=120))
    assert stats.retried == 1
    updated = store.outbox[row["id"]]
    assert updated["attempts"] == 2
    assert updated["next_retry_at"] == (now + timedelta(seconds=120 + 120)).isoformat()


def test_compute_backoff_schedule() -> None:
    assert compute_backoff_seconds(1, base_seconds=60) == 60
    assert compute_backoff_seconds(2, base_seconds=60) == 120
    assert compute_backoff_seconds(3, base_seconds=60) == 240


@pytest.mark.asyncio
async def test_permanent_failure_dead_letters_after_max_attempts(
    store: InMemoryOutboxStore,
    dispatcher: NotificationDispatcher,
) -> None:
    dedupe = build_dedupe_key("order_delivered", "ord-9", "whatsapp")
    failing = NoopAdapter(
        failures={
            dedupe: SendResult(
                success=False,
                failure_kind=FailureKind.RETRYABLE,
                message="temporary",
            )
        }
    )
    dispatcher._adapters["whatsapp"] = failing
    row = _seed_row(store, event_type="order_delivered", entity_id="ord-9", attempts=2)
    now = datetime(2026, 7, 8, 8, 0, tzinfo=UTC)

    stats = await dispatcher.run_batch(now=now)
    assert stats.failed == 1

    updated = store.outbox[row["id"]]
    assert updated["status"] == "failed"
    assert updated["attempts"] == 3
    assert updated["next_retry_at"] is None


@pytest.mark.asyncio
async def test_permanent_failure_routes_immediately_to_dead_letter(
    store: InMemoryOutboxStore,
    dispatcher: NotificationDispatcher,
) -> None:
    dedupe = build_dedupe_key("kyc_rejected", "kyc-1", "email")
    failing = NoopAdapter(
        failures={
            dedupe: SendResult(
                success=False,
                failure_kind=FailureKind.PERMANENT,
                message="invalid recipient",
            )
        }
    )
    dispatcher._adapters["email"] = failing
    row = _seed_row(store, event_type="kyc_rejected", entity_id="kyc-1", channel="email")

    stats = await dispatcher.run_batch()
    assert stats.failed == 1
    assert store.outbox[row["id"]]["status"] == "failed"
    assert store.outbox[row["id"]]["attempts"] == 1


@pytest.mark.asyncio
async def test_email_channel_injects_recipient_email_from_auth_users(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    """An email row with no address gets the recipient's auth.users email injected."""
    store.user_emails["user-1"] = "buyer@example.com"
    _seed_row(store, event_type="payment_receipt", entity_id="ord-9", channel="email")

    stats = await dispatcher.run_batch()

    assert stats.sent == 1
    assert len(noop.sent) == 1
    assert noop.sent[0].channel == "email"
    assert noop.sent[0].payload["email"] == "buyer@example.com"


@pytest.mark.asyncio
async def test_email_via_prefs_redirect_injects_email(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    """A whatsapp row that prefs redirect to email is still addressed (resolved channel)."""
    store.profiles["user-1"] = {
        "id": "user-1",
        "phone": "+260970000000",
        "notif_prefs": {"whatsapp": False, "sms": False, "email": True},
    }
    store.user_emails["user-1"] = "buyer@example.com"
    _seed_row(store, event_type="order_confirmed", entity_id="ord-10", channel="whatsapp")

    stats = await dispatcher.run_batch()

    assert stats.sent == 1
    assert noop.sent[0].channel == "email"
    assert noop.sent[0].payload["email"] == "buyer@example.com"


@pytest.mark.asyncio
async def test_email_channel_without_resolved_email_still_processes(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    """No auth.users email on file → nothing injected; the whatsapp/sms legs are untouched."""
    _seed_row(store, event_type="payment_receipt", entity_id="ord-11", channel="email")

    stats = await dispatcher.run_batch()

    assert stats.sent == 1
    assert "email" not in noop.sent[0].payload


def test_pending_lookup_uses_status_and_next_retry_at_index(
    store: InMemoryOutboxStore,
    dispatcher: NotificationDispatcher,
) -> None:
    now = datetime(2026, 7, 8, 10, 0, tzinfo=UTC)
    dispatcher.fetch_pending_rows(now=now)

    assert store.last_pending_query is not None
    filters = store.last_pending_query["filters"]
    assert ("eq", "status", "pending") in filters
    or_filter = store.last_pending_query["or_filter"]
    assert or_filter.startswith("next_retry_at.is.null,next_retry_at.lte.")
    assert store.last_pending_query["limit"] == 10


def test_is_pending_dispatch_guard() -> None:
    assert is_pending_dispatch({"status": "pending", "payload": {}})
    assert not is_pending_dispatch({"status": "sent", "payload": {}})
    assert not is_pending_dispatch({"status": "pending", "payload": {"_delivered": True}})


def test_resolve_channel_honors_prefs_and_defaults() -> None:
    assert resolve_channel("whatsapp", None) == "whatsapp"
    assert resolve_channel("whatsapp", {"whatsapp": False, "sms": True}) == "sms"
    assert resolve_channel("email", {"whatsapp": False, "sms": False, "email": False}) == "email"


@pytest.mark.asyncio
async def test_marketing_row_suppressed_when_all_channels_disabled(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    store.profiles["user-1"] = {
        "id": "user-1",
        "phone": "+260970000000",
        "locale": "en",
        "notif_prefs": {"whatsapp": False, "sms": False, "email": False},
    }
    row = enqueue_outbox_row(
        store,
        event_type="review_request",
        entity_id="ord-1",
        channel="whatsapp",
        template="review_request",
        payload={"recipient_id": "user-1"},
    )
    assert row is not None

    now = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    stats = await dispatcher.run_batch(now=now)

    assert stats.skipped == 1
    assert len(noop.sent) == 0
    updated = store.outbox[row["id"]]
    assert updated["status"] == "sent"
    assert updated["payload"]["_suppressed"] is True
    assert updated["payload"]["suppression_reason"] == "marketing_opt_out"


@pytest.mark.asyncio
async def test_transactional_row_still_sends_when_all_channels_disabled(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    store.profiles["user-1"] = {
        "id": "user-1",
        "phone": "+260970000000",
        "locale": "en",
        "notif_prefs": {"whatsapp": False, "sms": False, "email": False},
    }
    row = enqueue_outbox_row(
        store,
        event_type="otp_login",
        entity_id="otp-1",
        channel="whatsapp",
        template="otp_login",
        payload={"recipient_id": "user-1", "otp_code": "123456", "to": "+260970000000"},
    )
    assert row is not None

    stats = await dispatcher.run_batch()

    assert stats.sent == 1
    assert len(noop.sent) == 1


@pytest.mark.asyncio
async def test_marketing_falls_back_to_enabled_channel(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    store.profiles["user-1"] = {
        "id": "user-1",
        "phone": "+260970000000",
        "locale": "en",
        "notif_prefs": {"whatsapp": False, "sms": True, "email": False},
    }
    row = enqueue_outbox_row(
        store,
        event_type="review_request",
        entity_id="ord-2",
        channel="whatsapp",
        template="review_request",
        payload={"recipient_id": "user-1"},
    )
    assert row is not None

    now = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)
    stats = await dispatcher.run_batch(now=now)

    assert stats.sent == 1
    assert noop.sent[0].channel == "sms"


@pytest.fixture
def dispatch_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("INTERNAL_DISPATCH_TOKEN", "test-internal-token")
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_internal_dispatch_requires_token(dispatch_client: TestClient) -> None:
    response = dispatch_client.post("/internal/dispatch/tick")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_internal_dispatch_accepts_valid_token(
    dispatch_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import internal_dispatch as internal_dispatch_module

    async def fake_run_batch(*_args: Any, **_kwargs: Any) -> Any:
        from app.services.notifications.dispatcher import DispatchStats

        return DispatchStats(processed=0, sent=0, failed=0, skipped=0, retried=0)

    monkeypatch.setattr(internal_dispatch_module, "run_dispatch_batch", fake_run_batch)

    response = dispatch_client.post(
        "/internal/dispatch/tick",
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "retried": 0,
    }
