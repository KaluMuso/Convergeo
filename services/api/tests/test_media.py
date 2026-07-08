from __future__ import annotations

from collections.abc import Generator

import pytest
from app.main import create_app
from app.media.authz import VendorScope, require_vendor_scope
from app.media.cloudinary_signing import (
    build_signed_params,
    parse_cloudinary_url,
    sign_upload_parameters,
)
from app.settings import get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient

CLOUDINARY_URL = "cloudinary://test-api-key:test-api-secret@test-cloud"
VENDOR_A = "vendor-a"
VENDOR_B = "vendor-b"


@pytest.fixture
def cloudinary_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDINARY_URL", CLOUDINARY_URL)
    get_settings.cache_clear()


@pytest.fixture
def media_client(cloudinary_env: None) -> Generator[TestClient, None, None]:
    app: FastAPI = create_app()

    async def override_vendor_scope() -> VendorScope:
        return VendorScope(vendor_id=VENDOR_A)

    app.dependency_overrides[require_vendor_scope] = override_vendor_scope
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_parse_cloudinary_url_golden() -> None:
    cloud_name, api_key, api_secret = parse_cloudinary_url(CLOUDINARY_URL)
    assert cloud_name == "test-cloud"
    assert api_key == "test-api-key"
    assert api_secret == "test-api-secret"


def test_sign_upload_parameters_cloudinary_golden_vector() -> None:
    params = {
        "eager": "w_400,h_300,c_pad|w_260,h_200,c_crop",
        "public_id": "sample_image",
        "timestamp": 1315060510,
    }
    signature = sign_upload_parameters(params, "abcd")
    assert signature == "bfd09f95f331f558cbd1320e67aa8d488770583e"


def test_build_signed_params_never_returns_api_secret() -> None:
    signed = build_signed_params(
        folder=f"listings/{VENDOR_A}",
        public_id="hero",
        timestamp=1315060510,
        api_secret="super-secret",
        allowed_formats="jpg,png,webp,avif",
        max_bytes=10_485_760,
    )
    assert "api_secret" not in signed
    assert "super-secret" not in str(signed.values())


def test_media_sign_returns_vendor_scoped_folder(media_client: TestClient) -> None:
    response = media_client.post(
        "/media/sign",
        json={"resource_kind": "listing", "public_id": "hero-image"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["folder"] == f"listings/{VENDOR_A}"
    assert body["cloud_name"] == "test-cloud"
    assert body["api_key"] == "test-api-key"
    assert body["allowed_formats"] == "jpg,png,webp,avif"
    assert body["signature"]
    assert "api_secret" not in body
    assert "test-api-secret" not in response.text


def test_media_sign_ignores_client_folder_injection(media_client: TestClient) -> None:
    response = media_client.post(
        "/media/sign",
        json={
            "resource_kind": "listing",
            "folder": f"listings/{VENDOR_B}/stolen",
            "public_id": "photo-1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["folder"] == f"listings/{VENDOR_A}"
    assert VENDOR_B not in body["folder"]


def test_media_sign_missing_auth_returns_envelope(cloudinary_env: None) -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post("/media/sign", json={"resource_kind": "listing"})
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"]


def test_media_sign_invalid_auth_returns_envelope(cloudinary_env: None) -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/media/sign",
            json={"resource_kind": "listing"},
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
    assert response.status_code in {401, 403}
    body = response.json()
    assert body["error"]["code"] in {"unauthorized", "forbidden"}
    assert body["error"]["request_id"]


def test_media_sign_wrong_resource_kind_returns_envelope(media_client: TestClient) -> None:
    response = media_client.post(
        "/media/sign",
        json={"resource_kind": "not-a-kind"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"


def test_media_sign_oversize_returns_envelope(media_client: TestClient) -> None:
    response = media_client.post(
        "/media/sign",
        json={
            "resource_kind": "listing",
            "file_size_bytes": 20_000_000,
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "file_too_large"
    assert body["error"]["request_id"]


def test_media_sign_invalid_public_id_returns_envelope(media_client: TestClient) -> None:
    response = media_client.post(
        "/media/sign",
        json={
            "resource_kind": "listing",
            "public_id": "../escape",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
