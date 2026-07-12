> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-G — D8 prohibited-category not enforced on product listing create (🟢 #9)

## Finding

`services/api/app/routers/vendor_listings.py:366` — in `create_listing` (product path / `new_canonical`), the category-block layer of the moderation screen is never run: `screen_listing()` is called with only title/brand and NOT the `category` argument, and `_load_category_commission_key()` selects the vendor-supplied category WITHOUT checking `categories.prohibited`. So a listing under a category flagged `prohibited` (D8 geo-fence: salaula, used phones, alcohol, pharma, live animals, cement/aggregates) is accepted on the product path. (M15-P08 keyword screen still runs on title/brand, but the category-level block is bypassed.)

## Required fix

- Pass the resolved category to `screen_listing(..., category=…)` so the category-block layer runs, **and/or** have the create path reject a category whose `categories.prohibited = true` (check it when resolving the category commission key, or as an explicit guard). A listing under a prohibited category must be rejected with the uniform prohibited-listing error (reuse the existing key from M15-P08).
- Keep the change to the guard call + the category lookup only — no refactor of the create flow.

## Files (ONLY)

- Modify `services/api/app/routers/vendor_listings.py`
- Add/extend `services/api/tests/test_listing_create.py` (or the existing product-create test)
- **Do NOT touch** moderation/prohibited.py (reuse it), services_listings.py, csv_import.py, db.ts, migrations.

## Tests (RUN)

Create a product listing under a `prohibited=true` category → rejected (422/prohibited). A benign category still succeeds. The keyword screen still fires on title/brand. **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS/FILES/DEVIATIONS (how the category now reaches the screen / prohibited check) /TESTS (paste prohibited-category-rejected + benign-passes + full-pytest tail) /EXCERPTS the category guard /QUESTIONS.
