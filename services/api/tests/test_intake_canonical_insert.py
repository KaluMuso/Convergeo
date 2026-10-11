"""Same-client RPC boundary: no fallback or success from malformed receipts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.errors import AppError
from app.services.intake.canonical_insert import insert_intake_class_a_listing
from postgrest.exceptions import APIError

VENDOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PRODUCT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CATEGORY = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def call(client: MagicMock) -> dict[str, object]:
    return insert_intake_class_a_listing(
        SimpleNamespace(client=client),
        vendor_id=VENDOR,
        product_id=PRODUCT,
        expected_category_id=CATEGORY,
        payload={"price_ngwee": 350_000},
    )


def test_same_client_exact_params_and_valid_receipt() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [
        {"id": LISTING, "status": "draft", "product_id": PRODUCT}
    ]
    assert call(client) == {"id": LISTING, "status": "draft", "product_id": PRODUCT}
    client.rpc.assert_called_once_with(
        "insert_intake_class_a_listing",
        {
            "p_vendor_id": VENDOR,
            "p_product_id": PRODUCT,
            "p_expected_category_id": CATEGORY,
            "p_listing_payload": {"price_ngwee": 350_000},
        },
    )
    client.table.assert_not_called()


@pytest.mark.parametrize(
    "message,reason",
    [
        ("intake_canonical_unavailable", "canonicalUnavailable"),
        ("intake_canonical_class", "unsupportedClass"),
        ("intake_canonical_units", "unsupported_mapping"),
        ("intake_canonical_category", "canonicalCategory"),
    ],
)
def test_canonical_error_maps_without_fallback(message: str, reason: str) -> None:
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = APIError(
        {
            "code": "23514",
            "message": message,
            "details": None,
            "hint": None,
        }
    )
    with pytest.raises(AppError) as exc:
        call(client)
    assert exc.value.http_status == 422
    assert exc.value.details["reason"] == reason
    client.table.assert_not_called()


@pytest.mark.parametrize("code", ["42501", "22023", "PGRST202", "08006"])
def test_failure_is_closed_and_does_not_echo_database_details(code: str) -> None:
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = APIError(
        {
            "code": code,
            "message": "private database detail",
            "details": None,
            "hint": None,
        }
    )
    with pytest.raises(AppError) as exc:
        call(client)
    assert exc.value.http_status == 500
    assert "private" not in exc.value.message
    client.table.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        [{"id": LISTING, "status": "active", "product_id": PRODUCT}],
        [{"id": "bad", "status": "draft", "product_id": PRODUCT}],
        [{"id": LISTING, "status": "draft", "product_id": CATEGORY}],
        [{"id": LISTING, "status": "draft", "product_id": PRODUCT}] * 2,
    ],
)
def test_invalid_receipt_cannot_report_success(data: object) -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = data
    with pytest.raises(AppError) as exc:
        call(client)
    assert exc.value.http_status == 500
    client.table.assert_not_called()
