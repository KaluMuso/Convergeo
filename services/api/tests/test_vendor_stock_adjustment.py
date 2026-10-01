"""HTTP/adapter controls only. SQL races live in the separate real-DB module."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from app.errors import AppError
from app.services.inventory.adjustment import adjust_stock
from fastapi.testclient import TestClient
from tests.test_listing_manage import (
    LISTING_A_ID,
    LISTING_B_ID,
    FakeSupabaseClient,
    FakeTable,
    _auth_headers,
)
from tests.test_listing_manage import (
    fake_client as fake_client,
)
from tests.test_listing_manage import (
    manage_client as manage_client,
)

REQUEST = {
    "operation_id": "aaaaaaaa-1234-1234-1234-aaaaaaaaaaaa",
    "location_id": "bbbbbbbb-1234-1234-1234-bbbbbbbbbbbb",
    "delta": -1,
    "reason": "damaged unit",
    "sale_unit": "each",
    "unit_step_milli": 1000,
}


def test_http_passes_full_immutable_input_without_absolute_stock_write(
    manage_client: TestClient, fake_client: FakeSupabaseClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rpc = Mock(return_value={"ok": True, "old_qty": 5, "new_qty": 4})
    monkeypatch.setattr("app.routers.vendor_listings_manage.adjust_stock", rpc)
    before = dict(fake_client.tables["vendor_listings"].rows[0])
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}/stock", headers=_auth_headers(), json=REQUEST
    )
    assert response.status_code == 200
    assert response.json()["new_qty"] == 4
    assert fake_client.tables["vendor_listings"].rows[0] == before
    for field in REQUEST:
        assert rpc.call_args.kwargs[f"p_{field}"] == REQUEST[field]
    assert rpc.call_args.kwargs["p_vendor_id"] == before["vendor_id"]


def test_foreign_listing_is_rejected_before_rpc(
    manage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rpc = Mock()
    monkeypatch.setattr("app.routers.vendor_listings_manage.adjust_stock", rpc)
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_B_ID}/stock", headers=_auth_headers(), json=REQUEST
    )
    assert response.status_code == 403
    rpc.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"stock_qty": 10},
        {"stock_qty": None},
        {"stock_mode": "always_available"},
        {"sale_unit": "kg", "unit_step_milli": 250},
        {"fulfilment_mode": "made_to_order"},
    ],
)
def test_general_editor_cannot_bypass_inventory_authority(
    manage_client: TestClient, fake_client: FakeSupabaseClient, payload: dict[str, Any]
) -> None:
    before = dict(fake_client.tables["vendor_listings"].rows[0])
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}", headers=_auth_headers(), json=payload
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stock.authority_required"
    assert fake_client.tables["vendor_listings"].rows[0] == before


@pytest.mark.parametrize(
    "patch",
    [
        {"operation_id": None},
        {"delta": True},
        {"delta": 1.5},
        {"delta": "2"},
        {"delta": 0},
        {"reason": " "},
        {"counted_total": 9},
        {"vendor_id": "other"},
        {"location_id": "invalid"},
    ],
)
def test_adjustment_input_is_strict(manage_client: TestClient, patch: dict[str, Any]) -> None:
    response = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}/stock", headers=_auth_headers(), json={**REQUEST, **patch}
    )
    assert response.status_code == 422


def test_price_save_does_not_restore_consumed_stock(
    manage_client: TestClient, fake_client: FakeSupabaseClient
) -> None:
    row = fake_client.tables["vendor_listings"].rows[0]
    row["stock_qty"] = 10
    loaded = manage_client.get(f"/vendor/listings/{LISTING_A_ID}", headers=_auth_headers())
    assert loaded.json()["stock_qty"] == 10
    row["stock_qty"] = 7
    saved = manage_client.patch(
        f"/vendor/listings/{LISTING_A_ID}", headers=_auth_headers(), json={"price_ngwee": 110_000}
    )
    assert saved.status_code == 200
    assert saved.json()["listing"]["stock_qty"] == 7
    assert row["stock_qty"] == 7


@pytest.mark.parametrize(
    "code", ["stock.operation_conflict", "stock.insufficient", "stock.invalid_location"]
)
def test_rejected_rpc_is_never_success(code: str) -> None:
    client = Mock()
    client.rpc.return_value.execute.return_value.data = {"ok": False, "status": 409, "code": code}
    with pytest.raises(AppError) as exc:
        adjust_stock(SimpleNamespace(client=client), p_operation_id=REQUEST["operation_id"])
    assert exc.value.http_status == 409
    assert exc.value.code == code


def test_uncertain_transport_requires_same_operation_retry() -> None:
    client = Mock()
    client.rpc.return_value.execute.side_effect = TimeoutError()
    with pytest.raises(AppError) as exc:
        adjust_stock(SimpleNamespace(client=client), p_operation_id=REQUEST["operation_id"])
    assert exc.value.http_status == 503
    assert exc.value.details["retry_same_operation"] is True


@pytest.mark.parametrize("branch_tracked", [False, True])
def test_protected_stock_read_uses_branch_rows_over_pool(
    manage_client: TestClient, fake_client: FakeSupabaseClient, branch_tracked: bool
) -> None:
    table = FakeTable()
    fake_client.tables["listing_location_stock"] = table
    listing = fake_client.tables["vendor_listings"].rows[0]
    if branch_tracked:
        table.rows.append(
            {
                "listing_id": LISTING_A_ID,
                "location_id": REQUEST["location_id"],
                "stock_qty": 7,
                "vendor_locations": {
                    "vendor_id": listing["vendor_id"],
                    "label": "Main shop",
                    "status": "active",
                },
            }
        )
    response = manage_client.get(f"/vendor/listings/{LISTING_A_ID}/stock", headers=_auth_headers())
    assert response.status_code == 200
    stock = response.json()
    assert stock["branch_tracked"] is branch_tracked
    if branch_tracked:
        assert stock["stock_qty"] is None
        assert stock["branches"][0]["stock_qty"] == 7
    else:
        assert stock["stock_qty"] == 5
    denied = manage_client.get(f"/vendor/listings/{LISTING_B_ID}/stock", headers=_auth_headers())
    assert denied.status_code == 403
