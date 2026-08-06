# Blockers — Evidence-Backed (Batch 0.5)

**Date:** 2026-08-06  
**Repository SHA:** `e7555b8d` (Batch 1A branch)  
**Aggregate launch posture:** **NO_GO**

Evidence pack: [2026-08-06/runtime-truth-evidence.md](./2026-08-06/runtime-truth-evidence.md)

---

## P0 blockers

### BLK-001 — Production DB migrations substantially behind Git

| Field                  | Value                                                                                                                                                                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `DATA_MIGRATION_BLOCKER`                                                                                                                                                                                                                      |
| **Description**        | Production Supabase (`dpadrlxukcjbewpqympu`) last applied migration is `0071_vendor_listing_compare_at`. Git tip includes `0072`–`0095` plus `20260802153539_rls_policy_contract_remediation.sql` — **24+ migrations missing** on production. |
| **Evidence**           | Supabase MCP `list_migrations` (2026-08-06); [runtime-truth-evidence.md](./2026-08-06/runtime-truth-evidence.md)                                                                                                                              |
| **Affected canonical** | CAN-ORD-002, CAN-CAT-005, CAN-OPS-001, CAN-SOC-001/002, CAN-FIN-004/005 (schema/features in unmigrated band)                                                                                                                                  |
| **Launch scope**       | PLATFORM                                                                                                                                                                                                                                      |
| **Next action**        | Plan staged migration apply on staging first; reconcile `schema_migrations` ordering; never apply blindly to production.                                                                                                                      |

### BLK-002 — Staging DB migrations behind Git

| Field                  | Value                                                                                                                                |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Category**           | `DATA_MIGRATION_BLOCKER`                                                                                                             |
| **Description**        | Staging (`iyasmrmbcrvlfxpzescb`) last applied `0079_clip_cost_guard`. Missing `0080`–`0095` and timestamp RLS remediation migration. |
| **Evidence**           | Supabase MCP (2026-08-06)                                                                                                            |
| **Affected canonical** | CAN-OPS-001, CAN-CAT-003, CAN-ORD-002/003                                                                                            |
| **Launch scope**       | PLATFORM                                                                                                                             |
| **Next action**        | Apply missing migrations on staging; run RLS matrix + smoke tests before production promotion.                                       |

### BLK-003 — API production deploy behind master

| Field                  | Value                                                                                                 |
| ---------------------- | ----------------------------------------------------------------------------------------------------- |
| **Category**           | `DEPLOYMENT_REQUIRED`                                                                                 |
| **Description**        | Production API `/fingerprint` reports `git_sha=e4a7bb79` — ancestor of current `master` (`fcf2b191`). |
| **Evidence**           | Live GET probes 2026-08-06                                                                            |
| **Affected canonical** | CAN-OPS-006                                                                                           |
| **Launch scope**       | PLATFORM                                                                                              |
| **Next action**        | Trigger API image build/deploy workflow after migration plan approved.                                |

### BLK-004 — Zero money exercised on production

| Field                  | Value                                                                                                                   |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `FINANCIAL_BLOCKER`                                                                                                     |
| **Description**        | `ledger_transactions` count = 0 on production; no sandbox money drill evidence in programme.                            |
| **Evidence**           | Supabase SQL count; `docs/plan/00-status.md`                                                                            |
| **Affected canonical** | CAN-FIN-001, CAN-FIN-002, CAN-FIN-003, CAN-FIN-004                                                                      |
| **Launch scope**       | PAYMENTS                                                                                                                |
| **Next action**        | Complete money drill prerequisite matrix; obtain F9b Lenco sandbox creds; run staging drill only after financial audit. |

### BLK-005 — Escrow automation workflows not confirmed active

| Field                  | Value                                                                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Category**           | `DEPLOYMENT_REQUIRED`                                                                                                                                                          |
| **Description**        | n8n MCP shows payment reconciliation + reservation sweeper ACTIVE, but `release-job.json`, `order-jobs.json`, `event-release.json` are **IN_GIT_ONLY** / import state unknown. |
| **Evidence**           | n8n MCP inventory 2026-08-06; `infra/n8n/` (25 JSON files)                                                                                                                     |
| **Affected canonical** | CAN-FIN-005, CAN-FIN-004, CAN-EVT-003                                                                                                                                          |
| **Launch scope**       | PLATFORM, VENDOR                                                                                                                                                               |
| **Next action**        | Read-only n8n fleet audit; import + wire error handler before enabling escrow timers.                                                                                          |

### BLK-006 — Database backup workflow inactive

