# DOCUMENT 1 — Convergeo_Strategy_Bible.pdf
`/root/.claude/uploads/ca3bf6a9-5ac0-59de-8d61-e7dcc0c18e35/8e747cb5-Convergeo_Strategy_Bible.pdf` — **actually 99 pages, not 13** (PDF24, dated 2026-07-06). It is a bundle of 4 "Companion Briefs to the Strategic Master Plan" (all "Prepared: April 2026"). The Master Plan itself (75 decisions "Q1–Q75", 60-day roadmap, schema, wireframes) is referenced constantly but **not included in either PDF**.

## 1. SECTION MAP (PDF page numbers)
**Brief A: Events Strategy & Ticketing Architecture (pp.1–23)**
- p.2 links to Master Plan (Q49 all-event-types, Q50 dynamic QR, Q5 commission, Day 49–53 build); why events ≠ products-with-dates
- pp.4–5 five event types + schema (Event/EventInstance/TicketType/Ticket)
- pp.6–7 six ticket pricing modes; capacity-as-tree; fees; event escrow timing
- pp.8–9 time-first discovery (When/What/Where lenses, ranking signals, "Tonight+This Weekend" default, calendar view Ph2, city-guide integration Q52)
- pp.10–11 dynamic QR mechanics (HMAC), PIN backup (Q33), transfer rules, door/scanner flow, refund matrix
- pp.12–13 organiser onboarding (2 tiers), 3-screen creation flow, co-organiser roles (Owner/Manager/Door), promo tools, 4-number analytics
- p.14 fraud (buyer-side, organiser no-show, disputes)
- pp.15–20 event catalogue: ~65 sub-categories / 11 categories
- pp.21–22 phased events launch; p.23 summary ("16 behavioural patterns, 275+ supply types")

**Brief B: Product Strategy & Catalogue Architecture (pp.24–46)**
- p.25 builds on canonical Product/VendorListing (Q12, Q41)
- pp.26–27 five product classes A–E; product_class enum; nullable product_id for D/E
- pp.28–29 six pricing modes; sale_unit/base_unit price-per-kg normalisation; FX (Q23: display any currency, settle ZMW; USD-pegged imports, FX locked at order)
- p.30 condition enum + evidence (IMEI/VIN/salaula photos); counterfeit defences; used = 72h escrow
- p.32 stock modes (tracked / made-to-order / by-weight / always-available); 10–15-min checkout reservation; cancel-rate 5% warn / 10% auto-suspend; POS-light Ph3
- pp.33–34 five vendor listing flows (search-and-attach; submit-new-canonical + moderation; commodity quick-list; unique-item; made-to-order template) + CSV/API bulk (Q39)
- p.35 discovery add-ons (in-stock boost, below-median price boost, browse/search/ask, 2–3x geo weight for Class C)
- pp.36–43 product catalogue: ~100 sub-categories / 13 departments with regulator flags
- pp.44–45 phased product launch; p.46 summary

**Brief C: Business, Pipelines & Three-Frontend Architecture (pp.47–76)**
- pp.48–49 Alibaba (1688/Taobao/Tmall/Alibaba.com) + Alipay benchmark → 3 frontends + B2B mode-toggle at $2K bootstrap
- p.50 six business archetypes (Market Trader, Registered Retailer, Service Professional, Manufacturer, Importer/Wholesaler, Event Organiser)
- pp.51–53 per-archetype support across 4 supply types; warehouse-aware inventory (Warehouse, InventoryLot, wholesale_pool_quantity; lot/batch, FIFO, goods-received, reorder alerts)
- pp.54–57 the three frontends in detail (Customer PWA / Vendor mobile+desktop / Admin command centre incl. n8n automations, Q63 solo-founder rationale)
- pp.58–59 B2B layer: who sells/buys, tiered pricing, MOQ, bulk RFQ, Net-30/60, account managers, contract pricing; Mwansa bakery worked example
- pp.60–61 supply pipeline, 9 stages (production → discovery activation → health monitoring)
- pp.62–63 demand pipeline, 12 stages (discovery → dispute)
- p.64 seven pipeline intersection points
- pp.66–67 phasing: Ph1 B2B latent-in-schema; Ph2 B2B live; Ph3 financial layer; Ph4 Year-2 (Convergeo Express, credit, Zimbabwe Q73)
- p.68 Alipay-shaped financial ladder (escrow → wallet Y1 → working-capital lending Y2 → off-platform payments/bills Y2–3 → wealth/insurance Y3+)
- pp.70–74 business/vendor catalogue: ~60 business types (Zambeef, Trade Kings, Shoprite, Link, Lafarge, etc.)
- pp.75–76 summary ("built in 60 days on $2K by a solo founder using AI tools")

