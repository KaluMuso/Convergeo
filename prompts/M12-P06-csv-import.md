> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M12-P06 — Bulk listing CSV import

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **Listing create merged (M12-P03):** `vendor_listings.py` — reuse its validators (`is_valid_price_tiers`, tier/moq/condition rules, `require_listing_cap`). **Do NOT import from it via a forbidden path** — if a validator is not already importable from a shared module, **re-implement the check inline** (do not edit `vendor_listings.py`). `vendor_listings(vendor_id, sku, title, price_ngwee, stock_qty, stock_mode, condition, wholesale, price_tiers, moq, returnable, return_window_hours, status)`. **Tier caps by kyc_tier** (T1 = 30 active listings) enforced via `require_listing_cap` semantics — an import that would exceed the cap is **partially rejected at the cap boundary**, not all-or-nothing.
- Vendor app `localePrefix:"always"` → page at **`apps/vendor/app/[locale]/listings/import/page.tsx`**. M12-P04 (same wave) owns `listings/page.tsx` + `listings/[id]/edit/`; **you own ONLY `listings/import/`** — disjoint. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- **`vendor.json` shared with M12-P04 + M12-P09 this wave** — you own a nested **`listings.import`** section (append-rule below).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P06.

## 2. Objective & scope

CSV bulk import: upload → parse → **per-row validation with row-level error feedback** (row N: reason) → commit valid rows; **idempotent by vendor SKU** (re-import updates, does not duplicate); tier cap respected (reject overflow rows at the boundary); downloadable template + example.
**Non-goals:** no single-listing create/edit (M12-P03/M12-P04), no images in CSV (URL-ref out of scope — M12-P05), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/listings/import/page.tsx` (+ `_components/*`) · `services/api/app/routers/listing_import.py` · `services/api/app/services/listings/csv_import.py` (parse+validate+upsert; **`app/services/listings/__init__.py` if the dir is new** — no `app/services/__init__.py`) · `services/api/tests/test_csv_import.py`
- **Modify:** `packages/i18n/messages/en/vendor.json` (add nested `listings.import` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `vendor_listings.py`/`vendor_listings_manage.py` (M12-P03/P04), `listings/page.tsx` or `listings/[id]/` (M12-P04), `main.py`, schema.**

## 4. Implementation spec

- **`csv_import.py`:** parse CSV (bounded row count + size), validate each row (required cols, price integer ngwee ≥ 0, stock ≥ 0, condition enum, tiers ascending-qty/descending-price via inline check, moq); collect **`{row, ok, errors[]}`** per row. Upsert valid rows **keyed on `(vendor_id, sku)`** (idempotent). **Cap enforcement:** count current active + would-be-new; rows beyond the tier cap → rejected with a cap reason (deterministic order = file order). No partial-row commits (a row commits fully or not at all).
- **`listing_import.py`** (`require_role('vendor')`): `POST /listings/import` (multipart or JSON rows) → returns the per-row result summary (`accepted`, `rejected`, `errors[]`). Vendor-scoped (rows always written under the caller's vendor_id — a `vendor_id` column in the CSV is ignored).
- **Import page:** upload, show per-row results table (row N → ok / reason), template download. All copy via `vendor` (`listings.import.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; vendor-scoped (CSV `vendor_id` ignored — tested); price integer ngwee; bounded upload size; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_csv_import.py`: **100-row mixed-valid/invalid → correct per-row accept/reject with reasons**; **idempotent re-import** (same SKU updates, no dup); **tier-cap overflow rejected at boundary** (file order); **`vendor_id`-in-CSV ignored** (written under caller). `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Mixed CSV → row-level feedback correct; idempotent by vendor SKU; cap overflow rejected at boundary (file order).
- [ ] CSV `vendor_id` ignored (caller-scoped); `listings.import.*` nested (append-rule); full API suite + repo green.

## vendor.json rule (shared with M12-P04 + M12-P09 this wave)

Append ONLY your nested `listings.import` section; do NOT reorder/reformat siblings. The later-merging vendor PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M12-P06 — Bulk listing CSV import
**STATUS/FILES/DEVIATIONS** (note whether validators were re-implemented inline vs shared-importable) **/TESTS** (paste mixed-row + idempotency + cap-overflow + vendor-scope + full-pytest tail) **/EXCERPTS** the per-row validation + upsert-by-SKU — nothing else **/QUESTIONS**
