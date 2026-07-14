from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EVENT_A_ID = "e1000000-0000-0000-0000-000000000001"
EVENT_B_ID = "e1000000-0000-0000-0000-000000000002"
INSTANCE_A_ID = "i1000000-0000-0000-0000-000000000001"
TICKET_TYPE_ID = "t1000000-0000-0000-0000-000000000001"
TICKET_ID = "tk100000-0000-0000-0000-000000000001"
HOLDER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
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

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._filters.append(("in", column, values))
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

    def delete(self) -> FakeQuery:
        self._pending_op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows):08x}-fake-fake-fake-fakefakefake"
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            if self._maybe_single:
                return MagicMock(data=updated[0] if updated else None, count=len(updated))
            return MagicMock(data=updated, count=len(updated))

        if self._pending_op == "delete":
            remaining: list[dict[str, Any]] = []
            deleted: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    deleted.append(dict(row))
                else:
                    remaining.append(row)
            self._parent.rows[:] = remaining
            return MagicMock(data=deleted, count=len(deleted))

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq" and row.get(column) != value:
                return False
            if op == "in" and row.get(column) not in set(value):
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

    def delete(self) -> FakeQuery:
        return FakeQuery(self, []).delete()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "events": FakeTable(),
            "event_instances": FakeTable(),
            "tickets": FakeTable(),
            "notification_outbox": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _future_iso(hours: int = 48) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def _past_iso(hours: int = 24) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _seed_vendors(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": VENDOR_A_ID,
                "owner_user_id": USER_A_ID,
                "status": "active",
                "kyc_tier": 2,
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": USER_B_ID,
                "status": "active",
                "kyc_tier": 2,
            },
        ]
    )


def _seed_event(
    fake: FakeSupabaseClient,
    *,
    event_id: str = EVENT_A_ID,
    vendor_id: str = VENDOR_A_ID,
    status: str = "draft",
    venue: str = "Lusaka Showgrounds",
    starts_at: str | None = None,
    capacity: int = 100,
    instance_id: str = INSTANCE_A_ID,
) -> None:
    fake.tables["events"].rows.append(
        {
            "id": event_id,
            "organiser_vendor_id": vendor_id,
            "title": "Summer Jam",
            "slug": "summer-jam",
            "description": (
                'Fun night\n<!--vergeo5:event-meta:'
                '{"category":"workshops","landmark":"East Park"}-->'
            ),
            "venue": venue,
            "lat": -15.4,
            "lng": 28.3,
            "images": ["events/summer"],
            "status": status,
            "updated_at": "2026-07-09T10:00:00Z",
        }
    )
    fake.tables["event_instances"].rows.append(
        {
            "id": instance_id,
            "event_id": event_id,
            "starts_at": starts_at or _future_iso(),
            "capacity": capacity,
        }
    )


def _seed_ticket(
    fake: FakeSupabaseClient,
    *,
    instance_id: str = INSTANCE_A_ID,
    holder_user_id: str = HOLDER_ID,
) -> None:
    fake.tables["tickets"].rows.append(
        {
            "id": TICKET_ID,
            "instance_id": instance_id,
            "ticket_type_id": TICKET_TYPE_ID,
            "holder_user_id": holder_user_id,
            "status": "issued",
        }
    )


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
    return FakeSupabaseClient()


