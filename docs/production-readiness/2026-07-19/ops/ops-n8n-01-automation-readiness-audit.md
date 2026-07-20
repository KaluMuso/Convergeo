# OPS-N8N-01 — Production automation readiness audit

**Date:** 2026-07-19  
**Scope:** Read-only audit of live n8n (`n8n.vergeo5.com` via MCP `n8n-vergeo5.mcp`) vs committed registry (`infra/n8n/*.json`, `docs/ops/n8n-workflows.md`).  
**Hard constraints observed:** no import, edit, enable, execute, delete, deploy, merge, secret change, live config change, payment enablement, migration, or n8n activation. No tokens or credential values recorded.

**Prior art checked:** open/merged PRs include staging evidence (#297), staging plane STG-01 (#300), and foundation n8n notes (`docs/production-readiness/2026-07-18/foundation/production-evidence.md` §6). No open PR duplicates this activation-sequence audit.

---

## 1. Classification legend

| Status            | Meaning                                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| **VERIFIED LIVE** | Present in live n8n, `active=true`, recent successful trigger executions observed                            |
| **DORMANT**       | Committed JSON (or documented contract) exists; **not** present in live n8n search (not imported / inactive) |
| **PARTIAL**       | Live coverage exists but incomplete vs registry contract, schedule/URL drift, or mixed success/error legs    |
| **BROKEN**        | Live schedule fires but recurring `error` executions at expected cadence (metadata only; no body inspected)  |
| **UNKNOWN**       | Cannot verify from n8n MCP + repo alone (e.g. host cron / OCI Object Storage without listing access)         |

---

## 2. Live inventory (MCP `search_workflows`, limit 200)

Exactly **2** workflows exist on the reachable n8n instance. Both are **active**. Search for `release`, `ticket`, `error`, `backup` returned **0** matches.

| Live id            | Live name                              | Active | Triggers | Target host (hardcoded in nodes) | Credential names bound (names only)                          |
| ------------------ | -------------------------------------- | ------ | -------- | -------------------------------- | ------------------------------------------------------------ |
| `sevKtX1AmimQCWsG` | Vergeo5 — notification dispatch        | true   | 1 min    | `https://api.vergeo5.com`        | `Vergeo5 Internal — Dispatch Token`                          |
| `C1MpTNjrfLACMG3f` | Vergeo5 — payment reconciliation crons | true   | 4        | `https://api.vergeo5.com`        | Header Auth for sweeper / reconciliation (names only listed) |

**Credential store (names only, `list_credentials`):** 3 Header Auth entries —

- `Vergeo5 Internal — Dispatch Token`
- `Vergeo5 Internal — Payment Sweeper Token`
- `Vergeo5 Internal — Reconciliation Token`

No credentials named for release-job, event-release, tickets, order-jobs, stock-sweeper, digest, or M14 nudge tokens.

**Error-workflow:** none. No workflow with Error Trigger; no `settings.errorWorkflow` on live or committed JSON.

**Tags:** none.

### 2.1 Execution health (metadata only; `includeData=false`)

| Workflow                     | Recent sample                         | Error sample                                          | Notes                                                                 |
| ---------------------------- | ------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------- |
| notification dispatch        | success every ~1m (2026-07-19 ~02:xx) | 8 errors clustered 2026-07-17 ~05:54–06:01 UTC        | Recovered; currently healthy                                          |
| payment reconciliation crons | success every ~1m (webhook drain)     | recurring errors at ~00:00:53 UTC on 2026-07-17/18/19 | Matches daily-report cadence (instance TZ likely Africa/Lusaka UTC+2) |

Retry fields on sampled executions: `retryOf=null`, `retrySuccessId=null` — no n8n-level retry observed.

---

## 3. Concern-area classifications

### 3.1 Escrow auto-confirm / release — **DORMANT**

| Artifact             | Committed | Live | API endpoint(s)                                             | Status  |
| -------------------- | --------- | ---- | ----------------------------------------------------------- | ------- |
| `order-jobs.json`    | yes       | no   | `POST /internal/order-jobs/auto-confirm` + `…/auto-release` | DORMANT |
| `release-job.json`   | yes       | no   | `POST /internal/release-job/tick`                           | DORMANT |
| `event-release.json` | yes       | no   | `POST /internal/event-release/tick`                         | DORMANT |

API routers exist (`internal_order_jobs`, `internal_release_job`, `internal_event_release`). Rate-limit policies enumerate the paths. **No live n8n tick** → product/service/event escrow auto-release will not run until imported + activated after gates below.

### 3.2 Ticket issuance — **DORMANT**

| Artifact               | Committed | Live | API endpoint                          | Status  |
| ---------------------- | --------- | ---- | ------------------------------------- | ------- |
| `tickets-issue.json`   | yes       | no   | `POST /internal/tickets/issue-tick`   | DORMANT |
| `tickets-release.json` | yes       | no   | `POST /internal/tickets/release-tick` | DORMANT |

Paid ticket issuance and stale-hold release are code-complete on the API side; automation plane is absent live (aligns with MR-W02 / SB-06).

### 3.3 Payment and reservation sweepers — **PARTIAL**

| Concern             | Committed                                                              | Live                                                                 | Status                                  |
| ------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------- |
| Payment sweeper     | `payment-sweeper.json` (every **5m**, `$env.API_URL`)                  | Bundled into live recon workflow (every **10m**, hardcoded prod URL) | **PARTIAL** (live but drifted)          |
| Reservation / stock | `reservation-sweeper.json` (every 2m → `/internal/stock-sweeper/tick`) | **Absent**                                                           | **DORMANT**                             |
| Webhook drain       | **Not** in committed `reconciliation.json`                             | Live every **1m** → `/internal/reconciliation/webhook-drain-tick`    | **PARTIAL** (live-only; registry drift) |

### 3.4 Reconciliation — **PARTIAL** (daily leg **BROKEN**)

| Leg               | Committed `reconciliation.json` | Live bundled workflow       | Status                                                          |
| ----------------- | ------------------------------- | --------------------------- | --------------------------------------------------------------- |
| Poll non-terminal | every 30m                       | every 30m                   | VERIFIED LIVE (as part of bundle)                               |
| Daily report      | cron `0 5 * * *` UTC            | schedule `triggerAtHour: 2` | **BROKEN** — error executions on 2026-07-17/18/19 at ~00:00 UTC |
| Webhook drain     | missing from committed JSON     | every 1m                    | PARTIAL (unregistered live)                                     |

Overall reconciliation concern = **PARTIAL** until daily-report failures are diagnosed (API auth, payload, or timeout) **without** activating new money-moving workflows.

### 3.5 Database / OCI backup and restore — **CODE_COMPLETE** (live still **DORMANT** / G7 **NOT PASS**)

| Artifact                              | Status                                                                                     |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| `infra/n8n/backup-schedule.md`        | Contract (cron 02:00 + watchdog 04:00 Africa/Lusaka → dump/watchdog)                       |
| `infra/n8n/backup.json`               | **Present** in repo (`active: false`); not imported/live → DORMANT                         |
| `infra/scripts/db-dump.sh`            | Present (manifest + sha256 + retention prune + OCI put)                                    |
| `infra/scripts/db-backup-watchdog.sh` | Present (missed-schedule / destination age check)                                          |
| `infra/scripts/db-restore.sh`         | Present in repo                                                                            |
| Live dump → OCI object proof          | **UNKNOWN** / NOT_AUDITABLE until founder activates + lists object                         |
| Restore drill                         | Local PASS in `docs/ops/drill-log.md` (2026-07-12); live staging drill still founder-gated |
| G7                                    | **NOT PASS** — CODE_COMPLETE ≠ dated dump + timed restore evidence                         |

### 3.6 Notification dispatch — **VERIFIED LIVE**

| Artifact                               | Live id            | Schedule | Timeout | Status                                                                               |
| -------------------------------------- | ------------------ | -------- | ------- | ------------------------------------------------------------------------------------ |
| Live “Vergeo5 — notification dispatch” | `sevKtX1AmimQCWsG` | 1 min    | 120s    | VERIFIED LIVE                                                                        |
| Committed `notification-dispatch.json` | —                  | 1 min    | 30s     | DORMANT template (inactive JSON; live copy diverged: hardcoded URL + longer timeout) |

Downstream M14 nudge workflows (`kyc-nudge`, `payout-failure-alert`, `low-stock-alert`, `review-request`, `abandoned-cart`, `admin-digest`) remain **DORMANT** (not imported). Dispatch can drain an empty/low outbox successfully even when producers are off.

---

## 4. Full committed registry vs live (completeness matrix)

Source of truth for filenames: `docs/ops/n8n-workflows.md` + `infra/n8n/*.json` (enforced by `services/api/tests/test_n8n_registry.py`).

| Workflow file                | Concern bucket              | Live present?           | Classification                               |
| ---------------------------- | --------------------------- | ----------------------- | -------------------------------------------- |
| `notification-dispatch.json` | Notification dispatch       | yes (diverged)          | VERIFIED LIVE*                               |
| `reconciliation.json`        | Reconciliation              | yes (bundled + drifted) | PARTIAL / daily BROKEN                       |
| `payment-sweeper.json`       | Payment sweeper             | yes (bundled, 10m≠5m)   | PARTIAL                                      |
| `order-jobs.json`            | Escrow auto-confirm/release | no                      | DORMANT                                      |
| `release-job.json`           | Escrow release              | no                      | DORMANT                                      |
| `event-release.json`         | Event escrow release        | no                      | DORMANT                                      |
| `tickets-issue.json`         | Ticket issuance             | no                      | DORMANT                                      |
| `tickets-release.json`       | Ticket hold release         | no                      | DORMANT                                      |
| `reservation-sweeper.json`   | Reservation sweeper         | no                      | DORMANT                                      |
| `admin-digest.json`          | Notifications (founder)     | no                      | DORMANT                                      |
| `kyc-nudge.json`             | Notifications               | no                      | DORMANT                                      |
| `payout-failure-alert.json`  | Notifications               | no                      | DORMANT                                      |
| `low-stock-alert.json`       | Notifications               | no                      | DORMANT                                      |
| `review-request.json`        | Notifications               | no                      | DORMANT                                      |
| `abandoned-cart.json`        | Notifications               | no                      | DORMANT                                      |
| `funnel-abandon.json`        | Analytics                   | no                      | DORMANT                                      |
| `analytics-retention.json`   | Analytics / DPA             | no                      | DORMANT                                      |
| `embeddings-cron.json`       | Search/AI                   | no                      | DORMANT                                      |
| `uptime-alert.json`          | Observability               | no                      | DORMANT                                      |
| `backup.json`                | DB/OCI backup               | no                      | DORMANT (CODE_COMPLETE in repo; G7 NOT PASS) |
| `backup-schedule.md`         | DB/OCI backup contract      | n/a                     | Contract for `backup.json`                   |

\*Live workflow is a manual/MCP-built sibling of the committed export, not a clean import of `notification-dispatch.json`.

---

## 5. Cross-cutting readiness gaps (must fix before activation)

| Gap                                                 | Evidence                                                | Risk if ignored                                                       |
| --------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------- |
| Live URLs hardcoded to `api.vergeo5.com`            | Live node params                                        | Staging import of live export would hit production                    |
| Committed JSON uses `$env.API_URL`                  | All `infra/n8n/*.json` HTTP nodes                       | Correct pattern — prefer for any new import                           |
| No shared Error Workflow                            | Live + committed                                        | Failures silent except n8n history                                    |
| No `retryOnFail` / `maxTries` on HTTP nodes         | Committed parse                                         | Transient 5xx → missed ticks until next schedule                      |
| Credential coverage only 3 of N                     | `list_credentials`                                      | Cannot bind release/tickets/order-jobs without new Header Auth        |
| Registry drift (webhook-drain, schedules, timeouts) | §3.3–3.4                                                | Ops runbooks disagree with live                                       |
| Daily reconciliation report failing                 | error executions @ ~00:00 UTC                           | Blind spot on Lenco vs ledger daily totals                            |
| Backup workflow not live                            | `backup.json` in repo (`active:false`) but not imported | UNKNOWN whether nightly dump runs until activation + OCI object proof |

---

## 6. Prerequisites (do not activate until all four are done)

These are **external gates**. This audit does **not** perform them.

1. **Migration reconciliation** — production `supabase_migrations` ledger matches repo tip; no missing/odd versions (see foundation evidence CONFLICT through `0055` vs live).
2. **Payment gate deployment** — API image/env with prepaid collection + release accounting (#274 / #294) deployed; Lenco sandbox (or prod) keys present only in env; payment feature flags still fail-closed until deliberate enablement.
3. **Prepaid collection and release accounting verification** — staging/sandbox proof: `CHARGE_RECEIVED` → `COMMISSION_CAPTURE` → `RELEASE_TO_VENDOR`, escrow nets 0, idempotent double-tick, COD isolation (see `payment-release-accounting-report.md` A1–A8 / C-01–C-06).
4. **Sandbox end-to-end testing** — MoMo/card sandbox order → webhook drain → sweeper → (manual or staging) release tick → ticket issue path for event orders; notifications to redirected test recipients only.

---

## 7. Exact activation sequence (document only — **do not execute**)

Activate **one workflow at a time**. Prefer **staging n8n** (`n8n.staging.vergeo5.com`, `$env.API_URL=https://api.staging.vergeo5.com`) before touching production. Production activation requires a separate founder approval after staging PASS.

### Phase A — Safety plane (non-money-moving)

| Step | Action                                                                                                                                           | Timeout         | Retry                                                      | Idempotency                              | Error-workflow             | Freeze / rollback                                   |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------- | ---------------------------------------------------------- | ---------------------------------------- | -------------------------- | --------------------------------------------------- |
| A0   | Create shared **Error Workflow** (Error Trigger → founder alert via outbox or WhatsApp). Publish it. Do not link money workflows until A0 green. | alert send ≤30s | n8n `retryOnFail` 2× / 60s on alert HTTP only              | alert de-dupe by execution id in message | self                       | Rollback: unpublish error workflow                  |
| A1   | Import `notification-dispatch.json` on **staging** (or reconcile live export → `$env.API_URL`). Bind Dispatch token. Leave inactive.             | HTTP 30–120s    | `retryOnFail` false (API tick is already batch-idempotent) | outbox row status / claim                | link to A0                 | Rollback: unpublish / deactivate                    |
| A2   | Activate dispatch on staging; watch 10 consecutive successes.                                                                                    | —               | —                                                          | —                                        | A0 must fire on forced 401 | Deactivate on auth failure storm                    |
| A3   | Fix **production daily-report** failures (diagnose API) **before** enabling new money ticks. Keep webhook-drain + poll + sweeper running.        | daily ≤120s     | after fix, 1 manual dry run only if approved               | report upsert by date                    | A0                         | If report posts bad totals: do not activate release |

### Phase B — Sweepers (state cleanup, limited money risk)

| Step | Action                                                                                                                                | Timeout | Retry | Idempotency                        | Error-workflow | Freeze / rollback                                               |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------- | ------- | ----- | ---------------------------------- | -------------- | --------------------------------------------------------------- |
| B1   | Import `reservation-sweeper.json` (staging first). Token `INTERNAL_STOCK_SWEEPER_TOKEN`.                                              | 30s     | 1×    | reservation expiry is monotonic    | A0             | Deactivate; reservations resume on next tick only               |
| B2   | Align payment sweeper schedule (commit 5m vs live 10m) — pick one; update registry. Prefer keeping live 10m until sandbox load known. | 60s     | false | payment status transitions guarded | A0             | Deactivate sweeper node/workflow; pause Lenco initiate if flood |
| B3   | Export live webhook-drain into registry (`reconciliation.json` or dedicated file) so git matches prod.                                | 30s     | false | drain cursor / event id            | A0             | —                                                               |

### Phase C — Reconciliation hardening

| Step | Action                                                                                 | Timeout   | Retry | Idempotency                                 | Error-workflow | Freeze / rollback                                 |
| ---- | -------------------------------------------------------------------------------------- | --------- | ----- | ------------------------------------------- | -------------- | ------------------------------------------------- |
| C1   | Daily report green for **3 consecutive days** (or 3 forced sandbox days).              | 120s      | 1×    | report key = calendar date                  | A0             | On red report: **money-movement freeze** (see §8) |
| C2   | Confirm poll-tick + webhook-drain do not double-apply (fixture + one sandbox payment). | 60s / 30s | false | payment_events unique / handler idempotency | A0             | Freeze webhooks via API flag if poison-pill       |

### Phase D — Escrow auto-confirm / release (money-moving)

**Stop and request founder approval before any production activate.**

| Step | Action                                                                                                                                | Timeout   | Retry                                                                           | Idempotency                           | Error-workflow  | Freeze / rollback                                 |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------------------------------------------------------------- | ------------------------------------- | --------------- | ------------------------------------------------- |
| D0   | **Money-movement freeze checklist** signed (§8). Sandbox only until signed.                                                           | —         | —                                                                               | —                                     | —               | —                                                 |
| D1   | Import `release-job.json` inactive. Credential `INTERNAL_RELEASE_JOB_TOKEN`. Verify URL is `$env.API_URL`.                            | 60s       | **false** (API must be idempotent; n8n retry risks double HTTP under ambiguity) | release + commission idempotency keys | A0 **required** | Unpublish immediately on unexpected RELEASE count |
| D2   | Import `order-jobs.json` inactive (`auto-confirm` then `auto-release`).                                                               | 120s each | false                                                                           | order status guards                   | A0              | Deactivate; manual confirm path remains           |
| D3   | Import `event-release.json` inactive.                                                                                                 | 30–60s    | false                                                                           | phase + commission capture once       | A0              | Deactivate; holds remain in escrow                |
| D4   | Staging sandbox: one product + one service + one event order through capture→release; assert escrow 0; double-tick no second capture. | —         | —                                                                               | —                                     | —               | On mismatch: freeze §8 + leave workflows inactive |
| D5   | Production activate **only** after D4 PASS + founder approval: `release-job` → `order-jobs` → `event-release` (this order).           | —         | —                                                                               | —                                     | A0              | §8 + unpublish all three                          |

### Phase E — Ticket issuance

| Step | Action                                                                                               | Timeout | Retry | Idempotency                      | Error-workflow | Freeze / rollback               |
| ---- | ---------------------------------------------------------------------------------------------------- | ------- | ----- | -------------------------------- | -------------- | ------------------------------- |
| E1   | Import `tickets-issue.json` + `tickets-release.json` inactive. Token `INTERNAL_TICKETS_ISSUE_TOKEN`. | 30s     | false | ticket row unique per order/line | A0             | Deactivate; paid orders wait    |
| E2   | Sandbox paid ticket order → issue-tick → wallet QR; second tick no duplicate.                        | —       | —     | —                                | —              | Freeze issue tick if duplicates |
| E3   | Production activate issue then release-hold sweeper after E2 PASS.                                   | —       | —     | —                                | A0             | Unpublish both                  |

### Phase F — Backup / restore proof

| Step | Action                                                                                                                         | Timeout              | Retry         | Idempotency                   | Error-workflow | Freeze / rollback                         |
| ---- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------- | ------------- | ----------------------------- | -------------- | ----------------------------------------- |
| F1   | Import `backup.json` (SSH → `db-dump.sh`); leave inactive until dump object listed; activate per `docs/ops/backup-runbook.md`. | dump SLA per runbook | 1× alert only | object key includes timestamp | A0 on failure  | Manual webhook / `db-dump.sh` break-glass |
| F2   | List latest `oci://…/db/vergeo5-*.sql.gz`; record name+size in drill-log (no secrets).                                         | —                    | —             | —                             | —              | —                                         |
| F3   | Staging restore drill PASS in `docs/ops/drill-log.md` (RTO ≤30m).                                                              | —                    | —             | —                             | —              | App pin rollback per `infra/ROLLBACK.md`  |

### Phase G — Secondary notifications (after dispatch proven)

Activate M14 nudges + `admin-digest` only when F5 WhatsApp templates and recipient allowlists are ready. Still **not** money-moving; keep behind feature flags where API supports them.

---

## 8. Money-movement freeze (required runbook)

Trigger freeze when: daily recon red, release tick posts unexpected captures, duplicate tickets, Lenco/API mismatch, or any activation step fails closed.

1. **Unpublish / deactivate** immediately: `release-job`, `order-jobs`, `event-release`, `tickets-issue` (and staging copies).
2. **Leave running:** notification dispatch (customer comms), webhook-drain, recon poll (visibility) — unless they are the failure source.
3. **Pause** new prepaid collection feature flag / Lenco initiate if freeze is collection-side.
4. **Hold** manual payouts and escrow releases until recon green.
5. **Do not** re-activate until double-tick idempotency re-proven on sandbox.

---

## 9. Rollback requirements (n8n plane)

| Level       | Action                                                                                                              |
| ----------- | ------------------------------------------------------------------------------------------------------------------- |
| Workflow    | Unpublish (MCP `unpublish_workflow` / UI inactive) — preferred first response                                       |
| Definition  | Re-import last known-good JSON from `infra/n8n/*.json` at git SHA; scrub credential IDs                             |
| Credentials | Rotate compromised `INTERNAL_*` tokens in API env + n8n Header Auth; never paste values into git                    |
| Container   | `docker compose restart n8n` (prod) or staging compose recreate per `infra/staging/n8n/README.md`                   |
| Data        | DB restore only via `infra/ROLLBACK.md` Path B + payment freeze coordination — **out of band** from workflow toggle |

---

## 10. Dependencies

| Dependency                                          | Needed for                                 |
| --------------------------------------------------- | ------------------------------------------ |
| Staging plane provisioned (SB-01)                   | Safe activation practice                   |
| Internal tokens in API env matching n8n credentials | Any tick auth                              |
| `#274` / `#294` accounting in deployed API          | Release activation (D)                     |
| Lenco sandbox (F9b)                                 | Phases C–E proof                           |
| WhatsApp / Meta (F5)                                | Founder alerts + customer dispatch content |
| OCI dump credentials on VM                          | Phase F                                    |
| Migration ledger match                              | Prerequisite 1                             |

---

## 11. Verification performed this audit

| Check                                                                | Result                                                               |
| -------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `gh pr list` for duplicate OPS-N8N audit                             | none open                                                            |
| MCP `search_workflows` (200)                                         | 2 workflows                                                          |
| MCP `get_workflow_details` ×2                                        | schedules, URLs, timeouts recorded (no secrets)                      |
| MCP `search_executions` success + error                              | dispatch healthy; daily report errors recurring                      |
| MCP `list_credentials`                                               | 3 names; no secret values                                            |
| MCP search release/ticket/error/backup                               | 0 workflows                                                          |
| Parse all `infra/n8n/*.json`                                         | all `active=false`; no `errorWorkflow`; `$env.API_URL` pattern       |
| Registry doc + API routers + ratelimit policies                      | endpoints exist for dormant ticks                                    |
| `backup.json` + `backup-schedule.md` + dump/watchdog/restore scripts | CODE_COMPLETE in repo; live import + G7 evidence still founder-gated |
| Activation / enable / execute                                        | **not performed**                                                    |

---

## 12. Next smallest task

**OPS-N8N-02 — Fix production daily reconciliation report failures (read-only diagnose → minimal API/n8n config fix; no new workflow activation).**

Acceptance: identify failing node/HTTP status for execution ids `1184` / `4257` / `7330` without logging tokens; land fix so next 02:00 Africa/Lusaka (or chosen cron) succeeds; update registry schedule to match live; still **do not** import release/tickets.
