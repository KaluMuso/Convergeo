"""Integration: RFQ provider match → outbox → dispatcher → WhatsApp adapter.

This test closes the seam the M11-P02 RFQ broadcaster shares with the shared
notification pipeline. The broadcaster (:func:`app.services.rfq.broadcast.broadcast_job`)
enqueues each matched provider's outbox row with template ``rfq_job_broadcast`` and
**only** a ``recipient_id`` — it deliberately does not carry ``to``/``locale``. The
dispatcher (:class:`NotificationDispatcher`) resolves the provider's phone + locale
from their profile and injects them before the official WhatsApp Cloud API adapter
renders the template registry entry and POSTs the message.

A prior audit found RFQ rows enqueued **without a template** (``template=None``),
which the adapter correctly rejects as a permanent failure — so providers were never
notified. That defect is fixed (template registered + ``recipient_id`` payload); the
unit guard lives in ``test_rfq.py``. What was still missing — and what this module
adds — is an *integration-level* assertion across the full boundary, driving the real
broadcaster, real dedupe/outbox, real dispatcher, real template render, and the real
``WhatsAppAdapter`` over an ``httpx.MockTransport`` so **no real HTTP call** is made.

Acceptance invariants asserted here:

* a successful RFQ acknowledgement yields a *dispatchable* outbox contract — the
  adapter send succeeds and the row is marked ``sent`` (with the localisable template
  language code carried through: ``en`` → ``en``, ``bem`` → ``bem_ZM``);
* a missing/unregistered template fails *deterministically* and permanently with no
  HTTP call;
* provider privacy is preserved — one row per provider, addressed only to that
  provider, and the payload carries no customer contact identifiers;
* opt-out (STOP) is preserved — a provider who disabled WhatsApp in ``notif_prefs``
  is not sent a WhatsApp message; the dispatcher routes past it (WhatsApp only —
  never WAHA).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from app.routers import rfq as rfq_router
from app.services.notifications.adapters.base import FailureKind, NoopAdapter, OutboxMessage
from app.services.notifications.adapters.whatsapp import WhatsAppAdapter
from app.services.notifications.dedupe import enqueue_outbox_row
from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.templates.whatsapp import (
    TemplateRenderError,
    render_whatsapp_template,
)
from app.services.rfq import broadcast as broadcast_service
from app.services.rfq.engagement import ACCEPT_OUTBOX_EVENT, OUTBOX_CHANNEL

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OWNER_A_ID = "33333333-3333-3333-3333-333333333333"
OWNER_B_ID = "44444444-4444-4444-4444-444444444444"
JOB_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
THREAD_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
PHONE_A = "+260971234567"
PHONE_B = "+260979876543"
CUSTOMER_PHONE = "+260955555555"

# A genuinely-unregistered WhatsApp template id — used to prove missing templates
# fail deterministically without any network call.
UNREGISTERED_TEMPLATE = "totally_unregistered_template"


# --------------------------------------------------------------------------- #
# Minimal in-memory Supabase double supporting BOTH the broadcaster's tables   #
# and the dispatcher's outbox/profiles queries (incl. the pending `.or_`).     #
# --------------------------------------------------------------------------- #
class _FakeQuery:
    def __init__(self, table: _FakeTable) -> None:
        self._t = table
        self._eq: list[tuple[str, Any]] = []
        self._in: tuple[str, list[Any]] | None = None
        self._op: str | None = None
        self._payload: Any = None
        self._single = False
        self._order: str | None = None
        self._limit: int | None = None

    def select(self, *_a: Any, **_k: Any) -> _FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> _FakeQuery:
        self._eq.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> _FakeQuery:
        self._in = (column, list(values))
        return self

    def or_(self, _expression: str) -> _FakeQuery:
        # Pending-row OR filter (next_retry_at is null / <= now). A passthrough is
        # faithful here: the dispatcher re-checks next_retry_at per row in
        # _process_row, and freshly-enqueued RFQ rows carry no next_retry_at.
        return self

    def order(self, column: str, *, desc: bool = False) -> _FakeQuery:
        self._order = column
        return self

    def limit(self, count: int) -> _FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> _FakeQuery:
        self._single = True
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> _FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for column, value in self._eq:
            if row.get(column) != value:
                return False
        if self._in is not None:
            column, values = self._in
            if row.get(column) not in values:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted: list[dict[str, Any]] = []
            for item in items:
                row = dict(item)
                row.setdefault("id", str(uuid4()))
                now = datetime.now(UTC).isoformat()
                row.setdefault("created_at", now)
                row.setdefault("updated_at", now)
                self._t.rows.append(row)
                inserted.append(dict(row))
            return MagicMock(data=inserted, count=len(inserted))

        if self._op == "update":
            updated: list[dict[str, Any]] = []
            for row in self._t.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            if self._single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        rows = [dict(row) for row in self._t.rows if self._match(row)]
        if self._order is not None:
            order_column = self._order
            rows.sort(key=lambda row: str(row.get(order_column, "")))
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, *a: Any, **k: Any) -> _FakeQuery:
        return _FakeQuery(self).select(*a, **k)

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> _FakeQuery:
        return _FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self).update(payload)


class _FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {}

    @property
    def client(self) -> _FakeSupabase:
        return self

    def table(self, name: str) -> _FakeTable:
        return self.tables.setdefault(name, _FakeTable())


def _seed_provider(
    fake: _FakeSupabase,
    *,
    vendor_id: str,
    owner_user_id: str,
    display_name: str,
    category: str,
    service_area: str,
    phone: str,
    locale: str = "en",
    notif_prefs: dict[str, Any] | None = None,
    preferred_badge: bool = False,
) -> None:
    fake.table("vendors").rows.append(
        {
            "id": vendor_id,
            "owner_user_id": owner_user_id,
            "display_name": display_name,
            "preferred_badge": preferred_badge,
            "status": "active",
        }
    )
    fake.table("services").rows.append(
        {
            "id": f"service-{vendor_id}",
            "vendor_id": vendor_id,
            "category": category,
            "service_area": service_area,
            "status": "active",
        }
    )
    fake.table("profiles").rows.append(
        {
            "id": owner_user_id,
            "phone": phone,
            "locale": locale,
            "notif_prefs": notif_prefs if notif_prefs is not None else {},
        }
    )


class _CapturingTransport:
    """httpx MockTransport wrapper that records every request; makes no network call."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(
                {
                    "url": str(request.url),
                    "headers": dict(request.headers),
                    "body": json.loads(request.content.decode()),
                }
            )
            return httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})

        return httpx.MockTransport(handler)


