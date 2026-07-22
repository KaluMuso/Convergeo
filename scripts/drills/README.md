# Vergeo5 money drills

Operational verification harnesses for payment/escrow rails. **Sandbox only** — never production.

## Lenco sandbox money drill (CR-D)

```bash
# From repo root — dry-run / cassette (no F9b creds required)
uv run python scripts/drills/lenco_sandbox_money_drill.py --mode dry-run

# Live sandbox (F9b — staging/isolated stack)
export LENCO_ENV=sandbox
export PAYMENTS_ENABLED=true
export LENCO_API_TOKEN=<sandbox-token>
export SUPABASE_DB_URL=<isolated-db-url>
export DRILL_API_BASE_URL=https://staging-api.example.com
export DRILL_BUYER_TOKEN=<buyer-jwt>
export DRILL_ADMIN_TOKEN=<admin-jwt>          # release/refund leg
export DRILL_CHECKOUT_GROUP_ID=<uuid>         # pending checkout with cart
export DRILL_ORDER_ID=<uuid>                  # order in that checkout group
export INTERNAL_RECONCILIATION_TOKEN=...
export INTERNAL_RELEASE_JOB_TOKEN=...
export INTERNAL_PAYOUTS_TOKEN=...
export DRILL_ALLOW_SQL_SETUP=1                # ops: advance order to completed

uv run python scripts/drills/lenco_sandbox_money_drill.py --mode live
```

### Modes

| Mode             | When to use                                   |
| ---------------- | --------------------------------------------- |
| `auto` (default) | Live if creds present; else cassette dry-run  |
| `live`           | Full E2E against Lenco sandbox + API          |
| `cassette`       | Replay bundled fixture assertions only        |
| `dry-run`        | Preflight + cassette (CI / agent without F9b) |

### Outputs

- JSON report under `scripts/drills/reports/lenco-sandbox-drill-<timestamp>.json`
- Exit `0` = PASS · `1` = FAIL · `2` = BLOCKED_EXTERNAL (missing creds)

### Lint

```bash
cd services/api && uv run ruff check ../../scripts/drills/lenco_sandbox_money_drill.py
```

Full runbook: [`docs/ops/lenco/sandbox-money-drill.md`](../../docs/ops/lenco/sandbox-money-drill.md).
