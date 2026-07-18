# Master Reconciliation Register — Vergeo5 / Convergeo

**Consolidation date:** 2026-07-18  
**Role:** Audit Consolidation Lead  
**Mode:** Documentation only — no production changes, no application code edits  
**Sources:** Six document audits under `../document-audits/*` + same-day foundation (`../foundation/*`)

**Verdict:** Platform is a **live demo marketplace** with schema/API shell for commerce, events, and trust — **not** real-money production-ready while any **P0** below remains open, unverified, or not auditable.

---

## How to read this register

| Column          | Meaning                                                                                                                                 |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **MR-ID**       | Deduplicated master finding ID (stable for coding sessions)                                                                             |
| **Priority**    | P0 release blocker · P1 launch quality · P2 hygiene/roadmap · DOC doc-only                                                              |
| **Status**      | VERIFIED / PARTIAL / MISSING / CONFLICT / NOT_AUDITABLE (per contract)                                                                  |
| **Workstream**  | One of: data · schema · backend/API · customer · vendor · admin · workflow/integration · security/RLS · test/observability · legal/docs |
| **Source refs** | Paths into document audits + foundation risk IDs                                                                                        |

**Rules applied**

- Findings that appear in multiple audits are merged into one MR-ID; all source IDs are preserved.
- Stack “conflicts” that are intentional supersessions (`00-decisions.md` D18–D24) are **DOC**, not engineering defects — listed explicitly so they are not built against.
- Do **not** recommend direct database edits without a reviewed migration or controlled import plan.
- Do **not** seed production to “close” empty operational tables.

### Source document slugs

| Slug         | Path                                                                |
| ------------ | ------------------------------------------------------------------- |
| `events`     | `../document-audits/convergeo-events-strategy/`                     |
| `product`    | `../document-audits/convergeo-product-strategy-april-2026/`         |
| `blueprint`  | `../document-audits/blueprint-zambia-vergeo-super-app/`             |
| `master`     | `../document-audits/strategic-master-plan-v1/`                      |
| `sfq`        | `../document-audits/strategic-foundation-questionnaire-april-2026/` |
| `roadmap`    | `../document-audits/convergeo-60-day-development-roadmap/`          |
| `foundation` | `../foundation/`                                                    |

---

## 0. Conflict ledger (do not hide)

Every CONFLICT below lists **document claim** vs **live / locked value**. Resolution authority for stack claims: `docs/plan/00-decisions.md` (rank-4 intent) plus live evidence (rank-1).

