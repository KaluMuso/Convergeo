# Production Readiness Scorecard — Vergeo5 / Convergeo

**Date:** 2026-07-18 (refresh after PRs #274, #289–#294)  
**Evidence baseline:** `../foundation/*` + six document audits + `../implementation/*` + `../integration/panel-pr-integration-review.md`  
**Register:** `master-reconciliation-register.md`  
**Git tip:** `d5c2134` (master)

## Overall verdict

**NOT PRODUCTION-READY for real-money public launch.**

Code-complete payment collection (#274), release accounting (#288/#294), KYC integrity (#293), and panel honesty (#289–#291) improve the engineering baseline, but **staging/live evidence** for payment reconciliation, migration rollout (incl. `0056`), RLS, n8n workflows, monitoring, backup/restore, rollback, and live configuration remains incomplete. Per contract rules, **no readiness percentage is calculated** while any P0 is open, unverified, or not auditable.

| Aggregate view           | Value                        |
| ------------------------ | ---------------------------- |
| Ready areas              | 0                            |
| Conditional areas        | 7                            |
| Blocked areas            | 8                            |
| Not auditable dimensions | 3+                           |
| P0 open                  | ≥13 (plus scope-conditional) |

**Safe current use:** invite/demo catalogue with `public_launch=false`.  
**Unsafe:** claiming marketplace GMV, enabling open public launch, or taking real prepaid funds.

### Maturity layers (do not conflate)

| Layer                   | Meaning                     | Payment (#274/#294) | KYC (#293)              | Panels (#289–#291)                           |
| ----------------------- | --------------------------- | ------------------- | ----------------------- | -------------------------------------------- |
| **CODE_COMPLETE**       | Merged on master with tests | YES                 | YES                     | YES                                          |
| **STAGING_VERIFIED**    | Sandbox/staging probes PASS | **NO**              | **NO** (`0056` + drill) | **NO** (env/deploy probes)                   |
| **PRODUCTION_VERIFIED** | Live prod probes PASS       | **NO**              | **NO**                  | **NO** (foundation prod SHA still `8cc1fa0`) |

---

## Scoring rubric

| Score             | Meaning                                                             |
| ----------------- | ------------------------------------------------------------------- |
| **Ready**         | Live PRODUCTION_VERIFIED; no open P0/P1 for this area’s launch path |
| **Conditional**   | Shell/config/code present; usable only under documented gates       |
| **Blocked**       | Open P0 or VERIFIED MISSING critical path                           |
| **Not Auditable** | Required probe/access unavailable                                   |

---

## Area scores

| Area                        | Score       | Why (evidence)                                                                                                                              | Blocking MR-IDs                        | What flips the score                                               |
| --------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------ |
| **Customer**                | Conditional | Healthy site; #289 routes/payment honesty CODE_COMPLETE; sell CTA unavailable; demo public; prod deploy of panel SHA unproven vs foundation | MR-C01, MR-D01, MR-C02, MR-C04, MR-C08 | Env CTA; demo gate; deploy+probe categories/compare/SW; staging G4 |
| **Vendor**                  | Conditional | Live login-gated; #291 honesty CODE_COMPLETE; #293 API freeze CODE_COMPLETE; KYC unexercised live; listing UX NOT_AUDITABLE                 | MR-D02, MR-V01–V04                     | `0056` applied; sandbox KYC; vendor JWT audit                      |
| **Admin**                   | Conditional | Access-gated; #290 honesty CODE_COMPLETE; #293 KYC admin routes CODE_COMPLETE; no role UI; deep UI NOT_AUDITABLE                            | MR-A01, MR-A02, MR-A03, MR-A07         | RBAC decision; staging KYC drill; Access audit pack                |
| **Authentication / RBAC**   | Blocked     | OTP schema present; `0051` unapplied; single `admin` vs doc two-tier                                                                        | MR-S02, MR-R04, MR-A02                 | Hook or exception; isolation VERIFIED; admin-tier decision         |
| **Database / RLS**          | Blocked     | Healthy project; drift CONFLICT (`0051`/`0053`–`0056`); FORCE RLS false on ticket tiers                                                     | MR-S01, MR-S11, MR-R01                 | Migrations reconciled; FORCE RLS decision; isolation suite         |
| **Catalogue / inventory**   | Conditional | Canonical products+listings; Phase-1 categories VERIFIED; all demo; no `product_class`                                                      | MR-D01, MR-B05, MR-S05*                | Real/labelled supply; reserve→pay; class/condition if claimed      |
| **Checkout / payments**     | Blocked     | Lenco paths + #274 collection CODE_COMPLETE; **0** live payments; staging ledger unproven; Zamtel conflict                                  | MR-B01, MR-O03, MR-L04                 | Sandbox MoMo+card STAGING_VERIFIED; Zamtel gated                   |
| **Escrow / reconciliation** | Blocked     | #294 release accounting CODE_COMPLETE; recon cron live; **release n8n MISSING**; ledger empty                                               | MR-B01b, MR-W01, MR-W05                | Charge→capture→release staging; active release workflow            |
| **Delivery**                | Conditional | Manual Lusaka dispatch (D16); #290 UX aligned; 0 orders                                                                                     | — (scope)                              | Sandbox order with dispatch labels                                 |
| **Notifications**           | Conditional | Dispatch workflow live; 0 operational sends proven this audit                                                                               | MR-W03                                 | Sandbox outbox drain                                               |
| **Automations**             | Blocked     | Only 2/18 workflows live; escrow release + tickets-issue + backup absent                                                                    | MR-W01, MR-W02, MR-W04                 | Critical workflows active + successful ticks                       |
| **Media / storage**         | Conditional | Cloudinary public; 134 demo images; KYC private storage path reinforced in #293                                                             | MR-D01, MR-V05*                        | Non-demo media; evidence rules if used goods                       |
| **Analytics**               | Conditional | Admin/vendor empty honesty (#290/#291); tables still 0                                                                                      | MR-A04, MR-O01                         | Non-zero aggregates after traffic                                  |
| **Security**                | Blocked     | Access on admin; FORCE RLS gaps; CI secret-scan non-blocking; KYC orphans live until `0056`+repair                                          | MR-R01, MR-R05, MR-D02                 | FORCE RLS closed; CI blocking; KYC PRODUCTION_VERIFIED             |
| **Observability**           | Blocked     | No Vergeo5 Sentry; uptime NOT_AUDITABLE                                                                                                     | MR-O01, MR-O02                         | Sentry test events + uptime green                                  |
| **Backups / recovery**      | Blocked     | Backup workflow missing; restore NOT_AUDITABLE                                                                                              | MR-W04, MR-O04                         | Dated backup + restore drill VERIFIED                              |
| **CI / CD**                 | Conditional | Frontend SHAs historically aligned; API SHA NOT_AUDITABLE; panel SHAs not yet PRODUCTION_VERIFIED; staging stub                             | MR-R05, MR-B10, MR-O05                 | Blocking security gates; digests pinned; rollback drill            |

\*Scope-conditional: hard-block only if launch claims Class D/E / used goods.

---

## Score distribution (counts only — not a readiness %)

```
Ready:          ░░░░░░░░░░░░░░░░░░░░  0
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
| Services RFQ                              | Conditional / thin | APIs present; 0 jobs                            |
| Open public launch (`public_launch=true`) | **Blocked**        | All P0s in register §12                         |

---

## Code-complete but not launch-cleared (explicit)

| Work                                        | PR   | CODE_COMPLETE | STAGING_VERIFIED     | PRODUCTION_VERIFIED |
| ------------------------------------------- | ---- | ------------- | -------------------- | ------------------- |
| Prepaid collection settlement               | #274 | YES           | NO                   | NO                  |
| Product/service commission at release       | #288 | YES           | NO                   | NO                  |
| Release accounting (event/COD + invariants) | #294 | YES           | NO                   | NO                  |
| KYC integrity lifecycle + eligibility       | #293 | YES           | NO (`0056` + drills) | NO                  |
| Customer panel honesty                      | #289 | YES           | partial tests only   | NO (deploy probe)   |
| Admin panel honesty                         | #290 | YES           | NO                   | NO                  |
| Vendor panel honesty                        | #291 | YES           | NO                   | NO                  |

---

## NOT_AUDITABLE access still required

| Need                                                  | Unlocks                        |
| ----------------------------------------------------- | ------------------------------ |
| Lenco sandbox MoMo+card checkout                      | MR-B01, MR-B01b, MR-O03, G3/G4 |
| Host `API_IMAGE_TAG` / GHCR digest                    | MR-B10, G9                     |
| Supabase Auth dashboard (hook enable)                 | MR-S02                         |
| Vercel env: `NEXT_PUBLIC_VENDOR_APP_URL`, Sentry DSNs | MR-C01, MR-O01                 |
| Cloudflare Access auditor session                     | MR-A07                         |
| Vendor test JWT                                       | MR-V02                         |
| OCI backup listing / host cron proof                  | MR-O04                         |
| GitHub branch-protection UI                           | MR-R05                         |
| UptimeRobot / equivalent                              | MR-O02                         |
| Written legal counsel artifact                        | MR-L01                         |
| Staging project with applied `0051`/`0053`–`0056`     | MR-S01, MR-S11, G0             |

---

## Score change log

| Date       | Area                                  | From → To                     | Evidence pointer                      | MR closed                 |
| ---------- | ------------------------------------- | ----------------------------- | ------------------------------------- | ------------------------- |
| 2026-07-18 | Checkout / Escrow (code only)         | Blocked → still Blocked       | #274/#294 CODE_COMPLETE; staging open | none (maturity note only) |
| 2026-07-18 | Security / Vendor / Admin (code only) | Blocked/Conditional unchanged | #293 CODE_COMPLETE; `0056` unapplied  | none                      |
| 2026-07-18 | Customer / Vendor / Admin honesty     | Conditional (improved shell)  | #289–#291 CODE_COMPLETE               | none                      |

---

_Do not mark the system production-ready while any P0 in `master-reconciliation-register.md` §12 is open, unverified, or not auditable — including when the only remaining gap is STAGING_VERIFIED / PRODUCTION_VERIFIED evidence._
