#!/usr/bin/env python3
"""GitHub Actions provenance helpers for release-control gates."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Any, Protocol

DEPLOY_STAGING_WORKFLOW = ".github/workflows/deploy-staging.yml"
RELEASE_CERTIFY_WORKFLOW = ".github/workflows/release-certify.yml"
STAGING_CERTIFICATION_ARTIFACT = "staging-certification-evidence"
STAGING_SHA_PROOF_ARTIFACT = "staging-sha-proof"
STAGING_SHA_PROOF_FILENAME = "staging-sha-proof.json"


class GitHubActionsClient(Protocol):
    def get_workflow_runs(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]: ...

    def get_run(self, run_id: str) -> dict[str, Any]: ...

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]: ...

    def download_artifact_zip(self, artifact_id: int) -> bytes: ...


@dataclass(frozen=True)
class LiveGitHubActionsClient:
    repository: str
    token: str
    api_version: str = "2022-11-28"

    def _request(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": self.api_version,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API HTTP {exc.code} for {url}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API error for {url}: {exc.reason}") from exc

    def get_workflow_runs(
        self,
        *,
        workflow_path: str,
        head_sha: str | None = None,
        status: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        owner, repo = self.repository.split("/", 1)
        workflows = self._request(f"https://api.github.com/repos/{owner}/{repo}/actions/workflows")
        workflow_id = None
        for item in workflows.get("workflows", []):
            if str(item.get("path")) == workflow_path:
                workflow_id = item.get("id")
                break
        if workflow_id is None:
            raise RuntimeError(f"workflow not found: {workflow_path}")

        query = [f"per_page={per_page}"]
        if head_sha:
            query.append(f"head_sha={head_sha}")
        if status:
            query.append(f"status={status}")
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/"
            f"{workflow_id}/runs?{'&'.join(query)}"
        )
        payload = self._request(url)
        runs = payload.get("workflow_runs")
        return runs if isinstance(runs, list) else []

    def get_run(self, run_id: str) -> dict[str, Any]:
        owner, repo = self.repository.split("/", 1)
        payload = self._request(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
        )
        return payload if isinstance(payload, dict) else {}

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        owner, repo = self.repository.split("/", 1)
        payload = self._request(
            f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
        )
        artifacts = payload.get("artifacts")
        return artifacts if isinstance(artifacts, list) else []

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        owner, repo = self.repository.split("/", 1)
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/"
            f"{artifact_id}/zip"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": self.api_version,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload: bytes = response.read()
                return payload
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"artifact download HTTP {exc.code} for artifact {artifact_id}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"artifact download failed for artifact {artifact_id}: {exc.reason}"
            ) from exc


def verify_completed_success_run(
    run: dict[str, Any],
    *,
    expected_workflow_path: str,
    expected_head_sha: str,
    label: str,
) -> None:
    if str(run.get("status")) != "completed":
        raise ValueError(f"{label} run is not completed")
    if str(run.get("conclusion")) != "success":
        raise ValueError(f"{label} run did not succeed (conclusion={run.get('conclusion')!r})")
    workflow_path = str(run.get("path") or "")
    if workflow_path != expected_workflow_path:
        raise ValueError(
            f"{label} workflow path {workflow_path!r} != {expected_workflow_path!r}"
        )
    head_sha = str(run.get("head_sha") or "").lower()
    if head_sha != expected_head_sha.lower():
        raise ValueError(
            f"{label} head_sha {head_sha[:12]} != candidate {expected_head_sha[:12]}"
        )


def extract_artifact_json(zip_bytes: bytes, filename: str) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.endswith(filename) and not name.endswith("/")
        ]
        if not candidates:
            raise ValueError(f"artifact zip missing {filename}")
        raw = archive.read(candidates[0])
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{filename} must contain a JSON object")
    return data


def download_named_artifact_json(
    client: GitHubActionsClient,
    *,
    run_id: str,
    artifact_name: str,
    filename: str,
    label: str,
) -> dict[str, Any]:
    artifacts = client.list_run_artifacts(run_id)
    target = None
    for artifact in artifacts:
        if str(artifact.get("name")) == artifact_name:
            target = artifact
            break
    if target is None:
        raise ValueError(f"{label} run {run_id} missing artifact {artifact_name!r}")
    if target.get("expired") is True:
        raise ValueError(f"{label} artifact expired for run {run_id}")
    zip_bytes = client.download_artifact_zip(int(target["id"]))
    return extract_artifact_json(zip_bytes, filename)
