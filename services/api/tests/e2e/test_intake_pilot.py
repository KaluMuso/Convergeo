"""M18-P08 — private-pilot proof for the WAHA vendor-intake lane (D35).

Every other intake test proves one pebble. This one proves the **chain**, and —
more importantly — proves the things that must remain impossible when the whole
chain is wired together, because that is where a boundary usually leaks.

Positive path (the pilot's happy case, R2 step 4):

    signed inbound photo+text
      → private intake record (never a listing)
      → duplicate delivery is harmless
      → missing details recorded as DATA, not messaged
      → vendor corrects and explicitly submits  → listing is **draft**
      → admin approves                          → listing becomes active

Negative paths, each proven **non-publishing**:

    group message · unknown number · invalid signature · flag off ·
    prohibited class · media failure

And the kill switch: flipping the flag off stops ingestion **without** harming
existing drafts or Lane 1. That last clause is the one worth testing, because a
kill switch that also destroyed in-flight vendor work would not get used.

The Supabase double below is deliberately shared across the whole chain rather
than per-pebble, so a session created by the webhook is the same row the vendor
router reads and the admin router approves. A per-test stub would let the pieces
agree with their own mocks while disagreeing with each other.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.intake import config as intake_config
from app.services.intake import orchestrator, state_machine
from fastapi.testclient import TestClient

SECRET = "test-waha-secret"
SESSION_NAME = "vergeo-intake"

VENDOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_USER_ID = "11111111-1111-4111-8111-111111111111"
ADMIN_USER_ID = "22222222-2222-4222-8222-222222222222"
BINDING_ID = "33333333-3333-4333-8333-333333333333"

MSISDN = "260971234567"
JID = f"{MSISDN}@c.us"
GROUP_JID = "120363000000000000@g.us"
STRANGER_JID = "260979999999@c.us"

WEBHOOK_URL = "/webhooks/waha-intake"
JWT = "valid.jwt.token"


# ---------------------------------------------------------------------------
# Shared in-memory Supabase double
# ---------------------------------------------------------------------------
class FakeNot:
    def __init__(self, query: FakeQuery) -> None:
        self._query = query

    def is_(self, column: str, value: Any) -> FakeQuery:
        self._query.filters.append(("not_is", column, value))
        return self._query


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self.filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    @property
    def not_(self) -> FakeNot:
        return FakeNot(self)

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self.filters.append(("in", column, values))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("lt", column, value))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("gte", column, value))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("is", column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> FakeQuery:
        self._op = "delete"
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, column, value in self.filters:
            actual = row.get(column)
            if op == "eq" and actual != value:
                return False
            if op == "neq" and actual == value:
                return False
            if op == "in" and actual not in value:
                return False
            if op == "lt" and (actual is None or str(actual) >= str(value)):
                return False
            if op == "gte" and (actual is None or str(actual) < str(value)):
                return False
            if op == "is" and value in ("null", None) and actual is not None:
                return False
            if op == "not_is" and value in ("null", None) and actual is None:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            self._parent.enforce_unique(row)
            row.setdefault("id", f"{self._parent.name}-{len(self._parent.rows)}")
            self._parent.apply_defaults(row)
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._op == "update":
            assert self._payload is not None
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        if self._op == "delete":
            kept = [row for row in self._parent.rows if not self._match(row)]
            removed = len(self._parent.rows) - len(kept)
            self._parent.rows[:] = kept
            return MagicMock(data=[{}] * removed)

        rows = [dict(row) for row in self._parent.rows if self._match(row)]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class UniqueViolation(Exception):
    """Stands in for Postgres 23505 so replay-dedupe is exercised for real."""


class FakeTable:
    #: (table, columns) pairs that carry a real UNIQUE constraint in the schema.
    UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
        "webhook_events": ("provider", "event_id"),
        "intake_messages": ("provider_message_id",),
    }
    DEFAULTS: dict[str, dict[str, Any]] = {
        "intake_sessions": {
            "status": state_machine.COLLECTING,
            "pending_requests": [],
            "listing_id": None,
            "submitted_at": None,
            "admin_notes": None,
            "rejection_reason": None,
            "last_activity_at": "2026-07-01T00:00:00+00:00",
            "expires_at": "2026-08-01T00:00:00+00:00",
        },
    }

    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def enforce_unique(self, row: dict[str, Any]) -> None:
        columns = self.UNIQUE_KEYS.get(self.name)
        if not columns:
            return
        key = tuple(row.get(column) for column in columns)
        for existing in self.rows:
            if tuple(existing.get(column) for column in columns) == key:
                raise UniqueViolation(f"{self.name} {columns} already exists")

    def apply_defaults(self, row: dict[str, Any]) -> None:
        for column, value in self.DEFAULTS.get(self.name, {}).items():
            row.setdefault(column, value)

    def select(self, columns: str = "*", *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()


class FakeBucket:
    def create_signed_url(self, path: str, ttl: int) -> dict[str, str]:
        return {"signedURL": f"https://signed.example/{path}?ttl={ttl}"}


class FakeStorage:
    def from_(self, name: str) -> FakeBucket:
        return FakeBucket()


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


class Store:
    """Service-role wrapper, matching what the routers depend on."""

    def __init__(self) -> None:
        self.client = FakeSupabase()

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(intake_config.ENV_WEBHOOK_SECRET, SECRET)
    monkeypatch.setenv(intake_config.ENV_SESSION, SESSION_NAME)
    monkeypatch.setenv(intake_config.ENV_BASE_URL, "http://waha.internal:3000")
    monkeypatch.setenv(intake_config.ENV_API_KEY, "k")
    monkeypatch.setenv(intake_config.ENV_ALLOWED_IPS, "10.0.0.1/32")
    monkeypatch.setenv(intake_config.ENV_SENDER_E164, "+260970000000")
    monkeypatch.delenv("ENV", raising=False)


@pytest.fixture()
def store() -> Store:
    # The quota cache is process-wide; a stale entry from another test would make
    # this suite pass or fail depending on ordering.
    from app.services.kyc.caps import clear_vendor_cap_cache

    clear_vendor_cap_cache()
    st = Store()
    st.rows("feature_flags").append({"flag": intake_config.INTAKE_FLAG, "enabled": True})
    st.rows("platform_config").extend(
        [
            {"key": intake_config.INTAKE_ALLOWLIST_KEY, "value": [VENDOR_ID]},
            {"key": "cod_cap_ngwee", "value": 50_000},
        ]
    )
    st.rows("vendors").append(
        {
            "id": VENDOR_ID,
            "owner_user_id": VENDOR_USER_ID,
            "status": "active",
            "kyc_tier": 2,
            "display_name": "Pilot Vendor",
        }
    )
    st.rows("intake_vendor_bindings").append(
        {
            "id": BINDING_ID,
            "vendor_id": VENDOR_ID,
            "msisdn": MSISDN,
            "opted_out_at": None,
        }
    )
    # The KYC cap path reads a real quota row rather than a stub, so the pilot
    # proves the same tier enforcement a hand-typed listing gets.
    st.rows("vendor_quotas").append(
        {
            "tier": 1,
            "max_listings": 25,
            "first_orders_cap_ngwee": None,
            "first_orders_count": None,
            "payout_velocity": {},
        }
    )
    # Tables the chain touches but never seeds itself.
    for name in (
        "intake_sessions",
        "intake_messages",
        "intake_media",
        "intake_draft_fields",
        "intake_field_provenance",
        "intake_events",
        "intake_deep_links",
        "webhook_events",
        "vendor_listings",
        "products",
        "orders",
        "notification_outbox",
        "audit_log",
    ):
        st.rows(name)
    return st


@pytest.fixture()
def api(
    env: None, store: Store, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: store
    for module in (
        "app.routers.webhooks_waha_intake",
        "app.routers.vendor_intake",
        "app.routers.admin_intake",
        "app.routers.internal_intake",
    ):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: store, raising=False)
    monkeypatch.setattr("app.routers.vendor_intake.bump_rate_counter", lambda **_k: (True, 0))

    with patch("app.deps.get_supabase_service_client", return_value=store), patch(
        "app.supabase_client.get_supabase_service_client", return_value=store
    ), patch("app.core.admin_audit.get_supabase_service_client", return_value=store):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


def _as(monkeypatch: pytest.MonkeyPatch, user_id: str, roles: frozenset[str]) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda user_id, service_client: roles
    )


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {JWT}"}


# ---------------------------------------------------------------------------
# Inbound helpers
# ---------------------------------------------------------------------------
def inbound(
    *,
    msg_id: str = "waha.msg.1",
    frm: str = JID,
    text: str | None = "Samsung fridge, brand new, K3500",
    participant: str | None = None,
    session: str = SESSION_NAME,
) -> bytes:
    payload: dict[str, Any] = {
        "event": "message",
        "session": session,
        "payload": {"id": msg_id, "from": frm, "body": text, "fromMe": False},
    }
    if participant is not None:
        payload["payload"]["participant"] = participant
    return json.dumps(payload).encode()


def sign(raw: bytes, *, secret: str = SECRET, algo: str = "sha512") -> dict[str, str]:
    digest_mod = hashlib.sha512 if algo == "sha512" else hashlib.sha256
    return {
        "X-Webhook-Hmac": hmac.new(secret.encode(), raw, digest_mod).hexdigest(),
        "X-Webhook-Hmac-Algorithm": algo,
        "X-Webhook-Request-Id": "req-pilot",
        "X-Webhook-Timestamp": str(int(time.time() * 1000)),
    }


def deliver(api: TestClient, raw: bytes, headers: dict[str, str] | None = None) -> Any:
    return api.post(WEBHOOK_URL, content=raw, headers=headers if headers else sign(raw))


def dispositions(store: Store) -> list[str]:
    return [
        str(row.get("disposition"))
        for row in store.rows("intake_events")
        if row.get("kind") == "ingestion"
    ]


def assert_nothing_published(store: Store) -> None:
    """The single assertion this whole mountain exists to keep true."""
    assert store.rows("vendor_listings") == [], "the intake lane published a listing"


# ===========================================================================
# Positive chain
# ===========================================================================
def test_inbound_creates_a_private_record_and_never_a_listing(
    api: TestClient, store: Store
) -> None:
    assert deliver(api, inbound()).status_code == 200

    assert len(store.rows("intake_sessions")) == 1
    assert len(store.rows("intake_messages")) == 1
    assert dispositions(store) == [state_machine.DISPOSITION_DRAFT_CREATED]
    assert_nothing_published(store)


def test_duplicate_delivery_is_harmless(api: TestClient, store: Store) -> None:
    """WAHA retries. A replay must not double the session, message, or audit."""
    raw = inbound()
    assert deliver(api, raw).status_code == 200
    assert deliver(api, raw).status_code == 200

    assert len(store.rows("intake_sessions")) == 1
    assert len(store.rows("intake_messages")) == 1
    assert dispositions(store) == [state_machine.DISPOSITION_DRAFT_CREATED]


def test_full_chain_ends_active_only_after_a_human_approves(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pilot's happy path, end to end, with both human gates exercised."""
    # 1. Inbound.
    assert deliver(api, inbound()).status_code == 200
    session_id = str(store.rows("intake_sessions")[0]["id"])

    # 2. Extraction (M18-P04). Rules-only — no model, as in a degraded pilot.
    orchestrator.progress_session(
        store,
        session_id=session_id,
        vendor_id=VENDOR_ID,
        text="Samsung fridge, brand new, K3500",
    )
    assert_nothing_published(store)

    # 3. Vendor opens their draft and supplies what is missing.
    _as(monkeypatch, VENDOR_USER_ID, frozenset({"vendor"}))
    detail = api.get(f"/vendor/intake/sessions/{session_id}", headers=_auth()).json()
    assert detail["draft"]["price_ngwee"] == 350_000, "K3500 must parse to integer ngwee"

    for field in detail["missing_fields"]:
        assert field in {"title", "category_slug", "price_ngwee", "condition"}

    patched_response = api.patch(
        f"/vendor/intake/sessions/{session_id}/draft",
        headers=_auth(),
        json={"title": "Samsung RT38 Fridge", "condition": "new"},
    )
    assert patched_response.status_code == 200, patched_response.text
    patched = patched_response.json()
    assert patched["missing_fields"] == []
    assert_nothing_published(store)

    # A draft that is ready still is not a listing until the vendor says so.
    store.rows("intake_sessions")[0]["status"] = state_machine.READY_FOR_VENDOR_REVIEW

    # 4. Vendor submits — explicitly.
    submit_response = api.post(
        f"/vendor/intake/sessions/{session_id}/submit", headers=_auth()
    )
    assert submit_response.status_code == 200, submit_response.text
    submitted = submit_response.json()
    assert submitted["listing_status"] == "draft", "submission must never publish"
    assert submitted["session_status"] == state_machine.PENDING_ADMIN_REVIEW
    listing_id = submitted["listing_id"]
    assert store.rows("vendor_listings")[0]["status"] == "draft"

    # 5. Admin approves — the only step that can make it buyable.
    _as(monkeypatch, ADMIN_USER_ID, frozenset({"admin"}))
    queue = api.get("/admin/intake", headers=_auth()).json()
    assert [row["session_id"] for row in queue] == [session_id]

    approved = api.post(f"/admin/intake/{session_id}/approve", headers=_auth()).json()
    assert approved["listing_status"] == "active"
    assert approved["session_status"] == state_machine.APPROVED

    listing = next(r for r in store.rows("vendor_listings") if r["id"] == listing_id)
    assert listing["status"] == "active"
    # Provenance survived the handoff: the session still points at the listing.
    assert str(store.rows("intake_sessions")[0]["listing_id"]) == listing_id
    assert store.rows("intake_field_provenance"), "per-field provenance must persist"


