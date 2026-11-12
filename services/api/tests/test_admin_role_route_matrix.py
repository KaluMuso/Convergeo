"""Role x route acceptance matrix for every `/admin` endpoint (live HTTP, no DB).

Built during the 2026-11 analytics/RBAC audit. Each identity sends a real request
through the real app and guards; 403 means denied, anything else means the request got
past authorization (handlers run against an inert fake, so the status is otherwise
irrelevant).

The expected tables below are deliberately written out, not derived from
`app.core.auth._ADMIN_ROUTE_PERMISSIONS`: widening a role in the route map, or adding
an admin route, must show up here as a reviewed diff. A new `/admin` route that is in
no table fails `test_every_admin_route_is_classified`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.auth import ADMIN_PERMISSIONS, CurrentUser, get_current_user
from app.deps import get_supabase_client
from app.main import create_app
from app.supabase_client import get_supabase_service_client
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ME = "GET /admin/me/permissions"

# Routes a restricted `rbac_*` role reaches with exactly one permission.
PERMISSION_ROUTES: dict[str, frozenset[str]] = {
    "finance.read": frozenset(
        {
            "GET /admin/disputes",
            "GET /admin/disputes/{dispute_id}",
            "GET /admin/orders/search",
            "GET /admin/orders/{order_id}",
        }
    ),
    "products.manage": frozenset(
        {
            "GET /admin/products/canonical",
            "GET /admin/products/duplicates",
            "GET /admin/products/search",
            "GET /admin/products/{product_id}/relations",
            "PATCH /admin/products/canonical/{product_id}/status",
            "POST /admin/products/merge",
            "POST /admin/qa/{kind}/{item_id}/moderate",
            "PUT /admin/products/{product_id}/relations",
        }
    ),
    "vendors.manage": frozenset(
        {
            "GET /admin/business",
            "GET /admin/intake",
            "GET /admin/intake/{session_id}",
            "GET /admin/kyc",
            "GET /admin/kyc/orphaned-tiers",
            "GET /admin/kyc/{kyc_record_id}",
            "GET /admin/licences",
            "GET /admin/licences/expiring",
            "GET /admin/vendors",
            "GET /admin/vendors/{vendor_id}/kyc",
            "PATCH /admin/vendors/{vendor_id}/status",
            "POST /admin/business/{buyer_id}/reject",
            "POST /admin/business/{buyer_id}/verify",
            "POST /admin/intake/{session_id}/approve",
            "POST /admin/intake/{session_id}/attach-canonical",
            "POST /admin/intake/{session_id}/reject",
            "POST /admin/intake/{session_id}/request-changes",
            "POST /admin/kyc/{kyc_record_id}/approve",
            "POST /admin/kyc/{kyc_record_id}/reject",
            "POST /admin/kyc/{kyc_record_id}/request-resubmit",
            "POST /admin/kyc/{kyc_record_id}/revoke",
            "POST /admin/kyc/{kyc_record_id}/start-review",
            "POST /admin/kyc/{kyc_record_id}/suspend",
            "POST /admin/licences/{licence_id}/reject",
            "POST /admin/licences/{licence_id}/revoke",
            "POST /admin/licences/{licence_id}/verify",
        }
    ),
    "analytics.read": frozenset(
        {
            "GET /admin/clip-analytics",
            "GET /admin/dashboard",
            "GET /admin/governance/vendors",
            "GET /admin/search-insights/ask-cost",
            "GET /admin/search-insights/top-terms",
            "GET /admin/search-insights/zero-results",
        }
    ),
    "services.read": frozenset(
        {
            "GET /admin/services",
        }
    ),
    "events.manage": frozenset(
        {
            "GET /admin/events/high-value-queue",
            "POST /admin/events/{event_id}/high-value-verify",
        }
    ),
    "ads.manage": frozenset(
        {
            "DELETE /admin/home-feed/sections/{section_id}",
            "DELETE /admin/merch/slots/{slot_id}",
            "GET /admin/ads/placements",
            "GET /admin/flash-deals",
            "GET /admin/home-feed/preview",
            "GET /admin/home-feed/sections",
            "GET /admin/merch/hero-variants",
            "GET /admin/merch/preview-url",
            "GET /admin/merch/slots",
            "PATCH /admin/ads/placements/{placement_id}",
            "PATCH /admin/flash-deals/{deal_id}",
            "PATCH /admin/home-feed/sections/{section_id}",
            "PATCH /admin/merch/slots/{slot_id}",
            "POST /admin/ads/placements",
            "POST /admin/ads/placements/{placement_id}/transition",
            "POST /admin/flash-deals",
            "POST /admin/home-feed/sections",
            "POST /admin/home-feed/sections/reorder",
            "POST /admin/merch/slots",
            "POST /admin/merch/slots/{slot_id}/draft",
            "POST /admin/merch/slots/{slot_id}/publish",
        }
    ),
    "inventory.read": frozenset(
        {
            "GET /admin/inventory",
        }
    ),
}

# The fixed `moderator` role: product and vendor review queues, no decisions on KYC.
MODERATOR_ROUTES: frozenset[str] = frozenset(
    {
        "GET /admin/intake",
        "GET /admin/intake/{session_id}",
        "GET /admin/kyc",
        "GET /admin/kyc/orphaned-tiers",
        "GET /admin/kyc/{kyc_record_id}",
        "GET /admin/licences",
        "GET /admin/licences/expiring",
        "GET /admin/products/canonical",
        "GET /admin/products/duplicates",
        "GET /admin/vendors",
        "GET /admin/vendors/{vendor_id}/kyc",
        "PATCH /admin/products/canonical/{product_id}/status",
        "PATCH /admin/vendors/{vendor_id}/status",
        "POST /admin/intake/{session_id}/approve",
        "POST /admin/intake/{session_id}/attach-canonical",
        "POST /admin/intake/{session_id}/reject",
        "POST /admin/intake/{session_id}/request-changes",
        "POST /admin/qa/{kind}/{item_id}/moderate",
        "PUT /admin/products/{product_id}/relations",
    }
)

# Role and permission management: `superadmin` only — `admin` is denied.
SUPERADMIN_ONLY_ROUTES: frozenset[str] = frozenset(
    {
        "DELETE /admin/roles/{key}",
        "DELETE /admin/roles/{key}/users/{user_id}",
        "GET /admin/roles",
        "PATCH /admin/roles/{key}",
        "POST /admin/roles",
        "PUT /admin/roles/{key}/users/{user_id}",
    }
)

# Everything else is reachable only by the unrestricted `admin` / `superadmin` roles.
# Money mutations (refunds, escrow, disputes, COD), platform config, flags, support,
# clips moderation, dispatch and translations all live here: no permission grants them.
UNRESTRICTED_ONLY_ROUTES: frozenset[str] = frozenset(
    {
        "DELETE /admin/translations/overrides",
        "GET /admin/clips",
        "GET /admin/clips/reports",
        "GET /admin/clips/{clip_id}",
        "GET /admin/config/categories",
        "GET /admin/config/commissions",
        "GET /admin/config/delivery-zones",
        "GET /admin/config/flags",
        "GET /admin/config/platform",
        "GET /admin/dispatch/board",
        "GET /admin/dispatch/couriers",
        "GET /admin/dispatch/requests/{dispatch_id}",
        "GET /admin/dispatch/requests/{dispatch_id}/message",
        "GET /admin/flags",
        "GET /admin/health",
        "GET /admin/support/log",
        "GET /admin/support/lookup",
        "GET /admin/translations/overrides",
        "PATCH /admin/config/categories/{category_id}",
        "PATCH /admin/config/commissions/{category_key}",
        "PATCH /admin/config/delivery-zones/{zone_key}",
        "PATCH /admin/config/flags/{flag}",
        "PATCH /admin/config/platform/{key}",
        "PATCH /admin/dispatch/couriers/{courier_id}",
        "POST /admin/ai-spend/reset-kill-switch",
        "POST /admin/clip-analytics/reset-kill-switch",
        "POST /admin/clips/reports/{report_id}/dismiss",
        "POST /admin/clips/reports/{report_id}/uphold",
        "POST /admin/clips/{clip_id}/approve",
        "POST /admin/clips/{clip_id}/reject",
        "POST /admin/clips/{clip_id}/takedown",
        "POST /admin/config/categories/reorder",
        "POST /admin/dispatch/couriers",
        "POST /admin/dispatch/requests",
        "POST /admin/dispatch/requests/{dispatch_id}/handover",
        "POST /admin/dispatch/requests/{dispatch_id}/notify",
        "POST /admin/dispatch/requests/{dispatch_id}/transition",
        "POST /admin/disputes/{dispute_id}/decide",
        "POST /admin/echo",
        "POST /admin/flags/{flag_id}/dismiss",
        "POST /admin/flags/{flag_id}/escalate-suspend",
        "POST /admin/flags/{flag_id}/remove",
        "POST /admin/flags/{flag_id}/unpublish",
        "POST /admin/flags/{flag_id}/warn-vendor",
        "POST /admin/orders/{order_id}/cod/confirm-collection",
        "POST /admin/orders/{order_id}/cod/refuse-collection",
        "POST /admin/orders/{order_id}/dispatch",
        "POST /admin/orders/{order_id}/escrow",
        "POST /admin/orders/{order_id}/intervene",
        "POST /admin/refunds/execute",
        "POST /admin/support/send",
        "PUT /admin/translations/overrides",
    }
)

MONEY_MUTATIONS: frozenset[str] = frozenset(
    {
        "POST /admin/refunds/execute",
        "POST /admin/orders/{order_id}/escrow",
        "POST /admin/orders/{order_id}/intervene",
        "POST /admin/orders/{order_id}/dispatch",
        "POST /admin/orders/{order_id}/cod/confirm-collection",
        "POST /admin/orders/{order_id}/cod/refuse-collection",
        "POST /admin/disputes/{dispute_id}/decide",
        "PATCH /admin/config/commissions/{category_key}",
        "PATCH /admin/config/platform/{key}",
        "PATCH /admin/config/flags/{flag}",
    }
)

# identity -> (roles held, permissions on its rbac role)
IDENTITIES: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    "customer": (frozenset({"customer"}), ()),
    "vendor": (frozenset({"vendor"}), ()),
    "moderator": (frozenset({"moderator"}), ()),
    "admin": (frozenset({"admin"}), ()),
    "superadmin": (frozenset({"superadmin"}), ()),
    **{
        f"rbac[{permission}]": (frozenset({"rbac_scoped"}), (permission,))
        for permission in sorted(ADMIN_PERMISSIONS)
    },
}


def _iter_routes(routes: Any, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in routes or []:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        original = getattr(route, "original_router", None)
        if original is not None:
            nested = getattr(getattr(route, "include_context", None), "prefix", "") or ""
            yield from _iter_routes(original.routes, prefix + nested)


def _admin_routes() -> list[str]:
    found: set[str] = set()
    for path, route in _iter_routes(create_app().routes):
        if path.startswith("/admin"):
            for method in (route.methods or set()) - {"HEAD", "OPTIONS"}:
                found.add(f"{method} {path}")
    return sorted(found)


ADMIN_ROUTES = _admin_routes()


def expected_allowed(identity: str, route: str) -> bool:
    roles, permissions = IDENTITIES[identity]
    if roles & {"customer", "vendor"}:
        return False
    if "superadmin" in roles:
        return True
    if "admin" in roles:
        return route not in SUPERADMIN_ONLY_ROUTES
    if route == ME:
        return True
    if "moderator" in roles:
        return route in MODERATOR_ROUTES
    return any(route in PERMISSION_ROUTES[p] for p in permissions)


def _inert_service(permissions: tuple[str, ...]) -> MagicMock:
    """Answers the permission lookup truthfully; every other read/write is empty."""
    service = MagicMock()

    def table(name: str) -> MagicMock:
        query = MagicMock()
        for method in (
            "select", "in_", "eq", "neq", "order", "limit", "or_", "is_", "ilike", "range",
            "gte", "lte", "gt", "lt", "maybe_single", "single", "insert", "update", "delete",
            "upsert", "contains", "filter", "match", "like",
        ):  # fmt: skip
            getattr(query, method).return_value = query
        rows = [{"permissions": list(permissions)}] if name == "admin_roles" else []
        query.execute.return_value = SimpleNamespace(data=rows, count=0)
        return query

    service.client.table.side_effect = table
    service.client.rpc.return_value.execute.return_value = SimpleNamespace(data=[])
    return service


def _observe(identity: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    roles, permissions = IDENTITIES[identity]
    service = _inert_service(permissions)
    app = create_app()
    user = CurrentUser(id="00000000-0000-0000-0000-0000000000a1", roles=roles, token="t")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_supabase_client] = lambda: service
    app.dependency_overrides[get_supabase_service_client] = lambda: service
    monkeypatch.setattr("app.core.auth.get_supabase_service_client", lambda: service)
    statuses: dict[str, int] = {}
    with TestClient(app, raise_server_exceptions=False) as client:
        for route in ADMIN_ROUTES:
            method, path = route.split(" ", 1)
            concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000003", path)
            body: dict[str, object] | None = {} if method in {"POST", "PATCH", "PUT"} else None
            statuses[route] = client.request(method, concrete, json=body).status_code
    return statuses


def test_every_admin_route_is_classified() -> None:
    classified = (
        set().union(*PERMISSION_ROUTES.values())
        | MODERATOR_ROUTES
        | SUPERADMIN_ONLY_ROUTES
        | UNRESTRICTED_ONLY_ROUTES
        | {ME}
    )
    unclassified = sorted(set(ADMIN_ROUTES) - classified)
    assert not unclassified, (
        "New /admin route(s) with no reviewed role decision — add each to exactly one "
        f"table in this file: {unclassified}"
    )
    stale = sorted(classified - set(ADMIN_ROUTES))
    assert not stale, f"Expectation tables name routes that no longer exist: {stale}"


def test_tables_do_not_overlap_with_unrestricted_or_superadmin_only() -> None:
    granted = set().union(*PERMISSION_ROUTES.values()) | MODERATOR_ROUTES
    assert not granted & UNRESTRICTED_ONLY_ROUTES
    assert not granted & SUPERADMIN_ONLY_ROUTES
    assert set(PERMISSION_ROUTES) == set(ADMIN_PERMISSIONS)


def test_no_permission_or_moderator_grant_reaches_money_or_control_mutations() -> None:
    assert MONEY_MUTATIONS <= UNRESTRICTED_ONLY_ROUTES
    assert MONEY_MUTATIONS <= set(ADMIN_ROUTES)
    # Read permissions never carry a write.
    for permission in ("finance.read", "analytics.read", "services.read", "inventory.read"):
        writes = sorted(r for r in PERMISSION_ROUTES[permission] if not r.startswith("GET "))
        assert not writes, f"{permission} must stay read-only, grants {writes}"


@pytest.mark.parametrize("identity", sorted(IDENTITIES))
def test_identity_reaches_exactly_its_routes(
    identity: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    statuses = _observe(identity, monkeypatch)
    wrongly_allowed = sorted(
        route
        for route, status in statuses.items()
        if status != 403 and not expected_allowed(identity, route)
    )
    wrongly_denied = sorted(
        route
        for route, status in statuses.items()
        if status == 403 and expected_allowed(identity, route)
    )
    assert not wrongly_allowed, f"{identity} passed authorization on: {wrongly_allowed}"
    assert not wrongly_denied, f"{identity} was refused on routes it should reach: {wrongly_denied}"
    assert not [r for r, s in statuses.items() if s == 401], "identity was not authenticated"


def test_anonymous_is_rejected_on_every_admin_route() -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        for route in ADMIN_ROUTES:
            method, path = route.split(" ", 1)
            concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000003", path)
            body: dict[str, object] | None = {} if method in {"POST", "PATCH", "PUT"} else None
            assert client.request(method, concrete, json=body).status_code == 401, route
