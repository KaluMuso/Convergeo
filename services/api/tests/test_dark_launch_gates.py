"""BATCH 1E — dark-launch server gates for Clips and vendor intake.

When a feature flag is OFF, every vendor/customer/public surface must fail closed
with 404 — not 403, not empty data, and not a partial leak. Admin and internal
surfaces stay operational for moderation and pilot ops.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.services.clips import flags as clips_flags
from app.services.clips import state_machine
from app.services.intake import config as intake_config
from fastapi.testclient import TestClient

VENDOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_USER_A = "11111111-1111-4111-8111-111111111111"
CLIP_ID = "c1000000-0000-4000-8000-000000000001"
SESSION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
JWT = "valid.jwt.token"


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
        rows = [
            dict(row)
            for row in self._parent.rows
            if all(row.get(c) == v for c, v in self._eq)
        ]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str = "*", **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(columns)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable())


class Store:
    def __init__(self) -> None:
        self.client = FakeSupabase()

    def rows(self, name: str) -> list[dict[str, Any]]:
        return self.client.table(name).rows


def _enable_clips(store: Store, *, enabled: bool = True) -> None:
    store.rows("feature_flags").append({"flag": clips_flags.CLIPS_FLAG, "enabled": enabled})


def _enable_intake_lane(
    store: Store,
    *,
    enabled: bool = True,
    vendor_ids: list[str] | None = None,
) -> None:
    store.rows("feature_flags").append(
        {"flag": intake_config.INTAKE_FLAG, "enabled": enabled}
    )
    store.rows("platform_config").append(
        {
            "key": intake_config.INTAKE_ALLOWLIST_KEY,
            "value": vendor_ids if vendor_ids is not None else [VENDOR_A],
        }
    )


def _seed_clip(store: Store) -> None:
    store.rows("video_clips").append(
        {
            "id": CLIP_ID,
            "vendor_id": VENDOR_A,
            "status": state_machine.PUBLISHED,
            "caption": "demo",
            "poster_url": "https://res.cloudinary.com/demo/poster.webp",
            "duration_s": 30,
            "renditions": {
                "480p": {
                    "url": "https://res.cloudinary.com/demo/clip.mp4",
                    "width": 480,
                    "bytes": 1_000_000,
                }
            },
            "like_count": 0,
            "comment_count": 0,
            "view_count": 0,
            "published_at": "2026-07-01T00:00:00+00:00",
            "category_id": None,
        }
    )
    store.rows("vendors").append(
        {
            "id": VENDOR_A,
            "owner_user_id": VENDOR_USER_A,
            "display_name": "Alpha",
            "slug": "alpha",
            "status": "active",
            "kyc_tier": 2,
        }
    )


def _seed_vendor_intake(store: Store) -> None:
    store.rows("vendors").append(
        {
            "id": VENDOR_A,
            "owner_user_id": VENDOR_USER_A,
            "status": "active",
            "kyc_tier": 2,
        }
    )
    store.rows("intake_sessions").append(
        {
            "id": SESSION_ID,
            "vendor_id": VENDOR_A,
            "binding_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "status": "ready_for_vendor_review",
            "pending_requests": [],
            "listing_id": None,
            "last_activity_at": "2026-07-01T00:00:00+00:00",
        }
    )


@pytest.fixture
def store() -> Store:
    st = Store()
    for name in (
        "feature_flags",
        "platform_config",
        "video_clips",
        "vendors",
        "clip_products",
        "vendor_listings",
        "intake_sessions",
        "intake_draft_fields",
        "intake_field_provenance",
        "intake_media",
    ):
        st.rows(name)
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    for module in (
        "app.routers.clips",
        "app.routers.clips_engagement",
        "app.routers.clips_upload",
        "app.routers.vendor_clips",
        "app.routers.vendor_intake",
        "app.routers.media",
        "app.media.authz",
    ):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: wrapper, raising=False)
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": VENDOR_USER_A, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )
    monkeypatch.setattr(
        "app.routers.vendor_intake.bump_rate_counter",
        lambda **_kwargs: (True, 0),
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {JWT}"}


# --- Clips: flag false ------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    ["/clips/feed", f"/clips/{CLIP_ID}", f"/clips/{CLIP_ID}/ranking"],
)
def test_clips_public_routes_404_when_flag_off(
    api: TestClient, store: Store, path: str
) -> None:
    _enable_clips(store, enabled=False)
    _seed_clip(store)
    assert api.get(path).status_code == 404


def test_clips_vendor_routes_404_when_flag_off(api: TestClient, store: Store) -> None:
    _enable_clips(store, enabled=False)
    _seed_clip(store)
    headers = _auth()
    assert api.get("/vendor/clips", headers=headers).status_code == 404
    assert api.get(f"/vendor/clips/{CLIP_ID}", headers=headers).status_code == 404


def test_clips_upload_404_when_flag_off(api: TestClient, store: Store) -> None:
    _enable_clips(store, enabled=False)
    store.rows("vendors").append(
        {
            "id": VENDOR_A,
            "owner_user_id": VENDOR_USER_A,
            "status": "active",
            "kyc_tier": 2,
        }
    )
    response = api.post("/clips", headers=_auth(), json={"caption": "hello"})
    assert response.status_code == 404


# --- Clips: flag true preserves behavior (unit-level) -----------------------
def test_clips_enabled_returns_true_when_flag_on() -> None:
    client = Store()
    _enable_clips(client, enabled=True)
    assert clips_flags.clips_enabled(client) is True


def test_lane_open_for_true_when_both_gates_pass() -> None:
    client = Store()
    _enable_intake_lane(client, enabled=True, vendor_ids=[VENDOR_A])
    assert intake_config.lane_open_for(client, VENDOR_A) is True


# --- Intake: flag false / not allowlisted -----------------------------------
@pytest.mark.parametrize(
    "enabled,allowlist",
    [(False, [VENDOR_A]), (True, [])],
)
def test_intake_vendor_api_404_when_lane_closed(
    api: TestClient,
    store: Store,
    enabled: bool,
    allowlist: list[str],
) -> None:
    _enable_intake_lane(store, enabled=enabled, vendor_ids=allowlist)
    _seed_vendor_intake(store)
    headers = _auth()
    assert api.get("/vendor/intake/sessions", headers=headers).status_code == 404
    assert (
        api.get(f"/vendor/intake/sessions/{SESSION_ID}", headers=headers).status_code == 404
    )


def test_require_clips_enabled_raises_404() -> None:
    client = Store()
    with pytest.raises(Exception) as exc:
        clips_flags.require_clips_enabled(client)
    assert exc.value.http_status == 404  # type: ignore[attr-defined]


def test_require_lane_open_for_raises_404_when_not_allowlisted() -> None:
    client = Store()
    _enable_intake_lane(client, enabled=True, vendor_ids=[])
    with pytest.raises(Exception) as exc:
        intake_config.require_lane_open_for(client, VENDOR_A)
    assert exc.value.http_status == 404  # type: ignore[attr-defined]
