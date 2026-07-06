# Phase 0 — Discovery: Vergeo5

**Date:** 2026-07-06 · **Status:** COMPLETE — awaiting founder answers to §7 · **Mode:** GATED

**Sources read (raw inputs — not to be re-read after this phase):**
- `docs/concept/Convergeo_Strategic_Master_Plan.pdf` — 37 pages (upload metadata claimed 293; actual page count verified 37). Contains: 7-page "Vergeo" marketing/UI deck + "THE MOUNTAIN — Convergeo Strategic Master Plan v1.0" (75 decisions Q1–Q75, tensions, business model, architecture, methodology, phases, 60-day schedule, KPIs, risks) + day-by-day 60-Day Development Roadmap. Distilled → `research/master-plan-distilled-{A,B,C}.md` (three independent passes, cross-checked).
- `docs/concept/Convergeo_Strategy_Bible.pdf` — 99 pages (metadata claimed 13). Four companion briefs: Events/Ticketing, Product/Catalogue, Business/Pipelines/Three-Frontends, Services platform. Distilled → `research/strategy-bible-and-blueprint-distilled.md`.
- `docs/concept/Blueprint_for_Zambias_Vergeo_superapp.pdf` — 37-page podcast-style transcript narrating the internal docs. Secondary/derivative; its dashboard numbers are wireframe mock data. Distilled → same file as above.
- Fresh July-2026 verification research on Zambian payments, ZRA, BoZ, WhatsApp → `research/payments-compliance-zambia-2026-07.md` (all claims source-linked).

**Inputs NOT readable from this environment (blockers, see §6):** the 12 Claude Design HTML files (`docs/designs/SOURCES.md`) and the live prototype `https://vergeo-21ffc.web.app/` (egress-blocked; audit harness ready in `docs/designs/live-prototype/README.md`). `reference/prototype/` does not exist — the repo was empty at session start.

---

## 1. Understanding summary

**Vergeo5 (working brand unresolved: consumer deck says "Vergeo"/vergeo.zm; strategy docs say "Convergeo") is a multi-vendor, commerce-powered discovery platform for Zambia** — "Discover Everything Zambia Has to Offer." One discoverable surface for four supply types: **products** (canonical catalog + per-vendor listings with comparison), **services** (quote/RFQ model, no booking calendar in early phases), **events + ticketing** (dynamic 60-second QR tickets), and **inventory/B2B wholesale** (latent in schema, UI later). It is explicitly *not* a single-brand storefront, and its stated biggest competitor is **WhatsApp informal selling**, not Jumia.

**Who it serves:** mobile-first Zambian consumers on budget Androids over 3G/4G (78% mobile internet share); vendors from informal market traders (NRC-only KYC, listing live in ~10 minutes) to registered companies (PACRA docs, verified badge) to premium brands (API access); service professionals; event organisers. Lusaka-first, Copperbelt next, 10-province ambition. Solo founder (Prosper Kaluba) + AI tooling, ~$2K bootstrap, ~$60/mo infra target.

**How it makes money:** (1) category-variable commissions — 5% electronics, 8% home goods, 10% fashion/beauty, 12% services, 5% event tickets; (2) vendor subscriptions Free/Bronze K99/Silver K249/Gold K499 per month; (3) event ticket commission + promoted events; (4) future promoted-listing auctions, Tier-3 API access, and an Alipay-style financial ladder (wallet → working capital → payments). Free tier pitched as "no monthly fees — only pay when you sell."

**The moat is trust mechanics:** visible escrow ("You paid → Held → Released"), fast vendor settlement (48h vs industry 7–14 days), verified-purchase reviews, tiered vendor verification, QR+PIN pickup, and price-per-kg normalisation — things WhatsApp sellers structurally can't offer.

**Production-ready v1 (per master prompt):** Lusaka customer on mid-range Android over 3G can browse → search → cart → pay with mobile money → get WhatsApp confirmation; secure, observable, tested, legally covered, CI/CD-deployable with backups/rollback.

## 2. Design inventory

