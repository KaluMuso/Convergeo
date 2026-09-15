"""Synthetic offline tests; these are NOT live deployment evidence."""

import copy
import hashlib
import io
import json
import sys
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from release_handoff_contract import (  # noqa: E402
    API_HOST,
    CUSTOMER_ORIGIN,
    ORCHESTRATION_WORKFLOW,
    PORTALS,
    REPOSITORY,
    REPOSITORY_ID,
    REQUIRED_JOBS,
    SMOKE_STEPS,
    STAGING_PROJECT,
    WORKFLOW,
    ContractError,
    full_sha,
    preview_origin,
    read_proof_archive,
    resolve_handoff,
    reuse_eligible,
)
from validate_staging_proof import RELEASE_PROOF_OUTCOMES  # noqa: E402

S = "a" * 40
OTHER = "a" * 12 + "b" * 28


def archive_of(proof, filename="staging-sha-proof.json"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, json.dumps(proof))
    return output.getvalue()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.proof = {
            "schema_version": 2,
            "candidate_sha": S,
            "proved_at": "2026-09-14T12:01:00Z",
            "previews": {},
            "migrate_supabase_result": "success",
            "api_fingerprint": {
                "env": "staging",
                "git_sha": S,
                "image_tag": S,
                "supabase_project_ref": STAGING_PROJECT,
            },
            "source": {
                "repository": REPOSITORY,
                "repository_id": REPOSITORY_ID,
                "workflow": WORKFLOW,
                "ref": "refs/heads/staging",
                "candidate_sha": S,
                "run_id": 10,
                "run_attempt": 2,
            },
            "configuration": {
                "identity_scheme": "operator-managed-non-secret-v1",
                "revision": "rev_fixture",
            },
            "proof_outcomes": {proof_id: "PASS" for proof_id in RELEASE_PROOF_OUTCOMES},
        }
        for portal in PORTALS:
            self.proof["previews"][portal] = {
                "candidate_sha": S,
                "deployment_sha": S,
                "deployment_id": "dpl_" + portal,
                "project_id": "prj_" + portal,
                "target": "preview",
                "health_status": "ok",
                "health_app": portal,
                "health_env": "staging",
                "health_api_host": API_HOST,
                "health_build_id": S,
                "preview_url": f"https://convergeo-{portal}-abc123-vergeo-projects.vercel.app",
                "configuration_revision": "rev_fixture",
                "checkpoint_stage": "PRE_PROBE",
                "deployment_action": "created",
                "deployment_origin_attempt": 2,
                "deployment_create_calls": 1,
                "reused_deployments": 0,
            }
        self.proof["previews"]["customer"].update(
            stable_hostname_status="verified", stable_hostname_url=CUSTOMER_ORIGIN
        )
        self.proof["deployment_efficiency"] = {
            "create_calls": 3,
            "reused_deployments": 0,
            "portals": {portal: {"action": "created", "origin_attempt": 2} for portal in PORTALS},
        }
        self.run = {
            "id": 10,
            "run_attempt": 2,
            "head_sha": S,
            "head_branch": "staging",
            "path": WORKFLOW,
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
            "head_repository": {"id": REPOSITORY_ID},
            "run_started_at": "2026-09-14T12:00:00Z",
            "updated_at": "2026-09-14T12:02:00Z",
        }
        self.artifact = {
            "id": 20,
            "name": "staging-sha-proof-10-attempt-2",
            "expired": False,
            "created_at": "2026-09-14T12:01:01Z",
            "workflow_run": {
                "id": 10,
                "head_sha": S,
                "head_branch": "staging",
                "repository_id": REPOSITORY_ID,
            },
        }
        self.live_deployments = {
            portal: {
                "id": "dpl_" + portal,
                "projectId": "prj_" + portal,
                "readyState": "READY",
                "target": None,
                "meta": {
                    "githubCommitSha": S,
                    "convergeoBuildConfigRevision": "rev_fixture",
                    "convergeoRepositoryId": str(REPOSITORY_ID),
                    "convergeoSourceRunId": "10",
                    "convergeoCreationAttempt": "2",
                },
                "url": f"convergeo-{portal}-abc123-vergeo-projects.vercel.app",
            }
            for portal in PORTALS
        }
        self.expected_project_ids = {portal: "prj_" + portal for portal in PORTALS}
        self.jobs = [
            {
                "name": name,
                "run_id": 10,
                "run_attempt": 2,
                "started_at": "2026-09-14T12:00:30Z",
                "completed_at": "2026-09-14T12:01:30Z",
                "head_sha": S,
                "status": "completed",
                "conclusion": "success",
                "steps": [
                    {"name": step, "status": "completed", "conclusion": "success"}
                    for step in SMOKE_STEPS
                ]
                if name == "Staging smoke + evidence"
                else [],
            }
            for name in REQUIRED_JOBS
        ]
        self.kwargs = dict(
            expected_sha=S,
            current_staging_sha=S,
            expected_run_id=10,
            expected_attempt=2,
            configuration_revision="rev_fixture",
            max_age_seconds=3600,
            now=datetime(2026, 9, 14, 12, 3, tzinfo=UTC),
        )

    def resolve(self):
        archive = archive_of(self.proof)
        self.artifact["digest"] = "sha256:" + hashlib.sha256(archive).hexdigest()
        return resolve_handoff(
            archive,
            run=self.run,
            artifact=self.artifact,
            jobs=self.jobs,
            live_deployments=self.live_deployments,
            expected_project_ids=self.expected_project_ids,
            **self.kwargs,
        )

    def fails(self, code):
        with self.assertRaisesRegex(ContractError, "^" + code + "$"):
            self.resolve()

    def test_valid_proof_resolves_existing_dispatch_fields(self):
        h = self.resolve()
        inputs = h.diagnostic_inputs("vendor-auth")
        self.assertEqual(inputs["base_url"], CUSTOMER_ORIGIN)
        self.assertEqual(inputs["expect_sha"], S)
        self.assertIs(inputs["pre_release"], False)
        self.assertEqual(inputs["source_run_id"], 10)
        self.assertEqual(inputs["deployment_create_calls"], 3)
        self.assertEqual(inputs["reused_deployments"], 0)
        self.assertIn("STILL REQUIRED", h.summary())
        self.assertIn("not a browser-test result", h.summary())

    def test_full_suite_cannot_be_smuggled_in_as_diagnostic(self):
        with self.assertRaises(ContractError):
            self.resolve().diagnostic_inputs("full")

    def test_staging_advanced(self):
        self.kwargs["current_staging_sha"] = OTHER
        self.fails("STAGING_MOVED")

    def test_same_prefix_wrong_sha_rejected(self):
        self.proof["previews"]["vendor"]["health_build_id"] = OTHER
        self.fails("HEALTH_SHA_MISMATCH")

    def test_missing_health_sha_rejected(self):
        self.proof["previews"]["vendor"].pop("health_build_id")
        self.fails("INVALID_FULL_SHA")

    def test_candidate_requires_exact_full_hash(self):
        for bad in ("a", "a" * 7, "a" * 12, "a" * 41, "z" * 40, None, S + "\n"):
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                full_sha(bad)

    def test_untrusted_repo_rejected(self):
        self.run["repository"]["id"] = 1
        self.fails("WRONG_REPOSITORY")

    def test_fork_head_rejected(self):
        self.run["head_repository"]["id"] = 1
        self.fails("WRONG_REPOSITORY")

    def test_wrong_workflow_rejected(self):
        self.run["path"] = ".github/workflows/ci.yml"
        self.fails("UNTRUSTED_WORKFLOW_REF")

    def test_wrong_branch_rejected(self):
        self.run["head_branch"] = "feature/test"
        self.fails("UNTRUSTED_WORKFLOW_REF")

    def test_untrusted_event_rejected(self):
        self.run["event"] = "pull_request"
        self.fails("UNTRUSTED_EVENT")

    def test_failed_run_rejected(self):
        self.run["conclusion"] = "failure"
        self.fails("RUN_NOT_SUCCESSFUL")

    def test_wrong_run_attempt_rejected(self):
        self.run["run_attempt"] = 1
        self.fails("RUN_ATTEMPT_MISMATCH")

    def test_previous_attempt_artifact_not_reused_as_final_manifest(self):
        self.artifact["created_at"] = "2026-09-14T11:55:00Z"
        self.fails("ARTIFACT_ATTEMPT_NOT_BOUND")

    def test_previous_attempt_artifact_name_is_rejected_before_opening(self):
        self.artifact["name"] = "staging-sha-proof-10-attempt-1"
        self.fails("WRONG_ARTIFACT_KIND")

    def test_previous_successful_dependencies_can_be_reused(self):
        self.jobs[0]["run_attempt"] = 1
        self.assertEqual(self.resolve().source_attempt, 2)

    def test_current_failed_dependency_cannot_fall_back_to_old_success(self):
        previous = copy.deepcopy(self.jobs[0])
        previous["run_attempt"] = 1
        self.jobs[0]["conclusion"] = "failure"
        self.jobs.append(previous)
        self.fails("JOB_NOT_SUCCESSFUL")

    def test_final_smoke_must_be_current_attempt(self):
        self.jobs[-1]["run_attempt"] = 1
        self.fails("SMOKE_NOT_CURRENT_ATTEMPT")

    def test_proof_before_current_smoke_rejected_even_with_old_run_start(self):
        self.run["run_started_at"] = "2026-09-14T11:00:00Z"
        self.proof["proved_at"] = "2026-09-14T11:59:00Z"
        self.fails("PROOF_ATTEMPT_NOT_BOUND")

    def test_missing_job_attempt_is_not_provenance(self):
        self.jobs[0].pop("run_attempt")
        self.fails("JOB_ATTEMPT_UNBOUND")

    def test_artifact_other_run_rejected(self):
        self.artifact["workflow_run"]["id"] = 11
        self.fails("ARTIFACT_PROVENANCE_MISMATCH")

    def test_expired_artifact_rejected(self):
        self.artifact["expired"] = True
        self.fails("ARTIFACT_EXPIRED_OR_UNKNOWN")

    def test_stale_proof_rejected(self):
        self.kwargs["max_age_seconds"] = 10
        self.fails("STALE_OR_FUTURE_PROOF")

    def test_future_proof_rejected(self):
        self.proof["proved_at"] = "2026-09-14T13:00:00Z"
        self.fails("STALE_OR_FUTURE_PROOF")

    def test_missing_portal_rejected(self):
        self.proof["previews"].pop("admin")
        self.fails("INCOMPLETE_PORTAL_SET")

    def test_cross_site_customer_disallowed(self):
        self.proof["previews"]["customer"]["stable_hostname_url"] = "https://other.vercel.app"
        self.fails("SAMESITE_CUSTOMER_NOT_PROVEN")

    def test_missing_deployment_identity(self):
        self.proof["previews"]["vendor"].pop("deployment_id")
        self.fails("MISSING_DEPLOYMENT_ID")

    def test_mixed_backend_sha(self):
        self.proof["api_fingerprint"]["git_sha"] = OTHER
        self.fails("API_FINGERPRINT_MISMATCH")

    def test_api_image_tag_required(self):
        self.proof["api_fingerprint"].pop("image_tag")
        self.fails("API_FINGERPRINT_MISMATCH")

    def test_production_database_forbidden(self):
        self.proof["api_fingerprint"]["supabase_project_ref"] = "dpadrlxukcjbewpqympu"
        self.fails("API_FINGERPRINT_MISMATCH")

    def test_skipped_migration_not_certified(self):
        self.proof["migrate_supabase_result"] = "skipped"
        self.fails("MIGRATIONS_NOT_PROVEN")

    def test_missing_job_not_treated_as_success(self):
        self.jobs.pop()
        self.fails("MISSING_OR_AMBIGUOUS_JOB")

    def test_failed_or_skipped_step_not_treated_as_success(self):
        for result in ("failure", "skipped", "cancelled", None):
            with self.subTest(result=result):
                self.jobs[-1]["steps"][0]["conclusion"] = result
                self.fails("SMOKE_STEP_NOT_EXECUTED_SUCCESSFULLY")

    def test_other_run_job_not_accepted(self):
        self.jobs[0]["run_id"] = 99
        self.fails("JOB_PROVENANCE_MISMATCH")

    def test_unsafe_urls_and_secret_values_never_echoed(self):
        for value in (
            "http://convergeo-vendor-abc-vergeo-projects.vercel.app",
            "https://secret:secret@convergeo-vendor-abc-vergeo-projects.vercel.app",
            "https://convergeo-vendor-abc-vergeo-projects.vercel.app/?token=SECRET",
            "https://convergeo-vendor-abc-vergeo-projects.vercel.app.attacker.test",
            "https://convergeo-vendor-git-staging-vergeo-projects.vercel.app",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ContractError) as caught:
                    preview_origin("vendor", value)
                self.assertNotIn("secret", str(caught.exception).lower())

    def test_checksum_mismatch_rejected(self):
        archive = archive_of(self.proof)
        self.artifact["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ContractError, "ARTIFACT_DIGEST_MISMATCH"):
            read_proof_archive(
                archive,
                self.artifact,
                expected_name="staging-sha-proof-10-attempt-2",
            )

    def test_path_traversal_rejected_without_extraction(self):
        archive = archive_of(self.proof, "../staging-sha-proof.json")
        self.artifact["digest"] = "sha256:" + hashlib.sha256(archive).hexdigest()
        with self.assertRaisesRegex(ContractError, "UNEXPECTED_ARCHIVE_PATH"):
            read_proof_archive(
                archive,
                self.artifact,
                expected_name="staging-sha-proof-10-attempt-2",
            )

    def test_duplicate_json_fields_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("staging-sha-proof.json", '{"a":1,"a":2}')
        self.artifact["digest"] = "sha256:" + hashlib.sha256(buf.getvalue()).hexdigest()
        with self.assertRaisesRegex(ContractError, "DUPLICATE_JSON_KEY"):
            read_proof_archive(
                buf.getvalue(),
                self.artifact,
                expected_name="staging-sha-proof-10-attempt-2",
            )

    def test_full_scope_derives_certification_inputs(self):
        inputs = self.resolve().workflow_inputs("full")
        self.assertIs(inputs["pre_release"], True)
        self.assertEqual(inputs["source_run_attempt"], 2)
        self.assertEqual(inputs["source_artifact_id"], 20)

    def test_legacy_manifest_cannot_supply_e2e(self):
        self.proof["schema_version"] = 1
        self.fails("RELEASE_MANIFEST_INVALID")

    def test_configuration_revision_must_match_current_identity(self):
        self.kwargs["configuration_revision"] = "rev_other"
        self.fails("RELEASE_MANIFEST_INVALID")

    def test_non_pass_manifest_outcomes_are_rejected(self):
        for outcome in ("FAIL", "NOT_RUN", "SKIPPED_APPROVED", "UNKNOWN"):
            with self.subTest(outcome=outcome):
                self.proof["proof_outcomes"]["cors"] = outcome
                self.fails("RELEASE_MANIFEST_INVALID")

    def test_efficiency_counts_are_exposed_only_after_exact_validation(self):
        self.proof["previews"]["admin"]["deployment_action"] = "reused"
        self.proof["previews"]["admin"]["deployment_create_calls"] = 0
        self.proof["previews"]["admin"]["reused_deployments"] = 1
        self.proof["deployment_efficiency"] = {
            "create_calls": 2,
            "reused_deployments": 1,
            "portals": {
                portal: {
                    "action": row["deployment_action"],
                    "origin_attempt": row["deployment_origin_attempt"],
                }
                for portal, row in self.proof["previews"].items()
            },
        }
        handoff = self.resolve()
        self.assertEqual(handoff.deployment_create_calls, 2)
        self.assertEqual(handoff.reused_deployments, 1)

    def test_efficiency_count_tampering_fails_closed(self):
        self.proof["deployment_efficiency"]["create_calls"] = 2
        self.fails("RELEASE_MANIFEST_INVALID")

    def test_live_vercel_project_deployment_sha_url_state_and_target_are_bound(self):
        cases = (
            ("projectId", "prj_other", "VERCEL_PROJECT_MISMATCH"),
            ("id", "dpl_other", "VERCEL_DEPLOYMENT_MISMATCH"),
            ("readyState", "BUILDING", "VERCEL_DEPLOYMENT_NOT_READY"),
            ("target", "production", "VERCEL_TARGET_MISMATCH"),
            ("meta", {"githubCommitSha": OTHER}, "VERCEL_SHA_MISMATCH"),
            ("url", "convergeo-vendor-other-vergeo-projects.vercel.app", "VERCEL_URL_MISMATCH"),
        )
        for field, value, code in cases:
            with self.subTest(field=field):
                original = copy.deepcopy(self.live_deployments["vendor"])
                self.live_deployments["vendor"][field] = value
                self.fails(code)
                self.live_deployments["vendor"] = original

    def test_manifest_project_must_match_expected_project(self):
        self.proof["previews"]["admin"]["project_id"] = "prj_other"
        self.fails("VERCEL_PROJECT_MISMATCH")

    def test_live_vercel_configuration_and_producer_are_bound(self):
        meta = self.live_deployments["admin"]["meta"]
        cases = (
            ("convergeoBuildConfigRevision", "stale", "VERCEL_CONFIGURATION_MISMATCH"),
            ("convergeoRepositoryId", "999", "VERCEL_PRODUCER_MISMATCH"),
            ("convergeoSourceRunId", "11", "VERCEL_PRODUCER_MISMATCH"),
            ("convergeoCreationAttempt", "1", "VERCEL_PRODUCER_MISMATCH"),
        )
        for field, value, code in cases:
            with self.subTest(field=field):
                original = meta[field]
                meta[field] = value
                self.fails(code)
                meta[field] = original

    def test_reusable_workflow_job_prefixes_remain_unambiguous(self):
        self.run["path"] = ORCHESTRATION_WORKFLOW
        self.proof["source"]["workflow"] = ORCHESTRATION_WORKFLOW
        for job in self.jobs:
            job["name"] = "deploy / " + job["name"]
        self.assertEqual(self.resolve().candidate_sha, S)

    def test_in_progress_trusted_outer_operation_can_handoff_after_smoke(self):
        self.run["path"] = ORCHESTRATION_WORKFLOW
        self.run["status"] = "in_progress"
        self.run["conclusion"] = None
        self.proof["source"]["workflow"] = ORCHESTRATION_WORKFLOW
        self.assertEqual(self.resolve().candidate_sha, S)

    def test_cancelled_or_pending_job_is_not_success(self):
        cases = (("completed", "cancelled"), ("queued", None), ("in_progress", None))
        for status, conclusion in cases:
            with self.subTest(status=status, conclusion=conclusion):
                self.jobs[0]["status"] = status
                self.jobs[0]["conclusion"] = conclusion
                self.fails("JOB_NOT_SUCCESSFUL")

    def test_manifest_rejection_never_echoes_untrusted_value(self):
        marker = "SECRET_MARKER_DO_NOT_LOG"
        self.proof["configuration"]["revision"] = marker
        with self.assertRaises(ContractError) as caught:
            self.resolve()
        self.assertEqual(str(caught.exception), "RELEASE_MANIFEST_INVALID")
        self.assertNotIn(marker, str(caught.exception))


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.receipt = dict(
            candidate_sha=S,
            project_id="prj_fixture",
            deployment_id="dpl_fixture",
            build_config_revision="rev_fixture",
        )
        self.live = dict(
            id="dpl_fixture",
            projectId="prj_fixture",
            readyState="READY",
            target="preview",
            meta={"githubCommitSha": S},
            build_config_revision="rev_fixture",
        )
        self.kw = dict(candidate_sha=S, project_id="prj_fixture", config_revision="rev_fixture")

    def test_eligible_means_reprobe_not_accept(self):
        self.assertTrue(reuse_eligible(self.receipt, self.live, **self.kw))

    def test_absent_configuration_revision_forbids_reuse(self):
        self.kw["config_revision"] = ""
        self.assertFalse(reuse_eligible(self.receipt, self.live, **self.kw))

    def test_changed_configuration_forbids_reuse(self):
        self.live["build_config_revision"] = "changed"
        self.assertFalse(reuse_eligible(self.receipt, self.live, **self.kw))

    def test_wrong_sha_project_state_target_or_id_forbids_reuse(self):
        for key, value in (
            ("projectId", "prj_other"),
            ("id", "dpl_other"),
            ("readyState", "BUILDING"),
            ("target", "production"),
            ("meta", {"githubCommitSha": OTHER}),
        ):
            with self.subTest(key=key):
                live = copy.deepcopy(self.live)
                live[key] = value
                self.assertFalse(reuse_eligible(self.receipt, live, **self.kw))


if __name__ == "__main__":
    unittest.main()
