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
    """A 302 to our OWN login path is still a failure and must not be excused
    as a protection challenge. The wording stays neutral about the cause (a
    redirect can also come from an optional Vercel cookie flow), so it asserts
    the classification rather than blaming the application."""
    verdict = access.classify_access(
        http_status=302, location="/en/login?next=%2Fen%2Fhealth", bypass_present=True
    )
    assert verdict.verdict == "http_error"
    assert "no Vercel SSO marker was detected" in verdict.detail


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


# --------------------------------------------------------------------------
# One-shot health-probe request contract (deploy-staging run #33).
#
# Run #33 returned HTTP 307 on all three portals with curl exit 0 — an HTTP
# response, not a transport failure. Vercel documents
# `x-vercel-set-bypass-cookie` as OPTIONAL, for maintaining authorization
# "across multiple requests or within iframes"; their own one-shot curl
# example sends `x-vercel-protection-bypass` alone. This probe makes a single
# request, so it now sends only the bypass header. Playwright (a multi-request
# browser flow) keeps the cookie header.
# --------------------------------------------------------------------------


def _health_curl_config_block() -> str:
    """The `{ ... } > "${health_curl_config}"` block that builds the request."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")
    before = script.split('} > "${health_curl_config}"')[0]
    return before[before.rindex("\n{\n") :]


def test_case_a_one_shot_probe_sends_bypass_header_without_cookie_header() -> None:
    """CASE A: with a bypass configured, the probe emits
    x-vercel-protection-bypass and NOT x-vercel-set-bypass-cookie."""
    block = _health_curl_config_block()
    assert "x-vercel-protection-bypass: %s" in block
    assert "x-vercel-set-bypass-cookie" not in block
    # Accept header is retained.
    assert 'header = "Accept: application/json"' in block


def test_case_a_cookie_header_is_absent_from_the_whole_prove_script() -> None:
    """The cookie header must not reappear anywhere in the deploy-staging
    probe — including in a fallback branch."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")
    emitting = [
        line
        for line in script.splitlines()
        if "x-vercel-set-bypass-cookie" in line and "printf" in line
    ]
    assert emitting == []


def test_case_b_no_bypass_configured_emits_no_bypass_headers() -> None:
    """CASE B: the bypass header is emitted only inside the
    `if [ -n "${BYPASS_SECRET}" ]` guard, so an unconfigured portal sends
    neither bypass header."""
    block = _health_curl_config_block()
    guard_index = block.index('if [ -n "${BYPASS_SECRET}" ]')
    bypass_index = block.index("x-vercel-protection-bypass")
    assert guard_index < bypass_index
    # Accept is outside the guard and always sent.
    assert block.index('header = "Accept: application/json"') < guard_index


def test_case_c_http_200_with_correct_health_payload_passes() -> None:
    verdict = access.classify_access(http_status=200, body=_health_body(), bypass_present=True)
    assert verdict.verdict == "ok"


@pytest.mark.parametrize("status", [302, 307])
def test_case_d_redirect_after_cookie_removal_fails_as_unexpected(status: int) -> None:
    """CASE D: with the cookie header gone, a remaining 3xx that carries no
    Vercel SSO marker is an unexpected deployed-health redirect and fails."""
    verdict = access.classify_access(
        http_status=status, location="/en/somewhere", bypass_present=True
    )
    assert verdict.verdict == "http_error"
    assert "unexpected HTTP redirect from deployed health endpoint" in verdict.detail
    # Wording must no longer assert the application as the cause.
    assert "the application redirected the health route" not in verdict.detail


def test_case_d_a_vercel_sso_redirect_is_still_blocked_external_not_http_error() -> None:
    """Removing the cookie header must not blur the protection classification."""
    verdict = access.classify_access(
        http_status=307, location=VERCEL_SSO_LOCATION, bypass_present=True
    )
    assert verdict.verdict == "blocked_external"


# --------------------------------------------------------------------------
# CASE E — redirect diagnostics are safe
# --------------------------------------------------------------------------


def _headers_blob() -> str:
    return (
        "HTTP/2 307 \r\n"
        "location: https://example.vercel.app/en/health"
        "?x-vercel-protection-bypass=SUPERSECRET&nonce=abc123\r\n"
        "set-cookie: _vercel_jwt=TOPSECRETJWT; Path=/; HttpOnly\r\n"
        "server: Vercel\r\n"
        "\r\n"
    )


def test_case_e_diagnostics_report_useful_metadata() -> None:
    summary = access.summarize_response_headers(_headers_blob())
    assert "status_line=HTTP/2 307" in summary
    assert "location=present" in summary
    assert "host=example.vercel.app" in summary
    assert "path=/en/health" in summary
    assert "set_cookie=yes" in summary
    assert "server=Vercel" in summary


