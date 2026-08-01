> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P01 — Vendor location + hours completion (the geo-data unlock)

## 1. Context

**Wave R2-A.** Source: `docs/plan/r02/01-strategy-convergence.md` §1.4, §3.1 (rows 1.1, 1.6), §3.2 (rows 2.1, 2.2), §5.

**The problem is data, not code.** Verified read-only on the live production project
`dpadrlxukcjbewpqympu` on **2026-08-01**:

| Probe                                                | Value       |
| ---------------------------------------------------- | ----------- |
| `vendor_locations`                                   | **0**       |
| `search_documents` total / with non-null `lat`+`lng` | 288 / **0** |
| `vendors` where `status='active'`                    | 3           |
| `vendor_listings` where `status='active'`            | 134         |

Every piece of geo machinery is already built and correct: four Haversine implementations
(`routers/catalog.py:166`, `routers/directory.py:143`, `routers/comparison.py:87`,
`routers/checkout.py:138`), a `nearest` sort (`catalog.py:25`, `:627-631`), `lat`/`lng`/`radius_km`
filters (`catalog.py:852-854`, `directory.py:844-846`), and a distance-blended search re-rank
(`app/services/search/__init__.py:336-357`). **The search projection reads listing geo from
`vendor_locations`** (`supabase/migrations/0009_search.sql:258-270`) — so with zero location rows,
every one of those paths is inert. `sort=nearest` cannot order anything; the re-rank has nothing to
re-rank.

The profile API already models all of this: `vendor_locations` (`0002_identity_vendors.sql:87`),
`PATCH /vendor/profile` accepting `hours` + `location` (`routers/vendor_profile.py:479`),
`_upsert_location` (`:432`), hours validation (`:145-201`), and a five-field completeness breakdown
that **already includes `hours` and `location`** (`:19-26`, `:227-250`). Nothing surfaces the gap
where a vendor will act on it.

**Type:** `[CODE]` — API + vendor app + staging seed fixtures. **No migration.**

## 2. Objective & scope

Make a missing location/hours **visible and actionable** to the vendor who can fix it, and make the
staging seed exercise the geo path so the projection is covered by a test instead of by hope.

**In scope:** surface the existing `completeness.location` / `completeness.hours` signals on the
vendor home as a dismissible-but-recurring task card; add `vendor_locations` rows to the staging seed
fixtures; add a projection test proving an active listing whose vendor has a location lands non-null
`lat`/`lng` in `search_documents`.

**Non-goals — do NOT do these:**

- **Do not block listing publication.** The `draft → active` gate is **R02-P04** and it edits
  `routers/vendor_listings.py`, which this pebble must not touch.
- **Do not seed or mutate production.** `scripts/seed_staging.py` carries hard isolation guards
  (`assert_staging_supabase_isolated`, `assert_staging_api_host_isolated`) — **do not weaken, bypass
  or parameterise them.** Backfilling the three live demo vendors is an operator act (O5), not code.
- **Do not add an open-now filter** — that is R02-P11 and is ADR-gated (ADR-R02-01).
- **Do not add a map view.** No tile library, no map dependency, at any size.
- **Do not change the completeness scoring formula or `COMPLETENESS_FIELDS`** — the five fields and
  the score are consumed by `completeness-meter.tsx`; you are surfacing them, not re-weighting them.
- No migration. No new dependency.

## 3. Files (create/modify ONLY these)

**API**

- `services/api/app/routers/vendor_profile.py` — read-only additive: expose whether the vendor has any
  location at all (distinct from "location complete") if the existing response cannot already express
  it. Change nothing about validation, upsert or scoring.
- `services/api/tests/test_vendor_profile_location.py` **(new)**
- `services/api/tests/test_search_geo_projection.py` **(new)**

**Vendor app**

- `apps/vendor/app/[locale]/_components/setup-tasks.tsx` **(new)** — the task card component.
- `apps/vendor/app/[locale]/orders/_components/order-card.tsx` — mount the card in `VendorHomeView`
  **only**; this file already hosts the archetype quick-start card at `:652-750`, so follow that
  pattern and keep the diff local.
- `apps/vendor/app/[locale]/_components/setup-tasks.test.tsx` **(new)**

**i18n**

- `packages/i18n/messages/en/vendor.json` — new keys under a single new `home.setupTasks.*` subtree.
  **English only.** Do not touch `bem`/`nya`/`fr`/`zh` — those namespaces are owned by R02-P06/P07 and
  a concurrent edit will collide.

**Seed**

- `scripts/seed_staging.py` — add `vendor_locations` rows to the existing synthetic fixtures.

**Guardrail: modify ONLY the files listed above.** In particular do not touch
`routers/vendor_listings.py` (R02-P04), `routers/directory.py` or `routers/catalog.py` (R02-P11),
`scripts/ops/verify_live.sh` (R02-P02), or any `packages/i18n/messages/{bem,nya}/**` file.

