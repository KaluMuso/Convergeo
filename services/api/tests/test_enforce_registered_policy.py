"""Router dependency ``enforce_registered_policy`` (T52)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import anyio
import pytest
from app.core import ratelimit_policies as rp
from app.core.ratelimit_policies import STANDARD_WRITE, enforce_registered_policy, route_id
from app.errors import AppError, app_error_handler
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.routing import Route


def _register_app_error_handler(app: FastAPI) -> None:
    handler = cast(
        Callable[[Request, Any], JSONResponse],
        app_error_handler,
    )
    app.add_exception_handler(AppError, handler)


SYNTHETIC_PATH = "/synthetic/t52-rate-limit"


@pytest.mark.anyio
async def test_skips_non_mutating_methods() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/probe",
            "headers": [],
            "query_string": b"",
        }
    )
    await enforce_registered_policy(request)


@pytest.mark.anyio
async def test_fail_open_when_bump_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(enforce_registered_policy)])

    rid = route_id("POST", SYNTHETIC_PATH)
    monkeypatch.setitem(rp.POLICIES, rid, STANDARD_WRITE)

    @router.post(SYNTHETIC_PATH)
    async def write() -> dict[str, str]:
        return {"ok": "1"}

    app.include_router(router)

    def boom(**_: Any) -> tuple[bool, int]:
        raise RuntimeError("limiter down")

    monkeypatch.setattr("app.core.ratelimit_policies.bump_rate_counter", boom)

    client = TestClient(app)
    assert client.post(SYNTHETIC_PATH).status_code == 200


def test_mutating_route_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    rid = route_id("POST", SYNTHETIC_PATH)
    monkeypatch.setitem(rp.POLICIES, rid, STANDARD_WRITE)

    app = FastAPI()
    _register_app_error_handler(app)
    router = APIRouter(dependencies=[Depends(enforce_registered_policy)])

    @router.post(SYNTHETIC_PATH)
    async def write() -> dict[str, str]:
        return {"ok": "1"}

    app.include_router(router)
    monkeypatch.setattr(
        "app.core.ratelimit_policies.bump_rate_counter",
        lambda **_kwargs: (False, 42),
    )

    response = TestClient(app).post(SYNTHETIC_PATH)
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["details"]["retry_after"] == 42


def test_direct_dependency_raises_app_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.ratelimit_policies.bump_rate_counter",
        lambda **_kwargs: (False, 7),
    )
    rid = route_id("POST", "/cart/items")
    assert rid in rp.POLICIES

    async def run() -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/cart/items",
                "headers": [],
                "query_string": b"",
            }
        )
        request.scope["route"] = Route("/cart/items", endpoint=lambda: None, methods=["POST"])
        await enforce_registered_policy(request)

    with pytest.raises(AppError) as exc:
        anyio.run(run)
    assert exc.value.http_status == 429


def test_router_dependency_invokes_bump_before_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    rid = route_id("POST", SYNTHETIC_PATH)
    monkeypatch.setitem(rp.POLICIES, rid, STANDARD_WRITE)

    app = FastAPI()
    _register_app_error_handler(app)
    router = APIRouter(dependencies=[Depends(enforce_registered_policy)])

    @router.post(SYNTHETIC_PATH)
    async def write() -> dict[str, str]:
        return {"ok": "1"}

    app.include_router(router)

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        calls.append(kwargs)
        return len(calls) <= 1, 30

    monkeypatch.setattr("app.core.ratelimit_policies.bump_rate_counter", fake_bump)

    client = TestClient(app)
    assert client.post(SYNTHETIC_PATH).status_code == 200
    blocked = client.post(SYNTHETIC_PATH)
    assert calls
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"


def test_routes_in_same_tier_use_separate_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    path_a, path_b = "/synthetic/t52-a", "/synthetic/t52-b"
    monkeypatch.setitem(rp.POLICIES, route_id("POST", path_a), STANDARD_WRITE)
    monkeypatch.setitem(rp.POLICIES, route_id("POST", path_b), STANDARD_WRITE)

    app = FastAPI()
    router = APIRouter(dependencies=[Depends(enforce_registered_policy)])

    @router.post(path_a)
    async def write_a() -> dict[str, str]:
        return {"ok": "a"}

    @router.post(path_b)
    async def write_b() -> dict[str, str]:
        return {"ok": "b"}

    app.include_router(router)

    keys: list[tuple[str, str]] = []

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        keys.append((kwargs["scope"], kwargs["key"]))
        return True, 0

    monkeypatch.setattr("app.core.ratelimit_policies.bump_rate_counter", fake_bump)
    client = TestClient(app)
    client.post(path_a)
    client.post(path_b)
    assert len(keys) == 2
    assert keys[0][0] == keys[1][0]  # same tier scope
    assert keys[0][1] != keys[1][1]  # but distinct buckets
    assert path_a in keys[0][1] and path_b in keys[1][1]


def test_guest_keyed_by_cart_cookie_else_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    import jwt

    secret = "test-secret-key-for-guest-cart-cookie-0123456789"
    monkeypatch.setattr(
        "app.core.ratelimit_policies.get_settings",
        lambda: type("S", (), {"supabase_service_role_key": secret})(),
    )
    monkeypatch.setitem(rp.POLICIES, route_id("POST", SYNTHETIC_PATH), STANDARD_WRITE)

    app = FastAPI()
    router = APIRouter(dependencies=[Depends(enforce_registered_policy)])

    @router.post(SYNTHETIC_PATH)
    async def write() -> dict[str, str]:
        return {"ok": "1"}

    app.include_router(router)
    keys: list[str] = []

    def fake_bump(**kwargs: Any) -> tuple[bool, int]:
        keys.append(kwargs["key"])
        return True, 0

    monkeypatch.setattr("app.core.ratelimit_policies.bump_rate_counter", fake_bump)

    def cookie(token: str) -> str:
        return jwt.encode({"gt": token, "typ": "cart_guest"}, secret, algorithm="HS256")

    client = TestClient(app)
    ip_hdr = {"x-forwarded-for": "198.51.100.7"}
    client.post(SYNTHETIC_PATH, headers=ip_hdr, cookies={rp.GUEST_CART_COOKIE: cookie("g1")})
    client.post(SYNTHETIC_PATH, headers=ip_hdr, cookies={rp.GUEST_CART_COOKIE: cookie("g2")})
    client.post(SYNTHETIC_PATH, headers=ip_hdr, cookies={rp.GUEST_CART_COOKIE: "forged"})
    client.post(SYNTHETIC_PATH, headers=ip_hdr)
    assert keys[0] != keys[1]  # same IP, different guest carts -> different buckets
    assert "gc:" in keys[0] and "198.51.100.7" not in keys[0]
    assert keys[2].endswith("198.51.100.7")  # forged cookie falls back to IP
    assert keys[3] == keys[2]