def _whatsapp_adapter(capture: _CapturingTransport) -> WhatsAppAdapter:
    # Credentials injected directly so the adapter never reads env or hits the network.
    return WhatsAppAdapter(
        client=httpx.AsyncClient(transport=capture.transport()),
        phone_number_id="PNID-test",
        access_token="tok-test",
        api_version="v23.0",
    )


# --------------------------------------------------------------------------- #
# 1. Happy-path boundary: matched provider → outbox → dispatcher → adapter.    #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected_language_code"),
    [("en", "en"), ("bem", "bem_ZM")],
)
async def test_matched_provider_renders_and_sends_via_whatsapp_adapter(
    locale: str,
    expected_language_code: str,
) -> None:
    fake = _FakeSupabase()
    _seed_provider(
        fake,
        vendor_id=VENDOR_A_ID,
        owner_user_id=OWNER_A_ID,
        display_name="Alpha Plumbing",
        category="home_services",
        service_area="Lusaka",
        phone=PHONE_A,
        locale=locale,
    )

    description = "Fix the kitchen sink tap that keeps leaking"
    result = broadcast_service.broadcast_job(
        fake,
        job_id=JOB_ID,
        customer_id=CUSTOMER_ID,
        category="home_services",
        service_area="Lusaka",
        description=description,
    )
    # The acknowledgement produced a dispatchable outbox contract (not a no-match flag).
    assert result.no_match is False
    assert result.matched_count == 1
    outbox_rows = fake.table("notification_outbox").rows
    assert len(outbox_rows) == 1
    enqueued = outbox_rows[0]
    assert enqueued["template"] == broadcast_service.RFQ_MATCH_TEMPLATE
    assert enqueued["channel"] == "whatsapp"
    # Broadcaster does NOT carry the destination — the dispatcher must resolve it.
    assert "to" not in enqueued["payload"]
    assert "locale" not in enqueued["payload"]
    assert enqueued["payload"]["recipient_id"] == OWNER_A_ID

    capture = _CapturingTransport()
    adapter = _whatsapp_adapter(capture)
    dispatcher = NotificationDispatcher(
        fake,
        {"whatsapp": adapter},
        channel_pace_seconds={"whatsapp": 0.0},
    )
    try:
        stats = await dispatcher.run_batch()
    finally:
        await adapter.client.aclose()  # type: ignore[union-attr]

    # Exactly one message went out over the (mocked) Cloud API — no real HTTP.
    assert stats.sent == 1
    assert len(capture.requests) == 1
    sent = capture.requests[0]
    assert sent["url"] == "https://graph.facebook.com/v23.0/PNID-test/messages"
    assert sent["headers"]["authorization"] == "Bearer tok-test"

    body = sent["body"]
    assert body["messaging_product"] == "whatsapp"
    assert body["to"] == PHONE_A  # dispatcher injected the provider's phone as `to`
    assert body["type"] == "template"
    assert body["template"]["name"] == "rfq_job_broadcast"
    # Localisable template: locale flows through to the Meta language code.
    assert body["template"]["language"] == {"code": expected_language_code}
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert params == ["home_services", "Lusaka", description]

    # The outbox row is terminal-sent (dispatchable contract satisfied).
    assert fake.table("notification_outbox").rows[0]["status"] == "sent"