**Brief D: Multi-Vendor Commerce & Services Platform (Services brief) (pp.77–99)**
- p.78 executive framing + market signals (mobile money, 58% GDP services, 70% informal employment, no incumbent)
- pp.79–80 core architecture: polymorphic Listing primitive (kind: product|service|event|rental|space|menu_item, JSON attributes); Vendor→Location→Listing; Category+Tags taxonomy; vendor dashboard scope
- pp.81–82 six transaction archetypes (Buy-now, Bookable, Reservation/stay, Walk-in, Quote-based, Event ticket); vendor-controlled storefront; **trust tiers 0–3** (0 self-listed unverified, 1 NRC+PACRA, 2 regulator licence, 3 "Convergeo Preferred" earned)
- pp.83–85 discovery: vector RAG + geo (semantic document, query expansion, hybrid BM25+vector with RRF, geo/open-now/Bayesian-quality/verification re-rank, map+list UI, "New in town" / "Around me" / "On the route" flows, conversational assistant + voice)
- pp.86–94 services catalogue: ~110 sub-categories / 14 verticals with regulators
- pp.95–96 launch phasing (Lusaka months 0–4 → Copperbelt 4–9 → long tail/rural 9–18)
- pp.97–98 payments/trust/ops realities (mobile money native, aggregators, escrow, weekly payouts, <200KB payload, USSD, WhatsApp, localisation)
- p.99 defensibility summary

## 2. PRODUCT DEFINITION
- Convergeo = national multi-vendor **hybrid marketplace → super-app** for Zambia: "unifies products, services, events, and inventory under one discoverable surface"; explicitly benchmarked as Alibaba's 4 platforms compressed into one platform with role-aware UI + Alipay-style trust/financial ladder.
- Model: commission-based multi-vendor marketplace (B2C) + latent B2B wholesale layer (mode-toggle: wholesale tiers, MOQ, RFQ, Net terms, invoices, multi-user business accounts) + vendor SaaS-ish tooling. Not a storefront; vendors can be sellers and B2B buyers simultaneously.
- Verticals: 4 supply types — products (5 classes A–E, ~100 sub-cats/13 depts), services (6 archetypes, ~110 sub-cats/14 verticals), events (5 types, ~65 sub-cats/11 cats), inventory/B2B stock. Total claim: 16 behavioural patterns, 275+ supply sub-categories, 60+ business types, one schema.
- Target users: consumers (mobile-first, budget Android/3G), informal traders → premium brands (6 vendor archetypes, tiered KYC), registered business buyers (B2B), event organisers (2 tiers), tourists/travellers (city guides, "on the route"), solo-founder operator (Admin).
- Revenue: transaction commission variable by category (Q2: e.g. 5% electronics, 12% fashion); ticket commission 5–10% (Q5; floor 5% first 12 months, 8–10% premium later; free events never commissioned); vendor subscriptions Bronze/Silver/Gold/Platinum (Q4); later: promoted-listing auctions ("revenue Layer 4"), Tier-3 API/ERP access, financial layer (working-capital advances, e.g. 4% fee), Net-terms credit.

