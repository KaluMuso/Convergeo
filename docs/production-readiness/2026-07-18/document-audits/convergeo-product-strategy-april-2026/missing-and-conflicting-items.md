# Missing and Conflicting Items

Document: `convergeo-product-strategy-april-2026` · Audit 2026-07-18

## a. Missing production records

- **F022** (PARTIAL): ~100 product sub-categories across 13 departments must be absorbable by data model.
  - Evidence: Live 8 root departments (74 categories total) matching Phase1 set; Phase2/3 departments (fresh, alcohol, health, automotive, agriculture, crafts, pets, digital beyond tickets, etc.) absent as roots
  - Gap: missing master taxonomy for non-Phase1 departments
  - Action: P2 additive category migrations per phase; do not force 13 departments at launch

- **F025** (PARTIAL): Event tickets in Phase1 (Day49–53 plan) with dynamic QR; sits in taxonomy with class=ticket flag.
  - Evidence: event-tickets category root exists; events=0 tickets=0; n8n tickets-issue workflow absent; product_class/ticket flag absent
  - Gap: schema present, operational records + automation missing
  - Action: P0 before ticket launch: activate issuance workflow + seed real events

- **F026** (MISSING): Phase2 adds Class C produce, Class D used goods/salaula, heavy building materials, agriculture inputs, used vehicles.
  - Evidence: No fresh/agriculture/automotive root categories; no product_class; condition lacks used; vendor_locations=0
  - Gap: intentionally out of Phase1 — confirm not enabled
  - Action: Gate UI/copy so Phase2 categories cannot be selected until schema ready

- **F033** (PARTIAL): Tiered/volume pricing for wholesale-friendly listings.
  - Evidence: Schema+validator VERIFIED; live listings_with_tiers=0; wholesale_listings=0
  - Gap: feature unused in production data
  - Action: P2 seed one wholesale tiered listing after business_buyers path ready

- **F040** (PARTIAL): Digital goods include e-vouchers, software, event tickets, courses; tickets already in roadmap.
  - Evidence: event-tickets root present; other digital goods departments absent; always_available stock_mode exists for digital but unused (0 rows)
  - Gap: partial taxonomy
  - Action: Phase1: tickets only; defer vouchers/courses

## b. Missing fields / schema support

- **F003** (MISSING): Every item fits one of five product classes A–E (Branded SKU, Branded variant, Commodity, One-of-a-kind, Made-to-order).
  - Evidence: information_schema: no product_class column on products or vendor_listings
  - Gap: unsupported product feature / missing field
  - Action: P0 schema: additive product_class enum on products + vendor_listings with backfill default A for current demo

- **F004** (PARTIAL): Add product_class enum (A–E) on both Product and VendorListing; Class D/E use product_id NULL with listing-owned title/description/images.
  - Evidence: product_id nullable VERIFIED; live listings_null_product=0; API mode quick_list sets product_id NULL; product_class MISSING
  - Gap: missing field (product_class); no D/E production records
  - Action: Add product_class; document quick_list as D/C bridge; seed/test null-product listings

- **F005** (MISSING): Class B uses canonical with variants (variant table beneath product); per-unit per variant.
  - Evidence: to_regclass('public.product_variants')=false; no variant_id column
  - Gap: missing schema support
  - Action: P1 design additive variants or encode pack size in products.spec + related products until table lands

- **F006** (PARTIAL): Six pricing modes required from day one: per-unit fixed, per-weight/volume, per-bunch/pile/bundle, tiered/volume, range/from, quote-only.
  - Evidence: Per-unit via price_ngwee VERIFIED; tiered via price_tiers jsonb+CHECK VERIFIED (0 rows with tiers); quote flows exist for services/jobs not product listings; no pricing_mode/sale_unit; condition/stock enums lack weight/bunch/range modes
  - Gap: missing fields / unsupported modes
  - Action: P0 additive pricing_mode + unit fields; keep per-unit UI default; wire tiered UI for B2B

- **F007** (MISSING): Class A/B/C products carry sale_unit and optional base_unit; platform shows price-per-base-unit.
  - Evidence: No sale_unit/base_unit columns; catalog API has no price_per_base fields
  - Gap: missing fields/schema + UI
  - Action: P1 add unit fields + computed price-per-base in comparison API/UI

