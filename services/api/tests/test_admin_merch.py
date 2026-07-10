from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from app.main import create_app
from app.routers.admin_merch import (
    DEFAULT_PREVIEW_TOKEN,
    DRAFT_PAYLOAD_KEY,
    is_slot_in_schedule,
    now_in_lusaka,
    resolve_slots_for_display,
)
from fastapi.testclient import TestClient

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"
HERO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BANNER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
DEFAULT_HERO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
EXPIRED_HERO_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
VALID_TOKEN = "valid.jwt.token"
LUSAKA = ZoneInfo("Africa/Lusaka")


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

    def delete(self) -> FakeQuery:
        self._pending_op = "delete"
        return self

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"{len(self._parent.rows) + 1:08x}-0000-4000-8000-000000000001"
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            row.setdefault("updated_at", datetime.now(UTC).isoformat())
            self._parent.rows.append(row)
            if self._parent._audit_sink is not None:
                self._parent._audit_sink.append(row)
            return MagicMock(data=[row])

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if all(
                    row.get(column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    row.update(self._payload)
                    row["updated_at"] = datetime.now(UTC).isoformat()
                    updated.append(dict(row))
            return MagicMock(data=updated)

        if self._pending_op == "delete":
            remaining: list[dict[str, Any]] = []
            deleted: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if all(
                    row.get(column) == value
                    for op, column, value in self._filters
                    if op == "eq"
                ):
                    deleted.append(dict(row))
                else:
                    remaining.append(row)
            self._parent.rows = remaining
            return MagicMock(data=deleted)

        rows = self._apply_filters(self._parent.rows)
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, 0), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for op, column, value in self._filters:
            if op == "eq":
                filtered = [row for row in filtered if row.get(column) == value]
        return [dict(row) for row in filtered]


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._audit_sink: list[dict[str, Any]] | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        return FakeQuery(self, []).select(columns, count=count)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self, []).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self, []).delete()

    def eq(self, column: str, value: Any) -> FakeQuery:
        return FakeQuery(self, []).eq(column, value)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables = {
            "merch_slots": FakeTable(),
            "audit_log": FakeTable(),
        }
        self.audit_rows: list[dict[str, Any]] = []

    def table(self, name: str) -> FakeTable:
        table = self.tables[name]
        table._audit_sink = self.audit_rows if name == "audit_log" else None
        return table


@pytest.fixture
def merch_app() -> Any:
    return create_app()


@pytest.fixture
def merch_client(merch_app: Any) -> Generator[TestClient, None, None]:
    with TestClient(merch_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    service_wrapper = MagicMock()
    service_wrapper.client = client
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.routers.admin_merch.get_supabase_client", lambda: service_wrapper)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: service_wrapper)
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


def _mock_audit_insert(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeSupabaseClient,
) -> list[dict[str, Any]]:
    _ = monkeypatch
    return fake.audit_rows


def _seed_slots(fake: FakeSupabaseClient) -> None:
    now = datetime.now(UTC)
    fake.tables["merch_slots"].rows.extend(
        [
            {
                "id": HERO_ID,
                "slot_key": "hero",
                "variant_key": "editorial-light",
                "payload": {
                    "title_key": "merch.hero.live.title",
                    "is_default": True,
                },
                "schedule_from": None,
                "schedule_to": None,
                "position": 0,
                "active": True,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "id": BANNER_ID,
                "slot_key": "banner_row",
                "variant_key": "default",
                "payload": {
                    "items": [{"key": "b1", "title": "Live banner", "href": "/en/search"}],
                },
                "schedule_from": (now - timedelta(days=1)).isoformat(),
                "schedule_to": (now + timedelta(days=1)).isoformat(),
                "position": 1,
                "active": True,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            },
        ]
    )


def test_schedule_in_window_active() -> None:
    now = datetime(2026, 7, 10, 12, 0, tzinfo=LUSAKA)
    slot = {
        "active": True,
        "schedule_from": datetime(2026, 7, 10, 6, 0, tzinfo=LUSAKA).isoformat(),
        "schedule_to": datetime(2026, 7, 10, 18, 0, tzinfo=LUSAKA).isoformat(),
    }
    assert is_slot_in_schedule(slot, now=now) is True


def test_schedule_expired_falls_back_to_default() -> None:
    now = datetime(2026, 7, 10, 20, 0, tzinfo=LUSAKA)
    rows: list[dict[str, Any]] = [
        {
            "id": EXPIRED_HERO_ID,
            "slot_key": "hero",
            "variant_key": "carousel",
            "payload": {"title_key": "expired"},
            "schedule_from": datetime(2026, 7, 9, 0, 0, tzinfo=LUSAKA).isoformat(),
            "schedule_to": datetime(2026, 7, 10, 8, 0, tzinfo=LUSAKA).isoformat(),
            "position": 0,
            "active": True,
        },
        {
            "id": DEFAULT_HERO_ID,
            "slot_key": "hero",
            "variant_key": "editorial-light",
            "payload": {"title_key": "default", "is_default": True},
            "schedule_from": None,
            "schedule_to": None,
            "position": 1,
            "active": True,
        },
    ]
    resolved = resolve_slots_for_display(rows, now=now)
    hero = next(slot for slot in resolved if slot.slot_key == "hero")
    assert hero.variant_key == "editorial-light"
    assert hero.is_fallback is True


def test_schedule_lusaka_boundary_midnight() -> None:
    boundary = datetime(2026, 7, 10, 0, 0, tzinfo=LUSAKA)
    slot = {
        "active": True,
        "schedule_from": datetime(2026, 7, 10, 0, 0, tzinfo=LUSAKA).isoformat(),
        "schedule_to": datetime(2026, 7, 11, 0, 0, tzinfo=LUSAKA).isoformat(),
    }
    assert is_slot_in_schedule(slot, now=boundary) is True
    before = boundary - timedelta(seconds=1)
    assert is_slot_in_schedule(slot, now=before) is False


def test_now_in_lusaka_converts_utc() -> None:
    utc_noon = datetime(2026, 7, 10, 10, 0, tzinfo=UTC)
    lusaka = now_in_lusaka(utc_noon)
    assert lusaka.tzinfo == LUSAKA
    assert lusaka.hour == 12


def test_draft_not_live_until_published(
    merch_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch, fake_client)
    _seed_slots(fake_client)

    draft_response = merch_client.post(
        f"/admin/merch/slots/{HERO_ID}/draft",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "variant_key": "gradient-dark",
            "payload": {"title_key": "merch.hero.draft.title"},
        },
    )
    assert draft_response.status_code == 200
    body = draft_response.json()
    assert body["has_draft"] is True
    assert body["variant_key"] == "editorial-light"
    assert body["payload"]["title_key"] == "merch.hero.live.title"

    public = merch_client.get("/merch/slots")
    assert public.status_code == 200
    hero = next(slot for slot in public.json() if slot["slot_key"] == "hero")
    assert hero["variant_key"] == "editorial-light"

    publish_response = merch_client.post(
        f"/admin/merch/slots/{HERO_ID}/publish",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert publish_response.status_code == 200
    published = publish_response.json()
    assert published["has_draft"] is False
    assert published["variant_key"] == "gradient-dark"
    assert published["payload"]["title_key"] == "merch.hero.draft.title"
    assert len(audit_rows) >= 2


def test_preview_token_gate(
    merch_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch, fake_client)
    _seed_slots(fake_client)

    merch_client.post(
        f"/admin/merch/slots/{HERO_ID}/draft",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"variant_key": "carousel"},
    )

    invalid = merch_client.get("/merch/slots", params={"merch_preview": "wrong-token"})
    hero_invalid = next(slot for slot in invalid.json() if slot["slot_key"] == "hero")
    assert hero_invalid["variant_key"] == "editorial-light"
    assert hero_invalid["is_preview"] is False

    valid = merch_client.get(
        "/merch/slots",
        params={"merch_preview": DEFAULT_PREVIEW_TOKEN},
    )
    hero_valid = next(slot for slot in valid.json() if slot["slot_key"] == "hero")
    assert hero_valid["variant_key"] == "carousel"
    assert hero_valid["is_preview"] is True