## 3. FEATURES & MODULES (1-line each)
- Polymorphic Listing primitive + JSON attributes: one search index, cart, reviews, analytics across all kinds.
- Vendor→Location→Listing hierarchy: multi-branch businesses with per-branch hours/staff/GPS/stock.
- Category tree (2–3 levels) + moderated free-form tags.
- Canonical Product vs VendorListing (golden record + per-vendor offers); comparison view "7 vendors selling this", sort nearest/cheapest.
- Product classes A–E with per-class listing flows: search-and-attach (<30s), submit-new-canonical moderation queue (auto-approve dupes; reward adopted submissions), commodity quick-list (3 taps + photo), unique-item (Class D, evidence photos), made-to-order template + spec form (Class E).
- Six product pricing modes: per-unit, per-weight/volume, per-bunch/heap, tiered/volume, from/range, quote-only; price-per-base-unit auto-computed.
- Condition enum (New / open-box / Refurbished / Used Exc-Good-Fair / for-parts) with mandatory evidence (IMEI, VIN+mileage, actual salaula photos).
- Counterfeit defence: Tier 2+ only for cosmetics/pharma; brand-claim of canonical pages; one-tap "this looks fake".
- Stock: tracked / made-to-order capacity+lead-time / by-weight bulk / always-available; checkout reservation 10–15 min; low-stock + reorder alerts; POS-light off-platform sale marking (Ph3, 0.5% commission discount).
- Warehouse-aware inventory: multi-warehouse routing to nearest depot, lot/batch + expiry FIFO, goods-received (scan/CSV/manual), wholesale-vs-retail stock pools, production lead-time.
- Services: 6 archetypes; calendar/availability/blackout/multi-staff; RFQ inbox ("3–5 providers reply in an hour"); deposit+balance payments; portfolio gallery; visible response-time badge.
- Events: 5 types; 6 ticket pricing modes (fixed, multi-tier, early-bird schedule, group/table, free RSVP, pay-what-you-want Ph3); capacity tree + oversell validation; dynamic QR (HMAC over 60s time-windows, offline scanner cache, first-scan-wins), 6-digit PIN backup; transfer until T-6h, resale blocked; scanner mode + live attendance counter; refund/cancel/reschedule matrix; organiser tiers/caps; co-organiser roles via SMS invite; promo codes, affiliate links, OG share links, email/SMS to past attendees; 4-number organiser analytics incl. predicted attendance.
- Discovery: Meilisearch (Q15) + pgvector (Q14) hybrid, RRF fusion, query expansion via LLM/cache, geo (Haversine→OSRM/Google), open-now boost, Bayesian rating, verification boost, personalisation; time-first for events ("Tonight + This Weekend" default, sell-through "selling fast" badge), 2–3x distance weight for commodities, in-stock and below-median-price boosts; browse/search/ask modes; conversational AI assistant + voice input; "New in town", "Around me now", "On the route" flows; map+list UI.
- Checkout: multi-vendor cart with sub-orders, anonymous→auth cart merge, address or pickup-point (Q44), zone-based delivery fees, free-delivery nudge (Q6 K200+), payment picker (mobile money/card/COD Q25), escrow 4-step tracker (Q22).
- Post-order: state machine Placed→Confirmed→Processing→Shipped→Delivered→Completed; WhatsApp/SMS/push updates (Q68); QR+PIN pickup (Q33); 48h auto-confirm; verified-purchase reviews (Q32); one-tap reorder; disputes with evidence + admin resolution (Q62); back-in-stock notifications.
- Vendor frontend: mobile daily-driver vs desktop dashboard; catalogue/inventory/orders/B2B inbox/CRM-light/marketing/payouts+tax-ready exports (Q24)/storefront customisation (Q72 "hub of logos")/insights (search terms landed).
- Admin frontend: vendor KYC review, moderation queues, order ops + manual escrow release, trust&safety thresholds, GMV/commission/payout/subscription/reconciliation (DPO+Lenco dual, Q19), cohort + search analytics, live monitoring, n8n-automated ops (abandoned cart, onboarding sequences) — Q63 solo-founder multiplier.
- B2B: tiered price arrays, MOQ, bulk RFQ, Net-30/60 (platform fronts cash; Year 2 earliest), account managers, contract pricing; tax-compliant invoices; multi-user business accounts.
- Financial roadmap: escrow → Convergeo Wallet (free instant internal transfers) → working-capital advances → QR-pay at外 merchants/bills (ZESCO, DSTV)/airtime/P2P → savings/micro-insurance/credit scores.
- Ops/localisation: USSD vendor actions, WhatsApp first-class channel, <200KB initial payload, plot+landmark+mandatory GPS-pin addressing, +260 multi-line phone handling, multi-segment opening hours, English/Bemba/Nyanja (Q27).

## 4. STRATEGY
- Positioning: "the only place in Zambia where any vendor — formal or informal — can show up, get found by intent rather than by knowing-the-name, transact on rails customers already use, and accumulate a portable reputation." Super-app = commerce + services + events in one transaction layer (no Zambian incumbent does this; directories are static yellow pages; events compete vs Lusaka365/Facebook Events).
- Differentiation: canonical catalogue + comparison; escrow trust; time-first event discovery; dynamic QR done properly; price-per-kg normalisation vs WhatsApp sellers; response-time badges; regulator-tied verification; "on the route" long-tail geo; progressive formalisation on-ramp (Tier 1 → PACRA); 16-patterns-one-schema as the moat.
- GTM: hand-recruit 200–300 Lusaka vendors (services Ph1, 8 verticals); events Ph1 recruit 5–10 workshop facilitators, 2–3 comedy/theatre venues, 3–5 supper clubs; free-RSVP events free forever to populate calendar; influencer promo/affiliate links (Q28 TikTok/Instagram); school-season and Sept–Nov planting-window campaigns; B2B upsell path for existing vendors.
- Brand identity: no colours/voice defined for Convergeo itself (vendors get logo/theme-colour controls). Design principle quoted: Jack Ma "when you try to please everyone you please no one"; tone of briefs favours "visible reassuring state" trust UX.