| Conflict       | Document claim(s)                                                | Live / locked value                                                           | Source refs                                             | Resolution stance                                  |
| -------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------- | -------------------------------------------------- |
| C-STACK-BE     | Django + DRF                                                     | FastAPI + Supabase (D18)                                                      | blueprint F003; master Q9; sfq E1; roadmap F003         | DOC — superseded intentional                       |
| C-STACK-SEARCH | Meilisearch (+pgvector)                                          | Postgres FTS + pg_trgm + pgvector RRF (D22); search sometimes `degraded=true` | events F025; product F018; master Q15; roadmap F006     | DOC stack; P1 search quality                       |
| C-STACK-HOST   | Railway / Render                                                 | OCI/Hetzner + Caddy + Supabase + Cloudflare (D21)                             | master Q11; roadmap F004                                | DOC — superseded                                   |
| C-STACK-ASYNC  | Celery + Redis / Upstash                                         | n8n + outbox (D18/D21)                                                        | blueprint F006; master Q17–18; sfq E8; roadmap F007–008 | DOC — superseded                                   |
| C-STACK-NOTIF  | Supabase Realtime notifications                                  | WhatsApp Cloud API → SMS → email outbox (D15)                                 | blueprint F005; master Q14                              | DOC — superseded                                   |
| C-PAY-PROVIDER | DPO Pay (roadmap) / DPO+Lenco (master/SFQ)                       | **Lenco only** (D11); 0 DPO code refs                                         | roadmap F005; master Q19; sfq E2                        | **P0-investigate → DOC** after founder confirm     |
| C-PAY-ZAMTEL   | Zamtel collections at launch                                     | `zamtel_collections=false`; payout-only pending F9a                           | roadmap F026; blueprint F024; sfq SFQ-12                | **P0** until decision + UI gate                    |
| C-LOGISTICS    | Yango API + own fleet / 10-province ship                         | Manual Lusaka dispatch + nationwide pickup (D16)                              | blueprint F036; master Q43/47; sfq E5                   | DOC — do not build courier API for v1              |
| C-EVENT-TYPE   | Event type includes `multi_day`                                  | CHECK `standard\|recurring\|free_rsvp\|private`; duration via `ends_at`       | events F006                                             | Product decision → schema **or** accept `standard` |
| C-CONDITION    | Used / open-box / for-parts tiers                                | Live CHECK `new\|refurbished` only; all 134 listings `new`                    | product F009                                            | Schema gap before Class D                          |
| C-ESCROW-HOLD  | Used goods 72h escrow                                            | Flat `release_after_delivered_hours=48`                                       | product F010                                            | Config gap if used goods enabled                   |
| C-ADMIN-ROLES  | superadmin + moderator                                           | `user_roles.role` CHECK `customer\|vendor\|admin` only                        | roadmap F033; master BL-03; sfq SFQ-05                  | **P0-investigate** → adopt or supersede            |
| C-LANGUAGES    | EN+Bemba+Nyanja at launch                                        | English-only launch (D27); `0053` unapplied                                   | sfq E3; master Q27                                      | Decision holds; vernacular = P1                    |
| C-DEMO-PUBLIC  | Real marketplace / demo excluded from public search (D25 intent) | Public catalog `total=134` all `demo/` images                                 | product F024; blueprint F017–018; sfq E6; foundation R5 | **Genuine gap (P1)**                               |
| C-TRACTION     | 840 vendors / 12.4k products / K184k GMV (wireframes)            | 3 demo vendors, 134 listings, **0** money rows                                | blueprint F017–018, F038–039                            | Wireframe fiction — never seed                     |
| C-MIG-DRIFT    | Live schema == git tip                                           | Applied ≤0050 + odd `0052`; missing `0051/0053–0055`                          | foundation §4; master BL-02; sfq SFQ-06; roadmap F014   | **P0** genuine                                     |
| C-RETURNS      | “No returns MVP” (master)                                        | Two-lane returns incl. change-of-mind (D17)                                   | master Q48                                              | Production-ahead — doc stale                       |
| C-BRAND        | Convergeo / Vergio / Virgeo                                      | Live **Vergeo5** (`vergeo5.com`)                                              | blueprint F001; roadmap F001                            | Naming hygiene                                     |
| C-CURRENCY     | Multi-currency seam now                                          | ZMW ngwee only                                                                | sfq E4; product F008                                    | ADR required (P2)                                  |
| C-KYC-TIER     | Tier badges imply KYC trail                                      | `kyc_tier=2` on vendors; `kyc_records=0`                                      | blueprint F014–015; events F036                         | **P0** integrity                                   |

---

## 1. Data corrections (master data / operational emptiness)

> Controlled import or seed-replacement plans only. **No ad-hoc SQL UPDATEs** on production money/trust tables.

