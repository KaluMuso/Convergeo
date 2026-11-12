from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from tests.test_listing_create import (
    CATEGORY_ID,
    FakeQuery,
    FakeSupabaseClient,
    _auth_headers,
    _base_payload,
)
from tests.test_listing_create import (
    fake_client as fake_client,
)
from tests.test_listing_create import (
    listing_client as listing_client,
)


def test_atomic_database_cap_denial_keeps_safe_api_contract(
    listing_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from postgrest.exceptions import APIError

    original = FakeQuery.execute

    def execute(query: FakeQuery) -> MagicMock:
        if query._pending_op == "insert" and query._parent is fake_client.tables["vendor_listings"]:
            raise APIError(
                {
                    "code": "PT403",
                    "message": "listing_cap_exceeded",
                    "details": "private SQL",
                    "hint": "",
                }
            )
        return original(query)

    monkeypatch.setattr(FakeQuery, "execute", execute)
    response = listing_client.post(
        "/vendor/listings", headers=_auth_headers(), json=_base_payload()
    )
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "listing_cap_exceeded"
    assert error["details"] == {"message_key": "vendor.caps.listing_limit"}
    assert "private SQL" not in response.text
    assert fake_client.tables["vendor_listings"].rows == []


@pytest.mark.parametrize("product_class", ["A", "B", "C"])
def test_quick_normal_classes_require_canonical_route_before_writing(
    listing_client: TestClient, fake_client: FakeSupabaseClient, product_class: str
) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(
            mode="quick_list",
            product_id=None,
            title_override="Normal offer",
            product_class=product_class,
            publish=False,
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "canonical_product_required"
    assert fake_client.tables["vendor_listings"].rows == []


@pytest.mark.parametrize(
    "category_id,description", [(None, "Complete offer description."), (CATEGORY_ID, "Too short")]
)
def test_standalone_requires_owned_category_and_description_before_writing(
    listing_client: TestClient,
    fake_client: FakeSupabaseClient,
    category_id: str | None,
    description: str,
) -> None:
    response = listing_client.post(
        "/vendor/listings",
        headers=_auth_headers(),
        json=_base_payload(
            mode="quick_list",
            product_id=None,
            title_override="Used chair",
            product_class="D",
            condition="used",
            defect_notes="Disclosed wear on one arm",
            category_id=category_id,
            description=description,
            publish=False,
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "standalone_details_required"
    assert fake_client.tables["vendor_listings"].rows == []


def test_database_release_policy_denial_is_actionable_without_sql_diagnostics(
    listing_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from postgrest.exceptions import APIError

    original = FakeQuery.execute

    def execute(query: FakeQuery) -> MagicMock:
        if query._pending_op == "insert" and query._parent is fake_client.tables["vendor_listings"]:
            raise APIError(
                {
                    "code": "23514",
                    "message": "product class C is not customer-released",
                    "details": "private SQL",
                    "hint": "",
                }
            )
        return original(query)

    monkeypatch.setattr(FakeQuery, "execute", execute)
    response = listing_client.post(
        "/vendor/listings", headers=_auth_headers(), json=_base_payload()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "listing_policy_blocked"
    assert "private SQL" not in response.text
    assert fake_client.tables["vendor_listings"].rows == []
