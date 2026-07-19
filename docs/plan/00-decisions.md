# Phase 0 — Decision Record (LOCKED 2026-07-06)

Founder answered all 28 discovery questions; where a recommendation was delegated ("what do you suggest?"), the decision below is Claude's recommendation and is **final unless the founder objects before Phase 2 dispatch**. This file supersedes `00-discovery.md` §7 and is the source of truth for Phases 1–5.

## A. Business & model

**D1 — Brand:** **Vergeo5**, domain **vergeo5.com** (⚠ not yet purchased — founder action F1). Legal entity exists (PACRA) but annual returns lapsed (F2). Product name in UI: "Vergeo5"; company name per PACRA registration.

**D2 — v1 verticals: ALL FIVE — Products, Services, Events, Supplies, Directory** — scoped thin rather than deferred:

- _Products_: full flow (canonical catalog, listings, cart, checkout, escrow, delivery/pickup).
- _Services_: RFQ model only — post-a-job → providers quote → accept → deposit/balance via escrow. No booking calendar v1.
- _Events_: create → list → sell tickets (fixed + multi-tier + free RSVP pricing only) → dynamic QR (60s HMAC rotation) + PIN → organiser scanner PWA. No early-bird schedules/group tables/PWYW v1.
- _Supplies_ (B2B-lite): listings flagged `wholesale` with quantity-tier price arrays + MOQ, discoverable in a Supplies tab. NO credit terms, RFQ-broadcast, business accounts, or account managers v1.
- _Directory_: vendor profile pages double as directory entries + a browsable/searchable directory index tab. Near-zero marginal build since profiles must exist anyway.

**D3 — Vendor fees:** **Free-only at launch** ("Free to list. Pay only when you sell."). Paid tiers (Bronze K99 / Silver K249 / Gold K499 — caps/perks per Master Plan L2) ship as a **feature-flagged module** activated at ~300 orders/mo or month 3+, whichever first. Top tier = Gold (Platinum reserved for future). Free tier at launch: up to 30 listings, full selling features, standard analytics.

**D4 — Commissions (category-variable, shown to vendor before publish):** electronics 5% · home goods 8% · fashion/beauty 10% · services 12% · event tickets 5% · supplies/wholesale 3% · groceries/staples 5% · default for unmapped categories 8%. Free events: 0% forever. Rates live in a config table (admin-editable), never hard-coded. Review quarterly against vendor feedback.

**D5 — Settlement promise (customer/vendor-visible):** escrow release on delivery-confirmation (or 48h auto-confirm after delivered status; 7 days after shipping fallback). Payout after release via **Lenco API: mobile money ≈ instant (≤5 min); bank 24–36h**. Marketing claim: **"Paid out in minutes on mobile money — always within 48 hours."** Used-goods 72h window and event T-7/T+1 splits activate only when those features ship.

**D6 — Budget:** **≤ $50/mo** infra all-in until revenue; automation (n8n) preferred over manual ops; free tiers exploited aggressively (Supabase free, Cloudinary free, OCI Always Free, Vercel hobby→pro only when required).

**D7 — Timeline:** beta ≈ **8 weeks after Phase 3 prompts start executing**; public ≈ 4 weeks after beta. Quality gate ("production ready" definition in `/vergeo5` GOAL) beats the calendar.

## B. Customers & vendors

**D8 — Launch categories (8 departments, per Strategy Bible Ph1):** groceries & staples · personal care & beauty (new/sealed only) · fashion (chitenge + new retail; no salaula) · electronics (selective: phones Itel/Tecno/Samsung-class, accessories, solar kits; no used phones) · home & living · office & stationery · light hardware (no cement/sand/heavy aggregates) · event tickets. Services verticals (8): beauty · food/catering · auto (mechanics/car wash/tyres) · printing & creative · home services · tech services · cleaning · tailoring. Events categories (6): workshops/education · comedy & theatre · music & nightlife · community/lifestyle · cultural & arts · free RSVP events.

**D9 — KYC: 3 tiers + 1 earned badge; NO unverified public listings.**

