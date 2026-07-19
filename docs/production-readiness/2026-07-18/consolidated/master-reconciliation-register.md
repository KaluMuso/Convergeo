# Master Reconciliation Register — Vergeo5 / Convergeo

**Consolidation date:** 2026-07-18 (refresh after PRs #274, #289–#294)  
**Role:** Audit Consolidation Lead  
**Mode:** Documentation only — no production changes, no application code edits  
**Git tip reconciled:** `d5c2134` (merge PR #293) on `master`  
**Sources:** Six document audits under `../document-audits/*` · foundation (`../foundation/*`) · panel/implementation reports (`../implementation/*`, `../integration/*`)

**Verdict:** Platform remains a **live demo marketplace** with a much stronger **code-complete** money/KYC shell after #274/#288/#293/#294 and panel honesty PRs #289–#291 — **not** real-money production-ready while staging/live evidence for payments, migration rollout, n8n, RLS, monitoring, backup/restore, or rollback remains incomplete.

---

## How to read this register

| Column              | Meaning                                                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **MR-ID**           | Deduplicated master finding ID (stable for coding sessions)                                                         |
| **Priority**        | P0 release blocker · P1 launch quality · P2 hygiene/roadmap · DOC doc-only                                          |
| **Evidence status** | VERIFIED / PARTIAL / MISSING / CONFLICT / NOT_AUDITABLE (per `../foundation/document-audit-contract.md`)            |
| **Maturity**        | `CODE_COMPLETE` · `STAGING_VERIFIED` · `PRODUCTION_VERIFIED` · `N/A` (docs/ops/decisions)                           |
| **Workstream**      | data · schema · backend/API · customer · vendor · admin · workflow · security/RLS · test/observability · legal/docs |
| **Source refs**     | Paths into document audits + foundation risk IDs + merged PR numbers                                                |

**Maturity rules**

- Repository implementation alone may justify **CODE_COMPLETE** + evidence **PARTIAL**.
- **STAGING_VERIFIED** requires sandbox/staging probes with VERIFIED evidence.
- **PRODUCTION_VERIFIED** requires live production probes (never inferred from git).
- Do **not** mark a money/trust P0 closed until **STAGING_VERIFIED** (minimum) and the matching release gate PASSes.

**Rules applied**

- Findings that appear in multiple audits are merged into one MR-ID; all source IDs are preserved.
- Stack “conflicts” that are intentional supersessions (`docs/plan/00-decisions.md` D18–D24) are **DOC**, not engineering defects — see `source-conflicts-and-decisions.md`.
- Do **not** recommend direct database edits without a reviewed migration or controlled import plan.
- Do **not** seed production to “close” empty operational tables.

### Source document slugs

| Slug          | Path                                                                |
| ------------- | ------------------------------------------------------------------- |
| `events`      | `../document-audits/convergeo-events-strategy/`                     |
| `product`     | `../document-audits/convergeo-product-strategy-april-2026/`         |
| `blueprint`   | `../document-audits/blueprint-zambia-vergeo-super-app/`             |
| `master`      | `../document-audits/strategic-master-plan-v1/`                      |
| `sfq`         | `../document-audits/strategic-foundation-questionnaire-april-2026/` |
| `roadmap`     | `../document-audits/convergeo-60-day-development-roadmap/`          |
| `foundation`  | `../foundation/`                                                    |
| `impl`        | `../implementation/`                                                |
| `integration` | `../integration/panel-pr-integration-review.md`                     |

### Merged PRs in scope (master ancestry confirmed)

| PR       | Theme                                                            | Maturity after merge                                                                            |
| -------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **#274** | Prepaid collection → `CHARGE_RECEIVED` / escrow hold             | **CODE_COMPLETE**; **not** STAGING_VERIFIED                                                     |
| **#288** | Product/service release commission capture                       | **CODE_COMPLETE**; staging unproven                                                             |
| **#289** | Customer panel honesty (categories/compare/calendar/payment UI)  | **CODE_COMPLETE**; production deploy of panel SHA **NOT_AUDITABLE** vs foundation SHA `8cc1fa0` |
| **#290** | Admin analytics/dispatch/escrow honesty                          | **CODE_COMPLETE**; Access deep audit still NOT_AUDITABLE                                        |
| **#291** | Vendor KYC/catalogue/analytics honesty                           | **CODE_COMPLETE**; customer storefront badge residual                                           |
| **#293** | KYC integrity (eligibility + admin lifecycle + migration `0056`) | **CODE_COMPLETE**; **migration rollout-dependent**                                              |
| **#294** | Release accounting (capture-before-release; event/COD paths)     | **CODE_COMPLETE**; **not** STAGING_VERIFIED                                                     |

---

## 0. Conflict ledger (do not hide)

Every CONFLICT lists **document claim** vs **live / locked value**. Resolution authority for stack claims: `docs/plan/00-decisions.md` plus live evidence. Full decision queue: `source-conflicts-and-decisions.md`.

| Conflict       | Document claim(s)                     | Live / locked value                                                          | Source refs                                                            | Resolution stance                                                |
| -------------- | ------------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------- |
| C-STACK-BE     | Django + DRF                          | FastAPI + Supabase (D18)                                                     | blueprint F003; master Q9; sfq E1; roadmap F003                        | DOC — superseded                                                 |
| C-STACK-SEARCH | Meilisearch (+pgvector)               | Postgres FTS + pg_trgm + pgvector RRF (D22)                                  | events F025; product F018; master Q15; roadmap F006                    | DOC stack; P1 search quality                                     |
| C-STACK-HOST   | Railway / Render                      | OCI/Hetzner + Caddy + Supabase + Cloudflare (D21)                            | master Q11; roadmap F004                                               | DOC — superseded                                                 |
| C-STACK-ASYNC  | Celery + Redis / Upstash              | n8n + outbox (D18/D21)                                                       | blueprint F006; master Q17–18; sfq E8; roadmap F007–008                | DOC — superseded                                                 |
| C-STACK-NOTIF  | Supabase Realtime notifications       | WhatsApp → SMS → email outbox (D15)                                          | blueprint F005; master Q14                                             | DOC — superseded                                                 |
| C-PAY-PROVIDER | DPO Pay / DPO+Lenco                   | **Lenco only** (D11)                                                         | roadmap F005; master Q19; sfq E2                                       | DOC after founder confirm                                        |
| C-PAY-ZAMTEL   | Zamtel collections at launch          | `zamtel_collections=false`; payout-only pending F9a                          | roadmap F026; blueprint F024; sfq SFQ-12                               | **Founder decision** (P0)                                        |
| C-LOGISTICS    | Yango API + own fleet                 | Manual Lusaka dispatch + nationwide pickup (D16)                             | blueprint F036; master Q43/47; sfq E5                                  | DOC — do not build courier API for v1                            |
| C-EVENT-TYPE   | Event type includes `multi_day`       | CHECK `standard\|recurring\|free_rsvp\|private`                              | events F006                                                            | **Founder/product decision**                                     |
| C-CONDITION    | Used / open-box / for-parts           | CHECK `new\|refurbished` only                                                | product F009                                                           | Schema gap before Class D                                        |
| C-ESCROW-HOLD  | Used goods 72h escrow                 | Flat `release_after_delivered_hours=48`                                      | product F010                                                           | Config gap if used goods enabled                                 |
| C-ADMIN-ROLES  | superadmin + moderator                | `user_roles.role` CHECK `customer\|vendor\|admin`                            | roadmap F033; master BL-03; sfq SFQ-05                                 | **Founder decision** (P0)                                        |
| C-LANGUAGES    | EN+Bemba+Nyanja at launch             | English-only launch (D27); `0053` unapplied                                  | sfq E3; master Q27                                                     | Decision holds; vernacular = P1                                  |
| C-DEMO-PUBLIC  | Real marketplace / D25 demo exclusion | Public catalog `total=134` all `demo/` images                                | product F024; blueprint F017–018; sfq E6; foundation R5                | Genuine gap (P1)                                                 |
| C-TRACTION     | 840 vendors / K184k GMV wireframes    | 3 demo vendors; 0 money rows                                                 | blueprint F017–018, F038–039                                           | Wireframe fiction — never seed                                   |
| C-MIG-DRIFT    | Live schema == git tip                | Applied ≤0050 + odd `0052`; missing `0051`/`0053`–`0056`                     | foundation §4; master BL-02; sfq SFQ-06; roadmap F014; impl KYC `0056` | **P0** genuine (now includes `0056`)                             |
| C-RETURNS      | “No returns MVP” (master plan)        | Two-lane returns (D17)                                                       | master Q48                                                             | Production-ahead — doc stale                                     |
| C-BRAND        | Convergeo / Vergio / Virgeo           | Live **Vergeo5**                                                             | blueprint F001; roadmap F001                                           | Naming hygiene                                                   |
| C-CURRENCY     | Multi-currency seam now               | ZMW ngwee only                                                               | sfq E4; product F008                                                   | ADR required (P2)                                                |
| C-KYC-TIER     | Tier badges imply KYC trail           | Live: `kyc_tier` without records; **code** now freezes orphaned tiers (#293) | blueprint F014–015; events F036; impl `kyc-integrity-report.md`        | **CODE_COMPLETE**; staging/prod repair + `0056` apply still open |

---

## 1. Data corrections (master data / operational emptiness)

> Controlled import or seed-replacement plans only. **No ad-hoc SQL UPDATEs** on production money/trust tables.

| MR-ID  | Pri | Evidence                                       | Maturity                                       | Finding                            | Live / code evidence                                                                                        | Source refs                                                                            | Recommended action                                                                     | Acceptance                                                                                      |
| ------ | --- | ---------------------------------------------- | ---------------------------------------------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| MR-D01 | P1  | VERIFIED                                       | N/A (ops)                                      | Demo catalogue as public inventory | 3 vendors; 134 listings; 134 `demo/%` images                                                                | foundation R5; product F024; blueprint F017; sfq E6; roadmap F050                      | Label/exclude demo **or** replace via reviewed import; keep `public_launch=false`      | Public catalog cannot be mistaken for real marketplace                                          |
| MR-D02 | P0  | VERIFIED (live orphan) / PARTIAL (code freeze) | **CODE_COMPLETE** (#293); not STAGING_VERIFIED | KYC tier without audit trail       | Live orphans remain until ops repair; API eligibility ignores bare tier; migration `0056` in repo unapplied | blueprint BL-P0-05; events F036; roadmap F016; impl `kyc-integrity-report.md`; PR #293 | Apply `0056` staging→prod; run orphaned-tier report; **manual** controlled repair only | Every privileged capability requires approved `kyc_records`; orphans reported not auto-upgraded |
| MR-D03 | P1  | VERIFIED                                       | N/A                                            | Zero money / ticket / order rows   | payments/ledger/orders/tickets/payouts = 0                                                                  | foundation §5; all six audits                                                          | Sandbox drills only — do not fabricate prod rows                                       | Sandbox fixtures VERIFIED; prod empty until go-live                                             |
| MR-D04 | P1  | VERIFIED                                       | N/A                                            | Events inventory empty             | events=0, tickets=0                                                                                         | events F047; product F025; blueprint F032                                              | Organiser onboarding after MR-W01/W02                                                  | ≥1 published Phase-1 event under beta                                                           |
| MR-D05 | P1  | VERIFIED                                       | N/A                                            | Services RFQ empty                 | 1 demo service; jobs=0                                                                                      | blueprint F030–031                                                                     | Onboard real providers after notifications proven                                      | RFQ creates quotes; outbox drained                                                              |
| MR-D06 | P2  | PARTIAL                                        | N/A                                            | Tiered/wholesale pricing unused    | `price_tiers` schema OK; unused                                                                             | product F033                                                                           | After B2B path ready                                                                   | One tiered listing checkout-safe                                                                |

---

## 2. Schema changes (additive migrations only)

| MR-ID  | Pri   | Evidence | Maturity                         | Finding                                | Evidence                                                              | Source refs                                                                 | Action                                                                | Acceptance                                                                      |
| ------ | ----- | -------- | -------------------------------- | -------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| MR-S01 | P0    | CONFLICT | N/A (ops)                        | Live DB ≠ git tip                      | Missing applied `0051`, `0053`–`0056`; `0052` version-key skew        | foundation §4; master BL-02; sfq SFQ-06; roadmap BL-08; PR #293 adds `0056` | DBA-reviewed reconcile; backup first (MR-O04); apply in order         | `schema_migrations` matches agreed target; release ledger records SHA↔migration |
| MR-S02 | P0→P1 | MISSING  | CODE path in repo; live MISSING  | Role hook migration absent             | `0051` unapplied; `custom_access_token*` absent live                  | foundation R6/R8; master BL-03; sfq SFQ-05                                  | Apply `0051` + enable Auth hook **or** written manual-grant exception | JWT carries roles **or** signed exception; isolation tests green                |
| MR-S03 | P1    | MISSING  | repo only                        | `translation_overrides` (0053)         | Absent live                                                           | sfq SFQ-09                                                                  | Apply when vernacular starts                                          | Override path tested                                                            |
| MR-S04 | P1    | MISSING  | repo only                        | Service reviews / bookable (0054/0055) | Unapplied                                                             | master; sfq                                                                 | Apply with services GTM                                               | OpenAPI matches                                                                 |
| MR-S05 | P0*   | MISSING  | N/A                              | `product_class` A–E absent             | No column                                                             | product RB-PS-001                                                           | Gate Phase-1 as Class A **or** additive enum                          | Existing listings readable                                                      |
| MR-S06 | P0*   | CONFLICT | N/A                              | Condition model narrow                 | CHECK `new\|refurbished`                                              | product RB-PS-002                                                           | Expand **before** Class D                                             | Facets + RLS tests                                                              |
| MR-S07 | P1    | MISSING  | N/A                              | Variants / sale_unit / pricing_mode    | Absent                                                                | product RB-PS-008/009                                                       | After Class A proven                                                  | Normalized unit price where needed                                              |
| MR-S08 | P1    | CONFLICT | N/A                              | Event `multi_day` type                 | Brief 5 types vs live 4                                               | events BL-007                                                               | Decision: add enum **or** accept `standard`+`ends_at`                 | `00-decisions` updated                                                          |
| MR-S09 | P1    | MISSING  | N/A                              | Co-organiser / door roles              | No `event_organiser_roles`                                            | events BL-008                                                               | Additive event-scoped roles                                           | Door can scan only                                                              |
| MR-S10 | P2    | MISSING  | N/A                              | Venue capacity / fee_mode / promo      | Absent                                                                | events BL-010/011/015                                                       | Phase gates                                                           | Oversell rejected                                                               |
| MR-S11 | P0    | PARTIAL  | **CODE_COMPLETE** (file in repo) | KYC integrity migration `0056`         | In git; **not** applied live (foundation tip stopped at ≤0055 + skew) | impl `kyc-integrity-report.md`; PR #293                                     | Staging apply → orphan report → prod apply                            | Trigger/view/columns present; legacy `pending`→`submitted`                      |

\*Scope-gated: hard P0 only if launch claims Class D/E or used goods.

---

## 3. Backend / API work

| MR-ID   | Pri | Evidence                | Maturity                                                | Finding                                               | Evidence                                                                                                              | Source refs                                                                                                                                 | Action                                                           | Acceptance                                            |
| ------- | --- | ----------------------- | ------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------- |
| MR-B01  | P0  | PARTIAL                 | **CODE_COMPLETE** (#274); **not** STAGING_VERIFIED      | Prepaid collection → escrow ledger                    | `settle_prepaid_collection` → `CHARGE_RECEIVED` hooked from `payments/state.py`; live `payments=0`/`ledger=0`         | foundation R2; master BL-01; sfq SFQ-01; roadmap BL-02; blueprint BL-P0-03; product RB-PS-003; events BL-002; impl payment reports; PR #274 | Sandbox MoMo+card → SQL ledger proof; webhook replay             | Balanced legs; idempotent; **STAGING_VERIFIED**       |
| MR-B01b | P0  | PARTIAL                 | **CODE_COMPLETE** (#288/#294); **not** STAGING_VERIFIED | Release accounting (commission before vendor release) | `compute_release_amounts` / `capture_order_commission` on product/service/event/COD; snapshot-only rates; fail-closed | impl `payment-release-accounting-report.md`; PR #288, #294                                                                                  | Sandbox charge→capture→release; escrow→0; double-tick idempotent | A1–A8 invariants STAGING_VERIFIED                     |
| MR-B02  | P0* | PARTIAL                 | N/A                                                     | Escrow hold vs used goods                             | Flat 48h                                                                                                              | product F010                                                                                                                                | If used goods: 72h path                                          | Release tick honours window                           |
| MR-B03  | P0  | NOT_AUDITABLE / PARTIAL | N/A                                                     | Refund/cancel matrix unproven                         | refunds/disputes=0                                                                                                    | events BL-005                                                                                                                               | Sandbox cancel→refund+notify                                     | Policy matches code                                   |
| MR-B04  | P0  | MISSING                 | N/A                                                     | Organiser Tier-1 GMV fraud cap                        | Cap ~K20k not evidenced                                                                                               | events BL-004                                                                                                                               | Implement/verify cap                                             | Over-cap rejected + audit                             |
| MR-B05  | P1  | PARTIAL                 | N/A                                                     | Stock reservation unproven                            | TTL=15m; reservations=0                                                                                               | product F014                                                                                                                                | Staging reserve→expire→pay                                       | Atomic unpaid release                                 |
| MR-B06  | P1  | PARTIAL                 | N/A                                                     | Listing modes incomplete                              | OpenAPI 3/5 modes                                                                                                     | product RB-PS-011                                                                                                                           | Add unique/MTO                                                   | Five flows tested                                     |
| MR-B07  | P1  | PARTIAL                 | N/A                                                     | Search degraded                                       | `/search` `degraded=true` observed                                                                                    | blueprint BL-P1-07                                                                                                                          | Diagnose embeddings/FTS                                          | `degraded=false` common queries                       |
| MR-B08  | P1  | PARTIAL                 | N/A                                                     | Category×tier policy gates                            | Makeup/used skip rules                                                                                                | product RB-PS-015                                                                                                                           | Enforce 422                                                      | Prohibited rejected                                   |
| MR-B09  | P2  | PARTIAL                 | N/A                                                     | OTP rate limit runtime                                | Limiter code present                                                                                                  | roadmap BL-17                                                                                                                               | Integration test                                                 | Rapid OTP limited                                     |
| MR-B10  | —   | NOT_AUDITABLE           | N/A                                                     | API container git SHA unknown                         | OpenAPI `0.1.0`; GHCR unauthorized                                                                                    | foundation R8                                                                                                                               | Read `API_IMAGE_TAG` / digest                                    | SHA in release ledger                                 |
| MR-B11  | P0  | PARTIAL                 | **CODE_COMPLETE** (#293); rollout-dependent             | KYC eligibility + admin lifecycle API                 | `eligibility.py`; guarded admin routes; orphan report                                                                 | impl `kyc-integrity-report.md`; PR #293                                                                                                     | Deploy API with `0056`; staging approve/suspend drills           | Orphaned tier cannot unlock wholesale/events/verified |

---

## 4. Customer work

| MR-ID  | Pri | Evidence                       | Maturity                                               | Finding                              | Evidence                                                                                                                               | Source refs                                                                         | Action                                            | Acceptance                                         |
| ------ | --- | ------------------------------ | ------------------------------------------------------ | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------- | -------------------------------------------------- |
| MR-C01 | P1  | PARTIAL                        | CODE fail-closed; env N/A                              | Seller CTA unavailable               | `/en/sell` disabled; no localhost leak                                                                                                 | foundation R1; master BL-06; sfq SFQ-07; roadmap BL-06; blueprint BL-P1-05; CUST-01 | Set `NEXT_PUBLIC_VENDOR_APP_URL`; redeploy        | CTA → vendor prod; not “unavailable”               |
| MR-C02 | P1  | PARTIAL → CODE_COMPLETE routes | **CODE_COMPLETE** (#289); prod deploy unproven         | Categories/compare entry             | Routes + tests on master; foundation still recorded 404 at earlier SHA                                                                 | product RB-PS-012; impl `customer-change-report.md`; PR #289                        | Deploy customer SHA containing #289; re-probe     | `/en/categories` + `/en/compare` 200               |
| MR-C03 | P1  | PARTIAL                        | N/A                                                    | Events discovery UX incomplete       | Missing Where lens; Tonight+Weekend; selling-fast                                                                                      | events BL-009                                                                       | Phase-1 slice after supply                        | Browse matches Phase-1                             |
| MR-C04 | P1  | PARTIAL                        | CODE_COMPLETE build artifact; prod SW unproven         | PWA service worker                   | Manifest 200; live SW 404 at foundation; #289 build emits `sw.js`                                                                      | blueprint BL-P1-01; PR #289                                                         | Deploy + probe SW                                 | SW 200; installability                             |
| MR-C05 | P1  | PARTIAL                        | **CODE_COMPLETE** (#289 CUST-07)                       | Launch copy vs locked decisions      | Hero logistics wording tightened                                                                                                       | blueprint BL-P1-06; PR #289                                                         | Re-probe live copy after deploy                   | No Yango/own-fleet/Django claims                   |
| MR-C06 | P2  | PARTIAL                        | **CODE_COMPLETE** (#289 CUST-10)                       | Calendar route                       | Permanent redirect → events                                                                                                            | events F027; PR #289                                                                | Deploy + probe                                    | No dead 404                                        |
| MR-C07 | P2  | MISSING                        | N/A                                                    | Wishlist / recently viewed / reorder | Affordance-only                                                                                                                        | foundation R6                                                                       | Scope fence OUT                                   | Explicit OUT or shipped                            |
| MR-C08 | P0  | PARTIAL                        | **CODE_COMPLETE** UI (#289); ledger still staging-open | Checkout false-success hardening     | Card requires `order_confirmed`; MoMo confirming≠paid; residual: status contract lacks ledger field; checkout steps localhost residual | foundation R2; CUST-08; G4; PR #289; integration review                             | Staging E2E + harden remaining API base fallbacks | No paid UI without confirmed payment+ledger policy |
| MR-C09 | P1  | PARTIAL                        | N/A                                                    | Escrow trust UX                      | 0 orders                                                                                                                               | CLAUDE.md; CUST-09                                                                  | Wire to real statuses after MR-B01/W01            | Never invent held/released                         |
| MR-C10 | P1  | PARTIAL                        | CODE residual                                          | Customer storefront KYC badges       | `/v/[slug]` may still badge from bare `kyc_tier`                                                                                       | integration §4.4; PR #291 residual                                                  | Align customer badge to auditable eligibility     | No verified badge without approved record          |

---

## 5. Vendor work

| MR-ID  | Pri | Evidence      | Maturity                                               | Finding                       | Evidence                                                             | Source refs                               | Action                                  | Acceptance                                          |
| ------ | --- | ------------- | ------------------------------------------------------ | ----------------------------- | -------------------------------------------------------------------- | ----------------------------------------- | --------------------------------------- | --------------------------------------------------- |
| MR-V01 | P0  | PARTIAL       | **CODE_COMPLETE** UI (#291) + API (#293); staging open | KYC honesty                   | Vendor UI requires auditable record; API eligibility freezes orphans | blueprint BL-P0-05; VEND-01; PR #291/#293 | Staging KYC E2E + orphan repair         | Badge/capabilities only when approved record exists |
| MR-V02 | P1  | NOT_AUDITABLE | N/A                                                    | Listing UX / attach <30s      | Login-gated                                                          | product F038; blueprint F021–022          | Test vendor JWT audit                   | Five flows timed                                    |
| MR-V03 | P1  | PARTIAL       | N/A                                                    | Offline scanner cache missing | Offline cannot verify                                                | events BL-006                             | Cache + scan-sync                       | Offline then sync; first-scan-wins                  |
| MR-V04 | P1  | PARTIAL       | CODE_COMPLETE UI honesty (#291)                        | KYC lifecycle unexercised     | `kyc_records=0` live                                                 | roadmap BL-13; VEND-02                    | Sandbox submit→review→approve           | State machine cannot skip                           |
| MR-V05 | P1  | MISSING       | N/A                                                    | Evidence photos for non-new   | No IMEI/VIN/evidence_kind                                            | product RB-PS-007                         | Before Class D                          | Non-new rejects missing evidence                    |
| MR-V06 | P2  | MISSING       | Documented OUT (#291)                                  | Vendor staff RBAC             | Single owner                                                         | foundation R6; VEND-10                    | Post-v1 unless ADR                      | Documented OUT                                      |
| MR-V07 | P2  | MISSING       | N/A                                                    | Co-organiser invite UX        | Schema absent                                                        | events BL-008                             | After MR-S09                            | Door/Manager invite                                 |
| MR-V08 | P1  | PARTIAL       | **CODE_COMPLETE** empty honesty (#291)                 | Analytics / fee honesty       | Zero empty states; no fabricated GMV                                 | VEND-08; events F018                      | Ledger-backed stats after staging money | No invented organiser GMV                           |

---

## 6. Admin work

| MR-ID  | Pri           | Evidence      | Maturity                                    | Finding                        | Evidence                                                                         | Source refs                               | Action                                        | Acceptance                                      |
| ------ | ------------- | ------------- | ------------------------------------------- | ------------------------------ | -------------------------------------------------------------------------------- | ----------------------------------------- | --------------------------------------------- | ----------------------------------------------- |
| MR-A01 | P0→P1         | MISSING       | N/A                                         | Admin role management UI       | No CRUD UI                                                                       | foundation R6; master BL-03; roadmap F034 | Grant/revoke UI + audit **or** manual ops doc | Audit trail; least privilege                    |
| MR-A02 | P0            | CONFLICT      | N/A                                         | Two-tier admin unsupported     | Single `admin` CHECK                                                             | roadmap BL-05; ADM-01                     | **Founder decision**                          | Decision recorded; if adopt, authz-matrix green |
| MR-A03 | P0            | PARTIAL       | **CODE_COMPLETE** (#293); rollout-dependent | KYC review integrity           | Guarded start-review/approve/reject/suspend/revoke; needs `0056` + staging drill | ADM-03; impl KYC report; PR #293          | Staging review drill; orphan report           | No privilege without approved record            |
| MR-A04 | P1            | PARTIAL       | **CODE_COMPLETE** empty honesty (#290)      | Moderation / analytics honesty | Empty states; recon unknown without report                                       | product RB-PS-014; ADM-04/06; PR #290     | Staging moderation + traffic                  | Queue/tiles match reality                       |
| MR-A05 | P1            | PARTIAL       | **CODE_COMPLETE** (#290 ADM-07)             | Dispatch UX vs D16             | Manual book+paste; no Yango CTA framing                                          | D16; ADM-07; PR #290                      | Deploy + Access smoke                         | Matches manual Lusaka model                     |
| MR-A06 | P1            | PARTIAL       | **CODE_COMPLETE** honesty (#290 ADM-08)     | Escrow ops visibility          | Read-only ledger summary; no invented amounts                                    | ADM-08; MR-B01/W01                        | After staging money                           | Balances match ledger                           |
| MR-A07 | NOT_AUDITABLE | NOT_AUDITABLE | N/A                                         | Admin UI deep audit            | Cloudflare Access                                                                | foundation; blueprint                     | Access-approved auditor session               | Empty-state pack                                |

---

## 7. Workflow / integration work

| MR-ID  | Pri | Evidence                | Maturity     | Finding                                 | Evidence                           | Source refs                                                                                                  | Action                                                        | Acceptance                                 |
| ------ | --- | ----------------------- | ------------ | --------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------- | ------------------------------------------ |
| MR-W01 | P0  | VERIFIED MISSING        | MISSING live | Escrow auto-release n8n absent          | Only dispatch + payment recon live | foundation R3; events BL-001; product RB-PS-003; blueprint BL-P0-01; master BL-04; sfq SFQ-02; roadmap BL-03 | Import/activate `release-job` (+ order-jobs); sandbox release | Active; successful tick; no double-release |
| MR-W02 | P0  | VERIFIED MISSING        | MISSING live | Ticket issue / event-release n8n absent | Inactive; tickets=0                | foundation R3; events BL-001; product RB-PS-005; blueprint BL-P0-02; sfq SFQ-03                              | Activate issue + event-release ticks                          | Exactly-once ticket; dynamic QR works      |
| MR-W03 | P1  | MISSING                 | MISSING live | Lifecycle automations                   | abandoned-cart etc. off            | roadmap BL-14                                                                                                | Import + prove                                                | Each fires once in test                    |
| MR-W04 | P1  | MISSING / NOT_AUDITABLE | N/A          | Backup workflow                         | Only `backup-schedule.md`          | foundation R3; master BL-08; sfq SFQ-11; roadmap BL-09                                                       | Deploy backup **or** prove host cron; restore drill           | Dated artifact + restore proof             |
| MR-W05 | P1  | PARTIAL                 | LIVE partial | Payment reconciliation cron             | One of two live workflows          | foundation                                                                                                   | Prove failure alerting                                        | Mismatch alerted                           |
| MR-W06 | P2  | MISSING                 | MISSING live | Embeddings / sweeper / digests          | Repo JSON; not live                | foundation R3                                                                                                | Activate as needed                                            | Tick success logged                        |

---

## 8. Security / RLS work

| MR-ID  | Pri | Evidence | Maturity | Finding                                          | Evidence                                           | Source refs                                | Action                                   | Acceptance                            |
| ------ | --- | -------- | -------- | ------------------------------------------------ | -------------------------------------------------- | ------------------------------------------ | ---------------------------------------- | ------------------------------------- |
| MR-R01 | P0  | PARTIAL  | N/A      | FORCE RLS false on ticket allocation/price tiers | `ticket_type_instances`, `ticket_type_price_tiers` | events F051/BL-003; master BL-10           | Enable FORCE or signed exception         | Advisor + force true **or** exception |
| MR-R02 | P2  | PARTIAL  | N/A      | FORCE RLS false on `product_relations`           | Same pattern                                       | master BL-10                               | Same as MR-R01                           | Documented decision                   |
| MR-R03 | P2  | PARTIAL  | N/A      | Leaked-password protection disabled              | Advisor WARN                                       | master BL-10                               | Enable in Auth                           | Cleared or risk-accepted              |
| MR-R04 | P0  | PARTIAL  | N/A      | Authz/RBAC provisioning gap                      | `0051` absent; manual grants                       | foundation R6; sfq SFQ-05                  | Close MR-S02 + MR-A01/A02                | Isolation tests green                 |
| MR-R05 | P1  | PARTIAL  | N/A      | CI secret-scan non-blocking                      | `continue-on-error: true`                          | foundation R7; roadmap BL-10; master BL-09 | Make blocking; confirm branch protection | Merges blocked on secret hit          |

---

## 9. Test / observability work

| MR-ID  | Pri | Evidence                | Maturity                                         | Finding                          | Evidence                                 | Source refs                                                                | Action                                | Acceptance                                        |
| ------ | --- | ----------------------- | ------------------------------------------------ | -------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------- |
| MR-O01 | P1  | VERIFIED MISSING        | MISSING                                          | No Vergeo5 Sentry projects       | Org has unrelated projects only          | foundation R4; master BL-05; sfq SFQ-10; blueprint BL-P1-08; roadmap BL-07 | Create projects + wire DSNs           | Test error visible per app                        |
| MR-O02 | P1  | NOT_AUDITABLE           | N/A                                              | Uptime monitors                  | Not probed                               | foundation R4                                                              | Configure health monitors             | Monitors green                                    |
| MR-O03 | P0  | PARTIAL                 | Unit/integration **CODE_COMPLETE**; staging open | Money-path staging proof         | #274/#294 tests in repo; 0 live payments | MR-B01/B01b; roadmap BL-16                                                 | Sandbox MoMo+card + failure scenarios | Critical suite STAGING_VERIFIED; no false success |
| MR-O04 | P1  | MISSING / NOT_AUDITABLE | N/A                                              | Backup + restore proof           | No n8n backup                            | MR-W04                                                                     | Restore drill                         | RPO documented                                    |
| MR-O05 | P2  | PARTIAL                 | N/A                                              | Staging pipeline stub            | `deploy-staging.yml` stub                | roadmap BL-11                                                              | Real staging parity                   | UAT journeys pass                                 |
| MR-O06 | P2  | PARTIAL                 | N/A                                              | Perf/SEO/A11y not freshly probed | Egress-limited                           | roadmap BL-21                                                              | Lighthouse                            | Budgets met or waiver                             |

---

## 10. Legal / docs / SoT hygiene

| MR-ID  | Pri | Evidence      | Maturity | Finding                                        | Source refs    | Action                                      | Acceptance                         |
| ------ | --- | ------------- | -------- | ---------------------------------------------- | -------------- | ------------------------------------------- | ---------------------------------- |
| MR-L01 | P0  | NOT_AUDITABLE | N/A      | Zambian counsel / DPA / NPS Act escrow posture | sfq SFQ-04     | Counsel review before real money            | Written sign-off — never inferred  |
| MR-L02 | DOC | CONFLICT      | N/A      | Strategy docs claim obsolete stack             | All six audits | Banner “SUPERSEDED — see `00-decisions.md`” | Engineers cite locked decisions    |
| MR-L03 | DOC | CONFLICT      | N/A      | Payment provider language (DPO)                | roadmap BL-01  | Annotate DPO superseded by D11              | Grep clean of DPO as required      |
| MR-L04 | P0  | CONFLICT      | N/A      | Zamtel collections marketing vs flag           | roadmap BL-04  | Hide Zamtel until F9a                       | UI matches flag; decision recorded |
| MR-L05 | P2  | CONFLICT      | N/A      | Questionnaire blank; answers in decisions      | sfq SFQ-20     | Q→D mapping table                           | 75-row mapping committed           |

---

## 11. Deduplication map (audit ID → MR-ID)

| Theme                       | Canonical MR                                   | Also cited as                                                                                                         |
| --------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Prepaid → ledger collection | MR-B01                                         | foundation R2; master BL-01; sfq SFQ-01; roadmap BL-02; blueprint BL-P0-03; product RB-PS-003; events BL-002; PR #274 |
| Release accounting          | MR-B01b                                        | impl payment-release report; PR #288/#294; events BL-002 (escrow drill)                                               |
| Escrow release n8n          | MR-W01                                         | foundation R3; events BL-001; product RB-PS-003; blueprint BL-P0-01; master BL-04; sfq SFQ-02; roadmap BL-03          |
| Tickets issue n8n           | MR-W02                                         | foundation R3; events BL-001; product RB-PS-005; blueprint BL-P0-02; sfq SFQ-03; roadmap BL-03                        |
| Migration drift             | MR-S01 / MR-S11                                | foundation R8; master BL-02; sfq SFQ-06; roadmap BL-08; PR #293 `0056`                                                |
| Role hook / RBAC            | MR-S02 / MR-R04 / MR-A01                       | foundation R6; master BL-03; sfq SFQ-05; roadmap BL-05/BL-08                                                          |
| Seller CTA                  | MR-C01                                         | foundation R1; master BL-06; sfq SFQ-07; roadmap BL-06; blueprint BL-P1-05; product RB-PS-004                         |
| Demo catalogue              | MR-D01                                         | foundation R5; product RB-PS-004; blueprint BL-P1-02; master BL-07; sfq SFQ-08; roadmap BL-12                         |
| Observability               | MR-O01                                         | foundation R4; master BL-05; sfq SFQ-10; blueprint BL-P1-08; roadmap BL-07                                            |
| Backups                     | MR-W04 / MR-O04                                | foundation R3; master BL-08; sfq SFQ-11; roadmap BL-09                                                                |
| FORCE RLS tickets           | MR-R01                                         | events BL-003; master BL-10                                                                                           |
| KYC integrity               | MR-D02 / MR-B11 / MR-A03 / MR-V01              | blueprint BL-P0-05; events F036; roadmap BL-13; PR #291/#293                                                          |
| Legal counsel               | MR-L01                                         | sfq SFQ-04                                                                                                            |
| Meilisearch claims          | C-STACK-SEARCH / MR-L02                        | events BL-014; product RB-PS-006; master; roadmap                                                                     |
| product_class               | MR-S05                                         | product RB-PS-001                                                                                                     |
| Condition model             | MR-S06                                         | product RB-PS-002                                                                                                     |
| Panel honesty               | MR-C02/C04/C05/C06/C08; MR-A04–A06; MR-V01/V08 | PR #289/#290/#291; integration review                                                                                 |

---

## 12. P0 open set (release cannot proceed)

| #   | MR-ID                  | One-line blocker                               | Maturity note                |
| --- | ---------------------- | ---------------------------------------------- | ---------------------------- |
| 1   | MR-B01                 | Prepaid → escrow ledger **staging-unverified** | CODE_COMPLETE (#274)         |
| 2   | MR-B01b                | Release accounting **staging-unverified**      | CODE_COMPLETE (#288/#294)    |
| 3   | MR-W01                 | Escrow auto-release workflow not live          | MISSING                      |
| 4   | MR-W02                 | Ticket issuance workflow not live              | MISSING                      |
| 5   | MR-S01 / MR-S11        | DB migration drift (incl. `0056` unapplied)    | CONFLICT / rollout-dependent |
| 6   | MR-R01                 | FORCE RLS exceptions on ticket tier tables     | PARTIAL                      |
| 7   | MR-D02 / MR-B11        | KYC orphans live; `0056` not applied           | CODE_COMPLETE; rollout open  |
| 8   | MR-B03                 | Refund/cancel matrix unproven                  | NOT_AUDITABLE                |
| 9   | MR-B04                 | Organiser Tier-1 GMV cap not evidenced         | MISSING                      |
| 10  | MR-L01                 | Legal/DPA/NPS counsel sign-off pending         | NOT_AUDITABLE                |
| 11  | MR-L04 / C-PAY-ZAMTEL  | Zamtel collections conflict unresolved         | Founder decision             |
| 12  | MR-A02 / C-ADMIN-ROLES | Admin RBAC two-tier conflict unresolved        | Founder decision             |
| 13  | MR-O03                 | No STAGING_VERIFIED sandbox payment proof      | Blocks G3/G4                 |

**Scope-conditional P0s:** MR-S05, MR-S06, MR-B02, MR-V05 — only if launch claims Class D/E or used goods.

---

## 13. Explicit non-actions

1. Do **not** seed 75–100 / 840 vendors or fake GMV to match documents.
2. Do **not** build Django, Meilisearch, Celery, Redis, DPO, or Yango API against superseded docs.
3. Do **not** flip `public_launch=true` until P0 money/trust gates are **STAGING_VERIFIED** / **PRODUCTION_VERIFIED** as required by `release-gates.md`.
4. Do **not** mark MR-B01 / MR-B01b / MR-D02 closed on CODE_COMPLETE alone.
5. Do **not** auto-create `kyc_records` for orphaned demo vendors (PR #293 explicit non-action).

---

_Related:_ `production-readiness-scorecard.md` · `panel-backlogs.md` · `release-gates.md` · `source-conflicts-and-decisions.md` · `implementation-wave-plan.md`
