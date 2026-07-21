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


def require_role(*required_roles: str) -> Callable[..., Awaitable[CurrentUser]]:
    if not required_roles:
        raise ValueError("require_role expects at least one role")

    required = frozenset(required_roles)

    async def _require_role(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not current_user.roles.intersection(required):
            raise AppError(
                code="forbidden",
                message="Insufficient permissions for this action",
                http_status=403,
                details={"required_roles": sorted(required)},
            )
        return current_user

    return _require_role
