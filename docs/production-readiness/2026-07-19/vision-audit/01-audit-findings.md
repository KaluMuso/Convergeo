# Output 1 — Audit Findings (Vision → Code → Live gap table)

**Date:** 2026-07-19 · **Companion:** `00-README.md` (fingerprint), `02-open-questions.md`, `03-waves-and-phases.md`
**Evidence ranks:** live DB/n8n/Vercel (1) → applied migrations/infra (2) → repository (3) → docs (4).

## How to read

- **Severity:** `blocker` = P0, blocks real-money/launch · `major` = P1, blocks launch-week quality · `minor` = P2/hygiene.
- **Current state** encodes the three lenses: **BUILD** (code exists), **DEPLOY** (running live), **VERIFY** (exercised/proven).
- Two gap classes are separated deliberately:
  - **Deployment lag** = *live contradicts repo* (§1). Fix = promote/apply/activate. Rarely code.
  - **Build gap** = *repo contradicts vision* (§7). Fix = write code.
- Rows cite existing MR-/FD-/G-IDs where the 07-18 corpus already tracks the item, so this table **reconciles** rather than duplicates.

---

## §1 — DEPLOYMENT LAG (live ≠ repo) — the dominant near-term gap

> These are not build gaps. The code exists on `master`; it is not running in production. Every row here is closable by an ops promotion/apply/activation with evidence — no feature work.

