# Current Readiness Truth — 2026-08-13 (reconciled 2026-08-15)

**Purpose:** Fresh, evidence-first production-readiness reconciliation superseding stale July/August-6 documents. This is the source of truth for the August 2026 implementation wave (Prompts A–H).

**Do not use as implementation truth:** `docs/production-readiness/BLOCKERS.md`, `IMPLEMENTATION_QUEUE.md`, `2026-07-20/current-implementation-board.md`, or percentage estimates from July gap reports.

**Evidence session:** 2026-08-15 UTC — GitHub API, Supabase MCP (read-only), n8n MCP, Vercel MCP, live HTTP probes.

---

## 1. Master identity and CI posture

| Field                        | Value                                                 | Evidence                                                                     |
| ---------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| `origin/master` SHA          | `d0b7635a9c4e9144d0e1d3f83f7bc8ca6f5de794`            | `git rev-parse HEAD`; API `/fingerprint`                                     |
| Latest merge                 | PR #644 STG-DRIFT-03 (2026-08-15)                     | `gh pr list --state merged`                                                  |
| Open PRs                     | **0**                                                 | `gh pr list --state open`                                                    |
| CI (`master`)                | **GREEN** — CI, Performance budgets, API image (GHCR) | Actions runs `31856166115`, `31856166107`, `31856166112`                     |
| PR #627 (navbar wordmark)    | **MERGED GREEN** (2026-08-13)                         | All checks SUCCESS including Performance budgets                             |
| Branch protection / rulesets | **NOT CONFIGURED**                                    | `gh api repos/KaluMuso/Convergeo/rulesets` → `[]`; branch protection API 403 |

**Stale assessment:** User message citing PR #627 as blocked is **superseded** — merged at `06:45Z` 2026-08-13 with green Performance budgets.

**Founder action (Manual Step A1):** Enable `master` branch protection — require PR, required CI + Performance budgets, no direct pushes. Direct asset uploads bypass review today.

---

## 2. Deployment truth

### Production

| Surface                       | SHA / digest                                   | Evidence                                                        | Matches master? |
| ----------------------------- | ---------------------------------------------- | --------------------------------------------------------------- | --------------- |
| API (`api.vergeo5.com`)       | `d0b7635a9c4e9144d0e1d3f83f7bc8ca6f5de794`     | `GET /fingerprint` → `git_sha`, `image_tag`, `build_id`         | **YES**         |
| API health                    | `{"status":"ok"}`                              | `GET /healthz`                                                  | —               |
| Customer (`www.vergeo5.com`)  | `d0b7635a9c4e9144d0e1d3f83f7bc8ca6f5de794`     | `GET /en/health` → `buildId`                                    | **YES**         |
| Vendor (`vendor.vergeo5.com`) | `d0b7635a9c4e9144d0e1d3f83f7bc8ca6f5de794`     | Vercel production deployment `dpl_6tAhzdoHM5ypU388KfzVYXb9ZmDP` | **YES**         |
| Admin (`admin.vergeo5.com`)   | **UNKNOWN** (Vercel MCP 404 on project lookup) | Not probed this session                                         | —               |

**Supersedes:** `BLOCKERS.md` BLK-003 (API behind master) — **ALREADY_CLOSED** as of this probe.

### Staging plane

| Surface           | Status                 | Notes                                                                                   |
| ----------------- | ---------------------- | --------------------------------------------------------------------------------------- |
| Staging Supabase  | `iyasmrmbcrvlfxpzescb` | Dedicated sandbox project                                                               |
| Staging API SHA   | **UNKNOWN**            | Not probed; release-control expects push-to-`staging` branch certification (RELCTRL-04) |
| Staging frontends | **UNKNOWN**            | Vercel preview deployments exist per PR history                                         |

---

## 3. Migration truth

### Git canonical tip (106 migration files)

Last files (ordered):

