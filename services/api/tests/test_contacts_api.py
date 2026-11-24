"""T28 contacts router — flag gate, authz, pepper, rate limits, error mapping."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.services.social.phone import client_hash_to_storage_hash, e164_sha256_hex, normalize_to_e164
from fastapi.testclient import TestClient

USER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
REQ_ID = "33333333-3333-3333-3333-333333333333"


class _Q:
    def __init__(self, rows: list[dict[str, Any]] | Any, owner: "_Fake") -> None:
        self._rows = rows
        self._owner = owner
        self._pending: list[tuple[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        def chain(*args: Any, **kwargs: Any) -> _Q:
            self._pending.append((name, (args, kwargs)))
            return self

        return chain

    def execute(self) -> MagicMock:
        name = self._owner._last_rpc
        if name:
            return MagicMock(data=self._owner._rpc_payload.get(name))
        return MagicMock(data=self._rows)


class _Fake:
    def __init__(self, *, flag: bool = True, pepper: str = "test-pepper") -> None:
        self.flag = flag
        self.pepper = pepper
        self.calls: list[tuple[str, Any]] = []
        self._last_rpc: str | None = None
        self._rpc_payload: dict[str, Any] = {
            "my_contact_requests": [],
            "set_my_handle": "alice",
        }
        self.tables: dict[str, list[dict[str, Any]]] = {
            "feature_flags": [{"flag": "social_contacts", "enabled": flag}],
            "phone_discovery": [],
            "profiles": [{"id": USER, "phone": "+260977123456"}],
        }

    def table(self, name: str) -> _Q:
        self._last_rpc = None
        self.calls.append(("table", name))
        rows = self.tables.get(name, [])
        if name == "feature_flags" and rows:
            rows = rows[0] if isinstance(rows, list) else rows
        return _Q(rows, self)

    def rpc(self, name: str, params: dict[str, Any]) -> _Q:
        self._last_rpc = name
        self.calls.append(("rpc", (name, params)))
        return _Q(self._rpc_payload.get(name), self)


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
    a = client_hash_to_storage_hash(client_hash, settings=MagicMock(social_phone_pepper="pep", env="development"))
    b = client_hash_to_storage_hash(client_hash, settings=MagicMock(social_phone_pepper="pep", env="development"))
    assert a == b
    assert a != client_hash