# Reconciliation Matrix — Convergeo Strategic Master Plan v1.0 vs Production

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY · **Contract:** `../../foundation/document-audit-contract.md`
**Document:** Convergeo Strategic Master Plan v1.0 (April 2026, CONFIDENTIAL) · **Slug:** `strategic-master-plan-v1`
**Baseline:** `docs/production-readiness/2026-07-18/foundation/*` (same-day live probes) + repo HEAD `0b88723`.

### How to read status here
Per the contract's source-of-truth hierarchy (live > migrations/infra > repo > docs). This session could **not** independently re-probe live API/DB (`api.vergeo5.com` and `mcp.supabase.com` both returned proxy egress **403**), so **live/DB facts are inherited from the same-day foundation probes and attributed as such**; **repo-only** facts are held to **PARTIAL** for production behaviour. `LedgerTemplate`/adapter/enum existence is code evidence (PARTIAL for runtime).

### Supersession key (essential context)
`docs/plan/00-decisions.md` (LOCKED **2026-07-06**) deliberately **supersedes** this April-2026 plan's tech-stack decisions (D18–D24) and cites it directly ("per Master Plan L2/Q25"). Rows tagged **[superseded-intentional]** are conflicts by evolution, not defects — their remediation is *document reconciliation*, not a production change. Rows tagged **[gap]** are genuine production shortfalls.

---

