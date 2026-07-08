> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 5 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FREEZE IS ACTIVE** (migrations additive-only) — this pebble adds **no** migration; it proves the frozen schema.

# M03-P09 — RLS isolation matrix & seed framework

## 1. Context

**Wave 5 (parallel ×6).** This is the **gate-within-the-gate**: nothing downstream dispatches until the full RLS isolation matrix is green. Grounded against as-built `master`:

- All schema is merged (`0001`→`0011`; `0011_rate_counters` lands this wave from **M04-P07** — treat its table as possibly-present: your "every table" matrix must not hardcode a table list, it must **diff `information_schema`** so new tables auto-appear).
- Every table already has RLS + `FORCE ROW LEVEL SECURITY` and a `session_user in ('postgres','supabase_admin')` guard-trigger pattern; `public.has_role(text)` reads `public.user_roles`. `auth.uid()` / `auth.jwt()` are the identity source in policies.
- Python test harness exists: `services/api/tests/` with pytest + `fastapi.testclient`, `conftest.py` clearing the service-role cache. **PyJWT is already a dependency** (M04-P02) — mint role JWTs with it; **add NO new Python deps** (M04-P07 solely owns `pyproject.toml`/`uv.lock` this wave).
- **CI integration (interface edge with M01-P09 CI-hardening, same wave):** the RLS suite needs a live Postgres. You do **not** edit `.github/workflows/ci.yml` — M01-P09 owns it and will wire a job that boots the Supabase stack (`supabase db start` → `db reset`) and runs `uv run pytest services/api/tests/rls`. Make your suite runnable by that exact command against a stack DB reachable via env (`SUPABASE_DB_URL` or the standard local `postgresql://postgres:postgres@127.0.0.1:54322/postgres`). Document the command at the top of `tests/rls/README.md`.
  Spec: `docs/plan/02-pebbles/M03-data-core.md` §M03-P09.

## 2. Objective & scope

A pytest harness that executes SQL as each role and asserts the **full isolation matrix**: every table × {anon, customer, other-customer, vendor, other-vendor, admin} × {select, insert, update, delete}; plus an idempotent seed framework producing a browsable demo dataset.
**Non-goals:** no schema changes (freeze), no catalog stub seed (M03-P10 owns `supabase/seed.sql` + category tree), no CI yaml edits (M01-P09), no app code.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/tests/rls/__init__.py` · `services/api/tests/rls/conftest.py` (role-JWT factories: anon/customer/vendorA/vendorB/admin + a per-role DB connection or PostgREST client) · `services/api/tests/rls/test_matrix.py` (the matrix) · `services/api/tests/rls/test_no_untested_tables.py` · `services/api/tests/rls/README.md` · `scripts/seed.py` · `services/api/tests/fixtures/demo/` (fixture data the seed + matrix share)
  **Guardrail: nothing else. Do NOT edit the root `tests/conftest.py`, `pyproject.toml`, `.github/**`, or any migration.**

## 4. Implementation spec

- **Role connections:** connect to the DB as each logical role by setting the request JWT claims Postgres reads (`set local request.jwt.claims = '{...}'` / `set local role authenticated`) inside a transaction, OR go through PostgREST with a minted JWT. Prefer **direct SQL with `SET LOCAL "request.jwt.claims"`** + `SET LOCAL ROLE` (anon/authenticated) — deterministic and stack-independent. `conftest.py` exposes fixtures `as_anon`, `as_customer(uid)`, `as_vendor(uid)`, `as_admin(uid)` that yield a cursor scoped to that role.
- **Matrix (`test_matrix.py`):** parametrize over `information_schema.tables` (schema `public`) × the 6 role-personas × the 4 verbs. For each cell assert the expected outcome (allowed rows / 0 rows / permission error). Encode expectations in a **declarative table** (`EXPECTATIONS: dict[table] -> per-role-per-verb`) so a missing table is a hard failure, not a silent skip. **Cross-vendor denial is the headline:** vendorB cannot select/update/delete vendorA's `vendor_listings`, `payouts`, quotes, orders, etc.; other-customer cannot read a stranger's `orders`/`payments`/`invoices`/`addresses`; anon reads only public-catalog + published rows; `notification_outbox`/`audit_log`/ledger tables → zero client access for all non-service roles.
- **`test_no_untested_tables.py`:** query `information_schema.tables` and assert every `public` base table has an entry in `EXPECTATIONS` — fails the build when a future migration adds an untested table. (This is the "CI check diffs information_schema" AC.)
- **`scripts/seed.py`:** idempotent, `--env local|staging`; upserts a browsable demo dataset — a sandbox-flagged demo vendor + a couple real-shaped vendors, listings across verticals, an event with ticket types, a service, and orders in varied states (pending/paid/delivered/completed) so home/PLP/PDP render. Uses the service-role client. Re-running mutates nothing (stable ids / `on conflict do nothing`). Reads shared fixtures from `tests/fixtures/demo/`.

## 5–8. UI/UX · Responsiveness · Performance · SEO

N/A.

## 9. Security

The matrix **is** the security proof: cross-tenant reads/writes denied on every table; service-role-only tables invisible to clients; forged-role JWT (claim without a `user_roles` row) gets no privilege (roles come from DB). Seed never disables RLS.

## 10. Tests (RUN before reporting)

Boot a local stack (or point at one), `supabase db reset`, then `uv run pytest services/api/tests/rls -q` — paste the matrix summary (counts of allow/deny cells) + the cross-vendor denial cases + `test_no_untested_tables` passing. Run `python scripts/seed.py --env local` twice; show the second run is a no-op (idempotent) and that row counts let home/PLP/PDP populate. `uv run ruff check`, `uv run mypy` on the new files.

## 11. Acceptance criteria / DoD

- [ ] Explicit expectation for EVERY `public` table (enforced by `test_no_untested_tables`); no unlisted tables.
- [ ] Cross-vendor + cross-customer denial proven; service-role-only tables client-invisible.
- [ ] `scripts/seed.py` idempotent; seed → home/PLP/PDP browsable.
- [ ] Suite runs green via the single command M01-P09 will wire into CI; ruff+mypy clean.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M03-P09 — RLS isolation matrix & seed framework
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste the matrix summary + cross-tenant denial cases + no-untested-tables + idempotent-seed output
**EXCERPTS:** the `EXPECTATIONS` table shape + the role-scoping fixture (`conftest.py` core) — nothing else
**QUESTIONS:** (or "none")
