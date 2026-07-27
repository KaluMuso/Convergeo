"""M18-P02 — isolated WAHA inbound webhook (D35 Lane 2, WAHA 2026.5.1).

Structured as a rejection matrix: every gate gets a test that asserts both the
audited disposition **and** that the event never reached the domain. The most
important assertions here are negative ones — what the lane refuses to do.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.intake import config as intake_config
from fastapi.testclient import TestClient

SECRET = "test-waha-secret"
SESSION = "vergeo-intake"
VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
BINDING_A = "11111111-1111-4111-8111-111111111111"
MSISDN_A = "260971234567"
JID_A = f"{MSISDN_A}@c.us"
GROUP_JID = "120363000000000000@g.us"

URL = "/webhooks/waha-intake"


# ---------------------------------------------------------------------------
# In-memory Supabase double
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, table: FakeTable) -> None:
        self._t = table
        self._filters: list[tuple[str, Any]] = []
        self._in: tuple[str, list[Any]] | None = None
        self._is_null: list[str] = []
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _c: str = "*", **_k: Any) -> FakeQuery:
        return self

    def eq(self, col: str, val: Any) -> FakeQuery:
        self._filters.append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> FakeQuery:
        self._in = (col, vals)
        return self

    def is_(self, col: str, _v: Any) -> FakeQuery:
        self._is_null.append(col)
        return self

    def order(self, _c: str, **_k: Any) -> FakeQuery:
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

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._filters):
            return False
        if self._in is not None:
            col, vals = self._in
            if row.get(col) not in vals:
                return False
        return all(row.get(c) is None for c in self._is_null)

    def execute(self) -> MagicMock:
        with self._t.db.lock:
            if self._op == "insert":
                assert self._payload is not None
                row = dict(self._payload)
                row.setdefault("id", f"{self._t.name}-{len(self._t.rows) + 1}")
                if self._t.name == "webhook_events":
                    key = (row.get("provider"), row.get("event_id"))
                    if any((r.get("provider"), r.get("event_id")) == key for r in self._t.rows):
                        raise RuntimeError("duplicate key value violates unique constraint")
                if self._t.name == "intake_messages":
                    pid = row.get("provider_message_id")
                    if any(r.get("provider_message_id") == pid for r in self._t.rows):
                        raise RuntimeError("duplicate key")
                self._t.rows.append(row)
                return MagicMock(data=[dict(row)])

            if self._op == "update":
                assert self._payload is not None
                changed = []
                for row in self._t.rows:
                    if self._match(row):
                        row.update(self._payload)
                        changed.append(dict(row))
                return MagicMock(data=changed)

            rows = [dict(r) for r in self._t.rows if self._match(r)]
            if self._maybe_single:
                return MagicMock(data=rows[0] if rows else None)
            return MagicMock(data=rows)


class FakeTable:
    def __init__(self, db: FakeDB, name: str) -> None:
        self.db = db
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, c: str = "*", **k: Any) -> FakeQuery:
        return FakeQuery(self).select(c, **k)

    def insert(self, p: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(p)

    def update(self, p: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(p)


class FakeDB:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable(self, name)
        return self.tables[name]


class Wrapper:
    def __init__(self) -> None:
        self.client = FakeDB()

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows

    def dispositions(self) -> list[str]:
        return [r["disposition"] for r in self.rows("intake_events") if r.get("disposition")]


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(intake_config.ENV_WEBHOOK_SECRET, SECRET)
    monkeypatch.setenv(intake_config.ENV_SESSION, SESSION)
    monkeypatch.setenv(intake_config.ENV_BASE_URL, "http://waha.internal:3000")
    monkeypatch.setenv(intake_config.ENV_API_KEY, "k")
    monkeypatch.setenv(intake_config.ENV_ALLOWED_IPS, "10.0.0.1/32")
    monkeypatch.setenv(intake_config.ENV_SENDER_E164, "+260970000000")


@pytest.fixture()
def store() -> Wrapper:
    w = Wrapper()
    w.rows("feature_flags").append({"flag": intake_config.INTAKE_FLAG, "enabled": True})
    w.rows("platform_config").append(
        {"key": intake_config.INTAKE_ALLOWLIST_KEY, "value": [VENDOR_A]}
    )
    w.rows("vendors").append({"id": VENDOR_A, "status": "active", "kyc_tier": 1})
    w.rows("intake_vendor_bindings").append(
        {"id": BINDING_A, "vendor_id": VENDOR_A, "msisdn": MSISDN_A, "opted_out_at": None}
    )
    return w


@pytest.fixture()
def api(env: None, store: Wrapper) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: store
    with patch("app.deps.get_supabase_service_client", return_value=store), patch(
        "app.supabase_client.get_supabase_service_client", return_value=store
    ):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------
def body(
    *,
    event: str = "message",
    session: str = SESSION,
    msg_id: str = "waha.msg.1",
    frm: str = JID_A,
    text: str | None = "Fridge K3500",
    from_me: bool = False,
    participant: str | None = None,
    media: Any = None,
) -> bytes:
    payload: dict[str, Any] = {
        "event": event,
        "session": session,
        "payload": {"id": msg_id, "from": frm, "body": text, "fromMe": from_me},
    }
    if participant is not None:
        payload["payload"]["participant"] = participant
    if media is not None:
        payload["payload"]["media"] = media
    return json.dumps(payload).encode()


def sign(raw: bytes, secret: str = SECRET, algo: str = "sha512") -> dict[str, str]:
    digest = (
        hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        if algo == "sha512"
        else hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    )
    return {
        "X-Webhook-Hmac": digest,
        "X-Webhook-Hmac-Algorithm": algo,
        "X-Webhook-Request-Id": "req-1",
        "X-Webhook-Timestamp": str(int(time.time() * 1000)),
    }


def post(api: TestClient, raw: bytes, headers: dict[str, str] | None = None) -> Any:
    return api.post(URL, content=raw, headers=headers if headers is not None else sign(raw))


def assert_not_processed(store: Wrapper) -> None:
    assert store.rows("intake_sessions") == []
    assert store.rows("intake_messages") == []


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_valid_event_is_accepted(api: TestClient, store: Wrapper) -> None:
    assert post(api, body()).status_code == 200
    assert len(store.rows("intake_sessions")) == 1
    assert len(store.rows("intake_messages")) == 1
    assert "draft_created" in store.dispositions()


# ---------------------------------------------------------------------------
# Gate 1 — the kill switch
# ---------------------------------------------------------------------------
def test_flag_off_drops_everything(api: TestClient, store: Wrapper) -> None:
    """A validly-signed event is still dropped when the lane is disabled."""
    store.rows("feature_flags")[0]["enabled"] = False
    resp = post(api, body())
    assert resp.status_code == 200, "an authenticated caller should not retry"
    assert store.dispositions() == ["dropped_flag_off"]
    assert_not_processed(store)


def test_flag_row_missing_drops_everything(api: TestClient, store: Wrapper) -> None:
    store.rows("feature_flags").clear()
    assert post(api, body()).status_code == 200
    assert store.dispositions() == ["dropped_flag_off"]
    assert_not_processed(store)


def test_unsigned_request_is_403_even_when_the_flag_is_off(
    api: TestClient, store: Wrapper
) -> None:
    """Signature is checked BEFORE the flag, so unsigned is never a 200.

    A webhook endpoint must never return success to an unverified caller,
    whatever the lane's enabled state — the platform-wide invariant asserted by
    tests/test_authz_matrix.py::test_webhook_endpoints_reject_unsigned.
    """
    store.rows("feature_flags")[0]["enabled"] = False
    raw = body()
    resp = api.post(URL, content=raw, headers={"X-Webhook-Hmac": "garbage"})
    assert resp.status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


def test_unsigned_request_is_rejected_with_no_config_at_all(
    api: TestClient, store: Wrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with the secret unset and the flag missing, unsigned ⇒ 403."""
    monkeypatch.delenv(intake_config.ENV_WEBHOOK_SECRET, raising=False)
    store.rows("feature_flags").clear()
    resp = api.post(URL, content=body(), headers={})
    assert resp.status_code >= 400
    assert_not_processed(store)


