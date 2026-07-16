from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.deps import get_supabase_client
from app.main import create_app
from app.routers.vendor_profile import (
    compute_profile_completeness,
    normalize_whatsapp_msisdn,
    resolve_slug_redirect,
    validate_vendor_hours,
)
from fastapi.testclient import TestClient

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LOCATION_A_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
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

    def execute(self) -> MagicMock:
        if self._pending_op == "insert":
            assert isinstance(self._payload, dict)
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = str(uuid4())
            self._parent.rows.append(row)
            return MagicMock(data=[row], count=None)

        if self._pending_op == "update":
            assert isinstance(self._payload, dict)
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated, count=len(updated))

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None, count=len(rows))
        return MagicMock(data=rows, count=len(rows))

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._parent.rows)
        for op, column, value in self._filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
        return rows

    def _matches(self, row: dict[str, Any]) -> bool:
        return all(row.get(column) == value for op, column, value in self._filters if op == "eq")


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
            "vendor_locations": FakeTable(),
            "user_roles": FakeTable(),
        }

    def table(self, name: str) -> FakeTable:
        return self.tables[name]


def _seed_vendors(fake: FakeSupabaseClient) -> None:
    fake.tables["vendors"].rows.extend(
        [
            {
                "id": VENDOR_A_ID,
                "owner_user_id": USER_A_ID,
                "slug": "shop-a",
                "display_name": "Shop A",
                "description": None,
                "logo_url": None,
                "status": "active",
                "kyc_tier": 1,
                "preferred_badge": False,
                "caps_snapshot": {},
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": USER_B_ID,
                "slug": "shop-b",
                "display_name": "Shop B",
                "description": (
                    "A complete description with more than fifty characters for testing."
                ),
                "logo_url": "https://res.cloudinary.com/demo/logo.png",
                "status": "active",
                "kyc_tier": 2,
                "preferred_badge": True,
                "caps_snapshot": {},
            },
        ]
    )


def _seed_location(fake: FakeSupabaseClient) -> None:
    fake.tables["vendor_locations"].rows.append(
        {
            "id": LOCATION_A_ID,
            "vendor_id": VENDOR_A_ID,
            "lat": -15.3875,
            "lng": 28.3228,
            "landmark": "Near Manda Hill",
            "hours": {
                "mon": {"open": "08:00", "close": "18:00"},
                "sat": {"closed": True},
            },
            "created_at": "2026-01-01T00:00:00Z",
        }
    )


def _mock_auth(monkeypatch: pytest.MonkeyPatch, user_id: str) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda uid, service_client: frozenset({"vendor"}),
    )


def _mock_supabase(monkeypatch: pytest.MonkeyPatch, fake: FakeSupabaseClient) -> MagicMock:
    service_wrapper = MagicMock()
    service_wrapper.client = fake
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_wrapper)
    monkeypatch.setattr("app.supabase_client.get_supabase_service_client", lambda: service_wrapper)
    return service_wrapper


def _apply_supabase_overrides(app: Any, service_wrapper: MagicMock) -> None:
    app.dependency_overrides[get_supabase_client] = lambda: service_wrapper


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def profile_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> Generator[TestClient, None, None]:
    _mock_auth(monkeypatch, USER_A_ID)
    _seed_vendors(fake_client)
    _seed_location(fake_client)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_vendor_profile(profile_client: TestClient) -> None:
    response = profile_client.get("/vendor/profile", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["slug"] == "shop-a"
    assert payload["landmark"] == "Near Manda Hill"
    assert payload["completeness_score"] == 40
    assert payload["completeness"]["hours"] is True
    assert payload["completeness"]["location"] is True


def test_slug_edit_once_then_locked(
    profile_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    first = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"slug": "lusaka-electronics"},
    )
    assert first.status_code == 200
    assert first.json()["slug"] == "lusaka-electronics"
    assert first.json()["slug_locked"] is True
    assert first.json()["previous_slug"] == "shop-a"

    vendor_row = fake_client.tables["vendors"].rows[0]
    assert vendor_row["slug"] == "lusaka-electronics"
    assert vendor_row["caps_snapshot"]["slug_locked"] is True
    assert vendor_row["caps_snapshot"]["previous_slug"] == "shop-a"

    second = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"slug": "another-slug"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_old_slug_redirect_mapping_preserved(
    profile_client: TestClient,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"slug": "new-shop-a"},
    )
    service_wrapper = MagicMock()
    service_wrapper.client = fake_client
    assert resolve_slug_redirect(service_wrapper, "shop-a") == "new-shop-a"
    assert resolve_slug_redirect(service_wrapper, "new-shop-a") is None


