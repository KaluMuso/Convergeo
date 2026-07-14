from __future__ import annotations

from typing import Any

import pytest
from app.errors import AppError
from app.main import create_app
from app.routers.catalog import list_wholesale_supplies
from app.services.business.access import (
    BusinessAccess,
    get_business_access,
    require_wholesale_access,
    resolve_business_eligibility,
)
from app.services.business.store import upsert_application
from fastapi.testclient import TestClient

USER = "11111111-1111-1111-1111-111111111111"


# --- Minimal PostgREST-ish fake with a shared, mutable store ----------------
class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, store: dict[str, list[dict[str, Any]]], table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._single = False
        self._mode = "select"
        self._payload: Any = None

    def select(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[str]) -> _Query:
        self._filters.append(("in", column, list(values)))
        return self

    def order(self, *_a: Any, **_k: Any) -> _Query:
        return self

    def limit(self, n: int) -> _Query:
        self._limit = n
        return self

    def maybe_single(self) -> _Query:
        self._single = True
        return self

    def insert(self, row: Any) -> _Query:
        self._mode = "insert"
        self._payload = row
        return self

    def update(self, row: Any) -> _Query:
        self._mode = "update"
        self._payload = row
        return self

    def _apply(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = rows
        for op, col, val in self._filters:
            if op == "eq":
                out = [r for r in out if r.get(col) == val]
            elif op == "in":
                allowed = set(val)
                out = [r for r in out if r.get(col) in allowed]
        return out

    def execute(self) -> _Result:
        table_rows = self._store.setdefault(self._table, [])
        if self._mode == "insert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = [dict(r) for r in rows]
            table_rows.extend(inserted)
            return _Result([dict(r) for r in inserted])
        if self._mode == "update":
            matched = self._apply(table_rows)
            for row in matched:
                row.update(self._payload)
            return _Result([dict(r) for r in matched])
        rows = self._apply(list(table_rows))
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return _Result(dict(rows[0]) if rows else None)
        return _Result([dict(r) for r in rows])


class FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store

    def table(self, name: str) -> _Query:
        return _Query(self._store, name)


class FakeService:
    def __init__(self, client: FakeClient) -> None:
        self.client = client


def _service(store: dict[str, list[dict[str, Any]]]) -> FakeService:
    return FakeService(FakeClient(store))


# --- Resolver ---------------------------------------------------------------
class TestResolver:
    def test_verified_is_eligible(self) -> None:
        svc = _service({"business_buyers": [{"user_id": USER, "status": "verified"}]})
        access = resolve_business_eligibility(USER, svc)
        assert access.eligible is True
        assert access.status == "verified"

    def test_pending_is_not_eligible(self) -> None:
        svc = _service({"business_buyers": [{"user_id": USER, "status": "pending"}]})
        access = resolve_business_eligibility(USER, svc)
        assert access.eligible is False
        assert access.status == "pending"

    def test_no_application_is_not_eligible(self) -> None:
        access = resolve_business_eligibility(USER, _service({"business_buyers": []}))
        assert access.eligible is False
        assert access.status is None


class TestRequireWholesaleAccess:
    def test_allows_verified(self) -> None:
        require_wholesale_access(BusinessAccess(user_id=USER, status="verified", eligible=True))

    def test_blocks_consumer(self) -> None:
        with pytest.raises(AppError) as exc:
            require_wholesale_access(BusinessAccess(user_id=USER, status=None, eligible=False))
        assert exc.value.code == "business.wholesale_forbidden"
        assert exc.value.http_status == 403


# --- Application lifecycle --------------------------------------------------
class TestUpsertApplication:
    def test_new_application_is_pending(self) -> None:
        store: dict[str, list[dict[str, Any]]] = {"business_buyers": []}
        row = upsert_application(
            _service(store),
            user_id=USER,
            legal_name="Acme Ltd",
            registration_no="PACRA-123",
            tpin=None,
        )
        assert row["status"] == "pending"
        assert store["business_buyers"][0]["user_id"] == USER

    def test_rejected_can_reapply(self) -> None:
        store = {
            "business_buyers": [
                {"user_id": USER, "status": "rejected", "legal_name": "Old"}
            ]
        }
        row = upsert_application(
            _service(store),
            user_id=USER,
            legal_name="Acme Ltd",
            registration_no="PACRA-123",
            tpin="1000000000",
        )
        assert row["status"] == "pending"
        assert row["legal_name"] == "Acme Ltd"

    def test_verified_cannot_resubmit(self) -> None:
        store = {"business_buyers": [{"user_id": USER, "status": "verified"}]}
        with pytest.raises(AppError) as exc:
            upsert_application(
                _service(store),
                user_id=USER,
                legal_name="Acme Ltd",
                registration_no="PACRA-123",
                tpin=None,
            )
        assert exc.value.code == "business.already_decided"
        assert exc.value.http_status == 409


# --- Wholesale supplies feed ------------------------------------------------
def _supplies_store() -> dict[str, list[dict[str, Any]]]:
    return {
        "vendor_listings": [
            {
                "id": "L1",
                "vendor_id": "V1",
                "product_id": "P1",
                "title_override": "WL1",
                "condition": "new",
                "price_ngwee": 50_000,
                "moq": 10,
                "price_tiers": [{"min_qty": 10, "price_ngwee": 45_000}],
                "status": "active",
                "wholesale": True,
            },
            {
                "id": "L2",
                "vendor_id": "V2",  # suspended vendor — must be excluded
                "product_id": None,
                "title_override": "WL2",
                "condition": "new",
                "price_ngwee": 30_000,
                "moq": 5,
                "price_tiers": None,
                "status": "active",
                "wholesale": True,
            },
        ],
        "vendors": [
            {"id": "V1", "slug": "v1", "display_name": "Vendor One", "status": "active"},
            {"id": "V2", "slug": "v2", "display_name": "Vendor Two", "status": "suspended"},
        ],
        "products": [{"id": "P1", "slug": "p1", "name": "Product One", "status": "active"}],
        "listing_images": [
            {"listing_id": "L1", "cloudinary_public_id": "img1", "position": 1}
        ],
    }


class TestWholesaleSupplies:
    def test_only_active_vendor_listings_with_b2b_fields(self) -> None:
        client = FakeClient(_supplies_store())
        response = list_wholesale_supplies(client, limit=48)
        assert response.total == 1
        item = response.items[0]
        assert item.id == "L1"
        assert item.title == "Product One"
        assert item.product_slug == "p1"
        assert item.vendor_name == "Vendor One"
        assert item.wholesale is True
        assert item.moq == 10
        assert item.price_tiers == [{"min_qty": 10, "price_ngwee": 45_000}]
        assert item.image_public_id == "img1"


class TestWholesaleEndpointGating:
    def test_guest_wholesale_request_is_forbidden(self) -> None:
        from app.deps import get_supabase_client

        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: _service(_supplies_store())
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/catalog/listings?wholesale=true")
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "business.wholesale_forbidden"

    def test_verified_business_sees_supplies(self) -> None:
        from app.deps import get_supabase_client

        app = create_app()
        app.dependency_overrides[get_supabase_client] = lambda: _service(_supplies_store())
        app.dependency_overrides[get_business_access] = lambda: BusinessAccess(
            user_id=USER, status="verified", eligible=True
        )
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/catalog/listings?wholesale=true")
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["wholesale"] is True
        assert body["items"][0]["moq"] == 10
