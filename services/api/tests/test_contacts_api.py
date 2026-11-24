"""T28 contacts router — flag gate, authz, pepper, rate limits, error mapping."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.social.phone import (
    client_hash_to_storage_hash,
    e164_sha256_hex,
    normalize_to_e164,
)
from fastapi.testclient import TestClient

USER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
REQ_ID = "33333333-3333-3333-3333-333333333333"


class _AuthAdmin:
    def __init__(self, owner: _Fake) -> None:
        self._owner = owner

    def get_user_by_id(self, user_id: str) -> MagicMock:
        confirmed = self._owner.phone_confirmed_at
        return MagicMock(user=MagicMock(phone_confirmed_at=confirmed))


class _Q:
    def __init__(
        self,
        rows: list[dict[str, Any]] | dict[str, Any] | Any,
        owner: _Fake,
        *,
        table: str,
    ) -> None:
        self._rows = rows
        self._owner = owner
        self._table = table
        self._pending: list[tuple[str, Any]] = []
        self._filters: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        def chain(*args: Any, **kwargs: Any) -> _Q:
            self._pending.append((name, (args, kwargs)))
            if name == "eq" and args:
                self._filters[str(args[0])] = args[1]
            return self

        return chain

    def execute(self) -> MagicMock:
        name = self._owner._last_rpc
        if name:
            return MagicMock(data=self._owner._rpc_payload.get(name))
        inserted: dict[str, Any] | None = None
        for op, (args, _kwargs) in self._pending:
            if op == "insert" and args:
                inserted = dict(args[0])
                inserted.setdefault("id", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
                rows = self._owner.tables.setdefault(self._table, [])
                rows.append(inserted)
        if inserted is not None:
            return MagicMock(data=[inserted])
        rows = self._owner.tables.get(self._table, [])
        if isinstance(self._rows, dict):
            return MagicMock(data=self._rows)
        filtered = list(rows)
        if "id" in self._filters:
            filtered = [row for row in filtered if str(row.get("id")) == str(self._filters["id"])]
        if not filtered and self._pending and any(op == "maybe_single" for op, _ in self._pending):
            return MagicMock(data=None)
        if any(op == "maybe_single" for op, _ in self._pending) and filtered:
            return MagicMock(data=filtered[0])
        if self._filters:
            return MagicMock(data=filtered)
        return MagicMock(data=filtered if filtered else self._rows)


class _Fake:
    def __init__(
        self,
        *,
        flag: bool = True,
        pepper: str = "test-pepper",
        phone_confirmed: bool = True,
    ) -> None:
        self.flag = flag
        self.pepper = pepper
        self.phone_confirmed_at = "2026-01-01T00:00:00Z" if phone_confirmed else None
        self.calls: list[tuple[str, Any]] = []
        self._last_rpc: str | None = None
        self._rpc_payload: dict[str, Any] = {
            "my_contact_requests": [],
            "set_my_handle": "alice",
            "discover_by_phone_hashes": [],
            "set_phone_discovery": None,
        }
        self.tables: dict[str, list[dict[str, Any]]] = {
            "feature_flags": [{"flag": "social_contacts", "enabled": flag}],
            "phone_discovery": [],
            "profiles": [
                {"id": USER, "phone": "+260977123456"},
                {"id": OTHER, "phone": "+260966123456"},
            ],
            "flags": [],
        }
        self.auth = MagicMock()
        self.auth.admin = _AuthAdmin(self)

    def table(self, name: str) -> _Q:
        self._last_rpc = None
        self.calls.append(("table", name))
        raw = self.tables.get(name, [])
        if name == "feature_flags" and isinstance(raw, list) and raw:
            return _Q(raw[0], self, table=name)
        return _Q(raw, self, table=name)

    def rpc(self, name: str, params: dict[str, Any]) -> _Q:
        self._last_rpc = name
        self.calls.append(("rpc", (name, params)))
        return _Q(self._rpc_payload.get(name), self, table="__rpc__")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("SOCIAL_PHONE_PEPPER", "unit-test-pepper")
    monkeypatch.setattr("app.routers.contacts.bump_rate_counter", lambda **_: (True, 0))
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.app_ref = app
        yield c


def _login(c: TestClient, fake: _Fake) -> None:
    app = c.app_ref
    wrapper = MagicMock()
    wrapper.client = fake
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=USER, roles=frozenset({"customer"}), token="t"
    )
    app.dependency_overrides[get_supabase_client] = lambda: wrapper


def test_flag_off_returns_404(client: TestClient) -> None:
    _login(client, _Fake(flag=False))
    assert client.get("/contacts").status_code == 404


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/contacts").status_code == 401


def test_wrong_request_id_is_404(client: TestClient) -> None:
    fake = _Fake(flag=True)
    fake._rpc_payload["my_contact_requests"] = [
        {
            "id": REQ_ID,
            "from_user": OTHER,
            "to_user": USER,
            "note": None,
            "status": "pending",
            "created_at": "2026-11-24T00:00:00+00:00",
            "outgoing": False,
        }
    ]
    _login(client, fake)
    missing = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    resp = client.post(f"/contacts/requests/{missing}/accept")
    assert resp.status_code == 404


def test_pepper_missing_discovery_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.errors import AppError

    def _missing(*_: object, **__: object) -> str:
        raise AppError(
            code="service_unavailable",
            message="Phone discovery is temporarily unavailable",
            http_status=503,
            details={"message_key": "social.errors.pepperMissing"},
        )

    monkeypatch.setattr("app.routers.contacts.require_phone_pepper", _missing)
    fake = _Fake(flag=True)
    _login(client, fake)
    resp = client.post(
        "/contacts/discover-phones",
        json={"hashes": [e164_sha256_hex("+260977123456")]},
    )
    assert resp.status_code == 503


def test_too_many_hashes_rejected(client: TestClient) -> None:
    fake = _Fake(flag=True)
    _login(client, fake)
    hashes = ["a" * 64 for _ in range(501)]
    resp = client.post("/contacts/discover-phones", json={"hashes": hashes})
    assert resp.status_code == 422


def test_normalize_zm_phone_hashes_match() -> None:
    samples = ("0977123456", "977123456", "+260977123456", "260977123456")
    expected = e164_sha256_hex("+260977123456")
    for raw in samples:
        e164 = normalize_to_e164(raw)
        assert e164 == "+260977123456", raw
        assert e164_sha256_hex(e164) == expected


def test_foreign_number_kept() -> None:
    foreign = "+447700900123"
    assert normalize_to_e164(foreign) == foreign
    assert e164_sha256_hex(foreign) != e164_sha256_hex("+260977123456")


def test_client_hash_hmac_stable() -> None:
    client_hash = e164_sha256_hex("+260977123456")
    settings = MagicMock(social_phone_pepper="pep", env="development")
    a = client_hash_to_storage_hash(client_hash, settings=settings)
    b = client_hash_to_storage_hash(client_hash, settings=settings)
    assert a == b
    assert a != client_hash


def test_discover_rate_limited_after_five_per_day(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"count": 0}

    def _bump(**_: object) -> tuple[bool, int]:
        state["count"] += 1
        return (state["count"] <= 5, 60)

    monkeypatch.setattr("app.routers.contacts.bump_rate_counter", _bump)
    fake = _Fake(flag=True)
    _login(client, fake)
    payload = {"hashes": [e164_sha256_hex("+260977123456")]}
    for _ in range(5):
        assert client.post("/contacts/discover-phones", json=payload).status_code == 200
    assert client.post("/contacts/discover-phones", json=payload).status_code == 429


def test_write_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _bump(**kwargs: object) -> tuple[bool, int]:
        scope = kwargs.get("scope")
        if scope == "social_write":
            return (False, 30)
        return (True, 0)

    monkeypatch.setattr("app.routers.contacts.bump_rate_counter", _bump)
    fake = _Fake(flag=True)
    _login(client, fake)
    resp = client.put("/me/handle", json={"handle": "demo_shop"})
    assert resp.status_code == 429


def test_discover_returns_only_opted_in_matches(client: TestClient) -> None:
    fake = _Fake(flag=True)
    fake._rpc_payload["discover_by_phone_hashes"] = [
        {"user_id": OTHER, "handle": "friend", "display_name": "Friend", "enabled": True},
    ]
    _login(client, fake)
    resp = client.post(
        "/contacts/discover-phones",
        json={"hashes": [e164_sha256_hex("+260966123456")]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["user_id"] == OTHER


def test_put_phone_discovery_requires_verified_phone(client: TestClient) -> None:
    fake = _Fake(flag=True, phone_confirmed=False)
    _login(client, fake)
    resp = client.put("/me/phone-discovery", json={"enabled": True})
    assert resp.status_code == 422


def test_report_contact_unknown_user_404(client: TestClient) -> None:
    fake = _Fake(flag=True)
    fake.tables["profiles"] = [{"id": USER, "phone": "+260977123456"}]
    _login(client, fake)
    missing = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    resp = client.post(f"/contacts/{missing}/report", json={"reason": "spam"})
    assert resp.status_code == 404


def test_report_contact_inserts_flags_row(client: TestClient) -> None:
    fake = _Fake(flag=True)
    _login(client, fake)
    resp = client.post(f"/contacts/{OTHER}/report", json={"reason": "spam", "detail": "bots"})
    assert resp.status_code == 200
    assert fake.tables["flags"]
    row = fake.tables["flags"][0]
    assert row["entity_type"] == "user"
    assert row["entity_id"] == OTHER
    assert row["reporter_user_id"] == USER
    assert row["status"] == "open"


def test_share_card_rejects_unknown_keys(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _Fake(flag=True)
    _login(client, fake)
    thread = "44444444-4444-4444-4444-444444444444"
    monkeypatch.setattr(
        "app.routers.contacts._require_thread_party",
        lambda *_a, **_k: {"id": thread, "user_a": USER, "user_b": OTHER},
    )
    resp = client.post(
        f"/chats/{thread}/messages",
        json={"kind": "share_card", "card": {"type": "listing", "extra": "nope"}},
    )
    assert resp.status_code == 422