## 5. PAYMENTS / LOGISTICS / COMPLIANCE
- Payments: native MTN MoMo, Airtel Money, Zamtel Kwacha (USSD push, not redirects) rather than single aggregator; aggregator layer for cards/fallback — ZynlePay, DPO Pay, Pesapal, Flutterwave, swappable abstraction; Master-Plan Q19 = dual gateway DPO + Lenco (dual reconciliation); COD where allowed (Q25); Visa/Mastercard via DPO.
- Escrow: hold until customer confirms or fixed 24–48h window; used goods 72h; events: <14 days out → settle T+24h; ≥14 days out → 50% at T-7 / 50% at T+1; free RSVP no escrow; dispute auto-resolve for buyer if organiser silent 72h.
- Payouts: **weekly settlement default** to mobile money/bank ("daily sounds vendor-friendly but fragments ops and raises fees").
- Logistics (Q43/Q45 hybrid): platform-aggregated small-item delivery via Yango/local couriers; vendor-managed for heavy goods; customer pickup with QR+PIN (Q33/Q44); pass-through tracking (Q47); zone-priced delivery, free ≥K200 (Q6); nearest-warehouse geographic routing; conservative lead-time quoting; cold chain flagged for meat/fish/dairy; same-day-only fresh produce; local-pickup-only live animals; age verification at delivery + restricted hours for alcohol; own network "Convergeo Express" deferred to Year 2+.
- Compliance: NRC (Tier 1), PACRA (Tier 2); sector licences required for Tier-2 verification per category — ZAMRA (pharma/OTC only via licensed vendors; prescriptions excluded), HPCZ (clinics/medical), ERB (solar/electrical), RTSA (transport/driving schools; "ZMRA" as written), NCC grades 1–6 (contractors), ZIA, EIZ/SIZ, ZIEA (real estate), LAZ, ZICA, PIA, BoZ (mobile money agents/microfinance), ZICTA, Tourism Council, Vet Council, ZEMA (pesticides/pest control), WARMA (boreholes), DNPW, ZABS, Liquor Licensing Board, local councils, TEVETA/HEA, Ministries (Health/Education/Agriculture), Dept of Maritime, DoF, ZARI. Tax: "VAT-ready architecture" (Q24), tax-ready vendor exports, auto tax-compliant B2B invoices, manufacturer→distributor→retailer chain tracked "for taxation and trust traceability". **ZRA never named.** WhatsApp: first-class channel (booking confirmations, reminders, chat, vendor order alerts Q68, low-stock alerts, account-manager contact, ticket transfer delivery).

