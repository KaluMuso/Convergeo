"""M17-P03 — the public feed and detail surface.

Four claims are defended here, and they are the ones that would hurt if wrong:

* **published-only, no exceptions** — every other status is asserted absent, including
  to the clip's own vendor, because "the vendor can see their own draft" is exactly
  the kind of convenience that turns into a public leak;
* **cursor pagination** — no OFFSET, no duplicates, no skips, even while the table
  is receiving new rows underneath the reader;
* **card-complete payloads** — poster, duration, per-rendition byte size and counters
  in one response, because an N+1 on Fast-3G is the cost D-V1 exists to avoid;
* **no private Cloudinary data** — no secret, no admin URL, no signed upload params.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.clips import state_machine
from fastapi.testclient import TestClient

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
VENDOR_USER_A = "11111111-1111-4111-8111-111111111111"
LISTING_A = "b1000000-0000-4000-8000-000000000001"
JWT = "valid.jwt.token"

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._eq: list[tuple[str, Any]] = []
        self._in: list[tuple[str, list[Any]]] = []
        self._lt: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._maybe_single = False

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._eq.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self._in.append((column, list(values)))
        return self

    def lt(self, column: str, value: Any) -> FakeQuery:
        self._lt.append((column, value))
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self._limit = count
        return self

    def maybe_single(self) -> FakeQuery:
        self._maybe_single = True
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        if not all(row.get(c) == v for c, v in self._eq):
            return False
        if not all(row.get(c) in values for c, values in self._in):
            return False
        return all(str(row.get(c) or "") < str(v) for c, v in self._lt)

    def execute(self) -> MagicMock:
        rows = [dict(row) for row in self._parent.rows if self._match(row)]
        if self._order:
            column, desc = self._order
            rows.sort(key=lambda r: str(r.get(column) or ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

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


def _clip(
    clip_id: str,
    *,
    vendor: str = VENDOR_A,
    status: str = state_machine.PUBLISHED,
    minutes_old: float = 0.0,
    likes: int = 0,
) -> dict[str, Any]:
    published = (NOW - timedelta(minutes=minutes_old)).isoformat()
    return {
        "id": clip_id,
        "vendor_id": vendor,
        "status": status,
        "caption": f"caption {clip_id}",
        "poster_url": f"https://res.cloudinary.com/demo/{clip_id}.webp",
        "duration_s": 30,
        "renditions": {
            "480p": {
                "url": f"https://res.cloudinary.com/demo/{clip_id}_480.mp4",
                "width": 480,
                "bytes": 1_900_000,
            },
            "720p": {
                "url": f"https://res.cloudinary.com/demo/{clip_id}_720.mp4",
                "width": 720,
                "bytes": 4_100_000,
            },
        },
        "like_count": likes,
        "comment_count": 0,
        "view_count": 0,
        "published_at": published if status == state_machine.PUBLISHED else None,
        "category_id": None,
        # Private administration data that must NEVER reach a response.
        "cloudinary_public_id": f"clips/{vendor}/{clip_id}",
    }


@pytest.fixture
def store() -> Store:
    st = Store()
    st.rows("vendors").extend(
        [
            {"id": VENDOR_A, "display_name": "Alpha Traders", "slug": "alpha", "status": "active"},
            {"id": VENDOR_B, "display_name": "Beta Goods", "slug": "beta", "status": "active"},
        ]
    )
    st.rows("vendor_listings").append(
        {
            "id": LISTING_A,
            "vendor_id": VENDOR_A,
            "title_override": "Solar lamp",
            "price_ngwee": 45_000,
            "status": "active",
        }
    )
    for name in ("video_clips", "clip_products"):
        st.rows(name)
    st.rows("feature_flags").append({"flag": "clips", "enabled": True})
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    monkeypatch.setattr("app.routers.clips.get_supabase_client", lambda: wrapper, raising=False)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _auth(monkeypatch: pytest.MonkeyPatch, user_id: str = VENDOR_USER_A) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )
    return {"Authorization": f"Bearer {JWT}"}


# --- Published-only ---------------------------------------------------------
@pytest.mark.parametrize(
    "status",
    ["draft", "screening", "pending_review", "rejected", "taken_down"],
)
def test_a_non_published_clip_never_appears_in_the_feed(
    api: TestClient, store: Store, status: str
) -> None:
    store.rows("video_clips").append(_clip("hidden", status=status))
    store.rows("video_clips").append(_clip("shown"))

    body = api.get("/clips/feed").json()

    assert [item["id"] for item in body["items"]] == ["shown"]


@pytest.mark.parametrize(
    "status",
    ["draft", "screening", "pending_review", "rejected", "taken_down"],
)
def test_a_non_published_clip_is_404_on_detail(
    api: TestClient, store: Store, status: str
) -> None:
    store.rows("video_clips").append(_clip("hidden", status=status))

    assert api.get("/clips/hidden").status_code == 404


def test_the_owning_vendor_cannot_see_their_own_unpublished_clip(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vendor's own view is M17-P06's authenticated surface, not this one."""
    headers = _auth(monkeypatch)
    store.rows("video_clips").append(_clip("mine", vendor=VENDOR_A, status="pending_review"))

    assert api.get("/clips/mine", headers=headers).status_code == 404
    assert api.get("/clips/feed", headers=headers).json()["items"] == []