| MR-ID  | Priority | Status   | Finding                                      | Live evidence                                                     | Source refs                                                                     | Recommended action                                                                                                                         | Acceptance criteria                                                                                             |
| ------ | -------- | -------- | -------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| MR-D01 | P1       | VERIFIED | Demo catalogue presented as public inventory | 3 vendors; 134 listings; 134 `demo/%` images; catalog `total=134` | foundation R5; product F024; blueprint F017; sfq E6; roadmap F050; master BL-07 | Controlled merchandising plan: quarantine/label demo **or** replace via reviewed import; keep `public_launch=false` until money gates pass | Public catalog either excludes demo, labels demo unambiguously, or contains only real vendors; SEO not polluted |
| MR-D02 | P0       | VERIFIED | KYC tier without audit trail                 | `kyc_records=0`; vendors `kyc_tier=2`                             | blueprint BL-P0-05; events F036–037; roadmap F016                               | Investigate seed path; freeze badge claims; require `kyc_records` + guarded transition for tier>0                                          | Every `kyc_tier>0` has auditable history; RLS/admin path tested                                                 |
| MR-D03 | P1       | VERIFIED | Zero money / ticket / order operational rows | payments/ledger/orders/tickets/payouts/refunds = 0                | foundation §5; all six audits                                                   | Sandbox drills only — do not fabricate prod rows                                                                                           | Sandbox fixtures VERIFIED; prod stays empty until go-live                                                       |
| MR-D04 | P1       | VERIFIED | Events inventory empty                       | events=0, tickets=0, public `/events` total 0                     | events F047; product F025; blueprint F032                                       | Controlled organiser onboarding after automation (MR-W01/W02)                                                                              | ≥1 published Phase-1 event under beta when launching events                                                     |
| MR-D05 | P1       | VERIFIED | Services RFQ empty                           | 1 demo service; jobs=0; job_quotes=0                              | blueprint F030–031; sfq                                                         | Onboard real providers after notifications proven                                                                                          | RFQ creates quotes; outbox drained                                                                              |
| MR-D06 | P2       | PARTIAL  | Tiered/wholesale pricing unused              | `price_tiers` schema OK; listings_with_tiers=0                    | product F033                                                                    | After B2B path ready, controlled listing with tiers                                                                                        | One tiered listing readable + checkout-safe                                                                     |

---

## 2. Schema changes (additive migrations only)

| MR-ID  | Priority | Status   | Finding                             | Evidence                                                                                   | Source refs                                              | Recommended action                                                                             | Acceptance criteria                                                                              |
| ------ | -------- | -------- | ----------------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| MR-S01 | P0       | CONFLICT | Live DB ≠ git tip                   | Missing applied `0051`, `0053`, `0054`, `0055`; `0052` version-key skew (`20260717100303`) | foundation §4; master BL-02; sfq SFQ-06; roadmap BL-08   | DBA-reviewed migration reconcile plan; fix 0052 key; apply in order with backup proof (MR-O04) | `schema_migrations` matches agreed target; objects present; release ledger records SHA↔migration |
| MR-S02 | P0→P1    | MISSING  | Role hook migration absent          | `custom_access_token*` fn absent live                                                      | foundation R6/R8; master BL-03; sfq SFQ-05; roadmap F014 | Apply `0051` + enable Auth custom-access-token hook **or** document manual-grant posture       | JWT carries roles from `user_roles` **or** written exception; admin isolation test green         |
| MR-S03 | P1       | MISSING  | Translation overrides absent        | `translation_overrides` absent (0053)                                                      | sfq SFQ-09; master                                       | Apply 0053 when vernacular work starts                                                         | Table live; override path tested                                                                 |
| MR-S04 | P1       | MISSING  | Service reviews / bookable          | 0054/0055 unapplied                                                                        | master; sfq                                              | Apply with services GTM                                                                        | Columns/tables present; RFQ/bookable behaviour matches OpenAPI                                   |
| MR-S05 | P0*      | MISSING  | `product_class` A–E absent          | No column on `products` / `vendor_listings`                                                | product RB-PS-001                                        | **\*P0 only if launch claims five classes**; else gate Phase-1 as Class A branded              | Additive enum + backfill; OpenAPI updated; existing listings readable                            |
| MR-S06 | P0*      | CONFLICT | Condition model too narrow          | CHECK `new\|refurbished` vs brief used/open-box/for-parts                                  | product RB-PS-002                                        | Expand CHECK **before** Class D enablement                                                     | New values insertable under RLS tests; facets updated                                            |
| MR-S07 | P1       | MISSING  | Variants / sale_unit / pricing_mode | No `product_variants`; no `sale_unit`/`base_unit`/`pricing_mode`                           | product RB-PS-008/009                                    | Additive design after Class A path proven                                                      | Modes stored; comparison shows normalized unit price where needed                                |
| MR-S08 | P1       | CONFLICT | Event `multi_day` type              | Brief 5 types vs live 4                                                                    | events BL-007                                            | Decision: add enum **or** accept `standard`+`ends_at`                                          | `00-decisions` updated; UI labels match                                                          |
| MR-S09 | P1       | MISSING  | Co-organiser / door roles           | No `event_organiser_roles`                                                                 | events BL-008                                            | Additive event-scoped roles                                                                    | Door can scan only; no financials                                                                |
| MR-S10 | P2       | MISSING  | Venue capacity / fee_mode / promo   | No venue_capacity, fee_mode, promo_codes                                                   | events BL-010/011/015                                    | Phase gates                                                                                    | Oversell rejected; fee toggle works; promo applies                                               |

