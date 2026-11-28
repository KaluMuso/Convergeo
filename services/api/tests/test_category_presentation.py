"""Admin category icon / banner / banner copy + the cached public read."""

from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.ttl_cache import InMemoryTtlCacheStore, clear_ttl_cache_store
from app.main import create_app
from app.services.categories.presentation import (
    CategoryPresentationUpsert,
    list_public_presentations,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

USER_ID = "11111111-1111-1111-1111-111111111111"
TOKEN = "valid.jwt.token"
GROCERIES_ID = "c0000001-0000-4000-8000-000000000001"
BANNED_ID = "c0000002-0000-4000-8000-000000000002"
MISSING_ID = "c0000009-0000-4000-8000-000000000009"


class FakeStore:
    def __init__(self) -> None:
        self.categories: list[dict[str, Any]] = [
            {"id": GROCERIES_ID, "slug": "groceries-staples", "prohibited": False},
            {"id": BANNED_ID, "slug": "weapons", "prohibited": True},
        ]
        self.presentations: list[dict[str, Any]] = []
        self.audit_rows: list[dict[str, Any]] = []
        self.presentation_reads = 0
        self.missing_table = False


class FakeQuery:
    def __init__(self, store: FakeStore, name: str) -> None:
        self._store = store
        self._name = name
        self._filters: list[tuple[str, Any]] = []
        self._upsert: dict[str, Any] | None = None
        self._insert: dict[str, Any] | None = None
        self._delete = False
        self._in: tuple[str, list[str]] | None = None

    def select(self, _columns: str) -> FakeQuery:
        return self

    def eq(self, key: str, value: Any) -> FakeQuery:
        self._filters.append((key, value))
        return self

    def in_(self, key: str, values: list[Any]) -> FakeQuery:
        self._in = (key, [str(v) for v in values])
        return self

    def limit(self, _count: int) -> FakeQuery:
        return self

    def upsert(self, payload: dict[str, Any], on_conflict: str = "") -> FakeQuery:
        assert on_conflict == "category_id"
        self._upsert = payload
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._insert = payload
        return self

    def delete(self) -> FakeQuery:
        self._delete = True
        return self

    def _source(self) -> list[dict[str, Any]]:
        if self._name == "categories":
            return self._store.categories
        if self._name == "category_presentations":
            return self._store.presentations
        return []

    def _matches(self, row: dict[str, Any]) -> bool:
        if self._in is not None and str(row.get(self._in[0])) not in self._in[1]:
            return False
        return all(str(row.get(key)) == str(value) for key, value in self._filters)

    def execute(self) -> MagicMock:
        if self._name == "audit_log":
            assert self._insert is not None
            self._store.audit_rows.append(self._insert)
            return MagicMock(data=[{**self._insert, "id": "a" * 8}])
        if self._name == "category_presentations":
            if self._store.missing_table:
                raise RuntimeError("{'code': 'PGRST205', 'message': 'relation not found'}")
            if self._upsert is not None:
                row = {**self._upsert, "updated_at": "2026-11-28T18:00:00+00:00"}
                self._store.presentations = [
                    r for r in self._store.presentations if r["category_id"] != row["category_id"]
                ]
                self._store.presentations.append(row)
                return MagicMock(data=[copy.deepcopy(row)])
            if self._delete:
                self._store.presentations = [
                    r for r in self._store.presentations if not self._matches(r)
                ]
                return MagicMock(data=[])
            if not self._filters:
                self._store.presentation_reads += 1
        rows = [copy.deepcopy(r) for r in self._source() if self._matches(r)]
        return MagicMock(data=rows)


class FakeServiceClient:
    def __init__(self, store: FakeStore) -> None:
        self.client = MagicMock()
        self.client.table.side_effect = lambda name: FakeQuery(store, name)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Generator[FakeStore, None, None]:
    clear_ttl_cache_store()
    fake = FakeStore()
    service_client = FakeServiceClient(fake)
    monkeypatch.setattr("app.deps.get_supabase_service_client", lambda: service_client)
    monkeypatch.setattr("app.core.admin_audit.get_supabase_service_client", lambda: service_client)
    monkeypatch.setattr(
        "app.core.auth.verify_supabase_jwt",
        lambda token, settings: {"sub": USER_ID, "exp": 9_999_999_999},
    )
    yield fake
    clear_ttl_cache_store()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


def _as(monkeypatch: pytest.MonkeyPatch, *roles: str) -> dict[str, str]:
    monkeypatch.setattr(
        "app.core.auth._load_user_roles", lambda user_id, service_client: frozenset(roles)
    )
    return {"Authorization": f"Bearer {TOKEN}"}


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "icon_public_id": "categories/icons/rice",
        "banner_public_id": "categories/banners/rice",
        "banner_title_i18n": {"en": "Staples for less", "bem": "Ifya kulya"},
        "banner_description_i18n": {"en": "Mealie meal, rice and oil from Lusaka shops."},
    }
    body.update(overrides)
    return body


