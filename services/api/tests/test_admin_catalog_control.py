"""Admin catalog control API: authz per kind, guarded transitions, reasons, audit."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from tests import test_home_feed as _base
from tests.test_home_feed import ADMIN_ID, CUSTOMER_ID, FakeClient, FakeQuery, FakeRpc, _login

fake = _base.fake
http = _base.http

LISTING = "aaaaaaaa-0000-4000-8000-000000000011"
SERVICE = "aaaaaaaa-0000-4000-8000-000000000012"
VENDOR = "bbbbbbbb-0000-4000-8000-000000000011"


def _is(self: FakeQuery, column: str, value: Any) -> FakeQuery:
    self.filters.append(("eq", column, None if value == "null" else value))
    return self


FakeQuery.is_ = _is  # type: ignore[attr-defined]

_original_execute = FakeRpc.execute


def _rpc_execute(self: FakeRpc) -> MagicMock:
    """Model the SQL functions' contract closely enough for the router."""
    client = self.client
    if self.name not in {"moderate_catalog_entity", "release_catalog_moderation"}:
        return _original_execute(self)
    self.client.rpc_calls.append((self.name, self.params))
    table = {"listing": "vendor_listings", "service": "services", "vendor": "vendors"}[
        self.params["p_kind"]
    ]
    row = next(r for r in client.table(table).rows if r["id"] == self.params["p_entity_id"])
    holds = client.table("catalog_moderation_holds").rows
    active = [h for h in holds if h["entity_id"] == row["id"] and h.get("released_at") is None]
    if self.name == "moderate_catalog_entity":
        if active:
            raise APIError({"code": "23505", "message": "Entity is already moderated"})
        target = {"listing": {"hide": "paused", "block": "removed"}, "service": {}, "vendor": {}}
        new_status = target.get(self.params["p_kind"], {}).get(self.params["p_action"]) or (
            "suspended" if self.params["p_kind"] == "vendor" else "paused"
        )
        holds.append(
            {
                "id": f"hold-{len(holds)}",
                "entity_kind": self.params["p_kind"],
                "entity_id": row["id"],
                "action": self.params["p_action"],
                "from_status": row["status"],
                "reason": self.params["p_reason"],
                "actor": self.params["p_actor"],
                "released_at": None,
            }
        )
        row["status"] = new_status
        return MagicMock(data=holds[-1])
    if not active:
        raise APIError({"code": "P0002", "message": "No active moderation hold"})
    active[0]["released_at"] = "now"
    row["status"] = active[0]["from_status"]
    return MagicMock(data=active[0])


FakeRpc.execute = _rpc_execute  # type: ignore[method-assign]


