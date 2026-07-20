# Prompt 7 — n8n workflow fleet import / configure / verify

**Date:** 2026-07-20  
**Branch:** `cursor/n8n-fleet-import-da3e`  
**Operator surface:** n8n MCP (`n8n-vergeo5.mcp`) + committed `infra/n8n/*.json`  
**Hard constraints observed:** no encryption keys or credential secret values recorded; no money-moving activation; no S4 / G5 / G21 PASS claim.

**Companion evidence:** `docs/ops/n8n-workflows.md`, `docs/production-readiness/2026-07-19/ops/ops-n8n-01-automation-readiness-audit.md`, `docs/production-readiness/2026-07-20/deploy-migration-truth.md` (API/migration NO-GO), `docs/production-readiness/2026-07-18/consolidated/release-gates.md`.

---

## Verdict (sanitised)

| Gate    | Claim                | Why                                                                                                             |
| ------- | -------------------- | --------------------------------------------------------------------------------------------------------------- |
| **S4**  | **FAIL** (unchanged) | No release-job / tickets-issue / tickets-release active; no authenticated success tick; no double-release proof |
| **G5**  | **FAIL** (unchanged) | Escrow auto-release + tickets + dispatch drain not verified healthy; only fail-closed evidence under API 502    |
| **G21** | **FAIL** (unchanged) | Lifecycle fleet not imported/activated after money-path preflight                                               |

**Operational outcome of this session:** fail-closed disable of the two previously active production ticks; shared Error Trigger scaffold imported **inactive**; full registry import + activation **blocked** by API `502` and missing Header Auth credentials.

---

## 1. Preconditions (read before any activation)

