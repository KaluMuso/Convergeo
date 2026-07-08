from __future__ import annotations

from supabase import Client, create_client

from app.settings import Settings, get_settings


def get_user_client(token: str, settings: Settings | None = None) -> Client:
    """Return a Supabase client scoped to the caller's access token (RLS applies)."""
    resolved_settings = settings or get_settings()
    client = create_client(resolved_settings.supabase_url, resolved_settings.supabase_anon_key)
    client.postgrest.auth(token)
    return client