@pytest.mark.parametrize(
    "forbidden",
    ["SUPERSECRET", "TOPSECRETJWT", "nonce", "_vercel_jwt", "HttpOnly", "abc123"],
)
def test_case_e_diagnostics_never_print_secrets_cookies_or_query(forbidden: str) -> None:
    """CASE E: no Set-Cookie value, no bypass secret, no query string."""
    summary = access.summarize_response_headers(_headers_blob())
    assert forbidden not in summary


def test_case_e_location_query_is_always_stripped() -> None:
    assert access.sanitize_location("https://h.example/p?token=abc") == "host=h.example path=/p"
    # Relative redirects are query-stripped too.
    assert access.sanitize_location("/en/login?next=%2Fen%2Fhealth") == "path=/en/login"
    assert access.sanitize_location("") == ""


def test_case_e_set_cookie_absence_is_reported_as_no() -> None:
    summary = access.summarize_response_headers("HTTP/2 307 \r\nlocation: /en/x\r\n\r\n")
    assert "set_cookie=no" in summary
    assert "location=present path=/en/x" in summary


def test_case_e_missing_location_is_reported_as_absent() -> None:
    summary = access.summarize_response_headers("HTTP/2 500 \r\nserver: Vercel\r\n\r\n")
    assert "location=absent" in summary


def test_case_e_only_the_final_response_block_is_summarized() -> None:
    """curl -D can dump several blocks; the last response is the one that
    matters."""
    raw = (
        "HTTP/2 307 \r\nlocation: https://first.example/a?q=1\r\n\r\n"
        "HTTP/2 200 \r\nserver: Vercel\r\n\r\n"
    )
    summary = access.summarize_response_headers(raw)
    assert "status_line=HTTP/2 200" in summary
    assert "first.example" not in summary


def test_case_e_diagnostics_cli_is_secret_free(tmp_path: Path) -> None:
    headers_file = tmp_path / "h.txt"
    headers_file.write_text(_headers_blob(), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "summarize-headers",
            "--headers-file",
            str(headers_file),
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "VERCEL_AUTOMATION_BYPASS_SECRET": SECRET_VALUE},
    )
    assert proc.returncode == 0
    for forbidden in ("SUPERSECRET", "TOPSECRETJWT", SECRET_VALUE):
        assert forbidden not in proc.stdout
        assert forbidden not in proc.stderr


def test_case_e_diagnostics_run_only_on_non_2xx_and_never_gate() -> None:
    """Diagnostics must be logged, not used as a verdict input."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")
    assert "summarize-headers --headers-file" in script
    assert "response diagnostics:" in script
    # Guarded to non-2xx, and emitted via log (not feeding any decision).
    diag = script.split("# Safe response metadata on any non-2xx")[1].split("esac")[0]
    assert "2??) ;;" in diag
    assert "log " in diag
    assert "die" not in diag


# --------------------------------------------------------------------------
# CASE F — #668's retry classification is unchanged
# --------------------------------------------------------------------------


def test_case_f_transport_retry_and_http_no_retry_behaviour_is_unchanged() -> None:
    for code in (5, 6, 7, 18, 28, 35, 52, 55, 56):
        assert access.classify_curl_exit(code).retryable is True
    for code in (3, 23, 26, 60, 77, 99):
        assert access.classify_curl_exit(code).retryable is False
    # Any HTTP response is never retried.
    assert access.classify_curl_exit(0).kind == "HTTP_RESPONSE"
    assert access.classify_curl_exit(0).retryable is False


# --------------------------------------------------------------------------
# curl exit-code classification — retry only genuinely transient transport
# errors. Codes verified against libcurl's own CURLE_* enum.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "name"),
    [
        (5, "CURLE_COULDNT_RESOLVE_PROXY"),
        (6, "CURLE_COULDNT_RESOLVE_HOST"),
        (7, "CURLE_COULDNT_CONNECT"),
        (18, "CURLE_PARTIAL_FILE"),
        (28, "CURLE_OPERATION_TIMEDOUT"),
        (35, "CURLE_SSL_CONNECT_ERROR"),
        (52, "CURLE_GOT_NOTHING"),
        (55, "CURLE_SEND_ERROR"),
        (56, "CURLE_RECV_ERROR"),
    ],
)
def test_transient_transport_curl_codes_are_retried(code: int, name: str) -> None:
    verdict = access.classify_curl_exit(code)
    assert verdict.kind == "TRANSIENT_TRANSPORT"
    assert verdict.retryable is True
    assert verdict.name == name


@pytest.mark.parametrize(
    ("code", "name"),
    [
        (3, "CURLE_URL_MALFORMAT"),
        (23, "CURLE_WRITE_ERROR"),
        (26, "CURLE_READ_ERROR"),
        (60, "CURLE_PEER_FAILED_VERIFICATION"),
        (77, "CURLE_SSL_CACERT_BADFILE"),
    ],
)
def test_deterministic_curl_codes_fail_immediately(code: int, name: str) -> None:
    """Malformed URL, local read/write faults and certificate-validation
    failures cannot be fixed by retrying — they must fail on attempt 1."""
    verdict = access.classify_curl_exit(code)
    assert verdict.kind == "NON_RETRYABLE_CURL"
    assert verdict.retryable is False
    assert verdict.name == name


def test_certificate_validation_is_not_retried_even_though_tls_handshake_is() -> None:
    """35 (handshake failure, transient) and 60/77 (certificate/CA problems,
    deterministic) must land on opposite sides of the retry boundary."""
    assert access.classify_curl_exit(35).retryable is True
    assert access.classify_curl_exit(60).retryable is False
    assert access.classify_curl_exit(77).retryable is False


def test_unknown_curl_code_fails_safe_as_non_retryable() -> None:
    verdict = access.classify_curl_exit(99)
    assert verdict.kind == "NON_RETRYABLE_CURL"
    assert verdict.retryable is False
    assert verdict.name == ""


def test_curl_exit_zero_is_an_http_response_and_is_never_retried() -> None:
    verdict = access.classify_curl_exit(0)
    assert verdict.kind == "HTTP_RESPONSE"
    assert verdict.retryable is False


def test_http_302_protection_challenge_reaches_the_classifier_without_retry() -> None:
    """curl rc=0 with a 302 means the endpoint answered: no retry, and the
    response goes to the Deployment Protection classifier unchanged."""
    assert access.classify_curl_exit(0).retryable is False
    verdict = access.classify_access(
        http_status=302, location=VERCEL_SSO_LOCATION, bypass_present=False
    )
    assert verdict.verdict == "blocked_external"


def test_http_200_with_rc_zero_proceeds_to_health_verification() -> None:
    assert access.classify_curl_exit(0).retryable is False
    verdict = access.classify_access(http_status=200, body=_health_body(), bypass_present=True)
    assert verdict.verdict == "ok"


def test_classify_curl_exit_cli_prints_kind_retryable_and_name(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(MODULE_PATH), "classify-curl-exit", "--code", "6"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "VERCEL_AUTOMATION_BYPASS_SECRET": SECRET_VALUE},
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "TRANSIENT_TRANSPORT\t1\tCURLE_COULDNT_RESOLVE_HOST"
    assert SECRET_VALUE not in proc.stdout
    assert SECRET_VALUE not in proc.stderr


def test_probe_classifies_and_labels_the_failure_class() -> None:
    """The final diagnostic must name the actual class, never call a
    certificate or malformed-URL error 'a connection-level failure'."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")
    assert "classify-curl-exit" in script
    assert "TRANSIENT_TRANSPORT)" in script
    assert "NON_RETRYABLE_CURL:" in script
    assert 'if [ "${health_exit_retryable}" != "1" ]; then' in script
    # The old blanket wording is gone.
    assert "This is a connection-level failure, not an application" not in script


