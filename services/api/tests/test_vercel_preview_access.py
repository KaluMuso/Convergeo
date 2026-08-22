"""Regression tests for Vercel Deployment Protection access on Preview probes.

Root cause under test (deploy-staging run #31, staging SHA 858cfd0c): all
three Preview deployments were READY and all three `/{locale}/health` routes
independently returned HTTP 200 with the correct effective configuration,
but the CI probes saw HTTP 302 because the deployments sit behind Vercel
Deployment Protection and the probe was unauthenticated. The application
health implementation was never at fault, so a protection challenge must be
classified as BLOCKED_EXTERNAL and never reported as a broken health route.

Cases A-J from the mandate:
  A. protected + correct bypass    -> health 200 -> PASS
  B. protected + no bypass         -> 302 Vercel SSO -> BLOCKED_EXTERNAL
  C. protected + wrong bypass      -> challenge -> BLOCKED_EXTERNAL
  D. the secret never appears in stdout/stderr/evidence
  E. correct health + ciphertext env metadata -> PASS (env API non-blocking)
  F/G/H. customer/vendor/admin each select their own portal secret
  I. portal-specific secret takes precedence over the generic fallback
  J. absent portal-specific secret falls back to the generic secret
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "vercel_preview_access.py"
PROVE_SCRIPT = REPO_ROOT / "scripts" / "ci" / "vercel-staging-preview-prove.sh"

SECRET_VALUE = "s3cr3t-bypass-value-never-logged"
STAGING_HOST = "api.staging.vergeo5.com"
VERCEL_SSO_LOCATION = (
    "https://vercel.com/sso-api?url=https%3A%2F%2Fconvergeo-customer.vercel.app"
    "%2Fen%2Fhealth&nonce=abc123"
)


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("vercel_preview_access", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


access: Any = _module()


def _health_body(app: str = "customer") -> str:
    return json.dumps(
        {
            "status": "ok",
            "app": app,
            "env": "staging",
            "buildId": "858cfd0cad4c0616c1f6017a8f94d8f6b95003c0",
            "apiHost": STAGING_HOST,
        }
    )


# --------------------------------------------------------------------------
# A / B / C — protection challenge classification
# --------------------------------------------------------------------------


def test_case_a_protected_with_correct_bypass_reaches_the_app() -> None:
    """A: the bypass worked — HTTP 200 with an application JSON body."""
    verdict = access.classify_access(
        http_status=200, location="", body=_health_body(), bypass_present=True
    )
    assert verdict.verdict == "ok"


def test_case_b_protected_without_bypass_is_blocked_external() -> None:
    """B: exactly run #31 — a 302 to Vercel SSO with no bypass configured."""
    verdict = access.classify_access(
        http_status=302, location=VERCEL_SSO_LOCATION, body="", bypass_present=False
    )
    assert verdict.verdict == "blocked_external"
    assert "no bypass secret configured" in verdict.detail
    # Must NOT blame the application route.
    assert "health broken" not in verdict.detail.lower()


def test_case_c_protected_with_wrong_bypass_is_blocked_external() -> None:
    """C: a bypass was sent but Vercel still challenged — wrong/expired secret,
    or one issued for a different project."""
    verdict = access.classify_access(
        http_status=302, location=VERCEL_SSO_LOCATION, body="", bypass_present=True
    )
    assert verdict.verdict == "blocked_external"
    assert "different Vercel project" in verdict.detail


@pytest.mark.parametrize("status", [401, 403])
def test_challenge_via_status_and_body_markers(status: int) -> None:
    verdict = access.classify_access(
        http_status=status,
        location="",
        body="<html><body>Authentication Required — Log in to Vercel</body></html>",
        bypass_present=False,
    )
    assert verdict.verdict == "blocked_external"


def test_any_vercel_com_redirect_host_is_a_challenge() -> None:
    verdict = access.classify_access(
        http_status=307, location="https://vercel.com/login?next=%2F", bypass_present=False
    )
    assert verdict.verdict == "blocked_external"


# --------------------------------------------------------------------------
# The four outcomes stay distinguishable (mandate section 4)
# --------------------------------------------------------------------------


