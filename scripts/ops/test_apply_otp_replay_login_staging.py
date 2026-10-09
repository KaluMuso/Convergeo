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
        self.preflight = {
            "database_name": "postgres",
            "table_exists": True,
            "rls_enabled": True,
            "login_exists": False,
            "public_schema_create_count": 0,
            "public_reachable_definer_count": 0,
            "public_business_data_privilege_count": 0,
        }
        self.postcheck = {
            "restricted_login_exists": True,
            "insert_policy_exists": True,
            "select_policy_exists": True,
            "replay_usage": True,
            "request_id_insert": True,
            "expiry_insert": True,
            "request_id_select": True,
            "expiry_select": False,
            "replay_delete": False,
            "role_membership_count": 0,
            "schema_create_count": 0,
            "business_data_privilege_count": 0,
            "reachable_definer_count": 0,
        }

    def test_render_requires_reviewed_hash_and_injects_project_guard(self):
        sql = runner.checked_sql()
        self.assertNotIn(runner.GUARD_MARKER, sql)
        self.assertIn(f"set local otp_replay.target_project_ref = '{runner.PROJECT_REF}'", sql)

    def test_wrong_project_stops_before_database_request(self):
        project = {**self.project, "id": "another-project"}
        with mock.patch.object(runner, "api_json", return_value=project) as api:
            with self.assertRaisesRegex(ValueError, "project identity"):
                runner.apply("synthetic-token", runner.checked_sql())
        self.assertEqual(api.call_count, 1)

    def test_missing_table_and_broad_public_privilege_stop_before_write(self):
        for changed in ({"table_exists": False}, {"public_schema_create_count": 1},
                        {"public_reachable_definer_count": 1},
                        {"public_business_data_privilege_count": 1}):
            with self.subTest(changed=changed):
                before = {**self.preflight, **changed}
                with mock.patch.object(runner, "api_json", side_effect=[self.project, [before]]) as api:
                    with self.assertRaisesRegex(ValueError, "preflight"):
                        runner.apply("synthetic-token", runner.checked_sql())
                self.assertEqual(api.call_count, 2)
                self.assertTrue(api.call_args_list[-1].kwargs.get("read_only", True))

    def test_only_reviewed_project_and_preflight_reach_write(self):
        with mock.patch.object(runner, "api_json", side_effect=[
            self.project, [self.preflight], [], [self.postcheck]
        ]) as api, mock.patch("builtins.print"):
            runner.apply("synthetic-token", runner.checked_sql())
        self.assertEqual(api.call_count, 4)
        self.assertEqual(api.call_args_list[2].args[1], f"{runner.API_ROOT}/database/query")
        self.assertFalse(api.call_args_list[2].kwargs["read_only"])
        self.assertEqual(api.call_args_list[2].kwargs["query"], runner.checked_sql())

    def test_postcheck_denies_effective_expiry_read(self):
        after = {**self.postcheck, "expiry_select": True}
        with mock.patch.object(runner, "api_json", side_effect=[
            self.project, [self.preflight], [], [after]
        ]) as api:
            with self.assertRaisesRegex(ValueError, "postcheck"):
                runner.apply("synthetic-token", runner.checked_sql())
        self.assertEqual(api.call_count, 4)

    def test_postcheck_denies_business_data_privilege(self):
        after = {**self.postcheck, "business_data_privilege_count": 1}
        with mock.patch.object(runner, "api_json", side_effect=[
            self.project, [self.preflight], [], [after]
        ]):
            with self.assertRaisesRegex(ValueError, "postcheck"):
                runner.apply("synthetic-token", runner.checked_sql())

    def test_metadata_queries_cover_column_only_grants_and_truncate(self):
        for query in (runner.PREFLIGHT, runner.POSTCHECK):
            self.assertEqual(query.count("has_any_column_privilege("), 3)
            for privilege in ("SELECT", "INSERT", "UPDATE"):
                self.assertIn(f"'{privilege}')", query)
            self.assertIn("'TRUNCATE')", query)


if __name__ == "__main__":
    main()
