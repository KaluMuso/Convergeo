"""Admin category manager API: authz, validation, guards, audit, public filtering."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests import test_home_feed as _base
from tests.test_home_feed import ADMIN_ID, CUSTOMER_ID, FakeClient, _login

fake = _base.fake
http = _base.http

ROOT = "cccccccc-0000-4000-8000-000000000001"
CHILD = "cccccccc-0000-4000-8000-000000000002"
OTHER = "cccccccc-0000-4000-8000-000000000003"
BASE = "/admin/catalog/taxonomy"


def _row(node_id: str, slug: str, parent: str | None, position: int, **extra: object) -> dict:
    return {
        "id": node_id,
        "slug": slug,
        "name": slug.title(),
        "parent_id": parent,
        "path": slug if parent is None else f"root/{slug}",
        "position": position,
        "commission_key": "electronics",
        "umbrella": "product",
        "status": "published",
        "show_in_customer": True,
        "show_in_vendor": True,
        **extra,
    }


@pytest.fixture
def tree(fake: FakeClient) -> FakeClient:
    fake.table("categories").rows = [
        _row(ROOT, "root", None, 10),
        _row(CHILD, "child", ROOT, 10),
        _row(OTHER, "other", None, 20),
    ]
    fake.table("products").rows = [{"id": "p1", "category_id": CHILD}]
    fake.table("event_categories").rows = [
        {
            "slug": "music",
            "parent_slug": None,
            "label_key": "events.categories.music",
            "name": "Music",
            "sort": 10,
            "status": "published",
            "show_in_customer": True,
            "show_in_vendor": True,
        }
    ]
    fake.table("service_categories").rows = [
        {
            "slug": "beauty",
            "parent_slug": None,
            "name": "Beauty",
            "path": "beauty",
            "sort": 10,
            "is_active": True,
            "status": "published",
            "show_in_customer": True,
            "show_in_vendor": True,
        }
    ]
    return fake


def _admin(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return _login(monkeypatch, ADMIN_ID, frozenset({"admin"}))


def _operator(
    monkeypatch: pytest.MonkeyPatch, fake: FakeClient, permissions: list[str]
) -> dict[str, str]:
    fake.table("admin_roles").rows = [{"key": "rbac_ops", "permissions": permissions}]
    return _login(monkeypatch, CUSTOMER_ID, frozenset({"rbac_ops"}))


ROUTES = [
    ("GET", f"{BASE}?umbrella=product"),
    ("POST", BASE),
    ("POST", f"{BASE}/image/sign"),
    ("POST", f"{BASE}/product/reorder"),
    ("PATCH", f"{BASE}/product/{ROOT}"),
    ("POST", f"{BASE}/product/{ROOT}/status"),
    ("POST", f"{BASE}/product/{ROOT}/move"),
    ("DELETE", f"{BASE}/product/{ROOT}"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_routes_refuse_anon_and_customer(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    assert http.request(method, path, json={}).status_code == 401
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    assert http.request(method, path, json={}, headers=headers).status_code == 403


def test_list_returns_tree_with_status_and_filters_umbrella(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    body = http.get(f"{BASE}?umbrella=product", headers=headers).json()
    assert [n["slug"] for n in body] == ["root", "child", "other"] or {n["slug"] for n in body} == {
        "root",
        "child",
        "other",
    }
    assert all(n["umbrella"] == "product" and n["status"] == "published" for n in body)
    wholesale = http.get(f"{BASE}?umbrella=wholesale", headers=headers).json()
    assert wholesale == []
    searched = http.get(f"{BASE}?umbrella=product&q=child", headers=headers).json()
    assert {n["slug"] for n in searched} == {"root", "child"}


def test_umbrella_permissions_are_scoped(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    products_op = _operator(monkeypatch, tree, ["products.manage"])
    assert http.get(f"{BASE}?umbrella=product", headers=products_op).status_code == 200
    assert http.get(f"{BASE}?umbrella=wholesale", headers=products_op).status_code == 200
    assert http.get(f"{BASE}?umbrella=event", headers=products_op).status_code == 403
    assert http.get(f"{BASE}?umbrella=service", headers=products_op).status_code == 403
    events_op = _operator(monkeypatch, tree, ["products.manage", "events.manage"])
    assert http.get(f"{BASE}?umbrella=event", headers=events_op).status_code == 200
    assert http.get(f"{BASE}?umbrella=service", headers=events_op).status_code == 403
    no_perm = _operator(monkeypatch, tree, ["vendors.manage"])
    assert http.get(f"{BASE}?umbrella=product", headers=no_perm).status_code == 403


def test_create_defaults_to_draft_inherits_commission_and_audits(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    response = http.post(
        BASE,
        headers=headers,
        json={"umbrella": "product", "name": "Smart Home", "parent_id": ROOT},
    )
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["slug"] == "smart-home"
    assert out["status"] == "draft"
    assert out["commission_key"] == "electronics"
    assert out["parent_id"] == ROOT
    assert [row["action"] for row in tree.table("audit_log").rows] == ["catalog.taxonomy.create"]


def test_create_validation(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    assert http.post(BASE, headers=headers, json={"umbrella": "product"}).status_code == 422
    bad_slug = {"umbrella": "product", "name": "Valid name", "slug": "Bad Slug"}
    assert http.post(BASE, headers=headers, json=bad_slug).status_code == 422
    no_alt = {"umbrella": "product", "name": "Valid", "image_public_id": "taxonomy/x"}
    assert http.post(BASE, headers=headers, json=no_alt).status_code == 422
    traversal = {
        "umbrella": "product",
        "name": "Valid",
        "image_public_id": "../x",
        "image_alt": "x",
    }
    assert http.post(BASE, headers=headers, json=traversal).status_code == 422
    extra = {"umbrella": "product", "name": "Valid", "evil": 1}
    assert http.post(BASE, headers=headers, json=extra).status_code == 422
    dup = {"umbrella": "product", "name": "Dup", "slug": "root"}
    assert http.post(BASE, headers=headers, json=dup).status_code == 409


def test_publish_and_block_never_touch_listings(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    products_before = [dict(r) for r in tree.table("products").rows]
    blocked = http.post(
        f"{BASE}/product/{CHILD}/status",
        headers=headers,
        json={"status": "blocked", "reason": "Policy review"},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["status"] == "blocked"
    assert tree.table("products").rows == products_before
    actions = [row["action"] for row in tree.table("audit_log").rows]
    assert actions == ["catalog.taxonomy.blocked"]
    published = http.post(
        f"{BASE}/product/{CHILD}/status", headers=headers, json={"status": "published"}
    )
    assert published.json()["status"] == "published"
    bad = http.post(f"{BASE}/product/{CHILD}/status", headers=headers, json={"status": "nope"})
    assert bad.status_code == 422


def test_delete_blocked_when_category_has_listings_or_children(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    with_listings = http.delete(f"{BASE}/product/{CHILD}", headers=headers)
    assert with_listings.status_code == 409
    assert with_listings.json()["error"]["code"] == "category_has_listings"
    with_children = http.delete(f"{BASE}/product/{ROOT}", headers=headers)
    assert with_children.status_code == 409
    assert with_children.json()["error"]["code"] == "category_has_children"
    ok = http.delete(f"{BASE}/product/{OTHER}", headers=headers)
    assert ok.status_code == 200, ok.text
    assert OTHER not in {r["id"] for r in tree.table("categories").rows}
    assert http.delete(f"{BASE}/product/{OTHER}", headers=headers).status_code == 404


def test_move_rejects_cycles_and_rewrites_paths(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    cycle = http.post(f"{BASE}/product/{ROOT}/move", headers=headers, json={"parent_id": CHILD})
    assert cycle.status_code == 409
    moved = http.post(f"{BASE}/product/{CHILD}/move", headers=headers, json={"parent_id": OTHER})
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_id"] == OTHER
    assert moved.json()["path"] == "other/child"


def test_reorder_requires_every_sibling_once(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    partial = http.post(
        f"{BASE}/product/reorder", headers=headers, json={"parent_id": None, "ordered_ids": [ROOT]}
    )
    assert partial.status_code == 422
    ok = http.post(
        f"{BASE}/product/reorder",
        headers=headers,
        json={"parent_id": None, "ordered_ids": [OTHER, ROOT]},
    )
    assert ok.status_code == 200, ok.text
    positions = {r["id"]: r["position"] for r in tree.table("categories").rows}
    assert positions[OTHER] < positions[ROOT]
    assert [row["action"] for row in tree.table("audit_log").rows] == ["catalog.taxonomy.reorder"]


def test_service_and_event_umbrellas_use_slug_ids(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    created = http.post(
        BASE, headers=headers, json={"umbrella": "service", "name": "Logistics & delivery"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["slug"] == "logistics-and-delivery"
    blocked = http.post(f"{BASE}/event/music/status", headers=headers, json={"status": "blocked"})
    assert blocked.status_code == 200
    assert tree.table("event_categories").rows[0]["status"] == "blocked"
    patched = http.patch(
        f"{BASE}/service/beauty",
        headers=headers,
        json={"show_in_vendor": False, "icon": "sparkles"},
    )
    assert patched.status_code == 200
    assert patched.json()["show_in_vendor"] is False


def test_image_sign_scopes_folder_and_caps_size(
    http: TestClient, tree: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.settings import Settings, get_settings

    headers = _admin(monkeypatch)
    http.app.dependency_overrides[get_settings] = lambda: _FakeSettings()  # type: ignore[assignment]
    try:
        too_big = http.post(
            f"{BASE}/image/sign",
            headers=headers,
            json={"umbrella": "product", "file_size_bytes": 99_000_000},
        )
        assert too_big.status_code == 400
        ok = http.post(f"{BASE}/image/sign", headers=headers, json={"umbrella": "event"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["folder"] == "taxonomy/event"
        assert "api_secret" not in ok.text
    finally:
        http.app.dependency_overrides.pop(get_settings, None)
    _ = Settings


class _FakeSettings:
    cloudinary_cloud_name = "demo"
    cloudinary_api_key = "key"
    cloudinary_api_secret = "secret"
