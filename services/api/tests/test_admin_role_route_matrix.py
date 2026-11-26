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
            "GET /admin/analytics/export",
            "GET /admin/analytics/revenue",
            "GET /admin/analytics/status",
            "GET /admin/disputes",
            "GET /admin/disputes/{dispute_id}",
            "GET /admin/disputes/{dispute_id}/notes",
            "GET /admin/orders/search",
            "GET /admin/orders/{order_id}",
        }
    ),
    # D2 (founder, 2026-11-13): money operations without full `admin`. Reads included.
    "finance.operate": frozenset(
        {
            "GET /admin/analytics/export",
            "GET /admin/analytics/revenue",
            "GET /admin/analytics/status",
            "GET /admin/disputes",
            "GET /admin/disputes/{dispute_id}",
            "GET /admin/disputes/{dispute_id}/notes",
            "GET /admin/orders/search",
            "GET /admin/orders/{order_id}",
            "POST /admin/disputes/{dispute_id}/decide",
            "POST /admin/disputes/{dispute_id}/notes",
            "POST /admin/orders/{order_id}/cod/confirm-collection",
            "POST /admin/orders/{order_id}/cod/refuse-collection",
            "POST /admin/orders/{order_id}/escrow",
            "POST /admin/orders/{order_id}/intervene",
            "POST /admin/refunds/execute",
        }
    ),
    "support.manage": frozenset(
        {
            "GET /admin/disputes",
            "GET /admin/disputes/{dispute_id}",
            "GET /admin/disputes/{dispute_id}/notes",
            "GET /admin/support/log",
            "GET /admin/support/lookup",
            "POST /admin/disputes/{dispute_id}/notes",
            "POST /admin/support/send",
        }
    ),
    "logistics.manage": frozenset(
        {
            "GET /admin/dispatch/board",
            "GET /admin/dispatch/couriers",
            "GET /admin/dispatch/requests/{dispatch_id}",
            "GET /admin/dispatch/requests/{dispatch_id}/message",
            "GET /admin/orders/{order_id}",
            "PATCH /admin/dispatch/couriers/{courier_id}",
            "POST /admin/dispatch/couriers",
            "POST /admin/dispatch/requests",
            "POST /admin/dispatch/requests/{dispatch_id}/handover",
            "POST /admin/dispatch/requests/{dispatch_id}/notify",
            "POST /admin/dispatch/requests/{dispatch_id}/transition",
            "POST /admin/orders/{order_id}/dispatch",
            # Logistics phase 1 + area-pair pricing (rain mode only; shadow/live stay admin).
            "GET /admin/logistics/cash/custody",
            "GET /admin/logistics/intercity-rates",
            "GET /admin/logistics/margin-report",
            "GET /admin/logistics/pricing-switches",
            "PATCH /admin/dispatch/requests/{dispatch_id}/cost",
            "PATCH /admin/logistics/rain-mode",
            "POST /admin/dispatch/requests/{dispatch_id}/complete",
            "POST /admin/dispatch/requests/{dispatch_id}/returned",
        }
    ),
    "audit.read": frozenset(
        {
            "GET /admin/audit-log",
        }
    ),
    # Matching rider cash to the ledger is a finance power (logistics phase 1).
    "cod.reconcile": frozenset(
        {
            "GET /admin/logistics/cash/cash-up",
            "POST /admin/logistics/cash/remittances",
        }
    ),
    "products.manage": frozenset(
        {
            # Admin catalog control (T4): listings.
            "GET /admin/catalog/listings",
            "PATCH /admin/catalog/listings/{entity_id}",
            "POST /admin/catalog/listings/{entity_id}/moderate",
            "POST /admin/catalog/listings/{entity_id}/restore",
            # Shared canonical photos (#798).
            "DELETE /admin/products/{product_id}/images/{image_id}",
            "GET /admin/products/{product_id}/images",
            "POST /admin/products/{product_id}/images",
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
            # Admin catalog control (T4): vendor suspension holds.
            "GET /admin/catalog/vendors",
            "PATCH /admin/catalog/vendors/{entity_id}",
            "POST /admin/catalog/vendors/{entity_id}/moderate",
            "POST /admin/catalog/vendors/{entity_id}/restore",
            # Multi-branch review (#807): mapped to vendors.manage in auth.py.
            "GET /admin/branches",
            "GET /admin/branches/flags",
            "GET /admin/branches/{branch_id}",
            "POST /admin/branches/businesses/{business_id}/pacra",
            "POST /admin/branches/flags/{flag_id}/resolve",
            "POST /admin/branches/{branch_id}/approve",
            "POST /admin/branches/{branch_id}/reject",
            "POST /admin/branches/{branch_id}/request-info",
            "POST /admin/extras/requests/{request_id}/transition",
            "GET /admin/business",
            # Paid extras requests (20261117020000): mapped to vendors.manage in auth.py.
            "GET /admin/extras/requests",
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
            "GET /admin/analytics/export",
            "GET /admin/analytics/growth",
            "GET /admin/analytics/insights",
            "GET /admin/analytics/overview",
            "GET /admin/analytics/performance",
            "GET /admin/analytics/products-funnel",
            "GET /admin/analytics/search-demand",
            "GET /admin/analytics/services-events",
            "GET /admin/analytics/status",
            "GET /admin/analytics/users",
            "GET /admin/analytics/vendors",
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
            # Admin catalog control (T4): services are read-only here.
            "GET /admin/catalog/services",
            "GET /admin/services",
        }
    ),
    "services.manage": frozenset(
        {
            "GET /admin/rfq/jobs",
            "GET /admin/service-providers",
            "GET /admin/services",
            "PATCH /admin/services/{service_id}/status",
            "POST /admin/rfq/jobs/{job_id}/close",
        }
    ),
    "events.manage": frozenset(
        {
            # Admin catalog control (T4): events.
            "GET /admin/catalog/events",
            "PATCH /admin/catalog/events/{entity_id}",
            "POST /admin/catalog/events/{entity_id}/moderate",
            "POST /admin/catalog/events/{entity_id}/restore",
            "GET /admin/events",
            "GET /admin/events/high-value-queue",
            "GET /admin/events/organisers",
            "POST /admin/events/{event_id}/cancel",
            "POST /admin/events/{event_id}/high-value-verify",
            "POST /admin/events/{event_id}/unpublish",
        }
    ),
    "ads.manage": frozenset(
        {
            # Typed ad target picker (T4).
            "GET /admin/ads/targets",
            "DELETE /admin/home-feed/sections/{section_id}",
            "DELETE /admin/merch/slots/{slot_id}",
            "GET /admin/ads/placements",
            "GET /admin/flash-deals",
            "GET /admin/home-feed/preview",
            "GET /admin/home-feed/sections",
            "GET /admin/merch/hero-variants",
            "GET /admin/merch/preview-url",
            "GET /admin/merch/slots",
            # W8 offers moderation (#817 maps it to ads.manage).
            "GET /admin/offers",
            "POST /admin/offers/{offer_id}/pause",
            "POST /admin/offers/{offer_id}/unpause",
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
        # Admin catalog control (T4): moderators hold products.manage and vendors.manage.
        "GET /admin/catalog/listings",
        "GET /admin/catalog/vendors",
        "PATCH /admin/catalog/listings/{entity_id}",
        "PATCH /admin/catalog/vendors/{entity_id}",
        "POST /admin/catalog/listings/{entity_id}/moderate",
        "POST /admin/catalog/listings/{entity_id}/restore",
        "POST /admin/catalog/vendors/{entity_id}/moderate",
        "POST /admin/catalog/vendors/{entity_id}/restore",
        "GET /admin/intake",
        "GET /admin/intake/{session_id}",
        "GET /admin/kyc",
        "GET /admin/kyc/orphaned-tiers",
        "GET /admin/kyc/{kyc_record_id}",
        "GET /admin/licences",
        "GET /admin/licences/expiring",
        # Paid extras requests: moderators hold vendors.manage.
        "GET /admin/extras/requests",
        "POST /admin/extras/requests/{request_id}/transition",
        "DELETE /admin/products/{product_id}/images/{image_id}",
        "GET /admin/products/{product_id}/images",
        "POST /admin/products/{product_id}/images",
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

# Role, permission and admin-account management: `superadmin` only — `admin` is denied.
SUPERADMIN_ONLY_ROUTES: frozenset[str] = frozenset(
    {
        "GET /admin/accounts",
        "GET /admin/accounts/lookup",
        "POST /admin/accounts/{user_id}/deactivate",
        "DELETE /admin/roles/{key}",
        "DELETE /admin/roles/{key}/users/{user_id}",
        "GET /admin/roles",
        "PATCH /admin/roles/{key}",
        "POST /admin/roles",
        "PUT /admin/roles/{key}/users/{user_id}",
    }
)

# Everything else is reachable only by the unrestricted `admin` / `superadmin` roles:
# platform config, commission rates, flags, listing reports, clips moderation,
# translations and kill-switch resets. Money operations moved to `finance.operate` (D2),
# support tools to `support.manage`, dispatch to `logistics.manage` (2026-11-13).
UNRESTRICTED_ONLY_ROUTES: frozenset[str] = frozenset(
    {
        # Admin catalog control (T4): service mutations have no rbac permission.
        "PATCH /admin/catalog/services/{entity_id}",
        "POST /admin/catalog/services/{entity_id}/moderate",
        "POST /admin/catalog/services/{entity_id}/restore",
        "DELETE /admin/clip-pilot/vendors/{vendor_id}",
        "DELETE /admin/translations/overrides",
        "GET /admin/clip-pilot",
        "GET /admin/clips",
        "GET /admin/clips/reports",
        "GET /admin/clips/{clip_id}",
        "GET /admin/config/categories",
        "GET /admin/config/commissions",
        "GET /admin/config/delivery-zones",
        "GET /admin/config/flags",
        "GET /admin/config/platform",
        # Vendor listing plans (#798, flag off): commercial config, unrestricted only.
        "DELETE /admin/vendor-plans/{plan_key}",
        "DELETE /admin/vendors/{vendor_id}/plan/override",
        "GET /admin/vendor-plans",
        "GET /admin/vendors/{vendor_id}/plan",
        "PATCH /admin/vendor-plans/{plan_key}",
        "POST /admin/vendor-plans",
        "PUT /admin/vendors/{vendor_id}/plan",
        "PUT /admin/vendors/{vendor_id}/plan/override",
        # Paid extras catalogue + pilot trials (20261117020000): commercial config,
        # unrestricted only.
        "GET /admin/extras",
        "GET /admin/trials",
        "PATCH /admin/extras/{extra_key}",
        "POST /admin/extras",
        "POST /admin/trials/{business_id}",
        # Coupons (#792, flag off): platform coupon management stays with the
        # unrestricted roles until a founder decision maps it to a permission.
        "GET /admin/coupons",
        "PATCH /admin/coupons/{coupon_id}",
        "POST /admin/coupons",
        # Pay at the door (#795, flag off): not delegated to rbac roles until a
        # founder decision maps them (logistics.manage / finance.operate).
        "GET /admin/dispatch/door-payment/exceptions",
        "GET /admin/dispatch/requests/{dispatch_id}/door-payment",
        "POST /admin/dispatch/door-payment/exceptions/{exception_id}/resolve",
        "POST /admin/dispatch/requests/{dispatch_id}/door-payment/arrived",
        "POST /admin/dispatch/requests/{dispatch_id}/door-payment/cash",
        "POST /admin/dispatch/requests/{dispatch_id}/door-payment/poll",
        "POST /admin/dispatch/requests/{dispatch_id}/door-payment/request",
        # Organiser advance debts (#796): unrestricted roles only, never delegated.
        "GET /admin/event-advance-debts",
        "GET /admin/flags",
        "GET /admin/health",
        "GET /admin/translations/overrides",
        "PATCH /admin/config/categories/{category_id}",
        "PATCH /admin/config/commissions/{category_key}",
        "PATCH /admin/config/delivery-zones/{zone_key}",
        "PATCH /admin/config/flags/{flag}",
        "PATCH /admin/config/platform/{key}",
        "POST /admin/ai-spend/reset-kill-switch",
        "POST /admin/clip-analytics/reset-kill-switch",
        "POST /admin/clip-pilot/vendors",
        "POST /admin/clips/reports/{report_id}/dismiss",
        "POST /admin/clips/reports/{report_id}/uphold",
        "POST /admin/clips/{clip_id}/approve",
        "POST /admin/clips/{clip_id}/reject",
        "POST /admin/clips/{clip_id}/takedown",
        "POST /admin/config/categories/reorder",
        "POST /admin/echo",
        "POST /admin/event-advance-debts/repayments",
        "POST /admin/flags/{flag_id}/dismiss",
        "POST /admin/flags/{flag_id}/escalate-suspend",
        "POST /admin/flags/{flag_id}/remove",
        "POST /admin/flags/{flag_id}/unpublish",
        "POST /admin/flags/{flag_id}/warn-vendor",
        "PUT /admin/translations/overrides",
        # Area-pair pricing: shadow/live switch, formula and distance table stay with
        # full admins (operators only flip rain mode).
        "GET /admin/logistics/area-distances",
        "GET /admin/logistics/area-pricing/settings",
        "GET /admin/logistics/areas",
        "PATCH /admin/logistics/area-distances/{from_area}/{to_area}",
        "PATCH /admin/logistics/area-pricing",
        "PUT /admin/logistics/area-pricing/settings",
    }
)

MONEY_MUTATIONS: frozenset[str] = frozenset(
    {
        "POST /admin/refunds/execute",
        "POST /admin/orders/{order_id}/escrow",
        "POST /admin/orders/{order_id}/intervene",
        "POST /admin/orders/{order_id}/cod/confirm-collection",
        "POST /admin/orders/{order_id}/cod/refuse-collection",
        "POST /admin/disputes/{dispute_id}/decide",
    }
)
# Platform money/config controls stay with the unrestricted roles only.
CONTROL_MUTATIONS: frozenset[str] = frozenset(
    {
        "PATCH /admin/config/commissions/{category_key}",
        "PATCH /admin/config/platform/{key}",
        "PATCH /admin/config/flags/{flag}",
    }
)

# Granted to superadmin (and to an rbac role holding the permission), never implied by
# the unrestricted `admin` role (founder decision 2026-11-13).
ADMIN_EXCLUDED_ROUTES: frozenset[str] = PERMISSION_ROUTES["audit.read"]

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
        return route not in SUPERADMIN_ONLY_ROUTES and route not in ADMIN_EXCLUDED_ROUTES
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


def test_only_finance_operate_reaches_money_mutations_and_nothing_reaches_controls() -> None:
    assert MONEY_MUTATIONS <= set(ADMIN_ROUTES)
    assert CONTROL_MUTATIONS <= UNRESTRICTED_ONLY_ROUTES
    for permission, routes in PERMISSION_ROUTES.items():
        reached = sorted(routes & MONEY_MUTATIONS)
        if permission == "finance.operate":
            assert set(reached) == MONEY_MUTATIONS
        else:
            assert not reached, f"{permission} reaches money mutations {reached}"
    assert not MODERATOR_ROUTES & MONEY_MUTATIONS
    # Read permissions never carry a write.
    for permission in (
        "finance.read",
        "analytics.read",
        "services.read",
        "inventory.read",
        "audit.read",
    ):
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
