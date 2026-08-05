from __future__ import annotations

from fastapi.testclient import TestClient


def test_frontend_error_beacon_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/telemetry/frontend-errors",
        json={
            "message": "Test render failure",
            "digest": "abc123",
            "boundary": "route",
            "application": "customer",
            "locale": "en",
            "url": "https://vergeo5.com/en/checkout",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": True}


def test_frontend_error_beacon_rejects_oversized_message(client: TestClient) -> None:
    response = client.post(
        "/telemetry/frontend-errors",
        json={"message": "x" * 600},
    )
    assert response.status_code == 422
