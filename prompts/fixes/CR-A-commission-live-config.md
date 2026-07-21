> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** New FastAPI router module (auto-discovered — do NOT edit `main.py`). Foreground blocking only; run the FULL `uv run pytest` + `pnpm --filter customer test` before reporting.

# CR-A — Bind the public "Sell" page to live commission rates

## Finding

`apps/customer/app/[locale]/(marketing)/sell/_components/commission-rates.ts` is a **static constant mirror** of the `commission_rates` seed (`supabase/migrations/0008_config.sql`) with `TODO(config): bind to live commission_rates`. The rates displayed to prospective vendors on the **public** Sell page are the exact numbers that define the business model (D4). The only live readers of `commission_rates` are **admin-authed** (`services/api/app/routers/admin_config.py` `list_commission_rates`/`update_commission_rate`) and a server-side vendor read (`vendor_listings.py`). There is **no public, unauthenticated config-read endpoint**, so if an admin edits a rate the public page silently shows stale rates.

## Required fix

- Add a **public, read-only, cacheable** endpoint that returns the active commission rates: `GET /public/config/commission-rates` → `{ rates: [{ category_key, rate_pct }], updated_at }`. No auth, no secrets, service-role read of `commission_rates`, RLS-safe (rates are public info). Add a short `Cache-Control`/`s-maxage` (e.g. 300s) — this is 3G-sensitive, cache aggressively.
- In `apps/customer`, fetch this endpoint **server-side (RSC)** on the Sell page and render via the existing `buildCommissionTableRows(...)`. Keep `commission-rates.ts` **only** as a typed fallback if the fetch fails (degrade to last-known constant, never crash the page), or delete it if you wire a stable fallback in the fetch layer. Preserve the existing i18n category labels + `formatK`-style rate formatting.
- Rates stay integer/`Decimal`-clean; do not introduce float rounding on `rate_pct`.

## Files (ONLY)

- Add `services/api/app/routers/public_config.py` (+ `services/api/tests/test_public_config.py`)
- Modify `apps/customer/app/[locale]/(marketing)/sell/page.tsx` and `apps/customer/app/[locale]/(marketing)/sell/_components/commission-rates.ts` (and its co-located test if present)
- **Do NOT touch** `main.py`, `admin_config.py`, `vendor_listings.py`, migrations, or any other router/page.

## Tests (RUN)

- API: endpoint returns the seeded rates, is reachable **without auth**, sets a cache header, and reflects an updated rate (update a row in a fixture → response changes). Full `uv run pytest` + ruff + mypy.
- Customer: Sell page renders rates from the endpoint; on fetch failure it falls back without throwing. `pnpm --filter customer test` + typecheck + lint.

## Report

STATUS / FILES / DEVIATIONS (how the public read is cached + how fallback works) / TESTS (paste the no-auth + updated-rate + fallback assertions + pytest tail) / EXCERPTS (the router handler + the RSC fetch) / QUESTIONS.
