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

**Current:** **FAIL** — live `payments=0`, `ledger_transactions=0`; sandbox drills BLOCKED_EXTERNAL (Prompt 8).

### G4 — No false payment-success state

**Current:** **FAIL** — no staging E2E false-success pack attached to live tip.

### G5 — Workflow reliability / retries

**Current:** **FAIL** — live n8n: 3 workflows, all `active=false` (fail-closed under API 502). Escrow/tickets ticks not proven.

### G6 — Error monitoring and actionable logs

**Current:** **BLOCKED_EXTERNAL** — no Vergeo5 Sentry projects (create 403); uptime NOT_AUDITABLE (Prompt 9 / PR #378).

### G7 — Backups and restore proof

**Current:** **FAIL** — no approved backup workflow/artifact; restore CONDITIONAL on local-ci drill dump only (Prompt 10 / PR #379).

### G8 — Critical test suite and CI gates

**Current:** **FAIL** — `secret-scan` and other jobs still `continue-on-error`; branch protection NOT_AUDITABLE. App lint/type/test green on merges does not clear this gate.

### G9 — Deployment / rollback evidence

**Current:** **FAIL** — API digest UNKNOWN; migration tip drift; rollback drill NOT_RUN (Prompt 10). Frontend SHAs recorded but behind tip.

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