def test_missing_details_are_recorded_as_data_not_messaged(
    api: TestClient, store: Store
) -> None:
    """The lane is inbound-only: a follow-up is a row, never an outbound message."""
    assert deliver(api, inbound(text="fridge")).status_code == 200
    session_id = str(store.rows("intake_sessions")[0]["id"])

    orchestrator.progress_session(
        store, session_id=session_id, vendor_id=VENDOR_ID, text="fridge"
    )

    session = store.rows("intake_sessions")[0]
    assert session["status"] == state_machine.NEEDS_DETAILS
    assert session["pending_requests"], "expected recorded follow-up questions"
    assert store.rows("notification_outbox") == [], "the intake lane sent something"


# ===========================================================================
# Negative paths — each must be non-publishing
# ===========================================================================
def test_group_message_cannot_publish(api: TestClient, store: Store) -> None:
    response = deliver(api, inbound(frm=GROUP_JID, participant=JID))
    assert response.status_code == 200
    assert dispositions(store) == [state_machine.DISPOSITION_DROPPED_GROUP]
    assert store.rows("intake_sessions") == []
    assert_nothing_published(store)


def test_unknown_number_cannot_publish(api: TestClient, store: Store) -> None:
    response = deliver(api, inbound(frm=STRANGER_JID))
    assert response.status_code == 200
    assert dispositions(store) == [state_machine.DISPOSITION_DROPPED_UNVERIFIED]
    assert store.rows("intake_sessions") == []
    assert_nothing_published(store)


