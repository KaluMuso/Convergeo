from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.services_listings import (
    FAST_RESPONSE_SECONDS,
    SAME_DAY_RESPONSE_SECONDS,
    build_browse_response,
    compute_first_response_seconds,
    response_time_tier,
    response_time_tier_from_samples,
    response_time_tier_from_seconds,
)
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SERVICE_ACTIVE_ID = "a1000000-0000-4000-8000-000000000001"
SERVICE_DRAFT_ID = "a1000000-0000-4000-8000-000000000002"
SERVICE_OTHER_ID = "a1000000-0000-4000-8000-000000000003"
JOB_A_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._order: tuple[str, bool] | None = None
        self._ilike_filters: list[tuple[str, str]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
        return self

    def ilike(self, column: str, pattern: str) -> FakeQuery:
        self._ilike_filters.append((column, pattern))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
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
            self._parent.store.sync_search_for_service(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
                    self._parent.store.sync_search_for_service(row)
            if self._maybe_single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq":
                if column == "vendors.status":
                    vendor = row.get("vendors")
                    if isinstance(vendor, dict) and vendor.get("status") != value:
                        return False
                    if isinstance(vendor, list) and vendor and vendor[0].get("status") != value:
                        return False
                elif row.get(column) != value:
                    return False
            if op == "in" and row.get(column) not in set(value):
                return False
        for column, pattern in self._ilike_filters:
            haystack = str(row.get(column) or "").lower()
            needle = pattern.strip("%").lower()
            if needle not in haystack:
                return False
        return True

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in rows if self._matches(row)]


class FakeTable:
    def __init__(self, store: FakeSupabaseClient, name: str) -> None:
        self.store = store
        self.name = name
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
            "vendors": FakeTable(self, "vendors"),
            "services": FakeTable(self, "services"),
            "jobs": FakeTable(self, "jobs"),
            "job_quotes": FakeTable(self, "job_quotes"),
            "search_documents": FakeTable(self, "search_documents"),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]

    def sync_search_for_service(self, service_row: dict[str, Any]) -> None:
        service_id = str(service_row.get("id") or "")
        vendor_id = str(service_row.get("vendor_id") or "")
        vendor_rows = [
            row for row in self.tables["vendors"].rows if str(row.get("id")) == vendor_id
        ]
        vendor_status = vendor_rows[0].get("status") if vendor_rows else None
        is_public = service_row.get("status") == "active" and vendor_status == "active"
        docs = self.tables["search_documents"].rows
        existing = next(
            (
                row
                for row in docs
                if row.get("entity_kind") == "service" and str(row.get("entity_id")) == service_id
            ),
            None,
        )
        if is_public:
            payload = {
                "entity_kind": "service",
                "entity_id": service_id,
                "title": service_row.get("title"),
                "body": service_row.get("description") or "",
                "category_path": service_row.get("category"),
                "price_min_ngwee": service_row.get("from_price_ngwee"),
                "is_public": True,
            }
            if existing is None:
                docs.append(payload)
            else:
                existing.update(payload)
        elif existing is not None:
            existing["is_public"] = False


def _vendor_row(
    *,
    vendor_id: str = VENDOR_A_ID,
    owner_user_id: str = USER_A_ID,
    caps_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": vendor_id,
        "owner_user_id": owner_user_id,
        "status": "active",
        "slug": "provider-a",
        "display_name": "Provider A",
        "preferred_badge": True,
        "caps_snapshot": caps_snapshot or {},
    }


def _service_row(
    *,
    service_id: str,
    vendor_id: str = VENDOR_A_ID,
    category: str = "home-services",
    status: str = "active",
    service_area: str = "Lusaka",
    from_price_ngwee: int | None = 35000,
    includes: list[str] | None = None,
) -> dict[str, Any]:
    vendor = next(
        (
            row
            for row in [
                _vendor_row(vendor_id=VENDOR_A_ID),
                _vendor_row(vendor_id=VENDOR_B_ID, owner_user_id=USER_B_ID, caps_snapshot={}),
            ]
            if row["id"] == vendor_id
        ),
        _vendor_row(vendor_id=vendor_id),
    )
    return {
        "id": service_id,
        "vendor_id": vendor_id,
        "category": category,
        "title": "Pipe Repair",
        "description": "Fast plumbing in Lusaka",
        "service_area": service_area,
        "from_price_ngwee": from_price_ngwee,
        "portfolio_images": ["services/pipe-1"],
        "includes": ["On-site visit", "Cleanup after work"] if includes is None else includes,
        "status": status,
        "updated_at": "2026-07-09T10:00:00Z",
        "vendors": vendor,
    }


