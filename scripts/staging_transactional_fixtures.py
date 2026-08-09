#!/usr/bin/env python3
"""Plan or apply staging transactional fixture states (post static seed).

Usage:
  STAGING_SUPABASE_PROJECT_ID=iyasmrmbcrvlfxpzescb \\
    python scripts/staging_transactional_fixtures.py --env staging --state cod_placed --plan

Service-drivable states (checkout/payment service boundary):
  prepaid_awaiting_payment, payment_failed, payment_expired, cod_placed

External / harness-only (never direct ledger inserts):
  processing, delivered, return_eligible, dispute_held
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.env_guards import StagingIsolationError  # noqa: E402
from app.staging.synthetic_contract import guard_seed_targets  # noqa: E402
from app.staging.transactional import (  # noqa: E402
    TransactionalState,
    assert_transactional_safe,
    classify_state,
    is_service_drivable,
    plan_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging transactional fixture driver.")
    parser.add_argument("--env", choices=("staging",), required=True)
    parser.add_argument(
        "--state",
        choices=[state.value for state in TransactionalState],
        required=True,
    )
    parser.add_argument("--plan", action="store_true", help="Print the driver plan (default).")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reserved for post-deploy QA; service states require API runtime.",
    )
    args = parser.parse_args()

    staging_project_id = os.environ.get("STAGING_SUPABASE_PROJECT_ID", "")
    api_host = os.environ.get("STAGING_API_HOST") or os.environ.get("STAGING_API_BASE_URL", "")

    try:
        guard_seed_targets(
            supabase_url=os.environ.get("STAGING_SUPABASE_URL", ""),
            db_url=os.environ.get("SUPABASE_DB_URL", ""),
            api_host=api_host,
            staging_project_id=staging_project_id,
            require_exact_project=args.apply,
        )
        if staging_project_id or args.apply:
            assert_transactional_safe(
                project_ref=staging_project_id or None,
                api_host=api_host,
                require_exact_project=args.apply,
            )
        state = TransactionalState(args.state)
        spec = classify_state(args.state)
        plan = plan_state(state)
    except StagingIsolationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(plan, indent=2, sort_keys=True))

    if args.apply:
        if not is_service_drivable(state):
            print(
                f"ERROR: state {state.value} is external/harness-only — "
                "use Lenco sandbox or payment-mock harness after staging deploy",
                file=sys.stderr,
            )
            return 1
        print(
            "ERROR: --apply requires the staging API runtime at the deployed SHA; "
            "run this driver from the QA harness that calls checkout/payment services.",
            file=sys.stderr,
        )
        return 1

    if spec.delivery == "external":
        print(
            f"NOTE: {state.value} is classified external ({spec.summary})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