| Field                  | Value                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `RECOVERY_BLOCKER`                                                                                                              |
| **Description**        | n8n `Database Backup` workflow (`backup.json`) is **IMPORTED_INACTIVE**. Supabase PITR configuration not verified this session. |
| **Evidence**           | n8n MCP 2026-08-06                                                                                                              |
| **Affected canonical** | CAN-OPS-005                                                                                                                     |
| **Launch scope**       | PLATFORM                                                                                                                        |
| **Next action**        | Verify Supabase backup/PITR in dashboard; activate or replace n8n backup workflow; document restore procedure.                  |

### BLK-007 — F4 legal counsel sign-off absent

| Field                  | Value                                                                      |
| ---------------------- | -------------------------------------------------------------------------- |
| **Category**           | `FINANCIAL_BLOCKER`                                                        |
| **Description**        | Pre real-money gate per D14 — no counsel sign-off on escrow/payment flows. |
| **Evidence**           | `docs/plan/00-decisions.md` F4                                             |
| **Affected canonical** | CAN-FIN-004, CAN-FIN-002                                                   |
| **Launch scope**       | PAYMENTS                                                                   |
| **Next action**        | Founder legal review before `PAYMENTS_ALLOW_PRODUCTION`.                   |

### BLK-008 — OCI money gate env vars unverified

| Field                  | Value                                                                                                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `EXTERNAL_ACCESS_REQUIRED`                                                                                                                                           |
| **Description**        | `PAYMENTS_ENABLED`, `PAYMENTS_ALLOW_PRODUCTION`, `PAYOUTS_ENABLED`, `STAGING_ALLOW_PAYOUTS` effective values not readable from this session (no OCI SSH/env access). |
| **Evidence**           | BLOCKED_EXTERNAL in runtime-truth-evidence                                                                                                                           |
| **Affected canonical** | CAN-FIN-002, CAN-FIN-003                                                                                                                                             |
| **Launch scope**       | PAYMENTS                                                                                                                                                             |
| **Next action**        | Ops read-only env audit on OCI VM; confirm all gates false before drills.                                                                                            |

---

## P1 blockers

### BLK-101 — B2B cart read-path does not re-derive wholesale eligibility

| Field                  | Value                                                                                                                                                                                                                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Category**           | `CODE_DEFECT`                                                                                                                                                                                                                                                                                    |
| **Description**        | `GET /cart` / `_build_cart_response` uses stored `cart_items` without re-checking wholesale visibility. Checkout session creation **does** re-derive (`_rederive_line_prices` → 409). A retail user who added a listing before it became wholesale-only may see stale cart lines until checkout. |
| **Evidence**           | `services/api/app/routers/cart.py`, `services/api/app/services/cart/store.py`, `services/api/app/routers/checkout.py`; runtime-truth-evidence B2B trace                                                                                                                                          |
| **Affected canonical** | CAN-CAT-003, CAN-ORD-003                                                                                                                                                                                                                                                                         |
| **Launch scope**       | B2B, PLATFORM                                                                                                                                                                                                                                                                                    |
| **Next action**        | Bounded audit/fix in Batch 1 (cart & checkout derivation).                                                                                                                                                                                                                                       |

### BLK-102 — Vendor/admin production SHA unknown

| Field                  | Value                                                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `EXTERNAL_ACCESS_REQUIRED`                                                                                                  |
| **Description**        | Customer `buildId=fcf2b191` matches master. Vendor health returns HTML shell (no JSON SHA). Admin behind Cloudflare Access. |
| **Evidence**           | Live probes 2026-08-06                                                                                                      |
| **Affected canonical** | CAN-OPS-006                                                                                                                 |
| **Launch scope**       | PLATFORM                                                                                                                    |
| **Next action**        | Probe vendor JSON health endpoint or Vercel deployment metadata; CF Access session for admin.                               |

### BLK-103 — Registry traceability 2-row supply gap

| Field                  | Value                                                                                                  |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| **Category**           | `PRODUCT_DECISION`                                                                                     |
| **Description**        | Registry header claims 225 source rows; supplied matrix contains 223 (S1 header 53 vs 51 matrix rows). |
| **Evidence**           | [REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md); DECISIONS.md REG-001                     |
| **Affected canonical** | (traceability completeness)                                                                            |
| **Launch scope**       | PLATFORM                                                                                               |
| **Next action**        | Operator supplies missing S1 source IDs.                                                               |

### BLK-104 — Custom access token hook disabled

| Field                  | Value                                                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------ |
| **Category**           | `ENVIRONMENT_REQUIRED`                                                                           |
| **Description**        | Migration `0051` SQL exists; `custom_access_token_hook` commented out in `supabase/config.toml`. |
| **Evidence**           | Batch 0 architecture baseline                                                                    |
| **Affected canonical** | CAN-ID-002, CAN-OPS-001                                                                          |
| **Launch scope**       | PLATFORM                                                                                         |
| **Next action**        | Product decision FD-03 before enabling.                                                          |

