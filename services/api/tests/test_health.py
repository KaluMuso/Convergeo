from __future__ import annotations

import logging
from typing import Protocol, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient


class _CorrelatedLogRecord(Protocol):
    request_id: str
    path: str
    method: str
    status_code: int
    duration_ms: float


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
