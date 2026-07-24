# Automation & Background Workflow Inventory

**n8n instance:** `n8n.vergeo5.com` (MCP: `n8n-vergeo5.mcp`)  
**API target:** `https://api.vergeo5.com`  
**Auth:** `X-Internal-Token` per endpoint (separate env vars)

---

## Active workflows (7)

### 1. Payment reconciliation crons

| Field                | Value                                                                                                                                    |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **ID**               | `C1MpTNjrfLACMG3f`                                                                                                                       |
| **Triggers**         | 4 schedules                                                                                                                              |
| **Calls**            | `POST /internal/reconciliation/webhook-drain` (1m), `poll-tick` (30m), `POST /internal/payment-sweeper/tick` (10m), daily report (02:00) |
| **Token**            | `INTERNAL_RECONCILIATION_TOKEN`, `INTERNAL_PAYMENT_SWEEPER_TOKEN`                                                                        |
| **Status**           | ✅ Active — last execution success 2026-07-24T08:53:26Z                                                                                  |
| **Related features** | Lenco webhooks, escrow, daily reconciliation report                                                                                      |

### 2. Notification dispatch

| Field           | Value                                                 |
| --------------- | ----------------------------------------------------- |
| **ID**          | `sevKtX1AmimQCWsG`                                    |
| **Schedule**    | Every 1 minute                                        |
| **Calls**       | `POST /internal/dispatch/tick`                        |
| **Token**       | `INTERNAL_DISPATCH_TOKEN`                             |
| **Processing**  | Drains `notification_outbox` → WhatsApp → SMS → email |
| **Status**      | ✅ Active — executions every ~1m, success             |
| **Idempotency** | Outbox dedupe keys in API                             |

### 3. Reservation sweeper

| Field        | Value                               |
| ------------ | ----------------------------------- |
| **ID**       | `F25zEWiPoIveARys`                  |
| **Schedule** | Every 2 minutes                     |
| **Calls**    | `POST /internal/stock-sweeper/tick` |
| **Token**    | `INTERNAL_STOCK_SWEEPER_TOKEN`      |
| **DB**       | `stock_reservations` expiry         |
| **Status**   | ✅ Active                           |

### 4. Embeddings cron

| Field        | Value                                           |
| ------------ | ----------------------------------------------- |
| **ID**       | `oqjfSdMXClfsf3qd`                              |
| **Schedule** | Every 5 minutes                                 |
| **Calls**    | `POST /internal/embeddings/tick`                |
| **Token**    | `INTERNAL_EMBEDDINGS_TOKEN`                     |
| **DB**       | `embedding_jobs` → `search_documents.embedding` |
| **External** | OpenRouter / GTE-small embedder                 |
| **Status**   | ✅ Active — 288 jobs in queue                   |

### 5. Analytics retention

| Field        | Value                                     |
| ------------ | ----------------------------------------- |
| **ID**       | `8drZTFO79pwMPfZy`                        |
| **Schedule** | Daily 03:00                               |
| **Calls**    | `POST /internal/analytics/retention-tick` |
| **Token**    | `INTERNAL_ANALYTICS_TOKEN`                |
| **Purpose**  | DPA retention — NULL person-links >30d    |
| **Status**   | ✅ Active                                 |

### 6. Admin digest

| Field        | Value                                            |
| ------------ | ------------------------------------------------ |
| **ID**       | `rb5d4LHlXAOqkfPX`                               |
| **Schedule** | Daily 06:00                                      |
| **Calls**    | `POST /internal/digest`                          |
| **Token**    | `INTERNAL_DIGEST_TOKEN`                          |
| **Output**   | Founder digest: GMV, orders, payouts, KYC, flags |
| **Status**   | ✅ Active                                        |

### 7. Operational nudges

