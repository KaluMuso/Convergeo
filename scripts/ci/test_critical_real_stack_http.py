#!/usr/bin/env python3
"""Command/target guards only; real SQL and HTTP acceptance stays hosted."""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from critical_real_stack_http import (
    BindingError,
    RestGateway,
    forward_path,
    inspect_container,
    request_status,
    preflight,
    require_base_url,
    require_database_url,
    require_probe_rows,
    require_rest_urls,
)


class CriticalHttpGuards(unittest.TestCase):
    def test_head_keeps_upstream_content_length_without_a_body(self) -> None:
        class Upstream(BaseHTTPRequestHandler):
            def do_HEAD(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", "7")
                self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        original_connection = http.client.HTTPConnection
        with ThreadingHTTPServer(("127.0.0.1", 0), Upstream) as upstream, \
                ThreadingHTTPServer(("127.0.0.1", 0), RestGateway) as gateway:
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            upstream_thread.start()
            gateway_thread.start()

            def local_upstream(
                _host: str, _port: int, *, timeout: int
            ) -> http.client.HTTPConnection:
                return original_connection("127.0.0.1", upstream.server_port, timeout=timeout)

            try:
                with patch("critical_real_stack_http.http.client.HTTPConnection", local_upstream):
                    client = original_connection("127.0.0.1", gateway.server_port, timeout=5)
                    try:
                        client.request("HEAD", "/rest/v1/vendor_listings")
                        response = client.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.getheader("Content-Length"), "7")
                        self.assertEqual(response.read(), b"")
                    finally:
                        client.close()
            finally:
                gateway.shutdown()
                upstream.shutdown()
                gateway_thread.join(timeout=5)
                upstream_thread.join(timeout=5)

    def test_runner_binds_each_group_before_pytest_and_closes_after(self) -> None:
        runner = (Path(__file__).resolve().parent / "run-critical-real-stack.sh").read_text()
        group_body = runner.split("run_group() {", 1)[1].split("\n}\n", 1)[0]
        pytest_call = 'uv run pytest -q -o xfail_strict=true -rA --junitxml="$raw/$label.xml"'
        self.assertLess(
            group_body.index('start_postgrest "$database"'),
            group_body.index("critical_real_stack_http.py preflight"),
        )
        self.assertLess(
            group_body.index("critical_real_stack_http.py preflight"),
            group_body.index(pytest_call),
        )
        self.assertLess(group_body.index(pytest_call), group_body.index("stop_postgrest"))
        for group in ("cart", "checkout", "kyc", "prepaid", "collection", "tickets",
                      "concurrency", "creation"):
            self.assertIn(f"run_group {group} ci_critical_{group} {group} full ", runner)
        self.assertLess(
            runner.index("run_group checkout ci_critical_focus_checkout"),
            runner.index("run_group cart ci_critical_cart"),
        )

    def test_gateway_strips_only_the_supabase_rest_prefix(self) -> None:
        self.assertEqual(
            forward_path("/rest/v1/vendor_listings?select=id&limit=1"),
            "/vendor_listings?select=id&limit=1",
        )
        self.assertEqual(forward_path("/rest/v1/rpc/test"), "/rpc/test")
        for path in ("/auth/v1/user", "http://shared.example/rest/v1/x", "//shared/rest/v1/x"):
            with self.subTest(path=path), self.assertRaises(BindingError):
                forward_path(path)

    def test_wrong_endpoint_and_wrong_pinned_client_path_reject(self) -> None:
        with self.assertRaisesRegex(BindingError, "wrong, shared, or placeholder"):
            require_base_url("https://example.supabase.co")
        with self.assertRaisesRegex(BindingError, "local /rest/v1"):
            require_rest_urls("http://127.0.0.1:3006/rest/v1")
        require_base_url("http://127.0.0.1:3007")
        require_rest_urls("http://127.0.0.1:3007/rest/v1")

    def test_wrong_legacy_rest_endpoint_rejects_before_client_creation(self) -> None:
        with patch.dict(os.environ, {
            "SUPABASE_URL": "http://127.0.0.1:3007",
            "SUPABASE_REST_URL": "http://127.0.0.1:3006",
        }):
            with self.assertRaisesRegex(BindingError, "REST test endpoint"):
                preflight("checkout", "ci_critical_checkout", "0123456789ab")

    def test_stopped_service_rejects(self) -> None:
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        with self.assertRaisesRegex(BindingError, "REST service is absent"):
            request_status(f"http://127.0.0.1:{port}/rest/v1/ci_critical_binding_probe")

    def test_wrong_sql_database_and_stale_group_marker_reject(self) -> None:
        with self.assertRaisesRegex(BindingError, "SQL fixtures target"):
            require_database_url(
                "postgresql://postgres:postgres@127.0.0.1:54322/shared",
                "ci_critical_checkout",
            )
        with self.assertRaisesRegex(BindingError, "database marker"):
            require_probe_rows(
                [{"group_name": "cart", "database_name": "ci_critical_cart"}],
                "checkout",
                "ci_critical_checkout",
            )

    def test_wrong_container_database_and_stopped_container_reject(self) -> None:
        container = "0123456789ab"
        env = json.dumps(
            ["PGRST_DB_URI=postgresql://ci_critical_authenticator:password"
             "@127.0.0.1:54322/ci_critical_cart"]
        )
        with patch("critical_real_stack_http.subprocess.run") as run:
            run.side_effect = [
                subprocess.CompletedProcess([], 0, "true\n", ""),
                subprocess.CompletedProcess([], 0, env, ""),
            ]
            with self.assertRaisesRegex(BindingError, "SQL fixtures target"):
                inspect_container(container, "ci_critical_checkout")
        with patch("critical_real_stack_http.subprocess.run") as run:
            run.side_effect = [
                subprocess.CompletedProcess([], 0, "false\n", ""),
                subprocess.CompletedProcess([], 0, env, ""),
            ]
            with self.assertRaisesRegex(BindingError, "stopped"):
                inspect_container(container, "ci_critical_cart")


if __name__ == "__main__":
    unittest.main()