- `0096_listing_location_stock_service_role.sql`
- `20260802153539_rls_policy_contract_remediation.sql`
- `20260809214010_harden_event_access_ticket_lifecycle.sql`
- `20260812010000_vendor_business_archetypes.sql`
- `20260812090000_product_strategy_integrity.sql`
- `20260813063754_event_strategy_completion_foundation.sql`
- `20260813064106_product_strategy_core_contract.sql`
- `20260813150000_kyc_approve_vendor_atomic.sql`
- `20260813160000_rate_counter_scope_manifest.sql`
- `20260813160100_listing_view_surface_telemetry.sql`
- `20260813160200_security_definer_hardening.sql`

### Staging (`iyasmrmbcrvlfxpzescb`)

| Field              | Value                                                                                                                                  |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Ledger row count   | 103 (per repair plan)                                                                                                                  |
| Ledger tip (live)  | `20260813073039` `event_strategy_completion_foundation`                                                                                |
| Ledger state       | **REHEARSAL / NON-CANONICAL** — contains 7 rehearsal rows that must be normalized                                                      |
| Canonical parity   | **6 migrations pending** after ledger repair per `staging-ledger-repair-plan.md`                                                       |
| FORCE RLS (sample) | `event_categories`, `product_relations`, `service_reviews`, `ticket_type_*` → `relrowsecurity=true`, `relforcerowsecurity=true`        |
| Event money tables | `event_gmv_reservations`, `event_settlement_snapshots`, `event_refund_jobs` **exist** (schema from `20260813063754` / rehearsal alias) |

**Pending canonical migrations (post-repair):**

1. `20260812090000_product_strategy_integrity`
2. `20260813064106_product_strategy_core_contract`
3. `20260813150000_kyc_approve_vendor_atomic`
4. `20260813160000_rate_counter_scope_manifest`
5. `20260813160100_listing_view_surface_telemetry`
6. `20260813160200_security_definer_hardening`

**Status:** `DEPLOYMENT_REQUIRED` + `LIVE_VERIFICATION_REQUIRED` — ledger repair + `db push` not yet executed on canonical path (STG-DRIFT-03 merged tooling; operator execution pending).

### Production (`dpadrlxukcjbewpqympu`)

| Field                      | Value                                                              |
| -------------------------- | ------------------------------------------------------------------ |
| Ledger tip                 | `0071_vendor_listing_compare_at`                                   |
| Missing vs Git             | `0072`–`0096` + all `202608*` timestamp migrations (**35+ files**) |
| M17/M18 tables             | **Absent** — no `clips`, `waha_intake` flag rows on production     |
| FORCE RLS on launch tables | **Partial** — production never received `0064`+ band               |

**Status:** `DEPLOYMENT_REQUIRED` — production catch-up remains a founder-approved change window; do not apply blindly.

---

## 4. Feature flags and money posture

### Staging flags (live query)

| Flag                 | Enabled   |
| -------------------- | --------- |
| `public_launch`      | **false** |
| `zamtel_collections` | **false** |
| `clips`              | **false** |
| `clips_comments`     | **false** |
| `waha_vendor_intake` | **false** |
| `paid_tiers`         | **false** |
| `wallet`             | **false** |
| `abandoned_cart`     | **false** |

### Production flags (live query)

| Flag                           | Enabled                                |
| ------------------------------ | -------------------------------------- |
| `public_launch`                | **false**                              |
| `zamtel_collections`           | **false**                              |
| `paid_tiers`                   | **false**                              |
| `wallet`                       | **false**                              |
| `abandoned_cart`               | **false**                              |
| `clips` / `waha_vendor_intake` | **rows absent** (migrations unapplied) |

### Money table counts (both planes)

| Table                 | Staging | Production |
| --------------------- | ------- | ---------- |
| `payments`            | 0       | 0          |
| `orders`              | 0       | 0          |
| `ledger_transactions` | 0       | 0          |
| `refunds`             | 0       | 0          |
| `payouts`             | 0       | 0          |
| `kyc_records`         | 2       | 0          |