@pytest.fixture
def organiser_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    _seed_vendors(fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_payload(*, starts_at: str | None = None) -> dict[str, Any]:
    return {
        "title": "New Workshop",
        "category": "workshops",
        "description": "Learn something new",
        "venue": "Arcades Mall",
        "lat": -15.39,
        "lng": 28.32,
        "landmark": "Near Pick n Pay",
        "images": ["events/workshop"],
        "instances": [
            {
                "starts_at": starts_at or _future_iso(),
                "capacity": 50,
            }
        ],
    }


def test_non_kyc_vendor_cannot_create(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.tables["vendors"].rows[0]["status"] = "pending_kyc"
    fake_client.tables["vendors"].rows[0]["kyc_tier"] = None

    response = organiser_client.post(
        "/organiser/events",
        headers=_auth_headers(),
        json=_create_payload(),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "kyc_required"
    assert len(fake_client.tables["events"].rows) == 0


def test_vendor_b_cannot_access_vendor_a_event(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client, event_id=EVENT_A_ID, vendor_id=VENDOR_A_ID)

    response = organiser_client.patch(
        f"/organiser/events/{EVENT_A_ID}",
        headers=_auth_headers(TOKEN_B),
        json={"title": "Hijacked"},
    )
    assert response.status_code == 404


def test_create_and_list_events(
    organiser_client: TestClient,
) -> None:
    create = organiser_client.post(
        "/organiser/events",
        headers=_auth_headers(),
        json=_create_payload(),
    )
    assert create.status_code == 200
    body = create.json()["event"]
    assert body["status"] == "draft"
    assert body["category"] == "workshops"
    assert body["landmark"] == "Near Pick n Pay"

    listed = organiser_client.get("/organiser/events", headers=_auth_headers())
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1


def test_create_event_with_ends_at(organiser_client: TestClient) -> None:
    payload = _create_payload(starts_at="2026-09-01T18:00:00+02:00")
    payload["instances"][0]["ends_at"] = "2026-09-01T22:00:00+02:00"
    response = organiser_client.post(
        "/organiser/events", headers=_auth_headers(), json=payload
    )
    assert response.status_code == 200
    instances = response.json()["event"]["instances"]
    assert len(instances) == 1
    assert instances[0]["ends_at"] is not None
    # 22:00 +02:00 stored as UTC.
    assert instances[0]["ends_at"].startswith("2026-09-01T20:00:00")


def test_create_event_rejects_ends_at_before_starts_at(organiser_client: TestClient) -> None:
    payload = _create_payload(starts_at="2026-09-01T18:00:00+02:00")
    payload["instances"][0]["ends_at"] = "2026-09-01T17:00:00+02:00"  # before start
    response = organiser_client.post(
        "/organiser/events", headers=_auth_headers(), json=payload
    )
    assert response.status_code == 422


def test_pre_sale_venue_and_date_edit_allowed(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client)

    response = organiser_client.patch(
        f"/organiser/events/{EVENT_A_ID}",
        headers=_auth_headers(),
        json={
            "venue": "New Arena",
            "instances": [
                {
                    "id": INSTANCE_A_ID,
                    "starts_at": _future_iso(72),
                    "capacity": 100,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["event"]["venue"] == "New Arena"
    assert len(fake_client.tables["notification_outbox"].rows) == 0


def test_post_sale_date_change_enqueues_notification(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client)
    _seed_ticket(fake_client)

    response = organiser_client.patch(
        f"/organiser/events/{EVENT_A_ID}",
        headers=_auth_headers(),
        json={
            "instances": [
                {
                    "id": INSTANCE_A_ID,
                    "starts_at": _future_iso(96),
                    "capacity": 100,
                }
            ],
        },
    )
    assert response.status_code == 200
    assert len(fake_client.tables["notification_outbox"].rows) == 1
    outbox = fake_client.tables["notification_outbox"].rows[0]
    assert outbox["dedupe_key"].startswith("event_schedule_changed:")
    assert outbox["payload"]["recipient_id"] == HOLDER_ID
    assert "TODO(M14)" in outbox["payload"]["todo"]


def test_post_sale_venue_change_enqueues_notification(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client)
    _seed_ticket(fake_client)

    response = organiser_client.patch(
        f"/organiser/events/{EVENT_A_ID}",
        headers=_auth_headers(),
        json={"venue": "Moved Venue"},
    )
    assert response.status_code == 200
    assert len(fake_client.tables["notification_outbox"].rows) == 1


def test_capacity_below_sold_rejected(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client, capacity=10)
    _seed_ticket(fake_client)

    response = organiser_client.patch(
        f"/organiser/events/{EVENT_A_ID}",
        headers=_auth_headers(),
        json={
            "instances": [
                {
                    "id": INSTANCE_A_ID,
                    "starts_at": _future_iso(),
                    "capacity": 0,
                }
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "capacity_below_sold"


def test_publish_rejects_past_instance(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client, starts_at=_past_iso())

    response = organiser_client.post(
        f"/organiser/events/{EVENT_A_ID}/publish",
        headers=_auth_headers(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "past_instance"
    assert fake_client.tables["events"].rows[0]["status"] == "draft"


def test_publish_cancel_end_transitions(
    organiser_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_event(fake_client, status="draft")

    publish = organiser_client.post(
        f"/organiser/events/{EVENT_A_ID}/publish",
        headers=_auth_headers(),
    )
    assert publish.status_code == 200
    assert publish.json()["event"]["status"] == "published"
    assert fake_client.tables["events"].rows[0]["status"] == "published"

    end = organiser_client.post(
        f"/organiser/events/{EVENT_A_ID}/end",
        headers=_auth_headers(),
    )
    assert end.status_code == 200
    assert end.json()["event"]["status"] == "completed"
    assert fake_client.tables["events"].rows[0]["status"] == "completed"

    _seed_event(fake_client, event_id=EVENT_B_ID, status="published")
    cancel = organiser_client.post(
        f"/organiser/events/{EVENT_B_ID}/cancel",
        headers=_auth_headers(),
    )
    assert cancel.status_code == 200
    assert cancel.json()["event"]["status"] == "cancelled"
