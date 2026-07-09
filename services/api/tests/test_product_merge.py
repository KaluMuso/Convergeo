from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.routers import products as products_router
from app.routers.admin_products import (
    DUPLICATE_SIMILARITY_THRESHOLD,
    ProductMergeError,
    ServiceRoleClient,
    find_duplicate_pairs,
    pg_trgm_similarity,
    transition_product_merge,
)
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
VALID_TOKEN = "valid.jwt.token"

CATEGORY_PHONES = "d0000027-0000-4000-8000-000000000001"
CATEGORY_FASHION = "d0000028-0000-4000-8000-000000000002"

SURVIVOR_ID = "a0000013-0000-4000-8000-000000000001"
LOSER_ID = "a0000014-0000-4000-8000-000000000002"
OTHER_ID = "a0000015-0000-4000-8000-000000000003"
CROSS_CAT_ID = "a0000016-0000-4000-8000-000000000004"
LISTING_ONE = "11111111-1111-1111-1111-111111111111"
LISTING_TWO = "22222222-2222-2222-2222-222222222222"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._selected_columns = "*"

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
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

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "neq" and row.get(column) == value:
                return False
            if op == "in" and row.get(column) not in value:
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._matches(row)]


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
            "products": FakeTable(),
            "vendor_listings": FakeTable(),
            "audit_log": FakeTable(),
        }

    @property
    def client(self) -> FakeSupabaseClient:
        return self

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _product_row(
    *,
    product_id: str,
    name: str,
    slug: str,
    category_id: str = CATEGORY_PHONES,
    status: str = "active",
    aliases: list[str] | None = None,
    merged_into_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": product_id,
        "name": name,
        "slug": slug,
        "brand": "Itel",
        "category_id": category_id,
        "status": status,
        "aliases": aliases or [],
        "merged_into_id": merged_into_id,
        "updated_at": "2026-07-01T00:00:00+00:00",
    }


def _listing_row(*, listing_id: str, product_id: str) -> dict[str, Any]:
    return {
        "id": listing_id,
        "product_id": product_id,
        "status": "active",
        "price_ngwee": 10000,
    }


@pytest.fixture
def merge_app() -> Any:
    return create_app()