**Available now (from the deck, master plan pp.1–7):** home/overview with hero + module cards (Shop/Services/Events/Vendors); product grid cards (vendor eyebrow, K-prices with strikethrough, badges: Best Seller/Local/Handmade/Sale/Top Rated/New; location tags: Nearest/Cheapest/International/7-Day Wait); service cards with per-category colour themes (Home Repair red, Technology indigo, Catering orange, Energy green, Creative amber, Logistics navy); event cards (date, venue, price, capacity bar, "spots left", Featured/Selling Fast badges); vendor directory cards (tier badge, rating, product count, region). Visual language: cream/off-white ground, dark navy serif display headlines, sans body, dark aubergine panels, pastel card fills, pill tags. **No hex tokens or type scale defined anywhere.**

**Homepage IA (Q30 + Week-6 spec):** hero search → upcoming events → categories/collections → trending → vendor spotlight; infinite scroll; mini expandable footer.

**Not yet in repo (blocked):** the 12 Claude Design HTML files (wireframes, Vergeo/Convergeo variants, Events Desktop, Customer Desktop, Platform, Catalogue, Mobile, Standalone, v1, 2× Prototype) — see `docs/designs/SOURCES.md` for the import checklist — and the live prototype capture. **Design-element selection (strongest-elements-per-variant, admin-swappable candidates) is deferred until these land; it will be executed at the start of Phase 1 without re-reading concept PDFs.**

**Critical flows with no design reference yet (from any source):** multi-step checkout + mobile-money USSD-push wait state; escrow status tracker; vendor onboarding/KYC upload; vendor order-fulfilment (mobile daily-driver); admin moderation/KYC/dispute queues; disputes; RFQ post-a-job flow; auth/OTP; order tracking timeline; ticket wallet + door-scanner mode.

## 3. Prototype audit

`reference/prototype/` does not exist; the only prototype is the live Firebase app `vergeo-21ffc.web.app`, which is **unreachable from this environment** (org egress policy denies CONNECT; verified at proxy level — not a rendering issue). A self-contained audit harness (route discovery, 360px+desktop screenshots, token/animation/framework extraction) is committed at `docs/designs/live-prototype/README.md`; it completes the audit in one command from any unrestricted machine, or after `vergeo-21ffc.web.app` is allowlisted in this environment's network settings.

**Provisional stance (to confirm once auditable):** treat the prototype as **design/behaviour reference only — rebuild, don't extend.** Rationale: Firebase hosting implies a stack that matches neither the concept docs (Django+Next.js) nor the master prompt (FastAPI+Supabase); no source code is available; and every strategy doc assumes a purpose-built architecture (canonical catalog, escrow ledger, state machines) that a demo SPA will not contain.

## 4. Verified payments & compliance picture (July 2026)

Full evidence: `research/payments-compliance-zambia-2026-07.md`. Load-bearing findings:

