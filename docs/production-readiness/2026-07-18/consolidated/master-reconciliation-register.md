# Master Reconciliation Register — Vergeo5 / Convergeo

**Consolidation date:** 2026-07-18 (post-implementation refresh)  
**Role:** Audit Consolidation Lead  
**Mode:** Documentation only — no production changes, no application code edits  
**Master tip reconciled:** `d5c2134` (includes PR #293)  
**Sources:** Six document audits under `../document-audits/*` · foundation (`../foundation/*`) · panel implementation reports · panel PR integration review · KYC integrity report · payment release accounting report

**Verdict:** Platform remains a **live demo marketplace** with a substantially stronger **code** money/trust shell after same-day merges — **not** real-money production-ready while any **P0** below lacks staging-verified or production-verified evidence.

---

## How to read this register

| Column          | Meaning                                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **MR-ID**       | Deduplicated master finding ID (stable for coding sessions)                                                                            |
| **Priority**    | P0 release blocker · P1 launch quality · P2 hygiene/roadmap · DOC doc-only                                                             |
| **Status**      | VERIFIED / PARTIAL / MISSING / CONFLICT / NOT_AUDITABLE (live / ops evidence)                                                          |
| **Code**        | `DONE` / `PARTIAL` / `MISSING` / `N/A` on master tip                                                                                   |
| **Staging**     | `PASS` / `FAIL` / `NOT_RUN` / `N/A`                                                                                                    |
| **Production**  | `PASS` / `FAIL` / `NOT_RUN` / `N/A`                                                                                                    |
| **Class**       | `COMMITTED` (launch requirement) · `ASPIRATION` (Phase 2+/doc fiction) · `DOC` (superseded SoT)                                        |
| **Workstream**  | data · schema · backend/API · customer · vendor · admin · workflow · security/RLS · observability · legal/docs · payments · operations |
| **Source refs** | Paths into document audits + foundation risk IDs + PR numbers                                                                          |

**Rules applied**

- Findings that appear in multiple audits are merged into one MR-ID; all source IDs are preserved.
- Stack “conflicts” that are intentional supersessions (`docs/plan/00-decisions.md` D18–D24) are **DOC**, not engineering defects — see `source-conflicts-and-decisions.md`.
- **Merged code is not listed as MISSING.** Code-complete items stay open only for staging/production evidence.
- Empty operational tables with present schema = **PARTIAL** (unproven), not MISSING schema.
- Do **not** seed production to “close” empty operational tables.
- Do **not** declare production-ready while payment release accounting, migration rollout, RLS, workflows, monitoring, backup/restore, or rollback evidence is incomplete.

### Evidence ladder

| Layer                   | Meaning                                                           |
| ----------------------- | ----------------------------------------------------------------- |
| **Code-complete**       | Merged to `master`; unit/integration tests exist in repo          |
| **Staging-verified**    | Sandbox/staging environment exercised with VERIFIED artifacts     |
| **Production-verified** | Live production probe/SQL/n8n/deploy SHA matches intended release |

Repository implementation alone never upgrades a production behaviour to **VERIFIED** (per `../foundation/document-audit-contract.md`).

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

---

## Post-implementation merge ledger (do not treat as missing)

| PR                  | Merge SHA        | Delivered                                                                                                                  | Code | Staging | Production                                   |
| ------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------- | ---- | ------- | -------------------------------------------- |
| **#274**            | `17b2658`        | Prepaid `settle_prepaid_collection` → `CHARGE_RECEIVED` before payment SUCCESS; webhook idempotency                        | DONE | NOT_RUN | NOT_RUN                                      |
| **#288** / M08-P08b | (via #294 stack) | Product/service release-side commission capture                                                                            | DONE | NOT_RUN | NOT_RUN                                      |
| **#289**            | `5596853`        | Customer: categories, compare, calendar→events, logistics copy, false-success UI hardening, API base fail-closed           | DONE | NOT_RUN | NOT_RUN (live still older SHA at foundation) |
| **#290**            | `3c1983f`        | Admin: analytics empty-state honesty, D16 dispatch UX, escrow amount honesty                                               | DONE | NOT_RUN | NOT_RUN                                      |
| **#291**            | `2fc6b79`        | Vendor: KYC UI gating, analytics honesty; VEND-10 OUT                                                                      | DONE | NOT_RUN | NOT_RUN                                      |
| **#292**            | (docs)           | Panel PR integration review — PASS merge/compile; FAIL go-live                                                             | N/A  | N/A     | N/A                                          |
| **#294**            | `3f53e55`        | Release accounting: `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR` from `commission_snapshot` (product/service/event/COD) | DONE | NOT_RUN | NOT_RUN                                      |
| **#293**            | `d5c2134`        | KYC integrity: migration `0056`, eligibility freeze, guarded admin lifecycle, orphan report                                | DONE | NOT_RUN | NOT_RUN (`0056` unapplied live)              |

Foundation production frontend SHA at audit time: `8cc1fa0` (PR #271). Panel/money merges above are **on master but not production-verified**.

---

## 0. Conflict ledger (summary)

Full decision ownership lives in `source-conflicts-and-decisions.md`. Summary:

| Conflict                                                     | Stance                                         | Blocks                     |
| ------------------------------------------------------------ | ---------------------------------------------- | -------------------------- |
| C-STACK-* (Django/Meilisearch/Celery/Railway/Realtime/Yango) | DOC superseded by D18–D24                      | Do not build               |
| C-PAY-PROVIDER (DPO)                                         | DOC superseded by D11 Lenco-only               | Doc banner                 |
| C-PAY-ZAMTEL                                                 | **OPEN founder (F9a)**                         | G14                        |
| C-ADMIN-ROLES                                                | **OPEN founder**                               | G15, ADM-01                |
| C-MIG-DRIFT                                                  | **Genuine P0** (now includes unapplied `0056`) | G0, G9                     |
| C-KYC-TIER                                                   | Live orphans VERIFIED; code DONE (#293)        | G12 until migrate+repair   |
| C-DEMO-PUBLIC                                                | **OPEN merch**                                 | G11                        |
| C-CONDITION / C-ESCROW-HOLD / product_class                  | Scope-gated                                    | Only if Class D/E claimed  |
| C-EVENT-TYPE (`multi_day`)                                   | Product decision                               | Schema or accept `ends_at` |
| C-TRACTION (840 vendors / K184k GMV)                         | Wireframe fiction                              | Never seed                 |

---

## 1. Data / operational emptiness

| MR-ID  | Pri | Status                  | Code                                 | Staging | Prod    | Class      | Finding                                      | Live evidence                                                       | Source refs                                                                     | Action                                                                                   | Acceptance                                                                    |
| ------ | --- | ----------------------- | ------------------------------------ | ------- | ------- | ---------- | -------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| MR-D01 | P1  | VERIFIED                | N/A                                  | FAIL    | FAIL    | COMMITTED  | Demo catalogue presented as public inventory | 3 vendors; 134 listings; 134 `demo/%` images                        | foundation R5; product F024; blueprint F017; sfq E6; roadmap F050; master BL-07 | Label/quarantine demo **or** exclude from public search; keep `public_launch=false`      | Public UX cannot be mistaken for national marketplace                         |
| MR-D02 | P0  | VERIFIED (live orphans) | **DONE** (#291 UI + #293 API/`0056`) | FAIL    | FAIL    | COMMITTED  | KYC tier without audit trail                 | Live: `kyc_records=0`, vendors `kyc_tier=2`; code freezes bare tier | blueprint BL-P0-05; events F036; roadmap F016; `impl/kyc-integrity-report.md`   | Apply `0056` staging→prod; orphan report; **controlled** repair (no raw UPDATE); E2E KYC | Zero privilege from bare `kyc_tier`; every effective tier has approved record |
| MR-D03 | P1  | VERIFIED                | N/A                                  | N/A     | N/A     | COMMITTED  | Zero money/ticket/order rows                 | payments/ledger/orders/tickets/payouts/refunds = 0                  | foundation §5; all six audits                                                   | Sandbox drills only — do not fabricate prod rows                                         | Sandbox fixtures VERIFIED; prod empty until go-live                           |
| MR-D04 | P1  | VERIFIED                | PARTIAL                              | FAIL    | FAIL    | COMMITTED  | Events inventory empty                       | events=0, tickets=0                                                 | events F047; product F025; blueprint F032                                       | Organiser onboarding after MR-W01/W02                                                    | ≥1 published Phase-1 event in beta                                            |
| MR-D05 | P1  | VERIFIED                | PARTIAL                              | FAIL    | FAIL    | COMMITTED  | Services RFQ empty                           | 1 demo service; jobs=0                                              | blueprint F030–031                                                              | Onboard providers after notifications proven                                             | RFQ→quote; outbox drains                                                      |
| MR-D06 | P2  | PARTIAL                 | DONE (schema)                        | NOT_RUN | NOT_RUN | ASPIRATION | Tiered/wholesale pricing unused              | `price_tiers` schema OK; unused                                     | product F033                                                                    | After B2B path ready                                                                     | One tiered listing checkout-safe                                              |

---

## 2. Schema / migrations

| MR-ID  | Pri   | Status         | Code                           | Staging | Prod | Class                    | Finding                             | Evidence                                                       | Source refs                                                  | Action                                                         | Acceptance                                   |
| ------ | ----- | -------------- | ------------------------------ | ------- | ---- | ------------------------ | ----------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------- | -------------------------------------------- |
| MR-S01 | P0    | CONFLICT       | DONE (repo tip through `0056`) | FAIL    | FAIL | COMMITTED                | Live DB ≠ git tip                   | Missing applied `0051`, `0053`–`0056`; `0052` version-key skew | foundation §4; master BL-02; sfq SFQ-06; roadmap BL-08; #293 | Backup → reconcile plan → apply in order; record SHA↔migration | `schema_migrations` matches agreed target    |
| MR-S02 | P0→P1 | MISSING (live) | DONE (file `0051`)             | FAIL    | FAIL | COMMITTED                | Role hook unapplied                 | `custom_access_token*` absent live                             | foundation R6/R8; master BL-03; sfq SFQ-05                   | Apply `0051` + Auth hook **or** written manual-grant exception | JWT roles consistent **or** signed exception |
| MR-S03 | P1    | MISSING (live) | DONE (`0053`)                  | FAIL    | FAIL | ASPIRATION→P1            | Translation overrides               | Unapplied                                                      | sfq SFQ-09; master                                           | Apply when vernacular work starts                              | Table live; override path tested             |
| MR-S04 | P1    | MISSING (live) | DONE (`0054`/`0055`)           | FAIL    | FAIL | COMMITTED (services GTM) | Service reviews / bookable          | Unapplied                                                      | master; sfq                                                  | Apply with services GTM                                        | OpenAPI behaviour matches                    |
| MR-S05 | P0*   | MISSING        | MISSING                        | N/A     | N/A  | ASPIRATION*              | `product_class` A–E                 | No column                                                      | product RB-PS-001                                            | Only if launch claims five classes                             | Additive enum + OpenAPI                      |
| MR-S06 | P0*   | CONFLICT       | MISSING                        | N/A     | N/A  | ASPIRATION*              | Condition too narrow                | CHECK `new\|refurbished`                                       | product RB-PS-002                                            | Expand before Class D                                          | Facets + RLS tests                           |
| MR-S07 | P1    | MISSING        | MISSING                        | N/A     | N/A  | ASPIRATION               | Variants / sale_unit / pricing_mode | Absent                                                         | product RB-PS-008/009                                        | After Class A proven                                           | Modes stored                                 |
| MR-S08 | P1    | CONFLICT       | N/A                            | N/A     | N/A  | COMMITTED (decide)       | Event `multi_day` type              | Brief vs live 4 types + `ends_at`                              | events BL-007                                                | Decision in `00-decisions`                                     | UI labels match                              |
| MR-S09 | P1    | MISSING        | MISSING                        | N/A     | N/A  | ASPIRATION               | Co-organiser / door roles           | No `event_organiser_roles`                                     | events BL-008                                                | Additive event-scoped roles                                    | Door scans only                              |
| MR-S10 | P2    | MISSING        | MISSING                        | N/A     | N/A  | ASPIRATION               | Venue capacity / fee_mode / promo   | Absent                                                         | events BL-010/011/015                                        | Phase gates                                                    | Oversell/promo rules                         |

\*Scope-gated: hard P0 only when product claims include Class D/E or used-goods launch.

---

## 3. Backend / API / payments

| MR-ID   | Pri | Status        | Code            | Staging | Prod    | Class              | Finding                               | Evidence                                                                        | Source refs                                                                                                        | Action                                          | Acceptance                                               |
| ------- | --- | ------------- | --------------- | ------- | ------- | ------------------ | ------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- | -------------------------------------------------------- |
| MR-B01  | P0  | PARTIAL       | **DONE** (#274) | FAIL    | FAIL    | COMMITTED          | Prepaid → escrow ledger unproven live | `settlement.py` posts `CHARGE_RECEIVED`; live payments/ledger = 0               | foundation R2; master BL-01; sfq SFQ-01; roadmap BL-02; blueprint BL-P0-03; product RB-PS-003; events BL-002; #274 | Sandbox MoMo+card → SQL proof; keep fail-closed | Balanced legs; webhook replay safe; **no false success** |
| MR-B01b | P0  | PARTIAL       | **DONE** (#294) | FAIL    | FAIL    | COMMITTED          | Release accounting unproven live      | Capture-before-release from `commission_snapshot`; tests green; 0 live releases | `impl/payment-release-accounting-report.md`; #294                                                                  | Staging release tick + recon after MR-W01       | Escrow nets to 0; idempotent retry                       |
| MR-B02  | P0* | PARTIAL       | PARTIAL         | N/A     | N/A     | ASPIRATION*        | Used-goods 72h escrow                 | Flat 48h config                                                                 | product F010                                                                                                       | If used goods in scope                          | Hold window honoured                                     |
| MR-B03  | P0  | NOT_AUDITABLE | PARTIAL         | FAIL    | FAIL    | COMMITTED          | Refund/cancel matrix unproven         | refunds/disputes=0                                                              | events BL-005                                                                                                      | Sandbox cancel→refund+notify                    | Policy matches code                                      |
| MR-B04  | P0  | MISSING       | MISSING         | N/A     | N/A     | COMMITTED (events) | Organiser Tier-1 GMV cap ~K20k        | Not in live config                                                              | events BL-004                                                                                                      | Implement/verify cap                            | Over-cap rejected + audit                                |
| MR-B05  | P1  | PARTIAL       | DONE (TTL)      | NOT_RUN | NOT_RUN | COMMITTED          | Stock reservation unproven            | TTL=15m; reservations=0                                                         | product F014                                                                                                       | Staging reserve→expire→pay                      | Atomic unpaid release                                    |
| MR-B06  | P1  | PARTIAL       | PARTIAL         | N/A     | N/A     | ASPIRATION         | Listing modes 3/5                     | Missing unique/MTO                                                              | product RB-PS-011                                                                                                  | Add modes + validation                          | Five flows + tests                                       |
| MR-B07  | P1  | PARTIAL       | DONE (search)   | FAIL    | FAIL    | COMMITTED          | Search degraded                       | `degraded=true` observed                                                        | blueprint BL-P1-07                                                                                                 | Diagnose embeddings/FTS                         | `degraded=false` common queries                          |
| MR-B08  | P1  | PARTIAL       | PARTIAL         | N/A     | N/A     | COMMITTED          | Category×tier gates                   | Makeup/used skip rules                                                          | product RB-PS-015                                                                                                  | Enforce 422 with reason                         | Prohibited rejected                                      |
| MR-B09  | P2  | PARTIAL       | DONE            | NOT_RUN | NOT_RUN | COMMITTED          | OTP rate limit runtime                | Limiter code present                                                            | roadmap BL-17                                                                                                      | Integration test                                | Rapid OTP limited                                        |
| MR-B10  | —   | NOT_AUDITABLE | N/A             | N/A     | FAIL    | COMMITTED          | API container git SHA unknown         | OpenAPI `0.1.0`; GHCR unauthorized                                              | foundation R8                                                                                                      | Read `API_IMAGE_TAG` / digest                   | SHA in release ledger                                    |

---

## 4. Customer

| MR-ID  | Pri | Status         | Code                     | Staging | Prod | Class      | Finding                             | Evidence                                    | Source refs                                                                | Action                                     | Acceptance                           |
| ------ | --- | -------------- | ------------------------ | ------- | ---- | ---------- | ----------------------------------- | ------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------ | ------------------------------------ |
| MR-C01 | P1  | PARTIAL        | DONE (fail-closed)       | FAIL    | FAIL | COMMITTED  | Seller CTA unavailable              | Env likely unset; no localhost leak         | foundation R1; master BL-06; sfq SFQ-07; roadmap BL-06; blueprint BL-P1-05 | Set `NEXT_PUBLIC_VENDOR_APP_URL`; redeploy | CTA → vendor prod                    |
| MR-C02 | P1  | PARTIAL (live) | **DONE** (#289)          | FAIL    | FAIL | COMMITTED  | Categories/compare were 404 on live | Code routes exist; prod undeployed          | product RB-PS-012; #289                                                    | Deploy customer tip; re-probe              | `/en/categories` + `/en/compare` 200 |
| MR-C03 | P1  | PARTIAL        | PARTIAL                  | FAIL    | FAIL | COMMITTED  | Events discovery UX incomplete      | Where lens / Tonight+Weekend / selling-fast | events BL-009                                                              | After supply                               | Phase-1 browse matches               |
| MR-C04 | P1  | PARTIAL        | DONE (serwist)           | FAIL    | FAIL | COMMITTED  | PWA SW 404 on live                  | Manifest 200; SW 404 at foundation          | blueprint BL-P1-01; #289 stack                                             | Deploy + probe SW                          | SW 200; installable                  |
| MR-C05 | P1  | CONFLICT       | **DONE** (#289 copy)     | FAIL    | FAIL | COMMITTED  | Launch copy overclaim risk          | Hero logistics copy hardened in code        | blueprint BL-P1-06                                                         | Deploy + audit residual                    | No Yango/own-fleet/Django claims     |
| MR-C06 | P2  | PARTIAL (live) | **DONE** (#289 redirect) | FAIL    | FAIL | COMMITTED  | Calendar 404                        | Code redirects to events                    | events F027                                                                | Deploy                                     | No dead nav                          |
| MR-C07 | P2  | MISSING        | MISSING                  | N/A     | N/A  | ASPIRATION | Wishlist / reorder                  | No tables/APIs                              | foundation R6                                                              | Scope fence OUT                            | Explicit OUT or shipped              |

---

## 5. Vendor

| MR-ID  | Pri | Status        | Code                 | Staging | Prod    | Class       | Finding                     | Evidence                  | Source refs                      | Action                                       | Acceptance              |
| ------ | --- | ------------- | -------------------- | ------- | ------- | ----------- | --------------------------- | ------------------------- | -------------------------------- | -------------------------------------------- | ----------------------- |
| MR-V01 | P1  | NOT_AUDITABLE | PARTIAL              | NOT_RUN | NOT_RUN | COMMITTED   | Listing UX / attach &lt;30s | Login-gated; no audit JWT | product F038; blueprint F021–022 | Test vendor JWT audit                        | Flows timed + E2E       |
| MR-V02 | P1  | PARTIAL       | PARTIAL              | NOT_RUN | NOT_RUN | COMMITTED   | Offline scanner cache       | Offline cannot verify     | events BL-006                    | Cache + scan-sync                            | Offline then sync       |
| MR-V03 | P1  | PARTIAL       | **DONE** (#291/#293) | FAIL    | FAIL    | COMMITTED   | KYC lifecycle unexercised   | kyc_records=0 live        | roadmap BL-13; blueprint         | Sandbox Applied→Review→Approved after `0056` | Cannot skip states      |
| MR-V04 | P1  | MISSING       | MISSING              | N/A     | N/A     | ASPIRATION* | Evidence photos non-new     | No IMEI/VIN/evidence_kind | product RB-PS-007                | Before Class D                               | Reject missing evidence |
| MR-V05 | P2  | MISSING       | MISSING              | N/A     | N/A     | ASPIRATION  | Vendor staff RBAC           | Single owner              | foundation R6                    | Post-v1 / OUT                                | Documented              |
| MR-V06 | P2  | MISSING       | MISSING              | N/A     | N/A     | ASPIRATION  | Co-organiser invite UX      | Schema absent             | events BL-008                    | After MR-S09                                 | Door/Manager invite     |

---

## 6. Admin

| MR-ID  | Pri   | Status        | Code                      | Staging | Prod | Class              | Finding                    | Evidence                            | Source refs                               | Action                           | Acceptance                  |
| ------ | ----- | ------------- | ------------------------- | ------- | ---- | ------------------ | -------------------------- | ----------------------------------- | ----------------------------------------- | -------------------------------- | --------------------------- |
| MR-A01 | P0→P1 | MISSING       | MISSING                   | N/A     | N/A  | COMMITTED          | Admin role management UI   | No CRUD UI                          | foundation R6; master BL-03; roadmap F034 | UI + audit **or** manual ops doc | Grant/revoke audited        |
| MR-A02 | P0    | CONFLICT      | MISSING                   | N/A     | N/A  | COMMITTED (decide) | Two-tier admin unsupported | CHECK single `admin`                | roadmap BL-05                             | Founder: adopt or supersede      | Decision recorded           |
| MR-A03 | P1    | PARTIAL       | **DONE** (#293 endpoints) | FAIL    | FAIL | COMMITTED          | KYC/moderation queues      | Endpoints exist; empty / undeployed | product RB-PS-014; #293                   | Staging lifecycle                | Queue + guarded transitions |
| MR-A04 | P1    | PARTIAL       | **DONE** (#290 honesty)   | FAIL    | FAIL | COMMITTED          | Analytics tiles            | Empty-state honesty in code; 0 rows | foundation R4; #290                       | Deploy + traffic                 | Tiles = aggregates          |
| MR-A05 | P1    | PARTIAL       | PARTIAL                   | N/A     | N/A  | COMMITTED          | Authenticity report policy | Not enforced                        | product RB-PS-013                         | Report → queue                   | Policy documented           |
| MR-A06 | —     | NOT_AUDITABLE | N/A                       | N/A     | N/A  | COMMITTED          | Admin deep UI audit        | Cloudflare Access                   | foundation; blueprint                     | Access-approved session          | Empty-state pack            |

---

## 7. Workflows / operations

| MR-ID  | Pri | Status           | Code             | Staging | Prod    | Class         | Finding                              | Evidence                               | Source refs                                                                                                  | Action                                         | Acceptance                |
| ------ | --- | ---------------- | ---------------- | ------- | ------- | ------------- | ------------------------------------ | -------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | ------------------------- |
| MR-W01 | P0  | VERIFIED MISSING | DONE (repo JSON) | FAIL    | FAIL    | COMMITTED     | Escrow auto-release n8n absent       | Live: only dispatch + payment recon    | foundation R3; events BL-001; product RB-PS-003; blueprint BL-P0-01; master BL-04; sfq SFQ-02; roadmap BL-03 | Activate `release-job` + dry-run + sandbox     | Active; no double-release |
| MR-W02 | P0  | VERIFIED MISSING | DONE (repo JSON) | FAIL    | FAIL    | COMMITTED     | Tickets-issue / event-release absent | Inactive; tickets=0                    | foundation R3; events BL-001; product RB-PS-005; blueprint BL-P0-02; sfq SFQ-03                              | Activate issue + event-release ticks           | Exactly-once issue        |
| MR-W03 | P1  | MISSING          | DONE (repo)      | FAIL    | FAIL    | ASPIRATION→P1 | Lifecycle automations                | Onboarding/abandoned-cart not live     | roadmap BL-14                                                                                                | Import + prove                                 | Each fires once           |
| MR-W04 | P1  | MISSING          | PARTIAL (docs)   | FAIL    | FAIL    | COMMITTED     | Backup workflow                      | No n8n backup; host cron NOT_AUDITABLE | foundation R3; master BL-08; sfq SFQ-11; roadmap BL-09                                                       | Deploy backup **or** prove cron; restore drill | Dated artifact + restore  |
| MR-W05 | P1  | PARTIAL          | DONE             | PARTIAL | PARTIAL | COMMITTED     | Payment recon cron only              | One of two live workflows              | foundation                                                                                                   | Prove mismatch alerting                        | Actionable recon          |
| MR-W06 | P2  | MISSING          | DONE (repo)      | FAIL    | FAIL    | ASPIRATION    | Embeddings / sweeper / digests       | Not live                               | foundation R3                                                                                                | Activate as needed                             | Tick logged               |

---

## 8. Security / RLS

| MR-ID  | Pri | Status  | Code    | Staging | Prod | Class     | Finding                                | Evidence                                           | Source refs                      | Action                           | Acceptance            |
| ------ | --- | ------- | ------- | ------- | ---- | --------- | -------------------------------------- | -------------------------------------------------- | -------------------------------- | -------------------------------- | --------------------- |
| MR-R01 | P0  | PARTIAL | PARTIAL | FAIL    | FAIL | COMMITTED | FORCE RLS false on ticket tiers        | `ticket_type_instances`, `ticket_type_price_tiers` | events F051/BL-003; master BL-10 | Enable FORCE or signed exception | Advisor + decision    |
| MR-R02 | P2  | PARTIAL | PARTIAL | FAIL    | FAIL | COMMITTED | FORCE RLS false on `product_relations` | Same pattern                                       | master BL-10                     | Same as MR-R01                   | Documented            |
| MR-R03 | P2  | PARTIAL | N/A     | N/A     | FAIL | COMMITTED | Leaked-password protection off         | Advisor WARN                                       | master BL-10                     | Enable in Auth                   | Cleared/accepted      |
| MR-R04 | P0  | PARTIAL | PARTIAL | FAIL    | FAIL | COMMITTED | Authz provisioning gap                 | 0051 absent; manual grants                         | foundation R6; sfq SFQ-05        | Close MR-S02 + MR-A01/A02        | Isolation tests green |
| MR-R05 | P1  | PARTIAL | PARTIAL | N/A     | N/A  | COMMITTED | CI secret-scan non-blocking            | `continue-on-error: true`                          | foundation R7; roadmap BL-10     | Make blocking                    | Merges blocked on hit |

---

## 9. Observability / test

| MR-ID  | Pri | Status                  | Code                       | Staging | Prod    | Class     | Finding                       | Evidence                        | Source refs                                                                | Action                            | Acceptance                    |
| ------ | --- | ----------------------- | -------------------------- | ------- | ------- | --------- | ----------------------------- | ------------------------------- | -------------------------------------------------------------------------- | --------------------------------- | ----------------------------- |
| MR-O01 | P1  | VERIFIED MISSING        | PARTIAL (SDK)              | FAIL    | FAIL    | COMMITTED | No Vergeo5 Sentry projects    | Org has unrelated projects only | foundation R4; master BL-05; sfq SFQ-10; blueprint BL-P1-08; roadmap BL-07 | Create projects + DSNs            | Test error per app            |
| MR-O02 | P1  | NOT_AUDITABLE           | N/A                        | N/A     | N/A     | COMMITTED | Uptime monitors               | Not probed                      | foundation R4                                                              | Configure health monitors         | Green health                  |
| MR-O03 | P0  | PARTIAL                 | **DONE** (#274/#294 tests) | FAIL    | FAIL    | COMMITTED | Money-path sandbox unproven   | 0 live payments                 | MR-B01/B01b; roadmap BL-16                                                 | Sandbox MoMo+card + failure paths | Suite green; no false success |
| MR-O04 | P1  | MISSING / NOT_AUDITABLE | PARTIAL                    | FAIL    | FAIL    | COMMITTED | Backup + restore proof        | Tied to MR-W04                  | MR-W04                                                                     | Restore drill                     | RPO documented                |
| MR-O05 | P2  | PARTIAL                 | PARTIAL                    | FAIL    | FAIL    | COMMITTED | Staging pipeline stub         | `deploy-staging.yml` stub       | roadmap BL-11                                                              | Real staging parity               | UAT journeys pass             |
| MR-O06 | P2  | PARTIAL                 | N/A                        | NOT_RUN | NOT_RUN | COMMITTED | Lighthouse not freshly probed | Budgets exist                   | roadmap BL-21                                                              | Mobile Fast-3G/360px              | Perf≥90 SEO≥95 A11y≥95        |

---

## 10. Legal / docs

| MR-ID  | Pri | Status        | Class     | Finding                                   | Source refs        | Action                                | Acceptance                         |
| ------ | --- | ------------- | --------- | ----------------------------------------- | ------------------ | ------------------------------------- | ---------------------------------- |
| MR-L01 | P0  | NOT_AUDITABLE | COMMITTED | Zambian counsel / DPA / NPS Act escrow    | sfq SFQ-04 (F4)    | Counsel review before real money      | Written sign-off — never inferred  |
| MR-L02 | DOC | CONFLICT      | DOC       | Strategy docs claim obsolete stack        | All six audits     | Banner SUPERSEDED → `00-decisions.md` | Engineers cite locked decisions    |
| MR-L03 | DOC | CONFLICT      | DOC       | DPO provider language                     | roadmap BL-01      | Annotate DPO superseded               | Grep clean as required provider    |
| MR-L04 | P0  | CONFLICT      | COMMITTED | Zamtel collections vs flag                | roadmap BL-04; F9a | Hide Zamtel until F9a proven          | UI matches flag; decision recorded |
| MR-L05 | P2  | CONFLICT      | DOC       | Questionnaire blank; answers in decisions | sfq SFQ-20         | Q→D mapping table                     | 75-row mapping committed           |

---

## 11. Deduplication map (audit ID → MR-ID)

| Theme                | Canonical MR             | Also cited as                                                                                                                  |
| -------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Prepaid → ledger     | MR-B01                   | foundation R2; master BL-01; sfq SFQ-01; roadmap BL-02; blueprint BL-P0-03; product RB-PS-003; events BL-002; **PR #274 code** |
| Release accounting   | MR-B01b                  | #294; `impl/payment-release-accounting-report.md`; depends on #274 + MR-W01                                                    |
| Escrow release n8n   | MR-W01                   | foundation R3; events BL-001; product RB-PS-003; blueprint BL-P0-01; master BL-04; sfq SFQ-02; roadmap BL-03                   |
| Tickets issue n8n    | MR-W02                   | foundation R3; events BL-001; product RB-PS-005; blueprint BL-P0-02; sfq SFQ-03; roadmap BL-03                                 |
| Migration drift      | MR-S01                   | foundation R8; master BL-02; sfq SFQ-06; roadmap BL-08; **+0056 from #293**                                                    |
| Role hook / RBAC     | MR-S02 / MR-R04 / MR-A01 | foundation R6; master BL-03; sfq SFQ-05; roadmap BL-05/BL-08                                                                   |
| Seller CTA           | MR-C01                   | foundation R1; master BL-06; sfq SFQ-07; roadmap BL-06; blueprint BL-P1-05                                                     |
| Demo catalogue       | MR-D01                   | foundation R5; product RB-PS-004; blueprint BL-P1-02; master BL-07; sfq SFQ-08; roadmap BL-12                                  |
| Observability        | MR-O01                   | foundation R4; master BL-05; sfq SFQ-10; blueprint BL-P1-08; roadmap BL-07                                                     |
| Backups              | MR-W04 / MR-O04          | foundation R3; master BL-08; sfq SFQ-11; roadmap BL-09                                                                         |
| FORCE RLS tickets    | MR-R01                   | events BL-003; master BL-10                                                                                                    |
| KYC integrity        | MR-D02                   | blueprint BL-P0-05; events F036; roadmap BL-13; **#291/#293 code**                                                             |
| Legal counsel        | MR-L01                   | sfq SFQ-04                                                                                                                     |
| Meilisearch claims   | C-STACK-SEARCH / MR-L02  | events BL-014; product RB-PS-006; master; roadmap                                                                              |
| product_class        | MR-S05                   | product RB-PS-001                                                                                                              |
| Condition model      | MR-S06                   | product RB-PS-002                                                                                                              |
| Panel honesty routes | MR-C02/C05/C06           | product RB-PS-012; blueprint BL-P1-06; **#289 code**                                                                           |
| Admin honesty        | MR-A04                   | foundation R4; **#290 code**                                                                                                   |

---

## 12. P0 open set (release cannot proceed)

Evidence-adjusted after #274 / #293 / #294 / #289–#291:

| #   | MR-ID                  | Blocker (current framing)                          | What is NOT the blocker                                            |
| --- | ---------------------- | -------------------------------------------------- | ------------------------------------------------------------------ |
| 1   | MR-B01                 | Prepaid → ledger **staging/production unproven**   | Missing `post_transaction` on collection path (**code DONE #274**) |
| 2   | MR-B01b                | Release accounting **staging/production unproven** | Missing capture-before-release (**code DONE #294**)                |
| 3   | MR-W01                 | Escrow auto-release workflow not live              | —                                                                  |
| 4   | MR-W02                 | Ticket issuance workflow not live                  | —                                                                  |
| 5   | MR-S01                 | DB migration drift vs tip (incl. `0056`)           | —                                                                  |
| 6   | MR-R01                 | FORCE RLS exceptions on ticket tier tables         | —                                                                  |
| 7   | MR-D02                 | Live KYC orphans + `0056` unapplied / unrepaired   | Missing API freeze (**code DONE #293**)                            |
| 8   | MR-B03                 | Refund/cancel matrix unproven                      | —                                                                  |
| 9   | MR-B04                 | Organiser Tier-1 GMV cap not evidenced             | —                                                                  |
| 10  | MR-L01                 | Legal/DPA/NPS counsel sign-off pending             | —                                                                  |
| 11  | MR-L04 / C-PAY-ZAMTEL  | Zamtel collections conflict unresolved             | —                                                                  |
| 12  | MR-A02 / C-ADMIN-ROLES | Admin RBAC two-tier conflict unresolved            | —                                                                  |
| 13  | MR-O03                 | No VERIFIED sandbox payment proof                  | Missing unit tests (**tests DONE**)                                |

**Scope-conditional P0s:** MR-S05, MR-S06, MR-B02, MR-V04 — only if launch claims Class D/E / used goods.

---

## 13. Explicit non-actions

1. Do **not** seed 75–100 / 840 vendors or fake GMV to match documents.
2. Do **not** build Django, Meilisearch, Celery, Redis, DPO, or Yango API against superseded docs.
3. Do **not** flip `public_launch=true` until P0 money/trust gates are staging- and production-verified.
4. Do **not** mark MR-B01 / MR-B01b / MR-D02 resolved solely because PRs merged — evidence ladder required.
5. Do **not** apply `0056` or repair KYC orphans via ad-hoc production SQL outside the controlled plan in `impl/kyc-integrity-report.md`.

---

_Related:_ `production-readiness-scorecard.md` · `panel-backlogs.md` · `release-gates.md` · `source-conflicts-and-decisions.md` · `implementation-wave-plan.md`