# --- validation -------------------------------------------------------------
def test_title_over_60_chars_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 60"):
        CategoryPresentationUpsert(banner_title_i18n={"en": "x" * 61})


def test_title_exactly_60_chars_accepted() -> None:
    body = CategoryPresentationUpsert(banner_title_i18n={"en": "x" * 60})
    assert body.banner_title_i18n["en"] == "x" * 60


def test_description_over_160_chars_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 160"):
        CategoryPresentationUpsert(
            banner_title_i18n={"en": "Title"},
            banner_description_i18n={"en": "y" * 161},
        )


def test_whitespace_is_collapsed_before_length_check() -> None:
    body = CategoryPresentationUpsert(banner_title_i18n={"en": "  Fresh   " + "a" * 50 + "  "})
    assert body.banner_title_i18n["en"] == "Fresh " + "a" * 50


def test_unknown_locale_rejected() -> None:
    with pytest.raises(ValidationError, match="unsupported locale"):
        CategoryPresentationUpsert(banner_title_i18n={"en": "Hi", "de": "Hallo"})


def test_english_required_when_any_locale_set() -> None:
    with pytest.raises(ValidationError, match="English"):
        CategoryPresentationUpsert(banner_title_i18n={"bem": "Ifya kulya"})


def test_empty_locale_text_is_dropped() -> None:
    body = CategoryPresentationUpsert(banner_title_i18n={"en": "Hi", "nya": "   "})
    assert body.banner_title_i18n == {"en": "Hi"}


def test_description_without_title_rejected() -> None:
    with pytest.raises(ValidationError, match="requires a banner title"):
        CategoryPresentationUpsert(banner_description_i18n={"en": "Words"})


@pytest.mark.parametrize(
    "public_id",
    ["../secrets", "categories/../x", "https://evil.example/x.png", "a b", "x" * 256],
)
def test_bad_public_id_rejected(public_id: str) -> None:
    with pytest.raises(ValidationError, match="public id"):
        CategoryPresentationUpsert(icon_public_id=public_id)