- **F008** (MISSING): Display any currency, settle ZMW; imported goods may peg USD with daily FX margin; lock FX at order placement.
  - Evidence: No fx_currency/peg columns on listings; money is ZMW ngwee-only in live schema; 0 payments to observe FX lock
  - Gap: unsupported product feature
  - Action: P2 design FX peg after Phase1 per-unit ZMW path proven; do not claim Q23 product refinements live

- **F011** (MISSING): Non-New listings require evidence photos (powered-on + IMEI for phones; VIN/mileage/angles for vehicles; real item photo for salaula).
  - Evidence: listing_images stores cloudinary_public_id/position only; no IMEI/VIN/evidence_kind; all 134 images demo/ prefix per foundation
  - Gap: missing fields + enforcement
  - Action: P0 before Class D launch: evidence requirements in listing create + admin review

- **F013** (PARTIAL): Stock modes: tracked numeric; made-to-order (capacity/lead time); by-weight bulk; always-available.
  - Evidence: CHECK/OpenAPI only tracked|always_available; live all 134 tracked; no capacity_per_week/lead_time_days columns
  - Gap: missing stock modes
  - Action: P1 extend stock_mode enum + fields after product_class

- **F016** (PARTIAL): Five vendor onboarding flows: search-and-attach; submit-new-canonical; commodity quick-list; unique-item (D); made-to-order template (E).
  - Evidence: Live OpenAPI modes: attach, new_canonical, quick_list only; quick_list nulls product_id; no unique/made_to_order modes or MTO spec form fields
  - Gap: missing modes D/E + vendor UI not exercised (auth)
  - Action: P1 add unique + made_to_order modes; verify vendor UI against API

- **F017** (PARTIAL): Bulk ops: CSV import matching canonicals; Tier3 API webhook stock sync.
  - Evidence: Import endpoints present in live OpenAPI; webhook stock-sync not found as dedicated product; paid_tiers flag false
  - Gap: webhook stock sync unsupported; CSV runtime NOT_AUDITABLE without vendor auth
  - Action: P2 webhook stock sync after Tier3; verify CSV matching in staging

- **F028** (PARTIAL): Canonical Product/VendorListing works for all five classes if product_class added and product_id nullable for D/E.
  - Evidence: Nullable product_id VERIFIED; product_class MISSING; quick_list implements null product_id
  - Gap: half of stated schema implication delivered
  - Action: Ship product_class migration as highest-leverage catalogue pebble

- **F031** (PARTIAL): Additions (classes, pricing modes, condition models, attribute groups) fit as JSON attribute groups rather than new tables.
  - Evidence: products.spec jsonb exists; critical discriminators (product_class/condition/stock_mode) implemented as columns/CHECKs instead — OK for some attrs, but class/pricing modes not in spec either
  - Gap: neither JSON attrs nor columns encode product_class/pricing_mode
  - Action: Prefer typed columns for class/pricing_mode; use spec for category attributes

- **F034** (PARTIAL): Quote-only mode: no public price; customer requests; vendor responds (bulk/B2B).
  - Evidence: Service job quote endpoints exist; ListingCreateRequest requires price_ngwee (no quote-only product mode); job_quotes=0
  - Gap: product quote-only unsupported
  - Action: P2 decide reuse services RFQ vs product quote-only mode

## c. Configuration / workflow gaps

- **F012** (MISSING): Counterfeit defences: Tier2/3-only on high-risk categories; brand-protection claim on canonical page; customer 'this looks fake' report to admin.
  - Evidence: No authenticity-report endpoint found in OpenAPI path list; brand claim flow not present; KYC records=0 (foundation); flags table empty
  - Gap: missing workflows + UI
  - Action: P1 authenticity report + category×tier gates; brand claim later

- **F014** (PARTIAL): Checkout stock reservation 10–15 minutes; reserved counts as OOS; unpaid expiry releases atomically.
  - Evidence: reservation_ttl_min=15 VERIFIED; stock_reservations table exists (foundation) with 0 rows; no live paid checkout exercised this session
  - Gap: unproven operational path (0 orders/payments)
  - Action: P0 staged money test of reserve→pay→release before public launch