- T1 _Seller_: NRC photo + selfie + mobile-money name match → live same day; caps: ≤30 listings, orders ≤K500 each for first 5 orders, payout velocity limits.
- T2 _Verified Business_: PACRA cert + company TPIN → badge, caps lifted, supplies tab eligible.
- T3 _Premium/API_: invited/reviewed; API access, banner placement eligibility.
- _Vergeo5 Preferred_: earned badge (≥20 orders, ≥4.5★, <2% disputes, <5% cancels) — auto-granted/revoked monthly. (The Bible's "5-tier" reading collapses into this: its Tier-0 unverified is rejected; its "Preferred" is a badge, not KYC.)

**D10 — Vendor pipeline:** zero committed vendors today — founder recruits with the working product. Consequences baked into plan: polished vendor landing/pitch page is a launch feature; seed/demo catalog required (D25); onboarding must be self-service flawless; CSV bulk import stays in v1.

## C. Payments & compliance

**D11 — Aggregator: Lenco (BroadPay) — confirmed, founder HAS API access + docs.** All three MoMo rails + cards + bank. Payment abstraction layer regardless (strategy pattern) so Flutterwave/PawaPay can slot in later. **Founder action F3: commit Lenco API docs/credential names (never secrets) to `docs/ops/lenco/`** so prompts can reference real contracts.

**D12 — COD:** allowed for orders **≤ K500** (fraud cap per Master Plan Q25); above K500 → pay-at-pickup via mobile-money push or prepay. ⚠ Founder's reply read "greater than 500 is okay" — assumed to be agreement with the ≤K500 cap, **flagged for explicit confirmation** (if you truly want COD only _above_ K500, say so — it inverts the fraud logic and is NOT recommended).

**D13 — Tax/legal posture:** launch under **Turnover Tax** (5%, sub-K5M) with company TPIN (F2); ZRA-ready sequential invoicing from day 1, architected for **Smart Invoice VSDC API** activation at VAT registration (K800k/12mo or K200k/3mo threshold). Per-category VAT flag in schema from day 1.

**D14 — Escrow structure:** **Lenco-held funds** (collections settle to Lenco-managed account) + **platform ledger-of-record** driving releases/payouts via Lenco API. Platform never pools funds in its own bank account. **Zambian counsel review of the flow under NPS Act 2026 is a pre-real-money launch gate** (F4) — not blocking development.

**D15 — WhatsApp: official Cloud API only; WAHA banned from production AND dev** (test numbers make WAHA unnecessary even for development — see `docs/ops/whatsapp-cloud-api-setup.md` step-by-step). Founder actions F5 (Meta Business setup). SMS fallback: Africa's Talking (or LineServe if cheaper at signup); email tertiary (Resend/SES free tier).

## D. Logistics

**D16 — Delivery v1:** Lusaka delivery via **manual admin dispatch** (Yango/inDrive/local couriers booked by ops, tracking pasted in; delivery status updates flow to customer via WhatsApp/SMS). Nationwide: vendor listings visible everywhere; fulfilment via customer pickup (QR+PIN) or **bus/courier freight (Platinum couriers et al.) arranged case-by-case**; MOU discussions post-launch (F6). Delivery fee zones (Lusaka bands + intercity flat estimates), free delivery ≥K200 within Lusaka. No courier API integrations v1 — abstraction seam left for Phase 2.

**D17 — Returns & refunds (two lanes):**

- _Lane 1 — Faulty / wrong / not-as-described_ (platform-mandated, CCPC-aligned): report ≤48h of delivery with photo evidence → full refund incl. delivery from escrow; return shipping charged to vendor; admin arbitrates disputes.
- _Lane 2 — Change-of-mind_ (vendor opt-in per listing): vendor sets `returnable: yes/no` + window (48h–7 days). Item unused/original condition. Refund = item price − outbound delivery − return transport − **10% restocking fee** (config 5–15%). Refund to mobile money (or instant store credit when wallet ships).
- All refunds pre-release come from escrow; post-release refunds claw back from vendor's next payouts. Reverse logistics manual v1.

## E. Tech stack (LOCKED)

**D18 — Backend: FastAPI (Python 3.12) + Supabase** (Postgres 16 + pgvector, Auth, Storage, Realtime-later). Rationale vs Django: founder has FastAPI+Supabase experience (solo maintainability IS security); Supabase gives managed auth, RLS defense-in-depth for three apps, storage, and pgvector natively; $0–25/mo; Supabase MCP server accelerates dev/ops; async-first suits payment webhooks. Django's security "batteries" are matched by: Pydantic strict validation everywhere, RLS on every table, service-role keys server-side only, SlowAPI+Caddy rate limiting, security headers, OWASP checklist + tests in every pebble, dependency audit in CI. Django's admin advantage is moot — admin app is custom-built (D20).

**D19 — Frontend: Next.js 15 (App Router) + TypeScript strict + Tailwind CSS 4 + next-intl + PWA (serwist) + SSR/ISR** for SEO. GSAP admissible later for hero/marketing flourishes (performance budget still rules); default animation via CSS/Framer-Motion-lite patterns.

**D20 — Topology: THREE apps (founder decision, security isolation):** `apps/customer` (PWA, SSR, public) · `apps/vendor` (SPA-ish, auth-gated) · `apps/admin` (auth-gated, IP-allowlist/Cloudflare-Access-protected, separate origin) — in ONE monorepo (pnpm + turborepo) with `packages/ui` (design system), `packages/types` (generated from OpenAPI), `packages/config`, `packages/i18n`. One FastAPI backend serves all three with role-scoped routers + RLS beneath.

**D21 — Hosting:** **new dedicated OCI account** (Always Free ARM VM: Docker Compose — FastAPI, Caddy, n8n; Ampere 4 OCPU/24GB) + **Supabase cloud free tier** (founder has account) + customer app on **Vercel** (hobby → pro later; SSR/ISR + edge CDN matters most for shoppers); vendor+admin apps served from OCI behind Caddy (cheap, fine for logged-in tools). Cloudflare free in front of OCI (DNS, TLS, WAF-lite, caching). Backups: Supabase PITR-lite (daily dump to OCI Object Storage via n8n). Est. $0–20/mo + domain.

**D22 — Search: hybrid from day 1, one engine (Postgres).** Keyword lane: Postgres FTS + `pg_trgm` (typo tolerance) with faceted filters. Semantic lane: **pgvector** embeddings on a unified `search_documents` projection (products, services, events, supplies, vendors) — the same index IS the RAG store for AI mode. Fusion: Reciprocal Rank Fusion in SQL. Embeddings: cheap model via OpenRouter (or Supabase edge gte-small at $0) generated on publish/update. Meilisearch deferred until >~20k listings or FTS latency >150ms p95. (Founder's vector-first instinct honored — vectors are first-class, but exact/price/filter queries need the keyword lane; pure-vector marketplaces frustrate precise shoppers.)

**D23 — AI mode ("Ask Vergeo"):** dedicated tab (Alibaba-style) + inline entry from search. RAG over `search_documents` (D22) with structured filter extraction; answers ground ONLY in platform data with listing cards cited. Quotas: guests 3 questions (then signup prompt) · free accounts **25 questions/month** · top-ups later (e.g. K10/50 questions) or bundled into paid vendor tiers. Cost controls: cheap default model via OpenRouter, per-answer token caps, response cache on common queries, **global monthly kill-switch cap $15**. Semantic search itself (D22) is unmetered — near-zero marginal cost.

**D24 — Data model (Option A locked):** **canonical `products` + `vendor_listings`** (search-and-attach; comparison view "N vendors selling this" = differentiator) · `services` as provider-owned listings (no canonical layer) · `events` / `ticket_types` / `tickets` as first-class tables (NOT products-with-flags) · supplies = `vendor_listings.wholesale=true` + `price_tiers jsonb` + `moq` · unified `search_documents` projection for search/RAG · single `orders`/`order_items` spine with `item_kind` discriminator + per-kind detail tables; one escrow ledger + state machines over everything. (Rejected: B polymorphic single-Listing table — integrity/query pain; C no canonical layer — loses comparison moat.)

## F. Catalog & content

**D25 — Seeding:** Claude generates the category tree (8 departments → ~60–80 subcategories from the Bible's catalogue) + **~150 canonical product stubs** (name, spec skeleton, category, searchable aliases incl. Bemba/Nyanja terms) as reviewable seed migrations/fixtures. Founder reviews/prunes. Demo vendor + sandbox listings for the pitch environment (clearly flagged, excluded from public search).

**D26 — Media:** **Cloudinary free tier for public imagery** (products/services/events/banners — `f_auto,q_auto` WebP/AVIF, responsive transforms, 25 credits/mo ≈ enough for launch) + **Supabase Storage private buckets (RLS) for sensitive files** (KYC docs, invoices, dispute evidence). Migration seam: image URLs behind a helper so a later move to Supabase+CDN or R2 is a config change. Product images ≤8 per listing.

**D27 — Languages:** launch **English** with full i18n/l10n scaffolding (next-intl ICU messages, externalized strings enforced by lint rule, locale-aware ZMW/date/number, RTL-capable layout). Expansion order: **Bemba + Nyanja** (human-reviewed) → **French** (DRC/regional trade corridor) → Tonga + Lozi → others (Arabic/Chinese/Russian/German) only on demonstrated demand. Machine translation allowed for long-tail listing content with "auto-translated" tag, never for checkout/payment/legal copy without review.

**D28 — B2B wholesale gating (strategy-alignment audit, 2026-07-14):** wholesale supply pricing (tier prices + MOQ) and the wholesale discovery feed are **hidden until a buyer is a verified business**, never applied on the listing alone. A buyer-side `business_buyers` identity (PACRA reg + optional TPIN) carries a `pending→verified/rejected/suspended` lifecycle (status server-controlled; admin verifies). A single shared resolver (`is_verified_business` / `app/services/business/access.py`) is the eligibility gate, enforced identically at discovery, cart pricing, and checkout — a consumer always sees retail. **Follow-up (2026-07-15):** "hidden" now spans **every** consumer discovery surface, not just the dedicated supplies feed — wholesale-only listings are filtered from the catalog PLP, product detail, price comparison, vendor storefront profile, and FTS search/suggest for guests & non-verified consumers (verified businesses still see them inline via `get_business_access`), and dropped unconditionally from "Ask Vergeo" retrieval (query-keyed cache). The onboarding vendor **archetype** is persisted on the vendor row (not localStorage-only) and now drives a tailored vendor-home quick-start card. This is the thin, present-day slice; the **full B2B stack stays OUT of v1** per the scope fence below (credit/Net terms, buyer organisations & roles, account managers, contract pricing, multi-warehouse + lot/batch, wallet/financing) — all Phase 2.

**D29 — Events Phase-2 Wave A: schema foundation (founder gate answered 2026-07-15; amends D2 + §G).** Build-out being complete, the Events vertical enters its Phase-2 expansion. This decision **moves the following from the §G OUT list into scope** and supersedes D2's "no early-bird/group/PWYW v1" for the named subset only. Locked answers (planning detail in `docs/plan/events-wave-a-schema.md`):

- **event_type = _full behavioral driver_** (founder's explicit choice over the minimal-classifier option). New `events.event_type` drives per-type behavior across **discovery filtering, escrow timing, and UX** — not a display label. Because this couples event_type into the **money path**, it is implemented as a single **guarded per-type policy map** (one source of truth consumed by `event_release.py` + discovery), never scattered `if event_type == …` branches, and the escrow legs stay idempotent/audited/guarded exactly as the order engine requires.
- **Pricing modes = group/tiered + early-bird; _PWYW deferred_.** Ship qty→price tiers (activates the dormant `ticket_types.kind='tier'` seam) and time-gated early-bird sale windows. Pay-what-you-want stays OUT (its variable-paid-amount refund/escrow math + fraud surface get their own later decision). Prices always resolved server-side within locked bounds — no client-supplied price trusted.
- **Attendee data = optional per-ticket `holder_name`; buyer-phone only.** `tickets.holder_name` captured per attendee at purchase, required only when an organiser flags a ticket type "named" (pop-up dinners, allocated seating). No per-attendee phone (minimise PII).
- **Recurrence = _deferred_.** Manual multi-instance (already supported via `event_instances`) stays the mechanism for Wave A; no `recurrence_rule`/RRULE generation built now.
- **Lower-leverage (defaulted):** `events.visibility` = `public | unlisted` (hidden from browse, link works) `| private` (access-code required — the enforcement behind event_type's private behavior); **per-instance tier allocation = yes** (`ticket_type_instances` join, needed for real multi-night events); policy fields = `refund_policy_key + age_restriction + terms` (additive, no launch-behavior change).

**Still OUT (unchanged):** PWYW pricing, true recurrence/RRULE, ticket **resale** marketplace (transfer-to-friend remains the only secondary path), booking calendars. Migrations `0041`+ additive/reversible; every new table carries its RLS-matrix row.

## G. v1 scope fence

**IN (thin):** all five verticals per D2 · escrow + Lenco payments (MoMo/card/bank) + COD ≤K500 · QR+PIN pickup · manual-dispatch delivery · reviews (1–5★ + text + photos, verified-purchase) · WhatsApp/SMS/email notifications · vendor portal (KYC, listings, CSV import, orders, payouts, basic analytics) · admin (KYC queue, moderation, disputes, refunds, config, dashboards, **merchandising manager: admin-swappable hero/banners/featured collections**) · AI mode + hybrid search · directory tab · PWA + SEO + i18n scaffolding · ZRA-ready invoices · observability (Sentry free + UptimeRobot) · CI/CD + backups.

**OUT of v1 (explicit):** vendor subscription _billing_ (module flagged off, D3) · full B2B (credit/Net terms, RFQ-broadcast for goods, business accounts, account managers) · wallet/Vergeo Pay/financing · city guides & AI trip planner · promoted-listing auctions · referral program · multi-warehouse + lot/batch · POS-light · voice search & AR · native Android app · cross-border/Zimbabwe · ticket resale marketplace (simple transfer-to-friend allowed) · Copperbelt delivery ops (listings + pickup still work) · real-time in-app notification center · multi-dimensional reviews · booking calendars for services · ~~early-bird/group/PWYW ticket pricing~~ → **early-bird + group/tiered moved IN via D29 (Events Wave A); PWYW still OUT** · salaula, used phones, fresh produce, alcohol, pharma, live animals, heavy building materials categories · same-day delivery promises.

## Founder action list (non-blocking for Phase 1–3 planning; blocking where noted)

- **F1.** Buy **vergeo5.com** (also grab vergeo5.co.zm if cheap). Needed before Meta Business verification (F5) and email (hello@vergeo5.com).
- **F2.** PACRA annual returns renewal; company TPIN registration (personal TPIN won't do for Lenco settlement + ZRA later).
- **F3.** Commit Lenco API docs (PDF/links) to `docs/ops/lenco/` + note sandbox/production credential names (NEVER the secrets themselves — those go to env vars).
- **F4.** Zambian counsel review of Lenco-held escrow flow under NPS Act 2026 — **gate before real-money public launch**, not before build.
- **F5.** Meta Business + WhatsApp Cloud API activation — follow `docs/ops/whatsapp-cloud-api-setup.md` (test number available same-day; real number needs F1 domain for smooth verification).
- **F6.** Open MOU conversations with Platinum couriers / bus freight partners (post-beta is fine).
- **F7.** Upload remaining 7 design HTML files (see `docs/designs/SOURCES.md`) — most wanted: Events Desktop, Catalogue. Optionally allowlist `vergeo-21ffc.web.app` in the Claude Code environment network settings for the live-prototype audit.
- **F8.** Confirm or invert D12's COD cap (≤K500 recommended).

## H. Release & launch sequencing

**D30 — Release strategy: HYBRID controlled live-beta (founder decision 2026-07-19; resolves audit question B-1; supersedes the staging-first sequencing in `docs/production-readiness/2026-07-18/consolidated/implementation-wave-plan.md`).**

Adopt a **hybrid** path, not staging-first and not money-live:

- **Live-beta the no-money discovery surface to production, behind `public_launch=false`.** Harden and promote the customer/vendor/admin frontends to the current master tip (incl. the categories-500 fix), apply the outstanding migrations (`0051`/`0053`–`0056`), pin the API image, and set `NEXT_PUBLIC_VENDOR_APP_URL` — so real customers can browse/search/RFQ against an honest, deployed surface under an invite gate. (Vision-audit Wave 1 / VM-A.)
- **In parallel, prove money on an isolated target — not a full staging plane.** The Lenco sandbox money/escrow/KYC drills (S1–S6) run against sandbox credentials + a throwaway DB branch, so verification is **not blocked on standing up a separable staging stack** (VE-P08 environment isolation stays tracked as a Wave-4 item, not a prerequisite). (Vision-audit Wave 2 / VM-B.)
- **Real money stays OFF** — `public_launch=false`, prepaid collection disabled, `zamtel_collections=false` — until the money/escrow/KYC paths pass **S1–S6 somewhere isolated** AND every P0 gate (including legal counsel F4 / FD-08) passes per `release-gates.md` Go/No-Go. No calendar flip (NB-13/FD-11).

**Sequencing consequence:** vision-audit Wave 1 (deploy/schema truth) and Wave 2 (sandbox money + n8n activation) may run **in parallel**; neither waits on a full staging environment. Recorded in `docs/production-readiness/2026-07-19/vision-audit/02-open-questions.md` §B-1.

## I. Security, RBAC & catalogue-scope decisions (2026-07-19, from vision-audit B-2…B-5)

Founder locked the four remaining Wave-0 blocking questions on their recommended defaults. These gate vision-audit Wave 3 (VM-C).

**D31 — Role provisioning (resolves B-2 / FD-03): apply `0051` + enable the Auth hook.** JWT roles are carried by applying migration `0051_custom_access_token_role_hook` and enabling the Supabase Auth custom-access-token hook, so JWT `roles` == `public.user_roles`. Sequenced **after** a backup and a staging-first apply (D-VA-P00/P02 order). The written manual-grant exception is the fallback **only** if Auth-dashboard access blocks the hook. Admin authorization still never trusts the JWT alone — `getRoles` reads `user_roles` server-side and Cloudflare Access gates the origin. (Pebble VC-P03; closes MR-S02, gate G0.)

**D32 — FORCE RLS on money-isolation tables (resolves B-3 / FD-07): enable, not waive.** Set `relforcerowsecurity = true` on `ticket_type_instances`, `ticket_type_price_tiers`, and `product_relations` via an additive migration, fixing any table-owner/service-role assumption FORCE would break; the security advisor and RLS isolation matrix must stay green. A signed security exception is acceptable **only** if a hard platform constraint is proven on staging first. (Pebble VC-P02; closes MR-R01, gate G0.)

**D33 — Admin RBAC (resolves B-4 / FD-02): single `admin` + Cloudflare Access for v1.** v1 admin authorization is the single `admin` role behind Cloudflare Access — this **supersedes** the roadmap superadmin/moderator multi-tier for v1. Admin user/role management is a **documented manual-ops path** (guarded, audited grant/revoke), **not** a fabricated CRUD UI; agents must not invent superadmin/moderator roles. Additive human-operator roles are revisited only via a dated ADR before open launch. (Pebbles VC-P07 → VF-P03 become docs, not a build; resolves MR-A02, gate G15.)

**D34 — Phase-1 catalogue scope (resolves B-5 / FD-06): Class A branded/new only.** Phase-1 catalogue marketing is limited to **Class A branded/new goods (+ existing `refurbished`)**. No `product_class` A–E column, no used-goods/open-box evidence model (IMEI/VIN/`evidence_kind`), no expanded `condition` enum, and no 72h used-goods escrow window are built for launch — these stay OUT (per §G and the D8 category constraints) unless separately elevated by a dated ADR. This keeps MR-S05/S06/V05 and C-ESCROW-HOLD **out of scope**. (No new schema pebble; the catalogue-facing work is the demo-exclusion VC-P06.)
