"""Synthetic, offline regressions for the email diagnostic deployment handoff."""

from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from email_diagnostic_handoff import REQUIRED_JOBS, resolve_email_handoff
from release_handoff_contract import ContractError

SHA = "a" * 40
RUN_ID = 901
ATTEMPT = 1
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
START = NOW - timedelta(minutes=20)
PROVED = NOW - timedelta(minutes=10)
END = NOW - timedelta(minutes=5)
PROJECTS = {portal: f"prj_{portal}123" for portal in ("customer", "vendor", "admin")}


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def fixture() -> dict:
    previews = {
        portal: {
            "candidate_sha": SHA,
            "deployment_sha": SHA,
            "target": "preview",
            "preview_url": f"https://convergeo-{portal}-abc123-vergeo-projects.vercel.app",
            "health_status": "ok",
            "health_app": portal,
            "health_env": "preview",
            "health_api_host": "api.staging.vergeo5.com",
            "health_build_id": SHA,
            "project_id": PROJECTS[portal],
            "deployment_id": f"dpl_{portal}123",
        }
        for portal in PROJECTS
    }
    proof = {
        "candidate_sha": SHA,
        "proved_at": iso(PROVED),
        "previews": previews,
        "api_fingerprint": {
            "env": "staging",
            "git_sha": SHA,
            "image_tag": SHA,
            "supabase_project_ref": "iyasmrmbcrvlfxpzescb",
        },
        "migrate_supabase_result": "success",
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("staging-sha-proof.json", json.dumps(proof))
    archive_bytes = stream.getvalue()
    run = {
        "id": RUN_ID,
        "run_attempt": ATTEMPT,
        "repository": {"full_name": "KaluMuso/Convergeo", "id": 1290591718},
        "head_repository": {"id": 1290591718},
        "head_branch": "staging",
        "head_sha": SHA,
        "path": ".github/workflows/deploy-staging.yml",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "run_started_at": iso(START),
        "updated_at": iso(END),
    }
    artifact = {
        "id": 777,
        "size_in_bytes": len(archive_bytes),
        "name": f"staging-sha-proof-{RUN_ID}-attempt-{ATTEMPT}",
        "expired": False,
        "digest": "sha256:" + hashlib.sha256(archive_bytes).hexdigest(),
        "created_at": iso(PROVED + timedelta(minutes=1)),
        "workflow_run": {
            "id": RUN_ID,
            "head_sha": SHA,
            "head_branch": "staging",
            "repository_id": 1290591718,
            "path": ".github/workflows/deploy-staging.yml",
        },
    }
    jobs = [
        {
            "name": name,
            "run_id": RUN_ID,
            "run_attempt": ATTEMPT,
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "started_at": iso(START),
            "completed_at": iso(END),
        }
        for name in REQUIRED_JOBS
    ]
    return {
        "archive": archive_bytes,
        "run": run,
        "artifact": artifact,
        "jobs": jobs,
        "candidate_sha": SHA,
        "current_staging_sha": SHA,
        "run_id": RUN_ID,
        "attempt": ATTEMPT,
        "artifact_id": 777,
        "project_ids": PROJECTS,
        "now": NOW,
    }


def replace_proof(data: dict, change) -> None:
    with zipfile.ZipFile(io.BytesIO(data["archive"])) as original:
        proof = json.loads(original.read("staging-sha-proof.json"))
    change(proof)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("staging-sha-proof.json", json.dumps(proof))
    data["archive"] = stream.getvalue()
    data["artifact"]["digest"] = "sha256:" + hashlib.sha256(data["archive"]).hexdigest()


class EmailDiagnosticHandoffTests(unittest.TestCase):
    def test_workflow_keeps_diagnostic_out_of_deploy_reset_and_certification(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        operation = (root / ".github/workflows/staging-operation.yml").read_text()
        diagnostic = (
            root / ".github/workflows/staging-email-diagnostic.yml"
        ).read_text()
        self.assertIn("group: staging-operation", operation)
        self.assertIn("inputs.focus_group != 'email-diagnostic'", operation)
        self.assertIn("needs: authorize", operation)
        self.assertIn("environment: staging", diagnostic)
        self.assertIn("owner_provisioned_readiness", diagnostic)
        job_header = diagnostic.split("  diagnostic:", 1)[1].split("    steps:", 1)[0]
        self.assertNotIn("E2E_CUSTOMER_EMAIL_PASSWORD", job_header)
        self.assertNotIn("VERCEL_AUTOMATION_BYPASS_SECRET", job_header)
        self.assertNotIn("seed_staging.py", diagnostic)
        self.assertNotIn("staging-certification-evidence", diagnostic)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", diagnostic)

    def test_valid_manual_staging_deploy_yields_only_two_portal_origins(self) -> None:
        self.assertEqual(
            resolve_email_handoff(**fixture()),
            (
                "https://convergeo-customer-abc123-vergeo-projects.vercel.app",
                "https://convergeo-vendor-abc123-vergeo-projects.vercel.app",
            ),
        )

    def test_moved_staging_ref_rejected(self) -> None:
        data = fixture()
        data["current_staging_sha"] = "b" * 40
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)

    def test_non_manual_or_failed_deploy_rejected(self) -> None:
        for field, value in (("event", "push"), ("conclusion", "failure")):
            with self.subTest(field=field):
                data = fixture()
                data["run"][field] = value
                with self.assertRaises(ContractError):
                    resolve_email_handoff(**data)

    def test_wrong_or_missing_proof_rejected(self) -> None:
        data = fixture()
        data["artifact"]["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)
        data = fixture()
        replace_proof(data, lambda proof: proof.update(candidate_sha="b" * 40))
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)

    def test_missing_or_failed_deploy_job_rejected(self) -> None:
        data = fixture()
        data["jobs"] = data["jobs"][:-1]
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)
        data = fixture()
        data["jobs"][0]["conclusion"] = "skipped"
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)

    def test_wrong_project_or_production_api_rejected(self) -> None:
        data = fixture()
        data["project_ids"] = {**PROJECTS, "vendor": "prj_other"}
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)
        data = fixture()
        replace_proof(
            data,
            lambda proof: proof["api_fingerprint"].update(
                supabase_project_ref="dpadrlxukcjbewpqympu"
            ),
        )
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)

    def test_unapproved_portal_origin_rejected(self) -> None:
        data = fixture()
        replace_proof(
            data,
            lambda proof: proof["previews"]["vendor"].update(
                preview_url="https://vendor.vergeo5.com"
            ),
        )
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)

    def test_skipped_migration_or_stale_proof_rejected(self) -> None:
        data = fixture()
        replace_proof(
            data, lambda proof: proof.update(migrate_supabase_result="skipped")
        )
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)
        data = fixture()
        data["now"] = NOW + timedelta(days=2)
        with self.assertRaises(ContractError):
            resolve_email_handoff(**data)


