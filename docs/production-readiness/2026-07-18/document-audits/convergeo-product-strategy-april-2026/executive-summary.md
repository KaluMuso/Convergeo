# Executive Summary — convergeo-product-strategy-april-2026

**Document:** Convergeo Product Strategy & Catalogue Architecture (April 2026, 23 pages)  
**Audit date:** 2026-07-18  
**Class:** Requirements / policy / specification (catalogue architecture for products, pricing, inventory, onboarding, discovery, phased launch)  
**Mode:** READ-ONLY reconciliation against foundation inventory + live DB/API/n8n

---

## Verdict

The live platform implements the **canonical Product + VendorListing spine** and a **Phase-1-shaped category tree**, but it does **not** implement the brief’s core behavioural model (five product classes, six pricing modes, rich condition/evidence, Class D/E onboarding). Production remains a **demo catalogue** (3 vendors, 134 listings, demo images) with **zero money operations**, **`public_launch=false`**, and **incomplete escrow automation**.

### Release blocker?

**Yes — this document creates release blockers** if launch claims include the brief’s catalogue architecture (classes A–E, multi-mode pricing, used-goods trust) or Day-60 vendor/volume targets.

- **Hard blockers for full-brief launch:** missing `product_class`; condition enum CONFLICT; used-goods 72h escrow + evidence controls absent; escrow release workflow missing; Meilisearch claim CONFLICT with locked Postgres search; demo-only vendor cohort vs 75–100 target.
- **Phase-1 branded/new-goods-only path:** closer (Phase-1 category roots VERIFIED; attach/new_canonical/quick_list API modes PARTIAL; comparison API PARTIAL) but still blocked for real commerce by money/escrow proof, seller CTA unavailable, and demo data quality.

---

## Status counts (40 atomic facts)

| Status        |  Count |
| ------------- | -----: |
| VERIFIED      |      4 |
| PARTIAL       |     21 |
| MISSING       |      7 |
| CONFLICT      |      5 |
| NOT_AUDITABLE |      3 |
| **Total**     | **40** |

---

## What is solid

- Canonical `products` / `vendor_listings` model with money in ngwee, nullable `product_id`, tiered `price_tiers` schema, stock reservation TTL=15m config.
- Phase-1 department roots match the brief (8 roots / 74 categories).
- Public catalog + product comparison API + search boost signals (`in_stock`, `below_median`) respond live.
- Listing create API modes cover 3 of 5 brief flows (`attach`, `new_canonical`, `quick_list`).

## What is broken or absent

- No `product_class`, variants, `sale_unit`/`base_unit`, or non-unit pricing modes in live schema.
- Condition model CONFLICT: live `new|refurbished` only vs brief’s used/open-box/for-parts tiers; all 134 listings `new`.
- Escrow hold is flat 48h; no condition-based 72h; n8n escrow release absent.
- Search engine claim CONFLICT: brief Meilisearch vs live Postgres FTS+pgvector RRF (`degraded=true` observed).
- Vendor volume CONFLICT: 3 demo vendors vs 75–100 target; sell CTA unavailable; `public_launch=false`.
- Events/tickets category scaffolded but 0 operational rows and no tickets-issue workflow.

## Backlog pressure

| Priority | Items |
| -------- | ----: |
| P0       |     7 |
| P1       |     8 |
| P2       |     5 |

## Assumptions

1. Only the Product Strategy PDF was audited (uploaded Strategy Brief is out of scope).
2. Live Supabase `dpadrlxukcjbewpqympu` + `api.vergeo5.com` / `www.vergeo5.com` are production-of-record.
3. Operator SQL ≠ end-user RLS; used for aggregates/schema only.
4. Phase-2/3 absences are acceptable if gated; they become CONFLICTS when product claims imply they are live.
5. API container git SHA remains NOT_AUDITABLE (per foundation); OpenAPI behaviour is treated as live API evidence for public routes only.

## NOT_AUDITABLE — access still needed

| Fact                             | Need                                                                           |
| -------------------------------- | ------------------------------------------------------------------------------ |
| F021 Class C geo multiplier      | `product_class` live + ranking config/SQL inspection + listings with lat/lng   |
| F035 D/E search indexing         | Staging create of `quick_list` null-product listing + `search_documents` proof |
| F038 search-and-attach UX        | Vendor test JWT / session for vendor app listing create timing and fields      |
| (related) Tier/makeup gates F032 | Vendor JWT + KYC tier fixtures to prove listing rejection                      |
| (related) Admin moderation UX    | Cloudflare Access-authenticated admin session                                  |
| (related) API image SHA          | Host/`API_IMAGE_TAG`/GHCR digest read (least privilege)                        |

---

Artifacts: `source-document.md`, `extracted-facts.json`, `reconciliation-matrix.md`, `missing-and-conflicting-items.md`, `safe-query-log.md`, `remediation-backlog.md`, this file.