**Verdict:** Real-money collection has **never been exercised** on either plane. Sandbox drill remains `BLOCKED_EXTERNAL` (F9b credentials).

---

## 5. n8n workflow inventory

**Committed:** 27 JSON files under `infra/n8n/`.  
**Live (n8n MCP):** 9 workflows total.

| Workflow                         | Live state            | Git file                                     | Money-moving?        |
| -------------------------------- | --------------------- | -------------------------------------------- | -------------------- |
| Payment reconciliation crons     | **ACTIVE**            | `reconciliation.json`                        | Yes (internal ticks) |
| Reservation sweeper              | **ACTIVE**            | `reservation-sweeper.json`                   | No                   |
| Notification dispatch            | **ACTIVE**            | `notification-dispatch.json`                 | No                   |
| Embeddings cron                  | **ACTIVE**            | `embeddings-cron.json`                       | No                   |
| Analytics retention              | **ACTIVE**            | `analytics-retention.json`                   | No                   |
| Operational nudges               | **ACTIVE**            | `operational-nudges` (admin-digest adjacent) | No                   |
| Admin digest                     | **ACTIVE**            | `admin-digest.json`                          | No                   |
| Database Backup                  | **IMPORTED_INACTIVE** | `backup.json`                                | No                   |
| Shared error alert               | **IMPORTED_INACTIVE** | `money-workflow-error-alert.json`            | No                   |
| Release job                      | **IN_GIT_ONLY**       | `release-job.json`                           | **Yes**              |
| Order jobs                       | **IN_GIT_ONLY**       | `order-jobs.json`                            | **Yes**              |
| Event release                    | **IN_GIT_ONLY**       | `event-release.json`                         | **Yes**              |
| Ticket issuance                  | **IN_GIT_ONLY**       | `tickets-issue.json`                         | **Yes**              |
| Ticket release                   | **IN_GIT_ONLY**       | `tickets-release.json`                       | **Yes**              |
| Payouts                          | **IN_GIT_ONLY**       | `payouts.json`                               | **Yes**              |
| Payment sweeper                  | **IN_GIT_ONLY**       | `payment-sweeper.json`                       | Yes                  |
| Payout failure alert             | **IN_GIT_ONLY**       | `payout-failure-alert.json`                  | No                   |
| Uptime alert                     | **IN_GIT_ONLY**       | `uptime-alert.json`                          | No                   |
| WAHA intake (×2)                 | **IN_GIT_ONLY**       | `waha-intake-*.json`                         | No (flag-gated)      |
| + 9 more lifecycle/RFQ workflows | **IN_GIT_ONLY**       | various                                      | Mixed                |

**Status:** S4 automations — **LIVE_VERIFICATION_REQUIRED**. Reconciliation + sweeper active; escrow release/ticket/payout fleet **not imported**.

---

## 6. Security advisors (summary)

### Staging — notable WARN findings

- Multiple `anon`/`authenticated` can execute `SECURITY DEFINER` functions (clips guards, enquiry/rfq guards, `vendor_licence_is_valid`, etc.)
- `auth_leaked_password_protection` disabled
- RLS-enabled tables with no policies (expected for service-role-only tables: `event_gmv_reservations`, `notification_outbox`, etc.)

### Production — notable WARN findings

- `has_role`, `is_verified_business`, `search_query_facets`, `guard_kyc_record_integrity` callable by anon/authenticated
- Extensions `pg_trgm`, `vector` in public schema (production only)
- `auth_leaked_password_protection` disabled

**Recommended PR:** Prompt C (`SEC-DB-01`) — privileged-function grant audit; staging first, not production in same PR.

---

## 7. Blocker classification (historical → current)

### ALREADY_CLOSED (do not reimplement)