def test_probe_redacts_the_bypass_secret_from_curl_stderr() -> None:
    """curl never echoes request headers without -v, but the probe redacts
    defensively — via bash parameter expansion, so the secret never reaches
    an argv or a pipe even while being redacted."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")
    assert "sanitized_curl_error()" in script
    assert 'raw="${raw//${BYPASS_SECRET}/[redacted]}"' in script
    # Redaction must not shell out with the secret as an argument.
    assert "sed" not in script.split("sanitized_curl_error()")[1].split("}")[0]
    # Every place the error is surfaced goes through the sanitizer.
    assert "$(sanitized_curl_error)" in script
    assert 'tail -1 "${health_stderr_file}"' not in script


def test_health_probe_retries_connection_failures_and_surfaces_the_curl_exit_code() -> None:
    """deploy-staging run #32 regression: a Vercel deployment reports READY
    before its per-deployment hostname is reliably resolvable, so the probe
    failed to CONNECT ~0.7s after READY on all three portals — well under the
    15s connect timeout. The original probe discarded curl's stderr
    (`2>/dev/null`), which made that undiagnosable. The probe must now retry
    connection-level failures and report curl's actual exit code/message."""
    script = PROVE_SCRIPT.read_text(encoding="utf-8")

    # Retries the probe rather than dying on the first connection failure.
    assert "for health_attempt in 1 2 3 4 5; do" in script
    assert "sleep $((health_attempt * 3))" in script

    # curl's stderr is captured to a file, never discarded, and surfaced.
    assert '2>"${health_stderr_file}"' in script
    assert 'curl --config "${health_curl_config}" \\\n    --silent' in script
    assert "curl exit ${health_rc}" in script

    # An HTTP response of any status must NOT be retried — only rc != 0 is.
    # (Status handling belongs to classify_access, below the loop.)
    loop_body = script.split("for health_attempt in 1 2 3 4 5; do")[1].split("done")[0]
    assert 'if [ "${health_rc}" -eq 0 ]; then' in loop_body
    assert "break" in loop_body
    assert "blocked_external" not in loop_body

    # The old discard-stderr form is gone from the health probe.
    assert "-w '%{http_code}' \\\n  \"${health_url}\" 2>/dev/null" not in script
