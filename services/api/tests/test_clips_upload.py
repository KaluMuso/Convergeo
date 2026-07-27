"""M17-P02 — signed clip upload, transcode callback, automated screen.

The claims worth defending:

* the **image path is untouched** — a video preset leaking into `listing` signing
  would raise the image cap eightfold and admit video formats to a surface that
  has never accepted them;
* every **signed** parameter is also **returned**, because a signed-but-unreturned
  param is the documented cause of Cloudinary's ``#416 Invalid Signature`` (the
  trap already recorded on ``SignUploadResponse``);
* a prohibited caption **never receives an upload slot** — screening after upload
  would mean paying to store and transcode content we were always going to reject;
* **nothing in this pebble can reach ``published``**, asserted against the state
  machine rather than by reading the code.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import create_app
from app.media.cloudinary_signing import (
    CLIP_ALLOWED_FORMATS,
    DEFAULT_ALLOWED_FORMATS,
    MAX_CLIP_BYTES,
    MAX_CLIP_DURATION_S,
    build_signed_clip_params,
    sign_upload_parameters,
)
from app.services.clips import screen, state_machine
from fastapi.testclient import TestClient

VENDOR_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
VENDOR_USER_ID = "11111111-1111-4111-8111-111111111111"
CATEGORY_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
JWT = "valid.jwt.token"
CLOUDINARY_URL = "cloudinary://key123:secret456@democloud"
WEBHOOK_SECRET = "cld-webhook-secret"


# --- Fake Supabase ----------------------------------------------------------
class FakeQuery:
    def __init__(self, parent: FakeTable) -> None:
        self._parent = parent
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._op: str | None = None
        self._payload: dict[str, Any] | None = None

    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append((column, value))
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
        return all(row.get(column) == value for column, value in self._filters)

    def execute(self) -> MagicMock:
        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            self._parent.enforce_unique(row)
            row.setdefault("id", f"{self._parent.name}-{len(self._parent.rows)}")
            self._parent.rows.append(row)
            return MagicMock(data=[row])

        if self._op == "update":
            assert self._payload is not None
            updated: list[dict[str, Any]] = []
            for row in self._parent.rows:
                if self._match(row):
                    row.update(self._payload)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        rows = [dict(row) for row in self._parent.rows if self._match(row)]
        if self._maybe_single:
            return MagicMock(data=rows[0] if rows else None)
        return MagicMock(data=rows)


class UniqueViolation(Exception):
    """Stands in for Postgres 23505 so replay dedupe is exercised for real."""


class FakeTable:
    UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
        "webhook_events": ("provider", "event_id"),
    }

    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def enforce_unique(self, row: dict[str, Any]) -> None:
        columns = self.UNIQUE_KEYS.get(self.name)
        if not columns:
            return
        key = tuple(row.get(c) for c in columns)
        for existing in self.rows:
            if tuple(existing.get(c) for c in columns) == key:
                raise UniqueViolation(f"{self.name} {columns} exists")

    def select(self, columns: str = "*", **kwargs: Any) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)


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


# --- Fixtures ---------------------------------------------------------------
@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setenv("CLOUDINARY_URL", CLOUDINARY_URL)
    monkeypatch.setenv("CLOUDINARY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.delenv("CLOUDINARY_NOTIFICATION_URL", raising=False)
    from app.settings import get_settings

    get_settings.cache_clear()

    st = Store()
    st.rows("vendors").append(
        {
            "id": VENDOR_ID,
            "owner_user_id": VENDOR_USER_ID,
            "status": "active",
            "kyc_tier": 2,
        }
    )
    st.rows("categories").append(
        {"id": CATEGORY_ID, "name": "Electronics", "prohibited": False}
    )
    for name in ("video_clips", "audit_log", "webhook_events"):
        st.rows(name)
    return st


@pytest.fixture
def api(store: Store, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    wrapper = store
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: wrapper)
    for module in ("app.routers.clips_upload", "app.routers.webhooks_cloudinary"):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: wrapper, raising=False)
    monkeypatch.setattr(
        "app.media.authz.get_supabase_client", lambda: wrapper, raising=False
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client
    from app.settings import get_settings

    get_settings.cache_clear()


def _auth(monkeypatch: pytest.MonkeyPatch, user_id: str = VENDOR_USER_ID) -> None:
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": user_id, "exp": 9_999_999_999},
    )
    monkeypatch.setattr(
        "app.core.auth._load_user_roles",
        lambda user_id, service_client: frozenset({"vendor"}),
    )


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {JWT}"}


# --- The image path must be provably unchanged ------------------------------
def test_the_image_preset_is_untouched_by_the_video_preset() -> None:
    """A video preset leaking into the listing path is the failure to prevent."""
    assert DEFAULT_ALLOWED_FORMATS == "jpg,png,webp,avif"
    assert "mp4" not in DEFAULT_ALLOWED_FORMATS
    assert CLIP_ALLOWED_FORMATS == "mp4,mov,webm"
    for image_format in ("jpg", "png", "avif"):
        assert image_format not in CLIP_ALLOWED_FORMATS


def test_the_listing_kind_still_caps_at_ten_megabytes() -> None:
    from app.routers.media import MAX_LISTING_IMAGE_BYTES

    assert MAX_LISTING_IMAGE_BYTES == 10_485_760
    assert MAX_CLIP_BYTES == 83_886_080
    assert MAX_CLIP_BYTES > MAX_LISTING_IMAGE_BYTES


# --- Signing: the #416 regression guard -------------------------------------
def test_every_signed_param_is_returned() -> None:
    """A signed-but-unreturned parameter reproduces #416 Invalid Signature."""
    signed = build_signed_clip_params(
        folder=f"clips/{VENDOR_ID}",
        public_id="clip-1",
        timestamp=1_800_000_000,
        api_secret="secret456",
        notification_url="https://api.example/webhooks/cloudinary",
    )

    returned = {k: v for k, v in signed.items() if k != "signature"}
    recomputed = sign_upload_parameters(returned, "secret456")
    assert recomputed == signed["signature"], (
        "the returned params do not reproduce the signature — a signed param is missing "
        "from the response, which is exactly the #416 failure"
    )


