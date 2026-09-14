#!/usr/bin/env python3
"""Post-alias live fingerprint proof, with one monotonic deadline.

Only a well-formed, otherwise-correct staging fingerprint with another full
SHA, explicit transient curl errors, and HTTP 408/429/502/503/504 may retry.
All other failures are terminal. This is not the immutable Preview verifier.
The diagnostic artifact is an allowlist, never a request/response dump.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vercel_preview_access import classify_access, classify_curl_exit, resolve_bypass_source
from vercel_preview_health_verify import FULL_SHA, verify_health

RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 502, 503, 504})


@dataclass(frozen=True)
class Response:
    curl_exit: int = 0
    http_status: int = 0
    body: str = ""
    location: str = ""


def poll_health(
    request: Callable[[float], Response],
    *,
    expected_app: str,
    expected_api_host: str,
    expected_sha: str,
    deadline_seconds: float,
    interval_seconds: float = 3,
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Inject request/clock/wait for deterministic, offline deadline tests.

    Each request receives ONLY the remaining budget, including time already
    spent in requests and waits. A late response cannot become a success.
    Failure diagnostics contain enum reasons, numeric codes/times, and validated
    full SHAs only: no arbitrary body fields, URLs, headers or exception text.
    """
    started = clock()
    deadline = started + deadline_seconds
    report: dict[str, Any] = {
        "evidence_kind": "diagnostic-staging-alias",
        "certification_evidence": False,
        "verdict": "FAIL",
        "reason": "invalid_configuration",
        "attempts": [],
    }
    if (
        expected_app not in {"customer", "vendor", "admin"}
        or expected_api_host != "api.staging.vergeo5.com"
        or FULL_SHA.fullmatch(expected_sha) is None
        or not math.isfinite(deadline_seconds)
        or not 0 < deadline_seconds <= 90
        or not math.isfinite(interval_seconds)
        or interval_seconds <= 0
    ):
        return report
    report.update(candidate_sha=expected_sha, deadline_seconds=deadline_seconds)

    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            report["reason"] = "deadline_exceeded"
            break
        try:
            response = request(remaining)
        except (OSError, ValueError):
            # Raw transport/local exceptions may contain credentials or bodies.
            report["reason"] = "probe_error"
            break
        retryable = False
        observed_sha = None
        transport = classify_curl_exit(response.curl_exit)
        if response.curl_exit:
            reason = transport.kind
            retryable = transport.retryable
        else:
            access = classify_access(
                http_status=response.http_status,
                body=response.body,
                location=response.location,
            )
            if access.verdict == "blocked_external":
                reason = "blocked_external"
            elif response.http_status in RETRYABLE_HTTP_STATUSES:
                reason = "transient_service"
                retryable = True
            elif response.http_status != 200:
                reason = "http_error"
            elif access.verdict != "ok":
                reason = access.verdict
            else:
                body = json.loads(response.body)
                verdict = verify_health(
                    body,
                    expected_app=expected_app,
                    expected_api_host=expected_api_host,
                    expected_sha=expected_sha,
                    expected_env=("staging",),
                    require_build_id=True,
                )
                reason = verdict.reason
                retryable = reason == "sha_mismatch"
                # A whitelisted field NAME is not enough: never echo arbitrary
                # strings even from buildId (an error page can put secrets here).
                if verdict.build_id and FULL_SHA.fullmatch(verdict.build_id):
                    observed_sha = verdict.build_id
        report["attempts"].append(
            {
                "attempt": len(report["attempts"]) + 1,
                "elapsed_seconds": round(clock() - started, 3),
                "curl_exit": response.curl_exit,
                "http_status": response.http_status,
                "reason": reason,
                "retryable": retryable,
                "observed_build_id": observed_sha,
            }
        )
        if clock() >= deadline:
            report["reason"] = "deadline_exceeded"
            break
        if reason == "ok":
            report.update(verdict="PASS", reason="ok")
            break
        if not retryable:
            report["reason"] = reason
            break
        wait(min(interval_seconds, max(0, deadline - clock())))

    report["elapsed_seconds"] = round(clock() - started, 3)
    return report