- **Aggregators (all BoZ-licensed, all 3 mobile-money rails unless noted):** **Lenco/BroadPay** — MTN+Airtel+Zamtel+cards, 3.5%, same-day MoMo settlement, Lusaka onboarding, public API. **Flutterwave** — all 3 rails + cards/Apple/Google Pay, ~2% local, ~24h settlement, strong docs; needs TPIN + business docs. **PawaPay** — mobile-money only, all 3 rails, 1%+MNO fee, excellent API; no cards. **Pesapal** — 3.5%, settle-on-request ≤3 days. **DPO** (the docs' original choice) — MTN+Airtel+cards, fees unpublished/negotiated, Zamtel unconfirmed. Direct MNO APIs: production access is per-MNO business KYC, negotiated fees, no public signup — poor fit for launch.
- **BoZ:** the **National Payment System Act No. 5 of 2026** (April 2026) replaced the 2007 Act. A platform that itself collects/holds/pools vendor funds risks qualifying as a PSP needing a licence; the standard compliant route is a **licensed aggregator holding funds with split/scheduled settlement**. The docs' platform-held escrow ledger needs Zambian counsel review under the new Act. **This changes the escrow architecture** — design for aggregator-held funds + platform-side ledger of record.
- **ZRA:** **Smart Invoice is mandatory since 1 Jul 2024 for all VAT-registered taxpayers** (fines to ~K120k / 3yrs; active prosecutions in May 2026). VAT registration threshold **K800k/12mo or K200k/3 consecutive months**; below that, Turnover Tax 5% (threshold now K5M — K800k–K5M overlap needs local advice). Integration is via the **VSDC REST API** (public spec on zra.org.zm) — plan the invoice pipeline day 1, activate at VAT registration. **TPIN required** for registration and business banking; also required by Flutterwave onboarding.
- **WhatsApp:** per-template pricing since Jul 2025 — **utility messages ≈ $0.006 and free inside the 24h service window**; marketing ≈ $0.0225. Order-critical flows (confirmation/delivery/OTP-adjacent) are cheap on the **official Cloud API**. Unofficial gateways (WAHA) carry a real, documented ban risk (~15–30%/yr for proactive sends) — unacceptable for order-critical messaging. **Recommendation (challenging the master prompt's WAHA-first preference):** official Cloud API from day 1 for transactional messages; WAHA at most for internal/dev experiments. SMS fallback: Africa's Talking (~K0.17/SMS) or LineServe (~K0.11/SMS).

**Proposed performance budgets (to enforce in every relevant prompt):** initial critical-path payload **≤200KB** (Bible's own target); JS **≤150KB gzipped** on customer routes; **LCP ≤2.5s on Fast-3G throttle (1.6Mbps/150ms), ≤4s on Slow-3G**; images WebP/AVIF + `srcset` + lazy-load, hero image ≤60KB; API p95 <200ms; Lighthouse mobile: Perf ≥90, SEO ≥95, A11y ≥95. Test on 360×740 viewport, Tecno/Itel class device profile.

## 5. Gaps & risks

1. **Brand/domain split** — Vergeo vs Convergeo everywhere; company name, domain, and legal entity status unconfirmed.
2. **Stack contradiction** — concept docs specify Django 5 + DRF + Next.js ×3 apps + Meilisearch + Celery/Redis on Vercel/Railway; the master prompt specifies FastAPI + Supabase + Docker/Caddy on OCI + n8n + OpenRouter. Mutually exclusive backbones; must be resolved before Phase 1.
3. **Scope contradiction for v1** — the Mountain excludes events, services, directory, AI search, real-time notifications from the 60-day MVP; the Bible builds events on Days 49–53 and ships services verticals in Phase 1; the deck and your design set (Events Desktop, AI mode) imply events + AI in v1. Unresolved = unplannable.
4. **Escrow/payout promise inconsistency** — 48h-post-confirmation release (Mountain, marketing differentiator) vs weekly settlement default (Bible services brief) vs event-specific T-7/T+1 splits vs 72h used-goods. One customer- and vendor-visible policy must be chosen.
5. **BoZ licensing risk** on platform-held escrow (see §4) — architectural, not cosmetic.
6. **ZRA never named in the concept docs** — Smart Invoice/TPIN/VAT flow is absent from all feature lists; it is now a verified legal requirement with active enforcement.
7. **Data-model fork** — Bible proposes both canonical Product+VendorListing (Products brief) and a polymorphic `Listing(kind)` primitive (Services brief), plus an Event schema that contradicts the Mountain's tickets-as-products. Needs one decision.
8. **KYC tier fork** — 3-tier (NRC/PACRA/premium) vs 4-tier incl. Tier-0 unverified listings.
9. **Vendor fee model fork** — "no monthly fees ever" (Blueprint narrative) vs subscription tiers from day 1 (Mountain revenue architecture); tier names also inconsistent (Gold top vs Platinum).
10. **Design tokens undefined** — no hex palette, no type scale; 12 design HTML files pending import; live prototype unreachable. Design system pebbles are blocked on inputs.
11. **Timeline staleness** — the 60-day roadmap's dates (start 21 Apr 2026) have lapsed; targets need re-basing.
12. **Solo-founder ops load** — manual KYC review (1–3 days), dispute SLAs, verification calls, vendor recruitment (50–100 pre-launch) all land on one person alongside a day job; plan must bias toward n8n automation + admin tooling early.
13. **Cold start** (docs' own top risk) — supply-first strategy requires vendor onboarding tooling + CSV import to be excellent early.

## 6. Blocked inputs — how to unblock

1. **Design HTML (12 files):** cloud sessions cannot run `/design-login`. Either use **"Send to Claude Code Web"** from each Claude Design project, or export each HTML and commit to `docs/designs/` using the filenames in `docs/designs/SOURCES.md`.
2. **Live prototype:** allowlist `vergeo-21ffc.web.app` in this Claude Code environment's network settings (Environment → network policy), **or** run the committed audit harness locally (`docs/designs/live-prototype/README.md`, needs Node+Chromium) and commit its output folder.

## 7. Numbered questions (answer by number; "agree" accepts the ★ recommendation)

### A. Business & model
1. **Brand + domain for v1:** (a) Vergeo / vergeo.zm ★ (consumer deck already uses it; shorter) or (b) Convergeo? Is a company registered (PACRA) yet, and under which name? Do you own the domain?
2. **v1 verticals** — which are IN at public launch? (a) Products only, (b) Products + Events ★ (events are your differentiator, designs exist, ticket QR is spec'd; services RFQ is low-build but adds ops load), (c) Products + Events + Services RFQ, (d) all incl. directory tab. B2B stays schema-latent either way ★.
3. **Vendor monetization at launch:** (a) free-only, introduce paid tiers at traction ★ (matches "only pay when you sell" recruiting pitch and cold-start reality) or (b) Free/Bronze K99/Silver K249/Gold K499 live from day 1? If (b): top tier Gold or Platinum?
4. **Commission schedule confirm:** 5% electronics / 8% home goods / 10% fashion+beauty / 12% services / 5% tickets ★ (resolves the 10-vs-12 fashion discrepancy to 10%)?
5. **Escrow/settlement promise (customer- and vendor-visible):** (a) release 48h after delivery-confirmation, payout within 24h of release ★ (the docs' marketing differentiator, feasible via aggregator scheduled settlement) or (b) weekly payout batches (Bible ops default)? Used goods 72h and event T-7/T+1 splits apply only when those verticals ship ★.
6. **Budget posture:** confirm ≤ $60–80/mo infra all-in until revenue, one-off spends ≤ $2K total ★? Any paid services you already pay for (Supabase/Vercel/OCI/Cloudinary/domain)?
7. **Timeline target:** original 60-day plan lapsed. What's the target: (a) beta in ~8–10 weeks from Phase 3 start, public ~4 weeks later ★, or (b) a hard date you have in mind?

### B. Customers & vendors
8. **Launch categories:** Bible Phase-1 set = 8 product departments (groceries/staples, personal care, fashion-new+chitenge, selective electronics, home & living, office/stationery, light hardware, event tickets) ★ — confirm or trim? (Excluded until later: salaula, used phones, fresh produce, alcohol, pharma, live animals, heavy building materials.)
9. **KYC tiers:** (a) 3-tier — T1 NRC-only instant with caps (first 5 orders ≤K500), T2 PACRA verified badge, T3 premium/API ★ — no unverified Tier-0 listings, or (b) allow Tier-0 self-listed unverified (Bible services brief)?
10. **Vendor pipeline reality:** how many committed/interested Lusaka vendors exist today? Is the personally-onboard-50–100-before-launch plan still on? (Sets priority of CSV import, onboarding UX, and seed catalog.)

### C. Payments & compliance
11. **Primary payment aggregator:** (a) **Lenco** ★ (local, BoZ-licensed, all 3 MoMo rails + cards, same-day MoMo settlement, Lusaka support — 3.5% negotiable later), (b) **Flutterwave** (~2%, best API, needs TPIN + registered business), (c) DPO (docs' original pick; unpublished fees), or (d) PawaPay now (1%, MoMo-only) + cards later? Abstraction layer regardless ★. Any existing merchant account/relationship?
12. **COD in v1:** yes, orders <K500 with pay-at-pickup-via-MoMo above that ★, or defer COD entirely?
13. **Legal/tax status today:** PACRA registered? TPIN? VAT-registered or below threshold (expect Turnover Tax 5% initially)? v1 ships ZRA-ready invoicing (sequential tax invoices, VSDC-integrable) with Smart Invoice VSDC activation at VAT registration ★ — confirm.
14. **Escrow structure:** design for aggregator-held funds + platform ledger-of-record + scheduled/split settlement, and get Zambian counsel to confirm under the NPS Act 2026 before real-money launch ★ — confirm (the alternative, platform-pooled funds, likely needs a BoZ licence).
15. **WhatsApp:** official Cloud API from day 1 for transactional messages (utility ≈$0.006, free in 24h window; WAHA ban risk documented) ★ — confirm dropping WAHA for production. Do you have a Meta Business Manager + a dedicated phone number?

### D. Logistics
16. **v1 delivery:** Lusaka-only delivery + nationwide vendor listing + customer pickup with QR+PIN ★; delivery ops = (a) manual dispatch via admin (call courier/Yango app, paste tracking) ★ (Yango API partnership is unverified for small startups) or (b) attempt Yango API at launch? Free delivery ≥K200, zones otherwise ★.
17. **Returns:** refund-only MVP (faulty/wrong item → refund from escrow; no physical-return logistics) ★ — confirm.

### E. Tech stack & hosting
18. **Backend (the big fork):** (a) **FastAPI + Supabase** (Postgres+pgvector, Auth, Storage, Realtime) ★ — matches your prompt, one managed data platform, cheap; admin UI becomes our own build (mitigated by Q20) — or (b) Django+DRF per concept docs (free admin, but fights Supabase and your stated stack)? 
19. **Frontend:** Next.js (App Router, TypeScript, Tailwind, next-intl, PWA) ★ — SEO-critical for a discovery platform, matches docs; confirm.
20. **App topology for v1:** (a) ONE Next.js app with route groups `/(shop)`, `/vendor`, `/admin` ★ (one deploy, shared UI kit, fastest for solo ops; split later) or (b) three separate apps per the Bible?
21. **Hosting:** (a) OCI VM (Docker+Caddy: FastAPI, n8n, Meilisearch-when-needed) + Supabase cloud + Vercel-or-same-VM for Next.js ★ — matches your prompt at ~$0–20/mo — or (b) Vercel+Railway per docs? Do you already have an OCI account/free-tier?
22. **Search at launch:** (a) Postgres FTS + pg_trgm + pgvector, add Meilisearch when catalog >~10–20k listings ★ (one less service to babysit) or (b) Meilisearch day 1 per docs?
23. **AI mode scope for v1:** (a) hybrid semantic search (pgvector embeddings over products/services/events/inventory) + a conversational "Ask Vergeo" assistant with structured filters (OpenRouter, cheap model, strict cost caps) ★, or (b) semantic search only, assistant Phase 2, or (c) docs' position — defer AI until 10K+ transactions? (Your addendum says AI mode in — recommend (a) with a hard monthly spend cap.)
24. **Data model:** canonical Product + VendorListing with search-and-attach (comparison view = the differentiator) + separate Event/TicketType/Ticket tables + Service listings on a shared search index ★ — i.e., Bible-Products model, NOT the polymorphic single-Listing table — confirm.

### F. Content & catalog
25. **Catalog seeding:** who builds the initial canonical catalog + category tree (~8 departments)? (a) I generate the category tree + ~100–200 canonical product stubs from the Bible's catalogue for founder review ★, (b) founder provides a spreadsheet, (c) vendors create everything (slower cold start)?
26. **Media:** product images via Supabase Storage + on-the-fly transforms ★, or Cloudinary free tier per docs? Max 8 images/product ★.
27. **Languages at launch:** (a) English UI with full i18n scaffolding (externalized strings, locale-aware ZMW/date formatting) + Bemba/Nyanja added when translations exist ★ (translation is founder effort; scaffolding is free) or (b) EN+Bemba+Nyanja fully translated at launch per docs?

### G. Launch scope — confirm explicitly OUT of v1 ★
28. Confirm ALL of these are OUT of v1 (flag any you want IN): B2B/wholesale UI (schema-latent only) · vendor subscription billing (if Q3=a) · wallet/financing/Convergeo Pay · city guides + AI trip planner · promoted-listing auctions · referral program · multi-warehouse + lot/batch inventory · POS-light · voice search · AR try-on · native Android app · Zimbabwe/cross-border · resale/ticket-transfer marketplace · same-day delivery · salaula/used-goods/fresh-produce/alcohol/pharma categories · Copperbelt delivery (month ~3) · real-time in-app notifications (WhatsApp/SMS/email cover v1) · multi-dimensional reviews (v1 = 1–5 stars + text + photos, verified-purchase only).

---

**Next:** answer §7 by number (e.g. "1a, 2b, 3 agree, …"), unblock §6 when convenient, then say **`Phase 1`** (or `Phase 1, then EXPRESS`) in a fresh session.
