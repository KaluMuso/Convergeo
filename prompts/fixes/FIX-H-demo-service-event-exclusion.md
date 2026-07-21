> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-H — Demo services/events leak into public discovery (D25 / VC-P06 / RC-04)

## Finding

Server-side demo exclusion covers only three entity kinds. `services/api/app/services/listings/demo.py:125-163` (`drop_demo_listing_hits`) branches on `entity_kind in ('listing','product','vendor')` and detects demo inventory purely via the Cloudinary `demo/` image `public_id` (`is_demo_public_id`). But `search_documents.entity_kind` also includes `'service'` and `'event'` (`supabase/migrations/0009_search.sql:33`), and the search renderer already handles those kinds (`services/api/app/services/search/__init__.py:209-217`). Result: the demo seed service **`Laptop & Phone Repair (demo)`** surfaces in live `/search`, `/suggest`, and Ask retrieval — demo pitch inventory shown to real customers. The catalog PLP path (`routers/catalog.py`) is products/listings only, so it is not the leak; **search + suggest + Ask retrieval are.**

## Required fix

- **Ground the demo marker for services/events first.** Inspect the actual demo rows (`services`, `events`) and their media arrays (`services.portfolio_images`, `events.images`). Extend the **single** demo-detection seam so a `service`/`event` hit is dropped by the **same canonical rule** — a `demo/`-prefixed `public_id` in its media — via `is_demo_public_id`. **Do not match on the `(demo)` title string** (fragile, i18n-hostile).
- If the current demo service/event rows carry **no** demo-prefixed media, make the rule uniform by giving them a `demo/…` media entry in the seed/demo data path (`scripts/seed/…`) so one marker governs every entity kind — rather than adding a per-kind special case.
- Add `service`/`event` branches to `drop_demo_listing_hits` and apply them everywhere the listing/product/vendor drop already runs: `services/search/__init__.py` (search + suggest) and `services/ask/retrieve.py`. Keep it a post-filter after `search_rrf` (RPC unchanged), mirroring `drop_wholesale_listing_hits`.
- Verified businesses / consumers alike must never see demo entities (demo exclusion is unconditional — unlike wholesale gating).

## Files (ONLY)

- Modify `services/api/app/services/listings/demo.py`
- Modify `services/api/app/services/search/__init__.py` (ensure service/event hits pass through the drop)
- Modify `services/api/app/services/ask/retrieve.py` (if it doesn't already reuse the shared drop for all kinds)
- Modify the demo-seed data path under `scripts/seed/` **only if** the demo rows need a canonical `demo/` media marker
- Add/extend `services/api/tests/test_demo_exclusion.py` (or the existing demo-exclusion test)
- **Do NOT touch** `routers/catalog.py` (already correct), returns/_, kyc/_, events/* business logic, migrations, `db.ts`.

## Tests (RUN)

A seeded demo **service** and demo **event** are excluded from `run_search`, `run_suggest`, and Ask retrieval for guest + consumer + verified-business. A non-demo service/event still appears. Existing listing/product/vendor demo-exclusion tests stay green. **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (state the canonical demo marker you settled on for services/events, and whether the seed needed a media tag) / TESTS (paste demo-service-excluded + demo-event-excluded + non-demo-passes + full-pytest tail) / EXCERPTS (the new service/event branch) / QUESTIONS.