## 4. Implementation spec

1. **Task card (vendor home).** Render a card when `completeness.location` or `completeness.hours` is
   false, stating plainly what is missing and why it matters — _"Customers filtering by distance or
   browsing the directory cannot find you until your shop has a pin on the map."_ CTA links to
   `/[locale]/profile`. When both are true, render nothing.
   - It must be **recurring, not dismissible-forever**: an empty location is not a preference.
   - Reuse the existing quick-start card's markup idiom and design tokens. No new colours, no new
     spacing primitives, ≥44px touch target on the CTA.

2. **Ordering with the archetype card.** `VendorHomeView` already renders an archetype quick-start
   card. The setup-tasks card is **more urgent** (it gates discoverability) — render it **above**.
   Both may show at once; do not suppress either.

3. **Seed fixtures.** Give each seeded vendor fixture a `vendor_locations` row with plausible Lusaka
   coordinates and a landmark, plus a complete `hours` object that passes `validate_vendor_hours`
   (`vendor_profile.py:163`) — i.e. `{"mon": {"open": "08:00", "close": "17:00"}, …}` with at least
   one non-closed day. Keep the insert **idempotent** in the style of the surrounding statements
   (`ON CONFLICT … DO NOTHING` / `DO UPDATE`), and keep every value a fixed synthetic constant — the
   builder takes no user input by design (`_build_seed_sql` docstring) and must stay that way.
   - `vendor_locations` has no natural unique key beyond `id`; assign **deterministic UUIDs** to the
     fixtures so a re-run does not create duplicate branches.

4. **Projection test.** Prove the chain end to end against real Postgres: vendor + location + active
   listing ⇒ the listing's `search_documents` row carries non-null `lat`/`lng` matching the location.
   Then prove the negative: the same listing with **no** location row projects null geo. Wire it into
   the CI job that runs DB-backed tests, following the pattern used by
   `services/api/tests/test_listing_below_median.py`.

5. **Profile API.** Only touch it if the current `VendorProfileResponse` genuinely cannot distinguish
   "no location row at all" from "location row present but incomplete". `_load_primary_location`
   (`:282`) returns `None` in the first case and `_serialize_profile` (`:300`) already emits
   `lat`/`lng`/`landmark` as `None` — if that is sufficient for the card, **change nothing here** and
   say so in the report.

## 9. Security

- No authz change. `PATCH /vendor/profile` keeps `require_vendor_owner` (`:462`) and its rate-limit
  policy; do not add a route, so `ratelimit_policies.py` needs no row and the M15-P04 startup assert
  stays satisfied.
- The seed touches **staging only**. Do not log a DSN or a service-role key. Do not relax
  `_assert_no_production_markers` or the isolation guards.
- No PII in the fixtures — synthetic landmarks and coordinates only, no real vendor's address.

## 10. Tests (RUN before reporting)

- `uv run pytest services/api/tests/test_vendor_profile_location.py services/api/tests/test_search_geo_projection.py`
- `uv run pytest services/api/tests/test_vendor_profile.py` (or the existing profile suite) — prove the
  completeness contract is unchanged.
- `uv run ruff check .` · `uv run mypy app tests scripts`
- `pnpm test --filter vendor` · `pnpm lint` · `pnpm typecheck`
- `python -m py_compile scripts/seed_staging.py` and `python scripts/seed_staging.py --plan`
  (or the existing dry-run path) — the plan must show the new location rows and must still refuse a
  production target.
- `uv run pytest services/api/tests/test_seed_staging.py` — the isolation guards must still pass.

## 11. Acceptance criteria / DoD

- [ ] Vendor home shows a setup-tasks card when location or hours is missing, and nothing when both
      are present; asserted by test in both directions.
- [ ] Card renders **above** the archetype quick-start card; both can coexist.
- [ ] Zero hardcoded user-facing strings — every string is a `home.setupTasks.*` key in
      `packages/i18n/messages/en/vendor.json`; no other locale file touched.
- [ ] Staging seed inserts a `vendor_locations` row per vendor fixture, with deterministic ids and
      `validate_vendor_hours`-passing hours; re-running the seed creates no duplicate branch.
- [ ] `scripts/seed_staging.py` isolation guards **unchanged and still passing**.
- [ ] Projection test proves geo present with a location and null without one, against real Postgres.
- [ ] `routers/vendor_listings.py` **not modified** (`git diff --exit-code` on that path).
- [ ] No `packages/i18n/messages/{bem,nya,fr,zh}/**` file modified.
- [ ] No migration, no new dependency, no lockfile churn.
- [ ] Vendor app routes stay within their bundle ceilings.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P01 — Vendor location + hours completion (the geo-data unlock)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the pytest/vitest summary lines and the seed `--plan` output
**EXCERPTS:** the projection test's assertions, and the seed's location INSERT
**PROFILE API:** state explicitly whether `vendor_profile.py` needed a change, and why or why not
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
