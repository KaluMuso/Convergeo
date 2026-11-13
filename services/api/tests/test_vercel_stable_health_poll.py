"""Run #68 regression: alias accepted != exact live fingerprint propagated.

No live Vercel, wall-clock sleeps, deployments, or real credentials. The fake
clock advances on requests/waits so all retries exercise the actual deadline.
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
CI_DIR = REPO_ROOT / "scripts" / "ci"
SHA = "1509097b67480c7a5190d5e92f25444d5eeebaf1"
OLD_SHA = "1f07b7959216d6f2085a35768d8e824ec92374ce"
HOST = "api.staging.vergeo5.com"


def _module() -> Any:
    # Script imports siblings when invoked directly, not an application package.
    sys.path.insert(0, str(CI_DIR))
    try:
        spec = importlib.util.spec_from_file_location(
            "vercel_stable_health_poll", CI_DIR / "vercel_stable_health_poll.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


poll: Any = _module()
yaml: Any = importlib.import_module("yaml")


def body(**changes: Any) -> str:
    return json.dumps(
        {
            "status": "ok",
            "app": "customer",
            "env": "staging",
            "apiHost": HOST,
            "buildId": SHA,
            **changes,
        }
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def run(*responses: Any, cost: float = 0, budget: float = 10) -> tuple[Any, Clock, list[float]]:
    clock = Clock()
    budgets: list[float] = []

    def request(remaining: float) -> Any:
        index = min(len(budgets), len(responses) - 1)
        budgets.append(remaining)
        clock.now += cost
        return responses[index]

    result = poll.poll_health(
        request,
        expected_app="customer",
        expected_api_host=HOST,
        expected_sha=SHA,
        deadline_seconds=budget,
        clock=clock,
        wait=clock.wait,
    )
    return result, clock, budgets


def ok(**changes: Any) -> Any:
    return poll.Response(http_status=200, body=body(**changes))


def test_first_response_exact_no_wait() -> None:
    report, clock, budgets = run(ok())
    assert report["verdict"] == "PASS"
    assert report["reason"] == "ok"
    assert budgets == [10]
    assert clock.waits == []
    assert report["attempts"][0]["observed_build_id"] == SHA


def test_old_staging_then_candidate() -> None:
    report, clock, budgets = run(ok(buildId=OLD_SHA), ok())
    assert report["verdict"] == "PASS"
    assert [a["reason"] for a in report["attempts"]] == ["sha_mismatch", "ok"]
    assert clock.waits == [3]
    assert budgets == [10, 7]


@pytest.mark.parametrize("stale_sha", [OLD_SHA, SHA[:12] + "a" * 28, SHA[:-1] + "0"])
def test_persistent_stale_including_shared_prefix_fails(stale_sha: str) -> None:
    assert stale_sha != SHA
    report, clock, budgets = run(ok(buildId=stale_sha))
    assert report["verdict"] == "FAIL"
    assert report["reason"] == "deadline_exceeded"
    assert all(a["reason"] == "sha_mismatch" for a in report["attempts"])
    assert budgets == [10, 7, 4, 1]
    assert clock.waits == [3, 3, 3, 1]
    assert clock.now == 10


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"app": "vendor"}, "app"),
        ({"app": None}, "app"),
        ({"env": "production"}, "env"),
        ({"env": "preview"}, "env"),
        ({"env": None}, "env"),
        ({"apiHost": "api.vergeo5.com"}, "forbidden_host"),
        ({"apiHost": "localhost"}, "forbidden_host"),
        ({"apiHost": "api.other-staging.example"}, "host_mismatch"),
        ({"apiHost": None}, "missing_host"),
        ({"status": "degraded"}, "status"),
    ],
)
def test_wrong_plane_fails_even_if_build_is_old(change: dict[str, Any], reason: str) -> None:
    report, clock, budgets = run(ok(buildId=OLD_SHA, **change), ok())
    assert report["verdict"] == "FAIL"
    assert report["reason"] == reason
    assert budgets == [10]
    assert clock.waits == []


@pytest.mark.parametrize("build_id", [None, "", "unknown", SHA[:12], SHA[:39], 42, {}])
def test_missing_or_non_full_build_id_cannot_certify(build_id: Any) -> None:
    report, clock, _ = run(ok(buildId=build_id), ok())
    assert report["reason"] == "invalid_build_id"
    assert report["verdict"] == "FAIL"
    assert clock.waits == []


@pytest.mark.parametrize(
    "status,raw,location,reason",
    [
        (401, "unauthorized", "", "http_error"),
        (403, "forbidden", "", "http_error"),
        (302, "", "https://vercel.com/login?token=secret", "blocked_external"),
        (403, "Authentication Required", "", "blocked_external"),
        (503, "Authentication Required", "", "blocked_external"),
        (200, "<html>oops</html>", "", "not_json"),
        (200, "{broken", "", "not_json"),
        (200, "null", "", "not_json"),
        (200, "[]", "", "not_json"),
        (201, body(), "", "http_error"),
        (307, "", "/en/login", "http_error"),
        (404, "not found", "", "http_error"),
        (500, "internal error", "", "http_error"),
    ],
)
def test_unauthorized_malformed_and_other_http_fail_closed(
    status: int,
    raw: str,
    location: str,
    reason: str,
) -> None:
    report, clock, budgets = run(poll.Response(http_status=status, body=raw, location=location))
    assert report["verdict"] == "FAIL"
    assert report["reason"] == reason
    assert budgets == [10]
    assert clock.waits == []


@pytest.mark.parametrize("status", sorted(poll.RETRYABLE_HTTP_STATUSES))
def test_explicit_transient_service_can_recover_or_exhaust(status: int) -> None:
    temporary = poll.Response(http_status=status, body="temporarily unavailable")
    recovered, _, _ = run(temporary, ok())
    assert recovered["verdict"] == "PASS"
    exhausted, clock, _ = run(temporary)
    assert exhausted["reason"] == "deadline_exceeded"
    assert clock.now == 10


@pytest.mark.parametrize("code", [5, 6, 7, 18, 28, 35, 52, 55, 56])
def test_exhausted_transient_transport_budget(code: int) -> None:
    failed = poll.Response(curl_exit=code)
    report, clock, budgets = run(failed)
    assert report["reason"] == "deadline_exceeded"
    assert report["verdict"] == "FAIL"
    assert all(a["reason"] == "TRANSIENT_TRANSPORT" for a in report["attempts"])
    assert budgets == [10, 7, 4, 1]
    assert clock.now == 10
    recovered, _, _ = run(failed, ok())
    assert recovered["verdict"] == "PASS"


@pytest.mark.parametrize("code", [3, 23, 26, 47, 60, 77, 999])
def test_deterministic_transport_never_retries(code: int) -> None:
    report, clock, budgets = run(poll.Response(curl_exit=code), ok())
    assert report["reason"] == "NON_RETRYABLE_CURL"
    assert clock.waits == []
    assert budgets == [10]


def test_request_time_and_wait_share_one_deadline() -> None:
    report, clock, budgets = run(ok(buildId=OLD_SHA), cost=2)
    assert report["reason"] == "deadline_exceeded"
    assert budgets == [10, 5]
    assert clock.now == 10


def test_candidate_arriving_at_deadline_is_too_late() -> None:
    report, clock, budgets = run(ok(), cost=10)
    assert report["verdict"] == "FAIL"
    assert report["reason"] == "deadline_exceeded"
    assert clock.waits == []
    assert budgets == [10]


@pytest.mark.parametrize("budget", [0, -1, 91, float("inf"), float("nan")])
def test_invalid_deadline_does_not_request(budget: float) -> None:
    report, _, budgets = run(ok(), budget=budget)
    assert report["reason"] == "invalid_configuration"
    assert budgets == []


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_sha": SHA[:12]},
        {"expected_api_host": "api.vergeo5.com"},
        {"expected_app": "other"},
    ],
)
def test_invalid_expected_fingerprint_cannot_request(changes: dict[str, Any]) -> None:
    def never_request(remaining: float) -> Any:
        pytest.fail("invalid configuration must not send a request")

    settings = {
        "expected_app": "customer",
        "expected_api_host": HOST,
        "expected_sha": SHA,
        "deadline_seconds": 10,
        **changes,
    }
    assert poll.poll_health(never_request, **settings)["reason"] == "invalid_configuration"


@pytest.mark.parametrize(
    "ref,hostname,path",
    [
        ("master", "customer.staging.vergeo5.com", "/en/health"),
        ("fix/feature", "customer.staging.vergeo5.com", "/en/health"),
        ("staging", "vergeo5.com", "/en/health"),
        ("staging", "customer.staging.vergeo5.com.evil.example", "/en/health"),
        ("staging", "customer.staging.vergeo5.com", "/en/health?token=secret"),
    ],
)
def test_cli_staging_scope_refuses_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ref: str,
    hostname: str,
    path: str,
) -> None:
    monkeypatch.setenv("GITHUB_REF_NAME", ref)

    def forbidden_request(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid plane/host/path must not send a credential")

    monkeypatch.setattr(poll, "curl_request", forbidden_request)
    target = tmp_path / "diagnostics.json"
    assert (
        poll.main(
            [
                "--hostname",
                hostname,
                "--health-path",
                path,
                "--app",
                "customer",
                "--expected-api-host",
                HOST,
                "--expected-sha",
                SHA,
                "--deadline-seconds",
                "10",
                "--diagnostics-file",
                str(target),
            ]
        )
        == 1
    )
    assert json.loads(target.read_text())["reason"] == "invalid_configuration"


@pytest.mark.parametrize("remaining", [0.25, 15, 60])
def test_curl_request_bounds_and_private_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remaining: float,
) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        assert argv[:2] == ["curl", "--disable"]
        assert "--no-location" in argv and "--location" not in argv
        assert argv[argv.index("--retry") + 1] == "0"
        assert float(argv[argv.index("--max-time") + 1]) == min(30, remaining)
        assert float(argv[argv.index("--connect-timeout") + 1]) == min(15, remaining)
        assert kwargs["timeout"] == remaining
        (tmp_path / "body").write_text(body())
        (tmp_path / "headers").write_text("HTTP/2 200\nSet-Cookie: private-cookie\n")
        return subprocess.CompletedProcess(argv, 0, "200", "private-stderr")

    monkeypatch.setattr(poll.subprocess, "run", fake_run)
    result = poll.curl_request(
        "https://customer.staging.vergeo5.com/en/health",
        tmp_path / "curl.conf",
        tmp_path,
        remaining,
    )
    assert result.http_status == 200
    assert "private" not in repr(result)


def test_parent_process_timeout_does_not_leak_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("secret-command", 1, stderr="secret-stderr")

    monkeypatch.setattr(poll.subprocess, "run", fake_run)
    response = poll.curl_request(
        "https://customer.staging.vergeo5.com/en/health", tmp_path / "curl.conf", tmp_path, 1
    )
    assert response.curl_exit == 28
    assert "secret" not in repr(response)


@pytest.mark.parametrize(
    "scenario", ["success", "wrong_app", "malformed", "unauthorized", "transport", "probe_error"]
)
def test_cli_retains_only_sanitized_diagnostics_on_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
    scenario: str,
) -> None:
    secret = 'DO-NOT-EXPORT-THIS-SECRET"\\'
    monkeypatch.setenv("GITHUB_REF_NAME", "staging")
    monkeypatch.setenv("VERCEL_PORTAL_BYPASS_SECRET", secret)
    monkeypatch.setenv("UNRELATED_SECRET", secret)
    clock = Clock()
    real_poll = poll.poll_health
    private_paths: list[Path] = []

    def controlled_poll(*args: Any, **kwargs: Any) -> Any:
        return real_poll(*args, **kwargs, clock=clock, wait=clock.wait)

    def request(url: str, config: Path, scratch: Path, remaining: float) -> Any:
        assert secret not in url
        assert config.stat().st_mode & 0o777 == 0o600
        assert scratch.stat().st_mode & 0o777 == 0o700
        assert "x-vercel-set-bypass-cookie" not in config.read_text()
        private_paths.append(scratch)
        (scratch / "headers").write_text(f"Set-Cookie: {secret}\nAuthorization: {secret}")
        if scenario == "probe_error":
            raise OSError(secret)
        return {
            "success": ok(extra_secret=secret),
            "wrong_app": ok(app=secret, apiHost=secret, buildId=secret),
            "malformed": poll.Response(http_status=200, body=secret),
            "unauthorized": poll.Response(
                http_status=302, body=secret, location=f"https://vercel.com/login/{secret}"
            ),
            "transport": poll.Response(curl_exit=28, body=secret, location=secret),
        }[scenario]

    monkeypatch.setattr(poll, "poll_health", controlled_poll)
    monkeypatch.setattr(poll, "curl_request", request)
    target = tmp_path / "stable-health-diagnostics.json"
    code = poll.main(
        [
            "--hostname",
            "customer.staging.vergeo5.com",
            "--health-path",
            "/en/health",
            "--app",
            "customer",
            "--expected-api-host",
            HOST,
            "--expected-sha",
            SHA,
            "--deadline-seconds",
            "10",
            "--diagnostics-file",
            str(target),
        ]
    )
    assert code == (0 if scenario == "success" else 1)
    output = capsys.readouterr()
    report = json.loads(target.read_text())
    assert json.loads(output.out) == report
    assert output.err == ""
    assert report["certification_evidence"] is False
    assert report["evidence_kind"] == "diagnostic-staging-alias"
    assert "DO-NOT-EXPORT" not in target.read_text() + output.out
    assert "UNRELATED_SECRET" not in target.read_text()
    assert private_paths and all(not p.exists() for p in private_paths)


def test_workflow_failure_diagnostics_are_separate_and_allowlisted() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/deploy-staging.yml").read_text())
    steps = workflow["jobs"]["prove-vercel-preview"]["steps"]
    uploads = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@")]
    diagnostic = next(s for s in uploads if "diagnostics" in s["name"])
    assert diagnostic["if"] == "${{ always() }}"
    assert diagnostic["with"]["path"] == (
        "/tmp/staging-preview-${{ matrix.portal }}/stable-health-diagnostics.json"
    )
    assert not diagnostic["with"]["name"].startswith("staging-preview-evidence-")
    certification = next(s for s in uploads if "Preview evidence" in s["name"])
    assert "always()" not in certification.get("if", "")
    assert certification["with"]["path"] == (
        "/tmp/staging-preview-${{ matrix.portal }}/evidence.json"
    )
    script = (CI_DIR / "vercel-staging-preview-prove.sh").read_text()
    assert (
        script.index('prove_stable_hostname_health "${stable_hostname}"')
        < script.index('stable_hostname_status="verified"')
        < script.index('EVIDENCE_PATH="${VERCEL_PREVIEW_PROVE_EVIDENCE:')
    )
    function = script.split("prove_stable_hostname_health() {")[1].split("\n}", 1)[0]
    assert "--deadline-seconds 90" in function
    assert 'if ! python3 "${REPO_ROOT}/scripts/ci/vercel_stable_health_poll.py"' in function
    assert "die " in function
