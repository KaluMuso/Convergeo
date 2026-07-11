> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel batch 1). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-17 editor of `apps/customer/app/[locale]/layout.tsx`** (M16-P04 was told NOT to touch it). **Your migration is `0029` (next free — 0028 is the latest on master).** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master`, never stash). **⚙ CI GATING:** any DB test must be isolation-clean; converger wires it into the rls step + **hand-authors the `db.ts` block for your migration** (leave `packages/types/src/db.ts` for the converger — do NOT edit it, but paste your CREATE TABLE + any function signatures in the report so it can). **Run the FULL `uv run pytest` before reporting.**

# M16-P05 — Analytics (unify server event streams + GA4 mirror)

## 1. Context

**Grounded against as-built `master`:**

- **Two server-side streams already exist:** `services/api/app/services/analytics/funnel.py` (M07-P08 funnel events, table `funnel_events` from migration `0025`) and `services/api/app/services/analytics/search_log.py` (M06-P06/M07 search-term + zero-results, `search_query_log` from `0027`). **UNIFY these into one queryable schema — do NOT delete the existing tables; add a unifying view or a superset events table (`0029`) that both streams write to / are queryable through.** Prefer additive: a unified `analytics_events` table + a compatibility path, OR a view over the existing tables. Pick the lower-risk option and document why.
- **`packages/analytics/` does NOT exist — you create it** (GA4 wrapper: consent-aware, data-frugal beacon batching). GA4 is a convenience mirror; **the server log is the source of truth (ad-blocker-proof).**
- **GA4 wiring goes in `apps/customer/app/[locale]/layout.tsx`** (you own this edit this wave). **CSP must already allow GA4** (M15-P03 allowlists `*.googletagmanager.com`/`google-analytics.com`) — do NOT edit any `next.config.ts` (M15-P03 owns them); rely on their allowance.
  Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P05.

## 2. Objective & scope

Unify M06-P06 + M07-P08 server streams into one queryable schema (`0029`), a consent-aware data-frugal GA4 wrapper (`packages/analytics/`), GA4 wiring in the customer layout, and an event dictionary. Funnel queryable end-to-end (search→PDP→cart→pay) from the server log; consent refusal disables GA4 only (server log anonymized regardless).
**Non-goals:** no change to how existing streams currently emit beyond routing them into the unified schema; no vendor/admin GA4; no new business events beyond the funnel/search/AI set already emitted; no `db.ts` edit (converger).

## 3. Files (create/modify ONLY these)

- **Create:** `supabase/migrations/0029_analytics_unify.sql` (unified schema/view + RLS + FORCE — admin-read/service-write; NO client read of raw events) · `packages/analytics/` (package.json + `src/` GA4 wrapper: consent gate, beacon batching, typed `track()`) · `services/api/app/services/analytics/events.py` (the unified query/emit surface over funnel + search) · `docs/ops/analytics-events.md` (event dictionary) · `services/api/tests/test_analytics_unify.py`
- **Modify:** `apps/customer/app/[locale]/layout.tsx` (mount the consent-aware GA4 wrapper — SSR-safe, no layout-shift, deferred script) · `services/api/app/services/analytics/funnel.py` and/or `search_log.py` (ONLY if the unification requires them to also write the unified row — keep minimal; prefer a view that needs no emit change) · `packages/i18n/messages/en/*.json` ONLY if the consent banner needs a key — **prefer an existing consent/common key; do NOT create `marketing.json` (M16-P04 owns it) or touch `legal`.**
  **Guardrail: nothing else. Do NOT edit `packages/types/src/db.ts` (converger hand-authors it — paste your DDL in the report), any `next.config.ts` (M15-P03), other migrations, other apps' layouts.**

## 4. Implementation spec

- **`0029_analytics_unify.sql`:** additive. Either (a) `analytics_events` superset table (event_type, entity, session/user, ts, jsonb props) that funnel + search rows are inserted into alongside their existing tables, or (b) a `analytics_events` VIEW union-ing the existing tables into one shape. RLS+FORCE: service-role write, admin read, **no client/anon read of raw events**. Server log rows anonymized (no raw PII) regardless of consent.
- **`packages/analytics/`:** typed `track(event, props)`; consent-aware (reads the consent state — GA4 fires ONLY on consent; server beacon always allowed, anonymized); data-frugal (batch beacons, `navigator.sendBeacon`, no per-event XHR); GA4 measurement id from `NEXT_PUBLIC_*` env (never hardcoded).
- **`events.py`:** one queryable surface — `record_event(...)` + a funnel query helper (search→PDP→cart→pay) reading the unified schema. Existing callers keep working.
- **`layout.tsx`:** deferred GA4 script + consent gate; SSR-safe; no CLS; respects DPA (consent refusal → GA4 off, server log still anonymized).

## 5–9. Security etc.

RLS+FORCE on the unified schema (admin-read/service-write, no client read — assert in the RLS matrix note for the converger); server log anonymized (no raw PII); GA4 gated on consent (assert consent-refusal disables GA4 only); GA4 id from env only (no secret in repo); integer ngwee for any money prop; migration additive + reversible.

## 10. Tests (RUN before reporting)

`test_analytics_unify.py`: unified schema query returns a full funnel (search→PDP→cart→pay) from seeded events; existing funnel/search emits still land; anonymization (no raw PII column populated). Package: `track()` batches + skips GA4 when consent=false (unit). `pnpm --filter customer build/typecheck/lint`; **full `uv run pytest`**; migration replays clean (`scripts/ci/migration-replay.sh` locally if possible).

## 11. Acceptance criteria / DoD

- [ ] Funnel queryable end-to-end from the unified server schema; existing streams unbroken; GA4 mirror consent-gated (refusal disables GA4 only); server log anonymized.
- [ ] Migration `0029` additive + RLS+FORCE (no client read); `db.ts` DDL pasted for converger (not edited); customer build + full API suite + migration replay green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P05 — Analytics
**STATUS/FILES/DEVIATIONS** (view vs superset-table choice + why; how existing streams route into the unified schema; GA4 consent gate; the `0029` DDL + any function signatures **verbatim for the converger's db.ts**) **/TESTS** (paste funnel-query + consent-gate + anonymization + migration-replay + full-pytest tail) **/EXCERPTS** the `0029` DDL, the consent gate in the GA4 wrapper, the funnel query — nothing else **/QUESTIONS**