def _seed_store(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            _vendor_row(),
            _vendor_row(vendor_id=VENDOR_B_ID, owner_user_id=USER_B_ID),
        ]
    )
    fake.tables["services"].rows.extend(
        [
            _service_row(service_id=SERVICE_ACTIVE_ID, category="home-services", status="active"),
            _service_row(
                service_id=SERVICE_DRAFT_ID,
                category="beauty",
                status="draft",
                service_area="Ndola",
                from_price_ngwee=None,
            ),
            _service_row(
                service_id=SERVICE_OTHER_ID,
                vendor_id=VENDOR_B_ID,
                category="auto",
                status="active",
                service_area="Kitwe",
            ),
        ]
    )
    for row in fake.tables["services"].rows:
        fake.sync_search_for_service(row)


def _mock_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(token: str, settings: Any) -> dict[str, Any]:
        _ = settings
        if token == TOKEN_A:
            return {"sub": USER_A_ID, "exp": 9_999_999_999}
        if token == TOKEN_B:
            return {"sub": USER_B_ID, "exp": 9_999_999_999}
        raise ValueError("invalid token")

    def roles(user_id: str, service_client: Any) -> frozenset[str]:
        _ = service_client
        return frozenset({"vendor"})

    monkeypatch.setattr("app.core.auth.verify_supabase_jwt", verify)
    monkeypatch.setattr("app.core.auth._load_user_roles", roles)


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.deps.get_supabase_client", lambda: iter([service_wrapper]))
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    _seed_store(client)
    return client


@pytest.fixture
def services_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (FAST_RESPONSE_SECONDS - 1, "fast"),
        (FAST_RESPONSE_SECONDS, "same_day"),
        (SAME_DAY_RESPONSE_SECONDS - 1, "same_day"),
        (SAME_DAY_RESPONSE_SECONDS, "slow"),
        (SAME_DAY_RESPONSE_SECONDS + 3600, "slow"),
    ],
)
def test_response_time_tier_boundaries(seconds: float, expected: str) -> None:
    assert response_time_tier_from_seconds(seconds) == expected


def test_response_time_tier_median_fixture() -> None:
    assert response_time_tier_from_samples([8000, 10000, 12000]) == "same_day"
    assert response_time_tier_from_samples([900, 1200, 1500]) == "fast"
    assert response_time_tier_from_samples([90000, 100000]) == "slow"
    assert response_time_tier_from_samples([]) is None


def test_response_time_tier_uses_cached_caps_snapshot() -> None:
    job_created = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    quote_created = job_created + timedelta(hours=10)
    tier = response_time_tier(
        quote_rows=[{"job_id": JOB_A_ID, "created_at": quote_created.isoformat()}],
        job_rows_by_id={JOB_A_ID: {"id": JOB_A_ID, "created_at": job_created.isoformat()}},
        caps_snapshot={"response_time_tier": "fast"},
    )
    assert tier == "fast"


def test_compute_first_response_seconds() -> None:
    job_created = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    quote_created = job_created + timedelta(minutes=90)
    assert compute_first_response_seconds(job_created, quote_created) == 5400.0


def test_browse_filters_vertical_and_area(fake_client: FakeSupabaseClient) -> None:
    all_items = build_browse_response(fake_client, category=None, area=None)
    assert all_items.total == 2

    home = build_browse_response(fake_client, category="home-services", area=None)
    assert home.total == 1
    assert home.items[0].category == "home-services"

    lusaka = build_browse_response(fake_client, category=None, area="Lusaka")
    assert lusaka.total == 1
    assert lusaka.items[0].service_area == "Lusaka"

    empty = build_browse_response(fake_client, category="tailoring", area="Lusaka")
    assert empty.total == 0


