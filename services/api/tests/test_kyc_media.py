from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.media.authz import VendorScope, require_vendor_scope
from fastapi import FastAPI
from fastapi.testclient import TestClient

VENDOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _FakeBucket:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        self._recorder["path"] = path
        return {"signed_url": f"https://stack.local/upload/{path}?token=abc", "token": "abc"}


class _FakeStorage:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    def from_(self, bucket: str) -> _FakeBucket:
        self._recorder["bucket"] = bucket
        return _FakeBucket(self._recorder)


class _FakeClient:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self.storage = _FakeStorage(recorder)


class _FakeServiceClient:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self.client = _FakeClient(recorder)


def _make_client(vendor_id: str) -> tuple[TestClient, dict[str, Any]]:
    recorder: dict[str, Any] = {}
    app: FastAPI = create_app()

    async def override_vendor_scope() -> VendorScope:
        return VendorScope(vendor_id=vendor_id)

    def override_service_client() -> _FakeServiceClient:
        return _FakeServiceClient(recorder)

    app.dependency_overrides[require_vendor_scope] = override_vendor_scope
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False), recorder


@pytest.fixture
def vendor_a_client() -> Generator[tuple[TestClient, dict[str, Any]], None, None]:
    client, recorder = _make_client(VENDOR_A)
    with client:
        yield client, recorder


def test_sign_returns_vendor_scoped_private_signed_upload(
    vendor_a_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, recorder = vendor_a_client
    resp = client.post(
        "/media/kyc-doc/sign",
        json={"resource_kind": "kyc_doc", "doc_type": "nrc", "file_size_bytes": 500_000},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bucket"] == "kyc-docs"
    assert body["path"].startswith(f"kyc/{VENDOR_A}/nrc-")
    assert body["token"] == "abc"
    assert body["signed_url"].startswith("https://stack.local/upload/")
    # Path was pinned to the caller's vendor folder in the private bucket.
    assert recorder["bucket"] == "kyc-docs"
    assert recorder["path"].startswith(f"kyc/{VENDOR_A}/")


def test_path_is_scoped_to_the_authenticated_vendor() -> None:
    # A different vendor scope must never sign into vendor A's folder.
    client, recorder = _make_client(VENDOR_B)
    with client:
        resp = client.post(
            "/media/kyc-doc/sign",
            json={"resource_kind": "kyc_doc", "doc_type": "selfie", "file_size_bytes": 1000},
        )
    assert resp.status_code == 200, resp.text
    assert recorder["path"].startswith(f"kyc/{VENDOR_B}/selfie-")
    assert VENDOR_A not in recorder["path"]


def test_oversize_document_returns_400(
    vendor_a_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, _ = vendor_a_client
    resp = client.post(
        "/media/kyc-doc/sign",
        json={"resource_kind": "kyc_doc", "doc_type": "nrc", "file_size_bytes": 10_485_761},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "file_too_large"


def test_invalid_doc_type_rejected(
    vendor_a_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, _ = vendor_a_client
    resp = client.post(
        "/media/kyc-doc/sign",
        json={"resource_kind": "kyc_doc", "doc_type": "passport", "file_size_bytes": 1000},
    )
    assert resp.status_code == 422
