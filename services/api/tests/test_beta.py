"""M16-P09 — beta invite gate, capacity-safe redemption, flag no-op, feedback outbox."""

from __future__ import annotations

import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

ADMIN_ID = "66666666-6666-6666-6666-666666666666"
USER_ID = "11111111-1111-1111-1111-111111111111"
VALID_TOKEN = "valid.jwt.token"


# ---------------------------------------------------------------------------
# In-memory Supabase double: tables + a thread-safe rpc mirroring the SQL guard.
# ---------------------------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, _columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        return all(row.get(col) == val for col, val in self._filters)

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", f"{len(self._parent.rows) + 1:08x}-0000-4000-8000-000000000abc")
            row.setdefault("used_count", 0)
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            self._parent.rows.append(row)
            return MagicMock(data=[dict(row)])

        rows = [dict(r) for r in self._parent.rows if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "beta_invites": FakeTable(),
            "feature_flags": FakeTable(),
            "notification_outbox": FakeTable(),
            "audit_log": FakeTable(),
        }
        self._lock = threading.Lock()

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())

    def rpc(self, name: str, params: dict[str, Any]) -> MagicMock:
        if name == "bump_rate_counter":
            data: list[dict[str, Any]] = [{"allowed": True, "retry_after_seconds": 0}]
        elif name == "redeem_beta_invite":
            data = [self._redeem(params["p_code"])]
        else:
            raise AssertionError(f"unexpected rpc {name}")
        return MagicMock(execute=MagicMock(return_value=MagicMock(data=data)))

    def _redeem(self, code: str) -> dict[str, Any]:
        # The threading.Lock mirrors the per-row lock the SQL guard takes, so the
        # last slot is handed out exactly once even under concurrent redeems.
        with self._lock:
            match = next((r for r in self.tables["beta_invites"].rows if r["code"] == code), None)
            if match is None:
                return {"outcome": "invalid", "remaining": 0}
            if not match.get("active", True):
                return {"outcome": "inactive", "remaining": 0}
            expires_at = match.get("expires_at")
            if expires_at is not None:
                exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if exp <= datetime.now(UTC):
                    return {"outcome": "expired", "remaining": 0}
            used = int(match.get("used_count", 0))
            capacity = int(match["capacity"])
            if used >= capacity:
                return {"outcome": "exhausted", "remaining": 0}
            match["used_count"] = used + 1
            return {"outcome": "redeemed", "remaining": capacity - (used + 1)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def beta_client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    wrapper = MagicMock()
    wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: wrapper)
    return client


def _auth(monkeypatch: pytest.MonkeyPatch, user_id: str, roles: frozenset[str]) -> None:
    claims = {"sub": user_id, "exp": 9_999_999_999}
    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", lambda token, settings: claims)
    # beta.py binds verify_supabase_jwt directly for the optional-auth feedback path.
    monkeypatch.setattr("app.routers.beta.verify_supabase_jwt", lambda token, settings: claims)
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: roles if uid == user_id else frozenset(),
    )


def _set_flag(fake: FakeSupabaseClient, enabled: bool) -> None:
    fake.tables["feature_flags"].rows.append({"flag": "public_launch", "enabled": enabled})


