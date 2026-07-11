> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **⚠ SCHEMA: you own migration `0028` (review aggregates).** **⚙ CI GATING (M10 lesson):** your DB-backed test file must be **isolation-clean** (seed + tear down your own rows — shared Postgres) and green via `uv run pytest <yourfile>` on a real DB; per-pebble seeding is CI-invisible. **Do NOT edit `.github/workflows/ci.yml`** (converger wires your file into the rls-job blocking step at merge). **Run the FULL `uv run pytest` before reporting.**

# M15-P02 — Review aggregation & moderation surface

## 1. Context

**Grounded against as-built `master` (reviews + search MERGED):**

- **`reviews` (0007):** `rating int check between 1 and 5`, verified-purchase (FK + delivered), vendor_reply. **NO rating-aggregate columns exist anywhere** → you own **migration `0028`** to store the aggregate (Bayesian avg + count) **per listing + per vendor** (renumber to next free slot if claimed at merge).
- **Search boost:** `search_documents.boost_signals jsonb` (0009) — sync the aggregate into `boost_signals` (the search index reads this). The upsert paths that write `boost_signals` live in 0009's functions — **sync via your aggregate service (service-role update), do NOT rewrite 0009's functions.**
- **Bayesian average** (D-decision): `bayes = (C*m + sum_ratings) / (C + n)` where `m` = platform mean prior, `C` = confidence weight (config). Prevents 1-review-5-star gaming. Nightly recompute + incremental on write.
- **Report flow** → the M13-P04 admin flags queue (merged) — reuse it; do NOT build a new queue.
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P02.

## 2. Objective & scope

Bayesian review aggregation (per listing + per vendor), stored in `0028`, synced into `search_documents.boost_signals`, surfaced as the single source of star ratings on cards/PDP; a report-review flow into the existing admin flags queue; nightly recompute + incremental-on-write.
**Non-goals:** no review-submission change (M15-P01, merged), no new flags queue (reuse M13-P04), no 0009 function rewrite, no card component rewrite (feed them the aggregate).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/reviews/aggregate.py` (Bayesian compute; per-listing + per-vendor; nightly recompute + incremental; `boost_signals` sync via service-role update) · `supabase/migrations/0028_review_aggregates.sql` (aggregate storage: `rating_bayes numeric`/or ngwee-style scaled int, `rating_count int`, `rating_sum int` per listing + per vendor — columns on existing tables or a small aggregate table; + config for `m`/`C`) · `services/api/app/routers/internal_review_aggregate.py` (internal-token nightly recompute tick) · `apps/customer/app/[locale]/(shop)/p/[slug]/_components/report-review.tsx` (report → M13-P04 flags queue) · `services/api/tests/test_review_aggregate.py`
- **Also add** any new aggregate table to `services/api/tests/rls/test_matrix.py` EXPECTATIONS (public-read / service-role-write — cards read it; model on an existing public-read table).
  **Guardrail: nothing else. Do NOT edit 0009 search functions, `reviews` submission routers (M15-P01), card components (feed them the aggregate value), `main.py`, db.ts beyond `0028`, ci.yml.**

## 4. Implementation spec

- **`0028`:** store `rating_count`, `rating_sum`, and the Bayesian result per listing and per vendor (columns on `vendor_listings`/`vendors`, or a `review_aggregates` table keyed by `(entity_kind, entity_id)` — pick one, document it; additive + reversible). Seed `m` (platform mean prior) + `C` (confidence weight) into `platform_config` (or read-with-default). RLS: public read (cards need it), service-role write.
- **`aggregate.py`:** `recompute_all()` (nightly) + `apply_review(review)` (incremental on write) → `bayes = (C*m + rating_sum)/(C + rating_count)`; write the aggregate; sync into `search_documents.boost_signals` (service-role update, merge the rating signal into the existing jsonb — do not clobber other signals). Incremental and nightly must converge (tested).
- **`internal_review_aggregate.py`:** internal-token tick → `recompute_all()`.
- **`report-review.tsx`:** report CTA → POST to the existing M13-P04 flags/report endpoint (reuse; do not invent). 360px.

## 5–9. Security etc.

Public-read aggregate (single source for stars everywhere); service-role writes; report lands in the existing admin queue; Bayesian prevents low-n gaming; boost sync merges (no clobber); internal tick token-guarded; no float drift on the count/sum (integers; the bayes value may be numeric); no secrets.

## 10. Tests (RUN before reporting)

`test_review_aggregate.py` (isolation-clean, real DB): **Bayesian goldens** (0 reviews → prior m; 1 review; many reviews — exact formula match); **incremental vs nightly consistency** (apply_review sequence == recompute_all); **boost sync** (rating signal merged into `boost_signals` without clobbering existing keys); report → lands in flags queue; `0028` replay note (use `tests.rls.conftest.MIGRATIONS_DIR`). Full `uv run pytest`, `uv run ruff check .`, `uv run mypy .`, `pnpm --filter customer build/typecheck/lint`.

## 11. Acceptance criteria / DoD

- [ ] Aggregate matches the Bayesian formula goldens; card stars == aggregate everywhere (single source); report lands in the admin queue; incremental == nightly.
- [ ] `0028` additive+reversible + RLS-matrix entry; boost sync merges (no clobber); full API suite green (or DB tests skip); customer build + ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P02 — Review aggregation & moderation surface
**STATUS/FILES/DEVIATIONS** (aggregate storage choice; the Bayesian formula + m/C config; incremental vs nightly; boost-signals merge-not-clobber; report-queue reuse) **/TESTS** (paste Bayesian-goldens + incremental-vs-nightly + boost-sync + replay + full-pytest tail) **/EXCERPTS** the Bayesian compute + boost_signals merge — nothing else **/QUESTIONS**
