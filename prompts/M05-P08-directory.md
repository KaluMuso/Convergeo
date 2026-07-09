> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M05-P08 — Directory tab & vendor public profile

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- `public.vendors` (`0002`): `id, slug, display_name, description, logo_url, status ('draft'|'pending_kyc'|'active'|'suspended'), kyc_tier, preferred_badge, …` (grep for hours/location columns; landmark/lat-lng may live on the vendor or an addresses row — confirm before coding). **Only `active` vendors listed; pending/suspended → 404.**
- The `(shop)` group + layout exist (M05-P01). Reviews summary + listings grid reuse existing catalog/products reads or a directory-specific query. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard: no `from app.supabase_client`; local `Protocol` for the type).
- i18n `directory` namespace registered; `directory.json` exists — **you solely own it** (nest).
- **Interface edge with M12-P09 (same wave):** M12-P09 (storefront profile editor) writes the SAME vendor data you render. Code your read against the vendor columns; M12-P09 owns the write side + `vendor_profile.py`.
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P08.

## 2. Objective & scope

A browsable/searchable vendor index (category/location/badges filters) + a vendor public profile page (logo, hours, location+landmark, description, badges, listings grid, reviews summary) — the directory entry (D2).
**Non-goals:** no profile editor (M12-P09), no full SEO (M05-P09 — LocalBusiness stub only), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/directory/page.tsx` · `(shop)/v/[slug]/page.tsx` · `(shop)/_components/directory/{vendor-card-grid,filter-bar}.tsx` · `services/api/app/routers/directory.py` · `services/api/tests/test_directory.py`
- **Modify:** `packages/i18n/messages/en/directory.json` (nest + fill)
  **Guardrail: nothing else. Do NOT touch `vendor_profile.py` (M12-P09), `main.py`, schema, or other namespaces.**

## 4. Implementation spec

- **`directory.py`:** `GET /directory` (vendor index: filter by category/location/badges; **only `active`**) + `GET /directory/{slug}` (profile: vendor + listings + reviews summary; **pending/suspended → 404**). Injection-safe.
- **Directory page:** vendor-card grid + filter bar. **Profile page** (`v/[slug]`): shareable URL, logo/hours/location+landmark/description/badges/listings grid/reviews summary; **LocalBusiness schema.org stub** (full SEO in M05-P09). All copy via `directory` namespace.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; profile = shareable + LocalBusiness stub; **only active vendors visible** (visibility tested); public read; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_directory.py`: **visibility rules** (active listed; pending/suspended → 404); **filter combos**; empty-directory state. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Only active vendors listed; pending/suspended profile → 404; filters compose.
- [ ] Profile shareable + LocalBusiness stub; `directory.json` nested; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M05-P08 — Directory tab & vendor public profile
**STATUS/FILES/DEVIATIONS** (note vendor hours/location columns grounded) **/TESTS** (visibility + filters + full-pytest tail) **/EXCERPTS** (none) **/QUESTIONS**
