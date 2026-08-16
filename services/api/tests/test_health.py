from __future__ import annotations

import logging
from typing import Any, Protocol, cast
from uuid import UUID

import httpx
import pytest
from app.core.upstream import UpstreamFailureKind
from app.routers import health as health_router
from app.routers.health import (
    _supabase_reachable,
    _supabase_readiness_headers,
    _supabase_readiness_url,
)
from fastapi.testclient import TestClient


class _CorrelatedLogRecord(Protocol):
    request_id: str
    path: str
    method: str
    status_code: int
    duration_ms: float


class _UpstreamLogRecord(Protocol):
    dependency: str
    failure_kind: str
    status_code: int


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self.text = "[]" if self.is_success else "error"


class _RecordingAsyncClient:
    """Minimal httpx.AsyncClient stand-in for readiness probe tests."""

    def __init__(
        self,
        *,
        get_response: _FakeResponse | None = None,
        get_exc: BaseException | None = None,
        post_response: _FakeResponse | None = None,
    ) -> None:
        self.get_response = get_response
        self.get_exc = get_exc
        self.post_response = post_response
        self.get_calls: list[dict[str, Any]] = []
        self.post_calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> _RecordingAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **_kwargs: object,
    ) -> _FakeResponse:
        self.get_calls.append({"url": url, "headers": headers or {}})
        if self.get_exc is not None:
            raise self.get_exc
        assert self.get_response is not None
        return self.get_response

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
        **_kwargs: object,
    ) -> _FakeResponse:
        self.post_calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        assert self.post_response is not None
        return self.post_response


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
    client: _RecordingAsyncClient,
) -> _RecordingAsyncClient:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)
    return client


