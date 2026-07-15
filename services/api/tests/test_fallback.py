from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import httpx
import pytest
from app.services.notifications.adapters.base import (
    FailureKind,
    NoopAdapter,
    OutboxMessage,
    SendResult,
)
from app.services.notifications.adapters.email import (
    ResendEmailAdapter,
    render_email_html,
)
from app.services.notifications.adapters.sms import (
    AfricasTalkingSmsAdapter,
    gsm7_septet_length,
    truncate_gsm7,
)
from app.services.notifications.dedupe import build_dedupe_key, enqueue_outbox_row
from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.fallback import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    CHANNEL_WHATSAPP,
    UNDELIVERED_FALLBACK_SECONDS,
    DeliveryContext,
    FallbackReason,
    enqueue_fallback_row,
    evaluate_lifecycle_fallback,
    get_channel_adapter,
    log_fallback_decision,
    resolve_fallback_channel,
    resolve_primary_channel,
    undelivered_sla_elapsed,
    whatsapp_attempt_allowed,
)
from app.supabase_client import SupabaseServiceClient


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


@pytest.mark.parametrize(
    ("prefs", "opt_in", "context", "expected_channel", "expected_reason"),
    [
        (
            {"whatsapp": True, "sms": True, "email": True},
            True,
            DeliveryContext(channel=CHANNEL_WHATSAPP),
            CHANNEL_WHATSAPP,
            FallbackReason.PRIMARY,
        ),
        (
            {"whatsapp": False, "sms": True, "email": True},
            True,
            DeliveryContext(channel=CHANNEL_WHATSAPP),
            CHANNEL_SMS,
            FallbackReason.PREF_OVERRIDE,
        ),
        (
            {"whatsapp": True, "sms": True, "email": True},
            False,
            DeliveryContext(channel=CHANNEL_WHATSAPP, whatsapp_opt_in=False),
            CHANNEL_SMS,
            FallbackReason.WHATSAPP_NO_OPT_IN,
        ),
        (
            {"whatsapp": True, "sms": False, "email": True},
            False,
            DeliveryContext(channel=CHANNEL_WHATSAPP, whatsapp_opt_in=False),
            CHANNEL_EMAIL,
            FallbackReason.WHATSAPP_NO_OPT_IN,
        ),
        (
            {"whatsapp": True, "sms": True, "email": True},
            True,
            DeliveryContext(
                channel=CHANNEL_WHATSAPP,
                send_failed=True,
                failure_kind=FailureKind.RETRYABLE,
            ),
            CHANNEL_SMS,
            FallbackReason.WHATSAPP_FAILED,
        ),
        (
            {"whatsapp": True, "sms": True, "email": True},
            True,
            DeliveryContext(
                channel=CHANNEL_WHATSAPP,
                delivery_status="undelivered",
            ),
            CHANNEL_SMS,
            FallbackReason.WHATSAPP_FAILED,
        ),
        (
            {"whatsapp": True, "sms": False, "email": True},
            True,
            DeliveryContext(
                channel=CHANNEL_SMS,
                send_failed=True,
            ),
            CHANNEL_EMAIL,
            FallbackReason.SMS_FAILED,
        ),
    ],
)
def test_chain_decision_matrix(
    prefs: dict[str, bool],
    opt_in: bool,
    context: DeliveryContext,
    expected_channel: str,
    expected_reason: FallbackReason,
) -> None:
    if context.send_failed or context.delivery_status == "undelivered":
        decision = resolve_fallback_channel(context, prefs)
    else:
        decision = resolve_primary_channel(prefs, whatsapp_opt_in=opt_in)
    assert decision.next_channel == expected_channel
    assert decision.reason == expected_reason


def test_sms_only_user_never_gets_whatsapp_attempt() -> None:
    prefs = {"whatsapp": False, "sms": True, "email": False}
    assert not whatsapp_attempt_allowed(prefs, whatsapp_opt_in=True)
    decision = resolve_primary_channel(prefs)
    assert decision.next_channel == CHANNEL_SMS
    assert decision.reason == FallbackReason.PREF_OVERRIDE