| ID             | Item                                               | Evidence                                                                                       |
| -------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| A-627          | Navbar wordmark / image-lint / Performance budgets | PR #627 merged green                                                                           |
| P0-RLS-FORCE   | FORCE RLS on launch tables                         | Staging: all five sample tables `relforcerowsecurity=true`; migration `0064` in repo + staging |
| P0-SOURCE-KEY  | `refunds.source_key`                               | Migration `0065` applied staging; do not reimplement                                           |
| P2-DEMO-EXCL   | Synthetic/demo catalogue exclusion                 | `services/api/tests/test_synthetic_exclusion.py`, STG-SEED-04 contract                         |
| P3-E2E-FALSE   | `checkout-false-success.spec.ts`                   | `e2e/specs/checkout-false-success.spec.ts` exists                                              |
| P3-E2E-CRIT    | `critical-path.spec.ts`                            | `e2e/specs/critical-path.spec.ts` exists                                                       |
| P4-SECRET-SCAN | Secret scan blocking                               | CI job passes on master                                                                        |
| P4-RLS-CI      | RLS matrix blocking                                | `continue-on-error` removed from RLS step (`.github/workflows/ci.yml` L587–597)                |
| EVT-ACCESS-01  | Event access/ticket lifecycle hardening            | PR #624, migration `20260809214010`, staging rehearsal alias applied                           |
| STG-SEED       | Deterministic synthetic seed contract              | PRs #615–#617, `#616`                                                                          |
| STG-TOOLS      | Recovery drill tooling                             | PR #615 STG-REC-04                                                                             |
| RELCTRL        | Release certification framework                    | PRs #637–#644                                                                                  |
| BLK-003        | API deploy behind master                           | `/fingerprint` = master SHA                                                                    |

### CODE_REMAINS (repo work — August wave priority)

| ID                           | Priority | Item                                        | Repo evidence                                                                                             | Recommended PR     |
| ---------------------------- | -------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------ |
| EVT-GMV-ATOMIC               | **P0**   | Transactional Tier-1 GMV reservations       | Table `event_gmv_reservations` exists; `gmv_cap.py` checks successful GMV only — **no reservation logic** | Prompt D           |
| EVT-SETTLEMENT-SNAPSHOT      | **P0**   | Immutable settlement terms for sold tickets | Table `event_settlement_snapshots` exists; release still uses live schedule                               | Prompt E           |
| REFUND-PROVIDER-AUTHORITY    | **P0**   | Provider-authoritative refund completion    | Refund UI/state machine may treat payout row as completion                                                | Prompt F           |
| EVT-CANCELLATION-REFUND-JOBS | **P0**   | Durable cancellation refund orchestration   | Table `event_refund_jobs` exists; no worker wired                                                         | Prompt G (after F) |
| PRIVATE-EVENT-ACCESS-PROOF   | **P1**   | Signed private-event access proof           | Private purchase fails closed; no proof chain                                                             | Prompt H           |
| SEC-DB-01                    | **P1**   | Privileged function EXECUTE grant hardening | Security advisor WARN on 10+ functions (staging)                                                          | Prompt C           |

### DEPLOYMENT_REQUIRED

| ID              | Item                                            | Blocker detail                                           |
| --------------- | ----------------------------------------------- | -------------------------------------------------------- |
| STG-LEDGER      | Staging ledger normalization + 6-migration push | `staging-ledger-repair-plan.md`; STG-DRIFT-03 merged     |
| PROD-MIG        | Production migration catch-up 0072→tip          | 35+ migrations; founder-approved window only             |
| N8N-FLEET       | Import/activate money workflows                 | 18/27 workflows IN_GIT_ONLY                              |
| BACKUP-ACTIVATE | Database backup workflow                        | Imported but **inactive**; needs SSH + destination creds |

### LIVE_VERIFICATION_REQUIRED

| ID           | Item                               | Prerequisite                                        |
| ------------ | ---------------------------------- | --------------------------------------------------- |
| S1–S6        | Lenco sandbox money drill          | F9b sandbox creds; staging at canonical tip         |
| G7           | Backup + restore RTO               | Activate backup workflow; disposable restore target |
| G6           | Sentry + uptime alert delivery     | Observability config (Prompt 9)                     |
| STG-CERT     | Staging release certification PASS | RELCTRL-04 push-to-staging evidence                 |
| E2E-DEPLOYED | Deployed-target E2E                | Staging credentials + sandbox target                |

