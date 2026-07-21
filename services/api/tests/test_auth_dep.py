from __future__ import annotations

import json
import time
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Annotated, Any
from unittest.mock import MagicMock

import jwt
import pytest
from app.core.auth import (
    CurrentUser,
    _jwks_client,
    _load_user_roles,
    get_current_user,
    require_role,
    verify_supabase_jwt,
)
from app.core.supabase import get_user_client
from app.main import create_app
from app.settings import get_settings
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

USER_ID = "11111111-1111-1111-1111-111111111111"
VALID_TOKEN = "valid.jwt.token"
EXPIRED_TOKEN = "expired.jwt.token"
TAMPERED_TOKEN = "tampered.jwt.token"
JWT_KID = "test-rs256-kid"


@pytest.fixture
def auth_app() -> FastAPI:
    app = create_app()

    async def me(current_user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict[str, Any]:
        return {
            "id": current_user.id,
            "roles": sorted(current_user.roles),
        }

    async def admin_only(
        current_user: Annotated[CurrentUser, Depends(require_role("admin"))],
    ) -> dict[str, str]:
        return {"status": "ok", "id": current_user.id}

    async def me_twice(
        first: Annotated[CurrentUser, Depends(get_current_user)],
        second: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> dict[str, str]:
        assert first.id == second.id
        return {"id": first.id}

    app.add_api_route("/test/auth/me", me, methods=["GET"])
    app.add_api_route("/test/auth/admin", admin_only, methods=["GET"])
    app.add_api_route("/test/auth/me-twice", me_twice, methods=["GET"])
    return app


@pytest.fixture
def auth_client(auth_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(auth_app, raise_server_exceptions=False) as test_client:
        yield test_client


def _mock_verify(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token_map: dict[str, dict[str, Any]] | None = None,
    default_claims: dict[str, Any] | None = None,
    error_tokens: dict[str, Exception] | None = None,
) -> None:
    token_map = token_map or {}
    error_tokens = error_tokens or {}
    default = default_claims or {"sub": USER_ID, "exp": 9_999_999_999}

    def fake_verify(token: str, settings: Any) -> dict[str, Any]:
        _ = settings
        if token in error_tokens:
            raise error_tokens[token]
        if token in token_map:
            return token_map[token]
        return default

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", fake_verify)


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def test_valid_token_returns_current_user_with_db_roles(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"customer", "vendor"})})

    response = auth_client.get(
        "/test/auth/me",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == USER_ID
    assert body["roles"] == ["customer", "vendor"]


def test_forged_admin_claim_without_db_role_returns_403(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(
        monkeypatch,
        default_claims={"sub": USER_ID, "exp": 9_999_999_999, "role": "admin"},
    )
    _mock_roles(monkeypatch, {USER_ID: frozenset({"customer"})})

    response = auth_client.get(
        "/test/auth/admin",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["request_id"]


def test_missing_token_returns_401_envelope(auth_client: TestClient) -> None:
    response = auth_client.get("/test/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"]


def test_expired_token_returns_401_envelope(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(
        monkeypatch,
        error_tokens={EXPIRED_TOKEN: ExpiredSignatureError("expired")},
    )

    response = auth_client.get(
        "/test/auth/me",
        headers={"Authorization": f"Bearer {EXPIRED_TOKEN}"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"]


def test_tampered_token_returns_401_envelope(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(
        monkeypatch,
        error_tokens={TAMPERED_TOKEN: InvalidTokenError("bad signature")},
    )

    response = auth_client.get(
        "/test/auth/me",
        headers={"Authorization": f"Bearer {TAMPERED_TOKEN}"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"]


def test_require_role_admin_passes_for_real_admin(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})

    response = auth_client.get(
        "/test/auth/admin",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == USER_ID


def test_get_current_user_roles_cached_per_request(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    load_mock = MagicMock(return_value=frozenset({"customer"}))
    monkeypatch.setattr("app.core.auth._load_user_roles", load_mock)

    response = auth_client.get(
        "/test/auth/me-twice",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )

    assert response.status_code == 200
    assert load_mock.call_count == 1


def test_load_user_roles_reads_from_service_client() -> None:
    service_client = MagicMock()
    execute_result = MagicMock(data=[{"role": "vendor"}, {"role": "customer"}])
    query = service_client.client.table.return_value.select.return_value.eq.return_value
    query.execute.return_value = execute_result

    roles = _load_user_roles(USER_ID, service_client)
    assert roles == frozenset({"vendor", "customer"})


def test_get_user_client_sets_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class FakePostgrest:
        def auth(self, token: str) -> None:
            created["token"] = token

    class FakeClient:
        def __init__(self) -> None:
            self.postgrest = FakePostgrest()

    def fake_create_client(url: str, key: str) -> FakeClient:
        created["url"] = url
        created["key"] = key
        return FakeClient()

    monkeypatch.setattr("app.core.supabase.create_client", fake_create_client)
    get_settings.cache_clear()

    settings = get_settings()
    client = get_user_client("user-access-token")
    assert isinstance(client, FakeClient)
    assert created["url"] == settings.supabase_url
    assert created["key"] == settings.supabase_anon_key
    assert created["token"] == "user-access-token"


def test_require_role_without_roles_raises_value_error() -> None:
    with pytest.raises(ValueError, match="at least one role"):
        require_role()


def _build_rs256_keypair() -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": JWT_KID, "use": "sig", "alg": "RS256"})
    return private_key, public_jwk


def _mint_rs256_access_token(private_key: Any, issuer: str) -> str:
    now = int(time.time())
    claims = {
        "sub": USER_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "iss": issuer,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": JWT_KID})


@pytest.fixture
def rs256_jwks_stub() -> Generator[tuple[str, str], None, None]:
    private_key, public_jwk = _build_rs256_keypair()
    jwks_body = json.dumps({"keys": [public_jwk]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(jwks_body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    supabase_url = f"http://127.0.0.1:{port}"
    issuer = f"{supabase_url}/auth/v1"
    token = _mint_rs256_access_token(private_key, issuer)

    try:
        yield supabase_url, token
    finally:
        server.shutdown()


def test_verify_supabase_jwt_accepts_rs256_jwks_token(
    rs256_jwks_stub: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase_url, token = rs256_jwks_stub
    monkeypatch.setenv("SUPABASE_URL", supabase_url)
    get_settings.cache_clear()
    _jwks_client.cache_clear()

    settings = get_settings()
    claims = verify_supabase_jwt(token, settings)

    assert claims["sub"] == USER_ID
    assert claims["aud"] == "authenticated"


def test_verify_supabase_jwt_rejects_hs256_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "abcdefghijklmnopqrstuvwxyz012345"
    now = int(time.time())
    claims = {
        "sub": USER_ID,
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": now + 3600,
    }
    token = jwt.encode(claims, secret, algorithm="HS256")

    signing_key = MagicMock()
    signing_key.key = secret
    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = signing_key
    monkeypatch.setattr("app.core.auth._jwks_client", lambda _url: mock_client)

    settings = get_settings()
    with pytest.raises(InvalidTokenError):
        verify_supabase_jwt(token, settings)


def test_rs256_jwks_token_yields_current_user_with_roles(
    auth_client: TestClient,
    rs256_jwks_stub: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase_url, token = rs256_jwks_stub
    monkeypatch.setenv("SUPABASE_URL", supabase_url)
    get_settings.cache_clear()
    _jwks_client.cache_clear()
    _mock_roles(monkeypatch, {USER_ID: frozenset({"customer"})})

    response = auth_client.get(
        "/test/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == USER_ID
    assert body["roles"] == ["customer"]
