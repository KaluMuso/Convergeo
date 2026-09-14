"""Offline contract tests; these are not live Vercel or release evidence."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

from vercel_deployment_checkpoint import (  # noqa: E402
    EVIDENCE_KIND,
    REPOSITORY,
    REPOSITORY_ID,
    STAGE,
    WORKFLOW,
    CheckpointError,
    _write_json_exclusive,
    assess_reuse,
    checkpoint_artifact_name,
    create_decision,
    make_checkpoint,
    parse_checkpoint,
    read_checkpoint_archive,
    select_reuse,
)

SHA = "a" * 40
OTHER_SHA = "a" * 12 + "b" * 28
RUN_ID = 700
SOURCE_ATTEMPT = 1
CURRENT_ATTEMPT = 2
PORTAL = "customer"
PROJECT_ID = "prj_customer"
DEPLOYMENT_ID = "dpl_customer"
CONFIG_REVISION = "staging-config-42"
GENERATED_AT = "2026-09-14T12:00:10Z"


def archive_of(checkpoint: dict, name: str = "deployment-checkpoint.json") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(name, json.dumps(checkpoint))
    return output.getvalue()


def live_metadata(**changes):
    value = {
        "id": DEPLOYMENT_ID,
        "projectId": PROJECT_ID,
        "target": None,
        "readyState": "READY",
        "url": "convergeo-customer-fixture-vergeo-projects.vercel.app",
        "meta": {
            "githubCommitSha": SHA,
            "convergeoBuildConfigRevision": CONFIG_REVISION,
            "convergeoRepositoryId": str(REPOSITORY_ID),
            "convergeoSourceRunId": str(RUN_ID),
            "convergeoCreationAttempt": str(SOURCE_ATTEMPT),
        },
    }
    value.update(changes)
    return value


class CheckpointFixture(unittest.TestCase):
    def setUp(self):
        self.checkpoint = make_checkpoint(
            portal=PORTAL,
            project_id=PROJECT_ID,
            deployment_id=DEPLOYMENT_ID,
            candidate_sha=SHA,
            configuration_revision=CONFIG_REVISION,
            run_id=RUN_ID,
            run_attempt=SOURCE_ATTEMPT,
            action="created",
            creation_attempt=SOURCE_ATTEMPT,
            generated_at=GENERATED_AT,
        )
        self.archive = archive_of(self.checkpoint)
        self.artifact = {
            "id": 900,
            "name": checkpoint_artifact_name(PORTAL, RUN_ID, SOURCE_ATTEMPT),
            "expired": False,
            "size_in_bytes": len(self.archive),
            "digest": "sha256:" + hashlib.sha256(self.archive).hexdigest(),
            "created_at": "2026-09-14T12:00:12Z",
            "workflow_run": {
                "id": RUN_ID,
                "head_sha": SHA,
                "head_branch": "staging",
                "repository": REPOSITORY,
                "repository_id": REPOSITORY_ID,
                "path": WORKFLOW,
            },
            "source_job": {
                "id": 901,
                "name": "Vercel Preview proof (customer)",
                "run_attempt": SOURCE_ATTEMPT,
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2026-09-14T12:00:00Z",
                "completed_at": "2026-09-14T12:01:00Z",
            },
        }

    def select(self, *, live=None, **changes):
        kwargs = {
            "archive": self.archive,
            "artifact": self.artifact,
            "portal": PORTAL,
            "project_id": PROJECT_ID,
            "candidate_sha": SHA,
            "configuration_revision": CONFIG_REVISION,
            "run_id": RUN_ID,
            "current_attempt": CURRENT_ATTEMPT,
            "source_attempt": SOURCE_ATTEMPT,
            "live_reader": lambda _deployment_id: live or live_metadata(),
        }
        kwargs.update(changes)
        return select_reuse(**kwargs)


class CheckpointCreationTests(CheckpointFixture):
    def test_checkpoint_is_explicitly_pre_probe_not_a_certificate(self):
        self.assertEqual(self.checkpoint["stage"], STAGE)
        self.assertEqual(self.checkpoint["evidence_kind"], EVIDENCE_KIND)
        self.assertIs(self.checkpoint["certification_evidence"], False)
        self.assertNotIn("health", self.checkpoint)
        self.assertNotIn("stable_hostname_status", self.checkpoint)

    def test_created_and_reused_counts_are_mutually_exclusive(self):
        created = create_decision("CHECKPOINT_MISSING", CURRENT_ATTEMPT)
        reused = self.select()
        self.assertEqual((created.deployment_create_calls, created.reused_deployments), (1, 0))
        self.assertEqual((reused.deployment_create_calls, reused.reused_deployments), (0, 1))

    def test_first_attempt_without_checkpoint_creates(self):
        decision = select_reuse(
            archive=None,
            artifact=None,
            portal=PORTAL,
            project_id=PROJECT_ID,
            candidate_sha=SHA,
            configuration_revision=CONFIG_REVISION,
            run_id=RUN_ID,
            current_attempt=SOURCE_ATTEMPT,
            source_attempt=None,
            live_reader=lambda _deployment_id: self.fail("provider must not be read"),
        )
        self.assertEqual(decision.decision, "create")
        self.assertEqual(decision.reason, "CHECKPOINT_MISSING")

    def test_rerun_artifact_names_are_attempt_scoped(self):
        first = checkpoint_artifact_name(PORTAL, RUN_ID, 1)
        second = checkpoint_artifact_name(PORTAL, RUN_ID, 2)
        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("-attempt-1"))
        self.assertTrue(second.endswith("-attempt-2"))

    def test_output_collision_is_fatal_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "selection.json"
            _write_json_exclusive(output, {"decision": "create"})
            with self.assertRaisesRegex(CheckpointError, "^CHECKPOINT_OUTPUT_COLLISION$"):
                _write_json_exclusive(output, {"decision": "reuse"})


class CheckpointTransportTests(CheckpointFixture):
    def test_failed_source_job_can_transport_pre_probe_checkpoint(self):
        checkpoint = read_checkpoint_archive(
            self.archive,
            self.artifact,
            portal=PORTAL,
            run_id=RUN_ID,
            source_attempt=SOURCE_ATTEMPT,
            candidate_sha=SHA,
        )
        self.assertEqual(checkpoint.deployment_id, DEPLOYMENT_ID)

    def test_interrupted_creation_can_reuse_building_deployment(self):
        decision = self.select(live=live_metadata(readyState="BUILDING"))
        self.assertEqual(decision.decision, "reuse")
        self.assertEqual(decision.origin_attempt, SOURCE_ATTEMPT)

    def test_artifact_tampering_is_fatal_not_a_create_fallback(self):
        self.artifact["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(CheckpointError, "^ARTIFACT_DIGEST_MISMATCH$"):
            self.select()

    def test_duplicate_json_keys_are_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr(
                "deployment-checkpoint.json",
                '{"schema_version":1,"schema_version":2}',
            )
        self.archive = output.getvalue()
        self.artifact["size_in_bytes"] = len(self.archive)
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.archive).hexdigest()
        with self.assertRaisesRegex(CheckpointError, "^DUPLICATE_JSON_KEY$"):
            self.select()

    def test_path_traversal_entry_is_rejected_without_extraction(self):
        self.archive = archive_of(self.checkpoint, "../deployment-checkpoint.json")
        self.artifact["size_in_bytes"] = len(self.archive)
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.archive).hexdigest()
        with self.assertRaisesRegex(CheckpointError, "^UNEXPECTED_ARCHIVE_PATH$"):
            self.select()

    def test_wrong_producer_repository_is_fatal(self):
        self.checkpoint["producer"]["repository_id"] = 1
        self.archive = archive_of(self.checkpoint)
        self.artifact["size_in_bytes"] = len(self.archive)
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.archive).hexdigest()
        with self.assertRaisesRegex(CheckpointError, "^UNTRUSTED_CHECKPOINT_PRODUCER$"):
            self.select()

    def test_artifact_must_be_bound_to_exact_attempt_job_window(self):
        self.artifact["created_at"] = "2026-09-14T12:02:00Z"
        with self.assertRaisesRegex(CheckpointError, "^ARTIFACT_ATTEMPT_NOT_BOUND$"):
            self.select()

    def test_artifact_name_collision_or_wrong_attempt_is_rejected(self):
        self.artifact["name"] = checkpoint_artifact_name(PORTAL, RUN_ID, 2)
        with self.assertRaisesRegex(CheckpointError, "^WRONG_ARTIFACT_KIND$"):
            self.select()


class ReuseEligibilityTests(CheckpointFixture):
    def test_complete_binding_allows_only_a_fresh_reprobe(self):
        decision = self.select()
        self.assertEqual(decision.decision, "reuse")
        self.assertEqual(decision.reason, "ELIGIBLE_REPROBE")
        self.assertEqual(decision.deployment_id, DEPLOYMENT_ID)

    def test_stale_configuration_creates_without_provider_read(self):
        read = False

        def live_reader(_deployment_id):
            nonlocal read
            read = True
            return live_metadata()

        decision = select_reuse(
            archive=self.archive,
            artifact=self.artifact,
            portal=PORTAL,
            project_id=PROJECT_ID,
            candidate_sha=SHA,
            configuration_revision="staging-config-43",
            run_id=RUN_ID,
            current_attempt=CURRENT_ATTEMPT,
            source_attempt=SOURCE_ATTEMPT,
            live_reader=live_reader,
        )
        self.assertEqual(decision.reason, "CHECKPOINT_CONFIGURATION_MISMATCH")
        self.assertFalse(read)

    def test_wrong_checkpoint_project_or_sha_creates(self):
        cases = (
            ("project_id", "prj_other", "CHECKPOINT_PROJECT_MISMATCH"),
            ("candidate_sha", OTHER_SHA, "CHECKPOINT_SHA_MISMATCH"),
        )
        for field, value, reason in cases:
            with self.subTest(field=field):
                checkpoint = copy.deepcopy(self.checkpoint)
                checkpoint[field] = value
                self.archive = archive_of(checkpoint)
                self.artifact["size_in_bytes"] = len(self.archive)
                self.artifact["digest"] = "sha256:" + hashlib.sha256(self.archive).hexdigest()
                decision = self.select()
                self.assertEqual(decision.reason, reason)

    def test_live_project_sha_target_config_and_repository_are_bound(self):
        cases = (
            ({"projectId": "prj_other"}, "LIVE_PROJECT_MISMATCH"),
            ({"target": "production"}, "LIVE_TARGET_MISMATCH"),
            ({"readyState": "ERROR"}, "LIVE_STATE_INELIGIBLE"),
            (
                {"meta": {**live_metadata()["meta"], "githubCommitSha": OTHER_SHA}},
                "LIVE_SHA_MISMATCH",
            ),
            (
                {
                    "meta": {
                        **live_metadata()["meta"],
                        "convergeoBuildConfigRevision": "staging-config-41",
                    }
                },
                "LIVE_CONFIGURATION_MISMATCH",
            ),
            (
                {
                    "meta": {
                        **live_metadata()["meta"],
                        "convergeoRepositoryId": "1",
                    }
                },
                "LIVE_REPOSITORY_MISMATCH",
            ),
        )
        checkpoint = parse_checkpoint(
            self.checkpoint,
            expected_run_id=RUN_ID,
            expected_producer_attempt=SOURCE_ATTEMPT,
        )
        for change, reason in cases:
            with self.subTest(reason=reason):
                decision = assess_reuse(
                    checkpoint,
                    live_metadata(**change),
                    portal=PORTAL,
                    project_id=PROJECT_ID,
                    candidate_sha=SHA,
                    configuration_revision=CONFIG_REVISION,
                    run_id=RUN_ID,
                    current_attempt=CURRENT_ATTEMPT,
                )
                self.assertEqual(decision.decision, "create")
                self.assertEqual(decision.reason, reason)

    def test_mutable_alias_is_never_carried_forward(self):
        decision = self.select()
        self.assertEqual(decision.reason, "ELIGIBLE_REPROBE")
        self.assertFalse(hasattr(decision, "stable_hostname_status"))
        self.assertFalse(hasattr(decision, "health_verdict"))

    def test_missing_checkpoint_and_unavailable_provider_are_different(self):
        missing = select_reuse(
            archive=None,
            artifact=None,
            portal=PORTAL,
            project_id=PROJECT_ID,
            candidate_sha=SHA,
            configuration_revision=CONFIG_REVISION,
            run_id=RUN_ID,
            current_attempt=CURRENT_ATTEMPT,
            source_attempt=None,
            live_reader=lambda _deployment_id: {},
        )
        self.assertEqual(missing.reason, "CHECKPOINT_MISSING")
        with self.assertRaisesRegex(CheckpointError, "^VERCEL_METADATA_UNAVAILABLE$"):
            self.select(
                live=None,
                live_reader=lambda _deployment_id: (_ for _ in ()).throw(
                    CheckpointError("VERCEL_METADATA_UNAVAILABLE")
                ),
            )


class WorkflowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (REPO_ROOT / ".github/workflows/deploy-staging.yml").read_text(
            encoding="utf-8"
        )
        cls.prove = (REPO_ROOT / "scripts/ci/vercel-staging-preview-prove.sh").read_text(
            encoding="utf-8"
        )

    def test_checkpoint_upload_precedes_every_fresh_probe(self):
        prepare = self.workflow.index("- name: Create or recover Preview checkpoint")
        upload = self.workflow.index("- name: Upload PRE_PROBE checkpoint")
        prove = self.workflow.index(
            "- name: Re-probe immutable Preview and mutable Customer hostname"
        )
        self.assertLess(prepare, upload)
        self.assertLess(upload, prove)

    def test_all_rerun_artifacts_owned_by_this_path_are_attempt_scoped(self):
        expected = (
            "staging-preview-checkpoint-${{ matrix.portal }}-"
            "${{ github.run_id }}-attempt-${{ github.run_attempt }}",
            "staging-preview-evidence-${{ matrix.portal }}-"
            "${{ github.run_id }}-attempt-${{ github.run_attempt }}",
            "staging-sha-proof-${{ github.run_id }}-attempt-${{ github.run_attempt }}",
            "staging-smoke-evidence-${{ github.run_id }}-attempt-${{ github.run_attempt }}",
        )
        for name in expected:
            with self.subTest(name=name):
                self.assertIn(name, self.workflow)

    def test_create_is_sha_pinned_and_embeds_independent_config_identity(self):
        self.assertIn('"ref": os.environ["GITHUB_REF_NAME"]', self.prove)
        self.assertIn('"sha": os.environ["GITHUB_SHA"]', self.prove)
        self.assertIn("convergeoBuildConfigRevision", self.prove)
        self.assertIn("convergeoRepositoryId", self.prove)
        self.assertIn("convergeoSourceRunId", self.prove)
        self.assertIn("convergeoCreationAttempt", self.prove)

    def test_reuse_still_runs_immutable_and_mutable_health_probes(self):
        self.assertIn("checkpoint validated; re-probing deployment", self.prove)
        self.assertIn("vercel_preview_health_verify.py", self.prove)
        self.assertIn('prove_stable_hostname_health "${stable_hostname}"', self.prove)
        self.assertNotIn("checkpoint_health_verdict", self.prove)

    def test_prior_artifact_transport_verifies_digest_and_job_window(self):
        self.assertIn("checkpoint artifact digest mismatch", self.workflow)
        self.assertIn("checkpoint artifact falls outside its producer job window", self.workflow)
        self.assertIn("ambiguous prior-attempt checkpoint artifact", self.workflow)

    def test_create_and_reuse_counts_are_published_without_claiming_pass(self):
        self.assertIn("Deployment-create calls", self.workflow)
        self.assertIn("Reused deployments", self.workflow)
        self.assertIn("Checkpoint stage", self.workflow)
        self.assertIn("not certification evidence", self.workflow)


if __name__ == "__main__":
    unittest.main()
