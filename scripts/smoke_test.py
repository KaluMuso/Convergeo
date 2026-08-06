#!/usr/bin/env python3
"""Post-deployment synthetic smoke test for Vergeo5.

Lightweight, CI/CD-friendly checks across API health, DB, search, OTP rate
limiters, and guest cart flows. Safe for staging and production: never executes
payments, never completes checkout, and does not send OTP SMS unless explicitly
opted in.

Usage:
  API_BASE_URL=https://api.staging.vergeo5.com \\
  SUPABASE_URL=https://<ref>.supabase.co \\
  SUPABASE_ANON_KEY=<anon> \\
  SMOKE_TEST_PHONE=+260971234567 \\
  uv run --directory services/api python ../scripts/smoke_test.py

  # Plan only (no network):
  uv run --directory services/api python ../scripts/smoke_test.py --dry-run

Environment:
  API_BASE_URL            FastAPI origin (default https://api.vergeo5.com)
  CUSTOMER_URL            Customer PWA (default https://www.vergeo5.com)
  VENDOR_URL              Vendor SPA (default https://vendor.vergeo5.com)
  ADMIN_URL               Admin SPA (default https://admin.vergeo5.com)
  SUPABASE_URL            For categories DB probe + optional OTP send
  SUPABASE_ANON_KEY       Anon key for Supabase REST / Auth OTP
  SMOKE_CATEGORIES_PATH   API categories path (default /categories)
  SMOKE_SEARCH_QUERY      Search probe term (default test)
  SMOKE_TEST_PHONE        E.164 phone for OTP quota probe (optional)
  SMOKE_SEND_OTP          Set 1/true to call Supabase Auth OTP (default off)
  SMOKE_TEST_LISTING_ID   Optional listing UUID for add-to-cart probe
  SMOKE_TEST_ACCESS_TOKEN Optional bearer token (else guest cart)
  HTTP_TIMEOUT_SECONDS    Per-request timeout (default 30)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

import httpx

SMOKE_USER_AGENT = "Vergeo5-SmokeTest/1.0"
SMOKE_HEADER = "X-Vergeo-Smoke-Test"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    api_base_url: str
    customer_url: str
    vendor_url: str
    admin_url: str
    supabase_url: str
    supabase_anon_key: str
    categories_path: str
    search_query: str
    smoke_phone: str
    send_otp: bool
    listing_id: str
    access_token: str
    timeout_seconds: float
    dry_run: bool


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: str = ""


@dataclass
class SmokeReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(item.status == CheckStatus.FAIL for item in self.results)


class _Colors:
    def __init__(self, enabled: bool) -> None:
        if enabled:
            self.green = "\033[32m"
            self.red = "\033[31m"
            self.yellow = "\033[33m"
            self.cyan = "\033[36m"
            self.bold = "\033[1m"
            self.reset = "\033[0m"
        else:
            self.green = self.red = self.yellow = self.cyan = self.bold = self.reset = ""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    if digits.startswith("+"):
        return digits
    if digits.startswith("260"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+260{digits[1:]}"
    return f"+{digits}"


def _load_config(*, dry_run: bool) -> SmokeConfig:
    return SmokeConfig(
        api_base_url=os.environ.get("API_BASE_URL", "https://api.vergeo5.com").rstrip("/"),
        customer_url=os.environ.get("CUSTOMER_URL", "https://www.vergeo5.com").rstrip("/"),
        vendor_url=os.environ.get("VENDOR_URL", "https://vendor.vergeo5.com").rstrip("/"),
        admin_url=os.environ.get("ADMIN_URL", "https://admin.vergeo5.com").rstrip("/"),
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", "").strip(),
        categories_path=os.environ.get("SMOKE_CATEGORIES_PATH", "/categories"),
        search_query=os.environ.get("SMOKE_SEARCH_QUERY", "test").strip() or "test",
        smoke_phone=_normalize_phone(os.environ.get("SMOKE_TEST_PHONE", "").strip())
        if os.environ.get("SMOKE_TEST_PHONE", "").strip()
        else "",
        send_otp=_truthy(os.environ.get("SMOKE_SEND_OTP")),
        listing_id=os.environ.get("SMOKE_TEST_LISTING_ID", "").strip(),
        access_token=os.environ.get("SMOKE_TEST_ACCESS_TOKEN", "").strip(),
        timeout_seconds=float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30")),
        dry_run=dry_run,
    )


def _smoke_headers() -> dict[str, str]:
    return {
        SMOKE_HEADER: "1",
        "User-Agent": SMOKE_USER_AGENT,
        "Accept": "application/json",
    }


def _record(report: SmokeReport, name: str, status: CheckStatus, detail: str = "") -> None:
    report.results.append(CheckResult(name=name, status=status, detail=detail))


def _check_http_status(
    report: SmokeReport,
    *,
    name: str,
    client: httpx.Client,
    url: str,
    expected: int | set[int] = 200,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response | None:
    if isinstance(expected, int):
        expected_set = {expected}
    else:
        expected_set = expected

    try:
        response = client.request(method, url, json=json_body, headers=headers)
    except httpx.HTTPError as exc:
        _record(report, name, CheckStatus.FAIL, f"network error: {exc}")
        return None

    if response.status_code not in expected_set:
        _record(
            report,
            name,
            CheckStatus.FAIL,
            f"HTTP {response.status_code} (expected {sorted(expected_set)})",
        )
        return response

    _record(report, name, CheckStatus.PASS, f"HTTP {response.status_code}")
    return response


def _categories_probe(config: SmokeConfig, client: httpx.Client, report: SmokeReport) -> None:
    name = "DB GET /categories"
    api_url = f"{config.api_base_url}{config.categories_path}"

    try:
        api_response = client.get(api_url)
    except httpx.HTTPError as exc:
        _record(report, name, CheckStatus.FAIL, f"network error: {exc}")
        return

    if api_response.status_code == 200:
        _record(report, name, CheckStatus.PASS, "HTTP 200")
        return

    if not config.supabase_url or not config.supabase_anon_key:
        _record(
            report,
            name,
            CheckStatus.FAIL,
            (
                f"HTTP {api_response.status_code}; "
                "set SUPABASE_URL/SUPABASE_ANON_KEY for REST fallback"
            ),
        )
        return

    rest_url = (
        f"{config.supabase_url}/rest/v1/categories"
        f"?{urlencode({'select': 'id', 'limit': '1'})}"
    )
    headers = {
        **_smoke_headers(),
        "apikey": config.supabase_anon_key,
        "Authorization": f"Bearer {config.supabase_anon_key}",
    }
    _check_http_status(
        report,
        name="DB categories (Supabase REST)",
        client=client,
        url=rest_url,
        headers=headers,
    )


def _search_probe(config: SmokeConfig, client: httpx.Client, report: SmokeReport) -> None:
    query = urlencode({"q": config.search_query, "limit": "5"})
    url = f"{config.api_base_url}/search?{query}"
    response = _check_http_status(report, name="Search GET /search", client=client, url=url)
    if response is None or response.status_code != 200:
        return

    try:
        body = response.json()
    except json.JSONDecodeError:
        report.results[-1] = CheckResult(
            name="Search GET /search",
            status=CheckStatus.FAIL,
            detail="response is not JSON",
        )
        return

    if not isinstance(body, dict):
        report.results[-1] = CheckResult(
            name="Search GET /search",
            status=CheckStatus.FAIL,
            detail="response JSON is not an object",
        )
        return

    if "items" not in body and "total" not in body:
        report.results[-1] = CheckResult(
            name="Search GET /search",
            status=CheckStatus.FAIL,
            detail="missing items/total fields",
        )
        return

    degraded = body.get("degraded")
    detail = (
        f"query={config.search_query!r} total={body.get('total', '?')} "
        f"degraded={degraded!r}"
    )
    report.results[-1] = CheckResult(
        name="Search GET /search",
        status=CheckStatus.PASS,
        detail=detail,
    )


def _otp_quota_probe(config: SmokeConfig, client: httpx.Client, report: SmokeReport) -> None:
    if not config.smoke_phone:
        _record(report, "Auth OTP quota", CheckStatus.SKIP, "SMOKE_TEST_PHONE unset")
        return

    url = f"{config.api_base_url}/auth/guard/otp-quota"
    response = _check_http_status(
        report,
        name="Auth OTP quota",
        client=client,
        url=url,
        method="POST",
        json_body={"phone": config.smoke_phone},
    )
    if response is None or response.status_code != 200:
        return

    try:
        body = response.json()
    except json.JSONDecodeError:
        report.results[-1] = CheckResult(
            name="Auth OTP quota",
            status=CheckStatus.FAIL,
            detail="response is not JSON",
        )
        return

    if body.get("allowed") is not True:
        report.results[-1] = CheckResult(
            name="Auth OTP quota",
            status=CheckStatus.FAIL,
            detail=(
                f"allowed={body.get('allowed')!r} message_key={body.get('message_key')!r}"
            ),
        )
        return

    report.results[-1] = CheckResult(
        name="Auth OTP quota",
        status=CheckStatus.PASS,
        detail=f"phone={config.smoke_phone}",
    )


def _otp_send_probe(config: SmokeConfig, client: httpx.Client, report: SmokeReport) -> None:
    if not config.send_otp:
        _record(report, "Auth OTP dispatch", CheckStatus.SKIP, "SMOKE_SEND_OTP not enabled")
        return
    if not config.smoke_phone:
        _record(report, "Auth OTP dispatch", CheckStatus.SKIP, "SMOKE_TEST_PHONE unset")
        return
    if not config.supabase_url or not config.supabase_anon_key:
        _record(
            report,
            "Auth OTP dispatch",
            CheckStatus.SKIP,
            "SUPABASE_URL/SUPABASE_ANON_KEY required for Auth OTP",
        )
        return

    url = f"{config.supabase_url}/auth/v1/otp"
    headers = {
        **_smoke_headers(),
        "apikey": config.supabase_anon_key,
        "Authorization": f"Bearer {config.supabase_anon_key}",
        "Content-Type": "application/json",
    }
    response = _check_http_status(
        report,
        name="Auth OTP dispatch",
        client=client,
        url=url,
        method="POST",
        json_body={"phone": config.smoke_phone, "create_user": False},
        headers=headers,
    )
    if response is None or response.status_code != 200:
        return

    report.results[-1] = CheckResult(
        name="Auth OTP dispatch",
        status=CheckStatus.PASS,
        detail="Supabase /auth/v1/otp accepted",
    )


def _cart_flow_probe(config: SmokeConfig, client: httpx.Client, report: SmokeReport) -> None:
    headers = _smoke_headers()
    if config.access_token:
        headers["Authorization"] = f"Bearer {config.access_token}"

    cart_url = f"{config.api_base_url}/cart"
    response = _check_http_status(
        report,
        name="Cart create/get",
        client=client,
        url=cart_url,
        headers=headers,
    )
    if response is None or response.status_code != 200:
        return

    try:
        cart_body = response.json()
    except json.JSONDecodeError:
        report.results[-1] = CheckResult(
            name="Cart create/get",
            status=CheckStatus.FAIL,
            detail="response is not JSON",
        )
        return

    cart_id = cart_body.get("cart_id")
    if not isinstance(cart_id, str) or not cart_id:
        report.results[-1] = CheckResult(
            name="Cart create/get",
            status=CheckStatus.FAIL,
            detail="missing cart_id",
        )
        return

    if not config.listing_id:
        _record(report, "Cart add item", CheckStatus.SKIP, "SMOKE_TEST_LISTING_ID unset")
        _record(report, "Cart clear", CheckStatus.SKIP, "no item added")
        return

    add_url = f"{config.api_base_url}/cart/items"
    add_response = _check_http_status(
        report,
        name="Cart add item",
        client=client,
        url=add_url,
        method="POST",
        json_body={"listing_id": config.listing_id, "qty": 1},
        headers=headers,
    )
    if add_response is None or add_response.status_code != 200:
        return

    delete_url = f"{config.api_base_url}/cart/items/{config.listing_id}"
    _check_http_status(
        report,
        name="Cart clear",
        client=client,
        url=delete_url,
        method="DELETE",
        headers=headers,
    )


def _frontend_health(
    config: SmokeConfig,
    client: httpx.Client,
    report: SmokeReport,
    *,
    name: str,
    base_url: str,
    allow_403: bool = False,
) -> None:
    url = f"{base_url}/en/health"
    expected = {200, 403} if allow_403 else {200}
    _check_http_status(report, name=name, client=client, url=url, expected=expected)


def run_smoke(config: SmokeConfig) -> SmokeReport:
    report = SmokeReport()

    if config.dry_run:
        planned = [
            f"API GET {config.api_base_url}/health",
            f"API GET {config.api_base_url}/healthz",
            f"Customer GET {config.customer_url}/en/health",
            f"Vendor GET {config.vendor_url}/en/health",
            f"Admin GET {config.admin_url}/en/health",
            f"DB GET {config.api_base_url}{config.categories_path}",
            f"Search GET {config.api_base_url}/search?q={config.search_query}",
            "Auth OTP quota (if SMOKE_TEST_PHONE set)",
            "Cart flow (guest or bearer)",
        ]
        for step in planned:
            _record(report, step, CheckStatus.SKIP, "dry-run")
        return report

    with httpx.Client(
        timeout=config.timeout_seconds,
        headers=_smoke_headers(),
        follow_redirects=True,
    ) as client:
        _check_http_status(
            report,
            name="API GET /health",
            client=client,
            url=f"{config.api_base_url}/health",
        )
        _check_http_status(
            report,
            name="API GET /healthz",
            client=client,
            url=f"{config.api_base_url}/healthz",
        )
        _frontend_health(
            config,
            client,
            report,
            name="Customer PWA /en/health",
            base_url=config.customer_url,
        )
        _frontend_health(
            config,
            client,
            report,
            name="Vendor SPA /en/health",
            base_url=config.vendor_url,
        )
        _frontend_health(
            config,
            client,
            report,
            name="Admin SPA /en/health",
            base_url=config.admin_url,
            allow_403=True,
        )
        _categories_probe(config, client, report)
        _search_probe(config, client, report)
        _otp_quota_probe(config, client, report)
        _otp_send_probe(config, client, report)
        _cart_flow_probe(config, client, report)

    return report


def _status_symbol(status: CheckStatus, colors: _Colors) -> str:
    if status == CheckStatus.PASS:
        return f"{colors.green}✓{colors.reset}"
    if status == CheckStatus.FAIL:
        return f"{colors.red}✗{colors.reset}"
    return f"{colors.yellow}○{colors.reset}"


def _print_report(report: SmokeReport, config: SmokeConfig, colors: _Colors) -> None:
    print(f"{colors.bold}Vergeo5 synthetic smoke test{colors.reset}")
    print(f"API_BASE_URL={config.api_base_url}")
    if config.dry_run:
        print(f"{colors.yellow}DRY-RUN — no network probes executed{colors.reset}")
    print()

    name_width = max((len(item.name) for item in report.results), default=20)
    for item in report.results:
        symbol = _status_symbol(item.status, colors)
        status = item.status.value
        if item.status == CheckStatus.PASS:
            status = f"{colors.green}{status}{colors.reset}"
        elif item.status == CheckStatus.FAIL:
            status = f"{colors.red}{status}{colors.reset}"
        else:
            status = f"{colors.yellow}{status}{colors.reset}"

        line = f"  {symbol}  {item.name.ljust(name_width)}  {status}"
        if item.detail:
            line += f"  {colors.cyan}{item.detail}{colors.reset}"
        print(line)

    print()
    if report.failed:
        print(f"{colors.red}{colors.bold}OVERALL: FAIL{colors.reset}")
    else:
        print(f"{colors.green}{colors.bold}OVERALL: PASS{colors.reset}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vergeo5 post-deploy synthetic smoke test")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned checks without network I/O",
    )
    args = parser.parse_args(argv)

    config = _load_config(dry_run=args.dry_run)
    colors = _Colors(enabled=sys.stdout.isatty() and not _truthy(os.environ.get("NO_COLOR")))
    report = run_smoke(config)
    _print_report(report, config, colors)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