### ENVIRONMENT_CONFIGURATION

| ID              | Item                                       | Owner                   |
| --------------- | ------------------------------------------ | ----------------------- |
| MASTER-PROTECT  | GitHub branch protection on `master`       | Founder (Manual A1)     |
| AUTH-LEAKED-PW  | Supabase leaked-password protection        | Founder (both projects) |
| RECOVERY-TARGET | Disposable Supabase recovery-drill project | Founder                 |

### FOUNDER_REQUIRED

| ID  | Item                                        |
| --- | ------------------------------------------- |
| F2  | PACRA / TPIN / legal entity                 |
| F4  | Zambian legal escrow opinion                |
| F5  | WhatsApp template approvals                 |
| F8  | COD cap decision in runtime config          |
| F9b | Lenco sandbox (then production) credentials |

### LEGAL_REQUIRED

| ID  | Item                                                  |
| --- | ----------------------------------------------------- |
| F4  | Written counsel sign-off before real-money activation |

### SUPERSEDED (do not execute July prompts verbatim)

| July prompt              | Superseded by                                           |
| ------------------------ | ------------------------------------------------------- |
| Prompt 0 (July board)    | This document                                           |
| Prompt 1 FORCE RLS       | Already on staging; production needs migration catch-up |
| Prompt 2 demo exclusion  | STG-TOOLS-INT-05 / synthetic contract                   |
| Prompt 3 E2E specs       | Specs merged; need deployed-target runs                 |
| Prompt 4 security CI     | Mostly merged; SEC-DB-01 remains                        |
| Prompt 5 backup workflow | `backup.json` exists; activation pending                |

### DELIBERATELY_DEFERRED

| Item                            | Reason                                   |
| ------------------------------- | ---------------------------------------- |
| M17 Clips customer release      | `clips=false`; F-V gates                 |
| M18 WAHA intake                 | `waha_vendor_intake=false`; no WAHA host |
| Vernacular namespace completion | Post-launch (Prompt 11)                  |
| Wallet / Zamtel collections     | D-locked / F9a                           |

---

## 8. Events audit reconciliation (`docs/plan/events-strategy-audit-2026-08.md`)

| Audit item                        | Status                    | Category                       |
| --------------------------------- | ------------------------- | ------------------------------ |
| Non-public event exposure         | **ALREADY_CLOSED**        | PR #624 / `20260809214010`     |
| Cancellation terminates tickets   | **ALREADY_CLOSED**        | Same                           |
| Paid holds expire before issuance | **ALREADY_CLOSED**        | Same                           |
| End times optional                | **ALREADY_CLOSED**        | Same                           |
| Cancellation notice honesty       | **ALREADY_CLOSED**        | Same                           |
| EVT-GMV-ATOMIC                    | **CODE_REMAINS**          | Schema scaffold only           |
| EVT-SETTLEMENT-SNAPSHOT           | **CODE_REMAINS**          | Schema scaffold only           |
| REFUND-PROVIDER-AUTHORITY         | **CODE_REMAINS**          | —                              |
| EVT-CANCELLATION-REFUND-JOBS      | **CODE_REMAINS**          | Schema scaffold only           |
| PRIVATE-EVENT-ACCESS-PROOF        | **CODE_REMAINS**          | Fail-closed until proof exists |
| Recurrence / promo / affiliates   | **DELIBERATELY_DEFERRED** | P2 roadmap                     |

---

## 9. Remaining P0 blockers

### P0 repository (ordered)

