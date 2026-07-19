# Live Beta Prioritized Backlog — 2026-07-19

**Source:** `live-beta-experience-audit.md` + panel backlogs + founder decision brief  
**Priority:** P0 = live breakage / trust / unusable conversion · P1 = engagement/conversion · P2 = retention · Later = staging / migrations / payments / founder decisions

---

## P0 — Live breakage, security/trust, unusable conversion

| ID       | Surface  | Title                                                | Evidence                                         | Wave                                | Depends                      |
| -------- | -------- | ---------------------------------------------------- | ------------------------------------------------ | ----------------------------------- | ---------------------------- |
| LB-P0-01 | Customer | Promote categories fix to production aliases         | Prod 500 digest `3012388270`; #298 on master     | Ops promote (not code)              | Vercel prod deploy           |
| LB-P0-02 | Customer | Fail-closed API base on cart/checkout/PLP/search/PDP | `localhost:8000` fallbacks in conversion clients | **Wave 1**                          | none                         |
| LB-P0-03 | Customer | Search/PLP distinguish unavailable vs empty          | Failure currently collapses to empty/silent      | **Wave 1**                          | none                         |
| LB-P0-04 | Vendor   | Fail-closed API base (VEND-11)                       | Many `?? localhost:8000` clients                 | **Wave 1**                          | none                         |
| LB-P0-05 | Admin    | Fail-closed API base (ADM-11)                        | All domain `api.ts` localhost fallback           | **Wave 1**                          | none                         |
| LB-P0-06 | Customer | Soften overclaim “verified vendors” / badge honesty  | Live KYC records=0; hero + browse copy           | **Wave 1** (copy); badge gate Later | FD-04 / #293 deploy for full |
| LB-P0-07 | Cross    | Never enable real prepaid without ledger proof       | G3/G4 NO-GO                                      | **Later**                           | Staging money                |

---

## P1 — Immediate engagement & conversion

| ID       | Surface  | Title                                                          | Wave       | Notes                      |
| -------- | -------- | -------------------------------------------------------------- | ---------- | -------------------------- |
| LB-P1-01 | Customer | Mobile categories entry; fix duplicate bottom-nav Account tabs | **Wave 1** | Discovery                  |
| LB-P1-02 | Customer | Live cart badge on mobile TopNav                               | **Wave 1** | Conversion                 |
| LB-P1-03 | Customer | Product card: no null-slug → `/c/all`                          | **Wave 1** | Trust                      |
| LB-P1-04 | Customer | PDP loading/error labels ≠ “coming soon”                       | **Wave 1** | Trust                      |
| LB-P1-05 | Customer | Search suggestion terms i18n (en/fr/zh)                        | **Wave 1** | i18n                       |
| LB-P1-06 | Customer | Services rail title without false geo (“near you”)             | **Wave 1** | Honesty                    |
| LB-P1-07 | Admin    | Moderation + Config hub pages (dead nav)                       | **Wave 1** | Ops clarity                |
| LB-P1-08 | Customer | Set `NEXT_PUBLIC_VENDOR_APP_URL` (CUST-01)                     | Ops        | Env only                   |
| LB-P1-09 | Customer | Demo catalogue disclosure/exclude (CUST-02)                    | Later      | FD-04                      |
| LB-P1-10 | Vendor   | Services/jobs/returns/disputes empty+error parity              | Wave 2     | After W1                   |
| LB-P1-11 | Admin    | Permission-denied parity on KYC/disputes/flags                 | Wave 2     | Reuse dashboard classifier |

---

## P2 — Desirable retention / polish

| ID       | Title                                            | Wave              |
| -------- | ------------------------------------------------ | ----------------- |
| LB-P2-01 | Lighthouse Fast-3G budgets (CUST-11)             | Later             |
| LB-P2-02 | Events Phase-1 lenses when supply exists         | Later             |
| LB-P2-03 | Escrow trust UX wired to real statuses (CUST-09) | Later (MR-B01)    |
| LB-P2-04 | Cart free-delivery nudge honesty vs zone fees    | Wave 2            |
| LB-P2-05 | Replace emoji bottom-nav with token icons        | Wave 2            |
| LB-P2-06 | Wishlist                                         | **OUT** (CUST-12) |

---

## Later — staging, migrations, payments, founder decisions

| ID     | Title                                                   | Gate                              |
| ------ | ------------------------------------------------------- | --------------------------------- |
| LB-L01 | Staging plane provision (paused this program)           | Founder/ops                       |
| LB-L02 | Apply `0056` + deploy KYC API routes                    | DB-02; no prod apply this session |
| LB-L03 | Prepaid MoMo/card staging reconciliation evidence       | G3/G4                             |
| LB-L04 | n8n release + tickets workflows                         | N8N-01/02                         |
| LB-L05 | Backup/restore + observability (Sentry)                 | OPS-01/03                         |
| LB-L06 | FD-01…FD-12 decisions                                   | Founder brief                     |
| LB-L07 | Storefront verified badge = auditable eligibility only  | CUST-13 after #293 live           |
| LB-L08 | Redirect `/privacy`→`/legal/privacy` (optional hygiene) | Low                               |

---

## Explicit exclusions (do not build in beta Wave 1)

Wishlist, referrals, saved search, staff RBAC, advanced KYC UI, real escrow release automation, ticket issuance, payment-provider changes, mock data to fake completeness, broad schema changes, migration `0056` production apply.