def test_a_missing_clip_and_an_unpublished_clip_answer_identically(
    api: TestClient, store: Store
) -> None:
    """A different status here would confirm that an unpublished id exists."""
    store.rows("video_clips").append(_clip("hidden", status="pending_review"))

    hidden = api.get("/clips/hidden")
    absent = api.get("/clips/does-not-exist")

    assert hidden.status_code == absent.status_code == 404
    assert hidden.json()["error"]["code"] == absent.json()["error"]["code"]


def test_taking_a_clip_down_removes_it_from_feed_and_detail_immediately(
    api: TestClient, store: Store
) -> None:
    store.rows("video_clips").append(_clip("c1"))
    assert [i["id"] for i in api.get("/clips/feed").json()["items"]] == ["c1"]
    assert api.get("/clips/c1").status_code == 200

    # No cache to invalidate: status IS the visibility.
    store.rows("video_clips")[0]["status"] = state_machine.TAKEN_DOWN

    assert api.get("/clips/feed").json()["items"] == []
    assert api.get("/clips/c1").status_code == 404


def test_a_suspended_vendors_clips_are_not_served(api: TestClient, store: Store) -> None:
    store.rows("video_clips").append(_clip("c1", vendor=VENDOR_B))
    store.rows("vendors")[1]["status"] = "suspended"

    assert api.get("/clips/feed").json()["items"] == []
    assert api.get("/clips/c1").status_code == 404


# --- Card-complete payload --------------------------------------------------
def test_a_feed_item_carries_everything_needed_to_render_a_card(
    api: TestClient, store: Store
) -> None:
    store.rows("video_clips").append(_clip("c1", likes=7))
    store.rows("clip_products").append(
        {"clip_id": "c1", "listing_id": LISTING_A, "sort_order": 0}
    )

    item = api.get("/clips/feed").json()["items"][0]

    assert item["poster_url"].endswith(".webp")
    assert item["duration_s"] == 30
    assert item["like_count"] == 7
    assert item["comment_count"] == 0
    assert item["view_count"] == 0
    assert item["vendor"]["display_name"] == "Alpha Traders"
    assert item["listings"][0]["listing_id"] == LISTING_A
    assert item["listings"][0]["price_ngwee"] == 45_000


def test_every_rendition_reports_its_byte_size_for_the_dv5_chip(
    api: TestClient, store: Store
) -> None:
    """D-V5: the size chip shown before tap-to-play must be a real number."""
    store.rows("video_clips").append(_clip("c1"))

    renditions = api.get("/clips/feed").json()["items"][0]["renditions"]

    assert set(renditions) == {"480p", "720p"}
    assert renditions["480p"]["bytes"] == 1_900_000
    assert renditions["720p"]["bytes"] == 4_100_000
    assert renditions["480p"]["bytes"] < renditions["720p"]["bytes"]


def test_a_delisted_listing_is_not_advertised_on_a_clip(
    api: TestClient, store: Store
) -> None:
    """An overlay offering an add-to-cart that cannot succeed is worse than none."""
    store.rows("video_clips").append(_clip("c1"))
    store.rows("clip_products").append(
        {"clip_id": "c1", "listing_id": LISTING_A, "sort_order": 0}
    )
    store.rows("vendor_listings")[0]["status"] = "paused"

    assert api.get("/clips/feed").json()["items"][0]["listings"] == []


def test_rendering_a_page_of_cards_costs_one_request(
    api: TestClient, store: Store
) -> None:
    for index in range(5):
        store.rows("video_clips").append(_clip(f"c{index}", minutes_old=index))
        store.rows("clip_products").append(
            {"clip_id": f"c{index}", "listing_id": LISTING_A, "sort_order": 0}
        )

    body = api.get("/clips/feed").json()

    assert len(body["items"]) == 5
    for item in body["items"]:
        assert item["poster_url"] and item["renditions"] and item["listings"]


