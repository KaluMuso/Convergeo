"""Offline guard tests for the staging-only OTP replay login runner."""

import importlib.util
from pathlib import Path
from unittest import TestCase, main, mock


SCRIPT = Path(__file__).with_name("apply-otp-replay-login-staging.py")
SPEC = importlib.util.spec_from_file_location("replay_login_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ReplayLoginRunnerTests(TestCase):
    def setUp(self):
        self.project = {
            "id": runner.PROJECT_REF,
            "name": runner.PROJECT_NAME,
            "database": {"host": runner.DATABASE_HOST},
        }
        self.preflight = runner.EXPECTED_PREFLIGHT.copy()
        self.postcheck = runner.EXPECTED_POSTCHECK.copy()

    def test_render_requires_reviewed_hash_and_injects_project_guard(self):
        sql = runner.checked_sql()
        self.assertNotIn(runner.GUARD_MARKER, sql)
        self.assertIn(
            f"set local otp_replay.target_project_ref = '{runner.PROJECT_REF}'", sql
        )

    def test_wrong_project_stops_before_database_request(self):
        project = {**self.project, "id": "another-project"}
        with mock.patch.object(runner, "api_json", return_value=project) as api:
            with self.assertRaisesRegex(ValueError, "project identity"):
                runner.apply("synthetic-token", runner.checked_sql())
        self.assertEqual(api.call_count, 1)

    def test_missing_table_and_broad_public_privilege_stop_before_write(self):
        for changed in (
            {"table_exists": False},
            {"public_schema_create_count": 1},
            {"public_reachable_definer_count": 1},
            {"public_business_data_privilege_count": 1},
        ):
            with self.subTest(changed=changed):
                before = {**self.preflight, **changed}
                with mock.patch.object(
                    runner, "api_json", side_effect=[self.project, [before]]
                ) as api:
                    with self.assertRaisesRegex(ValueError, "preflight"):
                        runner.apply("synthetic-token", runner.checked_sql())
                self.assertEqual(api.call_count, 2)
                self.assertTrue(api.call_args_list[-1].kwargs.get("read_only", True))

    def test_only_reviewed_project_and_preflight_reach_write(self):
        with (
            mock.patch.object(
                runner,
                "api_json",
                side_effect=[self.project, [self.preflight], [], [self.postcheck]],
            ) as api,
            mock.patch("builtins.print"),
        ):
            runner.apply("synthetic-token", runner.checked_sql())
        self.assertEqual(api.call_count, 4)
        self.assertEqual(
            api.call_args_list[2].args[1], f"{runner.API_ROOT}/database/query"
        )
        self.assertFalse(api.call_args_list[2].kwargs["read_only"])
        self.assertEqual(api.call_args_list[2].kwargs["query"], runner.checked_sql())

    def test_postcheck_denies_effective_expiry_read(self):
        after = {**self.postcheck, "expiry_select": True}
        with mock.patch.object(
            runner,
            "api_json",
            side_effect=[self.project, [self.preflight], [], [after]],
        ) as api:
            with self.assertRaisesRegex(ValueError, "postcheck"):
                runner.apply("synthetic-token", runner.checked_sql())
        self.assertEqual(api.call_count, 4)

    def test_postcheck_denies_business_data_privilege(self):
        after = {**self.postcheck, "business_data_privilege_count": 1}
        with mock.patch.object(
            runner,
            "api_json",
            side_effect=[self.project, [self.preflight], [], [after]],
        ):
            with self.assertRaisesRegex(ValueError, "postcheck"):
                runner.apply("synthetic-token", runner.checked_sql())

    def test_metadata_queries_cover_column_only_grants_and_truncate(self):
        for query in (runner.PREFLIGHT, runner.POSTCHECK):
            self.assertEqual(
                query.count("has_any_column_privilege("),
                3 if query == runner.PREFLIGHT else 4,
            )
            for privilege in ("SELECT", "INSERT", "UPDATE"):
                self.assertIn(f"'{privilege}')", query)
            self.assertIn("'TRUNCATE')", query)


class ReplayLoginSafetyTests(TestCase):
    """Security regression cases; API and transport are always synthetic."""

    setUp = ReplayLoginRunnerTests.setUp

    def test_default_mode_makes_no_request_and_does_not_read_token(self):
        with (
            mock.patch.object(
                runner, "api_json", side_effect=AssertionError("network")
            ) as api,
            mock.patch.object(runner.sys, "argv", ["runner"]),
            mock.patch.object(runner.os, "environ", {}),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(runner.main(), 0)
        api.assert_not_called()

    def test_apply_requires_private_token_before_any_request(self):
        with (
            mock.patch.object(runner, "api_json") as api,
            mock.patch.object(runner.sys, "argv", ["runner", "--apply"]),
            mock.patch.object(runner.os, "environ", {}),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(runner.main(), 1)
        api.assert_not_called()

    def test_arbitrary_sql_is_rejected_before_network(self):
        with mock.patch.object(runner, "api_json") as api:
            with self.assertRaisesRegex(runner.BootstrapError, "guarded SQL"):
                runner.apply("synthetic-token", runner.checked_sql() + "SELECT 1;")
        api.assert_not_called()

    def test_source_hash_and_both_guard_markers_are_required(self):
        source = runner.SQL_FILE.read_bytes()
        with mock.patch.object(runner, "SQL_SHA256", "0" * 64):
            with self.assertRaisesRegex(runner.BootstrapError, "hash changed"):
                runner.checked_sql()
        for marker in (runner.GUARD_MARKER, runner.PREFLIGHT_MARKER):
            for replacement in ("", marker + "\n" + marker):
                data = source.replace(marker.encode(), replacement.encode())
                with (
                    mock.patch.object(runner.Path, "read_bytes", return_value=data),
                    mock.patch.object(
                        runner, "SQL_SHA256", runner.hashlib.sha256(data).hexdigest()
                    ),
                ):
                    with self.assertRaisesRegex(runner.BootstrapError, "guard marker"):
                        runner.checked_sql()

    def test_existing_role_policy_or_extra_relation_blocks_before_write(self):
        for change in (
            {"login_exists": True},
            {"replay_policy_count": 1},
            {"replay_relation_count": 2},
            {"replay_columns_valid": False},
            {"replay_constraints_valid": False},
            {"replay_expiry_index_valid": False},
            {"rls_enabled": False},
            {"database_name": "wrong-db"},
        ):
            with (
                self.subTest(change=change),
                mock.patch.object(
                    runner,
                    "api_json",
                    side_effect=[self.project, [{**self.preflight, **change}]],
                ) as api,
            ):
                with self.assertRaisesRegex(runner.BootstrapError, "preflight"):
                    runner.apply("synthetic-token", runner.checked_sql())
                self.assertEqual(api.call_count, 2)

    def test_all_project_identity_fields_and_malformed_database_fail_closed(self):
        for change in (
            {"name": "wrong-name"},
            {"database": {"host": "wrong-host"}},
            {"database": None},
            {"database": "wrong-shape"},
        ):
            with (
                self.subTest(change=change),
                mock.patch.object(
                    runner, "api_json", return_value={**self.project, **change}
                ) as api,
            ):
                with self.assertRaisesRegex(runner.BootstrapError, "project identity"):
                    runner.apply("synthetic-token", runner.checked_sql())
                self.assertEqual(api.call_count, 1)

    def test_metadata_types_missing_and_extra_fields_fail_closed(self):
        changed = [
            {**self.preflight, "table_exists": 1},
            {**self.preflight, "public_schema_create_count": False},
            {**self.preflight, "unknown": False},
            {
                key: value
                for key, value in self.preflight.items()
                if key != "rls_enabled"
            },
        ]
        for before in changed:
            with (
                self.subTest(before=before),
                mock.patch.object(
                    runner, "api_json", side_effect=[self.project, [before]]
                ) as api,
            ):
                with self.assertRaisesRegex(runner.BootstrapError, "preflight"):
                    runner.apply("synthetic-token", runner.checked_sql())
                self.assertEqual(api.call_count, 2)

    def test_new_postcheck_boundaries_stop_after_single_write(self):
        for key in (
            "replay_update",
            "replay_truncate",
            "restricted_search_path",
            "insert_policy_valid",
            "select_policy_valid",
            "rls_enabled",
            "replay_policy_count",
        ):
            changed = {
                **self.postcheck,
                key: 3 if key == "replay_policy_count" else not self.postcheck[key],
            }
            with (
                self.subTest(key=key),
                mock.patch.object(
                    runner,
                    "api_json",
                    side_effect=[self.project, [self.preflight], [], [changed]],
                ) as api,
            ):
                with self.assertRaisesRegex(
                    runner.BootstrapError, "inspect state.*do not rerun"
                ):
                    runner.apply("synthetic-token", runner.checked_sql())
                self.assertEqual(
                    sum(c.kwargs.get("read_only") is False for c in api.call_args_list),
                    1,
                )

    def test_write_and_postcheck_transport_failures_require_inspection(self):
        for phase in (2, 3):
            replies = [self.project, [self.preflight], [], [self.postcheck]]
            replies[phase] = runner.urllib.error.URLError("synthetic-secret-marker")
            with (
                self.subTest(phase=phase),
                mock.patch.object(runner, "api_json", side_effect=replies) as api,
            ):
                with self.assertRaisesRegex(
                    runner.BootstrapError, "may have committed.*do not rerun"
                ) as caught:
                    runner.apply("synthetic-token", runner.checked_sql())
                self.assertNotIn("synthetic-secret-marker", str(caught.exception))
                self.assertEqual(api.call_count, phase + 1)

    def test_raw_remote_exception_is_not_printed(self):
        with (
            mock.patch.object(
                runner,
                "api_json",
                side_effect=runner.urllib.error.URLError("synthetic-secret-marker"),
            ),
            mock.patch.object(runner.sys, "argv", ["runner", "--apply"]),
            mock.patch.object(
                runner.os, "environ", {"SUPABASE_ACCESS_TOKEN": "synthetic-token"}
            ),
            mock.patch("builtins.print") as output,
        ):
            self.assertEqual(runner.main(), 1)
        self.assertNotIn("synthetic-secret-marker", str(output.call_args_list))
        self.assertNotIn("synthetic-token", str(output.call_args_list))

    def test_malformed_http_is_suppressed_before_and_after_write(self):
        for error in (
            runner.http.client.BadStatusLine("synthetic-secret-marker"),
            runner.http.client.IncompleteRead(b"synthetic-secret-marker", 100),
        ):
            for phase in (0, 2, 3):
                replies = [self.project, [self.preflight], [], [self.postcheck]]
                replies[phase] = error
                with (
                    self.subTest(error=type(error).__name__, phase=phase),
                    mock.patch.object(runner, "api_json", side_effect=replies) as api,
                    mock.patch.object(runner.sys, "argv", ["runner", "--apply"]),
                    mock.patch.object(
                        runner.os,
                        "environ",
                        {"SUPABASE_ACCESS_TOKEN": "synthetic-token"},
                    ),
                    mock.patch("builtins.print") as output,
                ):
                    self.assertEqual(runner.main(), 1)
                    self.assertNotIn(
                        "synthetic-secret-marker", str(output.call_args_list)
                    )
                    self.assertNotIn("synthetic-token", str(output.call_args_list))
                    self.assertEqual(api.call_count, phase + 1)
                    if phase > 0:
                        self.assertIn("may have committed", str(output.call_args_list))
                        self.assertIn("do not rerun", str(output.call_args_list))

    def test_network_boundary_rejects_other_url_method_and_malformed_token(self):
        for token, url, query in (
            ("synthetic-token", "https://other.example", None),
            ("synthetic-token", runner.API_ROOT, "SELECT 1"),
            ("bad\nheader", runner.API_ROOT, None),
        ):
            with (
                self.subTest(url=url),
                mock.patch.object(runner.urllib.request, "build_opener") as opener,
            ):
                with self.assertRaises(runner.BootstrapError):
                    runner.api_json(token, url, query=query)
                opener.assert_not_called()

    def test_redirect_handler_refuses_all_redirects(self):
        for code in (301, 302, 303, 307, 308):
            with (
                self.subTest(code=code),
                self.assertRaisesRegex(runner.BootstrapError, "redirect refused"),
            ):
                runner.NoRedirect().redirect_request(
                    None, None, code, "ignored", {}, "https://other.example"
                )

    def test_transport_uses_verified_tls_no_proxy_unredirected_auth_and_bound(self):
        response = mock.MagicMock()
        response.geturl.return_value = runner.API_ROOT
        response.read.return_value = b'{"id":"synthetic"}'
        opener = mock.MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with mock.patch.object(
            runner.urllib.request, "build_opener", return_value=opener
        ) as build:
            self.assertEqual(
                runner.api_json("synthetic-token", runner.API_ROOT), {"id": "synthetic"}
            )
        handlers = build.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertTrue(handlers[1]._context.check_hostname)
        self.assertEqual(handlers[1]._context.verify_mode, runner.ssl.CERT_REQUIRED)
        self.assertIsInstance(handlers[2], runner.NoRedirect)
        request = opener.open.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(
            request.unredirected_hdrs["Authorization"], "Bearer synthetic-token"
        )
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 20)
        response.read.assert_called_once_with(runner.MAX_RESPONSE_BYTES + 1)

    def test_transport_rejects_changed_endpoint_and_oversize_response(self):
        for endpoint, payload in (
            ("https://other.example", b"{}"),
            (runner.API_ROOT, b"x" * (runner.MAX_RESPONSE_BYTES + 1)),
        ):
            response = mock.MagicMock()
            response.geturl.return_value = endpoint
            response.read.return_value = payload
            opener = mock.MagicMock()
            opener.open.return_value.__enter__.return_value = response
            with (
                self.subTest(endpoint=endpoint),
                mock.patch.object(
                    runner.urllib.request, "build_opener", return_value=opener
                ),
            ):
                with self.assertRaises(runner.BootstrapError):
                    runner.api_json("synthetic-token", runner.API_ROOT)

    def test_transactional_preflight_is_inside_transaction_before_role_creation(self):
        sql = runner.checked_sql()
        self.assertLess(sql.index("begin;"), sql.index("do $preflight$"))
        self.assertLess(
            sql.index("do $preflight$"), sql.index("create role n8n_otp_replay")
        )
        self.assertLess(sql.index("create role n8n_otp_replay"), sql.index("commit;"))
        self.assertIn("set local statement_timeout = '10s'", sql)
        self.assertIn("set local lock_timeout = '3s'", sql)


if __name__ == "__main__":
    main()
