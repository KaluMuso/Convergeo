from __future__ import annotations

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
        "events.manage",
        "products.manage",
        "services.read",
        "vendors.manage",
        "ads.manage",
        "analytics.read",
        "inventory.read",
    }
)


_ADMIN_ROUTE_PERMISSIONS: dict[tuple[str, str], str] = {
    ("GET", "/admin/orders/search"): "finance.read",
    ("GET", "/admin/orders/{order_id}"): "finance.read",
    ("GET", "/admin/disputes"): "finance.read",
    ("GET", "/admin/disputes/{dispute_id}"): "finance.read",
    ("GET", "/admin/events/high-value-queue"): "events.manage",
    ("POST", "/admin/events/{event_id}/high-value-verify"): "events.manage",
    ("GET", "/admin/products/duplicates"): "products.manage",
    ("GET", "/admin/products/search"): "products.manage",
    ("GET", "/admin/products/canonical"): "products.manage",
    ("GET", "/admin/products/{product_id}/relations"): "products.manage",
    ("POST", "/admin/products/merge"): "products.manage",
    ("PUT", "/admin/products/{product_id}/relations"): "products.manage",
    ("PATCH", "/admin/products/canonical/{product_id}/status"): "products.manage",
    ("GET", "/admin/services"): "services.read",
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
    ("GET", "/admin/dashboard"): "analytics.read",
    ("GET", "/admin/search-insights/top-terms"): "analytics.read",
    ("GET", "/admin/search-insights/zero-results"): "analytics.read",
    ("GET", "/admin/search-insights/ask-cost"): "analytics.read",
    ("GET", "/admin/clip-analytics"): "analytics.read",
    ("GET", "/admin/governance/vendors"): "analytics.read",
}


def admin_permission_for_request(path_template: str, method: str) -> str | None:
    """Explicit route inventory. Unknown and payment mutation routes deny."""
    return _ADMIN_ROUTE_PERMISSIONS.get((method, path_template))


def _admin_route_template(request: Request) -> str:
    if not request.url.path.startswith("/admin/"):
        return ""
    route = request.scope.get("route")
    template = str(getattr(route, "path", ""))
    # FastAPI's nested _IncludedRouter sets the matched route path relative to
    # its /admin parent. Standalone admin routers already include the prefix.
    return template if template.startswith("/admin/") else "/admin" + template


def load_admin_permissions(
    user: CurrentUser, service_client: SupabaseServiceClient
) -> frozenset[str]:
    """Read current grants from the same user_roles snapshot used for identity."""
    if "superadmin" in user.roles or "admin" in user.roles:
        return ADMIN_PERMISSIONS
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
    permission = admin_permission_for_request(_admin_route_template(request), request.method)
    if permission and permission in load_admin_permissions(user, get_supabase_service_client()):
        return user
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
            permission = admin_permission_for_request(
                _admin_route_template(request), request.method
            )
            if permission:
                allowed = permission in load_admin_permissions(
                    current_user, get_supabase_service_client()
                )
        if not allowed:
            raise AppError(
                code="forbidden",
                message="Insufficient permissions for this action",
                http_status=403,
                details={"required_roles": sorted(required)},
            )
        return current_user

    return _require_role
