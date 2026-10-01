from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.test_csv_import import (
    DEFAULT_PRODUCT_ID,
    FakeQuery,
    FakeSupabaseClient,
    _auth_headers,
    _rows_to_csv,
    _valid_json_row,
    _valid_row,
)
from tests.test_csv_import import (
    fake_client as fake_client,
)
from tests.test_csv_import import (
    import_client as import_client,
)


@pytest.mark.parametrize("status", ["draft", "active"])
def test_new_normal_csv_requires_canonical_product_before_insert(
    import_client: TestClient, fake_client: FakeSupabaseClient, status: str
) -> None:
    row = _valid_row("NO-PRODUCT")
    row.pop("product_id")
    row["status"] = status
    response = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "text/csv"},
        content=_rows_to_csv([row]),
    )
    assert response.status_code == 200
    assert response.json()["rows"][0]["errors"] == ["listings.import.errors.canonicalRequired"]
    assert response.json()["accepted"] == 0
    assert fake_client.tables["vendor_listings"].rows == []


def test_preview_preserves_existing_canonical_binding_when_product_omitted(
    import_client: TestClient, fake_client: FakeSupabaseClient
) -> None:
    row = _valid_json_row("EXISTING-PRODUCT")
    created = import_client.post("/listings/import", headers=_auth_headers(), json={"rows": [row]})
    assert created.json()["accepted"] == 1
    row.pop("product_id")
    response = import_client.post(
        "/listings/import/preview", headers=_auth_headers(), json={"rows": [row]}
    )
    preview = response.json()["rows"][0]
    assert preview["ok"] is True
    assert preview["product_id"] == DEFAULT_PRODUCT_ID
    assert preview["errors"] == []
    assert len(fake_client.tables["vendor_listings"].rows) == 1


@pytest.mark.parametrize(
    "code,message,expected",
    [
        ("PT403", "listing_cap_exceeded", "listingCap"),
        ("XX000", "SQL diagnostic with private_internal_table", "databaseFailure"),
    ],
)
def test_import_persistence_returns_safe_codes_not_database_diagnostics(
    import_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    message: str,
    expected: str,
) -> None:
    from postgrest.exceptions import APIError

    original = FakeQuery.execute

    def execute(query: FakeQuery) -> Any:
        if query._pending_op == "insert":
            raise APIError(
                {"code": code, "message": message, "details": "private details", "hint": ""}
            )
        return original(query)

    monkeypatch.setattr(FakeQuery, "execute", execute)
    response = import_client.post(
        "/listings/import", headers=_auth_headers(), json={"rows": [_valid_json_row("DB-ERROR")]}
    )
    assert response.status_code == 200
    assert response.json()["rows"][0]["errors"] == [f"listings.import.errors.{expected}"]
    assert "private" not in response.text
    assert message not in response.text
    assert fake_client.tables["vendor_listings"].rows == []


def test_import_validation_uses_stable_integer_and_duplicate_sku_codes(
    import_client: TestClient, fake_client: FakeSupabaseClient
) -> None:
    invalid = _valid_row("BAD-INTEGER")
    invalid["price_ngwee"] = "1.25"
    duplicate = _valid_row("DUPLICATE")
    response = import_client.post(
        "/listings/import",
        headers=_auth_headers(),
        json={"raw_rows": [invalid, duplicate, duplicate]},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["rows"][0]["errors"] == ["listings.import.errors.invalidInteger"]
    assert result["rows"][2]["errors"] == ["listings.import.errors.duplicateSku"]
    assert result["accepted"] == 1
    assert result["rejected"] == 2
    assert len(fake_client.tables["vendor_listings"].rows) == 1
