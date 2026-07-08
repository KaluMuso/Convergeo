> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 5 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FREEZE ACTIVE** — additive-only: your ONE new migration `0011_rate_counters.sql` is fine (new table). **You are the SOLE owner of `services/api/pyproject.toml` + `uv.lock` this wave** (you add SlowAPI). No other W5 pebble adds Python deps.

# M04-P07 — Rate limiting & OTP abuse guards

## 1. Context

**Wave 5 (parallel ×6).** Grounded against as-built `master`:

- `services/api/app/` has `settings.py` (pydantic-settings), `errors.py` (envelope `{"error":{code,message,details,request_id}}` + `AppError`), `core/` (`auth.py` — `CurrentUser`, `require_role`; `supabase.py` — user-token client), `supabase_client.py` (`get_supabase_service_client()` — the ONE service-role module), `main.py` (router **auto-discovery** via `pkgutil` — never edit it), `routers/{health,media}.py`.
- **No Redis in stack** (budget) → counters are **Postgres-backed**. Config-table tuning: `0008_config.sql` holds platform config (limits should be readable/tunable from there where sensible).
- Migration numbering: last is `0010_profile_bootstrap.sql` → yours is **`0011_rate_counters.sql`**. Tables need RLS + `FORCE` + `session_user` guard + service-role-only policies (clients never read counters). **db.ts:** append your `rate_counters` table (M03-P10 is the authoritative regenerator + merges last — it folds your table in; you still append so an interim tree compiles).
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P07.

## 2. Objective & scope

Postgres-backed per-number and per-IP OTP caps + exponential resend cooldown + global auth-endpoint limits, with i18n-keyed `retry-after`, plus a counters table with TTL cleanup.
**Non-goals:** no auth UI (M04-P04 surfaces the 429 states you define), no login endpoints themselves (guards + a reusable dependency), no schema beyond the counters table.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/core/ratelimit.py` (SlowAPI limiter + Postgres counter store) · `services/api/app/routers/auth_guard.py` (guard dependency/endpoints: check-and-increment, retry-after) · `supabase/migrations/0011_rate_counters.sql` · `supabase/tests/0011_rate_counters.test.sql` · `services/api/tests/test_ratelimit.py`
- **Modify:** `services/api/pyproject.toml` + `uv.lock` (add `slowapi`) · `packages/types/src/db.ts` (**append** `rate_counters` only — no sibling reformatting; M03-P10 regenerates authoritatively)
  **Guardrail: nothing else. Do NOT edit `main.py`, `core/__init__.py`, `core/auth.py`/`supabase.py`, other routers, or `0006`–`0010`.**

## 4. Implementation spec

- **`0011_rate_counters.sql`:** `rate_counters(id, key text not null, scope text check in ('otp_number','otp_ip','auth_ip','auth_number'), window_start timestamptz not null, count int not null default 0, expires_at timestamptz not null, unique(scope, key, window_start))`; index on `(expires_at)` for TTL cleanup and `(scope, key)` for lookup. RLS + FORCE; **service-role-only** (zero client policies) + `session_user` guard. A `security definer` function `public.bump_rate_counter(p_scope, p_key, p_window interval, p_limit int)` that upserts the current window's row, increments, and returns `(allowed bool, retry_after_seconds int)` atomically (single statement / `FOR UPDATE`). A cleanup helper deleting `expires_at < now()`.
- **`core/ratelimit.py`:** SlowAPI limiter configured to use the Postgres store (custom key func: per-number, per-IP); exponential resend cooldown (e.g. 30s·2^n up to a cap); caps like **5/hour/number, 20/day/IP** but **read from `platform_config` where present** (tunable). On breach → `AppError(code='rate_limited', http_status=429, details={'retry_after': n})` so the envelope carries `retry_after` (M04-P04 reads it).
- **`routers/auth_guard.py`:** a reusable `require_otp_quota(number, ip)` dependency + a lightweight endpoint the OTP flow calls to check/increment; per-number vs per-IP counters independent; lockout messaging i18n-keyed (return codes the UI maps).

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A. Counter bump is one indexed upsert; TTL cleanup cheap.

## 9. Security

Brute-force blocked (per-number + per-IP, independent); counters service-role-only + guard-trigger (clients cannot read/forge); no secrets; `retry_after` never leaks whether a number exists beyond the standard throttle.

## 10. Tests (RUN before reporting — `uv run pytest`, `ruff`, `mypy`)

`test_ratelimit.py`: cap breach → 429 with `retry_after`; window expiry restores; **per-number vs per-IP independence**; exponential cooldown grows. `0011_rate_counters.test.sql`: migrations `0001→0011` apply clean; `bump_rate_counter` atomic allow→deny at limit; client cannot read `rate_counters` (RLS); TTL cleanup removes expired. Regenerate/append `db.ts`; `pnpm --filter @vergeo/types typecheck`. `uv run ruff check`, `uv run mypy` green.

## 11. Acceptance criteria / DoD

- [ ] Brute-force script blocked (tested); legit resend unaffected; limits config-tunable.
- [ ] `0011` applies clean in sequence; counters service-role-only; `bump_rate_counter` atomic.
- [ ] 429 carries `retry_after` in the error envelope; db.ts appended; Python + types green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M04-P07 — Rate limiting & OTP abuse guards
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste 429+retry-after, per-number/per-IP independence, migration+RLS, mypy/ruff output
**EXCERPTS:** `bump_rate_counter` SQL + the limiter breach→429 path — nothing else
**QUESTIONS:** (or "none")
