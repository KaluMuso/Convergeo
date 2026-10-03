"""Installed client compatibility without provider, database, or socket traffic."""

from __future__ import annotations

import gzip
import socket
from typing import TYPE_CHECKING, Any, cast

import anyio
import httpx
import pytest
import sentry_sdk
import urllib3
from app.core.sentry import before_send
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import ResponseReceived
from h2.exceptions import ProtocolError
from sentry_sdk.transport import HttpTransport
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

if TYPE_CHECKING:
    from sentry_sdk._types import Event


@pytest.fixture(autouse=True)
def deny_socket_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Compatibility tests must use mocked transports")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_supabase_auth_and_postgrest_use_installed_httpx_transport() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/auth/v1/user":
            return httpx.Response(
                200,
                json={
                    "id": "11111111-1111-1111-1111-111111111111",
                    "aud": "authenticated",
                    "app_metadata": {},
                    "user_metadata": {},
                    "created_at": "2026-01-01T00:00:00Z",
                },
            )
        assert request.url.path == "/rest/v1/user_roles"
        return httpx.Response(200, json=[{"role": "customer"}])

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = create_client(
            "https://compatibility.invalid",
            "local-placeholder-key",
            options=SyncClientOptions(
                httpx_client=transport,
                auto_refresh_token=False,
                persist_session=False,
            ),
        )
        user = client.auth.get_user("local-access-token")
        assert user is not None
        assert user.user.id == "11111111-1111-1111-1111-111111111111"
        client.postgrest.auth("local-access-token")
        response = client.table("user_roles").select("role").execute()
        assert response.data == [{"role": "customer"}]
        assert len(requests) == 2
        assert all(r.headers["authorization"] == "Bearer local-access-token" for r in requests)


@pytest.mark.asyncio
async def test_httpx_async_transport_and_anyio_worker_compatibility() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "compatibility.invalid"
        await anyio.sleep(0)
        return httpx.Response(200, json={"quantity": 2, "amount_ngwee": 1500})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        response = await client.get("https://compatibility.invalid/mock")
    result = await anyio.to_thread.run_sync(lambda: response.json())
    assert result == {"quantity": 2, "amount_ngwee": 1500}


def test_http2_request_response_frames_without_network() -> None:
    client = H2Connection(config=H2Configuration(client_side=True))
    server = H2Connection(config=H2Configuration(client_side=False, header_encoding="utf-8"))
    client.initiate_connection()
    server.initiate_connection()
    server.receive_data(client.data_to_send())
    client.receive_data(server.data_to_send())
    client.send_headers(
        1,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":authority", "compatibility.invalid"),
            (":path", "/mock"),
        ],
        end_stream=True,
    )
    server.receive_data(client.data_to_send())
    server.send_headers(1, [(":status", "200")], end_stream=True)
    events = client.receive_data(server.data_to_send())
    assert any(
        isinstance(e, ResponseReceived) and e.headers == [(b":status", b"200")] for e in events
    )


def test_http2_rejects_duplicate_host_headers() -> None:
    client = H2Connection(
        config=H2Configuration(
            client_side=True,
            validate_outbound_headers=False,
            normalize_outbound_headers=False,
        )
    )
    server = H2Connection(config=H2Configuration(client_side=False))
    client.initiate_connection()
    server.receive_data(client.data_to_send())
    client.send_headers(
        1,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":path", "/mock"),
            ("host", "compatibility.invalid"),
            ("host", "different.invalid"),
        ],
        end_stream=True,
    )
    with pytest.raises(ProtocolError):
        server.receive_data(client.data_to_send())


def test_sentry_urllib3_transport_preserves_scrubbed_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[bytes] = []

    def request(_pool: Any, method: str, url: str, **kwargs: Any) -> urllib3.HTTPResponse:
        assert method == "POST"
        assert url.startswith("https://compatibility.invalid/")
        body = kwargs["body"]
        if kwargs["headers"].get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        sent.append(body)
        return urllib3.HTTPResponse(status=200, body=b"", headers={})

    monkeypatch.setattr(urllib3.PoolManager, "request", request)

    def filter_event(event: Event, hint: dict[str, Any]) -> Event:
        return cast("Event", before_send(dict(event), hint))

    client = sentry_sdk.Client(
        dsn="https://local-public-key@compatibility.invalid/1",
        default_integrations=False,
        auto_enabling_integrations=False,
        transport=HttpTransport,
        http_proxy="",
        https_proxy="",
        before_send=filter_event,
        send_client_reports=False,
    )
    try:
        event_id = client.capture_event(
            {
                "message": "Compatibility fixture for buyer@example.com",
                "extra": {"access_token": "local-fixture-secret", "quantity": 2},
            }
        )
        client.flush(timeout=2)
        assert event_id is not None
        assert len(sent) == 1
        assert b"buyer@example.com" not in sent[0]
        assert b"local-fixture-secret" not in sent[0]
        assert b'"quantity":2' in sent[0].replace(b" ", b"")
    finally:
        client.close(timeout=2)