def test_non_admin_returns_403(
    merch_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch, OTHER_USER_ID)
    _mock_roles(monkeypatch, {OTHER_USER_ID: frozenset({"vendor"})})
    _seed_slots(fake_client)

    response = merch_client.get(
        "/admin/merch/slots",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 403


def test_slot_crud_and_audit(
    merch_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    audit_rows = _mock_audit_insert(monkeypatch, fake_client)
    _seed_slots(fake_client)

    create_response = merch_client.post(
        "/admin/merch/slots",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={
            "slot_key": "events_row",
            "variant_key": "default",
            "payload": {"title_key": "merch.events.title"},
            "position": 2,
            "active": True,
        },
    )
    assert create_response.status_code == 201
    created_id = create_response.json()["id"]

    patch_response = merch_client.patch(
        f"/admin/merch/slots/{created_id}",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        json={"position": 3},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["position"] == 3

    delete_response = merch_client.delete(
        f"/admin/merch/slots/{created_id}",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert delete_response.status_code == 204
    assert len(audit_rows) == 3


def test_publish_without_draft_returns_422(
    merch_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_verify(monkeypatch)
    _mock_roles(monkeypatch, {USER_ID: frozenset({"admin"})})
    _mock_audit_insert(monkeypatch, fake_client)
    _seed_slots(fake_client)

    response = merch_client.post(
        f"/admin/merch/slots/{HERO_ID}/publish",
        headers={"Authorization": f"Bearer {VALID_TOKEN}"},
    )
    assert response.status_code == 422


def test_empty_schedule_window_falls_back() -> None:
    now = datetime(2026, 7, 10, 15, 0, tzinfo=LUSAKA)
    rows: list[dict[str, Any]] = [
        {
            "id": EXPIRED_HERO_ID,
            "slot_key": "hero",
            "variant_key": "carousel",
            "payload": {},
            "schedule_from": datetime(2026, 7, 9, 0, 0, tzinfo=LUSAKA).isoformat(),
            "schedule_to": datetime(2026, 7, 10, 8, 0, tzinfo=LUSAKA).isoformat(),
            "position": 0,
            "active": True,
        },
        {
            "id": DEFAULT_HERO_ID,
            "slot_key": "hero",
            "variant_key": "editorial-light",
            "payload": {"is_default": True},
            "schedule_from": None,
            "schedule_to": None,
            "position": 1,
            "active": True,
        },
    ]
    resolved = resolve_slots_for_display(rows, now=now)
    hero = next(slot for slot in resolved if slot.slot_key == "hero")
    assert hero.id == UUID(DEFAULT_HERO_ID)
    assert hero.is_fallback is True


def test_draft_payload_key_constant() -> None:
    assert DRAFT_PAYLOAD_KEY == "_merch_draft"
