from __future__ import annotations

from collections.abc import Generator

from fastapi import Request

from app.settings import Settings, get_settings
from app.supabase_client import SupabaseServiceClient, get_supabase_service_client


def get_settings_dep() -> Settings:
    return get_settings()


def get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return "unknown"


def get_supabase_client() -> Generator[SupabaseServiceClient, None, None]:
    yield get_supabase_service_client()
