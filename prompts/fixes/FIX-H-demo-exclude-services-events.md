> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration** (demo-vendor-ownership marker — default). Foreground blocking calls only; run the FULL `uv run pytest` before reporting.

# FIX-H — Demo service/event listings leak into public discovery (🟡 G11 honesty)

## Findings (from `docs/production-readiness/2026-07-21/code-reconciliation-since-audits.md` R-1 + `api-recovery-and-ops.md`)

- `services/api/app/services/listings/demo.py:125` `drop_demo_listing_hits` filters only `entity_kind ∈ {listing, product, vendor}`; detection keys on Cloudinary `demo/` public_ids on `listing_images` (`is_demo_public_id`).
- Search indexes services as `entity_kind="service"` and events as `"event"` (`services/api/app/services/search/__init__.py:209-219`) — both pass through **unfiltered**.
- `services/api/app/routers/services_listings.py` (+ the public events list router) apply **no** demo exclusion.
- Live probe `GET /search?q=phone` (2026-07-21) still surfaced a demo service titled `…(demo)`; services carry no `listing_images`, so the image marker can never catch them.

## Required fix

Use the **demo-vendor-ownership** marker (no schema change): a service/event is demo when its owning vendor/organiser is in the demo-only vendor set.

1. In `demo.py`, add a batched resolver (mirror `fetch_demo_listing_ids`, no N+1) that maps each service/event → owning `vendor_id` (organiser vendor for events) and reuses `fetch_demo_only_vendor_ids` to decide demo.
2. Extend `drop_demo_listing_hits` to also drop hits with `entity_kind ∈ {"service","event"}` whose owner is demo.
3. Add the same server-side exclusion to `routers/services_listings.py` public feed and the public events list router (mirror the listing/product/vendor pattern in #368; reuse the client already threaded there).
4. Confirm `services/ask/retrieve.py` (already calls the drop helper) now also excludes demo services/events.

_Alternative (only if the founder prefers it, NOT this PR): an explicit `is_demo` flag is unambiguous and covers services-only demo vendors — that is an additive migration `0067_service_event_is_demo.sql` + seed set._

## Files (ONLY)

- Modify `services/api/app/services/listings/demo.py`
- Modify `services/api/app/services/search/__init__.py` (only if the drop call must thread the new kinds)
- Modify `services/api/app/routers/services_listings.py` and the public events list router
- Extend `services/api/tests/test_demo_exclusion.py`
- **Do NOT touch** db.ts, migrations, money/authz paths.

## Tests (RUN)

Demo service + demo event dropped from `/search`, search suggest, services browse, events list, and `ask/retrieve`; non-demo service/event retained; all existing listing/product/vendor cases stay green. **Full `uv run pytest`** + `ruff` + `mypy`.

## Report

STATUS/FILES/DEVIATIONS/TESTS (paste a `/search` result before/after showing the `(demo)` service gone)/EXCERPTS (owner-resolve + drop extension)/QUESTIONS.