def test_slug_uniqueness_rejection(profile_client: TestClient) -> None:
    response = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"slug": "shop-b"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_slug_charset_rejection(profile_client: TestClient) -> None:
    response = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"slug": "Bad_Slug!"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_completeness_meter_deterministic() -> None:
    score_empty, breakdown_empty = compute_profile_completeness(
        logo_url=None,
        description=None,
        hours={},
        lat=None,
        lng=None,
        landmark=None,
        preferred_badge=False,
    )
    assert score_empty == 0
    assert breakdown_empty.logo is False

    score_full, breakdown_full = compute_profile_completeness(
        logo_url="https://res.cloudinary.com/demo/logo.png",
        description="This storefront description is definitely longer than fifty characters.",
        hours={"mon": {"open": "08:00", "close": "18:00"}},
        lat=-15.3875,
        lng=28.3228,
        landmark="Near Arcades",
        preferred_badge=True,
    )
    assert score_full == 100
    assert breakdown_full.badge is True

    score_partial, breakdown_partial = compute_profile_completeness(
        logo_url="https://res.cloudinary.com/demo/logo.png",
        description="Short",
        hours={"mon": {"open": "08:00", "close": "18:00"}},
        lat=-15.3875,
        lng=28.3228,
        landmark="Arcades",
        preferred_badge=False,
    )
    assert score_partial == 60
    assert breakdown_partial.description is False
    assert breakdown_partial.logo is True


def test_completeness_overnight_hours_count_as_complete() -> None:
    hours = {"fri": {"open": "20:00", "close": "02:00"}}
    validate_vendor_hours(hours)
    score, breakdown = compute_profile_completeness(
        logo_url=None,
        description=None,
        hours=hours,
        lat=None,
        lng=None,
        landmark=None,
        preferred_badge=False,
    )
    assert breakdown.hours is True
    assert score == 20


def test_authz_vendor_cannot_edit_other_vendor(
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
) -> None:
    _seed_vendors(fake_client)
    _seed_location(fake_client)
    service_wrapper = _mock_supabase(monkeypatch, fake_client)
    app = create_app()
    _apply_supabase_overrides(app, service_wrapper)

    _mock_auth(monkeypatch, USER_B_ID)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.patch(
            "/vendor/profile",
            headers=_auth_headers(TOKEN_B),
            json={"display_name": "Hijacked Shop A"},
        )
        assert response.status_code == 200
        assert response.json()["vendor_id"] == VENDOR_B_ID

    vendor_a = fake_client.tables["vendors"].rows[0]
    assert vendor_a["display_name"] == "Shop A"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0977123456", "260977123456"),
        ("260977123456", "260977123456"),
        ("+260 977 123 456", "260977123456"),
        ("977123456", "260977123456"),
        ("0967123456", "260967123456"),
    ],
)
def test_normalize_whatsapp_msisdn_accepts_valid(raw: str, expected: str) -> None:
    assert normalize_whatsapp_msisdn(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "12345",  # too short
        "0577123456",  # subscriber does not start with 7 or 9
        "09771234567",  # too long
        "",  # empty
    ],
)
def test_normalize_whatsapp_msisdn_rejects_invalid(raw: str) -> None:
    assert normalize_whatsapp_msisdn(raw) is None


def test_patch_sets_and_normalizes_whatsapp(
    profile_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    response = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"whatsapp_msisdn": "0977 123 456"},
    )
    assert response.status_code == 200
    # Stored + returned canonically as E.164 digits, ready for wa.me deep links.
    assert response.json()["whatsapp_msisdn"] == "260977123456"
    assert fake_client.tables["vendors"].rows[0]["whatsapp_msisdn"] == "260977123456"

    # And it round-trips on the next GET.
    fetched = profile_client.get("/vendor/profile", headers=_auth_headers())
    assert fetched.json()["whatsapp_msisdn"] == "260977123456"


def test_patch_whatsapp_invalid_rejected(profile_client: TestClient) -> None:
    response = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"whatsapp_msisdn": "12345"},
    )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"]["message_key"] == "vendor.profile.errors.whatsapp_invalid"


def test_patch_whatsapp_cleared_with_blank(
    profile_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"whatsapp_msisdn": "0977123456"},
    )
    cleared = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"whatsapp_msisdn": "  "},
    )
    assert cleared.status_code == 200
    assert cleared.json()["whatsapp_msisdn"] is None
    assert fake_client.tables["vendors"].rows[0]["whatsapp_msisdn"] is None


def test_patch_sets_and_clears_cover(
    profile_client: TestClient,
    fake_client: FakeSupabaseClient,
) -> None:
    set_response = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"cover_url": "https://res.cloudinary.com/demo/cover.png"},
    )
    assert set_response.status_code == 200
    assert set_response.json()["cover_url"] == "https://res.cloudinary.com/demo/cover.png"
    assert (
        fake_client.tables["vendors"].rows[0]["cover_url"]
        == "https://res.cloudinary.com/demo/cover.png"
    )

    cleared = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={"cover_url": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["cover_url"] is None
    assert fake_client.tables["vendors"].rows[0]["cover_url"] is None


def test_patch_updates_display_and_location(profile_client: TestClient) -> None:
    response = profile_client.patch(
        "/vendor/profile",
        headers=_auth_headers(),
        json={
            "display_name": "Lusaka Electronics",
            "description": (
                "Quality electronics with more than fifty characters in the description."
            ),
            "logo_url": "https://res.cloudinary.com/demo/logo.png",
            "location": {
                "lat": -15.4,
                "lng": 28.33,
                "landmark": "Manda Hill Mall entrance",
            },
            "hours": {
                "mon": {"open": "09:00", "close": "17:00"},
                "tue": {"open": "09:00", "close": "17:00"},
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "Lusaka Electronics"
    assert payload["landmark"] == "Manda Hill Mall entrance"
    assert payload["completeness_score"] == 80
