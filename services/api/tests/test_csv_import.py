from __future__ import annotations

import io
from collections.abc import Generator
from typing import Any

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.services.kyc.caps import clear_vendor_cap_cache
from app.services.listings.csv_import import build_template_csv
from app.supabase_client import get_supabase_service_client
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_VENDOR_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COD_CAP_NGWEE = 50_000
VALID_TOKEN = "valid.jwt.token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._count_exact = False

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        if count == "exact":
            self._count_exact = True
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._pending_op = "update"
        self._payload = payload
        return self

    def execute(self) -> Any:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            self._parent.rows.append(row)
            return _mock_response([row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            rows = self._apply_filters(self._parent.rows)
            if not rows:
                return _mock_response(None if self._maybe_single else [])
            target = rows[0]
            target.update(self._payload)
            if self._maybe_single:
                return _mock_response(target)
            return _mock_response([target])

        rows = self._apply_filters(self._parent.rows)
        if self._maybe_single:
            return _mock_response(rows[0] if rows else None)
        count = len(rows) if self._count_exact else None
        return _mock_response(rows, count=count)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
            elif op == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(column) in allowed]
        return filtered


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "vendor_listings": FakeTable(),
            "vendor_quotas": FakeTable(),
            "platform_config": FakeTable(),
            "orders": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _mock_response(data: Any, *, count: int | None = None) -> Any:
    from unittest.mock import MagicMock

    return MagicMock(data=data, count=count)


def _seed_base(fake: FakeSupabaseClient, *, listing_count: int = 0, kyc_tier: int = 1) -> None:
    fake.tables["vendors"].rows.append(
        {
            "id": VENDOR_ID,
            "owner_user_id": USER_ID,
            "status": "active",
            "kyc_tier": kyc_tier,
        }
    )
    fake.tables["vendor_quotas"].rows.append(
        {
            "tier": kyc_tier,
            "max_listings": 30 if kyc_tier == 1 else 9999,
            "first_orders_cap_ngwee": COD_CAP_NGWEE if kyc_tier == 1 else None,
            "first_orders_count": 5 if kyc_tier == 1 else None,
            "payout_velocity": {"max_payouts_per_day": 1, "max_amount_ngwee_per_day": 100_000},
        }
    )
    fake.tables["platform_config"].rows.append(
        {"key": "cod_cap_ngwee", "value": COD_CAP_NGWEE}
    )
    for index in range(listing_count):
        fake.tables["vendor_listings"].rows.append(
            {
                "id": f"listing-{index:02d}",
                "vendor_id": VENDOR_ID,
                "sku": f"EXIST-{index:02d}",
                "title_override": f"Existing item {index}",
                "status": "active",
            }
        )


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> Any:
    from unittest.mock import MagicMock

    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.deps.get_supabase_client", lambda: iter([service_wrapper]))
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: Any) -> None:
    def mock_get_supabase_client() -> Any:
        return service_wrapper

    app.dependency_overrides[get_supabase_client] = mock_get_supabase_client
    app.dependency_overrides[get_supabase_service_client] = lambda: service_wrapper


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    clear_vendor_cap_cache()
    return FakeSupabaseClient()