# --------------------------------------------------------------------------- #
# 2. Thread events resolve the counterparty and dispatch every template.       #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("template", "sender_party", "expected_recipient", "expected_phone", "expected_params"),
    [
        (rfq_router.RFQ_OPENED_TEMPLATE, "customer", OWNER_A_ID, PHONE_A, []),
        (rfq_router.RFQ_REPLY_TEMPLATE, "vendor", CUSTOMER_ID, CUSTOMER_PHONE, []),
        (
            rfq_router.RFQ_QUOTED_TEMPLATE,
            "vendor",
            CUSTOMER_ID,
            CUSTOMER_PHONE,
            ["K2,500.00"],
        ),
    ],
)
async def test_rfq_thread_notification_dispatches_to_counterparty(
    template: str,
    sender_party: rfq_router.Party,
    expected_recipient: str,
    expected_phone: str,
    expected_params: list[str],
) -> None:
    fake = _FakeSupabase()
    _seed_provider(
        fake,
        vendor_id=VENDOR_A_ID,
        owner_user_id=OWNER_A_ID,
        display_name="Alpha Plumbing",
        category="home_services",
        service_area="Lusaka",
        phone=PHONE_A,
    )
    fake.table("profiles").rows.append(
        {
            "id": CUSTOMER_ID,
            "phone": CUSTOMER_PHONE,
            "locale": "en",
            "notif_prefs": {},
        }
    )
    thread = {
        "id": THREAD_ID,
        "customer_id": CUSTOMER_ID,
        "vendor_id": VENDOR_A_ID,
        "listing_id": "listing-1",
        "service_id": None,
        "quote_price_ngwee": 250_000,
    }

    rfq_router._notify_counterparty(
        fake,
        thread=thread,
        party=sender_party,
        template=template,
        message_id=f"message-{template}",
    )

    outbox_rows = fake.table("notification_outbox").rows
    assert len(outbox_rows) == 1
    row = outbox_rows[0]
    assert row["template"] == template
    assert row["payload"]["recipient_id"] == expected_recipient
    assert "to" not in row["payload"]

    capture = _CapturingTransport()
    adapter = _whatsapp_adapter(capture)
    dispatcher = NotificationDispatcher(
        fake,
        {"whatsapp": adapter},
        channel_pace_seconds={"whatsapp": 0.0},
    )
    try:
        stats = await dispatcher.run_batch()
    finally:
        await adapter.client.aclose()  # type: ignore[union-attr]

    assert stats.sent == 1
    assert len(capture.requests) == 1
    body = capture.requests[0]["body"]
    assert body["to"] == expected_phone
    assert body["template"]["name"] == template
    components = body["template"].get("components", [])
    if expected_params:
        assert components
    else:
        assert "components" not in body["template"]
    params = [p["text"] for p in components[0]["parameters"]] if components else []
    assert params == expected_params
    outbound = json.dumps(body)
    assert THREAD_ID not in outbound
    assert CUSTOMER_ID not in outbound
    assert VENDOR_A_ID not in outbound
    assert row["status"] == "sent"