def test_the_signature_covers_the_eager_transform() -> None:
    """If `eager` were unsigned, a client could ask for any rendition it liked."""
    base = build_signed_clip_params(
        folder="clips/v", public_id="c", timestamp=1, api_secret="s"
    )
    tampered = dict(base)
    tampered["eager"] = "c_limit,w_4096"
    del tampered["signature"]
    assert sign_upload_parameters(tampered, "s") != base["signature"]


def test_signing_never_returns_the_api_secret() -> None:
    signed = build_signed_clip_params(
        folder="clips/v", public_id="c", timestamp=1, api_secret="secret456"
    )
    assert "secret456" not in json.dumps(signed)
    assert "api_secret" not in signed


def test_the_video_preset_requests_both_ceilings_and_a_poster() -> None:
    from app.media.cloudinary_signing import CLIP_EAGER_TRANSFORMATIONS

    assert "w_480" in CLIP_EAGER_TRANSFORMATIONS
    assert "w_720" in CLIP_EAGER_TRANSFORMATIONS
    assert "f_webp" in CLIP_EAGER_TRANSFORMATIONS
    # D-V4: progressive MP4, not HLS — hls.js alone would blow half a route budget.
    assert "f_mp4" in CLIP_EAGER_TRANSFORMATIONS
    assert "m3u8" not in CLIP_EAGER_TRANSFORMATIONS


# --- POST /clips ------------------------------------------------------------
def test_create_requires_authentication(api: TestClient, store: Store) -> None:
    assert api.post("/clips", json={"caption": "hello"}).status_code == 401