- **F015** (PARTIAL): Flag vendors with cancel-rate >5%; auto-suspend at 10%.
  - Evidence: OpenAPI includes /admin/governance/vendors; repo states signal is read-only (no auto-suspend); 0 orders so rates not observable live
  - Gap: configuration/workflow — warn exists, auto-suspend not enforced
  - Action: P1 enable controlled auto-suspend with audit log after order volume exists

- **F017** (PARTIAL): Bulk ops: CSV import matching canonicals; Tier3 API webhook stock sync.
  - Evidence: Import endpoints present in live OpenAPI; webhook stock-sync not found as dedicated product; paid_tiers flag false
  - Gap: webhook stock sync unsupported; CSV runtime NOT_AUDITABLE without vendor auth
  - Action: P2 webhook stock sync after Tier3; verify CSV matching in staging

- **F025** (PARTIAL): Event tickets in Phase1 (Day49–53 plan) with dynamic QR; sits in taxonomy with class=ticket flag.
  - Evidence: event-tickets category root exists; events=0 tickets=0; n8n tickets-issue workflow absent; product_class/ticket flag absent
  - Gap: schema present, operational records + automation missing
  - Action: P0 before ticket launch: activate issuance workflow + seed real events

- **F036** (PARTIAL): Escrow + payments + ranking already decided; this brief sharpens catalogue.
  - Evidence: payments=0 ledger_txns=0; n8n payment reconciliation active; escrow auto-release workflow MISSING (foundation)
  - Gap: money path incomplete
  - Action: P0 prepaid ledger + escrow release proof before public_launch

## d. UI / customer / vendor / admin gaps

- **F007** (MISSING): Class A/B/C products carry sale_unit and optional base_unit; platform shows price-per-base-unit.
  - Evidence: No sale_unit/base_unit columns; catalog API has no price_per_base fields
  - Gap: missing fields/schema + UI
  - Action: P1 add unit fields + computed price-per-base in comparison API/UI

- **F012** (MISSING): Counterfeit defences: Tier2/3-only on high-risk categories; brand-protection claim on canonical page; customer 'this looks fake' report to admin.
  - Evidence: No authenticity-report endpoint found in OpenAPI path list; brand claim flow not present; KYC records=0 (foundation); flags table empty
  - Gap: missing workflows + UI
  - Action: P1 authenticity report + category×tier gates; brand claim later

- **F016** (PARTIAL): Five vendor onboarding flows: search-and-attach; submit-new-canonical; commodity quick-list; unique-item (D); made-to-order template (E).
  - Evidence: Live OpenAPI modes: attach, new_canonical, quick_list only; quick_list nulls product_id; no unique/made_to_order modes or MTO spec form fields
  - Gap: missing modes D/E + vendor UI not exercised (auth)
  - Action: P1 add unique + made_to_order modes; verify vendor UI against API

- **F020** (PARTIAL): Three discovery modes on homepage with equal weight: Browse, Search, Ask (Ask Phase3).
  - Evidence: /en 200, /en/search 200, /en/ask 200 (Ask Vergeo + quota copy); /en/categories 404; /en/compare 404
  - Gap: UI browse taxonomy route missing/renamed; Ask present early vs Phase3 note
  - Action: P1 confirm browse entrypoints (home chips vs /categories); align Ask phase messaging

- **F029** (PARTIAL): Class A/B support comparison view, shared images, price-and-distance sort, hyper-local competition.
  - Evidence: comparison endpoint 200 for womens-clothing-standard with listing_count=1; distance fields often null; customer /en/compare 404
  - Gap: API exists; dedicated compare UI route missing; multi-vendor competition sparse
  - Action: P1 multi-vendor same SKU seed + customer compare UX entry

- **F030** (PARTIAL): Submit-new-canonical enters moderation queue; admin/AI approve/merge/reject; auto-approve high-confidence duplicates.
  - Evidence: products.status includes pending_moderation; live all 150 active (no queue depth); admin duplicates/merge paths in OpenAPI; auto-approve behavior NOT_AUDITABLE without exercising create
  - Gap: queue empty; auto-approve unproven; admin UI behind Access
  - Action: P1 moderated create test in staging; document auto-merge rules

- **F032** (PARTIAL): Phase1 skips salaula, used phones, used furniture, MTO, heavy cement/sand, fragrances; makeup Tier2+.
  - Evidence: Phase1 roots only (no salaula/used roots) VERIFIED; prohibited_categories=7 (foundation); Tier2+ makeup enforcement NOT_AUDITABLE without KYC/listing policy probe
  - Gap: policy enforcement evidence incomplete
  - Action: P1 audit listing create against prohibited + tier gates with vendor JWT

