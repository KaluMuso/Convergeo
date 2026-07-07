from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.settings import Settings, get_settings


class SupabaseServiceClient:
    """Server-side Supabase client wrapper.

    **SECURITY:** This client uses the Supabase **service-role** key. It is server-only,
  must never be exposed to browsers or mobile clients, and bypasses Row Level Security.
  Every caller is responsible for performing its own authorization checks before reading
  or mutating data.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    @property
    def client(self) -> Client:
        return self._client


@lru_cache
def get_supabase_service_client() -> SupabaseServiceClient:
    settings: Settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return SupabaseServiceClient(client)
