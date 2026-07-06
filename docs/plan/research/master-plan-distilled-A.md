# Convergeo/Vergeo Strategic Master Plan — Distilled Brief

**File note:** The PDF is **37 pages total**, not 293 (verified via pdfinfo; 29.9MB, created 2026-07-06 with PDF24). This brief therefore covers the ENTIRE document. It is a bundle of 3 artifacts: a marketing deck, a strategy doc, and a dev roadmap.

## 1. DOCUMENT STRUCTURE

- **pp. 1–7 — "Vergeo" brand/pitch deck** (7-slide brochure, "vergeo.zm · Platform Overview 2026"): p1 cover, p2 platform overview, p3 products catalogue mockup, p4 services marketplace mockup, p5 events & ticketing mockup, p6 vendor directory mockup, p7 vendor CTA + contacts.
- **pp. 8–24 — "THE MOUNTAIN — Convergeo Strategic Master Plan"** (Confidential, April 2026, v1.0; rendered HTML with visible source comments). 10 sections: §1 75 Strategic Decisions (pp. 9–14), §2 Critical Tensions & Resolutions (pp. 14–16), §3 Platform Identity & Business Model (pp. 16–17), §4 Technical Architecture Blueprint (pp. 17–18), §5 Development Methodology (p. 19), §6 The 4 Phases of Convergeo (pp. 20–21), §7 60-Day Sprint Schedule weekly (pp. 21–22), §8 Success Metrics & KPIs (pp. 22–23), §9 Risk Register (p. 23), §10 What Happens Next (p. 24). Footer credits founder **Prosper Kaluba**; built from 75 decisions, 5 research docs, 15 Red Team scenarios.
- **pp. 25–37 — "Convergeo 60-Day Development Roadmap"** (progress-tracker artifact, last updated April 19, 2026; start date April 21, 2026; 0% complete). Day-by-day tasks in 4 sub-phases: Foundation D1–15 (pp. 25–28), Commerce Engine D16–30 (pp. 28–30), Trust & Operations D31–45 (pp. 31–33), Polish & Launch D46–60 (pp. 34–37). Every day-card has deliverables + testing checkpoint + "Plan → Approve → Code → Validate".

## 2. PRODUCT DEFINITION

- **What it is:** Zambia-wide **multivendor marketplace** for Products + Services + Events, positioned as a "commerce-powered discovery platform" — "Discover Everything Zambia Has to Offer"; "hub of logos" business directory + commerce (§3, p16). Explicitly NOT single-brand.
- **Names:** Consumer deck brand = **Vergeo** (vergeo.zm, Vergeo Technologies Ltd., Cairo Road Lusaka, hello@/vendors@vergeo.zm, +260 211 000 000); strategy/dev docs = **Convergeo**. No reconciliation given.
- **Competitor framing:** biggest competitor is WhatsApp informal sellers, not Jumia (Q71); moat = discovery + escrow trust + delivery/pickup convenience + verified reviews.
- **Customers:** Zambian consumers (18–35 marketing focus), all 10 provinces; B2B buyers via bulk/RFQ (later phase). Vendors: market traders (NRC-only KYC) up to registered companies (PACRA docs); service professionals; event organisers.
- **Revenue streams (§3, pp16–17):** (1) variable category commissions — 5% electronics, 8% home goods, 10% fashion/beauty, 12% services, 5% event tickets; (2) vendor subscriptions — Free / Bronze K99/mo / Silver K249/mo / Gold K499/mo; (3) events 5% ticket commission + promoted event listings; (4) future auction-based promoted listings. Vendor pitch: "no monthly fees — only pay when you sell" (free tier).
- **Ownership/ops:** solo founder + AI tools, private limited company via PACRA, ~$2K bootstrap, 5-year super-app vision, Zimbabwe as first expansion, seek investment after 1,000+ orders/month.

## 3. FEATURES & MODULES

