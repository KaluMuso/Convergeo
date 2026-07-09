from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.core.auth import CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

VENDOR_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VENDOR_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"
LISTING_A_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LISTING_B_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
TOKEN_A = "vendor-a-token"
TOKEN_B = "vendor-b-token"
MAX_IMAGES = 8


class FakeQuery:
    def __init__(self, parent: FakeTable, filters: list[tuple[str, str, Any]]) -> None:
        self._parent = parent
        self._filters = filters
        self._order: tuple[str, bool] | None = None
        self._maybe_single = False
        self._pending_op: str | None = None
        self._payload: dict[str, Any] | None = None
        self._selected_columns = "*"

    def select(self, columns: str, *, count: str | None = None) -> FakeQuery:
        _ = count
        self._selected_columns = columns
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
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

        if self._pending_op == "delete":
            remaining: list[dict[str, Any]] = []
            deleted: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._matches(row):
                    deleted.append(dict(row))
                else:
                    remaining.append(row)
            self._parent.rows = remaining
            return MagicMock(data=deleted, count=len(deleted))

        rows = self._filtered_rows()
        if self._order is not None:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column, ""), reverse=desc)
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

    def delete(self) -> FakeQuery:
        return FakeQuery(self, []).delete()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {
            "vendors": FakeTable(),
            "vendor_listings": FakeTable(),
            "listing_images": FakeTable(),
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
                "status": "active",
            },
            {
                "id": VENDOR_B_ID,
                "owner_user_id": USER_B_ID,
                "status": "active",
            },
        ]
    )


def _seed_listings(fake: FakeSupabaseClient) -> None:
    fake.tables["vendor_listings"].rows.extend(
        [
            {
                "id": LISTING_A_ID,
                "vendor_id": VENDOR_A_ID,
                "status": "draft",
            },
            {
                "id": LISTING_B_ID,
                "vendor_id": VENDOR_B_ID,
                "status": "draft",
            },
        ]
    )


def _seed_roles(fake: FakeSupabaseClient) -> None:
    fake.tables["user_roles"].rows.extend(
        [
            {"user_id": USER_A_ID, "role": "vendor"},
            {"user_id": USER_B_ID, "role": "vendor"},
        ]
    )


def _attach_images(
    fake: FakeSupabaseClient,
    listing_id: str,
    count: int,
    *,
    prefix: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position in range(1, count + 1):
        row = {
            "id": str(uuid4()),
            "listing_id": listing_id,
            "cloudinary_public_id": f"{prefix}-{position}",
            "position": position,
        }
        fake.tables["listing_images"].rows.append(row)
        rows.append(row)
    return rows


@pytest.fixture
def listing_images_client() -> Generator[TestClient, None, None]:
    fake = FakeSupabaseClient()
    _seed_vendors(fake)
    _seed_listings(fake)
    _seed_roles(fake)

    class FakeServiceClient:
        def __init__(self, client: FakeSupabaseClient) -> None:
            self.client = client

    app: FastAPI = create_app()
    service_client = FakeServiceClient(fake)

    async def current_user_a() -> CurrentUser:
        return CurrentUser(id=USER_A_ID, roles=frozenset({"vendor"}), token=TOKEN_A)

    def service_dep() -> Generator[FakeServiceClient, None, None]:
        yield service_client

    app.dependency_overrides[get_supabase_client] = service_dep
    app.dependency_overrides[get_current_user] = current_user_a

    with TestClient(app, raise_server_exceptions=False) as client:
        client.fake = fake
        yield client

    app.dependency_overrides.clear()


def _auth_headers(token: str = TOKEN_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_attach_and_list_image(listing_images_client: TestClient) -> None:
    response = listing_images_client.post(
        f"/vendor/listings/{LISTING_A_ID}/images",
        headers=_auth_headers(),
        json={"cloudinary_public_id": "listings/vendor-a/photo-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["listing_id"] == LISTING_A_ID
    assert body["cloudinary_public_id"] == "listings/vendor-a/photo-1"
    assert body["position"] == 1


def test_ninth_image_blocked_server(listing_images_client: TestClient) -> None:
    fake: FakeSupabaseClient = listing_images_client.fake
    _attach_images(fake, LISTING_A_ID, MAX_IMAGES, prefix="cap")

    response = listing_images_client.post(
        f"/vendor/listings/{LISTING_A_ID}/images",
        headers=_auth_headers(),
        json={"cloudinary_public_id": "listings/vendor-a/photo-9"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "image_limit_reached"
    assert len(fake.tables["listing_images"].rows) == MAX_IMAGES


def test_vendor_a_cannot_attach_into_vendor_b_listing(listing_images_client: TestClient) -> None:
    response = listing_images_client.post(
        f"/vendor/listings/{LISTING_B_ID}/images",
        headers=_auth_headers(TOKEN_A),
        json={"cloudinary_public_id": "listings/vendor-b/stolen"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden"


def test_reorder_persists_positions(listing_images_client: TestClient) -> None:
    fake: FakeSupabaseClient = listing_images_client.fake
    seeded = _attach_images(fake, LISTING_A_ID, 3, prefix="reorder")
    reordered_ids = [seeded[2]["id"], seeded[0]["id"], seeded[1]["id"]]

    response = listing_images_client.patch(
        f"/vendor/listings/{LISTING_A_ID}/images/reorder",
        headers=_auth_headers(),
        json={"image_ids": reordered_ids},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == reordered_ids
    assert [item["position"] for item in body] == [1, 2, 3]

    stored = sorted(fake.tables["listing_images"].rows, key=lambda row: row["position"])
    assert [row["cloudinary_public_id"] for row in stored] == [
        "reorder-3",
        "reorder-1",
        "reorder-2",
    ]


def test_detach_renumbers_remaining_images(listing_images_client: TestClient) -> None:
    fake: FakeSupabaseClient = listing_images_client.fake
    seeded = _attach_images(fake, LISTING_A_ID, 3, prefix="detach")
    middle_id = seeded[1]["id"]

    response = listing_images_client.delete(
        f"/vendor/listings/{LISTING_A_ID}/images/{middle_id}",
        headers=_auth_headers(),
    )
    assert response.status_code == 204

    remaining = sorted(fake.tables["listing_images"].rows, key=lambda row: row["position"])
    assert len(remaining) == 2
    assert [row["position"] for row in remaining] == [1, 2]
    assert [row["cloudinary_public_id"] for row in remaining] == ["detach-1", "detach-3"]


def test_client_image_cap_helper_blocks_ninth() -> None:
    from app.routers.listing_images import MAX_IMAGES_PER_LISTING

    def would_exceed_image_cap(current_count: int, incoming_count: int) -> bool:
        return current_count + incoming_count > MAX_IMAGES_PER_LISTING

    assert would_exceed_image_cap(8, 1) is True
    assert would_exceed_image_cap(7, 1) is False
    assert would_exceed_image_cap(8, 0) is False