## e. Conflicting data / architecture claims

- **F009** (CONFLICT): Class A/B/D listings must declare controlled condition enum: New; New (open box); Refurbished; Used Excellent/Good/Fair; For parts/not working.
  - Evidence: Live CHECK allows only ('new','refurbished'); OpenAPI same; all 134 listings condition=new
  - Gap: bad/narrow enum vs document; missing used tiers
  - Action: P0 expand condition CHECK + API enums; migration + vendor UI + facets

- **F010** (CONFLICT): Used items get longer escrow window (72h rather than 48h).
  - Evidence: release_after_delivered_hours=48 only; no condition-keyed override; n8n escrow release workflow absent (only dispatch + payment recon)
  - Gap: configuration/workflow gap + security/money path incomplete
  - Action: Investigate P0: add condition-based hold config + escrow release automation before enabling used listings

- **F018** (CONFLICT): Primary search engine is Meilisearch; pgvector semantic layer; hybrid BM25+vector with RRF, then geo/quality re-rank.
  - Evidence: Live /search returns rrf_score + boost_signals via Postgres FTS/trgm/pgvector (degraded=true observed); no Meilisearch service in production inventory; CLAUDE.md locks Postgres FTS+pgvector
  - Gap: document vs locked/live architecture conflict
  - Action: P0 doc reconciliation: mark Meilisearch superseded by D18–D24 Postgres search; keep RRF requirements

- **F024** (CONFLICT): Public launch Day60 target: 75–100 active vendors with ≥5 products each.
  - Evidence: active_vendors=3; listings=134 (demo); public_launch=false; sell CTA unavailable on www
  - Gap: missing production vendor cohort vs target
  - Action: P0 controlled vendor onboarding when signup CTA/env ready; replace demo catalogue

- **F037** (CONFLICT): Phase1 vendors should have stable supply, photograph well, fulfil reliably; depth over breadth.
  - Evidence: 3 demo vendors; 134 demo/ Cloudinary IDs; kyc_records=0; seller signup unavailable
  - Gap: demo/seed vs real onboarding
  - Action: P0 replace demo media/vendors under controlled onboarding

## f. Access / evidence limitations

- **F014** (PARTIAL): Checkout stock reservation 10–15 minutes; reserved counts as OOS; unpaid expiry releases atomically.
  - Evidence: reservation_ttl_min=15 VERIFIED; stock_reservations table exists (foundation) with 0 rows; no live paid checkout exercised this session
  - Gap: unproven operational path (0 orders/payments)
  - Action: P0 staged money test of reserve→pay→release before public launch

- **F021** (NOT_AUDITABLE): Class C geo re-ranking weight should be 2–3× Class A.
  - Evidence: No product_class; cannot verify per-class geo multiplier; listing lat/lng often null in sample catalog items
  - Gap: access/mapping insufficient
  - Action: After product_class lands, audit ranking SQL/config with sample lat/lng

- **F030** (PARTIAL): Submit-new-canonical enters moderation queue; admin/AI approve/merge/reject; auto-approve high-confidence duplicates.
  - Evidence: products.status includes pending_moderation; live all 150 active (no queue depth); admin duplicates/merge paths in OpenAPI; auto-approve behavior NOT_AUDITABLE without exercising create
  - Gap: queue empty; auto-approve unproven; admin UI behind Access
  - Action: P1 moderated create test in staging; document auto-merge rules

- **F035** (NOT_AUDITABLE): One search layer indexes listings including D/E without canonical product.
  - Evidence: 0 null-product listings live to observe indexing; search_documents populated (foundation 288) but not proven for D/E; would need create+reindex test
  - Gap: no production D/E rows
  - Action: Staging test: quick_list → search_documents row → /search hit

- **F038** (NOT_AUDITABLE): Search-and-attach default: vendor finds canonical, adds price/stock/condition only.
  - Evidence: API mode=attach exists; vendor.vergeo5.com health redirects to login (307); no vendor JWT in audit session
  - Gap: UI/customer/vendor gap — cannot verify UX timing or form fields
  - Action: Provide vendor test account for attach-flow UI audit