def test_app_redirect_that_is_not_a_vercel_challenge_is_not_blocked_external() -> None:
    """A 302 to our OWN login path is an application routing regression (the
    vendor-middleware bug PR #666 fixed) — it must not be excused as a
    protection challenge."""
    verdict = access.classify_access(
        http_status=302, location="/en/login?next=%2Fen%2Fhealth", bypass_present=True
    )
    assert verdict.verdict == "http_error"
    assert "not a Vercel" in verdict.detail


def test_http_200_with_non_json_body_is_an_application_failure() -> None:
    verdict = access.classify_access(
        http_status=200, body="<html>not json</html>", bypass_present=True
    )
    assert verdict.verdict == "not_json"


def test_http_200_with_non_object_json_is_malformed() -> None:
    verdict = access.classify_access(http_status=200, body="[1, 2, 3]", bypass_present=True)
    assert verdict.verdict == "not_json"


def test_http_500_is_an_application_runtime_failure() -> None:
    verdict = access.classify_access(http_status=500, body="boom", bypass_present=True)
    assert verdict.verdict == "app_error"
    assert "not a protection challenge" in verdict.detail


# --------------------------------------------------------------------------
# E — env-API metadata stays non-blocking
# --------------------------------------------------------------------------


def test_case_e_ciphertext_env_metadata_does_not_affect_access_classification() -> None:
    """E: classify_access() takes only the HTTP response. A `ciphertext`
    env-API verdict cannot influence it, so correct health still passes."""
    import inspect

    params = inspect.signature(access.classify_access).parameters
    assert "env_metadata" not in params
    assert "ciphertext" not in params

    verdict = access.classify_access(http_status=200, body=_health_body(), bypass_present=True)
    assert verdict.verdict == "ok"


# --------------------------------------------------------------------------
# F / G / H / I / J — per-portal secret selection
# --------------------------------------------------------------------------


@pytest.mark.parametrize("portal", ["customer", "vendor", "admin"])
def test_cases_f_g_h_each_portal_selects_its_own_secret(portal: str) -> None:
    """F/G/H: with all three portal-specific secrets present, each portal
    resolves to its OWN project's variable — never another portal's."""
    env = {
        "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER": "customer-secret",
        "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR": "vendor-secret",
        "VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN": "admin-secret",
    }
    source = access.resolve_bypass_source(env, portal)
    assert source.kind == "portal_specific"
    assert source.env_name == f"VERCEL_AUTOMATION_BYPASS_SECRET_{portal.upper()}"


def test_case_i_portal_specific_takes_precedence_over_generic_fallback() -> None:
    env = {
        "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR": "vendor-secret",
        "VERCEL_AUTOMATION_BYPASS_SECRET": "generic-secret",
    }
    source = access.resolve_bypass_source(env, "vendor")
    assert source.kind == "portal_specific"
    assert source.env_name == "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR"


def test_case_j_absent_portal_specific_falls_back_to_generic() -> None:
    env = {"VERCEL_AUTOMATION_BYPASS_SECRET": "generic-secret"}
    for portal in ("customer", "vendor", "admin"):
        source = access.resolve_bypass_source(env, portal)
        assert source.kind == "fallback"
        assert source.env_name == "VERCEL_AUTOMATION_BYPASS_SECRET"


def test_caller_scoped_variable_wins_over_everything() -> None:
    """deploy-staging.yml's matrix pre-scopes exactly one secret per job."""
    env = {
        "VERCEL_PORTAL_BYPASS_SECRET": "scoped-secret",
        "VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN": "admin-secret",
        "VERCEL_AUTOMATION_BYPASS_SECRET": "generic-secret",
    }
    source = access.resolve_bypass_source(env, "admin")
    assert source.kind == "portal_scoped"
    assert source.env_name == "VERCEL_PORTAL_BYPASS_SECRET"


def test_no_secret_configured_reports_none() -> None:
    source = access.resolve_bypass_source({}, "customer")
    assert source.kind == "none"
    assert source.env_name is None
    assert source.present is False