\*Catalogue class/condition items are **scope-gated**: they become hard P0 only when product claims include Class D/E or used-goods launch.

---

## 3. Backend / API work

| MR-ID  | Priority      | Status                  | Finding                                    | Evidence                                                                                                                               | Source refs                                                                                   | Recommended action                                                              | Acceptance criteria                                                                           |
| ------ | ------------- | ----------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| MR-B01 | P0            | PARTIAL                 | Prepaid success may not post escrow ledger | Code: prepaid path updates `payments`+`audit_log` only; no `post_transaction(CHARGE_RECEIVED/ESCROW_HOLD)` on that path; live 0 ledger | foundation R2; master BL-01; sfq SFQ-01; roadmap BL-02; blueprint BL-P0-03; product RB-PS-003 | Trace sandbox MoMo+card success; add idempotent ledger hook if confirmed absent | Balanced ledger legs; webhook replay safe; failure-path test; **no false payment-success UI** |
| MR-B02 | P0            | PARTIAL                 | Escrow hold timing vs used goods           | Flat 48h config; no 72h condition path                                                                                                 | product F010                                                                                  | If used goods in scope: config path used=72h                                    | Config + release tick honour hold window                                                      |
| MR-B03 | P0            | NOT_AUDITABLE / PARTIAL | Refund/cancel matrix unproven              | refunds/disputes=0; events matrix unproven                                                                                             | events BL-005                                                                                 | Map matrix → guarded transitions; organiser-cancel auto-refund                  | Cancel → full refund + notify in sandbox; policy matches code                                 |
| MR-B04 | P0            | MISSING                 | Organiser Tier-1 GMV fraud cap             | Cap ~K20k not evidenced in config                                                                                                      | events BL-004                                                                                 | Implement/verify cap; block over-cap publish/sales                              | Over-cap rejected + audit_log                                                                 |
| MR-B05 | P1            | PARTIAL                 | Stock reservation unproven                 | TTL=15m VERIFIED; reservations=0                                                                                                       | product F014                                                                                  | Staging reserve→expire→pay                                                      | Unpaid release atomic; paid reserve consumes stock                                            |
| MR-B06 | P1            | PARTIAL                 | Listing modes incomplete                   | OpenAPI: attach/new_canonical/quick_list; missing unique/MTO                                                                           | product RB-PS-011                                                                             | Add modes + validation                                                          | Five flows reachable with tests                                                               |
| MR-B07 | P1            | PARTIAL                 | Search degraded                            | `/search` `degraded=true` observed                                                                                                     | blueprint BL-P1-07; product                                                                   | Diagnose embeddings/FTS                                                         | `degraded=false` for common queries                                                           |
| MR-B08 | P1            | PARTIAL                 | Category×tier policy gates unclear         | Makeup/used skip rules                                                                                                                 | product RB-PS-015                                                                             | Enforce 422 with reason                                                         | Prohibited listing rejected                                                                   |
| MR-B09 | P2            | PARTIAL                 | OTP rate limit runtime unverified          | Limiter code present                                                                                                                   | roadmap BL-17                                                                                 | Integration test                                                                | Rapid OTP limited in CI                                                                       |
| MR-B10 | NOT_AUDITABLE | NOT_AUDITABLE           | API container git SHA unknown              | OpenAPI `0.1.0`; GHCR unauthorized                                                                                                     | foundation R8                                                                                 | Read `API_IMAGE_TAG` / digest                                                   | SHA recorded in release ledger                                                                |

---

## 4. Customer work

