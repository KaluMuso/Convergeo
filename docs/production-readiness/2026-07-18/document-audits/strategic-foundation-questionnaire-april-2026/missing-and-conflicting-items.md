# Missing & Conflicting Items — Strategic Foundation Questionnaire (April 2026)

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY · Source: `source-document.md` · Matrix: `reconciliation-matrix.md`

This document is a **requirements/strategy** artifact, so "missing production records" is mostly *not applicable* — the questionnaire does not assert operational records that should exist. The dominant findings are **configuration/workflow gaps**, **feature gaps**, and **document-vs-reality conflicts**. Items are grouped per the required taxonomy. All evidence is redacted to counts/existence only.

---

## a. Missing production records

The questionnaire is a planning artifact and names **no specific records** (no named vendors, orders, tickets, payments). Therefore there is **no case where a document-named record is absent from the database**. The related, non-record observation is that whole operational tables are **empty** where the document's *vision* implies activity:

| Observation | Table(s) | Live count (foundation, same-day) | Status | Why it matters |
| --- | --- | --- | --- | --- |
| No money operations | `payments`, `ledger_transactions`, `payouts`, `refunds`, `webhook_events`, `reconciliation_reports` | 0 each | PARTIAL | Escrow/settlement (RT#5/#9, Q21/Q22) cannot be proven |
| No issued tickets | `tickets`, `order_item_tickets` | 0 | PARTIAL | Events vertical (Applause#5, Q49/Q50) unexercised |
| No real vendors | `vendors` (real) | 3 **demo** only | PARTIAL | Cold-start (RT#15) unmitigated |
| No KYC / reviews / disputes / returns | `kyc_records`, `reviews`, `disputes`, `returns` | 0 each | PARTIAL | Trust/onboarding (RT#3/#5, Q22/Q32/Q48) unexercised |
| No invoices | `invoices`, `invoice_counters` | 0 | PARTIAL | ZRA sequencing (Q24) unexercised |
| No analytics events | `analytics_events`, `funnel_events`, `search_query_log` | 0 (wiring PRs #275–277 merged this session) | PARTIAL | Personalization/metrics (RT#10, Q65) unexercised |

> These are "empty, not missing" — schema exists; **do not** label them MISSING records. They are PARTIAL pending live activity.

---

## b. Missing fields / schema support

| Item | Source ref | Expected object | Live state | Status | Note |
| --- | --- | --- | --- | --- | --- |
| Translation overrides (vernacular launch) | RT#8 / Q27 | `translation_overrides` (mig 0053) | **Absent on live** (migration not applied) | MISSING | Repo has 0053; live DB stopped at 0050 (+odd 0052). Blocks localized content overrides |
| Service bookable flag | Q51 | `services.bookable` (mig 0055) | **Absent on live** | MISSING | Repo has 0055; not applied. RFQ-only holds without it, but drift is real |
| Service review extensions | Q32 | mig 0054 | **Absent on live** | MISSING | Not applied; review depth for services limited |
| Multi-currency dimension | RT#11 / Q23 | currency column/seam on money tables | Not evidenced (ZMW-ngwee only) | CONFLICT | Doc recommends building the *data-model seam now*; platform is single-currency by design |
| Vendor sales-data share/consent | RT#13 | consented export structure | Not evidenced | MISSING | Needed for MFI financing feature (roadmap) |
| Vendor↔customer messaging | Q40 | messaging table/route | Not confirmed in foundation | NOT_AUDITABLE | Requires scoped check; may be absent |

---

## c. Configuration / workflow gaps

| Item | Source ref | Expected | Live state (this session) | Status | Impact |
| --- | --- | --- | --- | --- | --- |
| **Escrow auto-release workflow** | RT#5 / Q21 / Q22 | n8n `release-job` tick (release on delivery-confirm/48h) | **Absent** (only 2 workflows live) | MISSING | **P0** — paid funds may never release to vendors |
| **Ticket-issuance workflow** | Applause#5 / Q49 / Q50 | n8n `tickets-issue` tick | **Absent** | MISSING | **P0** — paid tickets may never issue |
| Order-jobs auto-confirm | Q21 / Q48 | n8n `order-jobs` | Absent | MISSING | Delivery-confirm automation missing |
| Event release | Q50 | n8n `event-release` | Absent | MISSING | Event escrow timing unautomated |
| DB backup workflow | Ops (implied) | n8n backup → OCI Object Storage | Absent as workflow (only `backup-schedule.md`) | MISSING / NOT_AUDITABLE | RPO unproven (host cron not observable) |
| Marketing/onboarding automation | Q66 | abandoned-cart, review-request, onboarding | Absent (marketing flag `abandoned_cart`=false) | MISSING | RT#10 personalization / Q66 coverage gap |
| Prepaid charge → ledger posting | RT#5 / Q22 | `CHARGE_RECEIVED`/`ESCROW_HOLD` legs on prepaid success | Code path added PR #274 (this session, merged), but **0 ledger rows** — unproven live | PARTIAL | **P0** — money integrity until sandbox-proven |
| `NEXT_PUBLIC_VENDOR_APP_URL` (seller CTA) | Applause#1 / Q35 | set on customer prod | Foundation: CTA disabled ("temporarily unavailable"); env likely unset | PARTIAL | Vendor acquisition surface broken |
| Zamtel collections | RT#1 / Q20 | `zamtel_collections` flag on | flag=false (payout-only pending F9a) | PARTIAL | Mobile-money coverage incomplete |
| VAT flag | Q24 | off at launch (Turnover Tax) | Off (D13) | VERIFIED (intent) / PARTIAL (unexercised) | Correct posture; unexercised |
| COD cap value | Q25 | ≤K500 in `platform_config` | `platform_config`=16 keys; value not read (privacy) + founder confirm F8 open | PARTIAL | Fraud exposure if misconfigured |

---

## d. UI / customer / vendor / admin gaps

| Item | Source ref | Surface | Live state | Status | Note |
| --- | --- | --- | --- | --- | --- |
| Seller/vendor signup CTA | Applause#1 / Q35 | customer web `/sell` | Disabled ("temporarily unavailable") | PARTIAL | Env-gated; see (c) |
| WhatsApp commerce surface | RT#2 / Q68 | customer + WhatsApp | Notification-only; no browse/order/pay in WhatsApp | PARTIAL | Feature not built |
| Offline browsing / USSD ordering | RT#7 / Q46 | customer PWA | PWA present; offline-commerce/USSD not evidenced | PARTIAL | Peri-urban reach |
| Vernacular UI (Bemba/Nyanja) at launch | RT#8 / Q27 | all apps i18n | English-only launch (D27); scaffolding present | CONFLICT | Rec vs decision |
| Homepage merch ("hub of logos") | Q30 / Q58 | customer homepage | `merch_slots`=1 (minimal) | PARTIAL | Data-thin |
| Vendor dashboard analytics | Q38 / Q65 | vendor + admin | UI exists; analytics tables=0 rows | PARTIAL | No data yet |
| Admin users/roles management UI | Q60/RBAC (R6) | admin | `user_roles` service-role only; **no admin CRUD UI** | MISSING | Role grants are manual SQL/dashboard |
| Directory / tourism UI | Q52 / Q53 | customer | Directory in scope; tourism absent | PARTIAL / NOT_AUDITABLE | Login/UI verification pending |
| Visual/voice search, AR try-on | Q69 / Q70 | customer | Absent | MISSING | Phase 3 (correct for MVP) |

---

## e. Conflicting data (document vs live/decision)

| # | Conflict | Document says | Live / ratified reality | Resolution note | Severity |
| --- | --- | --- | --- | --- | --- |
| E1 | Backend stack | Q9-A + Caution#1: **Django + PostgreSQL** (Recommended) | **FastAPI + Supabase** (D18, deliberate) | Later ratified decision supersedes the questionnaire recommendation; both Python+Postgres | Low (documented) |
| E2 | Payment gateway | Realistic MVP + Q19: "Lenco/**DPO**" | **Lenco only** (D11); DPO not integrated | Doc treats DPO as co-option; platform chose Lenco-only with abstraction seam | Low |
| E3 | Launch languages | RT#8 + Q27: launch **EN + Bemba + Nyanja** | **English-only** launch + i18n scaffolding (D27); `translation_overrides` not applied | Genuine gap vs red-team advice; inclusivity risk | Medium |
| E4 | Cross-border data model | RT#11 + Q23: build **multi-currency seam now** | **ZMW-ngwee single currency**, no seam | Deviation may force a later migration; decide consciously | Medium |
| E5 | Delivery integration | Applause#4 + Realistic v1.0: **Yango API** integration | **Manual admin dispatch, no courier API v1** (D16) | Applause/realistic overstate an integration that doesn't exist | Medium |
| E6 | Demo catalogue exposure | Applause#5/Q30/Q50 imply a real, browsable marketplace | **134 demo listings + demo images served by public catalog** (`total=134`); D25 intended demo **excluded from public search** | Live contradicts D25 intent; misleads real-money positioning | Medium (P1) |
| E7 | Questionnaire status | Artifact is a 75-question decision form | **Blank** here; answers live in `00-decisions.md` | Approval not captured in this artifact; risk of "undecided" misread | Low (process) |
| E8 | Background tasks | Q18: **Celery + n8n** (Recommended) | n8n + outbox; **no Celery/Redis queue** evidenced | Confirm whether Celery is intended or intentionally dropped | Low |

> Per the contract, conflicts are reported with both sides and **not silently resolved**. Where a locked decision (D-number) exists, it is the higher-authority *intent*, but live behavior (E6) can still contradict that intent — that is itself the finding.

---

## f. Access / evidence limitations (NOT_AUDITABLE this session)

| # | Item needed | Why blocked | What it would confirm |
| --- | --- | --- | --- |
| L1 | **Supabase read-only SQL** (`mcp.supabase.com`) | Org egress policy denied CONNECT (403) this session; server also unauthenticated | Fresh COD cap value, commission bps, RLS policy list, exact row counts (currently cited from same-day foundation) |
| L2 | **Direct HTTP to `*.vergeo5.com`** | Org egress policy denied CONNECT (403) | Fresh health/catalog/`/sell` CTA re-probe (cited from same-day foundation) |
| L3 | Legal / regulatory sign-off (RT#12, Q60–Q62) | No artifact; F4 counsel review is a pending founder gate | Whether DPA/NPS-Act/ZICTA compliance is actually met — **must not be inferred** |
| L4 | Payment settlement proof (RT#5/#9, Q19–Q22) | 0 payment rows; no sandbox run performed (read-only, no writes) | Whether charge→hold→release→payout actually posts ledger legs |
| L5 | Vendor/admin login-gated UI (Q35–Q42, Q53, Q64) | Auth-gated; not exercised (no credentials, read-only) | Onboarding speed, dashboard analytics, directory prominence, support channel |
| L6 | Messaging module (Q40) | Not present in foundation inventory | Whether in-platform vendor↔customer messaging exists |
| L7 | API container git SHA (deploy parity) | GHCR unauth; no host SSH | Whether deployed API matches repo tip (relevant to any code-only PARTIAL) |
| L8 | Business facts (Q7/Q8 capital, Q56/Q57 targets, Q60 registration, Q63 team, Q71–Q75) | No platform surface | These are business decisions; belong in `00-decisions.md`, not the platform |

---

## Priority summary

- **P0 (money / trust / security):** E-scrow auto-release + ticket-issuance workflows missing (c); prepaid→ledger posting unproven (c); no live payment/settlement proof (a, L4); regulatory compliance unverifiable and gated (f/L3).
- **P1 (launch quality):** Demo catalogue publicly served vs D25 (e/E6); seller CTA disabled (c/d); launch-language gap (e/E3); migration drift 0051/0053–0055 (b).
- **P2 (roadmap / scope):** Multi-currency seam (e/E4); courier API (e/E5); WhatsApp commerce, offline/USSD, financing, super-app, AR (d) — mostly correct deferrals but track explicitly.
