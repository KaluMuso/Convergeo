# Production Readiness Scorecard — Vergeo5 / Convergeo

**Date:** 2026-07-18  
**Evidence baseline:** `../foundation/*` + six document audits in `../document-audits/*`  
**Register:** `master-reconciliation-register.md`

## Overall verdict

**NOT PRODUCTION-READY for real-money public launch.**

Multiple **P0** blockers remain open, unverified, or not auditable (ledger posting, escrow/ticket automations, migration drift, KYC integrity, legal sign-off, payment false-success risk). Per consolidation rules, **no single readiness percentage is calculated** while any P0 is open — a percentage would be misleading.

| Aggregate view             | Value                        |
| -------------------------- | ---------------------------- |
| Ready areas                | 0                            |
| Conditional areas          | 6                            |
| Blocked areas              | 8                            |
| Not auditable areas        | 3                            |
| P0 open (see register §12) | ≥12 (plus scope-conditional) |

**Safe current use:** invite/demo catalogue with `public_launch=false`; parallel remediation on panel branches. **Unsafe:** claiming marketplace GMV, enabling open public launch, or taking real prepaid funds.

---

## Scoring rubric

| Score             | Meaning                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| **Ready**         | Live VERIFIED evidence; no open P0/P1 for this area’s launch path                      |
| **Conditional**   | Shell/config present; usable only under documented gates (invite, demo, feature flags) |
| **Blocked**       | Open P0 or VERIFIED MISSING critical path for this area                                |
| **Not Auditable** | Required probe/access unavailable; cannot upgrade without new evidence                 |

---

## Area scores

| Area                        | Score       | Why (evidence)                                                                                                            | Blocking MR-IDs                | What flips the score                                                                     |
| --------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------------- |
| **Customer**                | Conditional | `www.vergeo5.com` healthy; SHA `8cc1fa0`; sell CTA unavailable; demo catalogue public; PWA SW 404; categories/compare 404 | MR-C01, MR-D01, MR-C02, MR-C04 | Seller CTA live; demo gated/labelled; critical browse routes green; SW 200               |
| **Vendor**                  | Conditional | `vendor.vergeo5.com` live login-gated; KYC unexercised; listing UX NOT_AUDITABLE; scanner offline incomplete              | MR-D02, MR-V01–V03             | Sandbox KYC trail; vendor test JWT audit; listing create E2E                             |
| **Admin**                   | Conditional | Access-gated live; no role UI; analytics empty; deep UI NOT_AUDITABLE                                                     | MR-A01, MR-A02, MR-A04, MR-A06 | Role path decided+tested; moderation/analytics proven behind Access                      |
| **Authentication / RBAC**   | Blocked     | Phone OTP schema present; `0051` role hook unapplied; single `admin` role vs doc two-tier; manual grants                  | MR-S02, MR-R04, MR-A02         | Hook applied **or** exception; role isolation tests VERIFIED; admin-tier decision closed |
| **Database / RLS**          | Blocked     | Healthy project; migration drift CONFLICT; FORCE RLS false on ticket tier tables; operator≠RLS                            | MR-S01, MR-R01, MR-R02         | Migrations reconciled; FORCE RLS decision VERIFIED; RLS isolation suite green            |
| **Catalogue / inventory**   | Conditional | Canonical products+listings; Phase-1 categories VERIFIED; all demo; no `product_class`; reservations unproven             | MR-D01, MR-B05, MR-S05*        | Real/labelled supply; reserve→pay proven; class/condition if claimed                     |
| **Checkout / payments**     | Blocked     | Lenco paths in code; **0** payments; prepaid→ledger PARTIAL; Zamtel conflict; false-success risk                          | MR-B01, MR-O03, MR-L04         | Sandbox MoMo+card VERIFIED ledger; no false success; Zamtel gated                        |
| **Escrow / reconciliation** | Blocked     | Escrow config 48h; recon cron live; **release workflow MISSING**; ledger empty                                            | MR-W01, MR-B01, MR-W05         | Hold→release→payout sandbox; idempotent retry; recon alerts                              |
| **Delivery**                | Conditional | Manual Lusaka dispatch (D16) — intentional; courier APIs correctly absent; unexercised (0 orders)                         | — (scope)                      | Sandbox order with dispatch labels; copy matches D16                                     |
| **Notifications**           | Conditional | Dispatch workflow live; WhatsApp/SMS/email outbox design; 0 operational sends proven this audit                           | MR-W03                         | Sandbox outbox drain; opt-out respected                                                  |
| **Automations**             | Blocked     | Only 2/18 workflows live; escrow release + tickets-issue + backup absent                                                  | MR-W01, MR-W02, MR-W04         | Critical workflows active + successful ticks                                             |
| **Media / storage**         | Conditional | Cloudinary public; 134 demo images; private KYC storage not deeply audited                                                | MR-D01, MR-V04*                | Non-demo media; evidence rules if used goods                                             |
| **Analytics**               | Conditional | Admin UI exists; `analytics_events`/`funnel_events` = 0                                                                   | MR-A04, MR-O01                 | Non-zero aggregates match tiles after traffic                                            |
| **Security**                | Blocked     | Access on admin; FORCE RLS gaps; leaked-password off; CI secret-scan non-blocking; KYC integrity                          | MR-R01, MR-R03, MR-R05, MR-D02 | FORCE RLS closed; CI blocking; KYC trail; advisors cleared/accepted                      |
| **Observability**           | Blocked     | No Vergeo5 Sentry projects; uptime NOT_AUDITABLE; production errors may be invisible                                      | MR-O01, MR-O02                 | Sentry test events + uptime green                                                        |
| **Backups / recovery**      | Blocked     | Backup workflow missing; restore proof NOT_AUDITABLE                                                                      | MR-W04, MR-O04                 | Dated backup artifact + restore drill VERIFIED                                           |
| **CI / CD**                 | Conditional | Frontend prod SHAs aligned; API SHA NOT_AUDITABLE; secret-scan/Lighthouse `continue-on-error`; staging stub               | MR-R05, MR-B10, MR-O05         | Blocking security gates; API digest pinned; rollback drill                               |