@pytest.fixture
def import_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    _seed_base(fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


def _valid_row(sku: str, *, price_ngwee: int = 2500, title: str | None = None) -> dict[str, str]:
    return {
        "sku": sku,
        "title": title or f"Item {sku}",
        "price_ngwee": str(price_ngwee),
        "stock_mode": "tracked",
        "stock_qty": "10",
        "condition": "new",
        "wholesale": "false",
        "moq": "1",
        "status": "active",
    }


def _valid_json_row(
    sku: str,
    *,
    price_ngwee: int = 2500,
    title: str | None = None,
) -> dict[str, object]:
    return {
        "sku": sku,
        "title": title or f"Item {sku}",
        "price_ngwee": price_ngwee,
        "stock_mode": "tracked",
        "stock_qty": 10,
        "condition": "new",
        "wholesale": False,
        "moq": 1,
        "status": "active",
    }


def _rows_to_csv(rows: list[dict[str, str]]) -> bytes:
    if not rows:
        return b"sku,title,price_ngwee,stock_mode,stock_qty,condition\n"
    fieldnames = sorted({key for row in rows for key in row})
    buffer = io.StringIO()
    import csv

    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def test_mixed_hundred_row_import(
    import_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.tables["vendors"].rows[0]["kyc_tier"] = 2
    fake_client.tables["vendor_quotas"].rows.append(
        {
            "tier": 2,
            "max_listings": 9999,
            "first_orders_cap_ngwee": None,
            "first_orders_count": None,
            "payout_velocity": {},
        }
    )
    clear_vendor_cap_cache()

    rows: list[dict[str, str]] = []
    for index in range(100):
        if index % 10 == 0:
            rows.append(_valid_row(f"BAD-{index}", price_ngwee=0))
        elif index % 7 == 0:
            rows.append({**_valid_row(f"MISS-{index}"), "stock_qty": ""})
        else:
            rows.append(_valid_row(f"SKU-{index:03d}"))

    response = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "text/csv"},
        content=_rows_to_csv(rows),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 77
    assert body["rejected"] == 23
    assert len(body["rows"]) == 100

    for result in body["rows"]:
        source_index = result["row"] - 1
        if source_index % 10 == 0:
            assert result["ok"] is False
            assert any("price_ngwee" in error for error in result["errors"])
        elif source_index % 7 == 0:
            assert result["ok"] is False
            assert any("stock_qty" in error for error in result["errors"])
        else:
            assert result["ok"] is True
            assert result["listing_id"] is not None


def test_idempotent_reimport_updates_same_sku(
    import_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    payload = {"rows": [_valid_json_row("IDEM-001", price_ngwee=5000)]}
    first = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["accepted"] == 1
    first_id = first_body["rows"][0]["listing_id"]
    assert len(fake_client.tables["vendor_listings"].rows) == 1

    payload["rows"][0]["price_ngwee"] = 7500
    payload["rows"][0]["title"] = "Updated title"
    second = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["accepted"] == 1
    assert len(fake_client.tables["vendor_listings"].rows) == 1
    assert second_body["rows"][0]["listing_id"] == first_id
    stored = fake_client.tables["vendor_listings"].rows[0]
    assert stored["price_ngwee"] == 7500
    # SKU lives in its own column; title_override holds the real, un-encoded title.
    assert stored["sku"] == "IDEM-001"
    assert stored["title_override"] == "Updated title"


def test_import_stores_plain_display_title_not_encoded_sku(
    import_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    # Regression: title_override is the customer-facing display title (search
    # projection, PDP, cart, checkout all read it). The SKU must NOT be smuggled
    # into it — it belongs in the dedicated sku column.
    response = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json={"rows": [_valid_json_row("DISP-001", title="Fresh tomatoes per kg")]},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
    stored = fake_client.tables["vendor_listings"].rows[0]
    assert stored["title_override"] == "Fresh tomatoes per kg"
    assert stored["sku"] == "DISP-001"
    assert "sku:" not in str(stored["title_override"])


def test_cap_overflow_rejected_at_boundary_in_file_order(
    import_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.tables["vendor_listings"].rows.clear()
    for index in range(28):
        fake_client.tables["vendor_listings"].rows.append(
            {
                "id": f"listing-{index:02d}",
                "vendor_id": VENDOR_ID,
                "sku": f"EXIST-{index:02d}",
                "title_override": f"Existing item {index}",
                "status": "active",
            }
        )

    rows = [_valid_row(f"NEW-{index:02d}") for index in range(5)]
    response = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "text/csv"},
        content=_rows_to_csv(rows),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 2
    assert body["rejected"] == 3
    assert body["rows"][0]["ok"] is True
    assert body["rows"][1]["ok"] is True
    assert body["rows"][2]["ok"] is False
    assert "listing cap exceeded" in body["rows"][2]["errors"][0]
    assert body["rows"][3]["ok"] is False
    assert body["rows"][4]["ok"] is False
    assert len(fake_client.tables["vendor_listings"].rows) == 30


def test_vendor_id_in_csv_ignored_writes_under_caller(
    import_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    row = _valid_json_row("SCOPE-001")
    row["vendor_id"] = OTHER_VENDOR_ID
    response = import_client.post(
        "/listings/import",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json={"rows": [row]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 1
    stored = fake_client.tables["vendor_listings"].rows[0]
    assert stored["vendor_id"] == VENDOR_ID
    assert stored["vendor_id"] != OTHER_VENDOR_ID


def test_template_download(import_client: TestClient) -> None:
    response = import_client.get("/listings/import/template", headers=_auth_headers())
    assert response.status_code == 200
    assert "sku" in response.text
    assert response.headers["content-type"].startswith("text/csv")


def test_build_template_csv_has_example_rows() -> None:
    template = build_template_csv()
    assert "TOM-001" in template
    assert "price_ngwee" in template