## 6. TECH STACK & ARCHITECTURE
- Three frontends (Customer PWA Q34 / Vendor / Admin) sharing **one Django REST API** (Q12); PostgreSQL; pgvector (Q14) + **Meilisearch** (Q15) hybrid search with RRF; Cloudinary image pipeline (Q16); n8n automation (Q66); embeddings via multilingual model (named options: OpenAI text-embedding-3-large, Voyage AI, Cohere embed-multilingual); pgvector now, Qdrant/Weaviate if 100k+ listings; OSRM self-hosted or Google Distance Matrix; USSD channel; WhatsApp/SMS messaging; AI feature order per Q67: descriptions → fraud → pricing.
- Schema decisions: canonical Product + VendorListing (product_id nullable, product_class enum A–E); sibling Event/EventInstance/TicketType/Ticket subtree (proposed, vs Master Plan's ticket-as-product-flag); polymorphic Listing with kind discriminator + JSON attributes (services brief); Vendor→Location→Listing; Warehouse/InventoryLot/wholesale_pool_quantity; price_tiers arrays; B2B latent-in-schema from day 1; atomic order creation with stock reservation; state machines for orders.
- Constraint framing: $2K bootstrap, solo founder + AI tools (Q63), 60-day build; admin designed so "could AI or n8n do this?".

## 7. PHASING / SCOPE
- MVP (Day 60): B2C PWA complete; single-warehouse inventory; retail pricing only; search-and-attach; escrow + mobile money; 3 frontends (Vendor basic); events built Days 49–53. Targets: 75–100 active vendors ×≥5 products; 50–100 orders/month.
- Product Ph1 departments (8): groceries/staples, personal care (Tier2+ makeup, no fragrances), fashion (chitenge + new retail, no salaula), selective electronics (Itel/Tecno, accessories, solar kits; no used phones), home & living (no used/made-to-order), office & stationery, light hardware (no cement/sand), event tickets.
- Services Ph1 (Lusaka, months 0–4, 8 verticals): beauty; restaurants/cafes/bars; lodges/guesthouses; gyms; mechanics/car wash/tyres; printing/creative; clinics/dental/pharmacies; home services.
- Events Ph1 (6 categories): workshops/education, comedy/theatre, pop-up dinners, cultural & arts, lifestyle/community, free RSVP broadly.
- Ph2 (months 3–6 / 4–9): B2B mode live at 300–500 orders/month (tiered pricing UI, business-mode toggle, bulk RFQ, multi-warehouse, lot/batch, invoices); fresh produce (Lusaka pilot), used goods incl. vehicles, heavy building materials, agri inputs (planting window); concerts, conferences, sports, fashion shows, multi-day events; city guides; calendar view (50+ events); tutoring/professional services/real estate/construction/tourism; Kitwe/Ndola/Livingstone.
- Ph3 (months 6–12 / 9–18): Net-30/60 credit, account managers, contract pricing, Convergeo Wallet, demand forecasting; made-to-order, OTC pharma, crafts, live animals, alcohol delivery; international concerts (8–10% commission, mandatory verification calls), religious at scale (5,000+ scans), private events, cultural festivals, tourism-adjacent; agro/funeral/crafts/momo-agent directories; smaller towns (Solwezi, Chipata, Mongu, Kasama); AI "ask" mode (≥10K transactions); conversational assistant.
- Ph4 / Year 2+: ERP-grade API, Convergeo Express own logistics, platform credit facility, Zimbabwe→SADC cross-border (Q73, B2B-led), full AI mode.
- Explicitly out of v1: all B2B UI, multi-warehouse, wallet/lending/insurance, COD-heavy categories above, pay-what-you-want, POS-light, promoted-listing auctions, cross-border.

## 8. NUMBERS
- Budget $2K bootstrap; 60-day build; solo founder + AI; launch Day 60; events build Days 49–53.
- Commissions: Q5 tickets 5–10% (floor 5% yr 1; 8–10% international touring); Q2 category-variable (5% electronics, 12% fashion cited); 0% on free events forever; buyer cancel >7d = full refund minus 5% admin fee; 1–7d = 50%; <24h = none.
- Caps/thresholds: Tier-1 organiser K20,000 GMV/event until 3 successful events; verification calls >K100,000 ticket sales; ID spot-check >K500 tickets; Class-D manual review first 5 listings >K1,000; cancel-rate 5%/10% warn/suspend; disputes ≤7 days post-event; 3+ upheld disputes = ban; transfer cutoff T-6h; reservation 10–15 min; reorder alert at 14 days stock; canonical-submission reward = free Bronze month or K50.
- Targets: 75–100 vendors, ≥5 products each, 50–100 orders/mo (Ph1); 300–500 orders/mo gate for B2B; 200–300 hand-recruited Lusaka service vendors; events Ph1 recruit 5–10 + 2–3 + 3–5 partners.
- Market data: mobile money = de facto rails, "well over half of adult Zambians", monthly volumes "hundreds of billions of kwacha"; services ≈58% GDP; informality ≈70% of employment; no incumbent combines self-service + bookings + geo + momo checkout.
- Catalogue math: 5 product classes + 6 service archetypes + 5 event types = 16 patterns; ~100 + ~110 + ~65 = 275+ sub-categories; 60+ business types; 14 service verticals; 13 product departments; 11 event categories.
- Example price points: wholesale flour 50kg K780/K720(10+)/K680(50+); price_tiers {1:K50, 10:K42, 50:K38}; pop-up dinners K300–1,500/seat; international concert tickets K500–2,000+; cake RFQ K150/cake + K500 setup; working-capital example "sold K12,000/mo avg → borrow up to K8,000 at 4% fee"; free delivery ≥K200; payload <200KB.

---

# DOCUMENT 2 — Blueprint_for_Zambia_s_Vergeo_superapp.pdf
`/root/.claude/uploads/ca3bf6a9-5ac0-59de-8d61-e7dcc0c18e35/84e27059-Blueprint_for_Zambia_s_Vergeo_superapp.pdf` — 37 pages. **Not a spec: a TurboScribe transcript of a 2-part podcast-style "deep dive"** (two speakers, NotebookLM-style) narrating a stack of internal docs: "Convergio architecture" schematic, marketing deck, 60-day roadmap, UI wireframes, database schema, catalogue. Platform named "Vergio/Vergeo/Virgeo", "also referred to internally as Convergio". Secondary/derivative source; numbers quoted appear to be wireframe/mock-dashboard data.

## 1. SECTION MAP (transcript pages)
- pp.1–4 (Part 1): framing — invisible digital infrastructure; Vergio = "Zambia's ambitious national marketplace", "comprehensive ecosystem", phased plan to "nationwide digital utility".
- pp.4–10: bedrock tech — Next.js on Vercel + Cloudflare CDN (pp.5–7); Django REST API + PostgreSQL+PGVector semantic search (pp.7–9); Supabase Realtime, Celery workers, Upstash Redis (pp.9–10); 60-day roadmap "impossibly aggressive".
- pp.10–11: build-vs-buy — why Shopify/WooCommerce/WhatsApp Business APIs are a "dead end"; consumer app + vendor panel + admin dashboard; own the architecture.
- pp.12–19: Phase 1 "aggressive low-friction onboarding" — 78% mobile stat; phone-number-first OTP (no username/email/password) via Africa's Talking over MTN/Airtel (pp.12–13); PWA install bypassing app stores/data fees (pp.13–16); vendor "list a shop in minutes"; 3-tier progressive-trust KYC: Tier 1 NRC photo ≈10 min (lower withdrawal limits, monitoring), Tier 2 PACRA docs 1–3 day manual review → verified badge, Tier 3 premium (rich customisation, CSV bulk upload, API) (pp.16–18); formalisation on-ramp (p.18); projections 840+ vendors, 12,400+ products (p.19).
- pp.19–24: Phase 2 "taming the chaos" — canonical product vs vendor_listing tables (pp.20–21); comparison UI: chitenge set, "7 vendors selling this", Mulenga Fashion K420 @0.8km vs Chitenge Bazaar K380 @3km (pp.21–22); two-pronged vendor workbench: mobile daily driver ("today K2,860, 7 orders, 3 to ship, mark packed") vs desktop dashboard (GMV 30/60/90d, conversion, CSV, low-stock) (pp.22–23); "no monthly fees, only pay when you sell" → long-tail listing economics (pp.23–24).
- pp.24–29: Phase 2 trust engine — mobile-money-first APIs: Airtel Money, MTN MoMo, Zamtel (p.25); escrow as "visible reassuring state, not hidden policy"; checkout K525 + K20 delivery = "pay K545 with MoMo"; 4-step tracker ("You paid → Held by Convergio → …"); confirm-received → 48h auto-release; 48h payout as the sweet spot vs 7–14-day industry holds (pp.26–28); "once you establish trust you can sell anything" → Phase 3 super-app expansion, 10 provinces (pp.28–29).
- pp.30–33 (Part 2): services marketplace — listings "plumbing from K350 available today", "web & app development from K2,500", catering, logistics, photography, solar installation; RFQ flow: "What do you need?", "3–5 providers usually reply in an hour", pick date, budget range K400–700, "send to 8 providers" (pp.30–31). Events & ticketing — 24 events this month, 12,000+ expected attendees; tech summit K250, harvest agriculture fair K50; dynamic QR refreshing every 60s with countdown (screenshot useless); flat 5% ticket commission (pp.31–32). City Guides (Phase 3) — AI trip planner, Livingstone/Victoria Falls example; sunrise tour bookable via vetted partners; links to 5 verified craft-market shops (p.32). Nationwide logistics — tagline "shop everything, ship anywhere"; Yango API + other couriers + own internal Vergeo logistics network; Ndola buyer ← Lusaka vendor, tracked in-app, all 10 provinces (p.33).
- pp.33–35: economics — catalogue price spectrum: organic maize meal K185, chitenge dress K320, hybrid maize seed K280, solar panel kit K2,800, HP ProBook K9,500, iPhone 15 Pro Max K18,900 ("K185 to ~K19,000 — as ubiquitous as the currency"); admin "desktop command center": daily GMV K184K (+22%), 312 orders, 148 new users today; payout ledger: K1,840 escrow release to Mulenga Fashion, K152 platform commission line; revenue = % of every transaction, 5% tickets, monetised Tier-3 B2B API access; low marginal cost.
- pp.35–37: recap + thesis — informal traders empowered, not replaced; "tools of enterprise" from a K1,000 smartphone.

## 2. PRODUCT DEFINITION
- Vergeo/Convergio = Zambia's national marketplace **super-app**, digitising informal + formal commerce; explicitly "not a store… an entire ecosystem": consumer app + vendor management panel + admin dashboard; integrates local services and ticketing in one place.
- Model: pure commission marketplace ("no monthly fees, only pay when you sell"), escrow-mediated, mobile-money-first.
- Verticals: physical products (agri staples → premium electronics), services (6+ categories incl. plumbing, dev, catering, logistics, photography, solar), events/ticketing, tourism city guides, nationwide delivery. (No B2B/wholesale/inventory layer mentioned.)
- Target users: mobile-first Zambian consumers (78% mobile web access, prepaid data, budget phones); informal market traders (Tier 1) through registered businesses (Tier 2) to premium brands/large retailers (Tier 3 API); event-goers and organisers; tourists (Livingstone).
- Revenue: per-transaction commission (payout ledger example ≈8.3%: K152 on K1,840); flat 5% event tickets; B2B API-access monetisation for Tier 3. Positioned to investors: automated infra → low marginal cost → GMV compounds "without proportional overhead".

## 3. FEATURES & MODULES (1-line each)
- PWA customer portal with in-page "install" button (no app stores, no big download).
- Phone-number-first signup: OTP via SMS, no username/email/password (Africa's Talking → MTN/Airtel routing).
- 3-tier progressive-trust KYC vendor onboarding ("list a shop in minutes"; OCR of NRC ID number).
- Canonical inventory system: `product` (canonical) vs `vendor_listing` tables; vendors attach offers (price, stock, condition).
- Product+vendor comparison screen: one master page, "N vendors selling this", sort nearest/cheapest.
- AI semantic search via PGVector (intent matching, colloquial/misspelled queries; "blue dress"="azure gown").
- Supabase Realtime push notifications (e.g., "order shipped").
- Celery + Upstash Redis background jobs (image processing, bulk SMS to 100 users).
- Vendor mobile daily-driver: today's takings, orders needing action, giant "mark packed" button.
- Vendor desktop dashboard: GMV 30/60/90-day graphs, conversion rates, CSV bulk upload, low-stock alerts.
- Tier-3 API access: retailers sync existing inventory software.
- Escrow checkout: visible 4-step vertical tracker; funds "held by Convergio"; confirm-received; 48h auto-release to vendor mobile wallet.
- Mobile money rails: Airtel Money, MTN MoMo, Zamtel API integrations.
- Services RFQ: plain-text need + preferred date + budget range → broadcast to 8 providers → competing quotes.
- Events & ticketing: dynamic QR regenerating every 60s with countdown; flat 5% commission.
- City Guides (Phase 3): AI trip planner; content→commerce funnel (bookable tours, linked verified shops).
- Logistics: Yango + courier APIs + own Vergeo logistics network; in-app last-mile tracking, 10 provinces.
- Admin desktop command center: daily GMV/orders/signups, payout ledger with commission deductions.

## 4. STRATEGY
- Positioning: national digital utility / "blueprint to capture an entire national market"; embed across whole economic spectrum (K185–K18,900) — "as ubiquitous as the currency"; empowers informal traders rather than replacing them.
- Differentiation: custom architecture vs Shopify/WooCommerce ceilings ("can't build a national highway from private driveways"); PWA = "acquisition cheat code" vs app-store friction/data cost; canonical catalogue forces hyper-local price/logistics competition vs duplicate-listing chaos; escrow as visible UI state = "the trust moment that beats informal sellers" (WhatsApp send-money-and-hope); 48h payout vs 7–14-day holds = vendor cash-flow sweet spot; commission-only flips vendor psychology to list entire long tail (vs $50/mo subscription → top-5 items only).
- GTM: Phase 1 aggressive low-friction onboarding of both sides (OTP buyers, 10-minute Tier-1 vendors); links shared into WhatsApp groups/Facebook posts open the PWA instantly; trust engine then unlocks Phase 3 expansion ("once you establish trust, you can sell anything").
- Brand identity: no colours/typography given; taglines/copy: "list a shop in minutes", "no monthly fees, only pay when you sell", "shop everything, ship anywhere", escrow "visible, reassuring state, not a hidden policy". Naming unstable (Vergio/Vergeo/Virgeo/Convergio).

## 5. PAYMENTS / LOGISTICS / COMPLIANCE
- Payments: mobile-money-first strategy; direct API integrations Airtel Money, MTN MoMo, Zamtel; credit cards dismissed as "an afterthought" for the market (Stripe/PayPal-style checkout "fails immediately"); no aggregator, card gateway, or COD mentioned.
- Escrow: funds deducted instantly to platform vault; vendor paid to mobile wallet 48h after buyer confirm (auto-release absent dispute); framed as core differentiator.
- Logistics: Yango (ride-hail/delivery) API + various courier services + internal Vergeo logistics network; "shop everything, ship anywhere"; predictable, integrated, tracked last-mile across all 10 provinces; K20 delivery fee in worked example; hyper-local pickup alternative (walk 0.8 km).
- Compliance: NRC photo (Tier 1); PACRA documents (Tier 2, 1–3-day manual verification, verified badge). Nothing on ZRA/VAT/tax, sector regulators, or data protection. WhatsApp appears as competitor/scam context and as PWA distribution channel, not as a product channel.

## 6. TECH STACK & ARCHITECTURE
- Frontend: Next.js hosted on Vercel; Cloudflare CDN edge caching (3G/4G resilience, "latency kills conversions"); customer portal is a PWA.
- Backend: Django REST API; PostgreSQL + PGVector (vector similarity / semantic search); Supabase Realtime (push); Celery workers + Upstash Redis (queues/cache); Africa's Talking (SMS/OTP via MTN/Airtel).
- Data model: canonical `product` table vs `vendor_listing` table separation as "the single most important architectural decision".
- Explicit rejection of white-label (Shopify/WooCommerce/WhatsApp Business API) to own UX end-to-end and avoid third-party scaling ceilings.
- Three apps: consumer PWA, vendor panel (mobile+desktop), admin dashboard.

## 7. PHASING / SCOPE
- 60-day roadmap to launch (characterised as "impossibly aggressive"; no day-by-day detail in transcript).
- Phase 1: infrastructure + frictionless onboarding (OTP, PWA, tiered KYC).
- Phase 2: taming catalogue chaos (canonical inventory, comparison, vendor workbench) + trust engine (mobile money + escrow).
- Phase 3: super-app expansion — services marketplace (6+ categories), events/ticketing, City Guides AI trip planner, nationwide logistics across 10 provinces.
- No explicit out-of-scope list, budget, or team plan stated.

## 8. NUMBERS
- 78% of Zambian internet users access web via mobile; ~80% drop-off claimed for app-store funnel (illustrative); 100MB app download as "financial penalty".
- Projections/mock dashboard: 840+ vendors; 12,400+ products; daily GMV K184K (+22%); 312 orders/day; 148 new users/day; 24 events this month, 12,000+ attendees.
- KYC: Tier 1 listing within 10 minutes; Tier 2 verification 1–3 days.
- Escrow/payout: 48h auto-release; competitors 7–14-day holds/weekly payouts.
- Commissions: 5% flat on tickets; payout example K1,840 released / K152 commission (≈8.3%); rejected counterfactual $50/mo vendor subscription.
- Prices: chitenge set K525 + K20 delivery = K545 MoMo checkout; K420 (0.8 km) vs K380 (3 km) same item; maize meal K185; chitenge dress K320; maize seed K280; solar kit K2,800; HP ProBook K9,500; iPhone 15 Pro Max K18,900; plumbing from K350 (burst pipe K3,000); web/app dev from K2,500; deep-clean budget K400–700; tech summit ticket K250; agri fair K50; K1,000 smartphone reference.
- Geography: 10 provinces; Lusaka, Copperbelt, Ndola, Livingstone named.

---

# 9. CONTRADICTIONS BETWEEN THE DOCUMENTS + OPEN QUESTIONS

**Contradictions / tensions**
1. **Name**: "Vergeo/Vergio/Virgeo/Convergio" (Blueprint) vs consistently "Convergeo" (Bible). Brand unresolved.
2. **Vendor fees**: Blueprint's core rule "no monthly fees, only pay when you sell" vs Bible's Bronze/Silver/Gold/Platinum subscriptions (Q4), subscription billing admin surface, features gated to "subscription tier and above", "free month of Bronze" rewards.
3. **Ticket commission**: flat 5% (Blueprint) vs 5–10% range, 5% floor year 1, 8–10% premium international (Bible).
4. **Overall commission**: single implied ~8.3% cut (Blueprint ledger) vs category-variable Q2 (5% electronics, 12% fashion) (Bible).
5. **Payout cadence**: 48h mobile-money payout as the differentiator (Blueprint) vs weekly settlement default (Bible services brief) plus event-specific escrow (T-7/T+1 splits) and 72h for used goods. Also the 48h semantics differ: post-confirmation release timer (Blueprint) vs 48h no-dispute auto-confirm window (Bible demand pipeline).
6. **KYC tiers**: 3 tiers, Tier 1 = NRC only (Blueprint, and Bible Q35/Q36 briefs) vs the Bible services brief's 4-tier model (Tier 0 unverified self-listed; Tier 1 = NRC + PACRA; Tier 2 = sector regulator licence; Tier 3 = earned "Convergeo Preferred") — inconsistent across docs *and* within the Bible.
7. **Scale at launch**: 840 vendors / 12,400 products / K184K daily GMV / 24 events / 12,000 attendees (Blueprint) vs Day-60 target of 75–100 vendors, ~375–500 products, 50–100 orders/month and a deliberately small events launch (Bible). Blueprint figures are almost certainly wireframe mock data, not targets.
8. **Payments scope**: direct MoMo APIs only, cards dismissed (Blueprint) vs cards via DPO, dual gateway DPO+Lenco (Q19), aggregator abstraction (ZynlePay/DPO/Pesapal/Flutterwave), COD (Q25), USSD (Bible). Bible internally also wavers: "native integrations rather than a single aggregator" (services brief) vs Q19 dual-gateway reconciliation.
9. **Logistics**: own "Vergeo logistics network" presented as current alongside Yango (Blueprint) vs own network ("Convergeo Express") explicitly deferred to Year 2+, hybrid courier/vendor/pickup at launch (Bible).
10. **Geography**: nationwide/10-province framing (Blueprint) vs Lusaka-first, Copperbelt months 4–9, small towns months 9–18 (Bible).
11. **Events data model**: Bible Events brief proposes a sibling Event/TicketType/Ticket schema *against* the Master Plan's (and its own Products brief catalogue row's) tickets-as-product-with-flag; Blueprint is silent. Needs a decision.
12. **Search**: PGVector presented as the search story (Blueprint) vs Meilisearch-primary + pgvector-semantic hybrid with RRF, external embedding models (Bible).
13. **City Guides phasing**: Phase 3 (Blueprint) vs Phase 2 customer-frontend surface (Bible, Q52).
14. **Services RFQ breadth**: "send to 8 providers" broadcast (Blueprint) vs "3–5 providers usually reply within an hour" copy (both) — same feature, different numbers surface.

**Open questions**
- The Strategic Master Plan (75 Q-decisions, day-by-day 60-day roadmap, §4 schema, wireframes, marketing deck) is the true source of record and is in neither PDF — obtain it.
- Final brand/domain; final commission schedule per category; subscription tier pricing and what each tier gates.
- Payout cadence and escrow windows to commit to (48h vs weekly vs event-split), and who legally holds escrow funds (BoZ e-money/PSP licensing is never addressed).
- Canonical KYC tier model; whether Tier 0 (unverified) listings are allowed at all.
- ZRA specifics: never mentioned by name — VAT registration, Smart Invoice/e-invoicing, TPIN capture, withholding on marketplace payouts are all unaddressed.
- COD scope (Q25) vs escrow-first narrative; card gateway final choice (DPO vs Lenco vs aggregator).
- Event entity vs product-flag decision before the Day 49–53 build.
- Whether Blueprint dashboard figures (K184K GMV, 840 vendors) should be treated as targets anywhere; realistic Phase-1 KPIs are the Bible's.
- Solo-founder ($2K) feasibility of manual ops promised: 1–3-day KYC review, pre-event verification calls, 24h dispute SLA, account managers.
- Launch language scope (English/Bemba/Nyanja Q27), USSD vendor flows in v1, embedding provider choice, and Qdrant/Weaviate migration threshold.