# --------------------------------------------------------------------------- #
# 3. Missing/unregistered template fails deterministically with no HTTP call.  #
# --------------------------------------------------------------------------- #
def test_unregistered_template_render_raises_deterministically() -> None:
    with pytest.raises(TemplateRenderError):
        render_whatsapp_template(
            UNREGISTERED_TEMPLATE,
            {"to": PHONE_A, "locale": "en", "category": "home_services"},
        )


@pytest.mark.asyncio
async def test_adapter_rejects_unregistered_template_without_http() -> None:
    capture = _CapturingTransport()
    adapter = _whatsapp_adapter(capture)
    message = OutboxMessage(
        id="outbox-unregistered",
        dedupe_key=f"{UNREGISTERED_TEMPLATE}:job:whatsapp",
        channel="whatsapp",
        template=UNREGISTERED_TEMPLATE,
        payload={"to": PHONE_A, "locale": "en"},
    )
    try:
        result = await adapter.send(message)
    finally:
        await adapter.client.aclose()  # type: ignore[union-attr]

    assert result.success is False
    assert result.failure_kind == FailureKind.PERMANENT
    # Deterministic local rejection — the transport was never invoked.
    assert capture.requests == []


@pytest.mark.asyncio
async def test_adapter_rejects_templateless_message_without_http() -> None:
    capture = _CapturingTransport()
    adapter = _whatsapp_adapter(capture)
    message = OutboxMessage(
        id="outbox-templateless",
        dedupe_key="rfq_job_broadcast:job:whatsapp",
        channel="whatsapp",
        template=None,
        payload={"to": PHONE_A, "locale": "en", "category": "home_services"},
    )
    try:
        result = await adapter.send(message)
    finally:
        await adapter.client.aclose()  # type: ignore[union-attr]

    assert result.success is False
    assert result.failure_kind == FailureKind.PERMANENT
    assert capture.requests == []


# --------------------------------------------------------------------------- #
# 3. Provider privacy: one row per provider, addressed only to that provider,  #
#    and no customer contact identifier in the broadcast payload.              #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_provider_privacy_one_row_each_no_customer_pii() -> None:
    fake = _FakeSupabase()
    _seed_provider(
        fake,
        vendor_id=VENDOR_A_ID,
        owner_user_id=OWNER_A_ID,
        display_name="Alpha Plumbing",
        category="home_services",
        service_area="Lusaka",
        phone=PHONE_A,
    )
    _seed_provider(
        fake,
        vendor_id=VENDOR_B_ID,
        owner_user_id=OWNER_B_ID,
        display_name="Beta Plumbing",
        category="home_services",
        service_area="Lusaka",
        phone=PHONE_B,
    )

    broadcast_service.broadcast_job(
        fake,
        job_id=JOB_ID,
        customer_id=CUSTOMER_ID,
        category="home_services",
        service_area="Lusaka",
        description="Fix a leaking tap",
    )

    outbox_rows = fake.table("notification_outbox").rows
    assert len(outbox_rows) == 2
    by_owner = {row["payload"]["recipient_id"]: row for row in outbox_rows}
    assert set(by_owner) == {OWNER_A_ID, OWNER_B_ID}

    for owner_id, row in by_owner.items():
        payload = row["payload"]
        # Each provider is addressed only by their own recipient id + a private,
        # provider-scoped dedupe key. No cross-provider or customer identity leaks.
        assert row["dedupe_key"].startswith("rfq_job_broadcast:")
        assert row["dedupe_key"].endswith(":whatsapp")
        assert "customer_id" not in payload
        # The customer's id never appears anywhere in the outbound payload values.
        assert CUSTOMER_ID not in json.dumps(payload)
        other_owner = OWNER_B_ID if owner_id == OWNER_A_ID else OWNER_A_ID
        assert other_owner not in json.dumps(payload)

    # Each provider's message is delivered only to their own phone.
    capture = _CapturingTransport()
    adapter = _whatsapp_adapter(capture)
    dispatcher = NotificationDispatcher(
        fake,
        {"whatsapp": adapter},
        channel_pace_seconds={"whatsapp": 0.0},
    )
    try:
        stats = await dispatcher.run_batch()
    finally:
        await adapter.client.aclose()  # type: ignore[union-attr]

    assert stats.sent == 2
    recipients = {req["body"]["to"] for req in capture.requests}
    assert recipients == {PHONE_A, PHONE_B}


