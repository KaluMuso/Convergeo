"""M17-P05 — clip → cart attribution the client cannot forge.

The single claim: **a `clip_id` in a request is a claim, not a credit.** Credit
is granted only when the clip exists, is published, and actually links the
listing being added. Everything else silently produces no attribution — and,
crucially, still adds to the cart, because a forged id must never be able to
*deny* a real customer their purchase.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from app.services.clips import state_machine
from app.services.clips.attribution import validate_clip_attribution

CLIP_ID = "c1000000-0000-4000-8000-000000000001"
OTHER_CLIP = "c1000000-0000-4000-8000-000000000002"
LISTING_ID = "b1000000-0000-4000-8000-000000000001"
OTHER_LISTING = "b1000000-0000-4000-8000-000000000002"


class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def execute(self) -> MagicMock:
        if self._parent.raises:
            raise RuntimeError("database unavailable")
        rows = [
            dict(row)
            for row in self._parent.rows
            if all(row.get(c) == v for c, v in self._eq)
        ]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []
        self.raises = False

    def select(self, columns: str = "*", **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(columns)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(name))


class Store:
    def __init__(self) -> None:
        self.client = FakeSupabase()

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows


@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("video_clips").append({"id": CLIP_ID, "status": state_machine.PUBLISHED})
    st.rows("clip_products").append({"clip_id": CLIP_ID, "listing_id": LISTING_ID})
    return st


def test_a_published_clip_that_links_the_listing_earns_credit(store: Store) -> None:
    assert (
        validate_clip_attribution(store, clip_id=CLIP_ID, listing_id=LISTING_ID) == CLIP_ID
    )


def test_a_nonexistent_clip_earns_nothing(store: Store) -> None:
    assert validate_clip_attribution(store, clip_id=OTHER_CLIP, listing_id=LISTING_ID) is None


@pytest.mark.parametrize(
    "status", ["draft", "screening", "pending_review", "rejected", "taken_down"]
)
def test_an_unpublished_clip_earns_nothing(store: Store, status: str) -> None:
    store.rows("video_clips")[0]["status"] = status

    assert validate_clip_attribution(store, clip_id=CLIP_ID, listing_id=LISTING_ID) is None


def test_a_clip_that_does_not_link_the_listing_earns_nothing(store: Store) -> None:
    """The most likely forgery: a real, published clip and someone else's listing."""
    assert (
        validate_clip_attribution(store, clip_id=CLIP_ID, listing_id=OTHER_LISTING) is None
    )


def test_a_taken_down_clip_stops_earning_immediately(store: Store) -> None:
    assert validate_clip_attribution(store, clip_id=CLIP_ID, listing_id=LISTING_ID) == CLIP_ID

    store.rows("video_clips")[0]["status"] = state_machine.TAKEN_DOWN

    assert validate_clip_attribution(store, clip_id=CLIP_ID, listing_id=LISTING_ID) is None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_absent_clip_id_is_simply_no_attribution(store: Store, value: str | None) -> None:
    assert validate_clip_attribution(store, clip_id=value, listing_id=LISTING_ID) is None


def test_a_read_failure_resolves_to_no_credit_rather_than_raising(store: Store) -> None:
    """An attribution check must never be able to fail a cart write."""
    store.client.table("video_clips").raises = True

    assert validate_clip_attribution(store, clip_id=CLIP_ID, listing_id=LISTING_ID) is None


def test_the_cart_input_accepts_an_optional_clip_id_and_nothing_else_new() -> None:
    """One cart, one payload: attribution is a field, not a parallel endpoint."""
    from app.routers.cart import CartItemInput

    fields = set(CartItemInput.model_fields)
    assert fields == {"listing_id", "qty", "clip_id"}
    assert CartItemInput(listing_id=LISTING_ID, qty=1).clip_id is None