def test_public_browse_hides_draft(services_client: TestClient) -> None:
    response = services_client.get("/services")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert SERVICE_ACTIVE_ID in ids
    assert SERVICE_DRAFT_ID not in ids


def test_public_detail_optional_from_price(
    services_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    priced = services_client.get(f"/services/{SERVICE_ACTIVE_ID}")
    assert priced.status_code == 200
    assert priced.json()["from_price_ngwee"] == 35000

    fake_client.tables["services"].rows.append(
        _service_row(
            service_id="a1000000-0000-4000-8000-000000000099",
            from_price_ngwee=None,
            status="active",
        )
    )
    fake_client.sync_search_for_service(fake_client.tables["services"].rows[-1])

    unpriced = services_client.get("/services/a1000000-0000-4000-8000-000000000099")
    assert unpriced.status_code == 200
    assert unpriced.json()["from_price_ngwee"] is None


def test_public_detail_returns_includes(services_client: TestClient) -> None:
    response = services_client.get(f"/services/{SERVICE_ACTIVE_ID}")
    assert response.status_code == 200
    assert response.json()["includes"] == ["On-site visit", "Cleanup after work"]


def test_create_normalizes_includes(services_client: TestClient) -> None:
    create = services_client.post(
        "/vendor/services",
        headers=_auth_headers(),
        json={
            "category": "cleaning",
            "title": "Deep Clean",
            # Whitespace-only and blank entries are dropped; the rest are trimmed.
            "includes": ["  Mop & polish  ", "", "   ", "Window wash"],
            "status": "draft",
        },
    )
    assert create.status_code == 200
    assert create.json()["service"]["includes"] == ["Mop & polish", "Window wash"]


def test_draft_detail_not_found(services_client: TestClient) -> None:
    response = services_client.get(f"/services/{SERVICE_DRAFT_ID}")
    assert response.status_code == 404


def test_vendor_b_cannot_update_vendor_a_service(
    services_client: TestClient,
) -> None:
    response = services_client.patch(
        f"/vendor/services/{SERVICE_ACTIVE_ID}",
        headers=_auth_headers(TOKEN_B),
        json={"title": "Hijacked"},
    )
    assert response.status_code == 404


def test_vendor_create_and_list(services_client: TestClient) -> None:
    create = services_client.post(
        "/vendor/services",
        headers=_auth_headers(),
        json={
            "category": "cleaning",
            "title": "Office Cleaning",
            "service_area": "Lusaka",
            "status": "draft",
        },
    )
    assert create.status_code == 200
    body = create.json()["service"]
    assert body["status"] == "draft"
    assert body["category"] == "cleaning"

    listing = services_client.get("/vendor/services", headers=_auth_headers())
    assert listing.status_code == 200
    titles = {item["title"] for item in listing.json()["items"]}
    assert "Office Cleaning" in titles


def test_active_service_projects_to_search_documents(fake_client: FakeSupabaseClient) -> None:
    docs = fake_client.tables["search_documents"].rows
    active_doc = next(
        row
        for row in docs
        if row.get("entity_kind") == "service" and row.get("entity_id") == SERVICE_ACTIVE_ID
    )
    assert active_doc["is_public"] is True
    assert active_doc["title"] == "Pipe Repair"

    draft_doc = next(
        (
            row
            for row in docs
            if row.get("entity_kind") == "service" and row.get("entity_id") == SERVICE_DRAFT_ID
        ),
        None,
    )
    assert draft_doc is None or draft_doc.get("is_public") is False

    for row in fake_client.tables["services"].rows:
        if row["id"] == SERVICE_ACTIVE_ID:
            row["status"] = "paused"
            fake_client.sync_search_for_service(row)
            break
    paused_doc = next(
        row
        for row in fake_client.tables["search_documents"].rows
        if row.get("entity_id") == SERVICE_ACTIVE_ID
    )
    assert paused_doc["is_public"] is False
