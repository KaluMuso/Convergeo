> **Prepend `prompts/_header.md`.**
>
> **Status: ⚠ RE-DIAGNOSED (2026-07-22) — this is a STAGING-DATA issue, not a code fix. Do NOT add a title heuristic.**

# FIX-M — Demo **service** leaks into discovery (re-diagnosed: data, not code)

## Original report (2026-07-21 api-recovery evidence)

A seeded service titled `Laptop & Phone Repair (demo)` still surfaced in `GET /search?q=phone`;
`#368`'s product demo-exclusion "does not strip service titles".

## What the code actually does (verified 2026-07-22)

The demo-exclusion is **correct and already covers services**:

- Canonical marker = the **`demo/` Cloudinary `public_id`** on a listing/portfolio image
  (`services/api/app/services/listings/demo.py` docstring; `is_demo_public_id`).
- `drop_demo_listing_hits` (called in `run_search` and `run_suggest`) drops **service** hits via
  `fetch_demo_service_ids` — "service hits drop when any portfolio image is demo".
- The repo has **no `(demo)` title convention** — a grep of `scripts/seed/` finds none; the seed
  marks demo inventory only by the image prefix.

## Conclusion — do this instead of a code change

The leaked service is a **data artifact**: it was seeded (directly on staging, not via the repo
seed) with a `(demo)` title but **without** a `demo/` image, so the image-based exclusion — working
as designed — does not catch it. The fix is **data-side** on staging, pick one:

1. **Mark it:** give the demo service a portfolio image with a `demo/…` Cloudinary `public_id`
   (then `fetch_demo_service_ids` excludes it automatically). *(preferred — consistent with the marker)*
2. **Remove/rename it:** delete the stray demo service, or drop the `(demo)` suffix if it's meant to be real.

**Do NOT** add an `is_demo_title` heuristic: it contradicts the canonical image-marker design and
would risk hiding legitimate titles containing "demo". If a title marker is ever genuinely wanted,
first make it a real seed convention, then gate consumer discovery on it — that's a design decision,
not a bug fix.

## Files

None (data action on staging). Verify after: `GET /search?q=phone` returns no `(demo)` service.
