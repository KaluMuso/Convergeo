# Product-strategy alignment — current implementation

**Date:** 2026-08-12<br>
**Baseline:** `master` at `64deebb8` plus the product-class integration work in this branch<br>
**Inputs:** `Convergeo_Product_Strategy.pdf`, the locked decisions in `00-decisions.md`, the
R02-P16 activation prompt, migrations `0085`, `0087`, and
`20260812090000_product_strategy_integrity.sql`, and the live API/web paths.

## Verdict

The codebase does **not** yet implement the full Product Strategy document. It has a strong
Phase-1 marketplace foundation and now implements a useful subset of the product-class model,
but several strategy capabilities remain partial or intentionally deferred.

The July gap audit is no longer current. Since that audit, the repository added:

- listing classes A–E;
- integer-step per-measure sales (`each`, `metre`, `kg`, `litre`, `bag`, `sqm`);
- made-to-order lead times and Class-E weekly capacity;
- the `used` condition, defect notes, and a listing-photo activation rule;
- Class-D/Class-E cart guards and made-to-order stock-reservation behaviour; and
- below-median offer boosting, canonical CSV match suggestions, and vendor governance signals.

This branch closes the most consequential integration gap: those database capabilities are
carried through vendor create/edit APIs, vendor forms, product detail, cart, and checkout instead
of being silently replaced by Phase-1 defaults.

## Current strategy matrix

| Area                                  | Current status               | Implemented now                                                                                                                                                                                                                                     | Still missing or deferred                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product classes A–E                   | **Partial**                  | Listing classes match the brief: A branded SKU, B branded variant, C commodity/generic, D unique, and E made-to-order; vendor create/edit and customer purchase paths understand the field; new/updated D/E rows are database-guarded as standalone | Classes are not canonical-product attributes; Class C lacks loose `(commodity × grade × unit)` canonicals and vendor-owned descriptions/photos; D/E lack listing-owned descriptions and structured attributes/specs; the new standalone constraints remain `NOT VALID` until legacy rows are audited; no complete class-specific discovery, ranking, moderation, or fulfilment policy |
| Pricing and sale units                | **Partial**                  | Integer ngwee; fixed and wholesale-tier prices; compare-at display; listing-level price per integer step, selected units, and minimum steps; exact line totals without floating-point money                                                         | Range/from and quote-only modes; the strategy's product-level `sale_unit` plus optional `base_unit` and price-per-base-unit normalization; broader market units such as bunch/pile/bundle; FX; and per-measure wholesale tiers                                                                                                                                                        |
| Condition and evidence                | **Partial**                  | `new`, `refurbished`, and `used`; used defect notes; at least one listing photo before activation                                                                                                                                                   | Open-box, used quality tiers, and parts/not-working; evidence for refurbished and other non-new conditions; structured evidence kinds; IMEI/VIN/serial verification; category-specific evidence; and the 72-hour used-goods escrow window                                                                                                                                             |
| Inventory                             | **Partial**                  | Tracked/always-available stock plus made-to-order capacity; made-to-order bypasses immediate stock reservation; Class-E weekly capacity is serialized and rechecked atomically when orders are created                                              | Multi-warehouse, lot/batch/expiry tracking, capacity calendar, POS-light mode, and inventory webhooks                                                                                                                                                                                                                                                                                 |
| Listing flows                         | **Partial**                  | Attach to canonical, propose canonical, and quick-list; the forms can express per-measure, used/Class-D, and made-to-order/Class-E listings                                                                                                         | Canonical candidates do not capture the strategy's description/images/specs; commodity quick-list lacks curated category/commodity selection plus its mandatory photo; and there are no complete dedicated unique-item or made-to-order template/options/spec flows or product quote workflows                                                                                        |
| Search and ranking                    | **Partial**                  | PostgreSQL FTS/trigram/vector RRF, distance sort, and below-median offer signal                                                                                                                                                                     | No dedicated end-to-end proof from a standalone quick-list through `search_documents` to a valid customer result route; the strategy's class-specific proximity multipliers, measurable ranking experiments, equal Browse/Search/Ask presentation, and Meilisearch before its locked scale/latency trigger remain absent or deferred                                                  |
| Product variants                      | **Not implemented**          | —                                                                                                                                                                                                                                                   | Size/colour/material variant groups, variant SKUs, option-specific stock/images, and variant comparison                                                                                                                                                                                                                                                                               |
| FX and currencies                     | **Intentionally deferred**   | ZMW/ngwee-only storage and settlement                                                                                                                                                                                                               | Display FX, price pegging, rate source/freshness rules, and non-ZMW settlement                                                                                                                                                                                                                                                                                                        |
| Escrow timing                         | **Partial**                  | Existing standard fulfilment windows                                                                                                                                                                                                                | A founder-approved rule for made-to-order lead time versus auto-release/dispute clocks, plus the used-goods 72-hour rule                                                                                                                                                                                                                                                              |
| Governance                            | **Partial**                  | Cancel-rate warn/critical visibility and existing manual moderation                                                                                                                                                                                 | Automatic suspension at the strategy threshold, appeal/recovery state machine, and POS/inventory reliability signals                                                                                                                                                                                                                                                                  |
| Canonical catalogue                   | **Partial**                  | Manual canonical governance and CSV match suggestions                                                                                                                                                                                               | Class-C loose canonicals, high-confidence auto-merge, contributor rewards, and richer duplicate-confidence operations                                                                                                                                                                                                                                                                 |
| Authenticity and regulated categories | **Partial**                  | KYC tiers, vendor licences, listing flags, and manual moderation foundations exist                                                                                                                                                                  | An enforced category-to-KYC/licence matrix, brand-owner claims, counterfeit reporting workflow, age-at-delivery checks, and cold-chain/pickup restrictions                                                                                                                                                                                                                            |
| Launch catalogue and phase gates      | **Operationally incomplete** | The taxonomy can represent broad departments and listings can be moderated                                                                                                                                                                          | Absorption of the brief's full 13-department/~100-product-subcategory universe is not proven; the eight-department Phase-1 assortment, minimum depth per category, and Class C/D/E enablement gates need measurable catalogue and operations controls                                                                                                                                 |
| AI/search maturity gates              | **Intentional deviation**    | Retrieval refusal on empty evidence, quotas, and cost kill switch                                                                                                                                                                                   | The strategy's 10,000-transaction activation gate, if still desired                                                                                                                                                                                                                                                                                                                   |
| Operational targets                   | **Not code-verifiable**      | Release and operational runbooks exist                                                                                                                                                                                                              | Vendor counts, transaction counts, licences, same-day delivery capacity, and commercial partner readiness require operational evidence                                                                                                                                                                                                                                                |

