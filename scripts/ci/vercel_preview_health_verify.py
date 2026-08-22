#!/usr/bin/env python3
"""Validate a Vercel Preview's `/health` payload against the staging contract.

This is the PRIMARY staging release proof: it verifies the EFFECTIVE
DEPLOYED CONFIGURATION of the actual Preview artifact — "is this build
wired to api.staging.vergeo5.com" — by reading `/{locale}/health`
(`{status, app, env, buildId, apiHost}`, added alongside this change; see
apps/*/app/[locale]/health/route.ts). It replaces Vercel env-value
decryption as the blocking check: Vercel's platform can refuse to decrypt a
row for reasons entirely outside this repository's control (see
vercel_preview_env_verify.py's docstring), which proves nothing about what
was actually deployed. `apiHost` is safe to expose — the corresponding
`NEXT_PUBLIC_*` variable is deliberately browser-public — and every app
derives it from the exact same effective-configuration resolver the running
app itself uses (`packages/config/src/api-base-url.ts`), so this proves the
real thing rather than merely a stored setting.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Config-intent guard, independent of the effective-deployed-configuration
# proof below: a host in this set is refused even if somehow reported by a
# deployed artifact.
FORBIDDEN_HOSTS = {"api.vergeo5.com", "localhost", "127.0.0.1", "0.0.0.0", "::1"}

DEFAULT_EXPECTED_ENV = ("staging", "preview")

#: "ok" | "status" | "app" | "env" | "missing_host" | "forbidden_host"
#: | "host_mismatch" | "sha_mismatch"
Reason = str


@dataclass(frozen=True)
class HealthVerdict:
    ok: bool
    reason: Reason
    # Populated only on success or a mismatch a caller may want to log
    # safely (host/build_id are not secrets — see module docstring).
    host: str | None = None
    build_id: str | None = None


def _normalize_host(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    host = value.strip().lower()
    return host or None


def _is_forbidden_host(host: str) -> bool:
    if host in FORBIDDEN_HOSTS:
        return True
    return host.endswith(".localhost")


def verify_health(
    body: dict[str, Any],
    *,
    expected_app: str,
    expected_api_host: str,
    expected_sha: str | None = None,
    expected_env: tuple[str, ...] = DEFAULT_EXPECTED_ENV,
) -> HealthVerdict:
    """Validate one portal's `/health` JSON body against the staging contract.

    Fails closed at every step: a missing/malformed field is never treated
    as an implicit pass, and no field is ever substituted with a default.
    """
    if body.get("status") != "ok":
        return HealthVerdict(False, "status")

    if body.get("app") != expected_app:
        return HealthVerdict(False, "app")

    if body.get("env") not in expected_env:
        return HealthVerdict(False, "env")

    host = _normalize_host(body.get("apiHost"))
    if host is None:
        return HealthVerdict(False, "missing_host")

    if _is_forbidden_host(host):
        return HealthVerdict(False, "forbidden_host", host=host)

    if host != expected_api_host.strip().lower():
        return HealthVerdict(False, "host_mismatch", host=host)

    build_id = body.get("buildId")
    build_id = build_id if isinstance(build_id, str) and build_id else None

    if expected_sha:
        if build_id != expected_sha:
            return HealthVerdict(False, "sha_mismatch", host=host, build_id=build_id)

    return HealthVerdict(True, "ok", host=host, build_id=build_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Vercel Preview's /health payload against the staging contract"
    )
    parser.add_argument("--app", required=True, help="Expected 'app' field (customer|vendor|admin)")
    parser.add_argument("--expected-api-host", required=True)
    parser.add_argument(
        "--expected-sha", default=None, help="Candidate SHA; omit to skip the SHA check"
    )
    parser.add_argument("--health-json-file", type=Path, required=True)
    args = parser.parse_args(argv)

    body = json.loads(args.health_json_file.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        print("status")
        return 0

    result = verify_health(
        body,
        expected_app=args.app,
        expected_api_host=args.expected_api_host,
        expected_sha=args.expected_sha,
    )
    # Host/build_id are safe (see module docstring) but the CLI only ever
    # prints the reason word — callers that want the safe metadata read the
    # dataclass directly (see tests); this keeps CI log output uniform with
    # vercel_preview_env_verify.py's verdict-only contract.
    print(result.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