# --- No private Cloudinary data ---------------------------------------------
def test_no_response_leaks_private_cloudinary_administration_data(
    api: TestClient, store: Store
) -> None:
    store.rows("video_clips").append(_clip("c1"))

    payloads = [
        json.dumps(api.get("/clips/feed").json()),
        json.dumps(api.get("/clips/c1").json()),
        json.dumps(api.get("/clips/c1/ranking").json()),
    ]

    for payload in payloads:
        for forbidden in (
            "api_secret",
            "cloudinary_public_id",
            "signature",
            "api_key",
            "timestamp",
            "api.cloudinary.com",
            "upload_preset",
        ):
            assert forbidden not in payload


def test_the_response_model_has_no_field_for_private_upload_data() -> None:
    """Structural, not textual: the shape itself cannot carry these."""
    from app.routers.clips import ClipOut

    fields = set(ClipOut.model_fields)
    assert not fields & {"cloudinary_public_id", "signature", "api_key", "api_secret"}


# --- Cursor pagination ------------------------------------------------------
def test_pages_do_not_overlap_or_skip(api: TestClient, store: Store) -> None:
    for index in range(9):
        store.rows("video_clips").append(_clip(f"c{index}", minutes_old=index))

    first = api.get("/clips/feed", params={"limit": 3}).json()
    second = api.get(
        "/clips/feed", params={"limit": 3, "cursor": first["next_cursor"]}
    ).json()
    third = api.get(
        "/clips/feed", params={"limit": 3, "cursor": second["next_cursor"]}
    ).json()

    ids = [i["id"] for i in first["items"] + second["items"] + third["items"]]
    assert len(ids) == 9
    assert len(set(ids)) == 9


def test_the_cursor_is_opaque_and_carries_no_offset(api: TestClient, store: Store) -> None:
    import base64

    for index in range(4):
        store.rows("video_clips").append(_clip(f"c{index}", minutes_old=index))

    cursor = api.get("/clips/feed", params={"limit": 2}).json()["next_cursor"]
    assert cursor is not None

    decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    assert "offset" not in decoded
    assert "published_before" in decoded


def test_new_clips_arriving_mid_scroll_do_not_shift_the_page_boundary(
    api: TestClient, store: Store
) -> None:
    """The failure OFFSET pagination has and a keyset cursor does not."""
    for index in range(6):
        store.rows("video_clips").append(_clip(f"c{index}", minutes_old=index + 10))

    first = api.get("/clips/feed", params={"limit": 3}).json()
    # Three brand-new clips land while the reader is on page one.
    for index in range(3):
        store.rows("video_clips").append(_clip(f"new{index}", minutes_old=index))

    second = api.get(
        "/clips/feed", params={"limit": 3, "cursor": first["next_cursor"]}
    ).json()

    seen = {i["id"] for i in first["items"]}
    assert not seen & {i["id"] for i in second["items"]}
    assert not any(i["id"].startswith("new") for i in second["items"])


def test_the_last_page_reports_no_next_cursor(api: TestClient, store: Store) -> None:
    for index in range(2):
        store.rows("video_clips").append(_clip(f"c{index}", minutes_old=index))

    body = api.get("/clips/feed", params={"limit": 5}).json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is None


def test_a_malformed_cursor_is_rejected_rather_than_silently_reset(
    api: TestClient, store: Store
) -> None:
    store.rows("video_clips").append(_clip("c1"))

    response = api.get("/clips/feed", params={"cursor": "!!!not-base64!!!"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_the_page_size_is_capped(api: TestClient, store: Store) -> None:
    assert api.get("/clips/feed", params={"limit": 500}).status_code == 422
    assert api.get("/clips/feed", params={"limit": 0}).status_code == 422


# --- Ranking explainability -------------------------------------------------
def test_the_ranking_endpoint_returns_a_per_component_breakdown(
    api: TestClient, store: Store
) -> None:
    store.rows("video_clips").append(_clip("c1", likes=9, minutes_old=120))

    body = api.get("/clips/c1/ranking").json()

    for key in ("freshness", "like_term", "order_term", "engagement", "score", "formula"):
        assert key in body
    assert body["max_per_vendor_per_page"] == 2


def test_the_ranking_endpoint_is_published_only(api: TestClient, store: Store) -> None:
    store.rows("video_clips").append(_clip("c1", status="pending_review"))

    assert api.get("/clips/c1/ranking").status_code == 404


# --- Read surface stays read-only -------------------------------------------
def test_the_feed_router_declares_no_mutating_routes() -> None:
    from app.routers import clips

    for route in clips.router.routes:
        assert set(getattr(route, "methods", set())) <= {"GET", "HEAD"}