| MR-ID  | Priority | Status   | Finding                                   | Evidence                                                                                        | Source refs                                                                | Recommended action                        | Acceptance criteria                                                       |
| ------ | -------- | -------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------- |
| MR-C01 | P1       | PARTIAL  | Seller CTA unavailable                    | `/en/sell` disabled; no localhost leak (fail-closed); `NEXT_PUBLIC_VENDOR_APP_URL` likely unset | foundation R1; master BL-06; sfq SFQ-07; roadmap BL-06; blueprint BL-P1-05 | Set env on `convergeo-customer`; redeploy | CTA → `https://vendor.vergeo5.com`; no `localhost:3001`; no “unavailable” |
| MR-C02 | P1       | PARTIAL  | Categories/compare entry 404              | `/en/categories`, `/en/compare` 404                                                             | product RB-PS-012                                                          | Wire browse taxonomy + compare entry      | Browse/search/compare entrypoints work                                    |
| MR-C03 | P1       | PARTIAL  | Events discovery UX incomplete            | Missing Where lens; Tonight+Weekend home default; selling-fast badge                            | events BL-009                                                              | Phase-1 events UX slice after supply      | Browse matches agreed Phase-1                                             |
| MR-C04 | P1       | PARTIAL  | PWA service worker 404                    | Manifest 200; `sw.js`/`serwist/sw.js` 404                                                       | blueprint BL-P1-01                                                         | Fix serwist route on customer prod        | SW 200; installability check                                              |
| MR-C05 | P1       | CONFLICT | Launch copy may overclaim stack/logistics | Yango/own-fleet/direct-MoMo language risk                                                       | blueprint BL-P1-06                                                         | Audit copy vs D11/D16                     | No Yango-API/own-fleet/Django/direct-telco claims                         |
| MR-C06 | P2       | PARTIAL  | Calendar route 404                        | `/en/calendar` 404                                                                              | events F027                                                                | Optional Phase-1                          | Route or remove nav claim                                                 |
| MR-C07 | P2       | MISSING  | Wishlist / recently viewed / reorder      | Design affordances; no tables/APIs                                                              | foundation R6                                                              | Scope fence unless docs claim v1          | Explicit OUT or shipped                                                   |

---

## 5. Vendor work

| MR-ID  | Priority | Status        | Finding                         | Evidence                  | Source refs                      | Recommended action                                   | Acceptance criteria                        |
| ------ | -------- | ------------- | ------------------------------- | ------------------------- | -------------------------------- | ---------------------------------------------------- | ------------------------------------------ |
| MR-V01 | P1       | NOT_AUDITABLE | Vendor listing UX / attach <30s | Login-gated; no audit JWT | product F038; blueprint F021–022 | Provide test vendor JWT; audit attach + quick_list   | Five flows timed; E2E tests                |
| MR-V02 | P1       | PARTIAL       | Offline scanner cache missing   | Offline = cannot verify   | events BL-006                    | Cache horizon secrets; queue + `/scan-sync`          | Offline scan then sync; first-scan-wins    |
| MR-V03 | P1       | PARTIAL       | KYC lifecycle unexercised       | kyc_records=0             | roadmap BL-13; blueprint         | Sandbox Applied→Under Review→Approved                | State machine cannot skip; owner-only edit |
| MR-V04 | P1       | MISSING       | Evidence photos for non-new     | No IMEI/VIN/evidence_kind | product RB-PS-007                | Before Class D: evidence slots + reject stock photos | Non-new create rejects missing evidence    |
| MR-V05 | P2       | MISSING       | Vendor staff RBAC               | Single owner model        | foundation R6                    | Post-v1                                              | Multi-user vendors supported               |
| MR-V06 | P2       | MISSING       | Co-organiser invite UX          | Schema absent (MR-S09)    | events BL-008                    | After schema                                         | Door/Manager phone invite works            |

---

## 6. Admin work

