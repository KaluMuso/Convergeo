"""Regression coverage for bounded, privacy-safe dependency diagnostics."""

from __future__ import annotations

import errno
import logging
from typing import Protocol, cast

import httpx
import pytest
from app.core.upstream import UpstreamFailureKind, classify_httpx_error
from app.routers.health import _supabase_reachable


class _UpstreamLogRecord(Protocol):
    dependency: str
    failure_kind: str
    status_code: int


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.ReadTimeout("timed out"), UpstreamFailureKind.TIMEOUT),
        (
            httpx.ConnectError("reset", request=httpx.Request("GET", "https://example.test")),
            UpstreamFailureKind.NETWORK_ERROR,
        ),
    ],
)
def test_classify_httpx_error_defaults_to_safe_bounded_labels(
    exc: httpx.HTTPError,
    expected: UpstreamFailureKind,
) -> None:
    assert classify_httpx_error(exc) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (errno.ECONNRESET, UpstreamFailureKind.CONNECTION_RESET),
        (errno.ECONNREFUSED, UpstreamFailureKind.CONNECTION_REFUSED),
        (errno.ENETUNREACH, UpstreamFailureKind.NETWORK_UNREACHABLE),
    ],
)
def test_classify_httpx_error_uses_os_error_cause(
    number: int,
    expected: UpstreamFailureKind,
) -> None:
    exc = httpx.ConnectError(
        "transport failed",
        request=httpx.Request("GET", "https://example.test"),
    )
    exc.__cause__ = OSError(number, "transport failed")
    assert classify_httpx_error(exc) == expected


@pytest.mark.asyncio
async def test_readiness_rejects_non_success_supabase_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: dict[str, object] = {}

    class _Response:
        status_code = 401
        is_success = False

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            **_kwargs: object,
        ) -> _Response:
            captured["url"] = url
            captured["headers"] = headers or {}
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: _Client())
    with caplog.at_level(logging.WARNING, logger="app.core.upstream"):
        assert await _supabase_reachable() is False

    assert "platform_config" in str(captured["url"])
    assert "select=key" in str(captured["url"])
    assert captured["headers"] == {
        "apikey": "service-role-key",
        "Authorization": "Bearer service-role-key",
    }

    failure = [
        record for record in caplog.records if record.message == "upstream_dependency_failed"
    ]
    assert failure
    record = cast(_UpstreamLogRecord, failure[-1])
    assert record.dependency == "supabase_rest"
    assert record.failure_kind == "unexpected_status"
    assert record.status_code == 401