@pytest.mark.asyncio
async def test_whatsapp_undelivered_triggers_sms_within_2min_sla(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    sent_at = datetime(2026, 7, 10, 10, 0, tzinfo=UTC)
    tick_at = sent_at + timedelta(seconds=UNDELIVERED_FALLBACK_SECONDS)

    context = DeliveryContext(
        channel=CHANNEL_WHATSAPP,
        delivery_status="sent",
        sent_at=sent_at,
    )
    assert not undelivered_sla_elapsed(sent_at, now=sent_at + timedelta(seconds=119))
    decision_before = resolve_fallback_channel(
        context,
        {"whatsapp": True, "sms": True, "email": True},
        now=sent_at + timedelta(seconds=119),
    )
    assert decision_before.next_channel is None

    decision = resolve_fallback_channel(
        context,
        {"whatsapp": True, "sms": True, "email": True},
        now=tick_at,
    )
    assert decision.next_channel == CHANNEL_SMS
    assert decision.reason == FallbackReason.WHATSAPP_UNDELIVERED_2MIN

    fallback_row = enqueue_fallback_row(
        store,
        event_type="order_confirmed",
        entity_id="ord-sla-1",
        decision=decision,
        template="order_confirmed",
        payload={"recipient_id": "user-1", "phone": "+260971234567"},
        attempts=1,
    )
    assert fallback_row is not None
    assert fallback_row["channel"] == CHANNEL_SMS
    assert "fallback" in fallback_row["payload"]

    stats = await dispatcher.run_batch(now=tick_at)
    assert stats.sent == 1
    sms_messages = [msg for msg in noop.sent if msg.channel == CHANNEL_SMS]
    assert len(sms_messages) == 1
    expected_key = build_dedupe_key("order_confirmed", "ord-sla-1", CHANNEL_SMS)
    assert sms_messages[0].dedupe_key == expected_key


def test_gsm7_truncation_appends_link() -> None:
    body = "A" * 200
    link = "https://vergeo5.com/o/abc"
    truncated, was_truncated = truncate_gsm7(body, link=link)
    assert was_truncated is True
    assert link in truncated
    assert gsm7_septet_length(truncated) <= 160
    assert truncated.endswith(link) or link in truncated


def test_gsm7_short_message_not_truncated() -> None:
    body = "Your Vergeo5 order is ready."
    truncated, was_truncated = truncate_gsm7(body, link="https://vergeo5.com/o/x")
    assert was_truncated is False
    assert truncated == body


@pytest.mark.asyncio
async def test_sms_adapter_truncates_overlength_message() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["message"] = request.content.decode()
        return httpx.Response(
            201,
            json={
                "SMSMessageData": {
                    "Recipients": [{"status": "Success", "number": "+260971234567"}]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = AfricasTalkingSmsAdapter(
        api_key="test-key",
        username="sandbox",
        sender_id="VERGEO5",
        client=client,
    )
    message = OutboxMessage(
        id="msg-1",
        dedupe_key="order:ord-1:sms",
        channel=CHANNEL_SMS,
        template="order_confirmed",
        payload={
            "phone": "+260971234567",
            "body": "X" * 200,
            "link": "https://vergeo5.com/o/ord-1",
        },
    )
    result = await adapter.send(message)
    assert result.success is True
    parsed = parse_qs(captured["message"])
    sent_message = parsed["message"][0]
    assert "https://vergeo5.com/o/ord-1" in sent_message
    assert "…" in sent_message


def test_email_receipt_renders_i18n_keys() -> None:
    subject, html_body, subject_key, body_key = render_email_html(
        "payment_receipt",
        locale="en",
        payload={"order_id": "ord-42", "amount_ngwee": 123456},
    )
    assert "ord-42" in subject
    assert "1234.56" in html_body
    assert subject_key == "notifications.email.receipt.subject"
    assert body_key == "notifications.email.receipt.body"


@pytest.mark.asyncio
async def test_email_adapter_sends_resend_payload() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"id": "email-1"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = ResendEmailAdapter(
        api_key="re_test",
        from_email="notifications@vergeo5.com",
        client=client,
    )
    message = OutboxMessage(
        id="msg-2",
        dedupe_key="payment:pay-1:email",
        channel=CHANNEL_EMAIL,
        template="payment_receipt",
        payload={
            "email": "buyer@example.com",
            "order_id": "ord-99",
            "amount_ngwee": 50000,
        },
    )
    result = await adapter.send(message)
    assert result.success is True
    assert "ord-99" in captured["body"]
    assert "notifications.email.receipt.subject" in captured["body"]


def test_get_channel_adapter_resolves_by_name(noop: NoopAdapter) -> None:
    adapters = {CHANNEL_WHATSAPP: noop, CHANNEL_SMS: noop, CHANNEL_EMAIL: noop}
    assert get_channel_adapter(adapters, CHANNEL_SMS) is noop
    assert get_channel_adapter(adapters, "unknown") is None


def test_log_fallback_decision_emits_structured_log(caplog: pytest.LogCaptureFixture) -> None:
    from app.services.notifications.fallback import FallbackDecision

    decision = FallbackDecision(
        next_channel=CHANNEL_SMS,
        reason=FallbackReason.WHATSAPP_UNDELIVERED_2MIN,
        detail="whatsapp undelivered after 2min SLA",
        from_channel=CHANNEL_WHATSAPP,
    )
    with caplog.at_level("INFO"):
        log_fallback_decision(
            decision,
            outbox_id="out-1",
            entity_id="ord-1",
            event_type="order_confirmed",
            attempts=2,
        )
    assert any("notification fallback decision" in record.message for record in caplog.records)


def test_evaluate_lifecycle_fallback_for_failed_whatsapp() -> None:
    context = DeliveryContext(
        channel=CHANNEL_WHATSAPP,
        send_failed=True,
        failure_kind=FailureKind.RETRYABLE,
    )
    decision = evaluate_lifecycle_fallback(context, {"whatsapp": True, "sms": True, "email": True})
    assert decision.next_channel == CHANNEL_SMS
    assert decision.reason == FallbackReason.WHATSAPP_FAILED


@pytest.mark.asyncio
async def test_forced_whatsapp_failure_enqueues_sms_via_dispatcher_tick(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
    dispatcher: NotificationDispatcher,
) -> None:
    whatsapp_row = enqueue_outbox_row(
        store,
        event_type="order_shipped",
        entity_id="ord-fail-1",
        channel=CHANNEL_WHATSAPP,
        template="order_shipped",
        payload={"recipient_id": "user-2", "phone": "+260971234567"},
    )
    assert whatsapp_row is not None
    store.outbox[whatsapp_row["id"]]["status"] = "failed"
    store.outbox[whatsapp_row["id"]]["attempts"] = 1

    decision = resolve_fallback_channel(
        DeliveryContext(
            channel=CHANNEL_WHATSAPP,
            send_failed=True,
            failure_kind=FailureKind.RETRYABLE,
        ),
        {"whatsapp": True, "sms": True, "email": True},
    )
    sms_row = enqueue_fallback_row(
        store,
        event_type="order_shipped",
        entity_id="ord-fail-1",
        decision=decision,
        template="order_shipped",
        payload={"recipient_id": "user-2", "phone": "+260971234567"},
        attempts=1,
    )
    assert sms_row is not None

    stats = await dispatcher.run_batch()
    assert stats.sent == 1
    assert any(msg.channel == CHANNEL_SMS for msg in noop.sent)


class _AlwaysFailAdapter:
    """ChannelAdapter that always fails — simulates WhatsApp Cloud API unavailable."""

    def __init__(self, failure_kind: FailureKind = FailureKind.PERMANENT) -> None:
        self.failure_kind = failure_kind
        self.calls = 0

    async def send(self, message: OutboxMessage) -> SendResult:
        self.calls += 1
        return SendResult(success=False, failure_kind=self.failure_kind, message="forced failure")


@pytest.mark.asyncio
async def test_dispatcher_auto_enqueues_sms_fallback_on_whatsapp_failure(
    store: InMemoryOutboxStore,
    noop: NoopAdapter,
) -> None:
    # The dispatcher itself must fail a WhatsApp send OVER to SMS (not just dead-letter
    # it). This is the wiring that was missing: fallback.py existed but nothing invoked it.
    store.profiles["user-9"] = {
        "id": "user-9",
        "phone": "+260970000000",
        "locale": "en",
        "notif_prefs": {},
    }
    whatsapp_row = enqueue_outbox_row(
        store,
        event_type="order_confirmed",
        entity_id="ord-9",
        channel=CHANNEL_WHATSAPP,
        template="order_confirmed",
        payload={"recipient_id": "user-9", "order_reference": "ord-9", "total_ngwee": 150000},
    )
    assert whatsapp_row is not None

    service = SupabaseServiceClient(MagicMock())
    service._client = store  # type: ignore[assignment]
    dispatcher = NotificationDispatcher(
        service,
        {"whatsapp": _AlwaysFailAdapter(FailureKind.PERMANENT), "sms": noop, "email": noop},
        max_attempts=1,
        channel_pace_seconds={"whatsapp": 0, "sms": 0, "email": 0},
    )

    await dispatcher.run_batch()

    rows = list(store.outbox.values())
    whatsapp = next(row for row in rows if row["channel"] == CHANNEL_WHATSAPP)
    assert whatsapp["status"] == "failed"
    sms_rows = [row for row in rows if row["channel"] == CHANNEL_SMS]
    assert len(sms_rows) == 1
    sms = sms_rows[0]
    assert sms["dedupe_key"] == build_dedupe_key("order_confirmed", "ord-9", CHANNEL_SMS)
    assert sms["template"] == "order_confirmed"
    assert sms["status"] == "pending"
    assert sms["payload"]["order_reference"] == "ord-9"
    assert sms["payload"]["phone"] == "+260970000000"  # recipient contact carried over
    assert "fallback" in sms["payload"]  # audit trail attached

    # A second tick delivers the SMS fallback row via the (noop) SMS adapter.
    stats = await dispatcher.run_batch()
    assert stats.sent == 1
    assert any(msg.channel == CHANNEL_SMS for msg in noop.sent)


def test_render_sms_body_covers_lifecycle_templates() -> None:
    from app.services.notifications.templates.sms import SMS_TEMPLATES, render_sms_body

    payload = {
        "order_reference": "ord-77",
        "total_ngwee": 150000,
        "amount_ngwee": 150000,
        "tracking_info": "Yango driver arriving 4pm",
        "pickup_details": "Kamwala stand 12",
        "product_title": "Samsung A15",
        "quantity": 2,
        "category": "plumbing",
        "service_area": "Lusaka",
        "description_preview": "Fix a burst pipe",
    }
    for template in SMS_TEMPLATES:
        body = render_sms_body(template, payload)
        assert body is not None
        assert body.startswith("Vergeo5")
    assert "ord-77" in (render_sms_body("order_confirmed", payload) or "")
    assert "K1500.00" in (render_sms_body("payment_received", payload) or "")
    assert render_sms_body("unknown_template", payload) is None
    assert render_sms_body(None, payload) is None


def test_email_renders_lifecycle_templates_with_order_reference() -> None:
    subject, html_body, _subject_key, _body_key = render_email_html(
        "order_confirmed",
        locale="en",
        payload={"order_reference": "ord-88", "total_ngwee": 250000},
    )
    assert "ord-88" in subject
    assert "ord-88" in html_body
    assert "K2500.00" in html_body

    rfq_subject, rfq_body, _sk, _bk = render_email_html(
        "rfq_job_broadcast",
        locale="en",
        payload={
            "category": "catering",
            "service_area": "Ndola",
            "description_preview": "Wedding for 100",
        },
    )
    assert "catering" in rfq_subject
    assert "Ndola" in rfq_body
    assert "Wedding for 100" in rfq_body
