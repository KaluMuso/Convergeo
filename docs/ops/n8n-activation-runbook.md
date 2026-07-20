# n8n Activation Runbook (VD-P01…P03)

**Purpose:** bring the committed `infra/n8n/*.json` workflows live. Today **2 of 20**
run (notification dispatch; the reconciliation-crons bundle = webhook-drain +
reconciliation-poll + payment-sweeper + daily-report). The other workflows are
authored but not imported/activated.

> **Founder decision (2026-07-20): Wave A may be activated now; Wave B is HELD.**
> The money & ticketing workflows (`release-job`, `order-jobs`, `event-release`,
> `tickets-issue`, `tickets-release`) stay **inactive** until the Lenco **sandbox**
> money path is proven (VB-P01…P06) **and** legal **F4** (NPS-Act escrow) has cleared.
> Do not activate Wave B before both gates are green.

**Why this is a founder/ops task (not code).** Every internal tick is **fail-closed**:
`app/core/internal_token.resolve_internal_token` returns **503** in `ENV=production`
when the endpoint's `INTERNAL_*_TOKEN` is missing or still the dev default. So a
workflow cannot be activated safely until its token exists on **both**:

1. the **production API host** (Hetzner) env — the secret the API compares against, and
2. an **n8n httpHeaderAuth credential** carrying the identical secret, referenced by the
   workflow's HTTP node(s).

Neither can be done from a coding-agent session (no host SSH; n8n credential creation
is UI/API-key only). Steps below are for the founder.

---

## Per-workflow token map

Each row: the workflow JSON, the API endpoint it calls, and the env var the API checks.
Set the env var on the host **and** create an n8n credential with the same value.

| Workflow JSON                  | API endpoint                                          | Token env var                      | Class                     |
| ------------------------------ | ----------------------------------------------------- | ---------------------------------- | ------------------------- |
| `notification-dispatch.json`   | `/internal/dispatch/tick`                             | `INTERNAL_DISPATCH_TOKEN`          | **LIVE ✓**                |
| `reconciliation.json` (bundle) | `/internal/reconciliation/*`                          | `INTERNAL_RECONCILIATION_TOKEN`    | **LIVE ✓**                |
| `payment-sweeper.json`         | `/internal/payment-sweeper/tick`                      | `INTERNAL_PAYMENT_SWEEPER_TOKEN`   | **LIVE ✓** (in bundle)    |
| `reservation-sweeper.json`     | `/internal/stock-sweeper/tick`                        | `INTERNAL_STOCK_SWEEPER_TOKEN`     | Safe-ops                  |
| `embeddings-cron.json`         | `/internal/embeddings/tick`                           | `INTERNAL_EMBEDDINGS_TOKEN`        | Safe-ops                  |
| `admin-digest.json`            | `/internal/digest`                                    | `INTERNAL_DIGEST_TOKEN`            | Safe-ops                  |
| `analytics-retention.json`     | `/internal/analytics/retention-tick`                  | `INTERNAL_ANALYTICS_TOKEN`         | Safe-ops                  |
| `kyc-nudge.json`               | `/internal/n8n/kyc-stalled/tick`                      | `INTERNAL_N8N_TOKEN`               | Safe-ops                  |
| `low-stock-alert.json`         | `/internal/n8n/low-stock/tick`                        | `INTERNAL_N8N_TOKEN`               | Safe-ops                  |
| `review-request.json`          | `/internal/n8n/review-requests/tick`                  | `INTERNAL_N8N_TOKEN`               | Safe-ops                  |
| `payout-failure-alert.json`    | `/internal/n8n/payout-failures/tick`                  | `INTERNAL_N8N_TOKEN`               | Safe-ops (alert only)     |
| `uptime-alert.json`            | inbound webhook                                       | `UPTIME_WEBHOOK_SECRET` (n8n only) | Safe-ops                  |
| `release-job.json`             | `/internal/release-job/tick`                          | `INTERNAL_RELEASE_JOB_TOKEN`       | **MONEY**                 |
| `order-jobs.json`              | `/internal/order-jobs/auto-confirm` + `/auto-release` | `INTERNAL_ORDER_JOBS_TOKEN`        | **MONEY**                 |
| `event-release.json`           | `/internal/event-release/tick`                        | `INTERNAL_EVENT_RELEASE_TOKEN`     | **MONEY**                 |
| `tickets-issue.json`           | `/internal/tickets/issue-tick`                        | `INTERNAL_TICKETS_ISSUE_TOKEN`     | **MONEY-adjacent**        |
| `tickets-release.json`         | `/internal/tickets/release-tick`                      | `INTERNAL_TICKETS_ISSUE_TOKEN`     | **MONEY-adjacent**        |
| `abandoned-cart.json`          | `/internal/n8n/abandoned-carts/tick`                  | `INTERNAL_N8N_TOKEN`               | **Keep OFF** (flag-gated) |
| `funnel-abandon.json`          | `/internal/funnel/abandon-tick`                       | `INTERNAL_FUNNEL_TOKEN`            | **Keep OFF** (flag-gated) |