@pytest.fixture
def merge_client(merge_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(merge_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_products.get_supabase_client", lambda: service_wrapper)
    return client


def _mock_verify(monkeypatch: pytest.MonkeyPatch, user_id: str = USER_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )


def _mock_roles(monkeypatch: pytest.MonkeyPatch, roles_by_user: dict[str, frozenset[str]]) -> None:
    def fake_load(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return roles_by_user.get(user_id, frozenset())

    monkeypatch.setattr("app.core.auth._load_user_roles", fake_load)


def _mock_audit_insert(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    inserted: list[dict[str, Any]] = []

    class AuditFakeQuery:
        def __init__(self, row: dict[str, Any]) -> None:
            self._row = row

        def execute(self) -> MagicMock:
            inserted.append(self._row)
            return MagicMock(data=[{**self._row, "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}])

    class AuditFakeTable:
        def insert(self, row: dict[str, Any]) -> AuditFakeQuery:
            return AuditFakeQuery(row)

    service_client = MagicMock()
    service_client.client.table.side_effect = (
        lambda name: AuditFakeTable() if name == "audit_log" else MagicMock()
    )
    monkeypatch.setattr(
        "app.core.admin_audit.get_supabase_service_client",
        lambda: service_client,
    )
    return inserted


def _seed_duplicate_candidates(fake: FakeSupabaseClient) -> None:
    fake.tables["products"].rows.extend(
        [
            _product_row(
                product_id=SURVIVOR_ID,
                name="Itel A70 Smartphone",
                slug="itel-a70",
            ),
            _product_row(
                product_id=LOSER_ID,
                name="Itel A70 Smart Phone",
                slug="itel-a70-alt",
                aliases=["a70"],
            ),
            _product_row(
                product_id=CROSS_CAT_ID,
                name="Itel A70 Smartphone",
                slug="itel-a70-fashion",
                category_id=CATEGORY_FASHION,
            ),
        ]
    )


def test_pg_trgm_similarity_matches_near_duplicates() -> None:
    score = pg_trgm_similarity("Itel A70 Smartphone", "Itel A70 Smart Phone")
    assert score >= DUPLICATE_SIMILARITY_THRESHOLD


def test_find_duplicate_pairs_same_category_only(fake_client: FakeSupabaseClient) -> None:
    _seed_duplicate_candidates(fake_client)
    pairs = find_duplicate_pairs(cast(ServiceRoleClient, fake_client))
    assert len(pairs) == 1
    ids = {str(pairs[0].product_a.id), str(pairs[0].product_b.id)}
    assert ids == {SURVIVOR_ID, LOSER_ID}
    assert pairs[0].similarity >= DUPLICATE_SIMILARITY_THRESHOLD


def test_find_duplicate_pairs_excludes_cross_category(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(product_id=SURVIVOR_ID, name="Blue Chitenge", slug="blue-chitenge"),
            _product_row(
                product_id=CROSS_CAT_ID,
                name="Blue Chitenge Wrap",
                slug="blue-chitenge-wrap",
                category_id=CATEGORY_FASHION,
            ),
        ]
    )
    pairs = find_duplicate_pairs(cast(ServiceRoleClient, fake_client))
    assert pairs == []


def test_merge_repoints_listings_aliases_and_resyncs_survivor(
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(
                product_id=SURVIVOR_ID,
                name="Itel A70 Smartphone",
                slug="itel-a70",
                aliases=["a70-phone"],
            ),
            _product_row(
                product_id=LOSER_ID,
                name="Itel A70 Smart Phone",
                slug="itel-a70-alt",
                aliases=["itel-alt"],
            ),
        ]
    )
    fake_client.tables["vendor_listings"].rows.extend(
        [
            _listing_row(listing_id=LISTING_ONE, product_id=LOSER_ID),
            _listing_row(listing_id=LISTING_TWO, product_id=LOSER_ID),
        ]
    )

    result, idempotent = transition_product_merge(
        actor_id=USER_ID,
        survivor_id=SURVIVOR_ID,
        loser_id=LOSER_ID,
        service_client=cast(ServiceRoleClient, fake_client),
    )

    assert idempotent is False
    assert result["listings_repointed"] == 2
    listings = fake_client.tables["vendor_listings"].rows
    assert all(row["product_id"] == SURVIVOR_ID for row in listings)

    loser = next(row for row in fake_client.tables["products"].rows if row["id"] == LOSER_ID)
    survivor = next(row for row in fake_client.tables["products"].rows if row["id"] == SURVIVOR_ID)
    assert loser["status"] == "merged"
    assert loser["merged_into_id"] == SURVIVOR_ID
    assert "itel-a70-alt" in survivor["aliases"]
    assert "itel-alt" in survivor["aliases"]
    assert survivor["updated_at"] != "2026-07-01T00:00:00+00:00"


def test_merged_product_slug_redirects_301(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(product_id=SURVIVOR_ID, name="Itel A70", slug="itel-a70"),
            _product_row(
                product_id=LOSER_ID,
                name="Itel A70 Alt",
                slug="itel-a70-alt",
                status="merged",
                merged_into_id=SURVIVOR_ID,
            ),
        ]
    )
    detail = products_router.build_product_detail(fake_client, "itel-a70-alt")
    assert isinstance(detail, RedirectResponse)
    assert detail.status_code == 301
    assert detail.headers["location"] == "/products/itel-a70"


def test_merge_idempotent_rerun_is_noop(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(product_id=SURVIVOR_ID, name="Itel A70", slug="itel-a70"),
            _product_row(
                product_id=LOSER_ID,
                name="Itel A70 Alt",
                slug="itel-a70-alt",
                status="merged",
                merged_into_id=SURVIVOR_ID,
            ),
        ]
    )
    fake_client.tables["vendor_listings"].rows.append(
        _listing_row(listing_id=LISTING_ONE, product_id=SURVIVOR_ID)
    )

    result, idempotent = transition_product_merge(
        actor_id=USER_ID,
        survivor_id=SURVIVOR_ID,
        loser_id=LOSER_ID,
        service_client=cast(ServiceRoleClient, fake_client),
    )
    assert idempotent is True
    assert result["listings_repointed"] == 0


def test_merge_guardrails_self_merge(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["products"].rows.append(
        _product_row(product_id=SURVIVOR_ID, name="Itel A70", slug="itel-a70")
    )
    with pytest.raises(ProductMergeError) as exc:
        transition_product_merge(
            actor_id=USER_ID,
            survivor_id=SURVIVOR_ID,
            loser_id=SURVIVOR_ID,
            service_client=cast(ServiceRoleClient, fake_client),
        )
    assert exc.value.http_status == 400


def test_merge_guardrails_cross_category(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(product_id=SURVIVOR_ID, name="Itel A70", slug="itel-a70"),
            _product_row(
                product_id=LOSER_ID,
                name="Itel A70",
                slug="itel-a70-alt",
                category_id=CATEGORY_FASHION,
            ),
        ]
    )
    with pytest.raises(ProductMergeError) as exc:
        transition_product_merge(
            actor_id=USER_ID,
            survivor_id=SURVIVOR_ID,
            loser_id=LOSER_ID,
            service_client=cast(ServiceRoleClient, fake_client),
        )
    assert exc.value.http_status == 409


def test_merge_guardrails_already_merged_into_other(fake_client: FakeSupabaseClient) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(product_id=SURVIVOR_ID, name="Itel A70", slug="itel-a70"),
            _product_row(product_id=LOSER_ID, name="Itel A70 Alt", slug="itel-a70-alt"),
            _product_row(product_id=OTHER_ID, name="Other", slug="other-phone"),
        ]
    )
    fake_client.tables["products"].rows[1]["status"] = "merged"
    fake_client.tables["products"].rows[1]["merged_into_id"] = OTHER_ID

    with pytest.raises(ProductMergeError) as exc:
        transition_product_merge(
            actor_id=USER_ID,
            survivor_id=SURVIVOR_ID,
            loser_id=LOSER_ID,
            service_client=cast(ServiceRoleClient, fake_client),
        )
    assert exc.value.http_status == 409


def test_duplicates_endpoint_requires_admin(
    merge_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = fake_client
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"customer"})})
    response = merge_client.get(
        "/admin/products/duplicates",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 403


def test_merge_endpoint_requires_admin(
    merge_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = fake_client
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"customer"})})
    response = merge_client.post(
        "/admin/products/merge",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"survivor_id": SURVIVOR_ID, "loser_id": LOSER_ID},
    )
    assert response.status_code == 403


def test_merge_endpoint_admin_success_writes_audit(
    merge_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client.tables["products"].rows.extend(
        [
            _product_row(product_id=SURVIVOR_ID, name="Itel A70", slug="itel-a70"),
            _product_row(product_id=LOSER_ID, name="Itel A70 Alt", slug="itel-a70-alt"),
        ]
    )
    fake_client.tables["vendor_listings"].rows.append(
        _listing_row(listing_id=LISTING_ONE, product_id=LOSER_ID)
    )
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch)

    response = merge_client.post(
        "/admin/products/merge",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"survivor_id": SURVIVOR_ID, "loser_id": LOSER_ID},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["listings_repointed"] == 1
    assert body["slug_redirect_from"] == "itel-a70-alt"
    assert body["slug_redirect_to"] == "itel-a70"
    assert "itel-a70-alt" in body["merged_aliases"]
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == "admin.products.merge"
