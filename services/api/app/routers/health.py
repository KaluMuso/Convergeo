from __future__ import annotations

import logging
import os

import httpx
from app.core.env_guards import extract_supabase_project_ref
from app.settings import get_settings
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
async def health() -> dict[str, str]:
    """Public liveness alias for external uptime monitors (keyword ``ok``).

    UptimeRobot and the observability docs probe ``/health``; the API otherwise
    exposes only ``/healthz``/``/readyz`` and Caddy does not rewrite, so an
    unaliased ``/health`` 404s and reads as perpetual downtime.
    """
    return {"status": "ok"}


@router.get("/fingerprint")
async def fingerprint() -> dict[str, str]:
    """Non-secret environment fingerprint for staging/production auditability.

    Contains no credentials. Supabase project ref is a public identifier used
    only to prove staging ≠ production.
    """
    settings = get_settings()
    git_sha = settings.git_sha or settings.sentry_release or "unknown"
    image_tag = settings.api_image_tag or git_sha
    project_ref = extract_supabase_project_ref(settings.supabase_url) or "unknown"
    return {
        "status": "ok",
        "env": settings.env,
        "git_sha": git_sha,
        "image_tag": image_tag,
        "supabase_project_ref": project_ref,
    }


async def _supabase_reachable() -> bool:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {settings.supabase_anon_key}",
                },
            )
            return response.status_code < 500
    except Exception:
        logger.warning("Supabase readiness check failed", exc_info=True)
        return False


def _search_embedding_configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


async def _search_vector_rpc_present() -> bool:
    """Probe that ``search_rrf`` is callable (FTS + trgm + optional vector lanes)."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/search_rrf",
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"query": "", "filters": {}},
            )
            return response.status_code < 500
    except Exception:
        logger.warning("Search vector RPC readiness check failed", exc_info=True)
        return False


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    supabase_ok = await _supabase_reachable()
    search_rpc_ok = await _search_vector_rpc_present()
    search_embedding_ok = _search_embedding_configured()

    overall_ok = supabase_ok and search_rpc_ok
    return {
        "status": "ok" if overall_ok else "degraded",
        "search_rpc": "ok" if search_rpc_ok else "degraded",
        "search_embedding": "ok" if search_embedding_ok else "degraded",
    }