| MR-ID  | Priority      | Status        | Finding                                           | Evidence                                   | Source refs                                    | Recommended action                                                  | Acceptance criteria                                          |
| ------ | ------------- | ------------- | ------------------------------------------------- | ------------------------------------------ | ---------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------ |
| MR-A01 | P0→P1         | MISSING       | Admin role management UI                          | No CRUD UI; `user_roles` service-role only | foundation R6; master BL-03; roadmap F034; sfq | Add grant/revoke UI + audit_log **or** document manual ops          | Admin can grant/revoke with audit; least privilege preserved |
| MR-A02 | P0            | CONFLICT      | Two-tier admin (superadmin/moderator) unsupported | CHECK has single `admin`                   | roadmap BL-05                                  | Founder decision: adopt additive roles+RLS **or** supersede roadmap | Decision recorded; if adopted, authz-matrix tests green      |
| MR-A03 | P1            | PARTIAL       | Moderation queue unproven                         | Endpoints exist; queue empty               | product RB-PS-014                              | Staging new_canonical → pending → merge/reject                      | Queue visible; merge idempotent                              |
| MR-A04 | P1            | PARTIAL       | Analytics tiles empty                             | analytics/funnel = 0                       | foundation R4; roadmap BL-15                   | After traffic + wiring                                              | Tiles match aggregates; CSV valid                            |
| MR-A05 | P1            | PARTIAL       | Authenticity report / cancel-rate policy          | No fake-report; auto-suspend not enforced  | product RB-PS-013                              | Report → admin queue; document ≥10% policy                          | Report creates flag; policy documented                       |
| MR-A06 | NOT_AUDITABLE | NOT_AUDITABLE | Admin UI deep audit                               | Cloudflare Access                          | foundation; blueprint                          | Access-approved auditor session                                     | Empty-state vs wireframe documented                          |

---

## 7. Workflow / integration work

| MR-ID  | Priority | Status           | Finding                                    | Evidence                                                                                           | Source refs                                                                                                  | Recommended action                                                    | Acceptance criteria                                              |
| ------ | -------- | ---------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------- |
| MR-W01 | P0       | VERIFIED MISSING | Escrow auto-release n8n absent             | Live n8n: only notification dispatch + payment reconciliation; repo has `release-job` / order-jobs | foundation R3; events BL-001; product RB-PS-003; blueprint BL-P0-01; master BL-04; sfq SFQ-02; roadmap BL-03 | Import/activate with `X-Internal-Token`; dry-run then sandbox release | Active workflow; successful tick; **no double-release** on retry |
| MR-W02 | P0       | VERIFIED MISSING | Ticket issue (+ event-release) n8n absent  | `tickets-issue` / `event-release` / `tickets-release` inactive; tickets=0                          | foundation R3; events BL-001; product RB-PS-005; blueprint BL-P0-02; sfq SFQ-03                              | Activate against `/internal/tickets/issue-tick` (+ event-release)     | Paid ticket issues exactly-once; dynamic QR works                |
| MR-W03 | P1       | MISSING          | Lifecycle automations absent               | Onboarding / abandoned-cart / review-request not live; `abandoned_cart=false`                      | roadmap BL-14; foundation R3                                                                                 | Import + prove each trigger                                           | Each fires once in test                                          |
| MR-W04 | P1       | MISSING          | Backup workflow absent in n8n              | Only `backup-schedule.md`; OCI cron NOT_AUDITABLE                                                  | foundation R3; master BL-08; sfq SFQ-11; roadmap BL-09                                                       | Deploy backup job **or** prove host cron; restore drill               | Dated artifact + successful restore proof                        |
| MR-W05 | P1       | PARTIAL          | Payment reconciliation only cron present   | One of two live workflows                                                                          | foundation                                                                                                   | Keep; prove failure alerting                                          | Recon report on mismatch; actionable log                         |
| MR-W06 | P2       | MISSING          | Embeddings / reservation sweeper / digests | Repo JSON; not live                                                                                | foundation R3                                                                                                | Activate as needed                                                    | Tick success logged                                              |

---

## 8. Security / RLS work

| MR-ID  | Priority | Status  | Finding                                          | Evidence                                                                       | Source refs                                | Recommended action                                        | Acceptance criteria                                          |
| ------ | -------- | ------- | ------------------------------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------ | --------------------------------------------------------- | ------------------------------------------------------------ |
| MR-R01 | P0       | PARTIAL | FORCE RLS false on ticket allocation/price tiers | `ticket_type_instances`, `ticket_type_price_tiers` `relforcerowsecurity=false` | events F051/BL-003; master BL-10           | Investigate privileges; enable FORCE or written exception | Advisor + `relforcerowsecurity=true` **or** signed exception |
| MR-R02 | P2       | PARTIAL | FORCE RLS false on `product_relations`           | Same pattern                                                                   | master BL-10                               | Same as MR-R01                                            | Documented decision                                          |
| MR-R03 | P2       | PARTIAL | Leaked-password protection disabled              | Advisor WARN                                                                   | master BL-10                               | Enable in Auth                                            | Advisor cleared or risk-accepted                             |
| MR-R04 | P0       | PARTIAL | Authz/RBAC provisioning gap                      | 0051 absent; manual grants; Access on admin                                    | foundation R6; sfq SFQ-05                  | Close MR-S02 + MR-A01/A02                                 | Role isolation tests green customer/vendor/admin             |
| MR-R05 | P1       | PARTIAL | CI secret-scan non-blocking                      | `continue-on-error: true` on secret-scan; Lighthouse/i18n advisory             | foundation R7; roadmap BL-10; master BL-09 | Make secret-scan blocking; confirm branch protection      | Merges blocked on secret hit; protection screenshot          |

