from __future__ import annotations

from fastapi.testclient import TestClient


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
