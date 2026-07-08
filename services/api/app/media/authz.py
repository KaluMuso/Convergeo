from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

from app.errors import AppError
from app.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class VendorScope:
    vendor_id: str


@lru_cache
def _jwks_client(supabase_url: str) -> PyJWKClient:
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url, cache_keys=True)


def _extract_vendor_id(claims: dict[str, Any]) -> str | None:
    for key in ("vendor_id",):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for metadata_key in ("app_metadata", "user_metadata"):
        metadata = claims.get(metadata_key)
        if isinstance(metadata, dict):
            vendor_id = metadata.get("vendor_id")
            if isinstance(vendor_id, str) and vendor_id.strip():
                return vendor_id.strip()

    subject = claims.get("sub")
    if isinstance(subject, str) and subject.strip():
        return subject.strip()

    return None


def _verify_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    jwks_client = _jwks_client(settings.supabase_url)
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256", "HS256"],
        audience="authenticated",
        issuer=issuer,
        options={"require": ["sub", "exp"]},
    )


async def require_vendor_scope(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> VendorScope:
    """Resolve the authenticated vendor scope for media signing.

    TODO(M04-P02): verify vendor role + ownership against the vendors table before
    issuing upload signatures. Today we only verify the Supabase JWT and derive
    vendor_id from JWT claims (vendor_id metadata when present, otherwise sub).
    """
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

    try:
        claims = _verify_supabase_jwt(token, settings)
    except InvalidTokenError as exc:
        raise AppError(
            code="unauthorized",
            message="Invalid or expired access token",
            http_status=401,
            details={"reason": exc.__class__.__name__},
        ) from exc
    except Exception as exc:
        raise AppError(
            code="forbidden",
            message="Unable to verify access token",
            http_status=403,
            details={"reason": exc.__class__.__name__},
        ) from exc

    vendor_id = _extract_vendor_id(claims)
    if not vendor_id:
        raise AppError(
            code="forbidden",
            message="Authenticated caller is missing vendor scope",
            http_status=403,
        )

    return VendorScope(vendor_id=vendor_id)