| # | What | Repo (master `6841b1e`) | Live (2026-07-19) | Gap | Severity | Surface | Ref |
| - | ---- | ----------------------- | ----------------- | --- | -------- | ------- | --- |
| DL-1 | Customer `/categories` fix (#298) + panel/live-beta work | fixed on master; #302 preview builds green | prod on **`cc4a824`** (#296); `/en\|fr\|zh/categories` **HTTP 500** digest `3012388270` | Customer prod not promoted past #296 | **blocker** (route integrity) | Customer | G1, MR-C02, 2026-07-19 postdeploy-check |
| DL-2 | Vendor/admin panel-honesty SHAs | on master | last VERIFIED `8cc1fa0` (07-18); prod SHA not re-confirmed this session | Promote + record vendor/admin prod SHAs; re-probe honesty empty-states | major | Vendor, Admin | G9, G17 |
| DL-3 | DB migrations `0051`,`0053`,`0054`,`0055`,`0056` | present in repo (`0001`–`0056`) | applied only `≤0050` + odd `20260717100303`(=`0052`) | 6 migrations unapplied; role hook, translation_overrides, service reviews/bookable, **KYC integrity `0056`** all absent live | **blocker** | Backend/DB | MR-S01, MR-S11, G0, C-MIG-DRIFT |
| DL-4 | n8n workflows (19 committed JSON) | 19 `active:false` shells → real `/internal/*` routes | **2 active** (dispatch, reconciliation); 17 dormant incl. **release-job, tickets-issue, event-release, order-jobs, backup(no JSON)** | Escrow auto-release & ticket issuance cannot fire; no scheduled backup | **blocker** | Automations | MR-W01, MR-W02, MR-W04, G5 |
| DL-5 | API container | GHCR `ghcr.io/kalumuso/convergeo-api` | healthy behind Caddy; **image SHA NOT_AUDITABLE**; KYC lifecycle routes returned 404 on live host (07-18) | Deployed API may lag master (esp. `0056`/#293 routes); pin + record digest | **blocker** | Backend | MR-B10, G9, R8 |
| DL-6 | Seller CTA env | fail-closed if `NEXT_PUBLIC_VENDOR_APP_URL` unset | CTAs disabled: "Vendor signup temporarily unavailable" (env unset) | Set env + redeploy customer → CTA → `vendor.vergeo5.com` | major | Customer | MR-C01, G10, R1 |
| DL-7 | Sentry projects | init code + DSNs wired in apps/API | **no Vergeo5 Sentry projects** exist | Create projects + set DSNs; fire test events | major | All | MR-O01, G6, R4 |
| DL-8 | Staging plane | `infra/staging/*` + `deploy-staging.yml` committed (stg-01) | **no separable staging stack provisioned** (`deploy-staging.yml` stub) | Provision identifier-distinct staging OR adopt live-beta path (B-7) | major | Ops | MR-O05, S0 |

---

## §2 — FRONTEND · CUSTOMER (`apps/customer`)

Build is near-complete; gaps are deployment + verification, not missing screens. (Every capability below is code-IMPLEMENTED unless stated.)

| Capability | Vision source | Current state | Gap | Severity | Surface |
| ---------- | ------------- | ------------- | --- | -------- | ------- |
| Home / merch-driven discovery | 01-mountains M05; §G merch | BUILD ✓ (admin-merch hero/banner/flash/collections + data-driven fallback) | DEPLOY: demo-only merch; VERIFY: n/a | minor | Customer |
| Product catalog + PDP + **multi-vendor comparison** | D24; M05 | BUILD ✓ (`c/[...slug]`, `p/[slug]` 690L, `compare` reuses comparison 482L) | Deployed on demo catalogue only | minor | Customer |
| Categories browse | M05 | BUILD ✓ | **DEPLOY: 500 in prod (DL-1)** | **blocker** | Customer |
| Unified search (FTS+trgm+vector RRF) | D22; M05 | BUILD ✓ UI + backend | VERIFY: `/search` observed `degraded=true` (embeddings/FTS health) | major | Customer |
| Services / RFQ (post-a-job) | D2; M11 | BUILD ✓ (`services`, `s/[slug]`, `post-job`, `account/jobs`) | VERIFY: 1 demo service, 0 jobs | minor | Customer |
| Events / dynamic-QR ticketing | D2/D29; M10 | BUILD ✓ (ticket-picker, wallet, transfer) | VERIFY: 0 events/tickets; issuance workflow off (DL-4) | major | Customer |
| Supplies / B2B tier pricing (gated) | D2/D28; M05 | BUILD ✓ (tier cards, `use-business-eligibility` gate, `account/business`) | VERIFY: wholesale gating unexercised (0 business_buyers) | minor | Customer |
| Directory + vendor storefront | D2; M05 | BUILD ✓ (`directory`, `v/[slug]` 466L) | Demo vendors only | minor | Customer |
| Cart + checkout (MoMo/card/COD≤K500) | M07 | BUILD ✓ (per-vendor split, landmark+GPS, MoMo pending-poll, Lenco card page) | **VERIFY: 0 checkouts; false-success E2E not run** | **blocker** | Customer |
| Escrow trust UX ("paid→held→released") | D14; M08 | BUILD ✓ tracker | VERIFY: wired to statuses but 0 orders; must never invent held/released | major | Customer |
| Order tracking + returns + disputes | M09 | BUILD ✓ (`orders/[id]`, dispute, return, pickup QR/PIN) | VERIFY: 0 orders | major | Customer |
| Reviews (verified-purchase) | D-G; M15 | BUILD ✓ (PDP read, write from order/job completion) | VERIFY: 0 reviews; DB enforces verified-purchase | minor | Customer |
| Ask Vergeo AI (RAG, quotas) | D23; M06 | BUILD ✓ (`ask` → `services/ask`, quota + `$`-kill-switch server-side) | VERIFY: grounding/quota unexercised live | minor | Customer |
| PWA / offline | D19; M16 | BUILD ✓ (serwist SW, offline page, install prompt) | DEPLOY: live SW must be re-probed after promotion | major | Customer |
| Account (addresses, prefs, **DPA export/delete**) | M04; M15 | BUILD ✓ (`account/privacy` 295L) | — | minor | Customer |
| Shoppable short-video feed ("Vergeo Clips") | M17 | **ABSENT** (no route/component) | Build gap — but **post-launch v2 by design** (do not dispatch pre-launch) | minor (deferred) | Customer |

---

## §3 — FRONTEND · VENDOR (`apps/vendor`) — whole app role-gated

| Capability | Vision source | Current state | Gap | Severity | Surface |
| ---------- | ------------- | ------------- | --- | -------- | ------- |
| Onboarding + tiered KYC (T1/T2) | D9; M12 | BUILD ✓ (onboarding-flow 453L, doc-capture camera, kyc-integrity client) | VERIFY: 0 kyc_records; `0056` unapplied live (DL-3) | **blocker** | Vendor |
| Listing CRUD + **CSV bulk import** + ≤8 images | M12; product-gap R2 | BUILD ✓ (image-manager 499L, `import`) | Demo listings only | minor | Vendor |
| Services CRUD | M11 | BUILD ✓ | — | minor | Vendor |
| Events organiser (CRUD, ticket types, offline scanner) | M10 | BUILD ✓ (event-form 354L, roster, `scan` offline SW) | Offline scan cache to prove (MR-V03) | major | Vendor |
| Orders / fulfilment (guarded transitions) | M09/M12 | BUILD ✓ (order-card 820L, action-bar 490L) | VERIFY: 0 orders | major | Vendor |
| RFQ responses (contact-stripped) | M11 | BUILD ✓ (`jobs`, quotes) | — | minor | Vendor |
| Payouts + statements | D5; M12 | BUILD ✓ (payouts-view, method-form) | VERIFY: 0 payouts; live payout delivery F9b-gated | major | Vendor |
| Analytics (ledger-backed) | M12 | BUILD ✓ (empty-honest per #291) | VERIFY: 0 data (no traffic) | minor | Vendor |
| Returns / reviews / disputes queues | M09/M15 | BUILD ✓ | VERIFY: empty | minor | Vendor |
| Vendor storefront = directory entry / pitch page | D10; M12 | BUILD ✓ | Customer badge must align to auditable KYC (MR-C10) | major | Vendor |
| Vendor staff / multi-user RBAC | — | **ABSENT** | Build gap — **OUT of v1 by decision** (FD-10, MR-V06) | minor (out) | Vendor |

---

## §4 — FRONTEND · ADMIN (`apps/admin`) — hardened origin (Cloudflare Access)

| Capability | Vision source | Current state | Gap | Severity | Surface |
| ---------- | ------------- | ------------- | --- | -------- | ------- |
| CF Access + `admin` RBAC | D20; M13 | BUILD ✓ (`verifyCfAccessAssertion` RS256, fail-closed) | VERIFY: deep UI NOT_AUDITABLE (Access-gated, MR-A07) | major | Admin |
| Dashboard tiles (GMV/orders/payouts/recon/AI/funnel) | M13 | BUILD ✓ (`dashboard-truth.ts`, empty-honest) | VERIFY: 0 aggregates | minor | Admin |
| KYC review (doc viewer, MoMo name-match, decisions) | M13 | BUILD ✓ (DecisionPanel 287L) | VERIFY: needs `0056` + staging drill (DL-3, S5) | **blocker** | Admin |
| Moderation (flags + duplicate-product merge) | M13 | BUILD ✓ (DuplicateQueue, MergeConfirm) | VERIFY: empty | minor | Admin |
| Merchandising (hero/banner/collection, admin-swappable) | §G; M13 | BUILD ✓ (MerchBoard 228L, SlotEditor 305L) → drives customer home | — | minor | Admin |
| Disputes console → refund actions | M13 | BUILD ✓ | VERIFY: 0 disputes | major | Admin |
| Reconciliation | M08/M13 | BUILD ✓ **tile only**; no standalone ledger workbench | Build gap (minor): dashboard tile vs full workbench | minor | Admin |
| Config editors (flags/platform/categories/commissions/delivery) | M13 | BUILD ✓ (guarded diff writes) | — | minor | Admin |
| Translations tool | M13/M14 | BUILD ✓ (TranslatorView 462L) — enables vernacular rollout | Unused (bem/nya still stubs) | major | Admin |
| **Generic user/role management UI** | roadmap superadmin/moderator | **ABSENT** (vendor/business/KYC-centric only); `user_roles` service-role-only | Build gap: no grant/revoke UI — **gated on FD-02 RBAC decision** | major | Admin |

---

## §5 — BACKEND (FastAPI + Supabase + payments + ZRA + notifications + security)

Backend is production-grade (88 routers / 274 endpoints; 71 tables all RLS-enabled; ~130 test files). Gaps are verification, rollout, and small hygiene — **not** missing implementation.

| Capability | Vision source | Current state | Gap | Severity | Surface |
| ---------- | ------------- | ------------- | --- | -------- | ------- |
| Prepaid MoMo/card → escrow ledger | D5/D11; M08; MR-B01 | BUILD ✓ (`settle_prepaid_collection`→`CHARGE_RECEIVED`; #274) | **VERIFY: 0 payments/ledger; not STAGING_VERIFIED** | **blocker** | Backend |
| Release accounting (commission before vendor net; escrow→0) | M08; MR-B01b | BUILD ✓ (`compute_release_amounts`, capture-before-release; #288/#294) | **VERIFY: staging drill not run** | **blocker** | Backend |
| Integer-ngwee / Decimal-only money | conv#1; D5 | BUILD ✓ (float rejected in `money.py`; no float-on-money confirmed) | — | — | Backend |
| Idempotent Lenco webhooks | conv#5; M08 | BUILD ✓ (HMAC on raw body → 401 not 500; `webhook_events` unique + `23505` dedupe; ref salt) | VERIFY: replay not exercised live | major | Backend |
| Double-entry ledger (sum=0) | D14; M08 | BUILD ✓ (`enforce_ledger_transaction_balance` deferred trigger) | VERIFY: 0 txns | major | Backend |
| Refund = ledger-orchestrated payout | D17; M09 | BUILD ✓ (`rfd-*` payout, stable idempotency key) | VERIFY: F9b live-delivery gated; refund/cancel matrix unproven (MR-B03) | **blocker** | Backend |
| Escrow release rules (48h delivered / 7d shipped / dispute hold) | D14; M09 | BUILD ✓ (`escrow/release.py` idempotent) | DEPLOY: release **workflow** off (DL-4); VERIFY unproven | **blocker** | Backend/Automations |
| Organiser Tier-1 GMV fraud cap (~K20k) | events BL-004 | Evidence not located (MR-B04) | Verify/implement cap before paid events | **blocker** (events) | Backend |
| ZRA sequential invoicing + VAT-off + VSDC seam | D13; M15 | BUILD ✓ numbering (`next_invoice_no` gapless, row-locked), RCP/TAX series, PDF; **VSDC = deliberate stub**, VAT flag off | Build (intentional): no live ZRA fiscalisation until VAT registration | minor (seam) | Backend |
| Auth (phone OTP/email/Google) + role claims | M04 | BUILD ✓; `getRoles` authoritative from `user_roles` (never JWT-alone for admin) | DEPLOY: role hook `0051` unapplied → manual grants (FD-03) | **blocker** | Backend |
| RLS on every table + guarded state machines | conv#3/#4 | BUILD ✓ (71/71 RLS; guard fns; matrix tests vs real PG) | **FORCE RLS false** on `ticket_type_instances`,`ticket_type_price_tiers`,`product_relations` (FD-07/MR-R01) | **blocker** | Backend |
| RLS test-matrix completeness | conv#9 | BUILD ✓ mostly | Hygiene: `event_categories`,`product_relations`,`service_reviews` policied but absent from RLS test registry | minor | Backend |
| Admin audit on every mutation | conv#4; M13 | BUILD ✓ (`AdminAuditedRoute`) | Hygiene: duplicate `/refunds/execute` mount skips audit-completeness wrapper (still admin-gated) | minor | Backend |
| Notifications outbox (WA→SMS→email, dedupe, quiet hours) | D15; M14 | BUILD ✓ (Cloud API only, WAHA-clean) | VERIFY: 0 outbox sends proven | major | Backend |
| Search health | D22; MR-B07 | BUILD ✓ | VERIFY: `degraded=true` — diagnose embeddings/FTS | major | Backend |
| Admin RBAC tier | roadmap | Single `admin` CHECK live (concept wanted 2-tier) | Decision FD-02 (do not invent roles) | major | Backend |

---

## §6 — AUTOMATIONS (`infra/n8n/*.json` → API `/internal/*` ticks)

All 19 workflows are thin `scheduleTrigger → httpRequest(POST X-Internal-Token)` shells; **all backing routes exist**. The gap is deployment + hardening, not authoring — except the backup workflow which has **no JSON**.

| Workflow | Vision role | Current state | Gap | Severity | Ref |
| -------- | ----------- | ------------- | --- | -------- | --- |
| release-job / order-jobs | Escrow auto-release | committed, **not live** | Activate + prove idempotent release; fix order-jobs confirm-before-release fan-out ordering | **blocker** | MR-W01 |
| tickets-issue / tickets-release / event-release | Exactly-once ticket issuance + event escrow | committed, **not live** | Activate; prove exactly-once (60s tick, shared token) | **blocker** | MR-W02 |
| payment-sweeper | Reconcile in-flight Lenco status | **live** (recon crons) | Prove failure alerting | major | MR-W05 |
| notification-dispatch | Drain outbox | **live** | Prove send in sandbox | major | MR-W03 |
| reconciliation | Poll + daily report | **live**; **daily 05:00 run undocumented** in registry | Doc the hidden `0 5 * * *` daily-report trigger | minor | — |
| reservation-sweeper / low-stock / kyc-nudge / payout-failure / review-request / funnel-abandon / abandoned-cart / analytics-retention / embeddings-cron / admin-digest | Lifecycle/ops | committed, **not live** (abandoned-cart/funnel flag-gated OFF) | Activate as backend lands; prove each ticks once | major | MR-W03/W06 |
| **DB backup** | Nightly dump + restore proof | **no JSON** (only `backup-schedule.md` spec) | **Author + deploy** backup workflow; run restore drill | **blocker** | MR-W04, G7 |
| uptime-alert | UptimeRobot → WhatsApp founder page | committed, **not live**; **webhook unauthenticated** | Add shared-secret/HMAC on `/webhook/uptime-alert` before activating | major | — |
| Cross-cutting | Money-workflow safety | idempotency lives in API only; **no error-alerting on money workflows** | Add error-workflow/retry alerting on release/recon/payout ticks | major | MR-W (D-risks) |

---

## §7 — BUILD GAPS (repo ≠ vision) — the genuinely unwritten/partial features

The short list. Everything else in the vision is code-complete.

| # | Vision capability | Source | State | Gap | Severity |
| - | ----------------- | ------ | ----- | --- | -------- |
| BG-1 | Bemba / Nyanja UI translations | D27; i18n-audit | routable, **stub** (notifications.json only); EN fallback everywhere else | Fill `bem`/`nya` 16 namespaces via admin TranslatorView | major (P1/P2 per D27) |
| BG-2 | Admin generic user/role management UI | roadmap | ABSENT; `user_roles` service-role-only | Build grant/revoke UI **or** document manual-ops path — gated on FD-02 | major |
| BG-3 | Organiser Tier-1 GMV fraud cap | events BL-004 | not evidenced | Implement/verify cap | blocker (events only) |
| BG-4 | Offline scanner cache + scan-sync | events BL-006 | partial | Cache tickets for offline verify; first-scan-wins | major (events) |
| BG-5 | DB backup workflow (JSON) | ops | spec only, no JSON | Author workflow | blocker |
| BG-6 | Shoppable video feed "Vergeo Clips" | M17 | ABSENT | **Deferred post-launch by design** — do not build pre-launch | minor (deferred) |
| BG-7 | Product model breadth: `product_class` A–E, used-goods evidence, 5 pricing modes | product strategy | narrow (`new\|refurbished`, single price + supplies tiers) | **OUT by decision** unless FD-06 elevates | minor (out) |
| BG-8 | Wishlist / recently-viewed / reorder / saved-search | designs | affordance-only | **OUT of v1 by decision** (MR-C07, R6) | minor (out) |
| BG-9 | Event `multi_day` type | events strategy | 4 types live | Decision FD-05 (accept `standard`+`ends_at`) | minor |

---

## §8 — CROSS-CUTTING (ops / trust / compliance / perf)

| # | Area | Vision | Current state | Gap | Severity | Ref |
| - | ---- | ------ | ------------- | --- | -------- | --- |
| X-1 | Observability | Sentry + uptime | no Vergeo5 Sentry; uptime NOT_AUDITABLE | Create projects/DSNs; monitors | major | MR-O01/O02, G6 |
| X-2 | Backup / restore | RPO + drill | no backup workflow; restore NOT_AUDITABLE | Backup artifact + restore drill | **blocker** | MR-W04/O04, G7 |
| X-3 | CI security gates | blocking on master | `secret-scan` `continue-on-error:true`; Lighthouse advisory | Make blocking; confirm branch protection | major | MR-R05, G8, R7 |
| X-4 | Legal (DPA / NPS-Act escrow) | written counsel | NOT_AUDITABLE | Engage counsel; written posture | **blocker** | MR-L01, FD-08, G13 |
| X-5 | Demo catalogue posture | D25 exclude/label | 134 demo listings public-eligible | Exclude from public search (FD-04) | major | MR-D01, G11 |
| X-6 | Perf/SEO/A11y budgets | conv#7; M16 | Lighthouse advisory, not freshly probed | Re-probe; enforce budgets | minor | MR-O06, G19 |
| X-7 | Auth leaked-password protection | advisor | disabled | Enable in Supabase Auth | minor | MR-R03, G20 |
| X-8 | Doc SoT banners (superseded stack/DPO/Zamtel) | hygiene | pending | Banner Django/Meilisearch/DPO/Yango docs | minor | MR-L02/L03/L04 |

### §8.1 — Environment reality (from Google Drive infra artifacts + live probes)

> Nothing in Drive post-dates 2026-07-19, so the **repo remains source-of-truth for the marketplace plan** — no newer strategy supersedes it. But Drive reveals a live-infra reality the repo `docs/` does not describe. These are cross-cutting risks; the decisions they imply are in Output 2 (NB-7…NB-10).

| # | Area | Repo/vision assumption | Live/Drive reality | Gap | Severity | Ref |
| - | ---- | ---------------------- | ------------------ | --- | -------- | --- |
| X-9 | Host capacity/isolation | one OCI Always-Free VM (api/caddy/n8n), $50/mo ceiling | same `n8n-vnic-vergeo5` VM also hosts **WAHA** + **ZedApply `zedcv-backend`** (separate product) | noisy-neighbor + resource-contention + blast-radius risk not in capacity plan; confirm Vergeo5 isolation | major | Drive C-2 → NB-8 |
| X-10 | WhatsApp compliance | official Cloud API only; **WAHA forbidden** even in dev (D15) | Vergeo5 app code **WAHA-clean ✓**, but shared brand/VM runs `waha.vergeo.company` (agency/ZedApply growth-messaging?) | WhatsApp **ban risk on the shared number/brand** would contaminate Vergeo5 official notifications; confirm number/sender separation | major | Drive C-1 → NB-7 |
| X-11 | Brand / domain / account | `vergeo5.com`, account `convergeozambia@gmail.com` | live automation uses `vergeo.company`; planning owned by `prosper2kaluba@gmail.com`; "Convergeo" also = an automation **agency** brand | authoritative-decision location + brand overload ambiguous; not a marketplace-scope contradiction | minor | Drive C-3, B-3 → NB-9 |
| X-12 | Growth data governance | Zambia DPA, consent-based | Drive holds 2026-07-01 WhatsApp group + `zambian_numbers.csv` harvest (un-mirrored) | cold-outreach lists raise DPA/consent + WhatsApp-ToS exposure if used for launch nudges | minor | Drive B-2 → NB-10 |

---

## §9 — Severity rollup (this audit)

- **Blockers (real-money/launch):** DL-1, DL-3, DL-4, DL-5; checkout+money verify (§5 prepaid/release/refund/escrow), KYC `0056` rollout (§3/§4), FORCE RLS (§5), role hook (§5), automations release/tickets/backup (§6), legal (X-4), backup/restore (X-2), organiser GMV cap (BG-3).
- **Majors (launch-week):** DL-2/6/7/8, search degraded, escrow trust UX proof, Sentry, demo posture, CI gates, Bemba/Nyanja, admin user-mgmt/RBAC, vendor storefront badge alignment, notification send proof, offline scanner cache.
- **Minors/hygiene/out-by-decision:** RLS test registry, refund mount, reconciliation workbench, `multi_day`, perf re-probe, leaked-password, SoT banners, video feed (deferred), product-model breadth (out), wishlist family (out).

**Net:** the launch-critical set is overwhelmingly **DEPLOY + VERIFY + OPS + DECISIONS**, not BUILD. This shapes Output 3: promote and prove first, build last.
