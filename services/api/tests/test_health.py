from __future__ import annotations

from fastapi.testclient import TestClient


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
    assert "supabase_project_ref" in body
    blob = str(body).lower()
    assert "service_role" not in blob
    assert "anon-key" not in blob
    assert "password" not in blob


def test_request_id_header_generated(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_request_id_header_echoed(client: TestClient) -> None:
    request_id = "550e8400-e29b-41d4-a716-446655440000"
    response = client.get("/healthz", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
