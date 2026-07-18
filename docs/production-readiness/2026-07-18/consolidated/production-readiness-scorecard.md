# Production Readiness Scorecard — Vergeo5 / Convergeo

**Date:** 2026-07-18 (post-implementation refresh)  
**Master tip:** `d5c2134` (includes #293)  
**Evidence baseline:** `../foundation/*` + six document audits + `../implementation/*` + `../integration/panel-pr-integration-review.md`  
**Register:** `master-reconciliation-register.md`

## Overall verdict

**NOT PRODUCTION-READY for real-money public launch.**

Same-day merges (#274, #289–#291, #293, #294) raised several money/trust/panel items to **code-complete**. They did **not** clear staging or production evidence. Per consolidation rules, **no single readiness percentage is calculated** while any P0 lacks verified staging/production proof — a percentage would be misleading.

| Aggregate view           | Value                              |
| ------------------------ | ---------------------------------- |
| Ready areas              | 0                                  |
| Conditional areas        | 7                                  |
| Blocked areas            | 8                                  |
| Not auditable dimensions | 3 (Admin deep UI, API SHA, Uptime) |
| P0 open (register §12)   | 13 (plus scope-conditional)        |

**Safe current use:** invite/demo catalogue with `public_launch=false`.  
**Unsafe:** claiming marketplace GMV, enabling open public launch, or taking real prepaid funds.

---

## Scoring rubric

| Score             | Meaning                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| **Ready**         | Live VERIFIED evidence; no open P0/P1 for this area’s launch path                      |
| **Conditional**   | Shell/config present; usable only under documented gates (invite, demo, feature flags) |
| **Blocked**       | Open P0 or VERIFIED MISSING critical path for this area                                |
| **Not Auditable** | Required probe/access unavailable; cannot upgrade without new evidence                 |

Each area below splits **Live production** vs **Master code** so merged work is not scored as missing.

---

## Area scores

| Area                        | Score       | Live production                                                                          | Master code (`d5c2134`)                                                                       | Blocking MR-IDs                  | What flips the score                                                    |
| --------------------------- | ----------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------- | ----------------------------------------------------------------------- |
| **Customer**                | Conditional | SHA ~`8cc1fa0` at foundation; sell CTA down; categories/compare 404; SW 404; demo public | #289: categories/compare/calendar redirect, logistics copy, false-success UI, API fail-closed | MR-C01, MR-D01, MR-C02*, MR-C04* | *Deploy tip + env; demo labelled; SW 200                                |
| **Vendor**                  | Conditional | Login-gated; KYC orphans live; listing UX NOT_AUDITABLE                                  | #291 UI honesty; #293 capability freeze (needs migrate)                                       | MR-D02, MR-V01–V03               | Apply `0056` + sandbox KYC; JWT audit                                   |
| **Admin**                   | Conditional | Access-gated; no role UI; analytics empty; deep UI NA                                    | #290 empty-state/D16 honesty; #293 KYC admin APIs                                             | MR-A01, MR-A02, MR-A04*, MR-A06  | *Deploy; founder RBAC decision; Access audit                            |
| **Authentication / RBAC**   | Blocked     | `0051` unapplied; single `admin`; manual grants                                          | Hook migration in repo                                                                        | MR-S02, MR-R04, MR-A02           | Hook applied or exception; isolation VERIFIED; admin-tier decision      |
| **Database / RLS**          | Blocked     | Drift ≤0050+skew0052; missing 0051/53–**56**; FORCE RLS false on ticket tiers            | Repo tip through `0056_kyc_integrity.sql`                                                     | MR-S01, MR-R01, MR-R02           | Migrations reconciled; FORCE RLS decision; RLS suite green              |
| **Catalogue / inventory**   | Conditional | Canonical model; Phase-1 categories; all demo; reservations=0                            | Unchanged core; panel browse routes in #289                                                   | MR-D01, MR-B05, MR-S05*          | Real/labelled supply; reserve→pay; class/condition if claimed           |
| **Checkout / payments**     | Blocked     | **0** payments; Zamtel flag conflict; false-success unproven live                        | **#274** collection ledger; **#289** UI hardening; kill-switch safe-by-default                | MR-B01, MR-O03, MR-L04           | Sandbox MoMo+card VERIFIED ledger; Zamtel gated; no false success       |
| **Escrow / reconciliation** | Blocked     | Recon cron live; release workflow MISSING; ledger empty                                  | **#294** capture-before-release; release-job JSON in repo only                                | MR-W01, MR-B01, MR-B01b, MR-W05  | Hold→release→payout sandbox; idempotent retry; recon alerts             |
| **Delivery**                | Conditional | Manual Lusaka dispatch (D16) intentional; 0 orders                                       | #290 dispatch UX honesty                                                                      | — (scope)                        | Sandbox order with dispatch labels                                      |
| **Notifications**           | Conditional | Dispatch workflow live; 0 operational sends proven this audit                            | Outbox design present                                                                         | MR-W03                           | Sandbox outbox drain                                                    |
| **Automations**             | Blocked     | Only 2/18 workflows live                                                                 | Repo JSON for release/tickets/backup                                                          | MR-W01, MR-W02, MR-W04           | Critical workflows active + successful ticks                            |
| **Media / storage**         | Conditional | Cloudinary; 134 demo images; KYC private storage lightly audited                         | Unchanged                                                                                     | MR-D01, MR-V04*                  | Non-demo media; evidence rules if used goods                            |
| **Analytics**               | Conditional | Tables = 0                                                                               | #290/#291 empty-state honesty                                                                 | MR-A04, MR-O01                   | Non-zero aggregates match tiles                                         |
| **Security**                | Blocked     | FORCE RLS gaps; leaked-password off; secret-scan non-blocking; live KYC orphans          | #293 integrity code; Access on admin                                                          | MR-R01, MR-R03, MR-R05, MR-D02   | FORCE RLS closed; CI blocking; `0056`+repair; advisors cleared/accepted |
| **Observability**           | Blocked     | No Vergeo5 Sentry; uptime NA                                                             | Sentry SDK code present (DSN-gated)                                                           | MR-O01, MR-O02                   | Sentry test events + uptime green                                       |
| **Backups / recovery**      | Blocked     | Backup workflow missing; restore NA                                                      | Runbook/scripts exist                                                                         | MR-W04, MR-O04                   | Dated backup + restore drill VERIFIED                                   |
| **CI / CD**                 | Conditional | Frontend SHAs known at foundation; API SHA NA; staging stub                              | Panel/money CI green on merges                                                                | MR-R05, MR-B10, MR-O05           | Blocking security gates; API digest pinned; rollback drill              |

\*Scope-conditional hard-block only if launch claims include Class D/E / used goods.

---

## Score distribution (counts only — not a readiness %)

```
Ready:          ████░░░░░░░░░░░░░░░░  0
Conditional:    ██████████████░░░░░░  7
Blocked:        ████████████████░░░░  8
```

Do **not** convert the above into “X% ready.” Blocked money/trust/ops areas dominate launch risk.

---

## Launch posture by product slice

| Slice                                     | Posture            | Notes                                           |
| ----------------------------------------- | ------------------ | ----------------------------------------------- |
| Demo browse (invite, no money)            | Conditional OK     | Disclose demo; keep `public_launch=false`       |
| Real-money catalogue (goods)              | **Blocked**        | MR-B01, MR-B01b, MR-W01, MR-O03, MR-L01, MR-D01 |
| Events / paid tickets                     | **Blocked**        | MR-W02, MR-B01, MR-B03, MR-B04, MR-R01, MR-D04  |
| Services RFQ                              | Conditional / thin | APIs present; 0 jobs; money P0 when quotes→pay  |
| Open public launch (`public_launch=true`) | **Blocked**        | All P0s in register §12                         |

---

## Aspiration vs committed (scorecard filter)

| Treat as launch requirement (COMMITTED)              | Do not score as launch defects (ASPIRATION / DOC)     |
| ---------------------------------------------------- | ----------------------------------------------------- |
| Prepaid ledger + release accounting + escrow release | Django / Meilisearch / Celery / DPO / Yango / Railway |
| Ticket issuance automation                           | PWYW, promo/affiliate, City Guides, AR, Zimbabwe      |
| Migration parity + RLS FORCE decisions               | 75–100 / 840 vendor scale targets                     |
| KYC auditable trail                                  | Class C–E catalogue modes until product claims them   |
| Legal F4; Zamtel decision; admin RBAC decision       | Vernacular launch (D27 EN-first)                      |
| Sentry/uptime/backup/restore/rollback                | Subscription billing, referrals, promoted listings    |

---

## NOT_AUDITABLE access still required

| Need                                                  | Unlocks                                         |
| ----------------------------------------------------- | ----------------------------------------------- |
| Lenco sandbox MoMo+card checkout                      | MR-B01, MR-B01b, MR-O03, payments/escrow scores |
| Host `API_IMAGE_TAG` / GHCR digest                    | MR-B10, CI/CD score                             |
| Supabase Auth dashboard (hook enable)                 | MR-S02                                          |
| Vercel env: `NEXT_PUBLIC_VENDOR_APP_URL`, Sentry DSNs | MR-C01, MR-O01                                  |
| Cloudflare Access auditor session                     | MR-A06                                          |
| Vendor test JWT                                       | MR-V01                                          |
| OCI backup listing or host cron proof                 | MR-O04                                          |
| GitHub branch-protection UI                           | MR-R05                                          |
| UptimeRobot / equivalent                              | MR-O02                                          |
| Written legal counsel artifact                        | MR-L01                                          |
| Production re-probe after next Vercel/API deploy      | Customer/Vendor/Admin live scores               |

---

## Score change log

| Date       | Area                    | From → To                                                               | Evidence pointer                      | MR / PR         |
| ---------- | ----------------------- | ----------------------------------------------------------------------- | ------------------------------------- | --------------- |
| 2026-07-18 | Checkout / payments     | Blocked (hook absent) → Blocked (code DONE, staging FAIL)               | #274 `settlement.py`; live payments=0 | MR-B01          |
| 2026-07-18 | Escrow / reconciliation | Blocked → Blocked (code DONE #294; n8n still MISSING)                   | #294 report; n8n 2 workflows          | MR-B01b, MR-W01 |
| 2026-07-18 | Security / Vendor       | Blocked → Blocked (code DONE #293; migrate FAIL)                        | #293 `0056`; live orphans             | MR-D02          |
| 2026-07-18 | Customer / Admin        | Conditional (live 404s) → Conditional (code DONE #289/#290; undeployed) | Integration review #292               | MR-C02, MR-A04  |

_Do not mark the system production-ready while any P0 in `master-reconciliation-register.md` §12 lacks staging-verified and (where applicable) production-verified evidence._
