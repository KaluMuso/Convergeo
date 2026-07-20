# Release Gates — Vergeo5 / Convergeo

**Date:** 2026-07-20 (Prompt 12 fresh audit)  
**Purpose:** Exact automated and manual evidence required before real-money / public release.  
**Rule:** A gate is **PASS** only with VERIFIED evidence at the required maturity layer. PARTIAL / CODE_COMPLETE-only / programme docs on unmerged branches ≠ PASS for launch.  
**While any P0 gate fails, the system is not production-ready** (no single blended readiness %).

**Authoritative go/no-go:** `docs/production-readiness/2026-07-20/go-no-go-report.md`  
**Board:** `docs/production-readiness/2026-07-20/current-implementation-board.md`

Allowed statuses: `PASS` · `FAIL` · `CONDITIONAL` · `BLOCKED_EXTERNAL` · `NOT_APPLICABLE`.

---

## Maturity required per gate class

| Gate class                           | Minimum maturity to PASS                                               |
| ------------------------------------ | ---------------------------------------------------------------------- |
| Code/unit invariants (CI)            | CODE_COMPLETE on release commit + green CI                             |
| Money, escrow, KYC privileges, RLS   | **STAGING_VERIFIED** (then PRODUCTION_VERIFIED before open real-money) |
| Public positioning / `public_launch` | **PRODUCTION_VERIFIED** probes on live URLs + flags                    |
| Legal                                | Written artifact (not code)                                            |

---

## Staging gates (must PASS before production money enablement)