def _seed_invite(fake: FakeSupabaseClient, **overrides: Any) -> None:
    row = {
        "id": f"aaaaaaaa-0000-4000-8000-{len(fake.tables['beta_invites'].rows):012d}",
        "code": "GOODCODE",
        "capacity": 5,
        "used_count": 0,
        "expires_at": None,
        "active": True,
        "note": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    row.update(overrides)
    fake.tables["beta_invites"].rows.append(row)


def _bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


# ---------------------------------------------------------------------------
# Gate (flag-controlled)
# ---------------------------------------------------------------------------
def test_gate_invite_required_when_flag_off(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    _set_flag(fake, enabled=False)
    body = beta_client.get("/beta/gate").json()
    assert body == {"public_launch": False, "invite_required": True}


def test_gate_public_when_flag_on(beta_client: TestClient, fake: FakeSupabaseClient) -> None:
    _set_flag(fake, enabled=True)
    body = beta_client.get("/beta/gate").json()
    assert body == {"public_launch": True, "invite_required": False}


def test_gate_defaults_invite_only_when_flag_missing(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    body = beta_client.get("/beta/gate").json()
    assert body["invite_required"] is True


# ---------------------------------------------------------------------------
# Redemption — distinct outcomes + flag no-op
# ---------------------------------------------------------------------------
def test_redeem_valid_code_grants(beta_client: TestClient, fake: FakeSupabaseClient) -> None:
    _set_flag(fake, enabled=False)
    _seed_invite(fake, capacity=2)
    body = beta_client.post("/beta/redeem", json={"code": "GOODCODE"}).json()
    assert body == {
        "outcome": "redeemed",
        "granted": True,
        "remaining": 1,
        "invite_required": True,
    }


def test_redeem_invalid_code_distinct(beta_client: TestClient, fake: FakeSupabaseClient) -> None:
    _set_flag(fake, enabled=False)
    body = beta_client.post("/beta/redeem", json={"code": "NOPE"}).json()
    assert body["outcome"] == "invalid"
    assert body["granted"] is False


def test_redeem_expired_code_distinct(beta_client: TestClient, fake: FakeSupabaseClient) -> None:
    _set_flag(fake, enabled=False)
    _seed_invite(fake, expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat())
    body = beta_client.post("/beta/redeem", json={"code": "GOODCODE"}).json()
    assert body["outcome"] == "expired"
    assert body["granted"] is False


def test_redeem_exhausted_code_distinct(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    _set_flag(fake, enabled=False)
    _seed_invite(fake, capacity=1, used_count=1)
    body = beta_client.post("/beta/redeem", json={"code": "GOODCODE"}).json()
    assert body["outcome"] == "exhausted"
    assert body["granted"] is False


def test_redeem_inactive_code_distinct(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    _set_flag(fake, enabled=False)
    _seed_invite(fake, active=False)
    body = beta_client.post("/beta/redeem", json={"code": "GOODCODE"}).json()
    assert body["outcome"] == "inactive"


def test_redeem_is_noop_when_public_launch_on(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    _set_flag(fake, enabled=True)
    # No invite seeded and no code required: the flag flip opens the gate.
    body = beta_client.post("/beta/redeem", json={"code": "anything"}).json()
    assert body == {
        "outcome": "public",
        "granted": True,
        "remaining": 0,
        "invite_required": False,
    }


# ---------------------------------------------------------------------------
# Capacity race — concurrent redeems never exceed capacity
# ---------------------------------------------------------------------------
def test_capacity_race_never_exceeds(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    capacity = 3
    _set_flag(fake, enabled=False)
    _seed_invite(fake, code="RACE", capacity=capacity, used_count=0)

    attempts = 15

    def redeem(_: int) -> str:
        return str(beta_client.post("/beta/redeem", json={"code": "RACE"}).json()["outcome"])

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        outcomes = list(pool.map(redeem, range(attempts)))

    granted = outcomes.count("redeemed")
    assert granted == capacity, outcomes
    assert outcomes.count("exhausted") == attempts - capacity
    invite = fake.tables["beta_invites"].rows[0]
    assert invite["used_count"] == capacity <= invite["capacity"]


# ---------------------------------------------------------------------------
# Admin invite management + authz
# ---------------------------------------------------------------------------
def test_admin_creates_invite_and_audits(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    res = beta_client.post(
        "/beta/invites",
        headers=_bearer(),
        json={"code": "LAUNCH-01", "capacity": 50, "note": "first cohort"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["code"] == "LAUNCH-01"
    assert body["capacity"] == 50
    assert body["remaining"] == 50
    assert len(fake.tables["beta_invites"].rows) == 1
    assert len(fake.tables["audit_log"].rows) == 1
    assert fake.tables["audit_log"].rows[0]["action"] == "beta.invite.create"


def test_non_admin_cannot_create_invite(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, USER_ID, frozenset({"customer"}))
    res = beta_client.post(
        "/beta/invites",
        headers=_bearer(),
        json={"code": "SNEAKY", "capacity": 10},
    )
    assert res.status_code == 403
    assert fake.tables["beta_invites"].rows == []


def test_non_admin_cannot_list_invites(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, USER_ID, frozenset({"vendor"}))
    res = beta_client.get("/beta/invites", headers=_bearer())
    assert res.status_code == 403


def test_admin_lists_invites(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, ADMIN_ID, frozenset({"admin"}))
    _seed_invite(fake, code="A1", capacity=4, used_count=1)
    res = beta_client.get("/beta/invites", headers=_bearer())
    assert res.status_code == 200
    rows = res.json()
    assert rows[0]["code"] == "A1"
    assert rows[0]["remaining"] == 3


# ---------------------------------------------------------------------------
# Feedback widget -> outbox
# ---------------------------------------------------------------------------
def test_feedback_roundtrips_to_outbox(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, USER_ID, frozenset({"customer"}))
    res = beta_client.post(
        "/beta/feedback",
        headers=_bearer(),
        json={"category": "bug", "message": "The cart total looks wrong", "path": "/en/cart"},
    )
    assert res.status_code == 201
    assert res.json()["ok"] is True

    outbox = fake.tables["notification_outbox"].rows
    assert len(outbox) == 1
    row = outbox[0]
    assert row["channel"] == "email"
    assert row["template"] == "beta_feedback"
    assert row["payload"]["message"] == "The cart total looks wrong"
    assert row["payload"]["category"] == "bug"
    assert row["payload"]["user_id"] == USER_ID
    assert row["payload"]["has_screenshot"] is False


def test_feedback_anonymous_is_accepted_without_token(
    beta_client: TestClient, fake: FakeSupabaseClient
) -> None:
    # The widget floats on pre-login pages: no token -> accepted, user_id is null.
    res = beta_client.post("/beta/feedback", json={"message": "hello there team"})
    assert res.status_code == 201
    row = fake.tables["notification_outbox"].rows[0]
    assert row["channel"] == "email"
    assert row["payload"]["user_id"] is None


def test_feedback_sanitizes_control_chars(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, USER_ID, frozenset({"customer"}))
    injection = "Subject: spam\r\nBcc: victim@example.com\x00 real message"
    res = beta_client.post(
        "/beta/feedback",
        headers=_bearer(),
        json={"message": injection},
    )
    assert res.status_code == 201
    stored = fake.tables["notification_outbox"].rows[0]["payload"]["message"]
    assert "\r" not in stored
    assert "\x00" not in stored
    assert "real message" in stored


def test_feedback_accepts_valid_screenshot(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, USER_ID, frozenset({"customer"}))
    shot = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    res = beta_client.post(
        "/beta/feedback",
        headers=_bearer(),
        json={"message": "screenshot attached", "screenshot": shot},
    )
    assert res.status_code == 201
    payload = fake.tables["notification_outbox"].rows[0]["payload"]
    assert payload["has_screenshot"] is True
    assert payload["screenshot"].startswith("data:image/png;base64,")


def test_feedback_rejects_non_image_screenshot(
    beta_client: TestClient, fake: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch, USER_ID, frozenset({"customer"}))
    res = beta_client.post(
        "/beta/feedback",
        headers=_bearer(),
        json={"message": "bad shot", "screenshot": "javascript:alert(1)"},
    )
    assert res.status_code == 422
    assert fake.tables["notification_outbox"].rows == []