# --- admin routes -----------------------------------------------------------
def test_admin_upsert_writes_row_and_audit(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.put(
        f"/admin/config/categories/{GROCERIES_ID}/presentation",
        headers=_as(monkeypatch, "admin"),
        json=_body(),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["slug"] == "groceries-staples"
    assert payload["banner_title_i18n"] == {"en": "Staples for less", "bem": "Ifya kulya"}
    assert store.presentations[0]["updated_by"] == USER_ID
    assert [row["action"] for row in store.audit_rows] == ["config.category_presentation.upsert"]
    assert store.audit_rows[0]["before"] is None


def test_admin_upsert_over_limit_writes_nothing(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.put(
        f"/admin/config/categories/{GROCERIES_ID}/presentation",
        headers=_as(monkeypatch, "admin"),
        json=_body(banner_title_i18n={"en": "t" * 61}),
    )
    assert response.status_code == 422
    assert store.presentations == []
    assert store.audit_rows == []


def test_admin_upsert_empty_body_rejected(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.put(
        f"/admin/config/categories/{GROCERIES_ID}/presentation",
        headers=_as(monkeypatch, "admin"),
        json={},
    )
    assert response.status_code == 422
    assert store.presentations == []


def test_admin_upsert_unknown_category_404(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.put(
        f"/admin/config/categories/{MISSING_ID}/presentation",
        headers=_as(monkeypatch, "admin"),
        json=_body(),
    )
    assert response.status_code == 404
    assert store.presentations == []


@pytest.mark.parametrize("roles", [("customer",), ("vendor",), ("moderator",)])
def test_non_admin_cannot_write(
    client: TestClient,
    store: FakeStore,
    monkeypatch: pytest.MonkeyPatch,
    roles: tuple[str, ...],
) -> None:
    headers = _as(monkeypatch, *roles)
    put = client.put(
        f"/admin/config/categories/{GROCERIES_ID}/presentation", headers=headers, json=_body()
    )
    sign = client.post("/admin/config/category-media/sign", headers=headers, json={"kind": "icon"})
    assert put.status_code == 403
    assert sign.status_code == 403
    assert store.presentations == []


def test_unauthenticated_cannot_write(client: TestClient, store: FakeStore) -> None:
    response = client.put(f"/admin/config/categories/{GROCERIES_ID}/presentation", json=_body())
    assert response.status_code == 401
    assert store.presentations == []


def test_admin_delete_removes_row_and_audits(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _as(monkeypatch, "admin")
    client.put(
        f"/admin/config/categories/{GROCERIES_ID}/presentation", headers=headers, json=_body()
    )
    response = client.delete(
        f"/admin/config/categories/{GROCERIES_ID}/presentation", headers=headers
    )
    assert response.status_code == 204
    assert store.presentations == []
    assert store.audit_rows[-1]["action"] == "config.category_presentation.delete"


def test_admin_delete_missing_presentation_404(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.delete(
        f"/admin/config/categories/{GROCERIES_ID}/presentation",
        headers=_as(monkeypatch, "admin"),
    )
    assert response.status_code == 404
    assert store.audit_rows == []


def test_admin_list_includes_prohibited_categories(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.presentations = [
        {"category_id": BANNED_ID, "icon_public_id": "categories/icons/x"},
        {"category_id": GROCERIES_ID, "icon_public_id": "categories/icons/y"},
    ]
    response = client.get(
        "/admin/config/categories/presentations", headers=_as(monkeypatch, "admin")
    )
    assert response.status_code == 200
    assert {row["slug"] for row in response.json()} == {"groceries-staples", "weapons"}


def test_sign_pins_folder_and_never_returns_secret(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://key123:secret456@democloud")
    from app.settings import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/admin/config/category-media/sign",
            headers=_as(monkeypatch, "admin"),
            json={"kind": "banner", "file_size_bytes": 1000},
        )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["folder"] == "categories/banners"
    assert payload["cloud_name"] == "democloud"
    assert "secret456" not in response.text
    assert store.audit_rows[-1]["action"] == "config.category_media.sign"


def test_sign_rejects_oversized_icon(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.post(
        "/admin/config/category-media/sign",
        headers=_as(monkeypatch, "admin"),
        json={"kind": "icon", "file_size_bytes": 3_000_000},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "file_too_large"


def test_sign_rejects_unknown_kind(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.post(
        "/admin/config/category-media/sign",
        headers=_as(monkeypatch, "admin"),
        json={"kind": "listing"},
    )
    assert response.status_code == 422


# --- public read + cache ----------------------------------------------------
def test_public_read_hides_prohibited_and_sets_cache_header(
    client: TestClient, store: FakeStore
) -> None:
    store.presentations = [
        {"category_id": BANNED_ID, "icon_public_id": "categories/icons/x"},
        {
            "category_id": GROCERIES_ID,
            "banner_public_id": "categories/banners/y",
            "banner_title_i18n": {"en": "Staples"},
        },
    ]
    response = client.get("/categories/presentation")
    assert response.status_code == 200
    assert [row["slug"] for row in response.json()] == ["groceries-staples"]
    assert "s-maxage=300" in response.headers["cache-control"]


def test_public_read_is_cached_and_busted_by_admin_write(
    client: TestClient, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/categories/presentation").json() == []
    assert client.get("/categories/presentation").json() == []
    assert store.presentation_reads == 1

    client.put(
        f"/admin/config/categories/{GROCERIES_ID}/presentation",
        headers=_as(monkeypatch, "admin"),
        json=_body(),
    )
    rows = client.get("/categories/presentation").json()
    assert [row["slug"] for row in rows] == ["groceries-staples"]


def test_public_read_degrades_when_table_missing(store: FakeStore) -> None:
    store.missing_table = True
    service_client = FakeServiceClient(store)
    assert list_public_presentations(service_client.client, store=InMemoryTtlCacheStore()) == []


@pytest.mark.parametrize(
    ("field", "public_id"),
    [
        ("icon_public_id", "demo/categories/rice"),
        ("icon_public_id", "categories/banners/rice"),
        ("icon_public_id", "categories/icons/"),
        ("banner_public_id", "listings/v1/photo"),
    ],
)
def test_public_id_outside_category_folder_rejected(field: str, public_id: str) -> None:
    with pytest.raises(ValidationError, match="category image upload"):
        CategoryPresentationUpsert(**{field: public_id})


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "draft"},
        {"status": "blocked"},
        {"status": "published", "show_in_customer": False},
    ],
)
def test_public_read_hides_unpublished_taxonomy_rows(
    client: TestClient, store: FakeStore, extra: dict[str, Any]
) -> None:
    store.categories[0].update(extra)
    store.presentations = [{"category_id": GROCERIES_ID, "icon_public_id": "categories/icons/y"}]
    assert client.get("/categories/presentation").json() == []


def test_public_read_shows_published_customer_visible_rows(
    client: TestClient, store: FakeStore
) -> None:
    store.categories[0].update({"status": "published", "show_in_customer": True})
    store.presentations = [{"category_id": GROCERIES_ID, "icon_public_id": "categories/icons/y"}]
    assert [row["slug"] for row in client.get("/categories/presentation").json()] == [
        "groceries-staples"
    ]
