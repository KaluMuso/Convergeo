# Missing & Conflicting Items — Strategic Master Plan v1.0

**Audit date:** 2026-07-18 · READ-ONLY · Baseline: `../../foundation/*` + repo `0b88723`.

Organised per the contract into: (a) missing production records · (b) missing fields/schema support · (c) configuration/workflow gaps · (d) UI gaps · (e) conflicting data · (f) access/evidence limitations.

> **Framing:** Most tech-stack "conflicts" are **intentional supersessions** — `docs/plan/00-decisions.md` (LOCKED 2026-07-06) deliberately revised the Master Plan's stack (Django→FastAPI, Railway→OCI, Meilisearch→Postgres, DPO+Lenco→Lenco-only, Celery/Upstash dropped, Supabase-Realtime-notifs→WhatsApp/outbox). These need **document reconciliation**, not production change. The list below separates those from **genuine gaps**.

---

## a. Missing production records (operational reality is empty/demo)

| Item | Expected (doc) | Live | Evidence | Status | Note |
| ---- | -------------- | ---- | -------- | ------ | ---- |
| Real vendors | 75–100 real vendors before launch (Q57, Risk#1) | 3 **demo** vendors | foundation R5 (vendors=3; slugs cairo-road-fashions/kabwata-market/lusaka-electronics) | CONFLICT | Demo seed, not real supply |
| Real orders / payments / ledger | Real money changing hands (Phase-1 goal) | 0 orders, 0 payments, 0 ledger txns, 0 payouts, 0 tickets | foundation §5 | NOT_AUDITABLE (KPIs) | Pre-real-money; targets can't be evaluated |
| Listing media (real) | Real product imagery | 134 images all `cloudinary_public_id LIKE 'demo/%'` | foundation R5 | CONFLICT | Demo imagery live on public catalog |
| Registered customers | 10k–25k yr1 (reframed 1k active) | profiles=3 | foundation §5 | NOT_AUDITABLE | Pre-launch |

## b. Missing fields / schema support (repo tip vs live)

| Item | Expected | Live | Evidence | Status | Note |
| ---- | -------- | ---- | -------- | ------ | ---- |
| `custom_access_token` role hook (0051) | JWT role claims from `user_roles` | function **absent** on live | foundation (mig 0051 not applied) | MISSING | Role provisioning stays manual until applied + Auth hook enabled |
| `translation_overrides` (0053) | i18n overrides (supports Q27 languages) | table **absent** on live | foundation | MISSING | Repo-ahead; not applied |
| `service_reviews` ext (0054) | Service review support (Q32/Q51) | **absent** on live | foundation | MISSING | Repo-ahead |
| `services.bookable` (0055) | Service bookability | column **absent** on live | foundation | MISSING | Repo-ahead |
| Subscription/tier tables | 4-tier vendor plans (Q4/Layer2) | **no subscription code/tables** | repo grep 0; D3 defers | MISSING (by-decision) | Billing OUT of v1 |
| Multi-dimensional review fields | quality/delivery/communication axes (Q32) | out of v1 (single-dim + photos) | scope fence | MISSING (by-decision) | Doc broader than v1 |

## c. Configuration / workflow gaps (genuine — the priority list)

| Item | Expected | Live | Evidence | Status | Priority |
| ---- | -------- | ---- | -------- | ------ | -------- |
| **Prepaid → ledger posting** | Successful prepaid collection posts `CHARGE_RECEIVED`/`ESCROW_HOLD` (Q22/T5/D14) | Ledger templates exist but prepaid webhook success path appears to update `payments`+`audit_log` only | foundation R2; repo `LedgerTemplate` present, `post_transaction` not on prepaid path | **PARTIAL → P0** | P0 |
| **n8n escrow auto-release** (`release-job`) | 48h auto-release (Q21/D5) | **absent** on live n8n (only 2 workflows active) | foundation R3 | MISSING | P1 |
| **n8n ticket issuance** (`tickets-issue`) | Paid tickets issued w/ dynamic QR (Q50) | **absent** on live n8n | foundation R3 | MISSING | P1 |
| Other n8n workflows (order-jobs, event-release, embeddings, sweepers, digests, backup) | Order/ops automation (Q66) | absent on live (18 in repo, 2 live) | foundation R3/§6 | MISSING | P1/P2 |
| Observability (Sentry projects + DSNs; UptimeRobot) | Sentry + uptime (W8) | **no Vergeo5 Sentry projects**; UptimeRobot NOT_AUDITABLE | foundation R4 | MISSING | P1 |
| Analytics stream population | GMV/CAC/LTV/NPS (Q65) | `analytics_events`/`funnel_events`=0 rows | foundation R4 | PARTIAL | P1 |
| Seller/vendor signup CTA env | Vendor acquisition (Q3/Q35) | CTA disabled ("temporarily unavailable"); `NEXT_PUBLIC_VENDOR_APP_URL` likely unset | foundation R1 | PARTIAL | P1 |
| Migration parity | Live DB == git tip | 0051/0053/0054/0055 not applied; 0052 version skew | foundation §4 | CONFLICT | P0 |
| CI blocking gates | Blocking lint/type/test/contract (Rule6) | secret-scan/i18n/Lighthouse `continue-on-error` | foundation R7 | PARTIAL | P2 |
| Auth leaked-password protection | GDPR-level (Q61) | **disabled** (advisor) | foundation §3.4 | PARTIAL | P2 |
| FORCE RLS on 3 tables | RLS defense-in-depth | `product_relations`, `ticket_type_instances`, `ticket_type_price_tiers` FORCE=false | foundation §3.3 | PARTIAL | P2 |
| Commission rate config values | Category rates (Q2/D4) | 9 rows exist; **values not readable this session** | foundation (count only) | NOT_AUDITABLE | P2 |
| Second payment gateway (resilience) | DPO+Lenco redundancy (Q19) | Lenco only | repo 0 DPO | CONFLICT (residual) | P2 |
| Backup workflow proof | DB backups (W8/D21 PITR-lite) | no n8n backup workflow; OCI dump host NOT_AUDITABLE | foundation R3 | MISSING/NOT_AUDITABLE | P1 |

## d. UI / customer / vendor / admin gaps

| Item | Expected | Live | Evidence | Status | Note |
| ---- | -------- | ---- | -------- | ------ | ---- |
| Admin users/roles management UI | Admin "manage users" (Phase 1) | none found; `user_roles` service-role only | foundation R6 | MISSING | Manual SQL/dashboard grants |
| Seller CTA (customer→vendor) | Working vendor signup entry | disabled button | foundation R1 | PARTIAL | Acquisition broken |
| Vendor subscription/upgrade UI | Tier upgrade (Q4/Q42) | none (billing deferred) | D3 | MISSING (by-decision) | — |
| Homepage merchandising | Hero+collections+trending (Q30) | merch_slots=1; admin merch manager (D-scope) | foundation | PARTIAL | Not re-probed live |
| Directory tab | First-class directory (Q53) | in scope (D2); live UI not re-probed | — | PARTIAL | Confirm live |

## e. Conflicting data (document vs production, or doc-internal)

| Conflict | Doc says | Production / other decision | Status | Type |
| -------- | -------- | --------------------------- | ------ | ---- |
| Backend framework | Django + DRF (Q9) | FastAPI (D18; live uvicorn) | CONFLICT | superseded-intentional |
| Backend host | Railway/Render (Q11) | OCI + Caddy (D21) | CONFLICT | superseded-intentional |
| Search engine | Meilisearch primary (Q15) | Postgres FTS+pgvector+RRF (D22) | CONFLICT | superseded-intentional |
| Cache | Upstash Redis (Q17) | none / SlowAPI+Caddy (D18) | CONFLICT | superseded-intentional |
| Async | Celery+n8n (Q18) | n8n only (D18) | CONFLICT | superseded-intentional |
| Notifications | Supabase Realtime (Q14) | WhatsApp/SMS/email outbox (D15) | CONFLICT | superseded-intentional |
| Payment gateways | DPO+Lenco (Q19); DPO in Phase 1, Lenco later | Lenco only, from start (D11) | CONFLICT | superseded-intentional (+ residual resilience gap) |
| Courier | Yango/Zampost APIs (Q43/Q47) | manual dispatch labels (D16) | CONFLICT | superseded-intentional |
| Returns | "no returns MVP" (Q48) | two-lane returns incl. change-of-mind (D17) | CONFLICT | production-ahead |
| Phase-1 scope | excludes Events/directory/AI/RFQ/Lenco | v1 INCLUDES them (D2/D29) | CONFLICT | re-sequenced |
| Timeline/methodology | 4 phases + 60-day sprint | 16 mountains + waves; D7 | CONFLICT | superseded-intentional |
| Launch languages | EN+Bemba+Nyanja at launch (Q27) | English at launch; others later (D27) | CONFLICT | timing |
| Persistent memory | AI_CONTEXT.md (Rule4) | CLAUDE.md + 00-status.md | CONFLICT | cosmetic |
| Vendor free-tier cap | 20 products (Layer2) | 30 listings (D3) | CONFLICT | doc↔decision numeric |
| Top vendor tier | Platinum (Q4) vs Gold (Layer2) | Gold top, Platinum future (D3) | CONFLICT | **doc-internal** |
| Infra cost | $62/mo (break-even) vs $30–60 (Sec4) vs $50 ceiling (D6) | ≤$50/mo target (D6) | CONFLICT | doc-internal + tighter decision |
| Demo vs real marketplace | 200–500 real vendors (Q57) | 3 demo vendors, 134 demo images (R5) | CONFLICT | genuine gap |
| DB migration parity | schema+all migrations delivered | live behind repo (0051/53–55) | CONFLICT | genuine gap |

## f. Access / evidence limitations (this session)

| Blocked capability | Why | Impact on audit | What would resolve |
| ------------------ | --- | --------------- | ------------------ |
| Live API re-probe (`api.vergeo5.com`) | proxy egress **403** (org policy) | Could not independently re-confirm health/catalog/OpenAPI; relied on same-day foundation probes | Allowlist `api.vergeo5.com` for the session, or run from foundation-capable session |
| Live SQL (`mcp.supabase.com`) | proxy egress **403** + interactive OAuth unavailable | Could not read `commission_rates` values, live row counts, RLS/policies, migration list fresh | Authorize Supabase MCP + allowlist host; then run the safe query pack |
| Vercel / n8n / Sentry MCP (fresh) | not exercised this session (egress likely same policy) | Deployment SHAs, live workflow list, Sentry projects inherited from foundation | Restore MCP egress; re-run `list_deployments`/`search_workflows`/`find_projects` |
| API container git SHA / image digest | GHCR auth + host SSH unavailable (foundation) | API deployed commit NOT_AUDITABLE | Read `API_IMAGE_TAG`/`docker inspect` with least privilege |
| Vercel/API env **values** (e.g. `NEXT_PUBLIC_VENDOR_APP_URL`, Lenco/WhatsApp/Sentry DSNs) | policy (never read secrets) | Seller-CTA/env-unset inferred, not confirmed | Confirm presence (not value) in Vercel dashboard |
| Commission rate values, delivery thresholds, tier caps | DB blocked | Config values NOT_AUDITABLE | Safe SELECT when DB access restored |
| Facebook social login enabled? | DB/Auth blocked | Provider set NOT_AUDITABLE | Read Supabase Auth providers |
| Sandbox paid-order → ledger proof | no payment execution permitted (contract) + no sandbox access | R2 (prepaid ledger) stays PARTIAL, not resolved | Controlled sandbox checkout in a non-audit change session |
