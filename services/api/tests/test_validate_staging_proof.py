"""Regression tests for the staging evidence.json secondary validator.

validate_portal_proof() is confirmatory, not the primary release gate (see
its docstring — vercel_preview_health_verify.py's deployed-health check is
primary and blocking, and evidence.json only exists once that has already
passed inside vercel-staging-preview-prove.sh). But it must still fully
assert the staging contract on the evidence document itself, so a stale or
hand-edited evidence.json cannot slip a bad host/env/portal past
release-certify. These tests cover the hardening pass that replaced the old
"health_api_host is non-empty" check with an exact-match assertion, added
the missing health_env check, and added the health_build_id
opt-in-corroboration policy (mirrors vercel_preview_health_verify.py's
buildId policy: deployment_sha is the blocking identity proof, so an absent
health_build_id is accepted and only present-and-wrong fails).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "validate_staging_proof.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("validate_staging_proof", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


proof_mod: Any = _module()

CANDIDATE_SHA = "dc65c413ffd64d853cd6f0e1ea818e065380ffcb"
OTHER_SHA = "0000000000000000000000000000000000dead"
STAGING_HOST = "api.staging.vergeo5.com"


def _proof(
    portal: str,
    *,
    deployment_sha: str = CANDIDATE_SHA,
    candidate_sha: str = CANDIDATE_SHA,
    target: str = "preview",
    preview_url: str = "https://convergeo-example-preview.vercel.app",
    health_status: str = "ok",
    health_app: str | None = None,
    health_env: str = "staging",
    health_api_host: str | None = STAGING_HOST,
    health_build_id: str | None = CANDIDATE_SHA,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "portal": portal,
        "deployment_sha": deployment_sha,
        "candidate_sha": candidate_sha,
        "target": target,
        "preview_url": preview_url,
        "health_status": health_status,
        "health_app": health_app if health_app is not None else portal,
        "health_env": health_env,
    }
    if health_api_host is not None:
        doc["health_api_host"] = health_api_host
    if health_build_id is not None:
        doc["health_build_id"] = health_build_id
    return doc


def test_valid_proof_passes() -> None:
    proof_mod.validate_portal_proof("customer", _proof("customer"), candidate_sha=CANDIDATE_SHA)


# --- SHA-proof combinations (mirrors vercel_preview_health_verify.py policy) ---


def test_deployment_sha_correct_build_id_correct_passes() -> None:
    proof = _proof("customer", deployment_sha=CANDIDATE_SHA, health_build_id=CANDIDATE_SHA)
    proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_deployment_sha_correct_build_id_absent_passes() -> None:
    """The blocking identity proof is deployment_sha; an absent
    health_build_id (Vercel system-var exposure not enabled on the project)
    must not fail validation on its own."""
    proof = _proof("customer", deployment_sha=CANDIDATE_SHA, health_build_id=None)
    proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_deployment_sha_correct_build_id_wrong_fails() -> None:
    proof = _proof("customer", deployment_sha=CANDIDATE_SHA, health_build_id=OTHER_SHA)
    with pytest.raises(proof_mod.ProofValidationError, match="health_build_id"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_deployment_sha_wrong_build_id_correct_fails() -> None:
    """deployment_sha is checked first and unconditionally — a matching
    health_build_id cannot rescue a wrong deployment_sha."""
    proof = _proof("customer", deployment_sha=OTHER_SHA, health_build_id=CANDIDATE_SHA)
    with pytest.raises(proof_mod.ProofValidationError, match="deployment_sha"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


# --- health_api_host must be an exact match, not merely non-empty ---


@pytest.mark.parametrize(
    "bad_host",
    ["api.vergeo5.com", "localhost", "wrong-host.example.com", ""],
)
def test_wrong_or_empty_api_host_fails_even_with_every_other_field_correct(bad_host: str) -> None:
    proof = _proof("vendor", health_api_host=bad_host)
    with pytest.raises(proof_mod.ProofValidationError, match="health_api_host"):
        proof_mod.validate_portal_proof("vendor", proof, candidate_sha=CANDIDATE_SHA)


def test_missing_api_host_field_fails() -> None:
    proof = _proof("vendor", health_api_host=None)
    with pytest.raises(proof_mod.ProofValidationError, match="health_api_host"):
        proof_mod.validate_portal_proof("vendor", proof, candidate_sha=CANDIDATE_SHA)


def test_api_host_comparison_is_case_and_whitespace_insensitive() -> None:
    proof = _proof("vendor", health_api_host=f" {STAGING_HOST.upper()} ")
    proof_mod.validate_portal_proof("vendor", proof, candidate_sha=CANDIDATE_SHA)


# --- health_env must be an allowed value, not merely present ---


def test_wrong_health_env_fails() -> None:
    proof = _proof("admin", health_env="production")
    with pytest.raises(proof_mod.ProofValidationError, match="health_env"):
        proof_mod.validate_portal_proof("admin", proof, candidate_sha=CANDIDATE_SHA)


def test_missing_health_env_fails() -> None:
    proof = _proof("admin")
    del proof["health_env"]
    with pytest.raises(proof_mod.ProofValidationError, match="health_env"):
        proof_mod.validate_portal_proof("admin", proof, candidate_sha=CANDIDATE_SHA)


@pytest.mark.parametrize("allowed_env", ["staging", "preview"])
def test_allowed_health_envs_pass(allowed_env: str) -> None:
    proof = _proof("admin", health_env=allowed_env)
    proof_mod.validate_portal_proof("admin", proof, candidate_sha=CANDIDATE_SHA)


# --- existing field checks stay intact ---


def test_wrong_health_status_fails() -> None:
    proof = _proof("customer", health_status="degraded")
    with pytest.raises(proof_mod.ProofValidationError, match="health_status"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_wrong_health_app_fails() -> None:
    proof = _proof("customer", health_app="vendor")
    with pytest.raises(proof_mod.ProofValidationError, match="health_app"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_wrong_target_fails() -> None:
    proof = _proof("customer", target="production")
    with pytest.raises(proof_mod.ProofValidationError, match="target"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_invalid_preview_url_fails() -> None:
    proof = _proof("customer", preview_url="not-a-url")
    with pytest.raises(proof_mod.ProofValidationError, match="preview_url"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)


def test_wrong_proof_candidate_sha_fails() -> None:
    proof = _proof("customer", candidate_sha=OTHER_SHA)
    with pytest.raises(proof_mod.ProofValidationError, match="candidate_sha"):
        proof_mod.validate_portal_proof("customer", proof, candidate_sha=CANDIDATE_SHA)