---

## 9. Test / observability work

| MR-ID  | Priority | Status                  | Finding                          | Evidence                                      | Source refs                                                                | Recommended action                                      | Acceptance criteria                                    |
| ------ | -------- | ----------------------- | -------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| MR-O01 | P1       | VERIFIED MISSING        | No Vergeo5 Sentry projects       | Org has only unrelated projects; DSNs unknown | foundation R4; master BL-05; sfq SFQ-10; blueprint BL-P1-08; roadmap BL-07 | Create projects + wire DSNs (customer/vendor/admin/API) | Test error visible per app; release tags match deploys |
| MR-O02 | P1       | NOT_AUDITABLE           | Uptime monitors                  | UptimeRobot not probed                        | foundation R4                                                              | Configure health monitors                               | Monitors green on `/en/health`, `/healthz`             |
| MR-O03 | P0       | PARTIAL                 | Money-path tests incomplete      | 0 live payments; ledger hook unverified       | MR-B01; roadmap BL-16                                                      | Sandbox MoMo+card + failure scenarios + invariant-check | Critical suite green; no false success state           |
| MR-O04 | P1       | MISSING / NOT_AUDITABLE | Backup + restore proof           | No n8n backup; host cron unknown              | MR-W04                                                                     | Restore drill with evidence                             | RPO documented; restore succeeds                       |
| MR-O05 | P2       | PARTIAL                 | Staging pipeline stub            | `deploy-staging.yml` stub                     | roadmap BL-11                                                              | Real staging parity                                     | Staging UAT journeys pass                              |
| MR-O06 | P2       | PARTIAL                 | Perf/SEO/A11y not freshly probed | Egress-limited in some sessions               | roadmap BL-21                                                              | Lighthouse on customer                                  | Perf≥90 SEO≥95 A11y≥95 (budgets)                       |

---

## 10. Legal / docs / SoT hygiene (non-code but release-gating)

| MR-ID  | Priority | Status        | Finding                                        | Source refs                     | Recommended action                                                                                       | Acceptance criteria                                            |
| ------ | -------- | ------------- | ---------------------------------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| MR-L01 | P0       | NOT_AUDITABLE | Zambian counsel / DPA / NPS Act escrow posture | sfq SFQ-04 (F4)                 | Complete counsel review before real money                                                                | Written sign-off recorded — **never inferred**                 |
| MR-L02 | DOC      | CONFLICT      | Strategy docs claim obsolete stack             | All six audits conflict ledgers | Banner “SUPERSEDED — see `00-decisions.md`” on Master Plan / Blueprint / Roadmap / Product search claims | Engineers cite locked decisions, not TurboScribe/roadmap stack |
| MR-L03 | DOC      | CONFLICT      | Payment provider language (DPO)                | roadmap BL-01                   | Annotate DPO superseded by D11 Lenco                                                                     | Grep clean of DPO as required provider                         |
| MR-L04 | P0       | CONFLICT      | Zamtel collections marketing vs flag           | roadmap BL-04                   | Hide Zamtel at checkout until F9a proven                                                                 | UI matches flag; decision recorded                             |
| MR-L05 | P2       | CONFLICT      | Questionnaire blank; answers in decisions      | sfq SFQ-20                      | Q→D mapping table                                                                                        | 75-row mapping committed                                       |

---

## 11. Deduplication map (audit ID → MR-ID)