| Check                                  | Result @ 2026-07-20                                                                                           |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz`  | **502**                                                                                                       |
| `GET https://api.vergeo5.com/readyz`   | **502**                                                                                                       |
| Live migration tip / RC-02 collision   | Open — see deploy-migration-truth (RC-02 makes repo `0063` match live revoke; `0064`/`0065` remain unapplied) |
| Ledger / money rows                    | Empty historically; no sandbox release drill in this session                                                  |
| `infra/n8n/backup.json` on master      | **Absent** (contract `backup-schedule.md` only; PR #374 may land later)                                       |
| WhatsApp Header Auth credential in n8n | **Missing**                                                                                                   |
| MCP JSON file import                   | **Unavailable** — only Workflow SDK `create_workflow_from_code` (no raw `infra/n8n/*.json` import path)       |

**Rule applied:** do not activate money-moving workflows before API health, migration/ledger preflight, and fail-closed controls are verified.

---

## 2. Committed inventory (before)

Static JSON validate: **19/19 OK** (`python json.loads` on every `infra/n8n/*.json`). All ship `"active": false`.

| #   | Committed file               | Deterministic name (JSON `name`)     | Trigger                | Endpoint(s)                           | Credential name in JSON            | Money-moving?                      |
| --- | ---------------------------- | ------------------------------------ | ---------------------- | ------------------------------------- | ---------------------------------- | ---------------------------------- |
| 1   | `uptime-alert.json`          | Uptime Downtime Founder Alert        | webhook `uptime-alert` | WhatsApp Graph API (`$env`)           | _(none — Bearer via `$env`)_       | No                                 |
| 2   | `notification-dispatch.json` | Notification Dispatch Tick           | schedule 1m            | `POST …/internal/dispatch/tick`       | `Vergeo5 Internal Dispatch`        | No                                 |
| 3   | `abandoned-cart.json`        | Abandoned Cart Recovery              | schedule 2h            | `…/internal/n8n/abandoned-carts/tick` | `Vergeo5 Internal N8N`             | No                                 |
| 4   | `kyc-nudge.json`             | KYC Stalled Applicant Nudge          | schedule 6h            | `…/internal/n8n/kyc-stalled/tick`     | `Vergeo5 Internal N8N`             | No                                 |
| 5   | `low-stock-alert.json`       | Vendor Low Stock Alert               | cron 07:00 UTC         | `…/internal/n8n/low-stock/tick`       | `Vergeo5 Internal N8N`             | No                                 |
| 6   | `review-request.json`        | Post-Completion Review Request       | schedule 4h            | `…/internal/n8n/review-requests/tick` | `Vergeo5 Internal N8N`             | No                                 |
| 7   | `admin-digest.json`          | Founder Daily Digest                 | cron 06:00 UTC         | `…/internal/digest` + WhatsApp        | Digest + WhatsApp                  | No                                 |
| 8   | `reservation-sweeper.json`   | Reservation Sweeper Tick             | schedule 2m            | `…/internal/stock-sweeper/tick`       | `Vergeo5 Internal Stock Sweeper`   | No                                 |
| 9   | `funnel-abandon.json`        | Funnel Abandonment Sweeper           | schedule 5m            | `…/internal/funnel/abandon-tick`      | `Vergeo5 Internal Funnel`          | No                                 |
| 10  | `analytics-retention.json`   | Analytics PII Retention Sweeper      | daily 03:00            | `…/internal/analytics/retention-tick` | `Vergeo5 Internal Analytics`       | No                                 |
| 11  | `embeddings-cron.json`       | Embeddings Tick                      | schedule 5m            | `…/internal/embeddings/tick`          | `Vergeo5 Internal Embeddings`      | No                                 |
| 12  | `payout-failure-alert.json`  | Payout Failure Founder Alert         | schedule 1h            | `…/internal/n8n/payout-failures/tick` | `Vergeo5 Internal N8N`             | Alert-only (reads payout failures) |
| 13  | `tickets-issue.json`         | Ticket Issue Tick                    | schedule 60s           | `…/internal/tickets/issue-tick`       | `Vergeo5 Internal Tickets Issue`   | **Yes**                            |
| 14  | `tickets-release.json`       | Ticket Release Tick                  | schedule 2m            | `…/internal/tickets/release-tick`     | `Vergeo5 Internal Tickets Release` | **Yes**                            |
| 15  | `event-release.json`         | Event Escrow Release Tick            | schedule 1h            | `…/internal/event-release/tick`       | `Vergeo5 Internal Event Release`   | **Yes**                            |
| 16  | `order-jobs.json`            | Order Auto Jobs                      | schedule 1h            | auto-confirm + auto-release           | `Vergeo5 Internal Order Jobs`      | **Yes**                            |
| 17  | `release-job.json`           | Escrow Release Job Tick              | schedule 1h            | `…/internal/release-job/tick`         | `Vergeo5 Internal Release Job`     | **Yes**                            |
| 18  | `payment-sweeper.json`       | Payment Sweeper Tick                 | schedule 5m            | `…/internal/payment-sweeper/tick`     | `Vergeo5 Internal Payment Sweeper` | **Yes**                            |
| 19  | `reconciliation.json`        | Reconciliation Poller & Daily Report | 30m + daily 05:00 UTC  | poll-tick + daily-report              | `Vergeo5 Internal Reconciliation`  | **Yes**                            |
| —   | `backup.json`                | _(not on master)_                    | —                      | —                                     | —                                  | Ops / G7                           |

Idempotency for API ticks is **API-side** (claim / outbox / ledger uniqueness) — committed JSON does not embed `X-Idempotency-Key` headers.

---

## 3. Live inventory

### 3.1 Before this session (OPS-N8N-01 + board)

| Live ID            | Name                                   | Active                                      |
| ------------------ | -------------------------------------- | ------------------------------------------- |
| `sevKtX1AmimQCWsG` | Vergeo5 — notification dispatch        | **true** (erroring every ~1m under API 502) |
| `C1MpTNjrfLACMG3f` | Vergeo5 — payment reconciliation crons | **true** (bundled money ticks; erroring)    |

### 3.2 After this session

| Live ID            | Name                                   | Active    | Notes                                                                                                            |
| ------------------ | -------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------- |
| `sevKtX1AmimQCWsG` | Vergeo5 — notification dispatch        | **false** | Unpublished (fail-closed)                                                                                        |
| `C1MpTNjrfLACMG3f` | Vergeo5 — payment reconciliation crons | **false** | Unpublished (fail-closed); **registry drift** vs separate committed files                                        |
| `LVuHqWgT1tqjYOtc` | Vergeo5 — shared error alert           | **false** | Created this session; Error Trigger → Format Actionable Alert; **not published** (no WhatsApp delivery node yet) |

**Live credentials (names only):**

| Credential ID      | Name                                     | Type           |
| ------------------ | ---------------------------------------- | -------------- |
| `4zHrwJ0aQkqDG2ib` | Vergeo5 Internal — Dispatch Token        | httpHeaderAuth |
| `2YIzCrGVKzsl14F6` | Vergeo5 Internal — Payment Sweeper Token | httpHeaderAuth |
| `wHBamWZu96ONsPts` | Vergeo5 Internal — Reconciliation Token  | httpHeaderAuth |

---

## 4. Mapping table (committed ↔ live)

| Committed file               | Live workflow ID                | Imported?                                                                                   | Active? | Creds required (names)                                    | Trigger            | Idempotency                             | Money?  | Safe activation order              |
| ---------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------- | ------- | --------------------------------------------------------- | ------------------ | --------------------------------------- | ------- | ---------------------------------- |
| _(ops)_ shared error alert   | `LVuHqWgT1tqjYOtc`              | **yes** (SDK scaffold)                                                                      | no      | WhatsApp Header Auth / `$env` WA token (missing)          | Error Trigger      | n/a (alert only)                        | No      | **1** — publish only after WA bind |
| `uptime-alert.json`          | —                               | **no**                                                                                      | —       | `$env` WA + webhook secret (RC-04: webhook `options: {}`) | webhook            | webhook auth + template idempotency TBD | No      | **1b** after secret hardening      |
| `notification-dispatch.json` | `sevKtX1AmimQCWsG` (name drift) | **partial** (live pre-exists; not registry JSON re-import)                                  | **no**  | Dispatch Token (present; name differs from JSON)          | schedule 1m        | API outbox claim                        | No      | **2** after `healthz`/`readyz` 200 |
| `kyc-nudge.json`             | —                               | no                                                                                          | —       | `Vergeo5 Internal N8N` (**missing**)                      | schedule           | outbox                                  | No      | **2**                              |
| `abandoned-cart.json`        | —                               | no                                                                                          | —       | Internal N8N (**missing**)                                | schedule           | outbox                                  | No      | **2**                              |
| `low-stock-alert.json`       | —                               | no                                                                                          | —       | Internal N8N (**missing**)                                | schedule           | outbox                                  | No      | **2**                              |
| `review-request.json`        | —                               | no                                                                                          | —       | Internal N8N (**missing**)                                | schedule           | outbox                                  | No      | **2**                              |
| `admin-digest.json`          | —                               | no                                                                                          | —       | Digest + WhatsApp (**missing**)                           | schedule           | read-only digest                        | No      | **2** after F5 WA                  |
| `reservation-sweeper.json`   | —                               | no                                                                                          | —       | Stock Sweeper (**missing**)                               | schedule           | API claim                               | No      | **3**                              |
| `funnel-abandon.json`        | —                               | no                                                                                          | —       | Funnel (**missing**)                                      | schedule           | API                                     | No      | **3**                              |
| `analytics-retention.json`   | —                               | no                                                                                          | —       | Analytics (**missing**)                                   | schedule           | API                                     | No      | **3**                              |
| `embeddings-cron.json`       | —                               | no                                                                                          | —       | Embeddings (**missing**)                                  | schedule           | API                                     | No      | **3**                              |
| `payout-failure-alert.json`  | —                               | no                                                                                          | —       | Internal N8N (**missing**)                                | schedule           | outbox alert                            | Alert   | **3** (after dispatch)             |
| `tickets-issue.json`         | —                               | no                                                                                          | —       | Tickets Issue (**missing**)                               | schedule 60s       | API exactly-once issue                  | **Yes** | **4** sandbox only                 |
| `tickets-release.json`       | —                               | no                                                                                          | —       | Tickets Release (**missing**)                             | schedule           | API claim                               | **Yes** | **5** controlled                   |
| `event-release.json`         | —                               | no                                                                                          | —       | Event Release (**missing**)                               | schedule           | API claim                               | **Yes** | **5** controlled                   |
| `order-jobs.json`            | —                               | no                                                                                          | —       | Order Jobs (**missing**)                                  | schedule           | API                                     | **Yes** | **6** after ledger preflight       |
| `release-job.json`           | —                               | no                                                                                          | —       | Release Job (**missing**)                                 | schedule           | API + ledger                            | **Yes** | **6** after migration/ledger       |
| `payment-sweeper.json`       | bundled in `C1MpTNjrfLACMG3f`   | **partial / drifted** (live 10m + hardcoded URL vs JSON 5m + `$env.API_URL`)                | **no**  | Sweeper Token (present)                                   | schedule           | API                                     | **Yes** | **6**                              |
| `reconciliation.json`        | bundled in `C1MpTNjrfLACMG3f`   | **partial / drifted** (live also has webhook-drain not in committed JSON; daily hour drift) | **no**  | Reconciliation Token (present)                            | schedule           | API                                     | **Yes** | **6**                              |
| `backup.json`                | —                               | **N/A** (not on master)                                                                     | —       | SSH / backup secret                                       | schedule + webhook | dump artifact uniqueness                | Ops     | **7** after #374 merge + configure |

### Live bundle drift (money)

`C1MpTNjrfLACMG3f` is **not** a 1:1 import of `reconciliation.json`. It combines:

1. webhook-drain 1m → `/internal/reconciliation/webhook-drain-tick` (**not** in committed `reconciliation.json`)
2. reconciliation poll 30m
3. payment sweeper **10m** (committed sweeper is **5m**)
4. daily report `triggerAtHour: 2` (committed daily is cron `0 5 * * *` UTC)

Prefer re-importing registry-aligned separate workflows after API recovery rather than re-activating the drifted bundle blindly.

### Credential name drift

| Committed JSON name                | Live store name                            |
| ---------------------------------- | ------------------------------------------ |
| `Vergeo5 Internal Dispatch`        | `Vergeo5 Internal — Dispatch Token`        |
| `Vergeo5 Internal Payment Sweeper` | `Vergeo5 Internal — Payment Sweeper Token` |
| `Vergeo5 Internal Reconciliation`  | `Vergeo5 Internal — Reconciliation Token`  |

Import procedure must bind by **credential ID reference**, not plaintext tokens.

---

## 5. Actions taken this session

1. **Inventory** committed 19 JSON + live 2 workflows + 3 credentials.
2. **Unpublished** `C1MpTNjrfLACMG3f` (money recon bundle) — fail-closed while API 502.
3. **Unpublished** `sevKtX1AmimQCWsG` (dispatch) — stopped 1m error spam; fail-closed.
4. **Created** `LVuHqWgT1tqjYOtc` shared Error Trigger scaffold (inactive, no publish).
5. **Did not** activate any money-moving workflow.
6. **Did not** mass-import remaining registry JSON via SDK (blocked: API down, missing creds, MCP has no raw-JSON import; accidental publish risk).

---

## 6. Controlled fixtures + idempotency

### 6.1 Notification dispatch (dependency-absent fail-closed)

| Run                | Execution ID | Mode   | Status    | HTTP to API                                                            |
| ------------------ | ------------ | ------ | --------- | ---------------------------------------------------------------------- |
| Fixture A          | `12345`      | manual | **error** | 502 Bad gateway                                                        |
| Fixture B (repeat) | `12346`      | manual | **error** | 502 Bad gateway (`uri=https://api.vergeo5.com/internal/dispatch/tick`) |
| Fixture C (repeat) | `12347`      | manual | **error** | 502 (metadata)                                                         |

**Proved:**

- Workflow fails closed when API dependency is absent (no success path).
- Repeat runs remain **error** — no success conversion of unpaid/failed dependency into success.
- Credential bound by reference: `httpHeaderAuth` id `4zHrwJ0aQkqDG2ib` (name only; secret not logged).
- Headers redacted in execution payload (`**hidden**`).

**Not proved (blocked by API 502):**

- Successful outbox drain
- Second successful tick is idempotent (no duplicate WhatsApp/SMS/email)
- DB/outbox row deltas for eligible vs ineligible records

### 6.2 Release / tickets / event (required proofs — outstanding)

| Required proof                                            | Status                                                                                                    |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| One eligible record processed exactly once                | **NOT RUN**                                                                                               |
| Ineligible record untouched                               | **NOT RUN**                                                                                               |
| Retries do not double-release / double-issue / double-pay | **NOT RUN**                                                                                               |
| Partial failure → actionable alert                        | **PARTIAL** — Error Trigger scaffold exists but unpublished / no WA delivery                              |
| Fail closed when internal token or dependency absent      | **PARTIAL** — dispatch 502 proves dependency fail-closed; token-absent 401/403 not re-probed this session |
| Provider errors do not convert unpaid → success           | **NOT RUN** (needs sandbox payment path + healthy API)                                                    |

---

## 7. Missing credentials (create before import bind)

Create **HTTP Header Auth** credentials (names aligned to registry or map explicitly):

- `Vergeo5 Internal N8N` → `INTERNAL_N8N_TOKEN`
- `Vergeo5 Internal Digest` → `INTERNAL_DIGEST_TOKEN`
- `Vergeo5 Internal Stock Sweeper`
- `Vergeo5 Internal Funnel`
- `Vergeo5 Internal Analytics`
- `Vergeo5 Internal Embeddings`
- `Vergeo5 Internal Order Jobs`
- `Vergeo5 Internal Release Job`
- `Vergeo5 Internal Event Release`
- `Vergeo5 Internal Tickets Issue`
- `Vergeo5 Internal Tickets Release`
- `Vergeo5 WhatsApp Cloud API` (Header / Bearer)

Also set n8n `$env`: `API_URL`, per-concern internal tokens, `FOUNDER_WHATSAPP_TO`, WhatsApp Cloud vars (never commit values).

---

## 8. Failed / blocked workflows

| Item                                | Blocker                                        |
| ----------------------------------- | ---------------------------------------------- |
| Full registry import (17 remaining) | API 502; missing creds; MCP no raw JSON import |
| Activation order steps 2–6          | Same                                           |
| Success-path idempotency            | Same                                           |
| Backup workflow                     | `backup.json` absent on master                 |
| Shared error alert publish          | Missing WhatsApp credential + delivery node    |
| S4 / G5 / G21                       | Explicitly remain **FAIL**                     |

---

## 9. Rollback / disable procedure

### Immediate fail-closed (already applied)

1. In n8n UI or MCP: **Unpublish** any active tick (`publish_workflow` inverse = unpublish).
2. Confirm `search_workflows` shows `active: false` and `activeVersionId: null`.
3. Confirm no new `mode=trigger` executions after unpublish timestamp.

### Republish after recovery (founder / ops)

**Gate:** `curl -fsS https://api.vergeo5.com/healthz` and `/readyz` both 200; migration/ledger preflight for money ticks.

1. Prefer **registry-aligned** import (`infra/n8n/*.json` via UI Import from file) over re-enabling drifted `C1MpTNjrfLACMG3f`.
2. Bind credentials by ID; scrub `REPLACE_WITH_CREDENTIAL_ID`.
3. Confirm `$env.API_URL` (committed JSON) or intentionally keep hardcoded host with documented exception.
4. Manual execute once → success; execute again → prove idempotent side effects (outbox/ledger SQL).
5. Publish in safe order (§4 column).
6. Link published Error Trigger workflow via `settings.errorWorkflow` only after it can deliver alerts.
7. Money ticks last: `release-job`, `order-jobs`, `event-release`, `tickets-*`, `payment-sweeper`, `reconciliation`.

### Emergency disable

- Unpublish all active workflows.
- Optionally rotate compromised internal tokens in API + n8n credentials (do not log values).
- Do **not** rotate `N8N_ENCRYPTION_KEY` without credential migration plan.

---

## 10. Safe activation order (authoritative for next ops window)

1. Error / ops alerting — finish `LVuHqWgT1tqjYOtc` (WA node) + harden `uptime-alert` webhook auth → publish.
2. Notification lifecycle — dispatch + M14 nudges + digest (non-money).
3. Non-money order lifecycle — reservation-sweeper, funnel, analytics-retention, embeddings.
4. Tickets-issue in **sandbox/test** mode only.
5. Tickets-release + event-release in controlled mode.
6. Escrow/release (`release-job`, `order-jobs`) + payment sweeper/recon **only after** migration + ledger preflight.
7. Backup workflow after `backup.json` PR merged + configured.

---

## 11. Gate evidence pointers (no PASS)

| Gate | Required evidence                                                | This session                                       |
| ---- | ---------------------------------------------------------------- | -------------------------------------------------- |
| S4   | active release + tickets; execution IDs; no double release/issue | **Absent** — workflows not imported/active         |
| G5   | MR-W01/W02 + dispatch drain + authz 401/403                      | **Absent** success path; fail-closed dispatch only |
| G21  | Lifecycle n8n after money path                                   | **Absent**                                         |

Update `release-gates.md` rows only when the above live proofs exist.

---

## 12. Next operator checklist (when API is green)

- [ ] Resolve API 502 + record deploy digest
- [ ] Close RC-02 migration collision; apply source_key / FORCE RLS as planned
- [ ] Create missing Header Auth credentials (names only in UI)
- [ ] UI-import each `infra/n8n/*.json` with deterministic names; leave inactive
- [ ] Align or retire drifted bundle `C1MpTNjrfLACMG3f`
- [ ] Complete WA delivery on `LVuHqWgT1tqjYOtc`; publish; wire `errorWorkflow`
- [ ] Double-run fixtures per workflow; record execution IDs + SQL deltas
- [ ] Activate in order §10; update this file’s after-inventory
- [ ] Only then reconsider S4 / G5 / G21
