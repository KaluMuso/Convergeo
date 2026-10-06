"""Dependency-upgrade auth/cart controls; all JWKS traffic is fixture-only."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from email.message import Message
from typing import Any

import jwt
import pytest
from app.core.auth import _jwks_client, get_current_user, verify_supabase_jwt
from app.errors import AppError
from app.routers.cart import _sign_guest_cart_cookie, _verify_guest_cart_cookie
from app.settings import Settings
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from jwt.exceptions import InvalidTokenError, PyJWKClientError, PyJWKSetError
from starlette.requests import Request

SECRET = "dependency-cart-test-key-at-least-48-bytes-for-HS384-fixtures"
BASE = "https://auth-fixture.invalid"


@pytest.fixture(autouse=True)
def no_external_connections(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("This test file must never open a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    _jwks_client.cache_clear()
    yield
    _jwks_client.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        SUPABASE_URL=BASE,
        SUPABASE_SERVICE_ROLE_KEY=SECRET,
        SUPABASE_ANON_KEY="fixture-anon",
        ENV="development",
    )


@pytest.fixture(scope="module")
def keypairs() -> dict[str, tuple[Any, dict[str, Any]]]:
    keys: dict[str, Any] = {
        "RS256": rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "ES256": ec.generate_private_key(ec.SECP256R1()),
    }
    result = {}
    for alg, key in keys.items():
        converter = RSAAlgorithm if alg == "RS256" else ECAlgorithm
        jwk = json.loads(converter.to_jwk(key.public_key()))
        jwk.update(kid=alg, alg=alg, use="sig")
        result[alg] = (key, jwk)
    return result


def claims(**overrides: Any) -> dict[str, Any]:
    return {
        "sub": "compatible-user",
        "aud": "authenticated",
        "iss": f"{BASE}/auth/v1",
        "exp": int(time.time()) + 300,
        **overrides,
    }


def transport(monkeypatch: pytest.MonkeyPatch, body: bytes) -> list[str]:
    calls: list[str] = []

    class Opener:
        def open(self, request: urllib.request.Request, **kwargs: Any) -> io.BytesIO:
            assert request.full_url == f"{BASE}/auth/v1/.well-known/jwks.json"
            calls.append(request.full_url)
            return io.BytesIO(body)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    return calls


@pytest.mark.parametrize("alg", ["RS256", "ES256"])
def test_auth_valid_asymmetric_jwks_and_cached_key(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
    alg: str,
) -> None:
    key, jwk = keypairs[alg]
    calls = transport(monkeypatch, json.dumps({"keys": [jwk]}).encode())
    token = jwt.encode(claims(), key, algorithm=alg, headers={"kid": alg})
    for _ in range(2):
        result = verify_supabase_jwt(token, settings)
        assert result["sub"] == "compatible-user"
        assert result["aud"] == "authenticated"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://other.invalid/auth/v1"},
        {"aud": "other"},
        {"exp": 1},
    ],
)
def test_auth_rejects_registered_claim_drift(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
    override: Any,
) -> None:
    key, jwk = keypairs["RS256"]
    transport(monkeypatch, json.dumps({"keys": [jwk]}).encode())
    token = jwt.encode(claims(**override), key, algorithm="RS256", headers={"kid": "RS256"})
    with pytest.raises(InvalidTokenError):
        verify_supabase_jwt(token, settings)


@pytest.mark.parametrize("alg", ["HS256", "none"])
def test_auth_rejects_disallowed_algorithm_after_real_jwk_selection(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
    alg: str,
) -> None:
    transport(monkeypatch, json.dumps({"keys": [keypairs["RS256"][1]]}).encode())
    token = jwt.encode(
        claims(), SECRET if alg == "HS256" else "", algorithm=alg, headers={"kid": "RS256"}
    )
    with pytest.raises(InvalidTokenError):
        verify_supabase_jwt(token, settings)


def test_unknown_kid_refresh_is_bounded_and_does_not_break_known_key(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
) -> None:
    key, jwk = keypairs["RS256"]
    calls = transport(monkeypatch, json.dumps({"keys": [jwk]}).encode())
    for kid in ("missing-a", "missing-b", "missing-c"):
        token = jwt.encode(claims(), key, algorithm="RS256", headers={"kid": kid})
        with pytest.raises(PyJWKClientError):
            verify_supabase_jwt(token, settings)
    assert len(calls) == 1  # Default cooldown suppresses repeated attacker-driven refresh.
    valid = jwt.encode(claims(), key, algorithm="RS256", headers={"kid": "RS256"})
    assert verify_supabase_jwt(valid, settings)["sub"] == "compatible-user"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b'{"keys": []}',
        b'{"keys": [{"kty":"RSA","kid":"RS256","n":"AQAB"}]}',
        b"[]",
    ],
)
def test_invalid_jwks_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
    body: bytes,
) -> None:
    calls = transport(monkeypatch, body)
    token = jwt.encode(claims(), keypairs["RS256"][0], algorithm="RS256", headers={"kid": "RS256"})
    with pytest.raises((PyJWKClientError, PyJWKSetError)):
        verify_supabase_jwt(token, settings)
    assert len(calls) == 1


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


@pytest.mark.parametrize("part", ["header", "payload"])
def test_deeply_nested_token_auth_failure_is_bounded_unauthorized(
    settings: Settings,
    part: str,
) -> None:
    # Fixed ~40KB input, not an unbounded stress test.
    nested = b'{"nested":' + b"[" * 20000 + b"0" + b"]" * 20000 + b"}"
    header = nested if part == "header" else b'{"alg":"RS256","kid":"RS256"}'
    payload = nested if part == "payload" else b"{}"
    token = f"{encoded(header)}.{encoded(payload)}.AA"
    request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})
    with pytest.raises(AppError) as exc:
        asyncio.run(get_current_user(request, settings))
    assert exc.value.http_status == 401
    assert exc.value.code == "unauthorized"
    assert (
        exc.value.details["reason"] != "AssertionError"
    )  # No network attempt hidden by auth mapping.


def test_jwks_redirect_handler_refuses_redirect(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    observed: list[int] = []

    class Opener:
        def open(self, request: Any, **kwargs: Any) -> Any:
            raise urllib.error.HTTPError(request.full_url, 302, "redirect", Message(), None)

    def build(*handlers: Any) -> Opener:
        assert len(handlers) == 1
        request = urllib.request.Request(f"{BASE}/auth/v1/.well-known/jwks.json")
        result = handlers[0].redirect_request(
            request, None, 302, "redirect", {}, "https://forbidden.invalid/jwks"
        )
        assert result is None
        observed.append(302)
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build)
    with pytest.raises(PyJWKClientError):
        _jwks_client(settings.supabase_url).fetch_data()
    assert observed == [302]


def test_cart_valid_hs256_roundtrip_preserves_existing_no_expiry_contract(
    settings: Settings,
) -> None:
    token = _sign_guest_cart_cookie("guest-identity", settings)
    assert _verify_guest_cart_cookie(token, settings) == "guest-identity"
    assert "exp" not in jwt.decode(token, SECRET, algorithms=["HS256"])


@pytest.mark.parametrize("case", ["malformed", "algorithm", "expired", "wrong_key", "empty_gt"])
def test_cart_invalid_cookie_is_unauthorized(settings: Settings, case: str) -> None:
    payload: dict[str, Any] = {"gt": "guest-identity", "typ": "cart_guest"}
    if case == "expired":
        payload["exp"] = 1
    if case == "empty_gt":
        payload["gt"] = " "
    token = (
        "broken"
        if case == "malformed"
        else jwt.encode(
            payload,
            "other-fixture-secret-with-32-bytes" if case == "wrong_key" else SECRET,
            algorithm="HS384" if case == "algorithm" else "HS256",
        )
    )
    with pytest.raises(AppError) as exc:
        _verify_guest_cart_cookie(token, settings)
    assert exc.value.http_status == 401
    assert exc.value.code == "cart.invalid_guest_token"


def test_auth_uses_fresh_options_after_unverified_decode(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
) -> None:
    """Qualify app non-reuse prerequisite, not a claim PYSEC-2026-4146 is fixed."""
    key, jwk = keypairs["RS256"]
    transport(monkeypatch, json.dumps({"keys": [jwk]}).encode())
    expired = jwt.encode(claims(exp=1), key, algorithm="RS256", headers={"kid": "RS256"})
    peek_options: Any = {"verify_signature": False}
    assert jwt.decode(expired, options=peek_options)["exp"] == 1
    real_decode = jwt.decode
    seen: list[dict[str, Any]] = []

    def recording_decode(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["options"])
        assert kwargs["options"] == {"require": ["sub", "exp"]}
        assert kwargs["options"] is not peek_options
        return real_decode(*args, **kwargs)

    monkeypatch.setattr(jwt, "decode", recording_decode)
    for _ in range(2):
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_supabase_jwt(expired, settings)
    assert len(seen) == 2
    assert seen[0] is not seen[1]


def test_cart_signed_deep_payload_fails_as_unauthorized(settings: Settings) -> None:
    # Sign raw JSON so the decoder, rather than the encoder, meets the fixed-depth input.
    payload = b'{"gt":"guest","nested":' + b"[" * 20000 + b"0" + b"]" * 20000 + b"}"
    message = f"{encoded(b'{"alg":"HS256"}')}.{encoded(payload)}"
    signature = hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).digest()
    with pytest.raises(AppError) as exc:
        _verify_guest_cart_cookie(f"{message}.{encoded(signature)}", settings)
    assert exc.value.code == "cart.invalid_guest_token"
    assert exc.value.http_status == 401


def test_deep_jwks_response_does_not_escape_auth_boundary(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    keypairs: Any,
) -> None:
    body = b'{"keys":' + b"[" * 20000 + b"0" + b"]" * 20000 + b"}"
    calls = transport(monkeypatch, body)
    token = jwt.encode(claims(), keypairs["RS256"][0], algorithm="RS256", headers={"kid": "RS256"})
    request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())]})
    with pytest.raises(AppError) as exc:
        asyncio.run(get_current_user(request, settings))
    assert exc.value.code == "unauthorized"
    assert exc.value.http_status == 401
    assert exc.value.details["reason"] != "AssertionError"
    assert len(calls) == 1
