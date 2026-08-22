"""Regression tests for the deployed-health staging release proof (Option B).

Covers HEALTH-01..09 from the OPTION-B mandate: verify_health() is the
PRIMARY blocking check that replaced Vercel env-value decryption
(vercel_preview_env_verify.py stays as a non-blocking, informational
secondary signal — see vercel-staging-preview-prove.sh).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "vercel_preview_health_verify.py"

STAGING_HOST = "api.staging.vergeo5.com"
CANDIDATE_SHA = "dc65c413ffd64d853cd6f0e1ea818e065380ffcb"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("vercel_preview_health_verify", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


health_mod: Any = _module()


def _body(
    app: str,
    *,
    status: str = "ok",
    env: str = "staging",
    api_host: str | None = STAGING_HOST,
    build_id: str | None = CANDIDATE_SHA,
) -> dict[str, Any]:
    body: dict[str, Any] = {"status": status, "app": app, "env": env}
    if api_host is not None:
        body["apiHost"] = api_host
    if build_id is not None:
        body["buildId"] = build_id
    return body


def test_health_01_customer_staging_passes() -> None:
    result = health_mod.verify_health(
        _body("customer"), expected_app="customer", expected_api_host=STAGING_HOST
    )
    assert result.ok is True
    assert result.reason == "ok"
    assert result.host == STAGING_HOST


def test_health_02_vendor_staging_passes() -> None:
    result = health_mod.verify_health(
        _body("vendor"), expected_app="vendor", expected_api_host=STAGING_HOST
    )
    assert result.ok is True
    assert result.reason == "ok"


def test_health_03_admin_staging_passes_with_safe_metadata_only() -> None:
    body = _body("admin")
    result = health_mod.verify_health(body, expected_app="admin", expected_api_host=STAGING_HOST)
    assert result.ok is True
    # Body carries only the documented safe fields — no session/user/admin data.
    assert set(body.keys()) == {"status", "app", "env", "apiHost", "buildId"}


def test_health_04_production_host_fails() -> None:
    result = health_mod.verify_health(
        _body("customer", api_host="api.vergeo5.com"),
        expected_app="customer",
        expected_api_host=STAGING_HOST,
    )
    assert result.ok is False
    assert result.reason == "forbidden_host"


def test_health_05_localhost_fails() -> None:
    for bad_host in ("localhost", "127.0.0.1", "sub.localhost", "0.0.0.0", "::1"):
        result = health_mod.verify_health(
            _body("vendor", api_host=bad_host),
            expected_app="vendor",
            expected_api_host=STAGING_HOST,
        )
        assert result.ok is False, bad_host
        assert result.reason == "forbidden_host", bad_host


def test_health_06_empty_or_malformed_host_fails() -> None:
    for bad_host in (None, "", "   "):
        result = health_mod.verify_health(
            _body("admin", api_host=bad_host),
            expected_app="admin",
            expected_api_host=STAGING_HOST,
        )
        assert result.ok is False
        assert result.reason == "missing_host"

    # A value that isn't a string at all (defensive — real JSON always gives
    # str|None here, but a body should never crash the verifier).
    body = _body("admin")
    body["apiHost"] = 12345
    result = health_mod.verify_health(body, expected_app="admin", expected_api_host=STAGING_HOST)
    assert result.ok is False
    assert result.reason == "missing_host"


def test_health_07_verify_health_is_independent_of_env_api_result() -> None:
    """HEALTH-07: a ciphertext/decrypted=false env-API result must not fail
    the deploy — verify_health() takes only the health body, never touches
    or depends on any Vercel env-API result, so it can only ever say PASS
    here. The bash script keeps that env-API check but downgrades it to a
    non-blocking, informational metadata result (see
    vercel-staging-preview-prove.sh's env_metadata_status handling)."""
    import inspect

    signature = inspect.signature(health_mod.verify_health)
    assert "env_metadata" not in signature.parameters
    assert "decrypted" not in signature.parameters

    result = health_mod.verify_health(
        _body("customer"), expected_app="customer", expected_api_host=STAGING_HOST
    )
    assert result.ok is True


def test_health_08_health_reports_production_api_despite_staging_env_metadata() -> None:
    """HEALTH-08: env says staging (body['env']=='staging') but apiHost is
    production — the deployed artifact itself is misconfigured, and that
    must fail regardless of what any env-API metadata claimed."""
    result = health_mod.verify_health(
        _body("vendor", env="staging", api_host="api.vergeo5.com"),
        expected_app="vendor",
        expected_api_host=STAGING_HOST,
    )
    assert result.ok is False
    assert result.reason == "forbidden_host"


def test_health_09_correct_host_but_wrong_sha_fails() -> None:
    result = health_mod.verify_health(
        _body("customer", build_id="0000000000000000000000000000000000dead"),
        expected_app="customer",
        expected_api_host=STAGING_HOST,
        expected_sha=CANDIDATE_SHA,
    )
    assert result.ok is False
    assert result.reason == "sha_mismatch"


def test_sha_check_is_opt_in() -> None:
    result = health_mod.verify_health(
        _body("customer", build_id="unknown"),
        expected_app="customer",
        expected_api_host=STAGING_HOST,
    )
    assert result.ok is True


def test_wrong_status_fails() -> None:
    result = health_mod.verify_health(
        _body("customer", status="degraded"),
        expected_app="customer",
        expected_api_host=STAGING_HOST,
    )
    assert result.ok is False
    assert result.reason == "status"


def test_wrong_app_fails() -> None:
    result = health_mod.verify_health(
        _body("customer"), expected_app="vendor", expected_api_host=STAGING_HOST
    )
    assert result.ok is False
    assert result.reason == "app"


def test_wrong_env_fails() -> None:
    result = health_mod.verify_health(
        _body("customer", env="development"),
        expected_app="customer",
        expected_api_host=STAGING_HOST,
    )
    assert result.ok is False
    assert result.reason == "env"


def test_host_comparison_is_case_and_whitespace_insensitive() -> None:
    result = health_mod.verify_health(
        _body("customer", api_host=f" {STAGING_HOST.upper()} "),
        expected_app="customer",
        expected_api_host=STAGING_HOST,
    )
    assert result.ok is True
    assert result.host == STAGING_HOST


def test_cli_never_prints_more_than_the_reason(tmp_path: Path, capsys: Any) -> None:
    import json

    health_json_file = tmp_path / "health.json"
    health_json_file.write_text(json.dumps(_body("customer")), encoding="utf-8")

    rc = health_mod.main(
        [
            "--app",
            "customer",
            "--expected-api-host",
            STAGING_HOST,
            "--expected-sha",
            CANDIDATE_SHA,
            "--health-json-file",
            str(health_json_file),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "ok"


def test_cli_host_mismatch_reason_only(tmp_path: Path, capsys: Any) -> None:
    import json

    health_json_file = tmp_path / "health.json"
    health_json_file.write_text(
        json.dumps(_body("customer", api_host="wrong-host.example.com")), encoding="utf-8"
    )

    rc = health_mod.main(
        [
            "--app",
            "customer",
            "--expected-api-host",
            STAGING_HOST,
            "--health-json-file",
            str(health_json_file),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "host_mismatch"
    assert "wrong-host" not in out