- **Product catalog:** 8 categories, hierarchical categories (MPTT, unlimited nesting), SKU/ZMW pricing/stock, variants (size/color) with own price/stock, up to 8 images, approval workflow Draft→Pending→Published/Rejected.
- **Canonical product + VendorListing model:** shared product images/specs; vendors attach listings (price, stock, delivery options, condition new/used); comparison view of same product across vendors sorted by price/distance (p18 data model).
- **Search:** Meilisearch typo-tolerant instant search (<50ms/10k products), faceted filters (category, price, vendor, rating, availability, location), autocomplete, sorting; pgvector for semantic/AI-ready; Postgres full-text fallback; Bemba/Nyanja handling.
- **Location-aware tags:** Nearest / Cheapest / International / 7-Day Wait product tags (deck p2–3).
- **Cart/checkout:** session + user carts, Redis persistence, anonymous→user merge, stock validation/reservation, multi-vendor order splitting into vendor sub-orders, multi-step checkout (address/pickup → delivery → payment → confirmation).
- **Orders:** state machine Placed→Confirmed→Processing→Shipped→Delivered→Completed, transition validation, audit event log, cancellation/refund by state, tracking timeline UI.
- **Payments/escrow:** DPO Pay (cards + MTN MoMo, Airtel Money, Zamtel Kwacha), payment abstraction (strategy pattern), full escrow ledger, settlement engine (commissions, payout batches), transaction ledger, refunds; Lenco added Phase 2.
- **Pickup/delivery:** QR code per order + PIN backup, vendor camera scanner, pickup point model, delivery zones + fee calculation, Yango API integration, pass-through tracking.
- **Reviews:** verified-purchase only, 1–5 stars, multi-dimensional (quality/delivery/communication per Q32), text + photo/video, vendor responses, aggregation, moderation flags.
- **Vendor portal:** tiered onboarding (instant basic; 1–3 day verified), tiered KYC (NRC vs PACRA), status machine Applied→Under Review→Approved/Rejected, dashboard (sales, orders, product stats), product/inventory management (manual + CSV bulk + API for POS), low-stock alerts, order fulfillment (confirm/reject, pick/pack/ship, tracking), profile (location/hours/description; richer with paid tiers), progressive analytics by tier.
- **Admin panel:** role-based (superadmin/moderator), vendor approval + KYC review, product moderation queue, user suspend/ban, disputes, platform analytics (GMV, revenue, commission engine per-vendor/per-category, top vendors/products, CSV export, payout reconciliation), admin audit log.
- **Events & ticketing (Phase 2):** all event types, in-app tickets with dynamic QR refreshing every 60s (anti-screenshot), 5% fee; deck shows event cards with capacity/"spots left".
- **Services (Phase 2):** quote-request model ("post a job", providers respond) — no booking calendar; 6 categories (home repair, technology, catering, energy, creative, logistics).
- **Business directory:** first-class nav tab; vendor profiles double as directory entries (Phase 2).
- **Notifications:** email (SendGrid/Mailgun), SMS (Africa's Talking OTP/status), in-app real-time (Supabase Realtime / WebSocket-or-polling), WhatsApp Business API (Meta Cloud API or BSP) with template messages, opt-in/out, SMS fallback; per-user channel preferences.
- **Disputes:** customer submission with evidence, vendor response, admin resolution, full/partial refunds from escrow, auto-release after dispute window (~7 days post-delivery).
- **Automation:** n8n (self-hosted) — order processing, vendor onboarding sequences, daily/weekly reports, abandoned cart recovery (email + WhatsApp), review requests; Celery for code-level async.
- **AI (phased):** rule-based "smart" features first; then AI product descriptions (photo→listing), personalized recommendations, conversational search ("find me a red dress under K200 near me"), fraud detection, price optimization, AI trip planner, voice search in Bemba/Nyanja; ML only at 10K+ transactions.
- **Other roadmap items:** referral program (K20/K20), city guides (Lusaka, Livingstone, Ndola/Copperbelt), in-platform pre-purchase messaging, B2B tiered volume pricing + RFQ, promoted listings, PWA (offline cached catalog, push), React Native Android app (Phase 4), Convergeo Pay wallet, airtime/bill payments, vendor financing via MFIs, virtual try-on/AR, pickup point network (Shoprite, Puma stations).
- **i18n:** English + Bemba + Nyanja at launch (~80% population); Tonga/Lozi/Kaonde/Luvale later.
- **Auth:** phone OTP (Africa's Talking) primary or email, + Google/Facebook social login; JWT (simplejwt).

## 4. DESIGN/UX

- **Mockups (deck, pp1–7):** p1 hero split-screen (serif display headline "Shop Everything. Ship Anywhere.", stat row, dark photo panel with feature chips); p2 four pastel module cards (Shop/Services/Events/Vendors) + 6 feature tiles; p3 product grid cards — vendor eyebrow, K-prices with strikethroughs, badges (Best Seller/Local/Handmade/Sale/Top Rated/Natural/New) + location tags; p4 service cards with **category color coding** (Home Repair pink/red, Technology indigo/blue, Catering orange, Energy green, Creative amber, Logistics navy — labeled "Themed UIs"); p5 event cards (date, venue, price, capacity bar, "spots left", category + Featured/Selling Fast/New/Free badges); p6 vendor directory cards (tier badge, category, rating, product count, region) + tier legend; p7 dark CTA + contact panel.
- **Deck visual language:** cream/off-white background, dark navy serif headlines (Playfair-style), sans-serif body, dark aubergine/near-black panels, pastel card fills, pill-shaped tags, "K" Kwacha pricing. No explicit hex tokens/typography names stated anywhere.
- **Homepage IA (Q30, p11):** hero search bar → events → curated collections/categories+logos → trending, infinite scroll, mini expandable footer. Week 6 finalization: hero → upcoming events placeholder → categories → trending → vendor spotlight.
- **Planned design work:** low-fidelity wireframes for homepage/product/cart/checkout in Week 1 (p21); shared UI component library (buttons/inputs/cards/modals) D10–11; mobile-first at 320/768/1024 breakpoints; test on cheap Android (Tecno, Itel) at 3G; WCAG 2.1 AA, Lighthouse Accessibility 95+; skeleton/empty/error states; cross-browser incl. Samsung Internet.
- **Strategy docs styling:** Mountain doc = red/crimson hero, amber tension cards, green resolution boxes; Roadmap = phase banners color-coded blue/crimson/orange/green with day cards + checklists (relevant only as internal tracker UI).

## 5. PAYMENTS / LOGISTICS / COMPLIANCE

- **Mobile money non-negotiable day 1:** MTN MoMo + Airtel Money (+ Zamtel Kwacha in deck & roadmap); 70%+ of Zambian digital payments are mobile money; USSD prompt flow UI.
- **Aggregators:** DPO Pay primary (mobile money + Visa/Mastercard); Lenco secondary/Phase 2 (bank transfers + developer API); long-term acquire/partner with licensed fintech rather than build. Apply for DPO production credentials Week 1; integration starts Week 3; manual bank-transfer fallback.
- **Escrow:** full escrow, ledger-based (not bank sub-accounts); auto-release 48h after delivery confirmation OR 7 days after shipping (whichever first); disputes extend hold; vendor settlement in 48h ("fastest in Zambia"; competitors 7–14 days), instant settlement only after K10,000+ float (~month 3–4).
- **COD:** allowed under K500; pay-at-pickup via mobile money for larger orders.
- **Currency:** display any currency (FX API), settle only ZMW.
- **Tax/legal:** below K800K turnover = no mandatory VAT registration (consult tax advisor); VAT-ready architecture (per-category VAT toggle) from day 1; PACRA private-limited registration Week 1; Zambia Data Protection Act-compliant privacy policy/ToS (Week 7); GDPR-ready architecture (encryption, consent tracking, audit logs) with formal GDPR certification deferred (pro setup would cost K25,000–K50,000+).
- **Delivery:** aggregation layer over Yango + local couriers (Zampost, private); launch = delivery Lusaka-only, self-pickup nationwide, vendors list nationwide; Copperbelt (Ndola, Kitwe) month 3; 1–3 day standard, no same-day; hybrid: platform-managed small items, vendor-managed large (furniture/appliances); pass-through partner tracking via APIs/webhooks; free delivery above ~K200 order value; no returns in MVP (refund-only for faulty/wrong; physical returns v2). Deck brands this "Vergeo Logistics."
- **WhatsApp:** #1 competitor (informal sellers); support channel (vendor beta group; WhatsApp + AI chatbot + phone for K500+ issues); WhatsApp Business API for order confirmations/shipping/delivery notifications + vendor new-order alerts with SMS fallback; later order placement/tracking via WhatsApp + abandoned-cart nudges.
- **SMS/OTP:** Africa's Talking, ~$0.02/SMS.

## 6. TECH STACK

- **Backend:** Django 5.x + DRF + PostgreSQL 16 with pgvector + Celery + Redis (Upstash free tier, 10K commands/day). Custom User model (phone primary identifier), django-allauth, simplejwt, django-treebeard/MPTT, meilisearch-python.
- **Frontend:** Next.js 14+ App Router + TypeScript strict + Tailwind CSS + Zustand + React Query; next-intl; PWA-first (no app store). One shared REST API, **three separate frontend apps**: Customer (PWA), Vendor (SPA), Admin (SPA), in a monorepo (apps/api, apps/customer, apps/vendor, apps/admin, packages/types, packages/utils).
- **Hosting:** Vercel (3 frontends, free tier) + Railway/Render (Django API + Postgres + Meilisearch, ~$7–20/mo) + Cloudflare CDN/DNS (free); Docker Compose local; PgBouncer in production.
- **Services:** Cloudinary (images, 25GB free), Supabase Realtime (notifications), Africa's Talking (SMS/OTP), Meilisearch (search), n8n self-hosted (workflows), Sentry free tier + UptimeRobot (monitoring), GA4.
- **Methodology (§5, p19):** OpenAPI 3.1 contract-first (single source of truth; auto-gen TS types + Pydantic models); "AI Council" — Claude Code generates, Gemini CLI (1M context) reviews, Cursor for UI, human approves; Plan→Approve→Code→Validate; AI_CONTEXT.md persistent memory + NotebookLM; atomic modules; CI/CD gate (ruff/eslint, mypy/tsc --strict, pytest/vitest, spectral OpenAPI lint, schemathesis/dredd contract tests); git branch guardrails.
- **Perf/security targets:** API p95 <200ms (p99 <500ms under load), homepage <2s on 3G, Lighthouse SEO 95+/Perf 90+/A11y 95+, cache hit >80%, OWASP Top 10 audit, rate limiting, HSTS/CSP headers, load test 100 concurrent users (k6/Locust), Playwright E2E.
- **Est. infra cost:** $30–60/mo (~$62/mo itemized: hosting $30, Meilisearch $10, domain $2, SMS $20, n8n $0).

## 7. PHASING / SCOPE

- **MVP (Days 1–60, "Foundation MVP"):** working multivendor marketplace — customer browse/search/cart/DPO checkout/QR pickup/order tracking/reviews/PWA; vendor KYC/listings/orders/basic analytics; admin approvals/moderation/disputes/metrics; escrow + 48h settlement; Lusaka delivery + nationwide pickup; n8n emails + OTP; EN/Bemba/Nyanja UI. **Explicitly NOT in MVP (p20):** events/ticketing, B2B wholesale, business directory, AI search, city guides, advertising, referral program, quote-request services, Lenco, real-time notifications.
- **Phase 2 (Days 61–120):** events+ticketing, business directory tab, quote-request services, referral program, subscription tiers, Lenco, Supabase real-time, Copperbelt delivery, messaging, comparison view, AI descriptions.
- **Phase 3 (Days 121–240):** recommendations, city guides, conversational AI search, fraud detection, advanced analytics, B2B (volume pricing + RFQ), WhatsApp Business API, abandoned cart, promoted listings, multi-city delivery.
- **Phase 4 (Months 9–18+):** super-app — airtime/bills, AR try-on, Convergeo Pay wallet, vendor financing, voice search, React Native Android, Zimbabwe, AI trip planner, price optimization, pickup-point network.
- **60-day execution:** Mountain §7 weekly plan (W1 contracts/scaffold → W2 users/catalog → W3 vendor+cart/checkout → W4 payments/escrow → W5 delivery/reviews/admin → W6 i18n/PWA/SEO polish → W7 testing + 20–30-user invite-only beta → W8 fixes/pre-launch → D57–60 public launch). Roadmap doc re-slices same 60 days into Foundation D1–15 / Commerce D16–30 / Trust & Ops D31–45 / Polish & Launch D46–60 with quality gates at D15/30/45/60. Launch style: quiet invite-only beta → public (Q54). Pre-launch in parallel: PACRA + personally onboard 50–100 Lusaka vendors (target 75–100 live at launch; never launch <50).

## 8. NUMBERS

- **Budget:** <K50,000 (~$2,000 USD) total bootstrap; infra ~$62/mo ($744/yr) = ~15 months runway. FX assumption ~K25/USD.
- **Commissions:** 5% electronics, 8% home goods, 10% fashion/beauty, 12% services, 5% event tickets (Q2 example says "12% fashion"); event fee policy 5–10%, start 5%.
- **Subscriptions:** Free (20 products) / Bronze K99/mo (100 products, verified badge, −1% commission) / Silver K249/mo (unlimited, priority search, bulk upload) / Gold K499/mo (homepage rotation, API, competitor insights, video profile).
- **Thresholds:** free delivery >K200 order; COD <K500; human support review K500+; new-vendor cap first 5 orders K500 each; escrow release 48h/7-day rules; VAT registration threshold K800K.
- **Referral:** K20 credit each to referrer + referee.
- **Targets:** Month 1 — 50–100 orders, 75–100 vendors (5+ products each), GMV K10,000–25,000 (~$400–1,000), revenue K800–2,000, >90% payment success, >80% order completion, 0 disputes >72h, 0 payouts >48h. Month 6 — 300–500 orders/mo, 200+ vendors, 2,000–5,000 users, GMV K75,000–125,000, revenue K6,000–12,000, >20% repeat purchase, NPS >40. Month 12 (break-even) — 1,000+ orders/mo, 500+ vendors, 10,000+ users, GMV K250,000+ (~$10K), revenue K25,000+ (~$1,000)/mo → then fundraise + Zimbabwe. Year-1 raw answers: 10,000–25,000 customers (reframed to 1,000 active buyers), 200–500 vendors. Revenue modeling: 200 orders/mo × K250 × 8% = K4,000 (~$160) + 20 Bronze subs K1,980 (~$79) ≈ $239/mo by month 6–8; 500 orders + 50 subs ≈ $600/mo at month 12.
- **Market data:** 70%+ of Zambian digital payments = mobile money; 78% of Zambian internet users are mobile; competitor vendor settlement 7–14 days; ~3% visitor→registration conversion assumption (needs ~500K visits for 10K+ signups).
- **Deck (aspirational) figures:** 12,400+ products, 840+ vendors, 6+ service categories, 10 provinces, 24 events/month, 12,000+ attendees; sample prices K185 (25kg maize meal) to K18,900 (iPhone 15 Pro Max); services from K350–K2,500; tickets Free–K250.
- **Risk register (p23):** cold start HIGH, payment integration failure HIGH, founder burnout MEDIUM, vendor fraud MEDIUM, competitor first-mover LOW-MED (each with mitigations).

## 9. OPEN QUESTIONS / CONTRADICTIONS

1. **Page count:** file is 37 pages, not the stated 293 — either wrong file or the 293-page version wasn't uploaded.
2. **Brand name unresolved:** consumer deck = "Vergeo"/vergeo.zm/Vergeo Technologies Ltd.; strategy + roadmap = "Convergeo". No mapping stated.
3. **Deck vs plan reality gap:** deck presents 840+ vendors, 12,400+ products, nationwide "Vergeo Logistics" delivery, live events, priced bookable services, and B2B "supported" as current facts; the plan launches with 75–100 vendors, Lusaka-only delivery, and defers events, services, B2B, and directory to Phases 2–3. Deck is aspirational mock, not launch scope.
4. **Two conflicting "4 Phases":** Mountain §6 (Phase 1 = whole 60-day MVP; 2 = D61–120; 3 = D121–240; 4 = M9–18+) vs Roadmap doc (Phases 1–4 = D1–15/16–30/31–45/46–60 within the MVP). A reader must know which "Phase 3" is meant.
5. **WhatsApp Business API timing conflict:** Mountain defers it to Phase 3 (D121–240) and excludes real-time notifications from MVP; Roadmap builds in-app real-time notifications (D39–40) and full WhatsApp Business API (D41–42) inside the 60 days.
6. **Subscription tier naming mismatch:** deck + Q4 use Bronze/Silver/Gold/**Platinum**; §3 revenue architecture defines Free/Bronze/Silver/**Gold** (no Platinum).
7. **Zamtel:** deck + roadmap include Zamtel Kwacha mobile money; Q20 commits only to MTN + Airtel day 1.
8. **Fashion commission inconsistency:** Q2 example "12% fashion" vs §3 "10% fashion/beauty, 12% services".
9. **Break-even arithmetic muddled (p17):** claims "~K775/month GMV ($31)" covers ~$62/mo costs at 8% commission ("4 orders at K200") — 8% of K775 ≈ K62 (~$2.5), not $62; K/$ units are conflated. Real infra break-even GMV is ~K19–20K/mo.
10. **Review scope ambiguity:** MVP list says reviews = "5-star + text + verified badge" while Q32/Week 5 spec multi-dimensional ratings (quality/delivery/communication) + photo/video.
11. **Timeline staleness:** roadmap start April 21, 2026, 0% complete tracker; PDF assembled July 6, 2026 — the 60-day schedule dates are already past as of the document's own creation date.
12. **Services pricing model tension:** deck shows fixed "from KXXX" service pricing; plan's chosen model is quote-request with no prices/calendar.
13. **Q24 tax posture unresolved by design:** "consult with tax advisor before deciding" — VAT approach intentionally open.