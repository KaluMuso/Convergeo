"""Vendor category pickers and creation honour admin publish/block (20261127130000)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.test_listing_create import (  # noqa: F401 - fixtures
    CATEGORY_ID,
    FakeSupabaseClient,
    _auth_headers,
    fake_client,
    listing_client,
)


def test_category_options_hide_blocked_and_vendor_hidden(
    listing_client: TestClient,  # noqa: F811
    fake_client: FakeSupabaseClient,  # noqa: F811 - pytest fixtures
) -> None:
    rows = fake_client.tables["categories"].rows
    rows.append(
        {
            "id": CATEGORY_ID,
            "name": "Electronics",
            "commission_key": "electronics",
            "prohibited": False,
            "status": "published",
            "show_in_vendor": True,
        }
    )
    rows.append(
        {
            "id": "blocked-cat",
            "name": "B",
            "commission_key": "default",
            "prohibited": False,
            "status": "blocked",
        }
    )
    rows.append(
        {
            "id": "hidden-cat",
            "name": "H",
            "commission_key": "default",
            "prohibited": False,
            "status": "published",
            "show_in_vendor": False,
        }
    )
    response = listing_client.get("/vendor/listings/categories", headers=_auth_headers())
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [CATEGORY_ID]


def test_new_listing_in_blocked_category_is_rejected(
    fake_client: FakeSupabaseClient,  # noqa: F811
) -> None:
    from app.routers.vendor_listings import _load_category_commission_key

    fake_client.tables["categories"].rows.append(
        {"id": CATEGORY_ID, "name": "E", "commission_key": "e", "status": "blocked"}
    )

    class Wrapper:
        client = fake_client

    try:
        _load_category_commission_key(Wrapper(), CATEGORY_ID)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "category_unavailable"
    else:
        raise AssertionError("blocked category must be rejected for new listings")
