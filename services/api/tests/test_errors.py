from __future__ import annotations

import json
import logging
import sys

import pytest
from app.errors import unhandled_exception_handler
from app.logging import JsonFormatter
from fastapi.testclient import TestClient
from starlette.requests import Request


def test_app_error_envelope(client: TestClient) -> None:
    response = client.get("/test/app-error")
    assert response.status_code == 418
    body = response.json()
    assert body["error"]["code"] == "test_error"
    assert body["error"]["message"] == "Something went wrong"
    assert body["error"]["details"] == {"field": "value"}
    assert body["error"]["request_id"]
    assert response.headers.get("X-Request-ID") == body["error"]["request_id"]


def test_validation_error_envelope(client: TestClient) -> None:
    response = client.post("/test/validation", json={"count": "nope"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert "errors" in body["error"]["details"]
    assert body["error"]["request_id"]
    assert response.headers.get("X-Request-ID") == body["error"]["request_id"]


def test_unhandled_exception_is_generic(client: TestClient) -> None:
    response = client.get("/test/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "An unexpected error occurred"
    assert "secret" not in body["error"]["message"].lower()
    assert body["error"]["request_id"]
    assert response.headers.get("X-Request-ID") == body["error"]["request_id"]


def test_unhandled_exception_log_bounds_frames_without_sensitive_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(depth: int) -> None:
        if depth:
            fail(depth - 1)
        else:
            raise RuntimeError("SQL credential business payload")

    try:
        fail(40)
    except RuntimeError as exc:
        request = Request({"type": "http", "path": "/test/unhandled", "headers": []})
        request.state.request_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        with caplog.at_level(logging.ERROR, logger="app.errors"):
            response = unhandled_exception_handler(request, exc)
    else:
        pytest.fail("Expected the synthetic exception")

    assert response.status_code == 500
    records = [record for record in caplog.records if record.name == "app.errors"]
    assert len(records) == 1
    log = json.loads(JsonFormatter().format(records[0]))
    assert log["request_id"] == request.state.request_id
    assert log["exception_type"] == "builtins.RuntimeError"
    assert len(log["exception_frames"]) == 16
    assert all(frame.endswith(":fail") for frame in log["exception_frames"])
    assert "SQL credential business payload" not in json.dumps(log)
    assert "SQL credential business payload" not in caplog.text


def test_unhandled_exception_logs_safe_context_outside_except(
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/internal/reconciliation/daily-report",
            "query_string": b"",
            "headers": [],
        }
    )
    request.state.request_id = "test-request-id"
    try:
        raise RuntimeError("secret payment token 4111111111111111")
    except RuntimeError as caught:
        exc = caught

    assert sys.exc_info()[0] is None
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = unhandled_exception_handler(request, exc)

    record = next(record for record in caplog.records if record.name == "app.errors")
    log = json.loads(JsonFormatter().format(record))
    assert log["request_id"] == "test-request-id"
    assert log["path"] == "/internal/reconciliation/daily-report"
    assert log["exception_type"] == "builtins.RuntimeError"
    assert any("test_errors.py" in frame for frame in log["exception_frames"])
    assert "NoneType: None" not in json.dumps(log)
    assert "secret payment token" not in json.dumps(log)
    assert "4111111111111111" not in json.dumps(log)

    body = json.loads(bytes(response.body))
    assert response.status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "An unexpected error occurred"
    assert response.headers["X-Request-ID"] == "test-request-id"