Other tokens the API also enforces (endpoints not yet on a schedule): `INTERNAL_PAYOUTS_TOKEN`,
`INTERNAL_JOB_JOBS_TOKEN`, `INTERNAL_REVIEW_AGGREGATE_TOKEN`.

---

## Per-workflow activation (4 steps)

For each workflow you're activating:

1. **Generate a secret** (one per token env var):
   `openssl rand -hex 32`
2. **Set it on the API host** — add `INTERNAL_<X>_TOKEN=<secret>` to the Hetzner
   `--env-file`, then restart the container (`docker restart <api>`). Verify the endpoint
   answers **401** (token set, wrong value) rather than **503** (token unset):
   `curl -s -o /dev/null -w "%{http_code}" -XPOST https://api.vergeo5.com/internal/<path> -H 'X-Internal-Token: wrong'` → expect `401`.
3. **Create the n8n credential** — n8n → Credentials → _Header Auth_ → Name `X-Internal-Token`,
   Value `<same secret>`. Name it `Vergeo5 Internal — <Workflow>`.
4. **Import + wire + activate** — Import the JSON, point its HTTP node(s) at the credential
   from step 3, set `API_URL=https://api.vergeo5.com` in the workflow/instance env, and toggle
   **Active**. Confirm the first execution is `success` (not 401/503).

---

## Recommended activation waves

**Wave A — safe operational (activate now).** No money movement; they improve the platform
immediately and fail harmlessly if a row set is empty:
`reservation-sweeper`, `embeddings-cron`, `admin-digest`, `analytics-retention`,
`kyc-nudge`, `low-stock-alert`, `review-request`, `payout-failure-alert`, `uptime-alert`.

**Wave B — money & ticketing (gate before activating).** `release-job`, `order-jobs`,
`event-release`, `tickets-issue`, `tickets-release` act on **real** orders/payments. Per the
launch gates they should go live only **after** the Lenco **sandbox** money path is proven
(VB-P01…P06) **and** legal F4 (NPS-Act escrow) has cleared — otherwise the first real beta
payment could auto-release escrow to a vendor before the money path was ever verified.
While `public_launch=false` and there are 0 payments they'd tick harmlessly, but activating
them is a standing commitment the moment money flows, so treat it as a gated go-live.
The tick nodes now carry `retryOnFail`; also set each workflow's **Settings → Error Workflow**
to a founder-page workflow (reuse the `uptime-alert.json` WhatsApp pattern).

**Keep OFF by design.** `abandoned-cart`, `funnel-abandon` — feature-flag-gated OFF;
leave inactive until the growth-nudge flags are turned on deliberately.

---

## Verification

- Each activated workflow's latest execution is `success`.
- No endpoint returns `503` (token unset) or `401` (credential/token mismatch).
- Record activation date + the executing operator per workflow in
  `docs/production-readiness/2026-07-19/vision-audit/evidence/n8n-*.md` (VD-P01…P03 evidence).
