# n8n Activation Runbook (VD-P01…P03)

**Purpose:** bring the committed `infra/n8n/*.json` workflows live and record which
are active. Logic lives in the API — each workflow calls an internal-token endpoint.

> **Prerequisite (learned live 2026-07-21).** Every internal tick is **fail-closed**:
> `app/core/internal_token.resolve_internal_token` returns **503** in `ENV=production`
> when the endpoint's `INTERNAL_*_TOKEN` is missing/default. And the ticks do real DB
> work, so `SUPABASE_DB_URL` **must** be set to the Supabase **session pooler** (5432,
> not 6543) — if it is blank the API falls back to a dead local DSN and every tick 500s
> with "couldn't get a connection after 10.00 sec" (this also shows as `/search
degraded=true`). Fix that first; see `infra/.env.example`.
>
> To activate a workflow you need, on **both** sides: (1) its `INTERNAL_*_TOKEN` on the
> API host, and (2) a matching n8n **httpHeaderAuth** credential named `X-Internal-Token`.

## Founder decisions

- **Wave A — activate now.** No money movement.
- **Wave B — HELD** (`release-job`, `order-jobs`, `event-release`, `tickets-issue`,
  `tickets-release`) until the Lenco **sandbox** money path is proven (VB-P01…P06)
  **and** legal **F4** (NPS-Act escrow) clears. Do not activate before both are green.
- **operational-nudges — HELD** until real vendors onboard (it enqueues outward SMS/
  email that the live dispatch workflow delivers; keeping it off avoids messaging the
  seeded demo vendors).

## Token → workflow map

| Workflow JSON                                                               | API endpoint                                                           | Token env var                                                      | Class                  |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------ | ---------------------- |
| `notification-dispatch.json`                                                | `/internal/dispatch/tick`                                              | `INTERNAL_DISPATCH_TOKEN`                                          | LIVE ✓                 |
| `reconciliation.json` (bundle)                                              | `/internal/reconciliation/*` + `/internal/payment-sweeper/tick`        | `INTERNAL_RECONCILIATION_TOKEN` / `INTERNAL_PAYMENT_SWEEPER_TOKEN` | LIVE ✓                 |
| `reservation-sweeper.json`                                                  | `/internal/stock-sweeper/tick`                                         | `INTERNAL_STOCK_SWEEPER_TOKEN`                                     | Wave A                 |
| `embeddings-cron.json`                                                      | `/internal/embeddings/tick`                                            | `INTERNAL_EMBEDDINGS_TOKEN`                                        | Wave A                 |
| `admin-digest.json`                                                         | `/internal/digest`                                                     | `INTERNAL_DIGEST_TOKEN`                                            | Wave A                 |
| `analytics-retention.json`                                                  | `/internal/analytics/retention-tick`                                   | `INTERNAL_ANALYTICS_TOKEN`                                         | Wave A                 |
| `kyc-nudge` / `low-stock-alert` / `review-request` / `payout-failure-alert` | `/internal/n8n/*/tick`                                                 | `INTERNAL_N8N_TOKEN`                                               | Wave A (nudges — HELD) |
| `uptime-alert.json`                                                         | inbound webhook                                                        | `UPTIME_WEBHOOK_SECRET` (n8n only)                                 | Wave A                 |
| `release-job.json`                                                          | `/internal/release-job/tick`                                           | `INTERNAL_RELEASE_JOB_TOKEN`                                       | Wave B                 |
| `order-jobs.json`                                                           | `/internal/order-jobs/{auto-confirm,auto-release}`                     | `INTERNAL_ORDER_JOBS_TOKEN`                                        | Wave B                 |
| `event-release.json`                                                        | `/internal/event-release/tick`                                         | `INTERNAL_EVENT_RELEASE_TOKEN`                                     | Wave B                 |
| `tickets-issue.json` / `tickets-release.json`                               | `/internal/tickets/{issue,release}-tick`                               | `INTERNAL_TICKETS_ISSUE_TOKEN`                                     | Wave B                 |
| `abandoned-cart.json` / `funnel-abandon.json`                               | `/internal/n8n/abandoned-carts/tick` / `/internal/funnel/abandon-tick` | `INTERNAL_N8N_TOKEN` / `INTERNAL_FUNNEL_TOKEN`                     | Keep OFF (flag-gated)  |

## Per-workflow activation

1. `openssl rand -hex 32` → one secret per token env var.
2. Add `INTERNAL_<X>_TOKEN=<secret>` to the host `--env-file` and **recreate** the
   container (`bash /root/redeploy-api.sh` — a plain `docker restart` does NOT reload
   the env file). Verify: `curl -s -o /dev/null -w "%{http_code}\n" -XPOST
https://api.vergeo5.com/internal/<path> -H 'X-Internal-Token: wrong'` → **401**
   (set), not **503** (unset).
3. n8n → Credentials → Header Auth → name `X-Internal-Token`, value = the same secret.
4. Import the workflow, point its HTTP node(s) at that credential, toggle **Active**,
   and confirm the first execution is `success`.

## Activation status (2026-07-23)

Live Wave A (production):

| Workflow                     | ID                 | Active                                                           |
| ---------------------------- | ------------------ | ---------------------------------------------------------------- |
| notification dispatch        | `sevKtX1AmimQCWsG` | yes                                                              |
| payment reconciliation crons | `C1MpTNjrfLACMG3f` | yes (published 2026-07-23)                                       |
| reservation sweeper          | `F25zEWiPoIveARys` | yes                                                              |
| embeddings cron              | `oqjfSdMXClfsf3qd` | yes                                                              |
| admin digest                 | `rb5d4LHlXAOqkfPX` | yes                                                              |
| analytics retention          | `8drZTFO79pwMPfZy` | yes                                                              |
| operational nudges           | `zkIe2zW72qp5fcli` | yes (held per policy until real vendors — consider unpublishing) |

Held (credentials / policy):

| Workflow                                             | ID                 | Reason                               |
| ---------------------------------------------------- | ------------------ | ------------------------------------ |
| shared error alert                                   | `LVuHqWgT1tqjYOtc` | No WhatsApp output node bound        |
| database backup                                      | `OAdOD4kmIbSNehkJ` | Needs SSH + OCI Object Storage creds |
| Wave B (release, tickets, order-jobs, event-release) | —                  | F4 + F9b sandbox                     |

Record activation date + operator per workflow in `docs/production-readiness/2026-07-19/vision-audit/evidence/` as they go live.
