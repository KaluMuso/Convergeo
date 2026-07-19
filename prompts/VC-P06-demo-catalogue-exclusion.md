> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P06 — Exclude the demo catalogue from public discovery `[CODE]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` X-5; MR-D01; **FD-04 (NB-3)**; `release-gates.md` G11. **Live:** 3 demo vendors / 134 `demo/%`-imaged listings are **public-eligible** in search/browse. D25 requires demo inventory to be **excluded from public discovery** (trust + SEO). **Default posture (FD-04): exclude from public search**, labelled fixtures only on demo routes.
**Type:** `[CODE]`. Note: `search.py` is also touched by VF-P04 (Wave 5) — different waves, so sequential; VF-P04 rebases on this.

## 2. Objective & scope
Filter demo vendors/listings out of every public discovery surface; keep them visible only on explicit demo/pitch routes.
**Non-goals:** deleting demo data (that's a later merch/import decision); the wholesale gate (already implemented); search health (VF-P04).

## 3. Files (edit ONLY these)
- `services/api/app/routers/search.py`, `services/api/app/routers/catalog.py`
- `scripts/seed/label-demo.(sql|py)` (mark demo vendors/listings so the filter is data-driven, not hardcoded)
**Guardrail: mirror the existing wholesale-exclusion pattern (`drop_wholesale_listing_hits`) rather than inventing a new mechanism.**

## 4. Implementation spec
- Add a demo flag/derivation (e.g. vendor `is_demo` or `cloudinary_public_id LIKE 'demo/%'`) and exclude demo hits from public `list_catalog`, PDP vendor lists, comparison, directory, `run_search`/`run_suggest`, and Ask retrieval — unless an explicit demo/pitch context requests them.
- Keep the exclusion server-side (not just UI); demo remains reachable on a labelled demo route for internal preview.

## 9. Security
- No auth change; visibility rule only. Demo must not leak into public SEO/sitemap.

## 10. Tests (RUN before reporting)
- New tests: public search/catalog/comparison/directory each **exclude** `demo/%`; the demo route still shows them labelled.
- `uv run pytest services/api/tests/test_search*.py test_catalog*.py -q` green.

## 11. Acceptance criteria / DoD (G11)
- [ ] Demo excluded from all public discovery surfaces (server-side).
- [ ] Demo visible only on the labelled demo/pitch route.
- [ ] Tests prove exclusion; data-driven (not hardcoded slugs).

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P06 — Exclude the demo catalogue from public discovery
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste search/catalog exclusion tests · **EXCERPTS:** the exclusion filter · **QUESTIONS:** …
