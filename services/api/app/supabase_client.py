from __future__ import annotations

from functools import lru_cache

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

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


#: Idle pooled connections are dropped before Supabase's edge closes them.
SERVICE_KEEPALIVE_EXPIRY_S = 15.0


def build_service_http_client() -> httpx.Client:
    """HTTP/1.1 client for the long-lived service-role Supabase client.

    postgrest-py defaults to a shared HTTP/2 connection. Production logged dozens of
    ``httpx.RemoteProtocolError`` per hour (the edge closing an idle HTTP/2
    connection that the pool then reuses), which surfaced as random 500s, e.g. on
    ``GET /rfq`` while loading the caller's roles. HTTP/1.1 with a short keep-alive
    expiry drops idle sockets before the server does.
    """
    return httpx.Client(
        http2=False,
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(keepalive_expiry=SERVICE_KEEPALIVE_EXPIRY_S),
    )


@lru_cache
def get_supabase_service_client() -> SupabaseServiceClient:
    settings: Settings = get_settings()
    client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=SyncClientOptions(httpx_client=build_service_http_client()),
    )
    return SupabaseServiceClient(client)
