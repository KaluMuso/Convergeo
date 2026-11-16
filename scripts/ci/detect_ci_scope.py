#!/usr/bin/env python3
"""Decide which CI tiers a change set needs (CI-SPEED).

Required status checks must ALWAYS report, so no workflow uses `paths:` filters.
Instead a cheap `changes` job runs this script and every expensive job gates itself
with a job-level `if:` on one of the outputs below. A job skipped by `if:` reports
"skipped", which GitHub counts as passing for required checks (unlike a workflow
skipped by `paths:`, which stays pending forever).

Fail-open by design: any doubt (missing base, diff failure, workflow/CI-script
change, the isolated coordinator review lane) turns EVERYTHING on. Pushes to
master and the nightly schedule always run every tier, so a gate that a pull
request skipped is still enforced on master before anything ships.

Outputs (written as `name=true|false` lines to $GITHUB_OUTPUT and echoed):

  docs_only     only documentation changed (see DOC_ONLY below)
  run_js        JavaScript / TypeScript
  run_python    Python API shards (docs_only -> reduced doc-truth run instead)
  run_security  Security gates (headers + authz matrix)
  run_db_light  Migration replay, RLS matrix, Money DB-trigger integration
  run_typegen   Database / typegen drift (~45 min migration-ledger proof)
  run_heavy     critical / financial real-stack + coordinator acceptance
  run_perf      Bundle, image lint & Lighthouse (perf.yml)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable

# Documentation that cannot influence any gate. Only these file shapes count:
# markdown anywhere, anything under prompts/, and non-executable doc assets.
# Other files under docs/ (txt/sql/json) are read by tests and real-stack gates
# (for example docs/ops/lenco/f2-required-nodes.txt), so they are NOT docs-only.
DOC_ONLY = re.compile(
    r"^(?:.*\.mdx?$|prompts/.*|docs/.*\.(?:md|mdx|pdf|png|jpe?g|svg|html)$)"
)

# Anything here can change how every gate behaves, so it forces the full set.
INFRA = re.compile(
    r"^(?:\.github/|scripts/ci/|scripts/qa/|scripts/gen-types\.sh$|infra/|policy/|"
    r"lefthook\.yml$|commitlint\.config\.cjs$|\.nvmrc$|"
    r"services/api/(?:pyproject\.toml|uv\.lock|\.python-version|mypy\.ini|ruff\.toml)$)"
)

FRONTEND = re.compile(
    r"^(?:apps/|packages/|e2e/|patches/|load/|package\.json$|pnpm-lock\.yaml$|"
    r"pnpm-workspace\.yaml$|turbo\.json$|lighthouserc\.json$|vercel\.json$|"
    r"eslint\.config\.mjs$|tsconfig\.base\.json$)"
)

# packages/types/src/db.ts is generated from the schema by the typegen job.
DB = re.compile(
    r"^(?:supabase/|packages/types/src/db\.ts$|scripts/(?:db|seed)/|scripts/seed.*\.py$)"
)

API = re.compile(r"^(?:services/|infra/api\.Dockerfile$)")

# Money, auth and migration paths. A change here keeps every real-stack tier on,
# whatever branch the pull request targets (release-train lesson: the merge that
# bypassed real-stack tests only touched release-targeted money paths).
MONEY = re.compile(
    r"^(?:"
    r"services/api/app/services/(?:payments|ledger|escrow|orders|refunds|payouts|cod)"
    r"|services/api/app/routers/(?:cod|checkout|payments_card|payment_status|orders_create|"
    r"order_|customer_orders|refunds|returns|vendor_payouts|vendor_orders|"
    r"internal_payouts|internal_payment|internal_order|internal_reconciliation|"
    r"internal_release|webhooks_lenco|auth_guard|admin_orders|admin_roles|admin_governance)"
    r"|services/api/app/core/auth"
    r"|services/api/app/(?:deps|db|settings)\.py$"
    r"|services/api/app/middleware/"
    r"|services/api/tests/rls/"
    r"|supabase/migrations/"
    r"|supabase/functions/"
    r"|supabase/config\.toml$"
    r"|.*(?:^|/)auth[^/]*(?:/|\.py$|\.tsx?$)"
    r")"
)

COORDINATOR_REVIEW_PREFIX = "codex/coordinator-ci-review-"

OUTPUTS = (
    "docs_only",
    "run_js",
    "run_python",
    "run_security",
    "run_db_light",
    "run_typegen",
    "run_heavy",
    "run_perf",
)


def _any(pattern: re.Pattern[str], files: Iterable[str]) -> bool:
    return any(pattern.match(path) for path in files)


def classify(
    files: list[str] | None,
    *,
    event_name: str,
    base_ref: str = "",
    head_ref: str = "",
) -> dict[str, bool]:
    """Return the tier decisions. `files=None` means the diff is unknown (fail open)."""
    everything = {name: True for name in OUTPUTS}
    everything["docs_only"] = False

    if event_name != "pull_request":
        return everything  # master pushes, nightly schedule, manual runs
    if files is None or head_ref.startswith(COORDINATOR_REVIEW_PREFIX):
        return everything

    docs_only = bool(files) and all(DOC_ONLY.match(path) for path in files)
    if docs_only:
        return {
            "docs_only": True,
            "run_js": False,
            "run_python": True,  # reduced to the doc-truth tests by the workflow
            "run_security": False,
            "run_db_light": False,
            "run_typegen": False,
            "run_heavy": False,
            "run_perf": False,
        }

    infra = _any(INFRA, files)
    if infra:
        return everything

    frontend = _any(FRONTEND, files)
    api = _any(API, files)
    db = _any(DB, files)
    money = _any(MONEY, files)
    to_master = base_ref == "master"
    backend = api or db  # anything that can change DB, money or API behaviour

    # A change set that matches no known category is unclassified: run everything.
    if not (frontend or backend):
        return everything

    run_db_light = backend
    # The 45 minute migration-ledger proof only depends on the schema and typegen
    # inputs. API-only changes cannot alter it, but the final gate into master
    # always runs everything for API changes.
    run_typegen = db or (api and to_master)
    run_heavy = backend and (to_master or money)
    run_perf = (frontend or backend) and (to_master or money)

    return {
        "docs_only": False,
        "run_js": True,
        "run_python": True,
        "run_security": True,
        "run_db_light": run_db_light,
        "run_typegen": run_typegen,
        "run_heavy": run_heavy,
        "run_perf": run_perf,
    }


def changed_files(base_sha: str) -> list[str] | None:
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha or ""):
        return None
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", base_sha, "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (subprocess.CalledProcessError, OSError):
        return None
    return [line for line in out.splitlines() if line]


def main() -> int:
    event = os.environ.get("EVENT_NAME", "")
    files = changed_files(os.environ.get("BASE_SHA", "")) if event == "pull_request" else []
    result = classify(
        files,
        event_name=event,
        base_ref=os.environ.get("BASE_REF", ""),
        head_ref=os.environ.get("HEAD_REF", ""),
    )
    lines = [f"{name}={'true' if result[name] else 'false'}" for name in OUTPUTS]
    print(f"event={event} base_ref={os.environ.get('BASE_REF', '')!r}")
    print(f"changed files: {'unknown (fail open)' if files is None else len(files)}")
    for line in lines:
        print(line)
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
