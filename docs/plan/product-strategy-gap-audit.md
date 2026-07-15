# Product-Strategy Gap Audit — verdicts & dispositions

**Date:** 2026-07-15 · **Trigger:** an external (Codex) audit compared the codebase to the
Product Strategy PDF and listed 16 "gaps." This note records the verified disposition of each
against the **locked decisions** (`docs/plan/00-decisions.md`, the source of truth per
`CLAUDE.md`), so the audit is not re-litigated later.

**Method:** every finding was checked against the live branch (`git grep` / schema / router /
service code) and cross-referenced to the governing decision. The raw Strategy Bible proposed a
much larger surface than v1; §G of `00-decisions.md` ("v1 scope fence") and the 27 locked
decisions deliberately scoped v1 **thin**. A "gap vs the PDF" that a locked decision defers or
scopes out is **not a defect** — only code that is wrong, broken, or dead is.

**Outcome:** 14 of 16 are intentional scope-deferrals. 2 were real and are now **resolved**
(below is the disposition; both shipped with tests).

---

## Resolved

| #   | Item                                          | What was wrong                                                                                                                                                                                                                                                                                           | Fix                                                                                                                                                                                                                                                                                      |
| --- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | **`below_median` search boost (dead signal)** | `search_apply_boost` (0009) multiplies a listing's RRF score by +0.05 when `boost_signals->>'below_median'` is true, but every projection hard-coded it to `false` — the boost never fired, so cheaper offers on a canonical product never got the intended lift (undercutting the D24 comparison moat). | Migration `0034` computes `below_median` = priced below the median of active listings for the **same canonical product**; non-destructive backfill. DB-verified (`tests/test_listing_below_median.py`, wired into the CI `rls` job).                                                     |
| R2  | **CSV import never linked canonicals (F12c)** | `csv_import.py` hard-coded `product_id=None` and had no canonical-match — contradicting the in-scope M12-P06 spec ("canonical-match by name/alias suggestion"), so every bulk-imported listing was standalone and excluded from the comparison view.                                                     | Optional `product_id` CSV column (validated ⇒ active canonical) + a dry-run **preview** endpoint that surfaces name/alias match **suggestions**; the vendor confirms in the preview (no silent auto-attach, consistent with M13-P03 "admin confirms every merge"). Backend + UI + tests. |

---

## Deferred (intentional scope — governing decision cited)

| #     | Finding                                                                                 | Verdict     | Governing decision                                                                                                                                                                      | Phase-2 pointer                                                               |
| ----- | --------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| F1    | No `product_class` (A–E) on products/listings                                           | scope       | **D24** locks "Option A" (canonical `products` + `vendor_listings`, nullable `product_id`); branded-vs-commodity is modelled by the nullable FK + `wholesale`, not a class enum         | Add a class enum only if per-class ranking/flows are pulled into scope        |
| F2    | One fixed `price_ngwee`; no sale/unit/range/FX modes                                    | scope       | **D24** (single price + wholesale `price_tiers`+`moq`); quote pricing exists via **D2** Services RFQ; ZMW-only per CLAUDE.md #1                                                         | Richer product pricing (sale price, unit normalisation) post-v1               |
| F3    | Condition only `new`/`refurbished`; no IMEI/VIN evidence                                | scope (OUT) | **D8** new-goods-only launch; **§G OUT** = salaula/used phones; **D5** used-goods 72h window "when those features ship"                                                                 | Used-goods vertical (Phase 2): add condition tiers + IMEI/VIN/serial evidence |
| F4    | `stock_mode` only `tracked`/`always_available`                                          | scope (OUT) | M03-P02 pebble spec; **§G OUT** = multi-warehouse/lot-batch, POS-light; by-weight ↔ fresh produce (OUT)                                                                                 | Phase-2 inventory mountain if warehouse-aware stock is prioritised            |
| F5    | Three listing flows, not five                                                           | scope       | M12-P03 spec (attach / new-canonical / quick-list); unique-item ↔ used goods (OUT), made-to-order ↔ Services RFQ (D2)                                                                   | Phase-2 with used-goods / made-to-order                                       |
| F6b   | No product-class proximity (2–3×) weighting in search                                   | scope       | **D22** locks v1 search = FTS+pg_trgm+pgvector+RRF (all present); distance sort covers in-scope proximity; the multiplier is a Bible p.35 add-on                                        | Ranking-refinement pass post-v1 (the `below_median` half is R1, now live)     |
| F7    | No product variants (Class B)                                                           | scope       | **D24** data model omits a variant layer                                                                                                                                                | Additive variant migration when apparel size/colour SKUs are prioritised      |
| F8    | No FX pegging / multi-currency                                                          | scope       | CLAUDE.md #1 ngwee-only (enforced by `money.py assert_zmw_currency`); **D5** settle ZMW; **§G** omits FX                                                                                | Post-v1 display-layer FX over ZMW prices (no settlement change)               |
| F9    | Escrow hold not condition-derived (72h used)                                            | scope       | **D5** locks 48h/7d v1 window; used-goods 72h deferred; no `used` condition exists to key off                                                                                           | With the used-goods vertical (D5)                                             |
| F10   | `listing_images` has no evidence/required flag; no counterfeit controls                 | scope (OUT) | **D8** new/sealed/refurbished only; **§G OUT** = used phones/salaula/pharma; evidence is bound to the deferred used-condition enum                                                      | With used-goods + counterfeit-sensitive categories (Phase 2+)                 |
| F11   | Cancel-rate warn-5% / auto-suspend-10% not enforced                                     | scope       | **D9** Preferred-badge `<5% cancels` is implemented; no locked decision mandates auto-suspend; v1 governance = manual admin moderation (§G IN); POS-light/webhook stock sync are §G OUT | Automated governance thresholds post-v1 if desired                            |
| F12ab | No auto-merge of high-confidence dupes; no contributor reward                           | scope       | M13-P03 explicit non-goal ("admin confirms every merge"); reward ↔ subscription/wallet (§G OUT)                                                                                         | With subscription-billing / rewards module                                    |
| F13   | No fractional qty/weight, capacity calendar, lead time, MTO checkout                    | scope       | **D24** (integer-qty products + supplies tiers); **D2** (standard checkout; supplies = tier pricing only); made-to-order is Bible Ph3                                                   | Phase-3 per strategy-bible-distilled                                          |
| F15   | Ask Vergeo has no ≥10k-transaction activation gate                                      | scope       | **D23** enumerates the AI controls (quotas 3/25, $15 kill-switch) and intentionally omits a txn gate; RAG refuses on empty retrieval, handling cold-start                               | Only if a maturity gate is later wanted                                       |
| F16   | Meilisearch not used                                                                    | scope       | **D22** defers Meilisearch until ~20k listings or FTS p95 >150ms (audit agreed this is intentional)                                                                                     | Meilisearch at the D22 scale/latency trigger                                  |
| F17   | Operational targets (75–100 vendors, 10k txns, licences, same-day) unprovable from code | n/a         | Business/founder responsibilities (**D10** recruitment, **F4** legal gate); same-day delivery is **§G OUT**                                                                             | Founder/ops, not code                                                         |

---

## Notes

- The two resolved items are the only findings that were code defects (dead code / an in-scope
  spec gap). Everything else is a deliberate v1 thinning with a clear owner.
- Retrofit cost was considered: `product_class` / variants / expanded conditions / evidence
  metadata are cheaper to add **before** large catalogue + order volume, but each is gated on a
  vertical (used goods, apparel variants) that is itself deferred — so adding the columns now
  would be speculative. Revisit when the owning vertical is scheduled.