# --------------------------------------------------------------------------- #
# 4. Accepted-quote provider notification (service_quote_accepted) is a         #
#    dispatchable outbox contract — closes the same templateless dead-letter    #
#    gap on the quote-acceptance path. accept_quote() runs against a real DB     #
#    (SUPABASE_DB_URL), so this drives the exact outbox row it enqueues through  #
#    the real dispatcher + adapter with no HTTP call.                            #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_service_quote_accepted_outbox_is_dispatchable() -> None:
    fake = _FakeSupabase()
    # The provider (vendor owner) is the recipient of the accepted-quote notice.
    fake.table("profiles").rows.append(
        {"id": OWNER_A_ID, "phone": PHONE_A, "locale": "en", "notif_prefs": {}}
    )

    # The exact outbox contract accept_quote() commits (template id == event id, the
    # provider owner as recipient_id, deposit/total ngwee), via the shared enqueue
    # path the money-spine SQL insert mirrors.
    row = enqueue_outbox_row(
        fake,
        event_type=ACCEPT_OUTBOX_EVENT,
        entity_id=f"{JOB_ID}:quote-1",
        channel=OUTBOX_CHANNEL,
        template=ACCEPT_OUTBOX_EVENT,
        payload={
            "job_id": JOB_ID,
            "quote_id": "quote-1",
            "vendor_id": VENDOR_A_ID,
            "order_id": "order-1",
            "deposit_ngwee": 125_000,
            "total_job_ngwee": 250_000,
            "recipient_id": OWNER_A_ID,
        },
    )
    assert row is not None
    assert row["template"] == "service_quote_accepted"
    assert "to" not in row["payload"]  # dispatcher must still resolve the destination

    capture = _CapturingTransport()
    adapter = _whatsapp_adapter(capture)
    dispatcher = NotificationDispatcher(
        fake,
        {"whatsapp": adapter},
        channel_pace_seconds={"whatsapp": 0.0},
    )
    try:
        stats = await dispatcher.run_batch()
    finally:
        await adapter.client.aclose()  # type: ignore[union-attr]

    assert stats.sent == 1
    assert len(capture.requests) == 1
    body = capture.requests[0]["body"]
    assert body["to"] == PHONE_A
    assert body["template"]["name"] == "service_quote_accepted"
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert params == ["K1,250.00", "K2,500.00"]  # deposit, total (ngwee → formatK)
    assert fake.table("notification_outbox").rows[0]["status"] == "sent"


# --------------------------------------------------------------------------- #
# 5. Opt-out / STOP preserved: a WhatsApp-disabled provider is not WhatsApp'd. #
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_whatsapp_opt_out_routes_past_whatsapp() -> None:
    fake = _FakeSupabase()
    _seed_provider(
        fake,
        vendor_id=VENDOR_A_ID,
        owner_user_id=OWNER_A_ID,
        display_name="Alpha Plumbing",
        category="home_services",
        service_area="Lusaka",
        phone=PHONE_A,
        # Mirrors a provider who sent STOP: webhook sets notif_prefs.whatsapp=False.
        notif_prefs={"whatsapp": False},
    )

    broadcast_service.broadcast_job(
        fake,
        job_id=JOB_ID,
        customer_id=CUSTOMER_ID,
        category="home_services",
        service_area="Lusaka",
        description="Fix a leaking tap",
    )

    capture = _CapturingTransport()
    whatsapp_adapter = _whatsapp_adapter(capture)
    sms_adapter = NoopAdapter()
    dispatcher = NotificationDispatcher(
        fake,
        {"whatsapp": whatsapp_adapter, "sms": sms_adapter},
        channel_pace_seconds={"whatsapp": 0.0, "sms": 0.0},
    )
    try:
        stats = await dispatcher.run_batch()
    finally:
        await whatsapp_adapter.client.aclose()  # type: ignore[union-attr]

    # WhatsApp was skipped entirely (no Cloud API call); SMS carried it instead.
    assert capture.requests == []
    assert stats.sent == 1
    assert len(sms_adapter.sent) == 1
    assert sms_adapter.sent[0].channel == "sms"