| Theme              | Canonical MR             | Also cited as                                                                                                |
| ------------------ | ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Prepaid → ledger   | MR-B01                   | foundation R2; master BL-01; sfq SFQ-01; roadmap BL-02; blueprint BL-P0-03; product RB-PS-003; events BL-002 |
| Escrow release n8n | MR-W01                   | foundation R3; events BL-001; product RB-PS-003; blueprint BL-P0-01; master BL-04; sfq SFQ-02; roadmap BL-03 |
| Tickets issue n8n  | MR-W02                   | foundation R3; events BL-001; product RB-PS-005; blueprint BL-P0-02; sfq SFQ-03; roadmap BL-03               |
| Migration drift    | MR-S01                   | foundation R8; master BL-02; sfq SFQ-06; roadmap BL-08                                                       |
| Role hook / RBAC   | MR-S02 / MR-R04 / MR-A01 | foundation R6; master BL-03; sfq SFQ-05; roadmap BL-05/BL-08                                                 |
| Seller CTA         | MR-C01                   | foundation R1; master BL-06; sfq SFQ-07; roadmap BL-06; blueprint BL-P1-05; product RB-PS-004                |
| Demo catalogue     | MR-D01                   | foundation R5; product RB-PS-004; blueprint BL-P1-02; master BL-07; sfq SFQ-08; roadmap BL-12                |
| Observability      | MR-O01                   | foundation R4; master BL-05; sfq SFQ-10; blueprint BL-P1-08; roadmap BL-07                                   |
| Backups            | MR-W04 / MR-O04          | foundation R3; master BL-08; sfq SFQ-11; roadmap BL-09                                                       |
| FORCE RLS tickets  | MR-R01                   | events BL-003; master BL-10                                                                                  |
| KYC integrity      | MR-D02                   | blueprint BL-P0-05; events F036; roadmap BL-13                                                               |
| Legal counsel      | MR-L01                   | sfq SFQ-04                                                                                                   |
| Meilisearch claims | C-STACK-SEARCH / MR-L02  | events BL-014; product RB-PS-006; master; roadmap                                                            |
| product_class      | MR-S05                   | product RB-PS-001                                                                                            |
| Condition model    | MR-S06                   | product RB-PS-002                                                                                            |

---

## 12. P0 open set (release cannot proceed)

| #   | MR-ID                  | One-line blocker                                               |
| --- | ---------------------- | -------------------------------------------------------------- |
| 1   | MR-B01                 | Prepaid → escrow ledger posting unproven / likely missing      |
| 2   | MR-W01                 | Escrow auto-release workflow not live                          |
| 3   | MR-W02                 | Ticket issuance workflow not live                              |
| 4   | MR-S01                 | DB migration drift vs git tip                                  |
| 5   | MR-R01                 | FORCE RLS exceptions on ticket tier tables (investigate)       |
| 6   | MR-D02                 | KYC tier without records                                       |
| 7   | MR-B03                 | Refund/cancel matrix unproven (events/money)                   |
| 8   | MR-B04                 | Organiser Tier-1 GMV cap not evidenced                         |
| 9   | MR-L01                 | Legal/DPA/NPS counsel sign-off pending                         |
| 10  | MR-L04 / C-PAY-ZAMTEL  | Zamtel collections conflict unresolved                         |
| 11  | MR-A02 / C-ADMIN-ROLES | Admin RBAC two-tier conflict unresolved (investigate)          |
| 12  | MR-O03                 | No VERIFIED sandbox payment proof (includes false-success ban) |

**Scope-conditional P0s** (only if launch claims include them): MR-S05 (`product_class`), MR-S06 (used condition), MR-B02 (72h used escrow), MR-V04 (evidence photos).

---

## 13. Explicit non-actions

1. Do **not** seed 75–100 / 840 vendors or fake GMV to match documents.
2. Do **not** build Django, Meilisearch, Celery, Redis, DPO, or Yango API against superseded docs.
3. Do **not** flip `public_launch=true` until P0 money/trust gates are VERIFIED.
4. Do **not** mark any P0 resolved without VERIFIED sandbox/live evidence per `document-audit-contract.md`.

---

_Related outputs:_ `production-readiness-scorecard.md` · `panel-backlogs.md` · `release-gates.md` · `24-hour-workboard.md`
