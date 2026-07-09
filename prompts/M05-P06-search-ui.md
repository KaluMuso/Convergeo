> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free.

# M05-P06 — Search UI

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- **The search API is merged (M05-P05):** `GET /search` (RRF, faceted, `kind` filter products/services/events/supplies/vendors, pagination) + `GET /search/suggest` (prefix+trgm autocomplete). Call these — do NOT reimplement search.
- **The `(shop)` group + `layout.tsx` come from M05-P01** — add the search page under `(shop)/`, do NOT create the layout.
- `@vergeo/ui` primitives (input, tabs) deep-imported; `@vergeo/config` `createApiClient` for calls.
- i18n: **`search` namespace** is already registered; `packages/i18n/messages/en/search.json` exists — nest it (no flat dotted keys, next-intl nests on dots). **You solely own `search.json` this wave** (distinct from the `catalog` namespace the M05-P01/02/03 shop pebbles use).
  Spec: `docs/plan/02-pebbles/M05-catalog-search-discovery.md` §M05-P06.

## 2. Objective & scope

Search page + TopNav entry: debounced autocomplete (via `/search/suggest`), results tabbed by vertical, recent searches (localStorage), zero-results state with category suggestions + an "Ask Vergeo" teaser slot (wired later by M06-P04).
**Non-goals:** no search backend (M05-P05 merged), no AI (M06), no PLP/PDP.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/search/page.tsx` · `(shop)/_components/search/{search-input,results-tabs,zero-results,recent-searches}.tsx`
- **Modify:** `packages/i18n/messages/en/search.json` (nest + fill)
  **Guardrail: nothing else. Do NOT touch `(shop)/layout.tsx`/`page.tsx` (M05-P01), `catalog.json`, `main.py`, backend search, or `request.ts`.**

## 4. Implementation spec

- **Search page** (`(shop)/search`): reads `?q=`; calls `GET /search` (paginated); **results tabbed by vertical** (All / Products / Services / Events / Supplies / Vendors) with per-tab counts; **debounced autocomplete** (`/search/suggest`, ~200ms debounce) that is **keyboard-navigable** (arrow/enter, ARIA combobox); **recent searches** in localStorage; **zero-results** state → category suggestions + an "Ask Vergeo" teaser slot placeholder (a labelled empty slot M06-P04 fills). **Back button restores results** (URL `?q=` + scroll).
- Data-frugal: **no result images above 720w**; lazy-load.
- All copy via `search` namespace; tokens only; 360px-first.

## 5–8. UI/UX · Responsiveness · Performance · SEO

360px-first; keyboard-navigable autocomplete; back-button restores; data-frugal images; search page is SSR-friendly.

## 9. Security

Public; user query escaped/encoded in URL; no secrets; suggest/search calls go through the API (no direct DB).

## 10. Tests (RUN before reporting)

Component: **autocomplete debounce + keyboard nav** (arrow/enter selects); **tab counts** render; **zero-result** state renders suggestions + teaser slot; recent-searches localStorage. i18n completeness `search.*` (nested, no flat keys). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Autocomplete debounced + keyboard-navigable; results tabbed per vertical with counts.
- [ ] Zero-results shows category suggestions + Ask-Vergeo teaser slot; back-button restores; recent searches persist.
- [ ] `search.json` nested; data-frugal; repo green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M05-P06 — Search UI
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste autocomplete/keyboard + tab-count + zero-result + i18n output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
