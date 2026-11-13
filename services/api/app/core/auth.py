from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

from app.errors import AppError
from app.settings import Settings, get_settings
from app.supabase_client import SupabaseServiceClient, get_supabase_service_client

_CURRENT_USER_STATE_KEY = "current_user"
_JWT_CLAIMS_STATE_KEY = "jwt_claims"


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: str
    roles: frozenset[str]
    token: str


@lru_cache
def _jwks_client(supabase_url: str) -> PyJWKClient:
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url, cache_keys=True)


def verify_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    jwks_client = _jwks_client(settings.supabase_url)
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience="authenticated",
        issuer=issuer,
        options={"require": ["sub", "exp"]},
    )


def get_request_jwt_claims(request: Request) -> dict[str, Any]:
    claims = getattr(request.state, _JWT_CLAIMS_STATE_KEY, None)
    if isinstance(claims, dict):
        return claims
    raise AppError(
        code="internal_error",
        message="JWT claims are unavailable for this request",
        http_status=500,
    )


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(
            code="unauthorized",
            message="Missing or invalid Authorization header",
            http_status=401,
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError(
            code="unauthorized",
            message="Missing or invalid Authorization header",
            http_status=401,
        )
    return token


def _load_user_roles(user_id: str, service_client: SupabaseServiceClient) -> frozenset[str]:
    response = (
        service_client.client.table("user_roles").select("role").eq("user_id", user_id).execute()
    )
    data = response.data
    if not isinstance(data, list):
        return frozenset()

    roles: set[str] = set()
    for row in data:
        if isinstance(row, dict):
            role = row.get("role")
            if isinstance(role, str) and role:
                roles.add(role)
    return frozenset(roles)


async def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    cached_user = getattr(request.state, _CURRENT_USER_STATE_KEY, None)
    if isinstance(cached_user, CurrentUser):
        return cached_user

    token = _extract_bearer_token(request)

    try:
        claims = verify_supabase_jwt(token, settings)
    except InvalidTokenError as exc:
        raise AppError(
            code="unauthorized",
            message="Invalid or expired access token",
            http_status=401,
            details={"reason": exc.__class__.__name__},
        ) from exc
    except Exception as exc:
        raise AppError(
            code="unauthorized",
            message="Invalid or expired access token",
            http_status=401,
            details={"reason": exc.__class__.__name__},
        ) from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AppError(
            code="unauthorized",
            message="Invalid or expired access token",
            http_status=401,
        )

    user_id = subject.strip()
    service_client = get_supabase_service_client()
    roles = _load_user_roles(user_id, service_client)
    current_user = CurrentUser(id=user_id, roles=roles, token=token)

    setattr(request.state, _CURRENT_USER_STATE_KEY, current_user)
    setattr(request.state, _JWT_CLAIMS_STATE_KEY, claims)
    return current_user


MODERATOR_ROLES = frozenset({"superadmin", "moderator", "admin"})
ADMIN_PERMISSIONS = frozenset(
    {
        "finance.read",
        "finance.operate",
        "events.manage",
        "products.manage",
        "services.read",
        "services.manage",
        "vendors.manage",
        "ads.manage",
        "analytics.read",
        "inventory.read",
        "support.manage",
        "logistics.manage",
        "audit.read",
    }
)

# Permissions the legacy unrestricted `admin` role does NOT receive implicitly. Reading
# the audit trail is a superadmin oversight duty (founder decision 2026-11-13); a
# superadmin may still grant it to anyone through an `rbac_*` role.
ADMIN_ROLE_EXCLUDED_PERMISSIONS = frozenset({"audit.read"})

# Dashboard tiles that expose money held, liabilities and reconciliation detail (D3).
DASHBOARD_FINANCE_PERMISSIONS = frozenset({"finance.read", "finance.operate"})


_ADMIN_ROUTE_PERMISSION_SPEC: dict[tuple[str, str], str | tuple[str, ...]] = {
    ("GET", "/admin/orders/search"): ("finance.read", "finance.operate"),
    ("GET", "/admin/orders/{order_id}"): ("finance.read", "finance.operate", "logistics.manage"),
    ("GET", "/admin/disputes"): ("finance.read", "finance.operate", "support.manage"),
    ("GET", "/admin/disputes/{dispute_id}"): ("finance.read", "finance.operate", "support.manage"),
    ("GET", "/admin/events/high-value-queue"): "events.manage",
    ("POST", "/admin/events/{event_id}/high-value-verify"): "events.manage",
    ("GET", "/admin/products/duplicates"): "products.manage",
    ("GET", "/admin/products/search"): "products.manage",
    ("GET", "/admin/products/canonical"): "products.manage",
    ("GET", "/admin/products/{product_id}/relations"): "products.manage",
    ("POST", "/admin/products/merge"): "products.manage",
    ("PUT", "/admin/products/{product_id}/relations"): "products.manage",
    ("PATCH", "/admin/products/canonical/{product_id}/status"): "products.manage",
    ("GET", "/admin/services"): ("services.read", "services.manage"),
    ("GET", "/admin/inventory"): "inventory.read",
    ("GET", "/admin/vendors"): "vendors.manage",
    ("GET", "/admin/vendors/{vendor_id}/kyc"): "vendors.manage",
    ("PATCH", "/admin/vendors/{vendor_id}/status"): "vendors.manage",
    ("GET", "/admin/business"): "vendors.manage",
    ("POST", "/admin/business/{buyer_id}/verify"): "vendors.manage",
    ("POST", "/admin/business/{buyer_id}/reject"): "vendors.manage",
    ("GET", "/admin/kyc"): "vendors.manage",
    ("GET", "/admin/kyc/{kyc_record_id}"): "vendors.manage",
    ("GET", "/admin/kyc/orphaned-tiers"): "vendors.manage",
    ("POST", "/admin/kyc/{kyc_record_id}/start-review"): "vendors.manage",
    ("POST", "/admin/kyc/{kyc_record_id}/approve"): "vendors.manage",
    ("POST", "/admin/kyc/{kyc_record_id}/reject"): "vendors.manage",
    ("POST", "/admin/kyc/{kyc_record_id}/request-resubmit"): "vendors.manage",
    ("POST", "/admin/kyc/{kyc_record_id}/suspend"): "vendors.manage",
    ("POST", "/admin/kyc/{kyc_record_id}/revoke"): "vendors.manage",
    ("GET", "/admin/licences"): "vendors.manage",
    ("GET", "/admin/licences/expiring"): "vendors.manage",
    ("POST", "/admin/licences/{licence_id}/verify"): "vendors.manage",
    ("POST", "/admin/licences/{licence_id}/reject"): "vendors.manage",
    ("POST", "/admin/licences/{licence_id}/revoke"): "vendors.manage",
    ("GET", "/admin/intake"): "vendors.manage",
    ("GET", "/admin/intake/{session_id}"): "vendors.manage",
    ("POST", "/admin/intake/{session_id}/request-changes"): "vendors.manage",
    ("POST", "/admin/intake/{session_id}/reject"): "vendors.manage",
    ("POST", "/admin/intake/{session_id}/attach-canonical"): "vendors.manage",
    ("POST", "/admin/intake/{session_id}/approve"): "vendors.manage",
    ("GET", "/admin/merch/hero-variants"): "ads.manage",
    ("GET", "/admin/merch/slots"): "ads.manage",
    ("GET", "/admin/merch/preview-url"): "ads.manage",
    ("POST", "/admin/merch/slots"): "ads.manage",
    ("PATCH", "/admin/merch/slots/{slot_id}"): "ads.manage",
    ("DELETE", "/admin/merch/slots/{slot_id}"): "ads.manage",
    ("POST", "/admin/merch/slots/{slot_id}/draft"): "ads.manage",
    ("POST", "/admin/merch/slots/{slot_id}/publish"): "ads.manage",
    ("GET", "/admin/home-feed/sections"): "ads.manage",
    ("POST", "/admin/home-feed/sections"): "ads.manage",
    ("PATCH", "/admin/home-feed/sections/{section_id}"): "ads.manage",
    ("DELETE", "/admin/home-feed/sections/{section_id}"): "ads.manage",
    ("POST", "/admin/home-feed/sections/reorder"): "ads.manage",
    ("GET", "/admin/home-feed/preview"): "ads.manage",
    ("GET", "/admin/ads/placements"): "ads.manage",
    ("POST", "/admin/ads/placements"): "ads.manage",
    ("PATCH", "/admin/ads/placements/{placement_id}"): "ads.manage",
    ("POST", "/admin/ads/placements/{placement_id}/transition"): "ads.manage",
    ("GET", "/admin/dashboard"): "analytics.read",
    ("GET", "/admin/search-insights/top-terms"): "analytics.read",
    ("GET", "/admin/search-insights/zero-results"): "analytics.read",
    ("GET", "/admin/search-insights/ask-cost"): "analytics.read",
    ("GET", "/admin/clip-analytics"): "analytics.read",
    ("GET", "/admin/governance/vendors"): "analytics.read",
    # Analytics dashboards (founder decision D3): operational and marketplace figures need
    # analytics.read; money figures need finance.read/finance.operate. The v2 overview
    # strips its commercial block, and the vendors report its sales value, without them.
    ("GET", "/admin/analytics/status"): ("analytics.read", "finance.read", "finance.operate"),
    ("GET", "/admin/analytics/overview"): "analytics.read",
    ("GET", "/admin/analytics/search-demand"): "analytics.read",
    ("GET", "/admin/analytics/products-funnel"): "analytics.read",
    ("GET", "/admin/analytics/insights"): "analytics.read",
    ("GET", "/admin/analytics/users"): "analytics.read",
    ("GET", "/admin/analytics/growth"): "analytics.read",
    ("GET", "/admin/analytics/vendors"): "analytics.read",
    ("GET", "/admin/analytics/services-events"): "analytics.read",
    ("GET", "/admin/analytics/performance"): "analytics.read",
    ("GET", "/admin/analytics/revenue"): ("finance.read", "finance.operate"),
    # Export re-checks the chosen report's permission and audits every attempt.
    ("GET", "/admin/analytics/export"): ("analytics.read", "finance.read", "finance.operate"),
    ("GET", "/admin/flash-deals"): "ads.manage",
    ("POST", "/admin/flash-deals"): "ads.manage",
    ("PATCH", "/admin/flash-deals/{deal_id}"): "ads.manage",
    ("POST", "/admin/qa/{kind}/{item_id}/moderate"): "products.manage",
    # D2: money operations. Superadmin and admin keep them; no second approver yet.
    ("POST", "/admin/refunds/execute"): "finance.operate",
    ("POST", "/admin/orders/{order_id}/escrow"): "finance.operate",
    ("POST", "/admin/orders/{order_id}/intervene"): "finance.operate",
    ("POST", "/admin/orders/{order_id}/cod/confirm-collection"): "finance.operate",
    ("POST", "/admin/orders/{order_id}/cod/refuse-collection"): "finance.operate",
    ("POST", "/admin/disputes/{dispute_id}/decide"): "finance.operate",
    ("GET", "/admin/disputes/{dispute_id}/notes"): (
        "finance.read",
        "finance.operate",
        "support.manage",
    ),
    ("POST", "/admin/disputes/{dispute_id}/notes"): ("finance.operate", "support.manage"),
    # Customer support: masked lookup, contact log, outbound message.
    ("GET", "/admin/support/lookup"): "support.manage",
    ("GET", "/admin/support/log"): "support.manage",
    ("POST", "/admin/support/send"): "support.manage",
    # Logistics: courier dispatch board and manual dispatch (routes on this branch only).
    ("POST", "/admin/orders/{order_id}/dispatch"): "logistics.manage",
    ("GET", "/admin/dispatch/board"): "logistics.manage",
    ("GET", "/admin/dispatch/couriers"): "logistics.manage",
    ("POST", "/admin/dispatch/couriers"): "logistics.manage",
    ("PATCH", "/admin/dispatch/couriers/{courier_id}"): "logistics.manage",
    ("POST", "/admin/dispatch/requests"): "logistics.manage",
    ("GET", "/admin/dispatch/requests/{dispatch_id}"): "logistics.manage",
    ("GET", "/admin/dispatch/requests/{dispatch_id}/message"): "logistics.manage",
    ("POST", "/admin/dispatch/requests/{dispatch_id}/handover"): "logistics.manage",
    ("POST", "/admin/dispatch/requests/{dispatch_id}/notify"): "logistics.manage",
    ("POST", "/admin/dispatch/requests/{dispatch_id}/transition"): "logistics.manage",
    # Services: listings, RFQ moderation, providers.
    ("PATCH", "/admin/services/{service_id}/status"): "services.manage",
    ("GET", "/admin/service-providers"): "services.manage",
    ("GET", "/admin/rfq/jobs"): "services.manage",
    ("POST", "/admin/rfq/jobs/{job_id}/close"): "services.manage",
    # Events: listings, organisers, unpublish and cancellation.
    ("GET", "/admin/events"): "events.manage",
    ("GET", "/admin/events/organisers"): "events.manage",
    ("POST", "/admin/events/{event_id}/unpublish"): "events.manage",
    ("POST", "/admin/events/{event_id}/cancel"): "events.manage",
    # Audit trail: superadmin, or a role holding audit.read (never implied by `admin`).
    ("GET", "/admin/audit-log"): "audit.read",
}


def _normalise_route_spec(
    spec: dict[tuple[str, str], str | tuple[str, ...]],
) -> dict[tuple[str, str], frozenset[str]]:
    out: dict[tuple[str, str], frozenset[str]] = {}
    for key, value in spec.items():
        permissions = frozenset((value,) if isinstance(value, str) else value)
        unknown = permissions - ADMIN_PERMISSIONS
        if not permissions or unknown:
            raise RuntimeError(f"Route {key} maps to unknown permission(s): {sorted(unknown)}")
        out[key] = permissions
    return out


_ADMIN_ROUTE_PERMISSIONS: dict[tuple[str, str], frozenset[str]] = _normalise_route_spec(
    _ADMIN_ROUTE_PERMISSION_SPEC
)


def admin_permissions_for_request(path_template: str, method: str) -> frozenset[str]:
    """Explicit route inventory: any one listed permission admits. Unknown routes deny."""
    return _ADMIN_ROUTE_PERMISSIONS.get((method, path_template), frozenset())


def _admin_route_template(request: Request) -> str:
    if not request.url.path.startswith("/admin/"):
        return ""
    route = request.scope.get("route")
    template = str(getattr(route, "path", ""))
    # FastAPI's nested _IncludedRouter sets the matched route path relative to
    # its /admin parent. Standalone admin routers already include the prefix.
    return template if template.startswith("/admin/") else "/admin" + template


_ADMIN_LIKE_ROLES = frozenset({"superadmin", "admin", "moderator"})
_denial_logger = logging.getLogger("app.admin.denied")


def holds_admin_like_role(user: CurrentUser) -> bool:
    return bool(user.roles & _ADMIN_LIKE_ROLES) or any(
        role.startswith("rbac_") for role in user.roles
    )


def record_denied_admin_attempt(request: Request, user: CurrentUser) -> None:
    """Append an `outcome = denied` audit row for an operator refused on an admin route.

    Only operators (fixed admin roles or an `rbac_*` role) are recorded: customers and
    vendors probing /admin are noise, already answered 403. Best effort — the refusal
    stands whether or not the row is written.
    """
    if not holds_admin_like_role(user):
        return
    route = _admin_route_template(request) or request.url.path
    request_id = getattr(request.state, "request_id", None)
    try:
        get_supabase_service_client().client.table("audit_log").insert(
            {
                "actor": user.id,
                "action": "admin.access.denied",
                "entity_type": "admin_route",
                "entity_id": None,
                "before": None,
                "after": {"method": request.method, "route": route},
                "actor_roles": sorted(user.roles),
                "outcome": "denied",
                "request_id": request_id if isinstance(request_id, str) else None,
            }
        ).execute()
    except Exception:  # noqa: BLE001 - audit of a refusal must never turn into a 500
        _denial_logger.warning("admin denial audit write failed", exc_info=True)


def load_admin_permissions(
    user: CurrentUser, service_client: SupabaseServiceClient
) -> frozenset[str]:
    """Read current grants from the same user_roles snapshot used for identity."""
    if "superadmin" in user.roles:
        return ADMIN_PERMISSIONS
    if "admin" in user.roles:
        return ADMIN_PERMISSIONS - ADMIN_ROLE_EXCLUDED_PERMISSIONS
    base_permissions = (
        frozenset({"products.manage", "vendors.manage"})
        if "moderator" in user.roles
        else frozenset()
    )
    keys = sorted(role for role in user.roles if role.startswith("rbac_"))
    if not keys:
        return base_permissions
    response = (
        service_client.client.table("admin_roles").select("permissions").in_("key", keys).execute()
    )
    if not isinstance(response.data, list):
        return base_permissions
    return base_permissions | frozenset(
        permission
        for row in response.data
        if isinstance(row, dict)
        for permission in row.get("permissions", [])
        if isinstance(permission, str) and permission in ADMIN_PERMISSIONS
    )


async def require_admin_scope(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Gate every route mounted on the shared admin router, including new ones."""
    if user.roles.intersection({"superadmin", "admin"}):
        return user
    permissions = admin_permissions_for_request(_admin_route_template(request), request.method)
    if permissions & load_admin_permissions(user, get_supabase_service_client()):
        return user
    record_denied_admin_attempt(request, user)
    raise AppError(code="forbidden", message="Insufficient admin permissions", http_status=403)


def require_moderator() -> Callable[..., Awaitable[CurrentUser]]:
    """Admin moderation workflows (KYC + canonical product approval)."""
    return require_role(*sorted(MODERATOR_ROLES))


def require_role(*required_roles: str) -> Callable[..., Awaitable[CurrentUser]]:
    if not required_roles:
        raise ValueError("require_role expects at least one role")

    required = frozenset(required_roles)

    async def _require_role(
        request: Request,
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        allowed = bool(current_user.roles.intersection(required)) or (
            "superadmin" in current_user.roles
            and bool(required.intersection({"admin", "moderator"}))
        )
        if (
            not allowed
            and required.intersection({"admin", "moderator"})
            and any(role.startswith("rbac_") for role in current_user.roles)
        ):
            permissions = admin_permissions_for_request(
                _admin_route_template(request), request.method
            )
            if permissions:
                allowed = bool(
                    permissions
                    & load_admin_permissions(current_user, get_supabase_service_client())
                )
        if not allowed:
            if request.url.path.startswith("/admin"):
                record_denied_admin_attempt(request, current_user)
            raise AppError(
                code="forbidden",
                message="Insufficient permissions for this action",
                http_status=403,
                details={"required_roles": sorted(required)},
            )
        return current_user

    return _require_role


async def require_route_permission(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Grant by the route map only — no blanket pass for the unrestricted `admin` role.

    Used where the founder withheld a duty from `admin` (the audit-log viewer): the
    effective permission set of `admin` excludes it, while `superadmin` holds every
    permission and an `rbac_*` role may be granted it explicitly.
    """
    permissions = admin_permissions_for_request(_admin_route_template(request), request.method)
    if permissions and permissions & load_admin_permissions(user, get_supabase_service_client()):
        return user
    record_denied_admin_attempt(request, user)
    raise AppError(code="forbidden", message="Insufficient admin permissions", http_status=403)