def test_invalid_signature_cannot_publish(api: TestClient, store: Store) -> None:
    raw = inbound()
    response = deliver(api, raw, headers=sign(raw, secret="wrong-secret"))
    assert response.status_code == 403
    assert dispositions(store) == [state_machine.DISPOSITION_REJECTED_AUTH]
    assert store.rows("intake_sessions") == []
    assert_nothing_published(store)


def test_valid_sha256_signature_is_still_refused(api: TestClient, store: Store) -> None:
    """Lane 1's algorithm must not open Lane 2 — that is the lane separation."""
    raw = inbound()
    response = deliver(api, raw, headers=sign(raw, algo="sha256"))
    assert response.status_code == 403
    assert_nothing_published(store)


def test_flag_off_cannot_publish(api: TestClient, store: Store) -> None:
    store.rows("feature_flags")[0]["enabled"] = False
    response = deliver(api, inbound())
    assert response.status_code == 200
    assert dispositions(store) == [state_machine.DISPOSITION_DROPPED_FLAG_OFF]
    assert store.rows("intake_sessions") == []
    assert_nothing_published(store)


def test_prohibited_class_cannot_publish(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocked draft never reaches ready-for-review, so it cannot be submitted."""
    assert deliver(api, inbound()).status_code == 200
    session_id = str(store.rows("intake_sessions")[0]["id"])

    monkeypatch.setattr(
        "app.services.intake.extract.screen_listing",
        lambda **kwargs: MagicMock(allowed=False, reason="keyword", matched="banned"),
        raising=False,
    )
    orchestrator.progress_session(
        store, session_id=session_id, vendor_id=VENDOR_ID, text="Samsung fridge K3500"
    )

    session = store.rows("intake_sessions")[0]
    assert session["status"] != state_machine.READY_FOR_VENDOR_REVIEW

    _as(monkeypatch, VENDOR_USER_ID, frozenset({"vendor"}))
    response = api.post(f"/vendor/intake/sessions/{session_id}/submit", headers=_auth())
    assert response.status_code == 409
    assert_nothing_published(store)


def test_media_failure_cannot_publish(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected image lands the session in needs_details — recoverable, not published."""
    from app.services.intake import media

    assert deliver(api, inbound()).status_code == 200
    session_id = str(store.rows("intake_sessions")[0]["id"])
    store.rows("intake_sessions")[0]["status"] = state_machine.COLLECTING

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise media.MediaRejected("bad_magic_bytes")

    monkeypatch.setattr(media, "ingest_one", boom)

    import asyncio

    stored = asyncio.run(
        media.ingest_session_media(
            store,
            vendor_id=VENDOR_ID,
            session_id=session_id,
            media_refs=[{"url": "http://waha.internal/x.jpg"}],
        )
    )
    assert stored == []
    assert store.rows("intake_sessions")[0]["status"] == state_machine.NEEDS_DETAILS
    assert_nothing_published(store)


def test_a_vendor_cannot_submit_another_vendors_session(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert deliver(api, inbound()).status_code == 200
    session_id = str(store.rows("intake_sessions")[0]["id"])
    store.rows("vendors").append(
        {
            "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "owner_user_id": ADMIN_USER_ID,
            "status": "active",
            "kyc_tier": 2,
            "display_name": "Other Vendor",
        }
    )

    _as(monkeypatch, ADMIN_USER_ID, frozenset({"vendor"}))
    response = api.post(f"/vendor/intake/sessions/{session_id}/submit", headers=_auth())
    assert response.status_code == 403
    assert_nothing_published(store)


# ===========================================================================
# Kill switch drill (Part B R4)
# ===========================================================================
def test_kill_switch_stops_ingestion_without_harming_drafts(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drill that makes the switch usable: flipping it destroys no work.

    A kill switch an operator is afraid to pull is not a kill switch.
    """
    # A vendor has work in flight.
    assert deliver(api, inbound(msg_id="waha.msg.before")).status_code == 200
    session_id = str(store.rows("intake_sessions")[0]["id"])
    orchestrator.progress_session(
        store,
        session_id=session_id,
        vendor_id=VENDOR_ID,
        text="Samsung fridge, brand new, K3500",
    )
    draft_before = dict(store.rows("intake_draft_fields")[0])
    messages_before = len(store.rows("intake_messages"))

    # Operator flips the flag.
    store.rows("feature_flags")[0]["enabled"] = False

    # Further events are ignored and audited.
    assert deliver(api, inbound(msg_id="waha.msg.after")).status_code == 200
    assert dispositions(store)[-1] == state_machine.DISPOSITION_DROPPED_FLAG_OFF
    assert len(store.rows("intake_messages")) == messages_before, "no new message stored"

    # The vendor's existing draft is untouched and still readable.
    assert store.rows("intake_draft_fields")[0] == draft_before
    assert len(store.rows("intake_sessions")) == 1

    _as(monkeypatch, VENDOR_USER_ID, frozenset({"vendor"}))
    response = api.get(f"/vendor/intake/sessions/{session_id}", headers=_auth())
    assert response.status_code == 200, "the kill switch must not lock vendors out of drafts"
    assert response.json()["draft"]["title"] is not None


def test_kill_switch_leaves_lane_1_intact(api: TestClient, store: Store) -> None:
    """Lane 2's flag gates Lane 2 only — the outbox path is untouched."""
    from app.services.notifications.dedupe import enqueue_outbox_row

    store.rows("feature_flags")[0]["enabled"] = False
    assert deliver(api, inbound()).status_code == 200

    row = enqueue_outbox_row(
        store.client,
        event_type="order_confirmed",
        entity_id="order-1",
        channel="whatsapp",
        template="order_confirmed",
        payload={"order_id": "order-1"},
    )
    assert row is not None, "Lane 1 must still enqueue while Lane 2 is killed"
    assert len(store.rows("notification_outbox")) == 1


# ===========================================================================
# Retention & redaction
# ===========================================================================
def test_retention_sweep_minimises_content_but_keeps_the_audit(
    api: TestClient, store: Store
) -> None:
    from app.routers import internal_intake

    assert deliver(api, inbound()).status_code == 200
    message = store.rows("intake_messages")[0]
    assert message["raw_excerpt"]
    message["purge_after"] = "2020-01-01T00:00:00+00:00"

    result = internal_intake.sweep_purge_messages(store)
    assert result["purged"] == 1
    assert store.rows("intake_messages")[0]["raw_excerpt"] is None
    # Dispositions survive minimisation — that is what makes them auditable.
    assert dispositions(store) == [state_machine.DISPOSITION_DRAFT_CREATED]


def test_logs_never_carry_a_raw_body_or_a_full_msisdn(
    api: TestClient, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    """Redaction assertion: an operator reading logs must not see either."""
    caplog.set_level("INFO")
    secret_text = "Samsung fridge, brand new, K3500"
    assert deliver(api, inbound(text=secret_text)).status_code == 200

    blob = "\n".join(
        [record.getMessage() + json.dumps(getattr(record, "__dict__", {}), default=str)
         for record in caplog.records]
    )
    assert MSISDN not in blob, "a full MSISDN reached the logs"
    assert secret_text not in blob, "a raw message body reached the logs"