def curl_request(url: str, config: Path, scratch: Path, remaining: float) -> Response:
    """One request; curl and its parent process are both deadline-bounded.

    No redirect following, cookie jar, implicit .curlrc, or curl-internal retry.
    Private temporary files are never part of an uploaded artifact. stderr is
    discarded, not redacted after logging. Only the numeric curl code escapes.
    """
    body = scratch / "body"
    headers = scratch / "headers"
    try:
        result = subprocess.run(
            [
                "curl",
                "--disable",
                "--config",
                str(config),
                "--silent",
                "--no-location",
                "--retry",
                "0",
                "--connect-timeout",
                str(min(15, remaining)),
                "--max-time",
                str(min(30, remaining)),
                "--max-filesize",
                "65536",
                "--output",
                str(body),
                "--dump-header",
                str(headers),
                "--write-out",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Response(curl_exit=28)
    if result.returncode:
        return Response(curl_exit=result.returncode)
    if re.fullmatch(r"[0-9]{3}", result.stdout) is None:
        return Response(curl_exit=2)
    location = ""
    for line in headers.read_text(encoding="utf-8", errors="replace").splitlines():
        name, _, value = line.partition(":")
        if name.lower() == "location":
            location = value.strip()
    return Response(
        http_status=int(result.stdout),
        body=body.read_text(encoding="utf-8", errors="replace"),
        location=location,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--health-path", required=True)
    parser.add_argument("--app", required=True, choices=["customer", "vendor", "admin"])
    parser.add_argument("--expected-api-host", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--diagnostics-file", type=Path, required=True)
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "evidence_kind": "diagnostic-staging-alias",
        "certification_evidence": False,
        "verdict": "FAIL",
        "reason": "invalid_configuration",
        "attempts": [],
    }
    try:
        # This helper cannot send the bypass credential to an arbitrary host or
        # production. Shell/deployment environment guards remain in place too.
        if (
            os.environ.get("GITHUB_REF_NAME") != "staging"
            or args.hostname != "customer.staging.vergeo5.com"
            or args.app != "customer"
            or re.fullmatch(r"/(?:en|bem|nya|fr|zh)/health", args.health_path) is None
        ):
            return 1
        source = resolve_bypass_source(dict(os.environ), args.app)
        secret = os.environ.get(source.env_name, "") if source.env_name else ""
        if any(ord(char) < 32 or ord(char) == 127 for char in secret):
            return 1
        escaped_secret = secret.replace("\\", "\\\\").replace('"', '\\"')
        url = f"https://{args.hostname}{args.health_path}"
        with tempfile.TemporaryDirectory(prefix="staging-alias-health-") as private:
            scratch = Path(private)
            config = scratch / "curl.conf"
            with config.open("x", encoding="utf-8") as handle:
                config.chmod(0o600)
                handle.write('header = "Accept: application/json"\n')
                handle.write('header = "Cache-Control: no-cache"\n')
                if secret:
                    handle.write(f'header = "x-vercel-protection-bypass: {escaped_secret}"\n')
            report = poll_health(
                lambda remaining: curl_request(url, config, scratch, remaining),
                expected_app=args.app,
                expected_api_host=args.expected_api_host,
                expected_sha=args.expected_sha,
                deadline_seconds=args.deadline_seconds,
            )
        return 0 if report["verdict"] == "PASS" else 1
    except (OSError, ValueError):
        report["reason"] = "probe_error"
        return 1
    finally:
        # Runs on success AND failure; never writes certification evidence.
        args.diagnostics_file.parent.mkdir(parents=True, exist_ok=True)
        args.diagnostics_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))


if __name__ == "__main__":
    raise SystemExit(main())