def test_blank_and_whitespace_only_secrets_count_as_absent() -> None:
    env = {
        "VERCEL_PORTAL_BYPASS_SECRET": "   ",
        "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR": "",
        "VERCEL_AUTOMATION_BYPASS_SECRET": "generic-secret",
    }
    source = access.resolve_bypass_source(env, "vendor")
    assert source.kind == "fallback"


def test_unknown_portal_is_rejected() -> None:
    with pytest.raises(ValueError):
        access.resolve_bypass_source({}, "marketing")


# --------------------------------------------------------------------------
# D — the secret never leaks
# --------------------------------------------------------------------------


def test_case_d_resolve_source_never_returns_or_prints_the_secret_value() -> None:
    """D (API level): BypassSource carries only a kind and a variable NAME."""
    env = {"VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER": SECRET_VALUE}
    source = access.resolve_bypass_source(env, "customer")
    rendered = f"{source!r} {source.kind} {source.env_name}"
    assert SECRET_VALUE not in rendered


def test_case_d_resolve_source_cli_never_prints_the_secret(tmp_path: Path) -> None:
    """D (CLI level): run the real CLI with a secret in the environment and
    assert it appears in neither stdout nor stderr."""
    proc = subprocess.run(
        [sys.executable, str(MODULE_PATH), "resolve-source", "--portal", "vendor"],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR": SECRET_VALUE,
        },
    )
    assert proc.returncode == 0
    assert SECRET_VALUE not in proc.stdout
    assert SECRET_VALUE not in proc.stderr
    assert "portal_specific" in proc.stdout
    assert "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR" in proc.stdout


def test_case_d_classify_cli_never_echoes_the_secret(tmp_path: Path) -> None:
    """D (CLI level): the classifier never receives the secret at all — only a
    boolean presence flag — so it cannot echo one."""
    body_file = tmp_path / "health.json"
    body_file.write_text(_health_body(), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "classify",
            "--http-status",
            "200",
            "--body-file",
            str(body_file),
            "--bypass-present",
            "1",
            "--print-detail",
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "VERCEL_AUTOMATION_BYPASS_SECRET": SECRET_VALUE},
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "ok"
    assert SECRET_VALUE not in proc.stdout
    assert SECRET_VALUE not in proc.stderr


def test_case_d_classify_cli_takes_no_secret_argument() -> None:
    """The CLI exposes only `--bypass-present`, so a secret can never be put
    into argv (where `ps` would expose it)."""
    import inspect

    source = inspect.getsource(access.main)
    assert "--bypass-present" in source
    for forbidden in ("--bypass-secret", "--secret", "--token"):
        assert forbidden not in source


def test_case_d_prove_script_never_puts_the_secret_in_argv_or_evidence() -> None:
    """D (shell level): static guarantees in vercel-staging-preview-prove.sh."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")

    # The secret reaches curl through a config file, never `-H` on the command line.
    assert '--config "${health_curl_config}"' in script
    assert '-H "x-vercel-protection-bypass' not in script
    assert "chmod 600" in script

    # Never traced. Checked against executable lines only — the file's prose
    # explains why `set -x` is avoided, which is not itself an enablement.
    code_lines = [line.strip() for line in script.splitlines() if not line.strip().startswith("#")]
    assert not any(
        line == "set -x" or line.startswith("set -x ") or " set -x" in line for line in code_lines
    )

    # Only the SOURCE label lands in evidence/outputs — never the value.
    assert '"bypass_source": os.environ["bypass_source"]' in script
    assert "BYPASS_SECRET" not in script.split("python3 - <<'PY'")[-1]
    for sink in ("printf 'url=%s", "printf 'deployment_id=%s", "printf 'sha=%s"):
        assert sink in script
    github_output_block = script.split('if [ -n "${GITHUB_OUTPUT:-}" ]; then')[-1]
    assert "BYPASS_SECRET" not in github_output_block

    # The secret is never echoed/logged; only its source variable name is.
    assert 'log "protection bypass: using ${BYPASS_SOURCE_VAR} (${BYPASS_SOURCE})"' in script
    assert 'echo "${BYPASS_SECRET}"' not in script
    assert 'log "${BYPASS_SECRET}"' not in script
