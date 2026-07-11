> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel batch 1). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master` to compare, never stash). **⚙ CI GATING:** `test_prohibited.py` must be pure-unit / isolation-clean. **Run the FULL `uv run pytest` before reporting.**

# M15-P08 — Prohibited-category enforcement

## 1. Context

**Grounded against as-built `master`:**

- **`services/api/app/services/moderation/` exists with `contact_strip.py`** (M11-P06). Add a SIBLING `prohibited.py` — same package, no edit to `contact_strip.py`.
- **Listing create/edit + CSV-import paths (all exist):** `services/api/app/routers/vendor_listings.py`, `vendor_listings_manage.py`, `services_listings.py`, `listing_import.py`, and `services/api/app/services/listings/csv_import.py`. **Enforce via DEPENDENCY INJECTION / a called guard — call `screen_listing(...)` at the top of each create/edit path.** Editing these routers to ADD THE CALL is allowed (it's the enforcement hook), but keep the diff to the single guard call + its import; do NOT refactor them.
- **Config-driven categories** (D8 / geo-fence): salaula (used clothing), used phones, alcohol, pharma, live animals, cement/heavy aggregates. Block at category level **plus** a keyword screen on titles/descriptions.
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P08.

## 2. Objective & scope

A central prohibited-category + keyword screen (`prohibited.py`) enforced at every listing create/edit + CSV-import entry point, rejecting blocked categories/keywords with a clear i18n-keyed error.
**Non-goals:** no ML/AI moderation (keyword + category only), no new migration (categories from config/constant), no admin override UI (later), no shared-file refactor.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/moderation/prohibited.py` (`screen_listing(title, description, category) -> ProhibitedResult`; config/constant list + keyword set; case/diacritic-insensitive match) · `services/api/tests/test_prohibited.py`
- **Modify (single guard call + import ONLY, no refactor):** `services/api/app/routers/vendor_listings.py` · `vendor_listings_manage.py` · `services_listings.py` · `listing_import.py` · `services/api/app/services/listings/csv_import.py`
  **Guardrail: nothing else. Do NOT touch `contact_strip.py`, db.ts, migrations, other routers, i18n namespaces beyond ONE reused error key (prefer an existing `errors`/`listings` key — do NOT create marketing/legal/vendor keys this wave).**

## 4. Implementation spec

- **`prohibited.py`:** `PROHIBITED_CATEGORIES` (set of category slugs) + `PROHIBITED_KEYWORDS` (salaula, used phone(s), alcohol/beer/spirits, pharma/prescription drug names as a small seed set, live animals, cement/aggregate). `screen_listing(...)` → `ProhibitedResult(allowed: bool, reason: str | None, matched: str | None)`. Normalize (lowercase, strip diacritics/whitespace) before matching; match on word boundaries to avoid false positives (e.g. "aggregate" inside a benign word). Central, reusable, no I/O.
- **Enforcement hooks:** at the top of each create/edit path (after auth + Pydantic parse, before persistence), call `screen_listing(...)`; on `allowed=False` raise the uniform 422/400 envelope with the i18n error key. CSV import: screen each row; reject the offending row (collect + report), do NOT abort the whole batch silently — surface which rows were blocked.

## 5–9. Security etc.

Screen runs server-side on every create/edit/import path (assert each hook in a test); no bypass via CSV; keyword match is diacritic/case-insensitive + word-boundary (no trivial evasion via case, and no over-block); no float/money; no secrets; clear i18n-keyed rejection.

## 10. Tests (RUN before reporting)

`test_prohibited.py`: each prohibited category blocked; each seed keyword blocked (incl. case/diacritic variants); benign listing passes (no false positive on a substring); CSV import rejects the offending row + reports it while keeping clean rows. Assert the guard is invoked on **every** create/edit/import path. **Full `uv run pytest`.** `uv run ruff check . && uv run mypy app tests`.

## 11. Acceptance criteria / DoD

- [ ] `screen_listing` enforced on all 5 create/edit/import paths (guard call only, no refactor); category + keyword screen; case/diacritic-insensitive, word-boundary (no false positives).
- [ ] CSV import reports blocked rows without dropping clean ones; no migration; full API suite + ruff + mypy green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P08 — Prohibited-category enforcement
**STATUS/FILES/DEVIATIONS** (the category/keyword source; normalization + word-boundary approach; how each of the 5 hooks calls the guard; CSV per-row rejection) **/TESTS** (paste category + keyword-variant + false-positive + CSV-row + full-pytest tail) **/EXCERPTS** `screen_listing` + one router guard call + the CSV per-row handling — nothing else **/QUESTIONS**