# ---------------------------------------------------------------------------
# Gate 2 — HMAC-SHA-512 (NOT Meta's SHA-256)
# ---------------------------------------------------------------------------
def test_missing_signature_rejected(api: TestClient, store: Wrapper) -> None:
    raw = body()
    resp = api.post(URL, content=raw, headers={"X-Webhook-Hmac-Algorithm": "sha512"})
    assert resp.status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


def test_invalid_signature_rejected(api: TestClient, store: Wrapper) -> None:
    raw = body()
    headers = sign(raw)
    headers["X-Webhook-Hmac"] = "0" * 128
    assert api.post(URL, content=raw, headers=headers).status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


def test_signature_over_a_different_body_rejected(api: TestClient, store: Wrapper) -> None:
    """Tamper the body after signing — the HMAC must be over the exact bytes."""
    headers = sign(body(text="Fridge K3500"))
    assert api.post(URL, content=body(text="Fridge K1"), headers=headers).status_code == 403
    assert_not_processed(store)


def test_sha256_signature_rejected(api: TestClient, store: Wrapper) -> None:
    """A valid Meta-style SHA-256 signature must NOT authenticate Lane 2.

    Accepting it would collapse the lane separation the whole design rests on.
    """
    raw = body()
    assert api.post(URL, content=raw, headers=sign(raw, algo="sha256")).status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