@pytest.fixture
def catalog(fake: FakeClient) -> FakeClient:
    fake.table("vendors").rows = [
        {
            "id": VENDOR,
            "status": "active",
            "display_name": "Shop",
            "slug": "shop",
            "description": None,
        }
    ]
    fake.table("vendor_listings").rows = [
        {
            "id": LISTING,
            "status": "active",
            "vendor_id": VENDOR,
            "title_override": "Phone",
            "description": "Old",
        }
    ]
    fake.table("services").rows = [
        {"id": SERVICE, "status": "active", "vendor_id": VENDOR, "title": "Plumbing", "slug": "pl"}
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
    ("GET", "/admin/catalog/listings"),
    ("POST", f"/admin/catalog/listings/{LISTING}/moderate"),
    ("POST", f"/admin/catalog/listings/{LISTING}/restore"),
    ("PATCH", f"/admin/catalog/listings/{LISTING}"),
    ("POST", f"/admin/catalog/services/{SERVICE}/moderate"),
    ("POST", f"/admin/catalog/events/{SERVICE}/moderate"),
    ("POST", f"/admin/catalog/vendors/{VENDOR}/moderate"),
    ("POST", f"/admin/catalog/vendors/{VENDOR}/restore"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_catalog_routes_refuse_anon_and_customer(
    http: TestClient, monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    assert http.request(method, path, json={}).status_code == 401
    headers = _login(monkeypatch, CUSTOMER_ID, frozenset({"customer"}))
    assert http.request(method, path, json={}, headers=headers).status_code == 403


def test_permissions_are_scoped_per_kind(
    http: TestClient, catalog: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"action": "hide", "reason": "Counterfeit report"}
    products_op = _operator(monkeypatch, catalog, ["products.manage"])
    assert (
        http.post(
            f"/admin/catalog/vendors/{VENDOR}/moderate",
            headers=products_op,
            json={"action": "block", "reason": "Fraud ring"},
        ).status_code
        == 403
    )
    services_reader = _operator(monkeypatch, catalog, ["services.read"])
    assert http.get("/admin/catalog/services", headers=services_reader).status_code == 200
    # services.read is read-only: moderation stays with admin/superadmin.
    assert (
        http.post(
            f"/admin/catalog/services/{SERVICE}/moderate", headers=services_reader, json=body
        ).status_code
        == 403
    )
    products_op = _operator(monkeypatch, catalog, ["products.manage"])
    ok = http.post(f"/admin/catalog/listings/{LISTING}/moderate", headers=products_op, json=body)
    assert ok.status_code == 200, ok.text


def test_hide_requires_reason_and_uses_guarded_function_with_audit(
    http: TestClient, catalog: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    path = f"/admin/catalog/listings/{LISTING}/moderate"
    assert http.post(path, headers=headers, json={"action": "hide"}).status_code == 422
    assert (
        http.post(path, headers=headers, json={"action": "hide", "reason": "  "}).status_code == 422
    )
    response = http.post(
        path, headers=headers, json={"action": "hide", "reason": "Counterfeit report"}
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "paused" and out["visible"] is False
    assert out["hold"]["reason"] == "Counterfeit report"
    calls = [c for c in catalog.rpc_calls if c[0] == "moderate_catalog_entity"]
    assert calls[0][1]["p_reason"] == "Counterfeit report"
    audit = catalog.table("audit_log").rows
    assert [row["action"] for row in audit] == ["catalog.listing.hide"]
    # No raw status write from the router: only the rpc moved it.
    assert all(
        "status" not in (row.get("after") or {}) or row["action"].startswith("catalog.")
        for row in audit
    )

    again = http.post(path, headers=headers, json={"action": "hide", "reason": "Second time"})
    assert again.status_code == 409

    restored = http.post(
        f"/admin/catalog/listings/{LISTING}/restore",
        headers=headers,
        json={"reason": "Seller proved authenticity"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active" and restored.json()["hold"] is None
    nothing = http.post(
        f"/admin/catalog/listings/{LISTING}/restore", headers=headers, json={"reason": "again"}
    )
    assert nothing.status_code == 404


def test_vendor_block_hides_its_listing_everywhere_visibility_reports(
    http: TestClient, catalog: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    assert (
        http.post(
            f"/admin/catalog/vendors/{VENDOR}/moderate",
            headers=headers,
            json={"action": "hide", "reason": "Vendors cannot be hidden"},
        ).status_code
        == 422
    )
    blocked = http.post(
        f"/admin/catalog/vendors/{VENDOR}/moderate",
        headers=headers,
        json={"action": "block", "reason": "Repeated fraud reports"},
    )
    assert blocked.status_code == 200 and blocked.json()["status"] == "suspended"
    listings = http.get("/admin/catalog/listings", headers=headers).json()
    assert listings[0]["status"] == "active" and listings[0]["visible"] is False


def test_display_edit_changes_text_only_with_audit(
    http: TestClient, catalog: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _admin(monkeypatch)
    path = f"/admin/catalog/listings/{LISTING}"
    assert http.patch(path, headers=headers, json={"reason": "typo fix"}).status_code == 422
    assert (
        http.patch(
            path, headers=headers, json={"status": "active", "reason": "smuggle"}
        ).status_code
        == 422
    )
    edited = http.patch(
        path, headers=headers, json={"title": "Phone 12 (refurbished)", "reason": "Misleading"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["label"] == "Phone 12 (refurbished)"
    audit = catalog.table("audit_log").rows[-1]
    assert audit["action"] == "catalog.listing.edit"
    assert audit["before"] == {"title_override": "Phone"}


def test_vendor_write_refused_by_moderation_hold_maps_to_409() -> None:
    from app.errors import unhandled_exception_handler
    from starlette.requests import Request

    request = Request({"type": "http", "method": "PATCH", "path": "/vendor/x", "headers": []})
    held = APIError(
        {"code": "42501", "message": "catalog_moderation_hold: listing x is held by an admin"}
    )
    response = unhandled_exception_handler(request, held)
    assert response.status_code == 409
    assert b"catalog.moderation_hold" in response.body
    other = unhandled_exception_handler(request, APIError({"code": "42501", "message": "nope"}))
    assert other.status_code == 500