| ID  | Gate                                    | Pass criteria                                                     | Current (2026-07-20)                                                                      |
| --- | --------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| S0  | Staging schema target                   | Agreed migrations applied without tip collision                   | **FAIL** — live tip `0063_revoke…` ≠ repo `0063_refunds_source_key`; `0064` unapplied     |
| S1  | Sandbox MoMo prepaid → ledger           | `CHARGE_RECEIVED` balanced; idempotent replay                     | **BLOCKED_EXTERNAL** — F9b + API 502 (Prompt 8 / PR #377 — see go-no-go-report §2)        |
| S2  | Sandbox card prepaid → ledger           | Same                                                              | **BLOCKED_EXTERNAL** — same                                                               |
| S3  | Release accounting drill                | `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR`; double-tick safe | **FAIL** — not executed; money n8n unpublished                                            |
| S4  | n8n release + tickets active on staging | Authenticated ticks succeed; no double release/issue              | **FAIL** — 0 active money/release workflows (Prompt 7 / PR #376 — see go-no-go-report §2) |
| S5  | KYC lifecycle drill                     | submit→under_review→approve; orphan report                        | **FAIL** — `0056` applied; drill not run (`kyc_records=0`)                                |
| S6  | False-success E2E                       | Pending/failed ≠ paid; COD isolated                               | **FAIL** — Playwright CODE on PR #370; not staging-verified                               |
| S7  | Staging UAT notes                       | Written pack attached                                             | **FAIL**                                                                                  |

---

## P0 production gates

### G0 — Authentication / authorization / RLS

**Current:** **FAIL** — RLS on for money/PII sample; FORCE RLS **false** on `ticket_type_instances`, `ticket_type_price_tiers`, `product_relations`; repo `0064_force_rls_launch_tables` **not applied**; `0056` **is** applied.

Evidence: Supabase SQL 2026-07-20 (`go-no-go-report.md` §1).

### G1 — Customer / vendor / admin route integrity

**Current:** **FAIL** — customer/vendor health 200; admin Access 302 OK; **API healthz/readyz/fingerprint 502**; frontend prod SHAs behind master `d9839db`.

### G2 — No localhost production links

**Current:** **CONDITIONAL** — probed customer HTML has **zero** localhost leaks (**PASS** aspect); seller CTA intentionally **disabled** (invite-only honesty), not a live vendor CTA.

### G3 — Payment ledger / reconciliation correctness

| Check                        | Automated   | Manual          | Pass criteria                            |
| ---------------------------- | ----------- | --------------- | ---------------------------------------- |
| Sandbox MoMo → ledger        | S1          | Lenco match     | Collection posts (#274) STAGING_VERIFIED |
| Sandbox card → ledger        | S2          | Same            | Same                                     |
| Release capture → vendor net | S3          | Recon fields    | #294 invariants STAGING_VERIFIED         |
| Webhook idempotency          | Replay      | —               | Single ledger txn                        |
| Recon cron                   | n8n success | Forced mismatch | Alerted; no silent drift                 |
| Integer ngwee only           | Unit tests  | Review          | No float money math                      |

**Current:** FAIL — CODE_COMPLETE only (#274/#294); live `payments=0`, `ledger_transactions=0`. Prompt 8 sandbox drill **BLOCKED_EXTERNAL** (`docs/production-readiness/2026-07-20/lenco-sandbox-money-drill.md`) — no F9b creds; API 502; tip mismatch.

---

### G4 — No false payment-success state

| Check         | Automated   | Manual | Pass criteria                                                                                |
| ------------- | ----------- | ------ | -------------------------------------------------------------------------------------------- |
| Pending UI    | E2E abandon | —      | Not success                                                                                  |
| Webhook delay | E2E         | —      | Success only after confirmed policy (order_confirmed / confirming≠paid; ledger per contract) |
| COD path      | E2E ≤K500   | —      | Never claims MoMo success                                                                    |

**Current:** FAIL — UI CODE_COMPLETE (#289); staging E2E open; Prompt 8 false-success matrix **NOT RUN** (BLOCKED_EXTERNAL).

---

### G5 — Workflow reliability / retries

| Check                                  | Automated              | Manual                   | Pass criteria   |
| -------------------------------------- | ---------------------- | ------------------------ | --------------- |
| Escrow auto-release active             | n8n active release-job | Sandbox release tick     | MR-W01          |
| Tickets-issue (+ event-release) active | n8n                    | Paid ticket exactly-once | MR-W02          |
| Internal ticks auth                    | Unauthorized → 401/403 | —                        | Tokens required |
| Notification dispatch                  | Live workflow          | Sandbox send             | Outbox drains   |

**Current:** FAIL (2026-07-20: dispatch + payment recon **unpublished** fail-closed under API 502; release/tickets never activated — Prompt 7 `n8n-fleet-import-verify.md` + Prompt 8 did not activate money workflows).

---

### G6 — Error monitoring and actionable logs

| Check                             | Automated       | Manual     | Pass criteria                  |
| --------------------------------- | --------------- | ---------- | ------------------------------ |
| Sentry projects exist             | Sentry list     | —          | Vergeo5 projects present       |
| Test error ingested               | Trigger per app | Event link | Release tags match             |
| Uptime on health                  | Monitor API     | —          | Monitors green                 |
| Payment/webhook errors actionable | Sentry/log      | —          | Alert on signature/ledger fail |

**Current:** FAIL (2026-07-20 Prompt 9: repo scrub/tags/test-paths/uptime-auth CODE_COMPLETE; Sentry `create_project` 403; no test-event ingestion; uptime alert NOT_AUDITABLE — see `…/2026-07-20/observability-live-evidence.md`).

---

### G7 — Backups and restore proof

| Check                | Automated                 | Manual               | Pass criteria             |
| -------------------- | ------------------------- | -------------------- | ------------------------- |
| Scheduled backup     | n8n or host cron listing  | OCI names/dates only | Dated artifact within RPO |
| Restore drill        | —                         | Scratch restore      | Documented success        |
| Pre-migration backup | Checklist before DB-01/02 | —                    | Timestamp before migrate  |

**Current:** FAIL.

Evidence 2026-07-20 (`docs/production-readiness/2026-07-20/ops-drills/`): approved n8n/OCI backup workflow+artifact **absent**; CONDITIONAL isolated restore of a `backup_mode=drill` local-ci dump only (checksum OK, RTO numeric ≤30min, production not overwritten). Does **not** clear G7.

---

### G8 — Critical test suite and CI gates

**Current:** **FAIL** — `secret-scan` and other jobs still `continue-on-error`; branch protection NOT_AUDITABLE. App lint/type/test green on merges does not clear this gate.

### G9 — Deployment / rollback evidence

| Check                      | Automated           | Manual                 | Pass criteria                                  |
| -------------------------- | ------------------- | ---------------------- | ---------------------------------------------- |
| Frontend SHAs recorded     | Vercel deployments  | —                      | SHA per app                                    |
| API image digest recorded  | Host/GHCR           | —                      | Digest ≠ unknown                               |
| DB migrations match target | `schema_migrations` | —                      | Incl. agreed `0056`                            |
| Rollback drill             | —                   | Prior Vercel + API tag | Time recorded                                  |
| Feature flags              | SQL flags           | —                      | `public_launch` intentional; Zamtel matches UI |

**Current (2026-07-20 Prompt 6):** FAIL / NO-GO. Frontend prod SHAs **recorded** (customer `cde40bf`, vendor `5a4668a`, admin `2f99711`) but **behind** master tip `d9839db`. Live migration tip = `0063_revoke_execute_review_reply_guards` (not repo tip: source_key + FORCE RLS unapplied; RC-02 collision). API host digest **NOT_AUDITABLE** (`api.vergeo5.com` **502**); GHCR `latest` digest known but not proof of running container. Rollback drill still open. Evidence: `docs/production-readiness/2026-07-20/deploy-migration-truth.md`.

---

## P1 gates (required before open public positioning)

| ID  | Gate                                  | Current (2026-07-20)                                                               |
| --- | ------------------------------------- | ---------------------------------------------------------------------------------- |
| G10 | Seller CTA live                       | **FAIL** — `/en/sell` CTA disabled invite-only                                     |
| G11 | Demo catalogue remediated/labelled    | **CONDITIONAL** — exclusion CODE (#368 path); API 502 blocks live discovery verify |
| G12 | KYC integrity live                    | **CONDITIONAL** — `0056` applied; no live drill                                    |
| G13 | Legal counsel sign-off                | **BLOCKED_EXTERNAL** — F4 absent                                                   |
| G14 | Zamtel collections decision + UI gate | **CONDITIONAL** — `zamtel_collections=false`                                       |
| G15 | Admin RBAC decision closed            | **FAIL**                                                                           |
| G16 | Staging UAT (core journeys)           | **FAIL**                                                                           |
| G17 | Panel honesty PRODUCTION_VERIFIED     | **FAIL** — tip/deploy parity incomplete                                            |

---

## P2 gates (hardening; track but do not block invite-beta)

| ID  | Gate                                | Current                                     |
| --- | ----------------------------------- | ------------------------------------------- |
| G18 | Vernacular Bemba/Nyanja core flows  | **FAIL**                                    |
| G19 | Lighthouse budgets                  | **FAIL**                                    |
| G20 | Leaked-password protection on       | **NOT_APPLICABLE** (not re-probed; no PASS) |
| G21 | Lifecycle n8n                       | **FAIL**                                    |
| G22 | Doc SoT banners on superseded plans | **FAIL**                                    |

---

## Go / No-Go (2026-07-20)

| Decision                           | Condition                                                                                                         | Today                   |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------------------- |
| **NO-GO real money**               | Any of G0–G9 = FAIL/BLOCKED_EXTERNAL/CONDITIONAL-without-waiver **or** S1–S6 ≠ PASS                               | **YES — NO_GO**         |
| **NO-GO public_launch=true**       | Any P0 FAIL **or** G10–G13 ≠ PASS                                                                                 | **YES — NO_GO**         |
| **GO invite-beta (no real money)** | Health shells OK + G2 localhost PASS + demo disclosure + `public_launch=false` + API healthy enough for catalogue | **NO** — API 502 blocks |
| **GO sandbox transaction beta**    | S0–S6 cleared + G3–G5 path                                                                                        | **NO**                  |
| **GO real-money beta**             | All P0 PASS + G13 + staging pack                                                                                  | **NO**                  |
| **GO open launch**                 | Real-money GO + G10–G17 PASS                                                                                      | **NO**                  |

### Recommendation

**NO_GO** — see `docs/production-readiness/2026-07-20/go-no-go-report.md`.

Next level `BROWSE_ONLY_CONTROLLED_BETA` blocked primarily by **G1** (API 502), **G11** live verify, and deploy tip parity (**G9** partial).

---

_Do not declare production readiness while payment reconciliation, migration rollout, FORCE RLS, workflows, monitoring, backup/restore, rollback, or live configuration evidence remains incomplete._
