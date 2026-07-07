from __future__ import annotations

import logging

import httpx
from app.settings import get_settings
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


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


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    if await _supabase_reachable():
        return {"status": "ok"}
    return {"status": "degraded"}
