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


if __name__ == "__main__":
    unittest.main()