def test_healthz_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_degrades_without_supabase(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_fingerprint_has_no_secrets(client: TestClient) -> None:
    response = client.get("/fingerprint")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["env"] in {"development", "staging", "production"}
    assert "git_sha" in body
    assert "image_tag" in body
    assert "build_id" in body
    assert "supabase_project_ref" in body
    blob = str(body).lower()
    assert "service_role" not in blob
    assert "anon-key" not in blob
    assert "password" not in blob


def test_fingerprint_exposes_only_safe_build_identifiers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.settings import get_settings

    monkeypatch.setenv("GIT_SHA", "9cd60b0352db24111ff097b1e3842755613a3d29")
    monkeypatch.setenv("API_IMAGE_TAG", "not-a-build-secret")
    get_settings.cache_clear()

    body = client.get("/fingerprint").json()
    assert body["git_sha"] == "9cd60b0352db24111ff097b1e3842755613a3d29"
    assert body["image_tag"] == "unknown"
    assert body["build_id"] == body["git_sha"]


def test_request_id_header_generated(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_request_id_header_echoed(client: TestClient) -> None:
    request_id = "550e8400-e29b-41d4-a716-446655440000"
    response = client.get("/healthz", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id


def test_request_id_header_rejects_untrusted_value(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "not-a-request-id"})
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id != "not-a-request-id"
    UUID(request_id)


def test_completed_request_log_is_correlated(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_id = "550e8400-e29b-41d4-a716-446655440000"
    with caplog.at_level(logging.INFO, logger="app.middleware"):
        assert client.get("/healthz", headers={"X-Request-ID": request_id}).status_code == 200

    completed = [record for record in caplog.records if record.message == "api_request_completed"]
    assert completed
    record = cast(_CorrelatedLogRecord, completed[-1])
    assert record.request_id == request_id
    assert record.path == "/healthz"
    assert record.method == "GET"
    assert record.status_code == 200
    assert isinstance(record.duration_ms, float)


def test_supabase_readiness_url_targets_platform_config_not_openapi_root() -> None:
    url = _supabase_readiness_url("https://example.supabase.co/")
    assert url == "https://example.supabase.co/rest/v1/platform_config?select=key&limit=1"
    assert not url.endswith("/rest/v1/")


def test_supabase_readiness_headers_use_service_role_only() -> None:
    headers = _supabase_readiness_headers("service-role-key")
    assert headers["apikey"] == "service-role-key"
    assert headers["Authorization"] == "Bearer service-role-key"
    assert "anon" not in headers["Authorization"]


@pytest.mark.asyncio
async def test_supabase_reachable_ok_on_data_api_200(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _patch_async_client(
        monkeypatch,
        _RecordingAsyncClient(get_response=_FakeResponse(200)),
    )
    with caplog.at_level(logging.WARNING, logger="app.core.upstream"):
        assert await _supabase_reachable() is True
    assert client.get_calls
    call = client.get_calls[0]
    assert "platform_config" in call["url"]
    assert call["headers"]["Authorization"] == "Bearer service-role-key"
    assert not any(record.message == "upstream_dependency_failed" for record in caplog.records)


@pytest.mark.parametrize(
    ("status_code", "expected_kind"),
    [
        (401, UpstreamFailureKind.UNEXPECTED_STATUS),
        (403, UpstreamFailureKind.UNEXPECTED_STATUS),
        (500, UpstreamFailureKind.UNEXPECTED_STATUS),
    ],
)
@pytest.mark.asyncio
async def test_supabase_reachable_degrades_on_non_success_status(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status_code: int,
    expected_kind: UpstreamFailureKind,
) -> None:
    _patch_async_client(monkeypatch, _RecordingAsyncClient(get_response=_FakeResponse(status_code)))
    with caplog.at_level(logging.WARNING, logger="app.core.upstream"):
        assert await _supabase_reachable() is False

    failure = [
        record for record in caplog.records if record.message == "upstream_dependency_failed"
    ]
    assert failure
    record = cast(_UpstreamLogRecord, failure[-1])
    assert record.dependency == "supabase_rest"
    assert record.failure_kind == expected_kind.value
    assert record.status_code == status_code


@pytest.mark.asyncio
async def test_supabase_reachable_degrades_on_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_async_client(
        monkeypatch,
        _RecordingAsyncClient(
            get_exc=httpx.ConnectTimeout(
                "timed out",
                request=httpx.Request("GET", "https://example.supabase.co/rest/v1/platform_config"),
            )
        ),
    )
    with caplog.at_level(logging.WARNING, logger="app.core.upstream"):
        assert await _supabase_reachable() is False

    record = cast(
        _UpstreamLogRecord,
        next(r for r in caplog.records if r.message == "upstream_dependency_failed"),
    )
    assert record.dependency == "supabase_rest"
    assert record.failure_kind == UpstreamFailureKind.TIMEOUT.value


@pytest.mark.asyncio
async def test_supabase_reachable_degrades_on_network_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_async_client(
        monkeypatch,
        _RecordingAsyncClient(
            get_exc=httpx.ConnectError(
                "network down",
                request=httpx.Request("GET", "https://example.supabase.co/rest/v1/platform_config"),
            )
        ),
    )
    with caplog.at_level(logging.WARNING, logger="app.core.upstream"):
        assert await _supabase_reachable() is False

    record = cast(
        _UpstreamLogRecord,
        next(r for r in caplog.records if r.message == "upstream_dependency_failed"),
    )
    assert record.dependency == "supabase_rest"
    assert record.failure_kind in {
        UpstreamFailureKind.NETWORK_ERROR.value,
        UpstreamFailureKind.UNKNOWN.value,
    }


@pytest.mark.asyncio
async def test_readiness_no_longer_probes_anon_openapi_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _patch_async_client(
        monkeypatch,
        _RecordingAsyncClient(get_response=_FakeResponse(200)),
    )
    assert await _supabase_reachable() is True
    url = client.get_calls[0]["url"]
    headers = client.get_calls[0]["headers"]
    assert "/rest/v1/platform_config" in url
    assert url.endswith("select=key&limit=1")
    assert url.rstrip("/") != "https://example.supabase.co/rest/v1"
    assert headers["apikey"] == "service-role-key"
    assert headers["Authorization"] == "Bearer service-role-key"
    assert headers["apikey"] != "anon-key"


def test_readyz_ok_when_data_api_probe_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording = _RecordingAsyncClient(get_response=_FakeResponse(200))
    _patch_async_client(monkeypatch, recording)

    body = client.get("/readyz").json()
    assert body["status"] == "ok"
    assert body["supabase"] == "ok"
    assert "[]" not in str(body)
    assert recording.get_calls


def test_readyz_does_not_return_upstream_response_bodies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_async_client(monkeypatch, _RecordingAsyncClient(get_response=_FakeResponse(200)))

    body = client.get("/readyz").json()
    assert set(body.keys()) == {"status", "supabase", "search_rpc", "search_embedding"}
    assert all(isinstance(value, str) for value in body.values())


def test_readyz_search_subcheck_remains_separate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording = _RecordingAsyncClient(
        get_response=_FakeResponse(200),
        post_response=_FakeResponse(500),
    )
    _patch_async_client(monkeypatch, recording)

    default_body = client.get("/readyz").json()
    assert default_body["status"] == "ok"
    assert default_body["supabase"] == "ok"
    assert default_body["search_rpc"] == "unchecked"
    assert not recording.post_calls

    search_body = client.get("/readyz", params={"checks": "search"}).json()
    assert search_body["status"] == "ok"
    assert search_body["supabase"] == "ok"
    assert search_body["search_rpc"] == "degraded"
    assert recording.post_calls


def test_readyz_search_failure_does_not_degrade_supabase_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _supabase_up() -> bool:
        return True

    async def _search_down() -> bool:
        return False

    monkeypatch.setattr(health_router, "_supabase_reachable", _supabase_up)
    monkeypatch.setattr(health_router, "_search_vector_rpc_present", _search_down)

    body = client.get("/readyz", params={"checks": "search"}).json()
    assert body["status"] == "ok"
    assert body["supabase"] == "ok"
    assert body["search_rpc"] == "degraded"


def test_readyz_service_role_not_exposed_in_public_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording = _RecordingAsyncClient(get_response=_FakeResponse(200))
    _patch_async_client(monkeypatch, recording)

    body = client.get("/readyz").json()
    blob = str(body).lower()
    assert "service-role-key" not in blob
    assert "service_role" not in blob
    assert recording.get_calls[0]["headers"]["Authorization"] == "Bearer service-role-key"


def test_readyz_logs_upstream_failure_for_data_api_401(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_async_client(monkeypatch, _RecordingAsyncClient(get_response=_FakeResponse(401)))
    with caplog.at_level(logging.WARNING, logger="app.core.upstream"):
        body = client.get("/readyz").json()

    assert body["status"] == "degraded"
    assert body["supabase"] == "degraded"
    record = cast(
        _UpstreamLogRecord,
        next(r for r in caplog.records if r.message == "upstream_dependency_failed"),
    )
    assert record.dependency == "supabase_rest"
    assert record.failure_kind == UpstreamFailureKind.UNEXPECTED_STATUS.value
    assert record.status_code == 401
