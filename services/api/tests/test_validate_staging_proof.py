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


def _release_proof() -> dict[str, Any]:
    previews = {portal: _proof(portal) for portal in proof_mod.REQUIRED_PORTALS}
    for portal, row in previews.items():
        row["deployment_id"] = f"dpl_{portal}"
        row["project_id"] = f"prj_{portal}"
        row["preview_url"] = f"https://convergeo-{portal}-abc123-vergeo-projects.vercel.app"
        row["configuration_revision"] = "staging-config-2026-09-14"
        row["checkpoint_stage"] = "PRE_PROBE"
        row["deployment_action"] = "created"
        row["deployment_origin_attempt"] = 2
        row["deployment_create_calls"] = 1
        row["reused_deployments"] = 0
    previews["customer"]["stable_hostname_status"] = "verified"
    previews["customer"]["stable_hostname_url"] = proof_mod.CUSTOMER_STAGING_ORIGIN
    return {
        "schema_version": proof_mod.RELEASE_PROOF_VERSION,
        "candidate_sha": CANDIDATE_SHA,
        "previews": previews,
        "api_fingerprint": {
            "env": "staging",
            "git_sha": CANDIDATE_SHA,
            "image_tag": CANDIDATE_SHA,
            "supabase_project_ref": proof_mod.STAGING_SUPABASE_PROJECT_REF,
        },
        "migrate_supabase_result": "success",
        "source": {
            "repository": proof_mod.RELEASE_REPOSITORY,
            "repository_id": proof_mod.RELEASE_REPOSITORY_ID,
            "workflow": ".github/workflows/deploy-staging.yml",
            "ref": proof_mod.RELEASE_REF,
            "candidate_sha": CANDIDATE_SHA,
            "run_id": 10,
            "run_attempt": 2,
        },
        "configuration": {
            "identity_scheme": "operator-managed-non-secret-v1",
            "revision": "staging-config-2026-09-14",
        },
        "deployment_efficiency": {
            "create_calls": 3,
            "reused_deployments": 0,
            "portals": {
                portal: {"action": "created", "origin_attempt": 2}
                for portal in proof_mod.REQUIRED_PORTALS
            },
        },
        "proof_outcomes": {proof_id: "PASS" for proof_id in proof_mod.RELEASE_PROOF_OUTCOMES},
    }


def _validate_release(proof: dict[str, Any]) -> None:
    proof_mod.validate_release_envelope(
        proof,
        candidate_sha=CANDIDATE_SHA,
        source_run_id=10,
        source_run_attempt=2,
        source_workflow=".github/workflows/deploy-staging.yml",
        configuration_revision="staging-config-2026-09-14",
    )


def test_valid_v2_release_envelope_passes() -> None:
    _validate_release(_release_proof())


@pytest.mark.parametrize("outcome", ["FAIL", "NOT_RUN", "SKIPPED_APPROVED", "UNKNOWN"])
def test_release_envelope_requires_executed_pass_outcomes(outcome: str) -> None:
    proof = _release_proof()
    proof["proof_outcomes"]["customer_same_site_cart"] = outcome
    with pytest.raises(proof_mod.ProofValidationError, match="did not pass"):
        _validate_release(proof)


def test_release_envelope_rejects_legacy_schema_and_stale_attempt() -> None:
    proof = _release_proof()
    proof["schema_version"] = 1
    with pytest.raises(proof_mod.ProofValidationError, match="schema_version"):
        _validate_release(proof)

    proof = _release_proof()
    proof["source"]["run_attempt"] = 1
    with pytest.raises(proof_mod.ProofValidationError, match="run_attempt"):
        _validate_release(proof)


def test_release_envelope_requires_full_health_and_api_image_sha() -> None:
    proof = _release_proof()
    proof["previews"]["vendor"]["health_build_id"] = None
    with pytest.raises(proof_mod.ProofValidationError, match="full health SHA"):
        _validate_release(proof)

    proof = _release_proof()
    proof["api_fingerprint"]["image_tag"] = "unknown"
    with pytest.raises(proof_mod.ProofValidationError, match="image tag"):
        _validate_release(proof)


def test_release_envelope_binds_configuration_and_customer_same_site_origin() -> None:
    proof = _release_proof()
    proof["configuration"]["revision"] = "older-config"
    with pytest.raises(proof_mod.ProofValidationError, match="configuration revision"):
        _validate_release(proof)

    proof = _release_proof()
    proof["previews"]["customer"]["stable_hostname_url"] = (
        "https://convergeo-customer-abc123-vergeo-projects.vercel.app"
    )
    with pytest.raises(proof_mod.ProofValidationError, match="same-site origin"):
        _validate_release(proof)


def test_release_envelope_binds_checkpoint_reprobe_counts_and_configuration() -> None:
    proof = _release_proof()
    proof["previews"]["vendor"].update(
        deployment_action="reused", deployment_create_calls=0, reused_deployments=1
    )
    proof["deployment_efficiency"].update(create_calls=2, reused_deployments=1)
    proof["deployment_efficiency"]["portals"]["vendor"]["action"] = "reused"
    _validate_release(proof)

    proof["deployment_efficiency"]["create_calls"] = 3
    with pytest.raises(proof_mod.ProofValidationError, match="create count"):
        _validate_release(proof)

    proof = _release_proof()
    proof["previews"]["admin"]["configuration_revision"] = "stale-config"
    with pytest.raises(proof_mod.ProofValidationError, match="configuration revision"):
        _validate_release(proof)