| Field        | Value                                                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------- |
| **ID**       | `zkIe2zW72qp5fcli`                                                                                                        |
| **Triggers** | 4 schedules                                                                                                               |
| **Calls**    | `/internal/n8n/kyc-stalled/tick` (6h), `low-stock/tick` (07:00), `review-requests/tick` (4h), `payout-failures/tick` (1h) |
| **Token**    | `INTERNAL_N8N_TOKEN`                                                                                                      |
| **Pattern**  | Enqueue to `notification_outbox` (not direct send)                                                                        |
| **Status**   | ✅ Active                                                                                                                 |

---

## Inactive workflows (2)

### Database backup

| Field       | Value                                                 |
| ----------- | ----------------------------------------------------- |
| **ID**      | `OAdOD4kmIbSNehkJ`                                    |
| **Trigger** | Nightly pg_dump → OCI Object Storage + 04:00 watchdog |
| **Status**  | ❌ **Inactive** — needs SSH + WhatsApp creds          |
| **Risk**    | R-015 P1 — independent backup not running             |

### Shared error alert

| Field       | Value                                       |
| ----------- | ------------------------------------------- |
| **ID**      | `LVuHqWgT1tqjYOtc`                          |
| **Trigger** | Error Trigger (n8n native)                  |
| **Status**  | ❌ **Unpublished** — no WhatsApp credential |
| **Risk**    | R-016 P2 — workflow failures unmonitored    |

---

## Internal API registry

Validated by `services/api/tests/test_n8n_registry.py` against `infra/n8n/*.json` and `docs/ops/n8n-workflows.md`.

### n8n-specific endpoints (`internal_n8n.py`)

| GET (list)                      | POST (tick/enqueue)                  |
| ------------------------------- | ------------------------------------ |
| `/internal/n8n/abandoned-carts` | `/internal/n8n/abandoned-carts/tick` |
| `/internal/n8n/kyc-stalled`     | `/internal/n8n/kyc-stalled/tick`     |
| `/internal/n8n/low-stock`       | `/internal/n8n/low-stock/tick`       |
| `/internal/n8n/payout-failures` | `/internal/n8n/payout-failures/tick` |
| `/internal/n8n/review-requests` | `/internal/n8n/review-requests/tick` |

### Other cron endpoints (called by n8n, not n8n-prefixed)

- `/internal/order-jobs/auto-confirm`, `/auto-release`
- `/internal/jobs/expire-tick`
- `/internal/release-job/tick`
- `/internal/event-release/tick`
- `/internal/review-aggregate/tick`
- `/internal/funnel/abandon-tick`
- `/internal/privacy/export-purge-tick`
- `/internal/tickets/issue-tick`, `/release-tick`

---

## Execution health (2026-07-24)

- **10,057** total executions recorded
- Recent 5: all **success** (payment reconciliation, dispatch, reservation sweeper)
- No failed executions in last 5 sampled

---

## Missing workflows (referenced in code/docs, not in n8n)

| Workflow                     | Status                                       |
| ---------------------------- | -------------------------------------------- |
| Abandoned cart (direct)      | Covered via `/internal/n8n/abandoned-carts`  |
| Refund processing automation | Ledger-orchestrated in API, not separate n8n |
| Dispute escalation cron      | Manual admin action                          |
| VSDC invoice sync            | Seam only (`services/invoicing/vsdc.py`)     |

---

## Retry & failure handling

| Layer               | Behaviour                                             |
| ------------------- | ----------------------------------------------------- |
| Lenco webhooks      | 30min × 24h retries (documented)                      |
| Notification outbox | Dispatch tick retries; fallback chain WA→SMS→email    |
| n8n nodes           | Default retry per workflow (not uniformly configured) |
| Error workflow      | **Not connected** — shared handler inactive           |

---

## Recommendations

1. Activate database backup workflow (R-015)
2. Publish shared error alert + link via `settings.errorWorkflow`
3. Add execution failure alerting to founder WhatsApp
4. Document manual drill: `POST /webhook/backup-manual` (backup workflow)
