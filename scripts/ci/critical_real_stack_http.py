#!/usr/bin/env python3
"""Loopback REST gateway and fail-closed preflight for the disposable CI stack.

The gateway only removes the Supabase client's /rest/v1 prefix. PostgREST
performs every table/RPC operation and every authorization decision.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

GATEWAY = "http://127.0.0.1:3007"
POSTGREST = "http://127.0.0.1:3006"
GROUPS = frozenset(
    ("cart", "checkout", "kyc", "prepaid", "collection", "tickets", "concurrency", "creation")
)
HOP_HEADERS = frozenset(
    ("connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
     "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length")
)


class BindingError(RuntimeError):
    """A CI-only endpoint, role, or database binding is unsafe or unavailable."""


def forward_path(request_path: str) -> str:
    parsed = urlsplit(request_path)
    if parsed.scheme or parsed.netloc or parsed.fragment or not request_path.startswith("/"):
        raise BindingError("absolute or malformed gateway request")
    if parsed.path != "/rest/v1" and not parsed.path.startswith("/rest/v1/"):
        raise BindingError("gateway request is outside /rest/v1")
    path = parsed.path[len("/rest/v1"):] or "/"
    return path + (f"?{parsed.query}" if parsed.query else "")


class RestGateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        # Requests contain JWTs and query data; never emit request/response logs.
        pass

    def _forward(self) -> None:
        try:
            path = forward_path(self.path)
        except BindingError:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {
            name: value for name, value in self.headers.items()
            if name.lower() not in HOP_HEADERS
        }
        headers["Host"] = "127.0.0.1:3006"
        upstream = http.client.HTTPConnection("127.0.0.1", 3006, timeout=90)
        try:
            upstream.request(self.command, path, body=body, headers=headers)
            response = upstream.getresponse()
            response_body = response.read()
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in HOP_HEADERS:
                    self.send_header(name, value)
            upstream_length = response.getheader("Content-Length")
            response_length = (
                upstream_length if self.command == "HEAD" and upstream_length is not None
                else str(len(response_body))
            )
            self.send_header("Content-Length", response_length)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response_body)
        except (OSError, TimeoutError):
            self.send_error(502, "disposable PostgREST unavailable")
        finally:
            upstream.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _forward


def require_base_url(value: str) -> None:
    if value.rstrip("/") != GATEWAY or urlsplit(value).path not in ("", "/"):
        raise BindingError("service client targets a wrong, shared, or placeholder endpoint")


def require_rest_urls(*urls: str) -> None:
    if not urls or any(url.rstrip("/") != GATEWAY + "/rest/v1" for url in urls):
        raise BindingError("pinned Supabase client does not use the local /rest/v1 route")


def require_database_url(value: str, expected: str) -> None:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise BindingError("SQL fixtures target the wrong database or host") from None
    if (parsed.scheme not in ("postgres", "postgresql")
            or parsed.hostname != "127.0.0.1" or port != 54322
            or parsed.path != "/" + expected or parsed.query or parsed.fragment):
        raise BindingError("SQL fixtures target the wrong database or host")


def require_probe_rows(data: object, group: str, database: str) -> None:
    if data != [{"group_name": group, "database_name": database}]:
        raise BindingError("service-client database marker differs from SQL fixture target")


def inspect_container(container: str, database: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{12,64}", container):
        raise BindingError("PostgREST container identity is missing")
    try:
        state = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        raw = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
            text=True, capture_output=True, check=True,
        ).stdout
        variables = dict(entry.split("=", 1) for entry in json.loads(raw) if "=" in entry)
    except (OSError, subprocess.CalledProcessError, ValueError, TypeError):
        raise BindingError("cannot inspect running disposable PostgREST") from None
    if state != "true":
        raise BindingError("disposable PostgREST is stopped")
    uri = variables.get("PGRST_DB_URI", "")
    require_database_url(uri, database)
    if urlsplit(uri).username != "ci_critical_authenticator":
        raise BindingError("PostgREST database role is not the disposable authenticator")


def request_status(url: str, token: str | None = None) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(Request(url, headers=headers), timeout=5) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except (OSError, URLError):
        raise BindingError("local REST service is absent") from None


def role_token(role: str, secret: str) -> str:
    def encode(value: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(value, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    content = encode({"alg": "HS256", "typ": "JWT"}) + "." + encode(
        {"role": role, "exp": int(time.time()) + 3600}
    )
    signature = hmac.new(secret.encode(), content.encode(), hashlib.sha256).digest()
    return content + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def preflight(group: str, database: str, container: str) -> None:
    permitted = (f"ci_critical_{group}", f"ci_critical_focus_{group}")
    if group not in GROUPS or database not in permitted:
        raise BindingError("unknown fixture group or database")
    require_base_url(os.environ.get("SUPABASE_URL", ""))
    if os.environ.get("SUPABASE_REST_URL") != GATEWAY + "/rest/v1":
        raise BindingError("REST test endpoint is not the local gateway route")
    if os.environ.get("LANE_D_POSTGREST_URL") != POSTGREST:
        raise BindingError("direct PostgREST endpoint is not disposable loopback")
    require_database_url(os.environ.get("SUPABASE_DB_URL", ""), database)
    order_db_url = os.environ.get("ORDER_TEST_DB_URL")
    if order_db_url and order_db_url != os.environ["SUPABASE_DB_URL"]:
        raise BindingError("order fixtures target another database")
    inspect_container(container, database)

    # Import only after checking environment; each group and preflight uses a
    # new process, so no cached client or settings survives a database switch.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))
    from app.services.cart.store import get_service_client
    from app.services.stock.claim import _service_client
    from app.settings import get_settings
    from app.supabase_client import get_supabase_service_client

    settings = get_settings()
    require_base_url(settings.supabase_url)
    service = get_supabase_service_client()
    client = service.client
    try:
        require_rest_urls(
            str(client.rest_url),
            str(client.postgrest.base_url),
            str(client.postgrest.session.base_url),
        )
        if get_service_client() is not service or _service_client() is not service:
            raise BindingError("nested listing/TTL factories use a stale service client")
        data = client.table("ci_critical_binding_probe").select(
            "group_name,database_name"
        ).limit(2).execute().data
        require_probe_rows(data, group, database)
        # These are the actual listing and TTL client paths, not fabricated rows.
        get_service_client().client.table("vendor_listings").select("id").limit(1).execute()
        _service_client().client.table("platform_config").select("key").limit(1).execute()
    except BindingError:
        raise
    except Exception as exc:
        raise BindingError(f"real service-factory read failed ({type(exc).__name__})") from None
    finally:
        if client._postgrest is not None:
            client.postgrest.aclose()
        get_supabase_service_client.cache_clear()
        get_settings.cache_clear()

    probe = GATEWAY + "/rest/v1/ci_critical_binding_probe?select=group_name&limit=1"
    if request_status(probe, "invalid.invalid.invalid") != 401:
        raise BindingError("invalid JWT was not rejected")
    anon = os.environ["SUPABASE_ANON_KEY"]
    authenticated = role_token("authenticated", os.environ["LANE_D_JWT_SECRET"])
    for role, token in (("anon", anon), ("authenticated", authenticated)):
        if request_status(probe, token) not in (401, 403):
            raise BindingError(f"{role} read the service-only database probe")
    print(
        f"group={group} sql_database={database} postgrest_database={database} "
        f"gateway={GATEWAY} effective_rest={GATEWAY}/rest/v1 "
        "factory_listing_ttl_reads=PASS invalid_jwt=DENIED anon=DENIED authenticated=DENIED"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("gateway", "preflight"))
    parser.add_argument("--group")
    parser.add_argument("--database")
    parser.add_argument("--container")
    args = parser.parse_args()
    if args.command == "gateway":
        with ThreadingHTTPServer(("127.0.0.1", 3007), RestGateway) as server:
            server.serve_forever(poll_interval=0.2)
        return 0
    try:
        preflight(args.group or "", args.database or "", args.container or "")
    except BindingError as exc:
        print(f"ERROR: critical real-stack preflight: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