class EmailDiagnosticNegativeBoundaryTests(unittest.TestCase):
    def reject(self, data: dict) -> None:
        with self.assertRaises(ContractError) as raised:
            resolve_email_handoff(**data)
        self.assertRegex(str(raised.exception), r"^[A-Z_]+$")

    def test_exact_run_source_repo_branch_sha_workflow_attempt_status(self) -> None:
        for field, value in (
            ("id", RUN_ID + 1),
            ("run_attempt", ATTEMPT + 1),
            ("head_branch", "master"),
            ("head_sha", "b" * 40),
            ("path", ".github/workflows/other.yml"),
            ("event", "push"),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("repository", {"id": 1, "full_name": "KaluMuso/Convergeo"}),
            ("repository", {"id": 1290591718, "full_name": "attacker/Convergeo"}),
            ("head_repository", {"id": 1}),
            ("repository", None),
        ):
            with self.subTest(field=field, value=value):
                data = fixture()
                data["run"][field] = value
                self.reject(data)

    def test_exact_selected_artifact_identity_and_provenance(self) -> None:
        for field, value in (
            ("id", 778),
            ("id", True),
            ("name", "staging-sha-proof-901-attempt-2"),
            ("expired", True),
            ("expired", None),
            ("digest", None),
            ("size_in_bytes", 0),
            ("size_in_bytes", True),
            ("size_in_bytes", 1024 * 1024 + 1),
            ("workflow_run", None),
        ):
            with self.subTest(field=field):
                data = fixture()
                data["artifact"][field] = value
                self.reject(data)
        for field, value in (
            ("id", 902),
            ("head_sha", "b" * 40),
            ("head_branch", "master"),
            ("repository_id", 1),
            ("path", ".github/workflows/other.yml"),
        ):
            with self.subTest(field=field):
                data = fixture()
                data["artifact"]["workflow_run"][field] = value
                self.reject(data)

    def test_input_ids_are_concrete_safe_integers_with_bounded_attempt(self) -> None:
        for field in ("run_id", "attempt", "artifact_id"):
            for value in (0, -1, True, "901", 2**53):
                with self.subTest(field=field, value=value):
                    data = fixture()
                    data[field] = value
                    self.reject(data)
        data = fixture()
        data["attempt"] = 101
        self.reject(data)

    def test_candidate_and_current_ref_require_full_sha(self) -> None:
        for field in ("candidate_sha", "current_staging_sha"):
            for value in (SHA[:12], SHA + "\n", None, "private-token"):
                with self.subTest(field=field):
                    data = fixture()
                    data[field] = value
                    self.reject(data)

    def test_jobs_require_exact_current_attempt_success_unique_and_run_window(
        self,
    ) -> None:
        for index in range(len(REQUIRED_JOBS)):
            for field, value in (
                ("run_id", 902),
                ("run_attempt", 2),
                ("head_sha", "b" * 40),
                ("status", "in_progress"),
                ("conclusion", "skipped"),
                ("started_at", iso(START - timedelta(seconds=1))),
                ("completed_at", iso(END + timedelta(seconds=1))),
            ):
                with self.subTest(job=index, field=field):
                    data = fixture()
                    data["jobs"][index][field] = value
                    self.reject(data)
        data = fixture()
        data["jobs"].append(dict(data["jobs"][0]))
        self.reject(data)
        data = fixture()
        data["jobs"][0]["run_attempt"] = True
        self.reject(data)
        data = fixture()
        data["jobs"][0]["run_id"] = str(RUN_ID)
        self.reject(data)

    def test_proof_artifact_and_smoke_freshness_windows(self) -> None:
        for when in (START - timedelta(seconds=1), END + timedelta(seconds=1)):
            data = fixture()
            data["artifact"]["created_at"] = iso(when)
            self.reject(data)
            data = fixture()
            replace_proof(data, lambda proof: proof.update(proved_at=iso(when)))
            self.reject(data)
        data = fixture()
        data["now"] = NOW.replace(tzinfo=None)
        self.reject(data)
        data = fixture()
        data["now"] = END - timedelta(seconds=1)
        self.reject(data)
        data = fixture()
        data["jobs"][-1]["started_at"] = iso(PROVED + timedelta(seconds=1))
        self.reject(data)
        data = fixture()
        data["jobs"][-1]["completed_at"] = iso(PROVED + timedelta(seconds=30))
        self.reject(data)

    def test_exact_api_image_plane_and_project(self) -> None:
        for field, value in (
            ("image_tag", ""),
            ("image_tag", "unknown"),
            ("image_tag", None),
            ("image_tag", "b" * 40),
            ("git_sha", "b" * 40),
            ("env", "production"),
            ("supabase_project_ref", "dpadrlxukcjbewpqympu"),
        ):
            with self.subTest(field=field, value=value):
                data = fixture()
                replace_proof(
                    data, lambda proof: proof["api_fingerprint"].update({field: value})
                )
                self.reject(data)
        data = fixture()
        replace_proof(data, lambda proof: proof.update(api_fingerprint=None))
        self.reject(data)

    def test_every_portal_has_exact_health_deployment_and_project_identity(
        self,
    ) -> None:
        for portal in PROJECTS:
            for field, value in (
                ("health_build_id", None),
                ("health_build_id", "b" * 40),
                ("health_app", "other"),
                ("health_env", "production"),
                ("health_api_host", "api.vergeo5.com"),
                ("deployment_sha", "b" * 40),
                ("candidate_sha", "b" * 40),
                ("deployment_id", ""),
                ("project_id", "prj_other"),
                ("target", "production"),
                (
                    "preview_url",
                    "https://user:private@convergeo-admin-abc123-vergeo-projects.vercel.app",
                ),
            ):
                with self.subTest(portal=portal, field=field):
                    data = fixture()
                    replace_proof(
                        data,
                        lambda proof: proof["previews"][portal].update({field: value}),
                    )
                    self.reject(data)
        data = fixture()
        data["project_ids"] = {p: "prj_same" for p in PROJECTS}
        self.reject(data)
        data = fixture()
        replace_proof(
            data,
            lambda proof: proof["previews"]["vendor"].update(
                deployment_id="dpl_customer123"
            ),
        )
        self.reject(data)

    def test_archive_paths_duplicate_keys_and_extra_entries_rejected(self) -> None:
        for names in (
            ("../staging-sha-proof.json",),
            ("staging-sha-proof.json", "private.txt"),
        ):
            data = fixture()
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as archive:
                for name in names:
                    archive.writestr(name, "{}")
            data["archive"] = stream.getvalue()
            data["artifact"]["digest"] = (
                "sha256:" + hashlib.sha256(data["archive"]).hexdigest()
            )
            self.reject(data)
        data = fixture()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(
                "staging-sha-proof.json",
                '{"candidate_sha":"a","candidate_sha":"private"}',
            )
        data["archive"] = stream.getvalue()
        data["artifact"]["digest"] = (
            "sha256:" + hashlib.sha256(data["archive"]).hexdigest()
        )
        self.reject(data)

    def test_structural_metadata_errors_fail_closed(self) -> None:
        for field, value in (
            ("run", None),
            ("artifact", []),
            ("jobs", "private"),
            ("jobs", [None]),
            ("project_ids", None),
            ("now", "private"),
            ("archive", "private"),
        ):
            with self.subTest(field=field):
                data = fixture()
                data[field] = value
                self.reject(data)

    def test_positive_metadata_ignores_unrelated_prior_attempt_jobs(self) -> None:
        data = fixture()
        data["jobs"].append(
            {**data["jobs"][0], "run_attempt": 2, "conclusion": "failure"}
        )
        self.assertEqual(
            resolve_email_handoff(**data)[0],
            "https://convergeo-customer-abc123-vergeo-projects.vercel.app",
        )

    def test_cli_outputs_only_derived_public_handoff_values(self) -> None:
        import tempfile
        from email_diagnostic_handoff import main

        data = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "proof.zip").write_bytes(data["archive"])
            for name in ("run", "artifact", "jobs"):
                (root / (name + ".json")).write_text(json.dumps(data[name]))
            (root / "staging-sha.txt").write_text(SHA)
            output = root / "env"
            argv = [
                "--metadata-dir",
                directory,
                "--candidate-sha",
                SHA,
                "--run-id",
                str(RUN_ID),
                "--attempt",
                str(ATTEMPT),
                "--artifact-id",
                "777",
                "--customer-project-id",
                PROJECTS["customer"],
                "--vendor-project-id",
                PROJECTS["vendor"],
                "--admin-project-id",
                PROJECTS["admin"],
                "--github-env",
                str(output),
            ]
            main(argv, now=NOW)
            pairs = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(
                set(pairs),
                {
                    "E2E_BASE_URL",
                    "E2E_VENDOR_BASE_URL",
                    "E2E_EXPECT_SHA",
                    "E2E_SOURCE_RUN_ID",
                    "E2E_SOURCE_RUN_ATTEMPT",
                    "E2E_SOURCE_ARTIFACT_ID",
                },
            )
            self.assertEqual(pairs["E2E_EXPECT_SHA"], SHA)
            self.assertEqual(pairs["E2E_SOURCE_ARTIFACT_ID"], "777")
            (root / "run.json").write_text(
                '{"repository":"private-password private-token"}'
            )
            output.unlink()
            with self.assertRaises(SystemExit) as error:
                main(argv, now=NOW)
            self.assertEqual(str(error.exception), "EMAIL_DIAGNOSTIC_HANDOFF_REJECTED")
            self.assertFalse(output.exists())

    def test_cli_argument_failure_does_not_echo_private_arguments(self) -> None:
        from email_diagnostic_handoff import main

        with self.assertRaises(SystemExit) as error:
            main(["--unrecognized-private-password"])
        self.assertEqual(str(error.exception), "EMAIL_DIAGNOSTIC_ARGUMENTS_REJECTED")

    def test_completion_never_certifies_or_echoes_untrusted_inputs(self) -> None:
        from email_diagnostic_handoff import render_email_completion

        text = render_email_completion(
            candidate_sha="private-password",
            operation_sha=SHA,
            operation_run_id="private-token",
            operation_attempt="1",
            source_run_id="private-url",
            source_attempt="2",
            artifact_id="private-body",
            authorize_outcome="private-error",
            diagnostic_outcome="private-error",
        )
        self.assertNotIn("private", text)
        self.assertIn("Release eligible: `NO`", text)
        self.assertIn("UNKNOWN", text)
        text = render_email_completion(
            candidate_sha=SHA,
            operation_sha=SHA,
            operation_run_id=101,
            operation_attempt=1,
            source_run_id=RUN_ID,
            source_attempt=ATTEMPT,
            artifact_id=777,
            authorize_outcome="success",
            diagnostic_outcome="success",
        )
        self.assertIn("Release eligible: `NO`", text)
        self.assertIn("`901/1/777`", text)


if __name__ == "__main__":
    unittest.main()