def test_missing_algorithm_header_rejected(api: TestClient, store: Wrapper) -> None:
    raw = body()
    headers = sign(raw)
    del headers["X-Webhook-Hmac-Algorithm"]
    assert api.post(URL, content=raw, headers=headers).status_code == 403
    assert_not_processed(store)


def test_missing_secret_fails_closed(
    api: TestClient, store: Wrapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No configured secret must mean 'reject everything', never 'accept all'."""
    monkeypatch.delenv(intake_config.ENV_WEBHOOK_SECRET, raising=False)
    raw = body()
    assert api.post(URL, content=raw, headers=sign(raw)).status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


def test_wrong_secret_rejected(api: TestClient, store: Wrapper) -> None:
    raw = body()
    assert api.post(URL, content=raw, headers=sign(raw, secret="other")).status_code == 403
    assert_not_processed(store)


# ---------------------------------------------------------------------------
# Gate 3 — request identity and freshness
# ---------------------------------------------------------------------------
def test_missing_request_id_rejected(api: TestClient, store: Wrapper) -> None:
    raw = body()
    headers = sign(raw)
    del headers["X-Webhook-Request-Id"]
    assert api.post(URL, content=raw, headers=headers).status_code == 403
    assert_not_processed(store)


@pytest.mark.parametrize("offset_ms", [-600_000, 600_000])
def test_stale_or_future_timestamp_rejected(
    api: TestClient, store: Wrapper, offset_ms: int
) -> None:
    raw = body()
    headers = sign(raw)
    headers["X-Webhook-Timestamp"] = str(int(time.time() * 1000) + offset_ms)
    assert api.post(URL, content=raw, headers=headers).status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


@pytest.mark.parametrize("bad", ["", "not-a-number", "12.5.3"])
def test_unparseable_timestamp_rejected(api: TestClient, store: Wrapper, bad: str) -> None:
    raw = body()
    headers = sign(raw)
    headers["X-Webhook-Timestamp"] = bad
    assert api.post(URL, content=raw, headers=headers).status_code == 403
    assert_not_processed(store)


# ---------------------------------------------------------------------------
# Gate 4 — source account
# ---------------------------------------------------------------------------
def test_wrong_session_rejected(api: TestClient, store: Wrapper) -> None:
    assert post(api, body(session="someone-elses-session")).status_code == 403
    assert store.dispositions() == ["rejected_auth"]
    assert_not_processed(store)


# ---------------------------------------------------------------------------
# Gate 5 — pinned event type
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("event", ["message.ack", "session.status", "presence.update", ""])
def test_non_message_event_ignored(api: TestClient, store: Wrapper, event: str) -> None:
    assert post(api, body(event=event)).status_code == 400
    assert store.dispositions() == ["error"]
    assert_not_processed(store)


def test_outbound_echo_is_not_intake(api: TestClient, store: Wrapper) -> None:
    """fromMe messages are our own; they must never create an intake record."""
    assert post(api, body(from_me=True)).status_code == 400
    assert_not_processed(store)


# ---------------------------------------------------------------------------
# Gate 6 — groups are categorically forbidden
# ---------------------------------------------------------------------------
def test_group_message_dropped(api: TestClient, store: Wrapper) -> None:
    resp = post(api, body(frm=GROUP_JID, participant=JID_A))
    assert resp.status_code == 200
    assert store.dispositions() == ["dropped_group"]
    assert_not_processed(store)


@pytest.mark.parametrize(
    "jid",
    [
        "120363000000000000@g.us",
        "status@broadcast",
        "123@broadcast",
        "abc@newsletter",
    ],
)
def test_every_group_like_jid_dropped(api: TestClient, store: Wrapper, jid: str) -> None:
    assert post(api, body(frm=jid)).status_code == 200
    assert store.dispositions() == ["dropped_group"]
    assert_not_processed(store)


def test_unfamiliar_jid_shape_is_refused_by_default(api: TestClient, store: Wrapper) -> None:
    """A conversation type we have never seen must NOT be treated as 1:1.

    The check is a positive whitelist, so a future WhatsApp surface cannot slip
    through merely by not matching the forbidden list.
    """
    assert post(api, body(frm=f"{MSISDN_A}@lid")).status_code == 200
    assert store.dispositions() == ["dropped_group"]
    assert_not_processed(store)


def test_no_group_send_capability_exists() -> None:
    """There is no code path that replies to, joins, or enumerates a group."""
    from app.routers import webhooks_waha_intake as mod

    exported = dir(mod)
    for forbidden in ("send", "reply", "join_group", "send_message", "ack", "post_message"):
        assert forbidden not in exported


# ---------------------------------------------------------------------------
# Gates 7 + 8 — sender shape, verified vendor, allowlist
# ---------------------------------------------------------------------------
def test_non_e164_sender_dropped(api: TestClient, store: Wrapper) -> None:
    assert post(api, body(frm="12345@c.us")).status_code == 200
    assert store.dispositions() == ["dropped_unverified"]
    assert_not_processed(store)


def test_unknown_number_dropped_without_disclosure(api: TestClient, store: Wrapper) -> None:
    resp = post(api, body(frm="260979999999@c.us"))
    assert resp.status_code == 200
    assert resp.content in (b"", b"null")
    assert store.dispositions() == ["dropped_unverified"]
    assert_not_processed(store)


def test_suspended_vendor_dropped(api: TestClient, store: Wrapper) -> None:
    store.rows("vendors")[0]["status"] = "suspended"
    assert post(api, body()).status_code == 200
    assert store.dispositions() == ["dropped_unverified"]
    assert_not_processed(store)


def test_under_tier_vendor_dropped(api: TestClient, store: Wrapper) -> None:
    store.rows("vendors")[0]["kyc_tier"] = 0
    assert post(api, body()).status_code == 200
    assert store.dispositions() == ["dropped_unverified"]
    assert_not_processed(store)


def test_not_allowlisted_vendor_dropped(api: TestClient, store: Wrapper) -> None:
    """Flag on is not enough during the pilot — the allowlist is a second gate."""
    store.rows("platform_config")[0]["value"] = []
    assert post(api, body()).status_code == 200
    assert store.dispositions() == ["dropped_unverified"]
    assert_not_processed(store)


def test_ineligible_reasons_are_indistinguishable(api: TestClient, store: Wrapper) -> None:
    """Unknown / suspended / not-allowlisted must look identical to the caller."""
    unknown = post(api, body(msg_id="m1", frm="260979999999@c.us"))
    store.rows("vendors")[0]["status"] = "suspended"
    suspended = post(api, body(msg_id="m2"))
    store.rows("vendors")[0]["status"] = "active"
    store.rows("platform_config")[0]["value"] = []
    not_listed = post(api, body(msg_id="m3"))

    codes = {unknown.status_code, suspended.status_code, not_listed.status_code}
    bodies = {unknown.content, suspended.content, not_listed.content}
    assert codes == {200}
    assert len(bodies) == 1, "responses must be byte-identical across reasons"
    assert set(store.dispositions()) == {"dropped_unverified"}


# ---------------------------------------------------------------------------
# Gate 9 — schema
# ---------------------------------------------------------------------------
def test_malformed_json_rejected(api: TestClient, store: Wrapper) -> None:
    raw = b"{not json"
    assert api.post(URL, content=raw, headers=sign(raw)).status_code == 400
    assert store.dispositions() == ["error"]
    assert_not_processed(store)


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"event": "message", "session": SESSION}).encode(),
        json.dumps({"event": "message", "session": SESSION, "payload": {}}).encode(),
        json.dumps({"event": "message", "payload": {"id": "x", "from": JID_A}}).encode(),
        json.dumps(["not", "an", "object"]).encode(),
    ],
)
def test_schema_violations_rejected(api: TestClient, store: Wrapper, raw: bytes) -> None:
    assert api.post(URL, content=raw, headers=sign(raw)).status_code == 400
    assert_not_processed(store)


# ---------------------------------------------------------------------------
# Gate 10 — replay
# ---------------------------------------------------------------------------
def test_duplicate_event_is_a_no_op(api: TestClient, store: Wrapper) -> None:
    first = post(api, body(msg_id="dup.1"))
    second = post(api, body(msg_id="dup.1"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(store.rows("intake_sessions")) == 1
    assert len(store.rows("intake_messages")) == 1
    assert len(store.rows("webhook_events")) == 1


def test_dedupe_row_uses_the_waha_provider(api: TestClient, store: Wrapper) -> None:
    post(api, body())
    assert store.rows("webhook_events")[0]["provider"] == "waha"


def test_replay_is_claimed_after_auth_not_before(api: TestClient, store: Wrapper) -> None:
    """A forged event must not be able to burn a legitimate event's dedupe key.

    If dedupe ran before signature verification, an attacker who guessed a
    message id could pre-claim it and make the real delivery a silent no-op.
    """
    raw = body(msg_id="target.1")
    api.post(URL, content=raw, headers=sign(raw, secret="wrong"))
    assert store.rows("webhook_events") == [], "unauthenticated event must not claim a key"

    assert post(api, raw).status_code == 200
    assert len(store.rows("intake_messages")) == 1


# ---------------------------------------------------------------------------
# Lane separation and inbound-only
# ---------------------------------------------------------------------------
def _imported_names(module: Any) -> set[str]:
    """Every module/symbol the module actually imports (docstrings excluded)."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(alias.name for alias in node.names)
    return names


def _code_text(module: Any) -> str:
    """Module source with docstrings and comments stripped.

    The module's prose *describes* the Lane 1 separation, so a naive substring
    search over raw source would match the explanation rather than real usage.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                node.value.value = ""
    return ast.unparse(tree)


def test_lane_1_verifier_is_not_reused() -> None:
    """Lane 2 must not import, wrap, or reuse the Cloud API webhook."""
    from app.routers import webhooks_waha_intake as mod

    imported = _imported_names(mod)
    assert not any("webhooks_whatsapp" in name for name in imported)
    assert "verify_hub_signature" not in imported

    code = _code_text(mod)
    assert "verify_hub_signature" not in code
    assert "X-Hub-Signature" not in code
    # And it does use the WAHA scheme.
    assert "sha512" in code.lower()


def test_no_outbound_client_is_constructed() -> None:
    """Strictly inbound-only: no HTTP client, no WAHA API call, no outbox."""
    from app.routers import webhooks_waha_intake as mod

    imported = _imported_names(mod)
    for forbidden in ("httpx", "requests", "aiohttp", "urllib.request"):
        assert forbidden not in imported, f"outbound capability leaked: {forbidden}"

    code = _code_text(mod)
    for forbidden in ("enqueue_outbox_row", "notification_outbox"):
        assert forbidden not in code, f"outbound capability leaked: {forbidden}"


def test_route_declares_a_rate_limit_policy() -> None:
    """Registered as a policy, not smuggled into the webhook exemption list."""
    from app.core import ratelimit_policies as rp

    assert "POST /webhooks/waha-intake" in rp.POLICIES
    assert "POST /webhooks/waha-intake" not in rp.EXEMPT_ROUTE_IDS


def test_oversized_body_rejected(api: TestClient, store: Wrapper) -> None:
    raw = b"x" * 2_000_000
    assert api.post(URL, content=raw, headers=sign(raw)).status_code == 413
    assert_not_processed(store)
