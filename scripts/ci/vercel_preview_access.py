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

#: curl exit codes that represent a TRANSPORT failure worth retrying, verified
#: against libcurl's own CURLE_* enum (read from the installed libcurl, not
#: copied from memory). Each is a network-level condition that can succeed on a
#: later attempt:
#:    5 CURLE_COULDNT_RESOLVE_PROXY   6 CURLE_COULDNT_RESOLVE_HOST
#:    7 CURLE_COULDNT_CONNECT        18 CURLE_PARTIAL_FILE (transfer cut short)
#:   28 CURLE_OPERATION_TIMEDOUT     35 CURLE_SSL_CONNECT_ERROR
#:   52 CURLE_GOT_NOTHING            55 CURLE_SEND_ERROR
#:   56 CURLE_RECV_ERROR
#:
#: 35 is included deliberately: CURLE_SSL_CONNECT_ERROR is a failure DURING the
#: TLS handshake (a dropped connection mid-handshake, an edge node not yet
#: serving), which is transient. It is distinct from 60/77, which are
#: deterministic certificate/CA-file problems and must never be retried.
RETRYABLE_CURL_EXIT_CODES = frozenset({5, 6, 7, 18, 28, 35, 52, 55, 56})

#: Names for the codes this probe can plausibly encounter, so a CI log says
#: what happened instead of printing a bare integer. Codes absent here are
#: still classified (as non-retryable) — the set above is the only gate.
CURL_EXIT_NAMES = {
    3: "CURLE_URL_MALFORMAT",
    5: "CURLE_COULDNT_RESOLVE_PROXY",
    6: "CURLE_COULDNT_RESOLVE_HOST",
    7: "CURLE_COULDNT_CONNECT",
    18: "CURLE_PARTIAL_FILE",
    22: "CURLE_HTTP_RETURNED_ERROR",
    23: "CURLE_WRITE_ERROR",
    26: "CURLE_READ_ERROR",
    28: "CURLE_OPERATION_TIMEDOUT",
    35: "CURLE_SSL_CONNECT_ERROR",
    47: "CURLE_TOO_MANY_REDIRECTS",
    52: "CURLE_GOT_NOTHING",
    55: "CURLE_SEND_ERROR",
    56: "CURLE_RECV_ERROR",
    60: "CURLE_PEER_FAILED_VERIFICATION",
    77: "CURLE_SSL_CACERT_BADFILE",
}

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


@dataclass(frozen=True)
class CurlExitVerdict:
    """What one curl exit code means for the probe's retry decision.

    `kind` is the reported classification:
      HTTP_RESPONSE      — curl succeeded; an HTTP response exists and belongs
                           to classify_access(). Never retried, whatever the
                           status: a 302 protection challenge goes straight to
                           the Deployment Protection classifier.
      TRANSIENT_TRANSPORT — a network-level failure that may succeed on retry.
      NON_RETRYABLE_CURL  — a deterministic local/configuration/certificate
                           failure. Retrying cannot help, so fail immediately.
    """

    kind: str
    retryable: bool
    #: CURLE_* name when known, else "" — never any request/response content.
    name: str


def classify_curl_exit(code: int) -> CurlExitVerdict:
    """Classify a curl exit code for retry purposes. Fails safe: an unknown
    code is NON_RETRYABLE_CURL, so a novel deterministic error surfaces
    immediately rather than being retried five times."""
    name = CURL_EXIT_NAMES.get(code, "")
    if code == 0:
        return CurlExitVerdict("HTTP_RESPONSE", False, "CURLE_OK")
    if code in RETRYABLE_CURL_EXIT_CODES:
        return CurlExitVerdict("TRANSIENT_TRANSPORT", True, name)
    return CurlExitVerdict("NON_RETRYABLE_CURL", False, name)


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
            f"unexpected HTTP redirect from deployed health endpoint (HTTP {http_status}) — "
            "no Vercel SSO marker was detected in the Location header or body; see the "
            "sanitized redirect diagnostics for the target host/path",
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


#: Headers whose VALUE must never be printed. Presence may be reported as a
#: yes/no; the value itself never is.
NEVER_PRINT_HEADER_VALUES = frozenset(
    {
        "set-cookie",
        "cookie",
        "authorization",
        "proxy-authorization",
        "x-vercel-protection-bypass",
        "x-vercel-set-bypass-cookie",
        "www-authenticate",
    }
)


def _last_header_block(raw: str) -> list[str]:
    """Return the final response's header lines (curl -D can dump several)."""
    blocks: list[list[str]] = [[]]
    for line in raw.replace("\r", "").split("\n"):
        if line.strip() == "":
            if blocks[-1]:
                blocks.append([])
            continue
        if line.upper().startswith("HTTP/") and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    for block in reversed(blocks):
        if block:
            return block
    return []


def sanitize_location(value: str) -> str:
    """Reduce a Location header to `host + path`, dropping any query/fragment.

    A redirect target can carry credentials or tokens in its query string (a
    Vercel SSO challenge, for instance, carries a nonce), so only the host and
    path are ever surfaced.
    """
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except ValueError:
        return "[unparseable]"
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if not host:
        # Relative redirect: path only, still query-stripped.
        return f"path={path}"
    return f"host={host} path={path}"


def summarize_response_headers(raw: str) -> str:
    """One safe diagnostic line for a non-2xx response.

    Reports only: status line, whether a Location exists and its sanitized
    host/path, whether a Set-Cookie exists (never its value), and the server
    header. No header listed in NEVER_PRINT_HEADER_VALUES ever has its value
    rendered, and the Location query string is always stripped.
    """
    lines = _last_header_block(raw)
    if not lines:
        return "no response headers captured"

    status_line = lines[0].strip() if lines[0].upper().startswith("HTTP/") else ""
    location = ""
    has_set_cookie = False
    server = ""

    for line in lines[1:]:
        name, _, value = line.partition(":")
        key = name.strip().lower()
        if key == "location":
            location = value
        elif key == "set-cookie":
            has_set_cookie = True
        elif key == "server":
            server = value.strip()

    parts: list[str] = []
    if status_line:
        parts.append(f"status_line={status_line}")
    if location.strip():
        parts.append(f"location=present {sanitize_location(location)}")
    else:
        parts.append("location=absent")
    parts.append(f"set_cookie={'yes' if has_set_cookie else 'no'}")
    if server:
        parts.append(f"server={server}")
    return " | ".join(parts)


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

    curl_exit = sub.add_parser(
        "classify-curl-exit", help="Print '<kind>\\t<retryable 0|1>\\t<CURLE name>'"
    )
    curl_exit.add_argument("--code", type=int, required=True)

    headers = sub.add_parser(
        "summarize-headers",
        help="Print one safe diagnostic line for a non-2xx response (no secrets)",
    )
    headers.add_argument("--headers-file", type=Path, required=True)

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

    if args.command == "classify-curl-exit":
        exit_verdict = classify_curl_exit(args.code)
        print(f"{exit_verdict.kind}\t{1 if exit_verdict.retryable else 0}\t{exit_verdict.name}")
        return 0

    if args.command == "summarize-headers":
        print(summarize_response_headers(_read_text(args.headers_file)))
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
