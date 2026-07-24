"""Service-review submit/edit, verified-engagement gate, listing, and vendor replies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_OWNER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_OWNER_ID = "44444444-4444-4444-4444-444444444444"
VENDOR_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
JOB_ID = "b0000000-0000-4000-8000-000000000001"
QUOTE_ID = "c0000000-0000-4000-8000-000000000002"
ORDER_ID = "d0000000-0000-4000-8000-000000000003"
ORDER_ITEM_ID = "e0000000-0000-4000-8000-000000000004"
SERVICE_ID = "f0000000-0000-4000-8000-000000000005"


@pytest.fixture(autouse=True)
def _allow_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.service_reviews.bump_rate_counter",
        lambda **kwargs: (True, 0),
    )


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, Any]] = []
        self._in: tuple[str, set[Any]] | None = None
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in = (column, set(values))
        return self

    def order(self, column: str, *, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._op = "update"
        self._payload = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for column, value in self._filters:
            if row.get(column) != value:
                return False
        if self._in is not None:
            column, allowed = self._in
            if row.get(column) not in allowed:
                return False
        return True

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert isinstance(self._payload, dict)
            if self._parent.name == "service_reviews":
                for existing in self._parent.rows:
                    if existing.get("job_id") == self._payload.get("job_id"):
                        raise RuntimeError(
                            'duplicate key value violates unique constraint '
                            '"service_reviews_job_id_key"'
                        )
            # Stamp the real insertion time (like the DB default) so the review
            # edit-window math is relative to "now" — a hardcoded date is a
            # time-bomb (created + REVIEW_EDIT_DAYS elapses on a fixed calendar day).
            now = datetime.now(tz=UTC).isoformat()
            row = {
                "id": f"rev-{len(self._parent.rows) + 1}",
                "created_at": now,
                "updated_at": now,
                "vendor_reply": None,
                "vendor_reply_at": None,
                **self._payload,
            }
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        matched = [row for row in self._parent.rows if self._match(row)]
        if self._op == "update":
            assert isinstance(self._payload, dict)
            for row in matched:
                row.update(self._payload)
            return MagicMock(data=[dict(row) for row in matched])

        rows = matched
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=list(rows))


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable(name)
        return self.tables[name]


class _Wrapper:
    def __init__(self, client: FakeClient) -> None:
        self.client = client


def _make_client(*, user_id: str, fake: FakeClient) -> TestClient:
    app: FastAPI = create_app()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(id=user_id, roles=frozenset({"customer"}), token="test-token")

    def override_service_client() -> _Wrapper:
        return _Wrapper(fake)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_supabase_client] = override_service_client
    return TestClient(app, raise_server_exceptions=False)


def _seed_completed_job(
    fake: FakeClient,
    *,
    customer_id: str = CUSTOMER_ID,
    provider_vendor_id: str = VENDOR_ID,
    quote_status: str = "accepted",
    order_status: str = "completed",
) -> None:
    fake.table("jobs").rows.append(
        {"id": JOB_ID, "customer_id": customer_id, "status": "completed"}
    )
    fake.table("job_quotes").rows.append(
        {
            "id": QUOTE_ID,
            "job_id": JOB_ID,
            "provider_vendor_id": provider_vendor_id,
            "status": quote_status,
        }
    )
    fake.table("order_item_services").rows.append(
        {"order_item_id": ORDER_ITEM_ID, "job_id": JOB_ID}
    )
    fake.table("order_items").rows.append({"id": ORDER_ITEM_ID, "order_id": ORDER_ID})
    fake.table("orders").rows.append({"id": ORDER_ID, "status": order_status})
    fake.table("vendors").rows.append(
        {"id": provider_vendor_id, "owner_user_id": VENDOR_OWNER_ID}
    )


@pytest.fixture
def fake() -> FakeClient:
    return FakeClient()


def _post_review(client: TestClient, *, rating: int = 5, body: str | None = "Great work") -> Any:
    return client.post("/service-reviews", json={"job_id": JOB_ID, "rating": rating, "body": body})


def test_submit_success_after_completed_job(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = _post_review(client)
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_vendor_id"] == VENDOR_ID
    assert payload["rating"] == 5
    assert len(fake.table("service_reviews").rows) == 1


def test_submit_rejected_when_not_completed(fake: FakeClient) -> None:
    _seed_completed_job(fake, order_status="placed")
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = _post_review(client)
    assert response.status_code == 403
    assert not fake.table("service_reviews").rows


def test_submit_rejected_for_non_owner(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    client = _make_client(user_id=OTHER_CUSTOMER_ID, fake=fake)
    response = _post_review(client)
    assert response.status_code == 403


def test_submit_rejected_without_accepted_provider(fake: FakeClient) -> None:
    _seed_completed_job(fake, quote_status="submitted")
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = _post_review(client)
    assert response.status_code == 409


def test_submit_edits_within_window(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    assert _post_review(client, rating=5).status_code == 200
    second = _post_review(client, rating=2, body="Changed my mind")
    assert second.status_code == 200
    assert second.json()["rating"] == 2
    assert len(fake.table("service_reviews").rows) == 1  # edited in place, not duplicated


def test_submit_rejected_after_edit_window(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    stale = (datetime.now(tz=UTC) - timedelta(days=8)).isoformat()
    fake.table("service_reviews").rows.append(
        {
            "id": "rev-old",
            "job_id": JOB_ID,
            "provider_vendor_id": VENDOR_ID,
            "customer_id": CUSTOMER_ID,
            "rating": 4,
            "body": "old",
            "vendor_reply": None,
            "vendor_reply_at": None,
            "status": "published",
            "created_at": stale,
            "updated_at": stale,
        }
    )
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = _post_review(client, rating=1)
    assert response.status_code == 403


def test_list_by_service_id_aggregates_published(fake: FakeClient) -> None:
    fake.table("services").rows.append({"id": SERVICE_ID, "vendor_id": VENDOR_ID})
    seeded = [
        (5, "published", "2026-01-01"),
        (3, "published", "2026-02-01"),
        (1, "removed", "2026-03-01"),
    ]
    for index, (rating, status, created) in enumerate(seeded):
        fake.table("service_reviews").rows.append(
            {
                "id": f"rev-{index}",
                "job_id": f"job-{index}",
                "provider_vendor_id": VENDOR_ID,
                "customer_id": CUSTOMER_ID,
                "rating": rating,
                "body": None,
                "vendor_reply": None,
                "vendor_reply_at": None,
                "status": status,
                "created_at": created,
                "updated_at": created,
            }
        )
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.get(f"/service-reviews?service_id={SERVICE_ID}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["rating_count"] == 2  # removed excluded
    assert payload["rating_avg"] == 4.0  # (5 + 3) / 2
    assert [item["rating"] for item in payload["items"]] == [3, 5]  # newest first


def test_list_unknown_service_returns_empty(fake: FakeClient) -> None:
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.get("/service-reviews?service_id=does-not-exist")
    assert response.status_code == 200
    assert response.json() == {"items": [], "rating_avg": None, "rating_count": 0}


def test_eligibility_completed_no_review(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    client = _make_client(user_id=CUSTOMER_ID, fake=fake)
    response = client.get(f"/service-reviews/eligibility/{JOB_ID}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["can_review"] is True
    assert payload["completed"] is True
    assert payload["review"] is None


def test_eligibility_forbidden_for_non_owner(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    client = _make_client(user_id=OTHER_CUSTOMER_ID, fake=fake)
    response = client.get(f"/service-reviews/eligibility/{JOB_ID}")
    assert response.status_code == 403


def test_vendor_reply_by_owner(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    fake.table("service_reviews").rows.append(
        {
            "id": "rev-1",
            "job_id": JOB_ID,
            "provider_vendor_id": VENDOR_ID,
            "customer_id": CUSTOMER_ID,
            "rating": 5,
            "body": "Great",
            "vendor_reply": None,
            "vendor_reply_at": None,
            "status": "published",
            "created_at": "2026-07-17T00:00:00Z",
            "updated_at": "2026-07-17T00:00:00Z",
        }
    )
    client = _make_client(user_id=VENDOR_OWNER_ID, fake=fake)
    response = client.post("/service-reviews/rev-1/reply", json={"reply": "Thank you!"})
    assert response.status_code == 200
    assert response.json()["vendor_reply"] == "Thank you!"


def test_vendor_reply_forbidden_for_non_owner(fake: FakeClient) -> None:
    _seed_completed_job(fake)
    fake.table("service_reviews").rows.append(
        {
            "id": "rev-1",
            "job_id": JOB_ID,
            "provider_vendor_id": VENDOR_ID,
            "customer_id": CUSTOMER_ID,
            "rating": 5,
            "body": "Great",
            "vendor_reply": None,
            "vendor_reply_at": None,
            "status": "published",
            "created_at": "2026-07-17T00:00:00Z",
            "updated_at": "2026-07-17T00:00:00Z",
        }
    )
    client = _make_client(user_id=OTHER_OWNER_ID, fake=fake)
    response = client.post("/service-reviews/rev-1/reply", json={"reply": "Not mine"})
    assert response.status_code == 403
