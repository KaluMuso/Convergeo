"""Offline producer/consumer tests for protected-operation certification."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

from emit_staging_certification_evidence import main as emit_evidence  # noqa: E402
from github_actions_provenance import (  # noqa: E402
    GitHubActionsClient,
    WorkflowRunsPage,
)
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
)
from staging_operation_certification import (  # noqa: E402
    CERTIFICATION_JOB,
    CERTIFICATION_STEPS,
    COMPLETION_JOB,
    E2E_JOB,
    E2E_STEPS,
    HANDOFF_JOB,
    HANDOFF_STEPS,
    operation_certification_artifact_name,
)
from validate_staging_proof import RELEASE_PROOF_OUTCOMES  # noqa: E402
from verify_staging_certification_gate import (  # noqa: E402
    FixtureGitHubActionsClient,
    MergeGateError,
    verify_staging_certification_gate,
)

SHA = "e" * 40
OTHER_SHA = "d" * 40
RUN_ID = 333333333
ATTEMPT = 2
SOURCE_ARTIFACT_ID = 9101
CERTIFICATION_ARTIFACT_ID = 9102


def _artifact_zip(filename: str, value: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, json.dumps(value))
    return buffer.getvalue()


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _successful_steps(names: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in names
    ]


def _workflow(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.load(
            (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        ),
    )


class OperationFixtureClient:
    def __init__(
        self,
        *,
        run_id: int = RUN_ID,
        attempt: int = ATTEMPT,
        source_artifact_id: int = SOURCE_ARTIFACT_ID,
        certification_artifact_id: int = CERTIFICATION_ARTIFACT_ID,
    ) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        self.now = now
        self.run_id = run_id
        self.attempt = attempt
        self.source_artifact_id = source_artifact_id
        self.certification_artifact_id = certification_artifact_id
        self.total_count = 1
        self.run: dict[str, Any] = {
            "id": run_id,
            "run_attempt": attempt,
            "status": "completed",
            "conclusion": "success",
            "head_sha": SHA,
            "head_branch": "staging",
            "event": "push",
            "path": ORCHESTRATION_WORKFLOW,
            "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
            "head_repository": {"id": REPOSITORY_ID},
            "created_at": _iso(now - timedelta(minutes=20)),
            "run_started_at": _iso(now - timedelta(minutes=20)),
            "updated_at": _iso(now),
        }
        self.proof: dict[str, Any] = {
            "schema_version": 2,
            "candidate_sha": SHA,
            "proved_at": _iso(now - timedelta(minutes=8)),
            "previews": {},
            "migrate_supabase_result": "success",
            "api_fingerprint": {
                "env": "staging",
                "git_sha": SHA,
                "image_tag": SHA,
                "supabase_project_ref": STAGING_PROJECT,
            },
            "source": {
                "repository": REPOSITORY,
                "repository_id": REPOSITORY_ID,
                "workflow": ORCHESTRATION_WORKFLOW,
                "ref": "refs/heads/staging",
                "candidate_sha": SHA,
                "run_id": run_id,
                "run_attempt": attempt,
            },
            "configuration": {
                "identity_scheme": "operator-managed-non-secret-v1",
                "revision": "rev_fixture",
            },
            "proof_outcomes": {
                proof_id: "PASS" for proof_id in RELEASE_PROOF_OUTCOMES
            },
        }
        for portal in PORTALS:
            self.proof["previews"][portal] = {
                "candidate_sha": SHA,
                "deployment_sha": SHA,
                "deployment_id": f"dpl_{portal}",
                "project_id": f"prj_{portal}",
                "target": "preview",
                "health_status": "ok",
                "health_app": portal,
                "health_env": "staging",
                "health_api_host": API_HOST,
                "health_build_id": SHA,
                "preview_url": (
                    f"https://convergeo-{portal}-abc123-vergeo-projects.vercel.app"
                ),
                "configuration_revision": "rev_fixture",
                "checkpoint_stage": "PRE_PROBE",
                "deployment_action": "created",
                "deployment_origin_attempt": attempt,
                "deployment_create_calls": 1,
                "reused_deployments": 0,
            }
        self.proof["previews"]["customer"].update(
            stable_hostname_status="verified",
            stable_hostname_url=CUSTOMER_ORIGIN,
        )
        self.proof["deployment_efficiency"] = {
            "create_calls": 3,
            "reused_deployments": 0,
            "portals": {
                portal: {"action": "created", "origin_attempt": attempt}
                for portal in PORTALS
            },
        }
        self.source_archive = _artifact_zip("staging-sha-proof.json", self.proof)
        self.source_artifact: dict[str, Any] = {
            "id": source_artifact_id,
            "name": f"staging-sha-proof-{run_id}-attempt-{attempt}",
            "workflow_run_id": run_id,
            "expired": False,
            "digest": "sha256:" + hashlib.sha256(self.source_archive).hexdigest(),
            "size_in_bytes": len(self.source_archive),
            "created_at": _iso(now - timedelta(minutes=8)),
            "workflow_run": {
                "id": run_id,
                "head_sha": SHA,
                "head_branch": "staging",
                "repository_id": REPOSITORY_ID,
            },
        }
        self.jobs = self._jobs()
        self.evidence: dict[str, Any] = {}
        self.certification_archive = b""
        self.certification_artifact: dict[str, Any] = {}
        self.artifacts = [self.source_artifact]

    def _job(
        self,
        name: str,
        steps: tuple[str, ...],
        *,
        started: datetime,
        completed: datetime,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "run_id": self.run_id,
            "run_attempt": self.attempt,
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "started_at": _iso(started),
            "completed_at": _iso(completed),
            "steps": _successful_steps(steps),
        }

    def _jobs(self) -> list[dict[str, Any]]:
        smoke_start = self.now - timedelta(minutes=10)
        smoke_end = self.now - timedelta(minutes=7)
        jobs = [
            self._job(
                name,
                SMOKE_STEPS if name == "Staging smoke + evidence" else (),
                started=smoke_start,
                completed=smoke_end,
            )
            for name in REQUIRED_JOBS
        ]
        jobs.extend(
            [
                self._job(
                    "Authorize protected staging graph",
                    ("Bind repository, ref and full candidate",),
                    started=self.now - timedelta(minutes=20),
                    completed=self.now - timedelta(minutes=19),
                ),
                self._job(
                    HANDOFF_JOB,
                    HANDOFF_STEPS,
                    started=self.now - timedelta(minutes=7),
                    completed=self.now - timedelta(minutes=6),
                ),
                self._job(
                    E2E_JOB,
                    E2E_STEPS,
                    started=self.now - timedelta(minutes=6),
                    completed=self.now - timedelta(minutes=3),
                ),
                self._job(
                    CERTIFICATION_JOB,
                    CERTIFICATION_STEPS,
                    started=self.now - timedelta(minutes=2),
                    completed=self.now - timedelta(minutes=1),
                ),
                self._job(
                    COMPLETION_JOB,
                    ("Publish truthful final record",),
                    started=self.now - timedelta(seconds=50),
                    completed=self.now - timedelta(seconds=20),
                ),
            ]
        )
        for job_id, job in enumerate(jobs, start=10001):
            job["id"] = job_id
        return jobs

    def publish_evidence(self, evidence: dict[str, Any]) -> None:
        self.evidence = evidence
        self.certification_archive = _artifact_zip(
            "staging-certification-evidence.json", evidence
        )
        self.certification_artifact = {
            "id": self.certification_artifact_id,
            "name": operation_certification_artifact_name(
                self.run_id, self.attempt
            ),
            "workflow_run_id": self.run_id,
            "expired": False,
            "digest": (
                "sha256:" + hashlib.sha256(self.certification_archive).hexdigest()
            ),
            "size_in_bytes": len(self.certification_archive),
            "created_at": _iso(self.now - timedelta(seconds=70)),
            "workflow_run": {
                "id": self.run_id,
                "head_sha": SHA,
                "head_branch": "staging",
                "repository_id": REPOSITORY_ID,
            },
        }
        self.artifacts = [self.source_artifact, self.certification_artifact]

    def get_workflow_runs(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        _ = per_page
        if workflow_path != ORCHESTRATION_WORKFLOW:
            return []
        if head_sha and head_sha != self.run["head_sha"]:
            return []
        if status and status != self.run["status"]:
            return []
        return [self.run]

    def get_workflow_runs_page(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> WorkflowRunsPage:
        runs = self.get_workflow_runs(
            workflow_path=workflow_path,
            head_sha=head_sha,
            status=status,
            per_page=per_page,
        )
        return WorkflowRunsPage(runs=runs, total_count=self.total_count)

    def get_run(self, run_id: str) -> dict[str, Any]:
        if int(run_id) != self.run_id:
            raise AssertionError(run_id)
        return self.run

    def get_run_attempt(self, run_id: str, attempt: int) -> dict[str, Any]:
        if int(run_id) != self.run_id or attempt != self.attempt:
            raise AssertionError((run_id, attempt))
        return self.run

    def list_run_attempt_jobs(self, run_id: str, attempt: int) -> list[dict[str, Any]]:
        if int(run_id) != self.run_id:
            raise AssertionError(run_id)
        return self.jobs if attempt == self.attempt else []

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        if int(run_id) != self.run_id:
            raise AssertionError(run_id)
        return self.artifacts

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        if artifact_id == self.source_artifact_id:
            return self.source_archive
        if artifact_id == self.certification_artifact_id:
            return self.certification_archive
        raise AssertionError(artifact_id)


class OperationHistoryClient:
    def __init__(
        self,
        clients: list[OperationFixtureClient],
        *,
        total_count: int | None = None,
        current_runs: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.clients = {client.run_id: client for client in clients}
        self.total_count = total_count
        self.current_runs = current_runs or {}
        self.queries: list[tuple[str | None, int]] = []

    def get_workflow_runs_page(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> WorkflowRunsPage:
        self.queries.append((status, per_page))
        runs = [
            client.run
            for client in self.clients.values()
            if workflow_path == ORCHESTRATION_WORKFLOW
            and (head_sha is None or client.run.get("head_sha") == head_sha)
            and (status is None or client.run.get("status") == status)
        ]
        total_count = self.total_count if self.total_count is not None else len(runs)
        return WorkflowRunsPage(runs=runs[:per_page], total_count=total_count)

    def get_workflow_runs(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        return self.get_workflow_runs_page(
            workflow_path=workflow_path,
            head_sha=head_sha,
            status=status,
            per_page=per_page,
        ).runs

    def get_run(self, run_id: str) -> dict[str, Any]:
        numeric_id = int(run_id)
        return self.current_runs.get(numeric_id, self.clients[numeric_id].run)

    def get_run_attempt(self, run_id: str, attempt: int) -> dict[str, Any]:
        return self.clients[int(run_id)].get_run_attempt(run_id, attempt)

    def list_run_attempt_jobs(self, run_id: str, attempt: int) -> list[dict[str, Any]]:
        return self.clients[int(run_id)].list_run_attempt_jobs(run_id, attempt)

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        return self.clients[int(run_id)].list_run_artifacts(run_id)

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        for client in self.clients.values():
            if artifact_id in {
                client.source_artifact_id,
                client.certification_artifact_id,
            }:
                return client.download_artifact_zip(artifact_id)
        raise AssertionError(artifact_id)


class OperationCertificationAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OperationFixtureClient()

    def emit(
        self,
        client: OperationFixtureClient | None = None,
        *,
        focus_group: str = "full",
        expected_exit: int = 0,
    ) -> dict[str, Any]:
        selected = client or self.client
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "run.json").write_text(json.dumps(selected.run), encoding="utf-8")
            (root / "artifact.json").write_text(
                json.dumps(selected.source_artifact), encoding="utf-8"
            )
            (root / "jobs.json").write_text(json.dumps(selected.jobs), encoding="utf-8")
            (root / "proof.zip").write_bytes(selected.source_archive)
            output = root / "output"
            args = [
                "--candidate-sha",
                SHA,
                "--certification-run-id",
                str(selected.run_id),
                "--certification-run-attempt",
                str(selected.attempt),
                "--operation-metadata-dir",
                str(root),
                "--output-dir",
                str(output),
                "--certified-at",
                _iso(selected.now - timedelta(seconds=90)),
                "--focus-group",
                focus_group,
            ]
            for name in (
                "authorize",
                "deploy",
                "handoff",
                "e2e",
                "setup",
                "browser",
                "execution",
                "matrix",
                "cleanup",
                "staging_ref",
                "customer_probe",
                "vendor_probe",
            ):
                args.extend([f"--{name.replace('_', '-')}-outcome", "success"])
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(emit_evidence(args), expected_exit)
            if expected_exit != 0:
                self.assertFalse(
                    (output / "staging-certification-evidence.json").exists()
                )
                return {}
            evidence = json.loads(
                (output / "staging-certification-evidence.json").read_text(
                    encoding="utf-8"
                )
            )
        if not isinstance(evidence, dict):
            raise AssertionError("emitter output must be a JSON object")
        selected.publish_evidence(evidence)
        return evidence

    def assert_rejected(self, client: GitHubActionsClient | None = None) -> None:
        with self.assertRaises(MergeGateError):
            verify_staging_certification_gate(
                candidate_sha=SHA,
                client=client or self.client,
                current_run_id="999999999",
            )

    def test_real_emitter_full_operation_feeds_existing_gate(self) -> None:
        produced = self.emit()
        evidence = verify_staging_certification_gate(
            candidate_sha=SHA,
            client=self.client,
            current_run_id="999999999",
        )
        self.assertEqual(evidence, produced)
        self.assertEqual(evidence["staging_operation_workflow_run_id"], str(RUN_ID))
        self.assertEqual(evidence["staging_operation_run_attempt"], ATTEMPT)
        self.assertEqual(evidence["source_proof"]["artifact_id"], SOURCE_ARTIFACT_ID)
        self.assertEqual(evidence["source_event"], "push")

    def test_newest_operation_failure_state_is_authoritative(self) -> None:
        self.emit()
        for status, conclusion in (
            ("queued", None),
            ("in_progress", None),
            ("completed", "failure"),
            ("completed", "cancelled"),
        ):
            with self.subTest(status=status, conclusion=conclusion):
                newer = OperationFixtureClient(
                    run_id=RUN_ID + 1,
                    source_artifact_id=9201,
                    certification_artifact_id=9202,
                )
                newer.run.update(status=status, conclusion=conclusion)
                self.assert_rejected(OperationHistoryClient([self.client, newer]))

    def test_newer_valid_success_is_the_only_accepted_operation(self) -> None:
        self.emit()
        newer = OperationFixtureClient(
            run_id=RUN_ID + 1,
            source_artifact_id=9201,
            certification_artifact_id=9202,
        )
        expected = self.emit(newer)
        history = OperationHistoryClient([self.client, newer])
        actual = verify_staging_certification_gate(
            candidate_sha=SHA,
            client=history,
            current_run_id="999999999",
        )
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual["staging_operation_workflow_run_id"], str(newer.run_id)
        )
        self.assertEqual(history.queries, [(None, 100)])

    def test_newer_attempt_failure_invalidates_same_run_success(self) -> None:
        successful_attempt = OperationFixtureClient(attempt=1)
        self.emit(successful_attempt)
        current = dict(successful_attempt.run)
        current.update(run_attempt=2, status="completed", conclusion="failure")
        history = OperationHistoryClient(
            [successful_attempt],
            current_runs={successful_attempt.run_id: current},
        )
        self.assert_rejected(history)

    def test_incomplete_bounded_operation_history_is_rejected(self) -> None:
        clients = [
            OperationFixtureClient(
                run_id=RUN_ID + index,
                source_artifact_id=10000 + index * 2,
                certification_artifact_id=10001 + index * 2,
            )
            for index in range(100)
        ]
        self.assert_rejected(OperationHistoryClient(clients, total_count=101))

    def test_newest_success_without_current_attempt_certification_is_rejected(self) -> None:
        self.emit()
        newer = OperationFixtureClient(
            run_id=RUN_ID + 1,
            source_artifact_id=9201,
            certification_artifact_id=9202,
        )
        self.assert_rejected(OperationHistoryClient([self.client, newer]))

    def test_workflow_dispatch_full_cannot_produce_or_satisfy_gate(self) -> None:
        diagnostic = OperationFixtureClient()
        diagnostic.run["event"] = "workflow_dispatch"
        self.assertEqual(self.emit(diagnostic, expected_exit=1), {})

        self.emit()
        self.client.run["event"] = "workflow_dispatch"
        self.assert_rejected()

    def test_non_push_source_event_is_rejected_by_evidence_consumer(self) -> None:
        self.emit()
        self.client.evidence["source_event"] = "workflow_dispatch"
        self.client.publish_evidence(self.client.evidence)
        self.assert_rejected()

    def test_diagnostic_vendor_auth_never_certifies(self) -> None:
        diagnostic = OperationFixtureClient()
        diagnostic.run["event"] = "workflow_dispatch"
        self.assertEqual(
            self.emit(diagnostic, focus_group="vendor-auth", expected_exit=1),
            {},
        )

        self.emit()
        self.client.evidence["focus_group"] = "vendor-auth"
        self.client.publish_evidence(self.client.evidence)
        self.assert_rejected()

    def test_tampered_certification_archive_rejected(self) -> None:
        self.emit()
        self.client.certification_archive += b"tamper"
        self.assert_rejected()

    def test_tampered_source_archive_rejected(self) -> None:
        self.emit()
        self.client.source_archive += b"tamper"
        self.assert_rejected()

    def test_mixed_attempt_and_sha_rejected(self) -> None:
        for field, value in (
            ("staging_operation_run_attempt", 1),
            ("candidate_sha", OTHER_SHA),
        ):
            with self.subTest(field=field):
                client = OperationFixtureClient()
                self.emit(client)
                client.evidence[field] = value
                client.publish_evidence(client.evidence)
                self.assert_rejected(client)

    def test_expired_certification_or_source_artifact_rejected(self) -> None:
        for which in ("certification", "source"):
            with self.subTest(which=which):
                client = OperationFixtureClient()
                self.emit(client)
                target = (
                    client.certification_artifact
                    if which == "certification"
                    else client.source_artifact
                )
                target["expired"] = True
                self.assert_rejected(client)

    def test_expired_evidence_window_rejected(self) -> None:
        self.emit()
        self.client.evidence["expires_at"] = _iso(
            self.client.now - timedelta(seconds=30)
        )
        self.client.publish_evidence(self.client.evidence)
        self.assert_rejected()

    def test_incomplete_evidence_rejected(self) -> None:
        self.emit()
        del self.client.evidence["deployment_binding"]["admin"]
        self.client.publish_evidence(self.client.evidence)
        self.assert_rejected()

    def test_tampered_executed_job_identity_rejected(self) -> None:
        self.emit()
        self.client.evidence["executed_jobs"][0]["job_id"] += 1
        self.client.publish_evidence(self.client.evidence)
        self.assert_rejected()

    def test_failed_or_skipped_recorded_outcomes_rejected(self) -> None:
        for outcome, value in (
            ("setup", "failure"),
            ("browser", "failure"),
            ("matrix", "skipped"),
        ):
            with self.subTest(outcome=outcome):
                client = OperationFixtureClient()
                self.emit(client)
                client.evidence["operation_outcomes"][outcome] = value
                client.publish_evidence(client.evidence)
                self.assert_rejected(client)

    def test_failed_or_skipped_required_e2e_outcomes_rejected(self) -> None:
        cases = (
            ("Canonical cleanup + seed (once per run)", "failure"),
            ("Run E2E suite", "failure"),
            ("Guard — E2E execution-completeness contract", "skipped"),
            ("Record expected matrix (static --list, no browser)", "skipped"),
        )
        for step_name, conclusion in cases:
            with self.subTest(step=step_name):
                client = OperationFixtureClient()
                self.emit(client)
                e2e = next(job for job in client.jobs if job["name"] == E2E_JOB)
                step = next(item for item in e2e["steps"] if item["name"] == step_name)
                step["conclusion"] = conclusion
                self.assert_rejected(client)

    def test_similarly_named_artifact_is_not_selected(self) -> None:
        self.emit()
        self.client.certification_artifact["name"] += "-newer"
        self.assert_rejected()

    def test_schema_four_is_rejected_by_main_merge_gate(self) -> None:
        fixture = REPO_ROOT / "scripts" / "ci" / "fixtures" / "staging-certification-gate" / "pass"
        self.assert_rejected(FixtureGitHubActionsClient(fixture))

    def test_producer_stays_inside_outer_lock_and_standalone_path_is_retired(self) -> None:
        operation = _workflow("staging-operation.yml")
        certification = operation["jobs"]["certify"]
        self.assertEqual(
            set(certification["needs"]),
            {"authorize", "deploy", "e2e"},
        )
        self.assertIn("needs.e2e.result == 'success'", certification["if"])
        self.assertIn("github.event_name == 'push'", certification["if"])
        self.assertNotIn("inputs.focus_group == 'full'", certification["if"])
        step_names = [step.get("name") for step in certification["steps"]]
        self.assertEqual(
            [name for name in step_names if name],
            [
                "Read exact operation attempt and source proof",
                "Emit operation-bound staging certification evidence",
                "Upload operation-bound staging certification evidence",
            ],
        )
        certification_text = str(certification).lower()
        for forbidden in ("seed_staging", "playwright test", "vercel deploy", "migration"):
            self.assertNotIn(forbidden, certification_text)

        standalone = _workflow("release-certify.yml")
        mode_options = standalone["on"]["workflow_dispatch"]["inputs"]["mode"]["options"]
        self.assertNotIn("integrated-staging", mode_options)
        first_steps = standalone["jobs"]["certify"]["steps"][:2]
        self.assertEqual(
            first_steps[1]["name"],
            "Reject retired standalone integrated-staging mode",
        )


if __name__ == "__main__":
    unittest.main()