### BLK-201 — Migration replay skips timestamp migration

| Field                  | Value                                                                                                                                        |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `CODE_DEFECT`                                                                                                                                |
| **Status**             | **RESOLVED** (Batch 1A.1 — `scripts/ci/migration-replay.sh` now replays all `*.sql` in sorted order, including timestamp migrations)         |
| **Description**        | `scripts/ci/migration-replay.sh` applied only `00*.sql`; `20260802153539_rls_policy_contract_remediation.sql` was excluded from fast replay. |
| **Evidence**           | Batch 1A; replay script `find … -name '00*.sql'`                                                                                             |
| **Affected canonical** | CAN-OPS-006                                                                                                                                  |
| **Launch scope**       | PLATFORM                                                                                                                                     |
| **Resolution**         | Replay glob widened to `*.sql`; deterministic `sort` matches Supabase CLI ordering (0001…0095, then timestamp).                              |

### BLK-202 — FE/API/DB version triangle mismatch (production)

| Field                  | Value                                                                                                                                                                 |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Category**           | `DEPLOYMENT_REQUIRED`                                                                                                                                                 |
| **Description**        | Customer FE at `master` exposes Contact Vendor (`POST /enquiries`) but production API (`e4a7bb79`) has no enquiries router → **404**. Prod DB at `0071` lacks `0082`. |
| **Evidence**           | Batch 1A; live probe; git ancestry (`enquiries.py` not in `e4a7bb79`)                                                                                                 |
| **Affected canonical** | CAN-SOC-001, CAN-OPS-006                                                                                                                                              |
| **Launch scope**       | PLATFORM, SOCIAL                                                                                                                                                      |
| **Next action**        | Catch-up plan Wave C + coordinated API deploy; or gate Contact Vendor UI until aligned.                                                                               |

### BLK-203 — Clips API missing feature-flag gate

| Field                  | Value                                                                                                             |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Category**           | `CODE_DEFECT`                                                                                                     |
| **Description**        | `clips.py` feed/detail query `video_clips` without `clips_enabled()` (comments route checks flag; feed does not). |
| **Evidence**           | Batch 1A code review                                                                                              |
| **Affected canonical** | CAN-UX-001                                                                                                        |
| **Launch scope**       | PLATFORM                                                                                                          |
| **Next action**        | Add fail-closed flag check before enabling `clips` flag.                                                          |

---

## Resolved (Batch 0.5)

| ID                                          | Resolution                                                                                |
| ------------------------------------------- | ----------------------------------------------------------------------------------------- |
| ~~BLK-003 (Batch 0) RLS CI false-green~~    | **Resolved** — `vergeo_rls_tester` + blocking RLS step on `master`; PR #583 CI green      |
| ~~BLK-103 (Batch 0) triple 0093 collision~~ | **Resolved** — renumbered to `0093`/`0094`/`0095` (PR #583)                               |
| ~~BLK-004 (Batch 0) Registry not in repo~~  | **Resolved** — MASTER_REQUIREMENTS + traceability ingested (223 rows + REG-001 gap noted) |

---

## Safety gates (must remain enforced)

| Gate               | DB flag / env             | Observed state (2026-08-06)             |
| ------------------ | ------------------------- | --------------------------------------- |
| Public marketplace | `public_launch`           | **false** (prod + staging)              |
| Online payments    | `PAYMENTS_ENABLED` etc.   | **UNKNOWN** (OCI); code defaults OFF    |
| Payouts            | `PAYOUTS_ENABLED`         | **UNKNOWN** (OCI); code defaults OFF    |
| WAHA intake        | `waha_vendor_intake`      | **false** (staging); row absent on prod |
| Clips              | `clips`, `clips_comments` | **false** (staging); absent on prod     |

**Do not activate** in audit sessions without explicit founder approval.

---

## External dependencies

| ID      | Dependency                              | Category                 | Blocks                             |
| ------- | --------------------------------------- | ------------------------ | ---------------------------------- |
| EXT-001 | Lenco sandbox credentials (F9b)         | EXTERNAL_ACCESS_REQUIRED | CAN-FIN-002 money drills           |
| EXT-002 | Zamtel collections decision (FD-01)     | PRODUCT_DECISION         | CAN-FIN-002 checkout honesty       |
| EXT-003 | Meta WhatsApp Cloud production (F5)     | EXTERNAL_ACCESS_REQUIRED | CAN-OPS-004 notifications at scale |
| EXT-004 | Supabase PITR / backup dashboard access | EXTERNAL_ACCESS_REQUIRED | CAN-OPS-005 recovery proof         |