## A. Technical architecture (Section 4 / Q9–Q18) — mostly intentional supersession

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q9 p.3 / Sec4 | Backend = Django REST + DRF | requirements | `services/api` | backend-framework | Repo: `pyproject` "Vergeo5 FastAPI backend", `fastapi>=0.115`, 181 fastapi imports, **0 django**; foundation live `server: uvicorn`, OpenAPI "Vergeo5 API" | **CONFLICT** [superseded-intentional] | Framework changed Django→FastAPI | Low if intended — but Master Plan is a **stale implementation reference** | Mark Master Plan §4/Q9 superseded by D18; version-stamp the plan |
| Q11 p.3 / Sec4 | Backend host = Railway/Render | requirements | hosting | backend-hosting | Foundation: API behind **Caddy** (`via: 1.1 Caddy`) on OCI/Hetzner VM (D21); `infra/docker-compose.yml` | **CONFLICT** [superseded-intentional] | Railway/Render → OCI Docker Compose | Low; doc stale | Reconcile plan to D21 |
| Sec4 | DB = PostgreSQL 16 + pgvector on Railway | requirements | Supabase Postgres | db-platform | Foundation: Supabase `dpadrlxukcjbewpqympu`, PG 17.x, pgvector | **PARTIAL** [superseded-intentional] | Managed Supabase (not Railway); v17 not v16 | Low | Reconcile plan to D18/D21 |
| Q15 p.3 / Sec4 | Meilisearch = primary search | requirements | search engine | search-engine | Repo: **0 Meilisearch**, 17 FTS/pgvector files, `search_documents`=288 (foundation); D22 "Meilisearch deferred >~20k listings" | **CONFLICT** [superseded-intentional] | Engine = Postgres FTS+pg_trgm+pgvector+RRF | Low; same UX delivered | Reconcile plan to D22 |
| Q17 p.3 / Sec4 | Upstash Redis cache layer | requirements | cache | redis-cache | Repo: **0 redis/upstash**; rate-limit via SlowAPI+Caddy (D18) | **CONFLICT** [superseded-intentional] | Redis dropped | Low; NOT_AUDITABLE whether any prod cache exists | Reconcile plan; confirm no runtime cache dependency |
| Q18 p.3 / Sec4 | Celery + n8n async | requirements | async worker | async-worker | Repo: **0 celery**; FastAPI async + n8n | **CONFLICT** [superseded-intentional] | Celery dropped | Low | Reconcile plan to D18 |
| Q14 p.3 / Sec4 | Supabase Realtime for notifications | requirements | notification mechanism | realtime-notifications | Repo: WhatsApp Cloud API + SMS(AfricasTalking) + email(Resend) via outbox/dispatcher; 110 whatsapp files; `notifications/adapters/{whatsapp,sms,email}` | **CONFLICT** [superseded-intentional] | Notif transport = WhatsApp-first outbox, not Realtime; real-time in-app center OUT of v1 | Medium — materially different notification architecture | Reconcile plan to D15; confirm order-tracking UX path |
| Q10 p.3 | Next.js SSR for SEO (App Router) | requirements | `apps/customer` | frontend-nextjs | Foundation: Vercel customer app healthy, SSR; D19 Next.js 15 | **VERIFIED** | doc 14+, prod 15 | — | none |
| Q12 p.3 | Shared API + 3 separate frontends | requirements | apps + services/api | monorepo-topology | Foundation: 3 Vercel projects; D20 | **PARTIAL** | 3-app topology matches; API is FastAPI under `services/api` not `/apps/api` Django | Low | Reconcile plan path/framework |
| Q16 p.3 / Sec4 | Cloudinary images | documents-media | Cloudinary + `listing_images` | media-cdn | Foundation: 134 `listing_images` `cloudinary_public_id LIKE 'demo/%'`; D26 | **VERIFIED** | +Supabase private buckets added | — | none |
| Sec4 (CDN) | Cloudflare CDN/DNS | requirements | Cloudflare | cdn | Foundation: `server: cloudflare` on customer HTML | **VERIFIED** | — | — | none |
| Sec4 (frontend state) | Zustand + React Query | requirements | apps/* | frontend-state | Not inventoried in foundation; not re-probed | **NOT_AUDITABLE** | State lib not confirmed | Low | Confirm in a repo/App-shell review if needed |
| Rule1/Contracts p.12 | OpenAPI 3.1 single source of truth | requirements | `openapi.json`, `packages/types` | openapi-contract | Foundation: live OpenAPI present, title "Vergeo5 API" v0.1.0 (not a SHA); `packages/types` generated (D20) | **PARTIAL** | "3.1" + single-source-of-truth not live-verified; version 0.1.0 | Low | Confirm OpenAPI version/type-gen in CI |

## B. Payments, escrow & money (Q19–Q26, T1/T5) — one genuine P0

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q19 p.3 | Both DPO + Lenco (redundancy) | requirements | `services/payments` | payment-gateway | Repo: **70 lenco / 0 DPO**; `payments/lenco/*`, `webhooks_lenco.py`; D11 Lenco-only + abstraction seam | **CONFLICT** [superseded-intentional] | DPO never integrated; single gateway | **P0-raised → P1 residual**: no gateway redundancy the doc mandated → Lenco is a single point of failure | Reconcile plan to D11; track "2nd gateway" as resilience backlog |
| Q20 p.3 (non-neg) | MTN MoMo + Airtel day one | requirements | Lenco MoMo rails; `payments` | momo-rails | D11 "all three MoMo rails + cards + bank"; `payments`=0 live (foundation R2) | **PARTIAL** [gap] | Code present; **no live paid order** | High — MoMo path unproven under real money | Sandbox MoMo E2E before real-money launch |
| Q21 p.3 / T1 | 48-hour settlement; instant later | requirements | escrow release + payout; n8n `release-job` | settlement-window | D5 escrow/48h auto; `LedgerTemplate.PAYOUT_EXECUTED`, `RELEASE_TO_VENDOR`; 0 payouts; n8n release-job **absent on live** (R3) | **PARTIAL** [gap] | Auto-release workflow not live | High — escrow may never auto-release | Import/activate `release-job` in n8n; prove one release tick |
| Q22 p.4 / T5 | Full escrow via ledger (not bank sub-accounts) | requirements | `ledger_*`; `LedgerTemplate` | escrow-ledger | Code VERIFIED: `LedgerTemplate.{CHARGE_RECEIVED,ESCROW_HOLD,…}`, `post_transaction` (37×). Live 0 ledger txns. **R2: prepaid webhook success path may not post CHARGE_RECEIVED/ESCROW_HOLD** | **PARTIAL** [gap] | Prepaid→ledger posting unproven | **P0 — money/escrow integrity** | Trace payment-success→ledger in sandbox; add VERIFIED fixture (see backlog BL-01) |
| Q25 p.4 | COD ≤K500 + pay-at-pickup | requirements | COD policy; `COD_COLLECTED` | cod-cap | D12 COD ≤K500 (cites Master Plan Q25); `LedgerTemplate.COD_COLLECTED`; CLAUDE.md | **VERIFIED** | D12/F8 asks founder to confirm cap direction | — | Founder confirm F8 |
| Q24 p.4 | VAT-ready architecture, Turnover Tax launch | requirements | `invoices`/`invoice_counters` | vat-architecture | D13 ZRA-ready sequential invoicing, per-category VAT flag off; tables exist (0 rows, foundation) | **PARTIAL** | VAT flag off at launch (intended) | Low | none (VSDC seam tracked) |
| Q23 p.4 | Display any currency, settle ZMW | requirements | money (ngwee) | currency-display | CLAUDE.md integer ngwee + `formatK()`, ZMW settle | **PARTIAL** | Multi-currency display via FX API not evidenced | Low | Confirm if multi-currency display is in scope |
| Q26 p.4 | Partner with licensed fintech long-term | requirements | — | fintech-partner | Lenco aggregator (D11) consistent | **NOT_AUDITABLE** | strategy | — | none |

## C. Business model & revenue (Q1–Q8, Layers 1–4)

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q1 p.2 | Commission + optional subscriptions | requirements | `commission_rates`; `feature_flags.paid_tiers` | revenue-model | commission_rates 9 rows; paid_tiers=**false** (foundation) | **PARTIAL** | Subscription billing deferred (D3) | Low (by decision) | none; track tier module |
| Q2 / Layer1 p.9 | Category commissions 5/8/10/12/5% | requirements | `commission_rates` (bps) | commission-by-category | 9 rows (foundation) consistent with D4 superset (adds supplies 3%, groceries 5%, default 8%, free-events 0%). **Exact live values not readable this session** | **PARTIAL** | Live rate values NOT_AUDITABLE (Supabase 403) | Money-config — must be right | Read `commission_rates` values when Supabase access restored (backlog BL-08) |
| Q3 p.2 | Free listings first (supply-first) | requirements | paid_tiers flag | free-listing-launch | paid_tiers=false; D3 "Free-only at launch" | **VERIFIED** | — | — | none |
| Q4 / Layer2 p.9 | 4 tiers Free/Bronze99/Silver249/Gold499 (+Platinum) | requirements | subscription module | vendor-tiers | **0 subscription/tier code**; D3 defers billing (Gold top; Platinum future); Free cap **30** (D3) vs **20** (doc) | **MISSING** [by-decision + doc-conflict] | Deferred; internal numeric conflicts (Platinum vs Gold-top; 20 vs 30 listings) | Low but ambiguous | Reconcile tier numbers doc↔D3; keep billing OUT per D3 |
| Q6 p.2 | Free delivery over ~K200 | requirements | `delivery_zones` | free-delivery-threshold | D16 free ≥K200 Lusaka; delivery_zones=3 | **PARTIAL** | Live threshold value NOT_AUDITABLE | Low | verify config value when DB access restored |
| Q7 p.2 | ≤$2K bootstrap budget | requirements | D6 | budget | D6 ≤$50/mo | **VERIFIED** | doc break-even cites $62/mo (minor internal) | — | none |
| Break-even p.10 | ~$62/mo infra; ~15mo runway | requirements | infra spend | cost-model | D6 tighter ($50); actual spend not readable | **PARTIAL** | Actual infra cost NOT_AUDITABLE | Low | none |
| Layer4 p.10 | Promoted listings (future) | requirements | — | promoted-listings | Scope fence OUT of v1 | **MISSING** [by-decision] | — | — | none |

## D. Customer & vendor experience (Q27–Q42, insight)

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q27 p.4 | EN + Bemba + Nyanja **at launch** | requirements | next-intl locales | launch-languages | D27 launch **English**, expand Bemba/Nyanja→French; next-intl scaffolding present | **CONFLICT** | Bemba/Nyanja post-launch, not at-launch | Low | Reconcile launch-language claim to D27 |
| Q29 p.4 | Phone OTP(Africa's Talking)+email+Google/Facebook | role-access | Supabase Auth providers | auth-methods | Foundation: Supabase Auth phone OTP/email/Google; Facebook not evidenced; OTP via Supabase not AT-direct | **PARTIAL** | Facebook NOT_AUDITABLE; OTP transport differs | Low | Confirm enabled providers in Supabase Auth |
| Q31 p.4 | Filters + autocomplete + pgvector | requirements | hybrid search | search-features | D22; search_documents 288; 17 FTS files | **VERIFIED** | — | — | none |
| Q32 p.4 | Verified, **multi-dimensional**, photo/video reviews | requirements | `reviews`/`review_aggregates` | reviews | D-scope: verified-purchase + text + photos; **multi-dim OUT of v1**; reviews empty | **PARTIAL** [partial-conflict] | Multi-dimensional deferred; video NOT_AUDITABLE | Low | Reconcile "multi-dimensional" to scope fence |
| Q33 p.4 | QR + PIN pickup | requirements | `services/pickup`, `pickup_verify`, mig 0017 | qr-pin-pickup | Code present; 0 orders live | **PARTIAL** | Runtime unproven | Medium (fulfilment) | Prove pickup verify in sandbox order |
| Q34 p.4 | PWA-first | requirements | serwist PWA | pwa | D19; foundation PWA installable | **VERIFIED** | — | — | none |
| Q36 p.5 | Tiered KYC (NRC/PACRA) | role-access | `kyc_records`; D9 | kyc-tiers | D9 3-tier + badge; kyc_records 0 rows | **PARTIAL** | Runtime unproven | Medium | Prove KYC flow pre-launch |
| Q40 p.5 | Contact-strip pre-purchase | requirements | `moderation/contact_strip.py` | contact-strip | Code present | **PARTIAL** | Runtime enforcement not re-probed | Medium (disintermediation) | Spot-check enforcement |
| Q41 p.5 | Comparison view (N vendors) + nearest | requirements | canonical products + listings | comparison-view | D24 canonical model; products 150 / listings 134 | **PARTIAL** | Geo-nearest sort not re-verified | Low | Confirm comparison UI live |
| Insight/Data model p.5,11 | Canonical Product + VendorListing shared images | master-records | `products`+`vendor_listings`+`listing_images` | canonical-data-model | D24 Option A locked = exact match; foundation aggregates 150/134/134 | **VERIFIED** | — | — | none (strong alignment) |
| Q35/Q38/Q39/Q42 | Tier onboarding / progressive analytics / manual+CSV+API / tiered profiles | requirements | vendor portal + tiers | vendor-tiering | CSV import in v1 (D10); tier-gated analytics/profiles/API deferred with subscriptions | **PARTIAL / MISSING** | Advanced tier features deferred (D3) | Low (by decision) | Track with tier module |

## E. Logistics & delivery (Q43–Q48)

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q43 p.5 | Yango + Zampost/courier via aggregation | requirements | dispatch | courier-integration | `admin_orders.py` `Courier=Literal['yango','indrive','other']` + admin `DispatchPanel`; **Zampost 0**; D16 no courier API v1 | **CONFLICT** [superseded-intentional] | Manual dispatch labels, not APIs | Low | Reconcile plan to D16 |
| Q44 p.5 / T4 | All cities; deliver Lusaka only; pickup all | requirements | `delivery_zones`; pickup | delivery-coverage | D16 Lusaka delivery only, nationwide pickup, Copperbelt OUT; delivery_zones=3 | **PARTIAL** | Matches T4 resolution | Low | none |
| Q47 p.6 | Courier tracking webhooks | requirements | tracking | courier-tracking | No courier API v1 (D16); manual status via WhatsApp/SMS | **CONFLICT** [superseded-intentional] | — | Low | Reconcile plan to D16 |
| Q48 p.6 | No returns MVP; refund-only faulty | requirements | `returns`/`refunds`; D17 | returns-policy | D17 two lanes (faulty + change-of-mind); tables exist empty | **CONFLICT** [prod-ahead] | Production adds change-of-mind lane | Low (positive) | Reconcile plan (prod broader) |

## F. Events, services, discovery (Q49–Q53)

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q50 p.6 | Dynamic-QR tickets (60s) | requirements | `tickets/qr.py`; n8n `tickets-issue` | dynamic-qr | Code VERIFIED: HMAC+60 (D2 60s HMAC+PIN); **n8n ticket-issue workflow absent on live** (R3) | **PARTIAL** [gap] | Paid tickets may never issue | High (events money path) | Import/activate `tickets-issue`; prove one issue tick |
| Q51 p.6 | Quote-request services | requirements | `services/rfq`, `job_quotes` | rfq-services | rfq/broadcast + jobs/job_quotes; 1 service row | **PARTIAL** | In v1 (doc said Phase 2) | Low (positive) | none |
| Q53 p.6 | Directory as nav tab | requirements | directory tab | directory-tab | D2 directory (profiles=entries) | **PARTIAL** | Live UI not re-probed | Low | Confirm directory tab live |
| Q52 p.6 | City guides + AI later | requirements | — | city-guides | Scope fence OUT of v1 | **MISSING** [by-decision] | — | — | none |
| Q49 p.6 | All event types | requirements | `events`/`event_categories` | event-types | D8 6 categories; events tables 0 rows | **PARTIAL** | Runtime empty | Low | none |

## G. Marketing, growth, legal, ops, AI (Q54–Q75, methodology, sprint, KPIs)

| Source ref | Extracted fact | Data class | Expected platform location | Matching key | Production evidence | Status | Gap | Impact | Recommended action |
| ---------- | -------------- | ---------- | -------------------------- | ------------ | ------------------- | ------ | --- | ------ | ------------------ |
| Q54 p.6 | Invite-only beta then public | requirements | `beta_invites`; `public_launch` | launch-gate | public_launch=false; beta_invites table (foundation) | **VERIFIED** | — | — | none |
| Q55 p.6 | Referral K20 credit | requirements | — | referral | OUT of v1 (scope fence; R6) | **MISSING** [by-decision] | — | — | Confirm not v1 |
| Q57 p.6 / Risk#1 | 200–500 real vendors; onboard 75+ before launch | master-records | `vendors`/`vendor_listings` | vendor-target / cold-start | Live = **demo**: 3 demo vendors, 134 listings, **134 demo/ images**, 0 real orders (R5); seller CTA broken (R1) | **CONFLICT** [gap] | Demo catalogue presented as marketplace; real vendors blocked by CTA | P1 — trust/SEO + acquisition | Fix seller CTA env; label/replace demo; keep public_launch gate |
| Q61 p.6 / T2 | GDPR-level compliance | role-access | `audit_log`; RLS; consent; encryption | data-protection | CLAUDE.md Zambia DPA; audit_log + RLS; **advisor: leaked-password-protection DISABLED** (foundation) | **PARTIAL** [gap] | Auth hygiene gap vs claim; legal cert deferred (T2) | P2 (security hygiene) | Enable Supabase leaked-password protection; DPIA-lite doc |
| Q63 p.7 | Solo founder + AI | requirements | CLAUDE.md | operating-model | Matches CLAUDE.md | **VERIFIED** | — | — | none |
| Q64 p.7 | WhatsApp + AI chatbot support | requirements | WhatsApp; support | support-channels | WhatsApp present (110 files); AI **support** chatbot not evidenced | **PARTIAL** | Support chatbot NOT_AUDITABLE | Low | Confirm scope |
| Q65 p.7 / KPIs | GMV/CAC/LTV/NPS instrumentation | operational | `analytics_events`/`funnel_events`; dashboard | kpi-instrumentation | Tables exist, **0 rows**; admin dashboard UI exists; no Vergeo5 Sentry (R4) | **PARTIAL** [gap] | Analytics unfed; blind prod | P1 (observability) | Create Sentry projects + DSNs; wire analytics; UptimeRobot |
| Q66 p.7 | n8n order automation first | requirements | n8n workflows | n8n-order-automation | Live n8n = **2 active** (dispatch + reconciliation); order-jobs/release/tickets/event-release **absent on live** though in repo (18 json) (R3) | **PARTIAL** [gap] | Most workflows not live | P1 (ops/trust) | Import/activate registry workflows; prove one tick each |
| Q67/Q69/Q70 p.7-8 | AI descriptions/fraud/pricing; recommendations; AR | requirements | AI services | ai-roadmap | D23 Ask Vergeo RAG (ask_* empty); rest Phase 3 / OUT of v1 | **MISSING / PARTIAL** [by-decision] | Deferred by phase | Low | none |
| Rule6 p.12 / W1 | CI gatekeeper blocking | requirements | `.github/workflows` | ci-gates | R7: secret-scan/i18n/Lighthouse `continue-on-error`; docs↔YAML deps-audit conflict; branch-protection NOT_AUDITABLE | **PARTIAL** [gap] | Some gates non-blocking | P2 (regression/secret risk) | Remove continue-on-error from secret-scan; align docs; confirm branch protection |
| Rule4 p.12 | AI_CONTEXT.md persistent memory | requirements | repo memory | context-file | Uses CLAUDE.md + docs/plan/00-status.md (no AI_CONTEXT.md) | **CONFLICT** [cosmetic] | Renamed; equivalent exists | Trivial | Reconcile name in plan |
| Sec6/7/10 | 4 phases + 60-day sprint; "ship in 60 days" | requirements | docs/plan | delivery-plan | Superseded by D7 + 16-mountains/waves | **CONFLICT** [superseded-intentional] | Re-planned methodology | Low | Reconcile plan to mountains/waves |
| W8 p.15 | Sentry + Better Uptime monitoring | requirements | Sentry/UptimeRobot | observability | No Vergeo5 Sentry projects (R4); UptimeRobot NOT_AUDITABLE | **MISSING** [gap] | Production largely blind | P1 | Create Sentry + monitors (see BL-05) |
| W1/Sec10 | DB schema + all migrations, CI-validated | role-access | `schema_migrations` | migration-parity | Live applied ≤0050 + odd 0052; **0051/0053/0054/0055 NOT applied** (foundation) | **CONFLICT** [gap] | Live DB ≠ git tip | **P0** — runtime ≠ repo assumptions | Reconcile/apply migrations with care; record release ledger (BL-02) |
| Phase1 admin / Q61 | Admin manages users/roles | role-access | `user_roles`; role hook; admin UI | rbac | user_roles RLS-on/**0 client policies** (service-role); mig 0051 role hook **not applied** → manual role provisioning; no admin users CRUD UI (R6) | **PARTIAL** [gap] | Manual role grants; hook dormant | **P0-raised → P1** (identity/RBAC; investigated: by-design + manual works) | Apply 0051 + enable Auth hook when ready; add admin role UI |
| Q60 p.6 / W1 | PACRA-registered company | requirements | legal entity | pacra-registration | D1 entity exists; annual returns lapsed (F2); TPIN pending | **PARTIAL** [gap, non-code] | Compliance action pending | P2 (payments/tax gate) | Founder F2 (returns + TPIN) |
| KPIs p.15-16 | Month-1/6/12 targets, >90% pay success, >80% completion | operational | orders/payments live | kpi-targets | 0 orders/payments; analytics empty | **NOT_AUDITABLE** | No real-money traffic yet | — | Re-evaluate post-launch |
| Q56/Q58/Q59/Q71/Q72/Q73/Q74/Q75 | Customer target / positioning / content / competitor / hub / Zimbabwe / investment / super-app | requirements | — (business) | strategy | Business strategy; some OUT of v1 (Zimbabwe) | **NOT_AUDITABLE / MISSING** | No production surface / deferred | — | none |

---

## Status tally (this matrix mirrors `extracted-facts.json`, 90 facts)

| Status | Count |
| ------ | ----- |
| VERIFIED | 10 |
| PARTIAL | 44 |
| MISSING | 10 |
| CONFLICT | 17 |
| NOT_AUDITABLE | 9 |

**Reading:** the large PARTIAL bucket reflects two facts of this environment — (1) the platform is a **built-but-pre-real-money demo** (schema/code present, zero money-ops rows), and (2) this session **could not re-probe live DB/API** (egress 403), so many code-present facts cannot be raised to VERIFIED. Most CONFLICTs are **intentional, documented supersessions** (Master Plan → `00-decisions.md`); the **genuine production gaps** are concentrated in payments-ledger (R2), n8n workflows (R3), observability (R4), demo data (R5), seller CTA (R1), migration drift, and CI hardening (R7).