def test_create_returns_a_draft_and_signed_params(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch)
    response = api.post(
        "/clips",
        headers=_headers(),
        json={"caption": "Fresh chitenge, 6 yards", "category_id": CATEGORY_ID},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["folder"] == f"clips/{VENDOR_ID}"
    assert body["allowed_formats"] == CLIP_ALLOWED_FORMATS
    assert body["max_file_size"] == MAX_CLIP_BYTES
    assert body["eager_async"] == "true"
    assert "api_secret" not in response.text

    clip = store.rows("video_clips")[0]
    assert clip["vendor_id"] == VENDOR_ID
    # The draft is waiting for bytes; the callback moves it onward.
    assert clip["status"] == state_machine.SCREENING


def test_the_public_id_is_server_generated(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller-chosen public_id could steer the upload at another object."""
    _auth(monkeypatch)
    response = api.post(
        "/clips",
        headers=_headers(),
        json={"caption": "ok", "public_id": "../../listings/other-vendor/steal"},
    )
    assert response.status_code == 200, response.text
    clip_id = store.rows("video_clips")[0]["id"]
    assert response.json()["public_id"] == clip_id
    assert ".." not in response.json()["public_id"]


def test_an_oversized_clip_is_refused_before_anything_is_created(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch)
    response = api.post(
        "/clips",
        headers=_headers(),
        json={"caption": "ok", "file_size_bytes": MAX_CLIP_BYTES + 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "file_too_large"
    assert store.rows("video_clips") == []


def test_an_overlong_clip_is_refused(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch)
    response = api.post(
        "/clips",
        headers=_headers(),
        json={"caption": "ok", "duration_s": MAX_CLIP_DURATION_S + 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "clip_too_long"
    assert store.rows("video_clips") == []


def test_a_prohibited_caption_never_gets_an_upload_slot(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Screen before signing: we never pay to store what we would reject."""
    _auth(monkeypatch)
    monkeypatch.setattr(
        "app.services.clips.screen.screen_listing",
        lambda **kwargs: MagicMock(allowed=False, reason="keyword", matched="banned"),
    )
    response = api.post("/clips", headers=_headers(), json={"caption": "banned goods"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "prohibited_clip"
    assert store.rows("video_clips") == [], "a rejected caption created a draft"
    assert "signature" not in response.text


def test_a_prohibited_category_is_refused(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch)
    store.rows("categories")[0]["prohibited"] = True
    response = api.post(
        "/clips", headers=_headers(), json={"caption": "ok", "category_id": CATEGORY_ID}
    )
    assert response.status_code == 422
    assert store.rows("video_clips") == []


def test_an_unknown_category_is_404(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _auth(monkeypatch)
    response = api.post(
        "/clips",
        headers=_headers(),
        json={"caption": "ok", "category_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
    assert store.rows("video_clips") == []


def test_a_user_without_a_vendor_row_is_refused(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-V7: vendors only. Ownership is DB-sourced, never claim-trusted."""
    _auth(monkeypatch, user_id="99999999-9999-4999-8999-999999999999")
    response = api.post("/clips", headers=_headers(), json={"caption": "ok"})
    assert response.status_code in {401, 403}
    assert store.rows("video_clips") == []


# --- The screen -------------------------------------------------------------
def test_the_screen_has_no_path_to_published(store: Store) -> None:
    """Structural, not a reading: `published` is unreachable from `screening`."""
    assert state_machine.PUBLISHED not in state_machine.ALLOWED_TRANSITIONS[
        state_machine.SCREENING
    ]


def test_a_passing_screen_queues_for_a_human(store: Store) -> None:
    store.rows("video_clips").append(
        {"id": "clip-1", "vendor_id": VENDOR_ID, "status": state_machine.SCREENING}
    )
    verdict = screen.apply_screen(store, clip_id="clip-1", caption="Nice fridge")
    assert verdict.allowed
    assert store.rows("video_clips")[0]["status"] == state_machine.PENDING_REVIEW


def test_a_failing_screen_rejects_with_a_reason(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows("video_clips").append(
        {"id": "clip-1", "vendor_id": VENDOR_ID, "status": state_machine.SCREENING}
    )
    monkeypatch.setattr(
        "app.services.clips.screen.screen_listing",
        lambda **kwargs: MagicMock(allowed=False, reason="keyword", matched="banned"),
    )
    verdict = screen.apply_screen(store, clip_id="clip-1", caption="banned")

    assert not verdict.allowed
    row = store.rows("video_clips")[0]
    assert row["status"] == state_machine.REJECTED
    assert row["rejection_reason"] == "prohibited_keyword"


def test_an_overlong_caption_is_refused_by_the_screen() -> None:
    verdict = screen.screen_text("x" * (screen.MAX_CAPTION_LEN + 1))
    assert not verdict.allowed
    assert verdict.reason == "caption_too_long"


def test_the_screen_reuses_the_shared_prohibited_module() -> None:
    """A second copy of the prohibited list is the copy that stops blocking."""
    import inspect

    from app.services.clips import screen as screen_module

    source = inspect.getsource(screen_module)
    assert "from app.services.moderation.prohibited import screen_listing" in source
    assert "PROHIBITED_KEYWORDS" not in source, "the keyword list must not be re-declared"


# --- Transcode callback -----------------------------------------------------
def _callback_body(
    *,
    clip_id: str,
    duration: float = 20.0,
    include_480: bool = True,
    include_720: bool = True,
    include_poster: bool = True,
    notification_id: str = "notif-1",
) -> bytes:
    eager: list[dict[str, Any]] = []
    if include_480:
        eager.append(
            {"secure_url": "https://cdn/480.mp4", "width": 480, "format": "mp4", "bytes": 1}
        )
    if include_720:
        eager.append(
            {"secure_url": "https://cdn/720.mp4", "width": 720, "format": "mp4", "bytes": 2}
        )
    if include_poster:
        eager.append(
            {"secure_url": "https://cdn/poster.webp", "width": 480, "format": "webp"}
        )
    return json.dumps(
        {
            "public_id": f"clips/{VENDOR_ID}/{clip_id}",
            "duration": duration,
            "eager": eager,
            "notification_id": notification_id,
        }
    ).encode()


def _sign_callback(raw: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = hashlib.sha1(
        raw + timestamp.encode("utf-8") + secret.encode("utf-8")
    ).hexdigest()
    return {"X-Cld-Signature": signature, "X-Cld-Timestamp": timestamp}


def _seed_screening_clip(store: Store, clip_id: str = "clip-1") -> str:
    store.rows("video_clips").append(
        {
            "id": clip_id,
            "vendor_id": VENDOR_ID,
            "status": state_machine.SCREENING,
            "caption": "Nice fridge",
            "duration_s": 20,
            "renditions": {},
            "poster_url": None,
        }
    )
    return clip_id


def test_a_valid_callback_advances_to_pending_review(
    api: TestClient, store: Store
) -> None:
    clip_id = _seed_screening_clip(store)
    raw = _callback_body(clip_id=clip_id)

    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert response.status_code == 200

    row = store.rows("video_clips")[0]
    assert row["status"] == state_machine.PENDING_REVIEW
    assert set(row["renditions"]) == {"480p", "720p"}
    assert row["poster_url"] == "https://cdn/poster.webp"


def test_a_bad_signature_is_403(api: TestClient, store: Store) -> None:
    clip_id = _seed_screening_clip(store)
    raw = _callback_body(clip_id=clip_id)

    response = api.post(
        "/webhooks/cloudinary", content=raw, headers=_sign_callback(raw, secret="wrong")
    )
    assert response.status_code == 403
    assert store.rows("video_clips")[0]["status"] == state_machine.SCREENING


def test_an_unsigned_callback_is_403(api: TestClient, store: Store) -> None:
    clip_id = _seed_screening_clip(store)
    response = api.post("/webhooks/cloudinary", content=_callback_body(clip_id=clip_id))
    assert response.status_code == 403


def test_a_missing_secret_fails_closed(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unconfigured verifier must refuse, not wave callbacks through."""
    monkeypatch.setenv("CLOUDINARY_WEBHOOK_SECRET", "")
    from app.settings import get_settings

    get_settings.cache_clear()

    clip_id = _seed_screening_clip(store)
    raw = _callback_body(clip_id=clip_id)
    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))

    assert response.status_code == 403
    assert store.rows("video_clips")[0]["status"] == state_machine.SCREENING


def test_a_replayed_callback_is_a_no_op(api: TestClient, store: Store) -> None:
    clip_id = _seed_screening_clip(store)
    raw = _callback_body(clip_id=clip_id)

    first = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert first.status_code == 200
    assert store.rows("video_clips")[0]["status"] == state_machine.PENDING_REVIEW

    audit_before = len(store.rows("audit_log"))
    second = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert second.status_code == 200
    assert len(store.rows("audit_log")) == audit_before, "replay caused a second effect"


def test_a_callback_for_an_unknown_clip_creates_nothing(
    api: TestClient, store: Store
) -> None:
    raw = _callback_body(clip_id="00000000-0000-0000-0000-000000000000")
    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert response.status_code == 200
    assert store.rows("video_clips") == [], "a callback conjured a clip"


def test_an_early_callback_leaves_a_draft_alone(api: TestClient, store: Store) -> None:
    """Out-of-order delivery must be safely retryable, not a crash."""
    store.rows("video_clips").append(
        {
            "id": "clip-1",
            "vendor_id": VENDOR_ID,
            "status": state_machine.DRAFT,
            "caption": "x",
        }
    )
    raw = _callback_body(clip_id="clip-1")
    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert response.status_code == 200
    assert store.rows("video_clips")[0]["status"] == state_machine.DRAFT


@pytest.mark.parametrize(
    ("kwargs", "expected_reason"),
    [
        ({"include_480": False}, "missing_renditions"),
        ({"include_720": False}, "missing_renditions"),
        ({"include_poster": False}, "missing_poster"),
        ({"duration": 90.0}, "duration_exceeded"),
    ],
)
def test_media_that_fails_our_own_limits_is_rejected_not_coerced(
    api: TestClient, store: Store, kwargs: dict[str, Any], expected_reason: str
) -> None:
    """Do not trust the callback where our schema constrains the answer."""
    clip_id = _seed_screening_clip(store)
    raw = _callback_body(clip_id=clip_id, **kwargs)

    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert response.status_code == 200

    row = store.rows("video_clips")[0]
    assert row["status"] == state_machine.REJECTED
    assert row["rejection_reason"] == expected_reason


def test_a_prohibited_caption_is_rejected_at_callback_time(
    api: TestClient, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip_id = _seed_screening_clip(store)
    monkeypatch.setattr(
        "app.services.clips.screen.screen_listing",
        lambda **kwargs: MagicMock(allowed=False, reason="keyword", matched="banned"),
    )
    raw = _callback_body(clip_id=clip_id)

    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert response.status_code == 200
    assert store.rows("video_clips")[0]["status"] == state_machine.REJECTED


def test_the_renditions_are_keyed_by_width_not_array_order(
    api: TestClient, store: Store
) -> None:
    """Mislabelling 720p as 480p would send cellular viewers the big file."""
    clip_id = _seed_screening_clip(store)
    payload = json.loads(_callback_body(clip_id=clip_id))
    payload["eager"].reverse()
    raw = json.dumps(payload).encode()

    response = api.post("/webhooks/cloudinary", content=raw, headers=_sign_callback(raw))
    assert response.status_code == 200

    renditions = store.rows("video_clips")[0]["renditions"]
    assert renditions["480p"]["url"] == "https://cdn/480.mp4"
    assert renditions["720p"]["url"] == "https://cdn/720.mp4"


def test_the_callback_module_cannot_publish() -> None:
    """No literal 'published' anywhere in the upload lane."""
    import inspect

    from app.routers import webhooks_cloudinary

    source = inspect.getsource(webhooks_cloudinary)
    assert "PUBLISHED" not in source
    assert "state_machine.publish" not in source
