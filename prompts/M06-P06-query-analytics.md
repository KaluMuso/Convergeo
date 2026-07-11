> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **⚠ SCHEMA: you own migration `0027` (search analytics).** **⚙ CI GATING (M10 lesson):** your DB-backed test file must be **isolation-clean** (seed AND tear down your own rows — shared Postgres) and green via `uv run pytest <yourfile>` on a real DB; per-pebble seeding is CI-invisible. **Do NOT edit `.github/workflows/ci.yml`** (M06-P05 owns it this wave; the converger wires your file into the rls-job blocking step at merge). **Run the FULL `uv run pytest` before reporting.**

# M06-P06 — Query analytics & zero-result mining

## 1. Context

**Grounded against as-built `master`:**

- **Search + Ask both exist:** `search_rrf` (0009) powers search; `POST /ask` (M06-P02) powers Ask. Log **every** search + ask query, anonymized (no user id retained past 30d — Zambia DPA-aligned).
- **Latest migration is `0026`** → you own **`0027_search_analytics.sql`** (renumber to next free slot if claimed at merge).
- **Admin data endpoints** feed the M13-P09 dashboard (already merged) — expose read endpoints; do NOT edit the dashboard.
  Spec: `docs/plan/02-pebbles/M06-ask-vergeo.md` §M06-P06.

## 2. Objective & scope

Fire-and-forget query logging (search + ask) into a `search_query_log` table; anonymized with a 30-day PII-retention trim; admin-role aggregate endpoints (top terms, zero-result terms, ask cost/day) for the merchandising dashboard.
**Non-goals:** no search/ask algorithm change, no dashboard UI (M13-P09 — endpoints only), no user-id retention beyond 30d.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/analytics/search_log.py` (fire-and-forget `log_search_query(...)` / `log_ask_query(...)` + aggregate queries + retention trim) · `services/api/app/routers/admin_search_insights.py` (admin-role: top terms, zero-result terms, ask cost/day) · `supabase/migrations/0027_search_analytics.sql` · `services/api/tests/test_search_analytics.py`
  **Also add** the new table to `services/api/tests/rls/test_matrix.py` EXPECTATIONS (admin-read / service-role-write, model on `funnel_events` — a new-table pebble owns its RLS-matrix row).
  **Guardrail: nothing else. Do NOT wire logging into the live search/ask routers in THIS pebble (add the logger; hook-wiring is a follow-up to avoid touching `search.py`/`ask.py` here); do NOT edit `main.py`, db.ts beyond `0027`, ci.yml.**

## 4. Implementation spec

- **`0027`:** `search_query_log` (`id`, `kind text check in ('search','ask')`, `term text`, `normalized_term text`, `entity_counts jsonb`, `zero_result boolean`, `usd_micros bigint default 0` for ask cost, `user_id uuid null` (nullable — trimmed after 30d), `created_at timestamptz`). Indexes on `(kind, created_at)`, `(zero_result) where zero_result`. RLS: admin read (`has_role('admin')`), service-role write; enable + FORCE. Reversible.
- **`search_log.py`:** `log_search_query`/`log_ask_query` insert via service-role client (best-effort, swallow errors so logging never breaks a request — <5ms, fire-and-forget). `trim_search_pii(now)` NULLs `user_id` where `created_at < now-30d`. Aggregates: `top_terms(days)`, `zero_result_terms(days)`, `ask_cost_by_day(days)`.
- **`admin_search_insights.py`** (auth, admin-only, uniform envelope): `GET /admin/search-insights/top-terms`, `/zero-results`, `/ask-cost` (query-param window). Non-admin → 403.

## 5–9. Security etc.

Admin-only reads; fire-and-forget logging swallows errors (never breaks the logged request); 30d PII trim (DPA); service-role writes only; no secrets.

## 10. Tests (RUN before reporting)

`test_search_analytics.py` (isolation-clean, real DB): insert search+ask logs → aggregates match fixtures; zero-result report; retention trim NULLs old `user_id`; admin-only 403 for non-admin. `0027` replay note (use `tests.rls.conftest.MIGRATIONS_DIR`, NOT a hardcoded path). Full `uv run pytest` (DB tests skip cleanly without Postgres), `uv run ruff check .`, `uv run mypy .`.

## 11. Acceptance criteria / DoD

- [ ] Logging is fire-and-forget (errors swallowed); zero-result report matches fixtures; retention trim removes PII after 30d; admin-only access.
- [ ] `0027` additive+reversible + RLS-matrix entry added; full API suite green (or DB tests skip); ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M06-P06 — Query analytics & zero-result mining
**STATUS/FILES/DEVIATIONS** (the log schema; fire-and-forget error swallow; retention trim; why logging isn't wired into live routers here) **/TESTS** (paste aggregate + retention + admin-authz + replay + full-pytest tail) **/EXCERPTS** the log-insert path + retention trim + admin authz — nothing else **/QUESTIONS**