1. **STG-LEDGER** — Execute staging ledger repair + apply 6 canonical migrations
2. **EVT-GMV-ATOMIC** (Prompt D)
3. **EVT-SETTLEMENT-SNAPSHOT** (Prompt E)
4. **REFUND-PROVIDER-AUTHORITY** (Prompt F)
5. **EVT-CANCELLATION-REFUND-JOBS** (Prompt G)
6. **SEC-DB-01** (Prompt C) — can parallel after this doc lands

### P0 external / operational

1. **MASTER-PROTECT** — Branch protection (no direct-to-master uploads)
2. **F9b** — Lenco sandbox credentials for money drill
3. **F4** — Legal escrow opinion
4. **PROD-MIG** — Production migration catch-up (after staging certified)
5. **N8N-FLEET** — Import + idempotency-proof money workflows
6. **S1–S6** — Sandbox money drill evidence

---

## 10. Launch verdicts (evidence-based, no percentage invented)

| Verdict                         | Status          | Gates preventing promotion                                                                                                    |
| ------------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Browse-only controlled beta** | **CONDITIONAL** | Production DB at `0071` (missing discovery/social schema); staging not at canonical tip; no deployed-target E2E PASS evidence |
| **Staging-transaction beta**    | **NO_GO**       | EVT money invariants incomplete; no S1–S6 sandbox drill; staging ledger repair pending                                        |
| **Real-money beta**             | **NO_GO**       | All of above + F4 legal + F9b production creds + n8n release/payout fleet                                                     |
| **Public launch**               | **NO_GO**       | `public_launch=false` on both planes; all money/ops gates                                                                     |

---

## 11. Recommended execution order

```
Manual A1: protect master
→ STG-LEDGER (operator): repair + db push + staging certification
→ Prompt C: SEC-DB-01 (staging only)
→ Prompt D: EVT-GMV-ATOMIC
→ Prompt E: EVT-SETTLEMENT-SNAPSHOT
→ Prompt F: REFUND-PROVIDER-AUTHORITY
→ Prompt G: EVT-CANCELLATION-REFUND-JOBS
→ Prompt H: PRIVATE-EVENT-ACCESS-PROOF
→ N8N-FLEET import/configure (operational)
→ S1–S6 sandbox money drill (needs F9b)
→ PROD-MIG change window (after staging PASS + backup)
→ Prompt 9–10 observability + ops drills
```

---

## 12. Stale documentation corrections

| Document                               | Stale claim                 | Current truth                                                         |
| -------------------------------------- | --------------------------- | --------------------------------------------------------------------- |
| `BLOCKERS.md` (2026-08-06)             | API behind master           | API at `d0b7635a` = master                                            |
| `BLOCKERS.md`                          | Staging behind Git          | Staging ahead on rehearsal rows; **behind** on 6 canonical migrations |
| `IMPLEMENTATION_QUEUE.md`              | Next: deploy API to staging | Superseded by RELCTRL + STG-DRIFT programme                           |
| `00-status.md` (2026-08-05)            | API health UNKNOWN          | API healthy at master SHA                                             |
| `00-status.md`                         | RG-6 RLS CI false-green     | RLS step now blocking (seed step only has `continue-on-error`)        |
| July `current-implementation-board.md` | Customer behind tip         | All production frontends at `d0b7635a`                                |
| User prompt pack Prompt 0–5            | Sequential July gaps        | Mostly **ALREADY_CLOSED** — use August wave instead                   |

---

## 13. Counts by status category

| Category                   | Count |
| -------------------------- | ----- |
| ALREADY_CLOSED             | 14    |
| CODE_REMAINS               | 6     |
| DEPLOYMENT_REQUIRED        | 4     |
| LIVE_VERIFICATION_REQUIRED | 5     |
| ENVIRONMENT_CONFIGURATION  | 3     |
| FOUNDER_REQUIRED           | 5     |
| LEGAL_REQUIRED             | 1     |
| SUPERSEDED                 | 6     |
| DELIBERATELY_DEFERRED      | 4     |

---

_This document is read-only evidence. It does not mutate production, apply migrations, or enable flags. Update only when new live evidence exists._