## Scope conflict requiring a decision

Locked decision **D34** says Phase 1 has no product-class column, no `used` condition, and no
evidence model. Later merged work (`0085_product_classes.sql`, `0087_product_class_enum.sql`, and
R02-P16 customer rules) implements exactly those capabilities. Both statements cannot remain the
current source of truth.

This branch does not rewrite a locked decision silently. Before production use of Class D or used
goods, the founder should approve a dated amendment that either:

1. elevates the implemented A–E subset into launch scope with evidence and escrow release gates;
   or
2. keeps it feature-disabled for Phase 1 while retaining the additive schema for later use.

Until that amendment exists, the safest launch posture is to keep used/Class-D availability behind
an operational gate even though the code can create and validate those listings.

## Invariants closed by this branch

- Vendor create and edit requests persist class, unit, step, minimum, fulfilment, lead-time,
  capacity, condition, and defect-note fields.
- `Class D` means `condition=used`; refurbished is not accepted as a substitute.
- A used/Class-D draft can be saved before image upload, but it cannot become active without an
  listing image and a meaningful defect note. Deferred database triggers also prevent direct
  PostgREST activation without evidence or removal of the last evidence image.
- Each-item listings use a 1,000-milli step; per-measure listings use positive integer milli-units.
- Per-measure wholesale remains rejected, matching the R02-P16 non-goal.
- Cart quantity is a count of integer steps, enforces `min_steps`, and money remains integer ngwee.
- Explicit Class-E capacity is rechecked under a listing-row lock in the atomic order transaction;
  legacy non-Class-E made-to-order listings remain uncapped as defined by migration `0085`.
- Product detail, cart, and checkout display the human quantity and made-to-order lead time.

## Explicitly not claimed complete

This work must not be described as full Product Strategy compliance. The highest-value next slices
are:

1. approve the D34 amendment and the made-to-order/used escrow timing rule;
2. add structured evidence (kind, identifier, verification state) for sensitive used categories;
3. add a proper variant/SKU layer for Class B;
4. add Class-C loose canonicals and listing-owned descriptions/photos, plus full D/E listing content
   and class-specific vendor flows;
5. add a capacity calendar and configurable options/spec capture for Class E;
6. add product-level sale/base units and define normalized comparisons before ranking mixed packs or
   increments;
7. audit legacy listing rows, validate the four strategy constraints, and enforce regulated-category
   KYC/licence requirements;
8. prove standalone quick-list → search index → valid customer route behaviour, the full catalogue
   taxonomy, and the intended Browse/Search/Ask phase gates; and
9. instrument production evidence for the strategy's vendor, transaction, delivery, and liquidity
   targets.

## Release verification

Before enabling the new paths in production, verify:

- migration replay from a clean database and upgrade from a representative production snapshot;
- vendor draft → image upload → activation for used/Class-D, including a no-image rejection;
- half-unit and minimum-step behaviour from PDP through checkout with exact integer totals;
- made-to-order checkout without a stock reservation and with lead time visible at every step;
- existing `new` and `refurbished` listings remain unchanged;
- RLS/API authorization still prevents cross-vendor listing edits and image reuse; and
- legacy rows satisfy the four `NOT VALID` strategy constraints
  (`vendor_listings_standalone_class_check`, `vendor_listings_standalone_title_check`,
  `vendor_listings_per_measure_wholesale_check`, and
  `vendor_listings_class_e_capacity_floor_check`) before those constraints are validated in a
  follow-up migration.
