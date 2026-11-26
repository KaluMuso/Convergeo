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