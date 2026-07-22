> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration.** Run the FULL `uv run pytest` for the touched suites before reporting.
>
> **⚠ FIRST verify the leak still reproduces on current master** (it was reported 2026-07-21 and master has moved ~80 commits). Probe `GET /search?q=phone` and `GET /catalog/services` (or the services browse) on staging or in a test — if no `(demo)`-titled service surfaces, close this as already-fixed instead of implementing.

# FIX-M — Exclude demo **services** from public discovery (🟠 MED, discovery quality)

## Finding (from the 2026-07-21 api-recovery evidence)

Demo-inventory exclusion (`services/api/app/services/listings/demo.py`) is **image-marker-based**:
a listing is "demo" when one of its images carries a `demo/` Cloudinary `public_id`
(`is_demo_public_id` / `fetch_demo_listing_ids`). A seeded **service** titled e.g.
`Laptop & Phone Repair (demo)` has **no demo image**, so the image marker never matches and it
**still surfaces** in `GET /search` and the services browse. `#368`'s product-exclusion does not
strip service titles.

## Required fix

1. Add a **title-marker** helper to `demo.py` (e.g. `is_demo_title(title)`) that matches **only**
   the exact marker the seed uses — confirm the seed's format first (`scripts/seed/…`), likely a
   trailing `" (demo)"`. Be precise: must NOT hide a legitimate listing whose title merely
   contains the word "demo" (e.g. "Demo Day tickets").
2. Apply it on the **service** discovery paths where the image marker can't reach —
   `services/api/app/services/search/__init__.py` (services hits) and the services browse
   (`services/api/app/routers/services_listings.py` / its service query), complementing
   `drop_demo_listing_hits`. Keep guests/consumers excluded; do not change product behaviour
   (products already covered by the image marker).
3. Keep the two markers unified conceptually — one demo-detection module, two signals
   (image `public_id` + title suffix).

## Files (ONLY)

- Modify `services/api/app/services/listings/demo.py` (add the title-marker helper)
- Modify the service discovery path (`search/__init__.py` and/or `routers/services_listings.py`)
- Extend `services/api/tests/` demo-exclusion tests (or add `test_demo_service_exclusion.py`)
- **Do NOT** change product/vendor exclusion or the image-marker logic.

## Tests (RUN)

- A seeded `(demo)`-suffixed **service** is excluded from `run_search` and the services browse for
  guests/consumers.
- A legitimate service whose title merely contains "demo" (not the exact marker) is **kept**.
- Products/vendors unchanged. **Full `uv run pytest`** on the search + services suites + `ruff` + `mypy`.

## Report

STATUS (incl. whether the leak still reproduced) / FILES / DEVIATIONS (the exact marker matched) / TESTS (paste the exclude + keep-legit cases) / EXCERPT the title-marker + where it's applied / QUESTIONS.
