> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M13-P03 — Canonical product moderation (dedupe & merge)

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **Canonical catalog merged:** `public.products` (canonical) + `vendor_listings.product_id` FK (listings point at a canonical product) + product `slug` + `pg_trgm` available (`0009_search.sql` enabled `pg_trgm`). Grep exact columns: `products(id, slug, title, category_id, brand, attributes, status …)`, plus any existing `product_aliases`/`slug_redirects` table (**reuse if present; if absent you MUST NOT add a migration** — represent aliases via an existing nullable column or reject the redirect leg and note it). Projection/search index = `0009` search doc (`search_document_tsv` generated column + RRF); a merge must **resync the projection** for the surviving product (re-touch the row so the generated tsv + any denormalised counts refresh).
- **Admin app is a separate hardened origin** (`apps/admin`, `localePrefix:"always"`) → page at **`apps/admin/app/[locale]/moderation/products/page.tsx`**. `require_role('admin')`. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). **State-machine rule:** the merge mutates via a guarded function + audit log — never a raw status UPDATE.
- i18n `admin` namespace registered; `admin.json` exists — **you solely own it this wave** (nest a `moderation` section).
  Spec: `docs/plan/02-pebbles/M13-catalog-governance.md` §M13-P03.

## 2. Objective & scope

Admin canonical-dedupe queue: **duplicate detection** (trgm title similarity within the **same category**) → review pairs → **merge** = re-point all losing product's `vendor_listings` to the survivor + **301 the old slug** + **union aliases** + **resync the search projection** for the survivor; audit-logged, idempotent.
**Non-goals:** no public catalog UI (M05), no auto-merge (admin confirms every merge), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/moderation/products/page.tsx` (+ `_components/*`) · `services/api/app/routers/admin_products.py` · `services/api/tests/test_product_merge.py`
- **Modify:** `packages/i18n/messages/en/admin.json` (nest a `moderation` section — fill)
  **Guardrail: nothing else. Do NOT touch `products`/catalog readers, `directory.py`, `main.py`, schema.**

## 4. Implementation spec

- **`admin_products.py`** (`require_role('admin')`): `GET /admin/products/duplicates` (candidate pairs: `pg_trgm` title similarity above a threshold **AND same `category_id`**, excluding already-merged; ordered by similarity desc) + `POST /admin/products/merge` (`{survivor_id, loser_id}`). **Merge (guarded fn + audit log, idempotent):** re-point `vendor_listings.product_id` loser→survivor; mark loser merged (not raw UPDATE — via the guarded transition); register the loser slug → survivor slug **301**; **union aliases** (loser's aliases + loser slug attach to survivor); **resync survivor projection** (re-touch so the `0009` generated tsv refreshes). Re-running the same merge is a no-op. **Guardrails:** cannot merge a product into itself; cannot merge across categories; merging an already-merged loser → 409/no-op.
- **Moderation page:** duplicate-pair queue with side-by-side compare + a **Merge (pick survivor)** action + confirm. All copy via `admin` (`moderation.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Admin-origin only (`require_role('admin')`); merge audit-logged + idempotent; 301 preserves SEO; injection-safe similarity query; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_product_merge.py`: **dupe detection** (trgm same-category surfaces pair; different-category does NOT); **merge re-points listings** + **old slug 301** + **aliases union** + **projection resynced**; **idempotent re-merge** (no-op); **guardrails** (self-merge / cross-category / already-merged rejected); **authz** (non-admin → 403). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Same-category trgm dupes surfaced (cross-category excluded); merge re-points listings + 301 + aliases-union + projection resync; idempotent.
- [ ] Guarded transition + audit log (no raw UPDATE); non-admin denied; `admin.moderation.*` nested; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P03 — Canonical product moderation
**STATUS/FILES/DEVIATIONS** (note aliases/slug-redirect columns grounded, and how the 301/alias legs are represented without a migration) **/TESTS** (paste dupe-detection + merge-repoint + idempotency + guardrails + authz + full-pytest tail) **/EXCERPTS** the guarded merge fn + dupe-detection query — nothing else **/QUESTIONS**
