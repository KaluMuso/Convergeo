from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
TOKEN = "vendor-token"


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _mock_auth(monkeypatch)
    service_wrapper = MagicMock()
    service_wrapper.client = MagicMock()
    app = create_app()
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper
    return TestClient(app, raise_server_exceptions=False)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_geo_search_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch) as client:
        response = client.get("/geo/search?q=Lusaka")
    assert response.status_code == 401


def test_geo_search_q_too_short_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(monkeypatch) as client:
        response = client.get("/geo/search?q=ab", headers=_auth())
    assert response.status_code == 422


@patch("app.routers.geo._fetch_nominatim")
def test_geo_search_returns_results(
    fetch_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_mock.return_value = [
        {"label": "Arcades, Lusaka, Zambia", "lat": -15.42, "lng": 28.28},
    ]
    with _client(monkeypatch) as client:
        response = client.get("/geo/search?q=Arcades", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body[0]["label"].startswith("Arcades")


@patch("app.routers.geo._fetch_nominatim")
def test_geo_search_cache_hit_single_upstream_call(
    fetch_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.routers.geo as geo_module

    geo_module._cache.clear()
    fetch_mock.return_value = [
        {"label": "Arcades, Lusaka", "lat": -15.42, "lng": 28.28},
    ]
    with _client(monkeypatch) as client:
        first = client.get("/geo/search?q=Arcades", headers=_auth())
        second = client.get("/geo/search?q=arcades", headers=_auth())
    assert first.status_code == 200
    assert second.status_code == 200
    assert fetch_mock.call_count == 1


@patch("app.routers.geo._fetch_nominatim")
def test_geo_search_upstream_failure_503(
    fetch_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.errors import AppError

    fetch_mock.side_effect = AppError(
        code="geo_unavailable",
        message="Place search is temporarily unavailable",
        http_status=503,
    )
    with _client(monkeypatch) as client:
        response = client.get("/geo/search?q=Lusaka", headers=_auth())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "geo_unavailable"


@patch("app.routers.geo.bump_rate_counter", return_value=(False, 30))
def test_geo_search_rate_limited(
    _bump: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _client(monkeypatch) as client:
        response = client.get("/geo/search?q=Lusaka", headers=_auth())
    assert response.status_code == 429