\*Scope-conditional: only hard-block if launch claims include Class D/E / used goods.

---

## Score distribution (counts only — not a readiness %)

```
Ready:          ████░░░░░░░░░░░░░░░░  0
Conditional:    ████████████░░░░░░░░  6
Blocked:        ████████████████░░░░  8
Not Auditable:  (folded into area notes; 3 area-level NA dimensions: Admin deep UI, API SHA, Uptime)
```

Do **not** convert the above into “X% ready.” Blocked money/trust areas dominate launch risk.

---

## Launch posture by product slice

| Slice                                     | Posture            | Notes                                                 |
| ----------------------------------------- | ------------------ | ----------------------------------------------------- |
| Demo browse (invite, no money)            | Conditional OK     | Disclose demo; keep `public_launch=false`             |
| Real-money catalogue (goods)              | **Blocked**        | MR-B01, MR-W01, MR-O03, MR-L01, MR-D01                |
| Events / paid tickets                     | **Blocked**        | MR-W02, MR-B01, MR-B03, MR-B04, MR-R01, MR-D04        |
| Services RFQ                              | Conditional / thin | APIs present; 0 jobs; not a money P0 until quotes→pay |
| Open public launch (`public_launch=true`) | **Blocked**        | All P0s in register §12                               |

---

## NOT_AUDITABLE access still required

| Need                                                                        | Unlocks                                |
| --------------------------------------------------------------------------- | -------------------------------------- |
| Lenco sandbox MoMo+card checkout                                            | MR-B01, MR-O03, escrow/payments scores |
| Host `API_IMAGE_TAG` / GHCR digest                                          | MR-B10, CI/CD score                    |
| Supabase Auth dashboard (hook enable, providers)                            | MR-S02                                 |
| Vercel env presence (names only): `NEXT_PUBLIC_VENDOR_APP_URL`, Sentry DSNs | MR-C01, MR-O01                         |
| Cloudflare Access auditor session                                           | MR-A06                                 |
| Vendor test JWT                                                             | MR-V01                                 |
| OCI backup listing or host cron proof                                       | MR-O04                                 |
| GitHub branch-protection UI                                                 | MR-R05                                 |
| UptimeRobot / equivalent                                                    | MR-O02                                 |
| Written legal counsel artifact                                              | MR-L01                                 |

---

## Score change log (for coding sessions)

When closing a blocker, update this table — never silently edit area scores.

| Date         | Area | From → To | Evidence pointer | MR closed |
| ------------ | ---- | --------- | ---------------- | --------- |
| _(none yet)_ | —    | —         | —                | —         |

---

_Do not mark the system production-ready while any P0 in `master-reconciliation-register.md` §12 is open, unverified, or not auditable._
