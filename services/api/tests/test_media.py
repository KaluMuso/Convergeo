from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from app.core.auth import CurrentUser
from app.errors import AppError
from app.main import create_app
from app.media.authz import VendorScope, _resolve_owned_vendor_id, require_vendor_scope
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

# Vendor-scope resolution (require_vendor_scope) fixtures.
OWNER_USER = "11111111-1111-1111-1111-111111111111"
OTHER_USER = "22222222-2222-2222-2222-222222222222"
OWNED_VENDOR_ID = "99999999-9999-9999-9999-999999999999"
OTHER_VENDOR_ID = "88888888-8888-8888-8888-888888888888"


class _FakeVendorsClient:
    """Minimal fake of the service-role client's ``vendors`` postgrest chain."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows
        self._filter: tuple[str, str] | None = None

    @property
    def client(self) -> _FakeVendorsClient:
        return self

    def table(self, name: str) -> _FakeVendorsClient:
        assert name == "vendors"
        self._filter = None
        return self

    def select(self, *_columns: str) -> _FakeVendorsClient:
        return self

    def eq(self, column: str, value: str) -> _FakeVendorsClient:
        self._filter = (column, value)
        return self

    def maybe_single(self) -> _FakeVendorsClient:
        return self

    def execute(self) -> SimpleNamespace:
        assert self._filter is not None
        column, value = self._filter
        matches = [row for row in self._rows if row.get(column) == value]
        return SimpleNamespace(data=matches[0] if matches else None)


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


# --- require_vendor_scope: DB-ownership resolution (M04-P02) ------------------


def test_resolve_owned_vendor_id_returns_db_vendor() -> None:
    client = _FakeVendorsClient([{"id": OWNED_VENDOR_ID, "owner_user_id": OWNER_USER}])
    assert _resolve_owned_vendor_id(client, OWNER_USER) == OWNED_VENDOR_ID


def test_resolve_owned_vendor_id_none_when_user_owns_no_vendor() -> None:
    client = _FakeVendorsClient([{"id": OTHER_VENDOR_ID, "owner_user_id": OTHER_USER}])
    assert _resolve_owned_vendor_id(client, OWNER_USER) is None


async def test_require_vendor_scope_resolves_owned_vendor_from_db() -> None:
    client = _FakeVendorsClient([{"id": OWNED_VENDOR_ID, "owner_user_id": OWNER_USER}])
    user = CurrentUser(id=OWNER_USER, roles=frozenset(), token="jwt")
    scope = await require_vendor_scope(current_user=user, service_client=client)
    assert scope == VendorScope(vendor_id=OWNED_VENDOR_ID)


async def test_require_vendor_scope_only_returns_callers_own_vendor() -> None:
    # Two vendors exist; the caller owns only one. Resolution keys off
    # current_user.id (DB-sourced), so it returns the caller's own vendor and
    # never the other — there is no JWT-claim path to spoof another vendor.
    client = _FakeVendorsClient(
        [
            {"id": OWNED_VENDOR_ID, "owner_user_id": OWNER_USER},
            {"id": OTHER_VENDOR_ID, "owner_user_id": OTHER_USER},
        ]
    )
    user = CurrentUser(id=OWNER_USER, roles=frozenset(), token="jwt")
    scope = await require_vendor_scope(current_user=user, service_client=client)
    assert scope.vendor_id == OWNED_VENDOR_ID
    assert scope.vendor_id != OTHER_VENDOR_ID


async def test_require_vendor_scope_403_when_caller_owns_no_vendor() -> None:
    client = _FakeVendorsClient([{"id": OTHER_VENDOR_ID, "owner_user_id": OTHER_USER}])
    user = CurrentUser(id=OWNER_USER, roles=frozenset(), token="jwt")
    with pytest.raises(AppError) as exc_info:
        await require_vendor_scope(current_user=user, service_client=client)
    assert exc_info.value.http_status == 403
    assert exc_info.value.code == "forbidden"
