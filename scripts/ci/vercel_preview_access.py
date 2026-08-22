#!/usr/bin/env python3
"""Resolve Vercel Deployment Protection access for a Preview health probe.

Root cause this module exists for (deploy-staging run #31, staging SHA
858cfd0c): all three Preview deployments reached READY and all three
`/{locale}/health` routes were independently confirmed to return HTTP 200
with the correct effective configuration — but the CI probes saw HTTP 302,
because the deployments sit behind Vercel Deployment Protection and the
probe was unauthenticated. The application health implementation, the admin
CF Access exception, and the API host wiring were all already correct; only
the probe's access was missing.

Two responsibilities, both kept out of bash so they are directly testable:

1. `resolve_bypass_source()` — pick WHICH bypass secret a portal should use.
   A Vercel "Protection Bypass for Automation" secret is issued per project,
   and Convergeo has three separate projects (convergeo-customer,
   convergeo-vendor, convergeo-admin), so a secret generated for one is not
   assumed to work on the others. Precedence, highest first:
     a. `VERCEL_PORTAL_BYPASS_SECRET` — already scoped to this portal by the
        caller (how deploy-staging.yml's matrix passes exactly one secret per
        leg, so a job never receives the other portals' secrets).
     b. `VERCEL_AUTOMATION_BYPASS_SECRET_{CUSTOMER,VENDOR,ADMIN}` — explicit
        portal-specific names, for local/manual runs.
     c. `VERCEL_AUTOMATION_BYPASS_SECRET` — the pre-existing repository-wide
        secret, kept ONLY as a backward-compatible fallback.
   Presence is decided per source in that order; secret VALUES are never
   compared to each other, so this can never reveal whether two projects
   share a secret.

2. `classify_access()` — say WHAT a probe response means, so a protection
   challenge is never misreported as a broken application route. See
   `AccessVerdict` for the four outcomes.

No function here returns, logs, or formats a secret value.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PORTALS = ("customer", "vendor", "admin")

#: Caller-scoped variable: deploy-staging.yml resolves the portal's secret via
#: the job matrix and exposes only that one to the job.
PORTAL_SCOPED_ENV = "VERCEL_PORTAL_BYPASS_SECRET"

#: Explicit per-project names (local/manual runs).
PORTAL_ENV_BY_PORTAL = {
    "customer": "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER",
    "vendor": "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR",
    "admin": "VERCEL_AUTOMATION_BYPASS_SECRET_ADMIN",
}

#: Pre-existing repository-wide secret — backward-compatible fallback only.
FALLBACK_ENV = "VERCEL_AUTOMATION_BYPASS_SECRET"

#: Substrings that identify a Vercel SSO / Deployment Protection challenge
#: rather than an application response. Matched case-insensitively against the
#: Location header and the response body.
SSO_MARKERS = (
    "vercel.com/sso-api",
    "vercel.com/login",
    "_vercel_sso_nonce",
    "authentication required",
    "log in to vercel",
    "sign in to vercel",
)

#: "ok" — HTTP 200 carrying an application JSON body; caller proceeds to the
#:        deployed-health assertions (vercel_preview_health_verify.py).
#: "blocked_external" — Vercel Deployment Protection challenge. The bypass
#:        secret is missing, invalid, or issued for a different project. NOT an
#:        application failure.
#: "not_json" — HTTP 200 but the body is not a JSON object: a real
#:        application/verifier failure.
#: "app_error" — HTTP 5xx from the application itself.
#: "http_error" — any other non-2xx that is not a protection challenge.
Verdict = str


@dataclass(frozen=True)
class BypassSource:
    """Which env var supplied the bypass secret — never the value itself."""

    #: "portal_scoped" | "portal_specific" | "fallback" | "none"
    kind: str
    #: Name of the env var used, or None when no secret is configured.
    env_name: str | None

    @property
    def present(self) -> bool:
        return self.kind != "none"


@dataclass(frozen=True)
class AccessVerdict:
    verdict: Verdict
    #: Safe, secret-free explanation for CI logs.
    detail: str


def resolve_bypass_source(env: dict[str, str], portal: str) -> BypassSource:
    """Pick the bypass env var for `portal`, highest precedence first.

    Only presence (non-empty after strip) is considered, one source at a
    time — secret values are never compared, so this cannot leak whether two
    portals share a secret.
    """
    if portal not in PORTALS:
        raise ValueError(f"unknown portal: {portal!r}")

    scoped = (env.get(PORTAL_SCOPED_ENV) or "").strip()
    if scoped:
        return BypassSource("portal_scoped", PORTAL_SCOPED_ENV)

    portal_env = PORTAL_ENV_BY_PORTAL[portal]
    if (env.get(portal_env) or "").strip():
        return BypassSource("portal_specific", portal_env)

    if (env.get(FALLBACK_ENV) or "").strip():
        return BypassSource("fallback", FALLBACK_ENV)

    return BypassSource("none", None)


def _has_sso_marker(*values: str) -> bool:
    haystack = "\n".join(v for v in values if v).lower()
    return any(marker in haystack for marker in SSO_MARKERS)


def _is_vercel_host(location: str) -> bool:
    if not location:
        return False
    try:
        host = (urlparse(location).hostname or "").lower()
    except ValueError:
        return False
    return host == "vercel.com" or host.endswith(".vercel.com")


def classify_access(
    *,
    http_status: int,
    location: str = "",
    body: str = "",
    bypass_present: bool = False,
) -> AccessVerdict:
    """Classify one probe response. Fails closed: never reports a challenge as OK.

    Deliberately distinguishes a protection challenge from an application
    fault so CI never again reports "customer health broken" for what is a
    Vercel access-configuration problem (run #31).
    """
    challenge = _has_sso_marker(location, body) or _is_vercel_host(location)

    if challenge:
        if bypass_present:
            hint = (
                "bypass secret was sent but rejected — it is missing, expired, or "
                "was issued for a different Vercel project than this portal's"
            )
        else:
            hint = (
                "no bypass secret configured for this portal — set the Vercel "
                "'Protection Bypass for Automation' secret"
            )
        return AccessVerdict(
            "blocked_external",
            f"Vercel Deployment Protection automation bypass missing or invalid "
            f"(HTTP {http_status}); {hint}",
        )

    if 300 <= http_status < 400:
        return AccessVerdict(
            "http_error",
            f"unexpected redirect (HTTP {http_status}) that is not a Vercel "
            "protection challenge — the application redirected the health route",
        )

    if http_status >= 500:
        return AccessVerdict(
            "app_error",
            f"application runtime failure (HTTP {http_status}) — the deployed app "
            "returned a server error, not a protection challenge",
        )

    if http_status < 200 or http_status >= 300:
        return AccessVerdict("http_error", f"unexpected HTTP {http_status}")

    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return AccessVerdict(
            "not_json",
            "HTTP 200 but the body is not JSON — application/verifier failure, "
            "not a protection challenge",
        )
    if not isinstance(parsed, dict):
        return AccessVerdict(
            "not_json", "HTTP 200 but the JSON body is not an object — malformed health"
        )

    return AccessVerdict("ok", "reachable — application JSON body received")


def _read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify a Vercel Preview health probe response (secret-free output)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve-source", help="Print the bypass source kind for a portal")
    resolve.add_argument("--portal", required=True, choices=list(PORTALS))

    classify = sub.add_parser("classify", help="Print the access verdict word")
    classify.add_argument("--http-status", type=int, required=True)
    classify.add_argument("--location", default="")
    classify.add_argument("--body-file", type=Path)
    classify.add_argument(
        "--bypass-present",
        default="0",
        help="1 when a bypass secret was sent (value is never passed in)",
    )
    classify.add_argument(
        "--print-detail", action="store_true", help="Also print the safe detail line"
    )

    args = parser.parse_args(argv)

    if args.command == "resolve-source":
        import os

        source = resolve_bypass_source(dict(os.environ), args.portal)
        # Prints only the source kind and env var NAME — never a value.
        print(f"{source.kind}\t{source.env_name or ''}")
        return 0

    result = classify_access(
        http_status=args.http_status,
        location=args.location,
        body=_read_text(args.body_file),
        bypass_present=str(args.bypass_present).strip() in {"1", "true", "yes"},
    )
    print(result.verdict)
    if args.print_detail:
        print(result.detail, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
