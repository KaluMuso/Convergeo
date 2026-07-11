> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel **batch 2** — dispatched only AFTER M11-P05 + M15-P07 merge, so the route set is COMPLETE). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-17 creator of `services/api/app/core/ratelimit_policies.py`.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master`, never stash). **⚙ CI GATING:** `test_ratelimit_sweep.py` must be pure-unit (no DB). **Run the FULL `uv run pytest` before reporting.**

# M15-P04 — Rate-limit sweep & input fuzz

## 1. Context

**Grounded against as-built `master`:**

- **`services/api/app/core/ratelimit.py` exists** with `bump_rate_counter(scope, ...)` (line ~187) + `raise_rate_limited(...)` (line ~217). This is the enforcement primitive. **You add a POLICY REGISTRY on top — `ratelimit_policies.py` — that declares a limit for every mutating route and asserts, at app startup, that no mutating route is unregistered.**
- **The full router set is stable at batch-2 dispatch** (M11-P05 job-completion + M15-P07 invoices merged). Enumerate EVERY mutating route (POST/PUT/PATCH/DELETE) across `services/api/app/routers/*` — the registry must cover all of them.
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P04.

## 2. Objective & scope

A central rate-limit policy registry (every mutating route MUST declare a limit — startup assert fails on an unregistered mutating route), a sweep test proving coverage, and an OpenAPI-driven input-fuzz suite (type confusion, huge payloads, unicode, negative/overflow ints on money fields).
**Non-goals:** no change to `ratelimit.py`'s primitive (build ON it), no new route, no per-route business-logic change (the registry is declarative — wire enforcement via the existing dependency/middleware, not by editing every router if avoidable).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/core/ratelimit_policies.py` (central registry: `POLICIES: dict[route_id, RateLimitPolicy]`; a `assert_all_mutating_routes_covered(app)` called at startup that walks the FastAPI route table and raises on any uncovered POST/PUT/PATCH/DELETE) · `services/api/tests/test_ratelimit_sweep.py` · `services/api/tests/fuzz/test_input_fuzz.py` (+ `tests/fuzz/__init__.py` if needed)
- **Modify:** `services/api/app/main.py` (ONLY to call `assert_all_mutating_routes_covered(app)` on startup — one hook; if a converger conflict risk exists, note it). **If the existing rate-limit enforcement is a shared dependency, prefer wiring the registry into THAT dependency rather than editing routers.**
  **Guardrail: nothing else. Do NOT edit `ratelimit.py`'s primitive, `ci.yml` (M15-P05 owns it this wave — converger wires the fuzz job), db.ts, migrations, individual routers (unless a route legitimately lacks any limit — then add the registry entry, not router logic).**

## 4. Implementation spec

- **`ratelimit_policies.py`:** `RateLimitPolicy(scope, limit, window)`; `POLICIES` keyed by a stable route id (method + path, or the endpoint function's qualname). `assert_all_mutating_routes_covered(app)`: iterate `app.routes`, collect every route whose methods intersect `{POST,PUT,PATCH,DELETE}`, subtract webhook/health exemptions (explicit allowlist, documented), and raise a clear error listing any uncovered route. Called once at startup (import-time or lifespan) so a new unregistered mutating route fails CI immediately.
- **`test_ratelimit_sweep.py`:** build the app, assert `assert_all_mutating_routes_covered` passes for the current route set; assert that a synthetic unregistered mutating route WOULD raise (proves the guard has teeth).
- **`test_input_fuzz.py`:** schemathesis/hypothesis over the OpenAPI schema (or hypothesis strategies against the money/int fields if schemathesis is heavy): type confusion, oversized payloads, unicode, **negative/overflow ints on ngwee money fields** (must be rejected by Pydantic, never persisted). Keep it deterministic/bounded (fixed seed via settings, capped examples) so CI is stable — no `Math.random`-style flake.

## 5–9. Security etc.

Every mutating route has a declared limit (startup assert — the core deliverable); webhook/health exemptions are an explicit documented allowlist (no silent gaps); money fuzz proves negative/overflow ngwee is rejected (no float, no overflow persist); fuzz suite deterministic; no secrets.

## 10. Tests (RUN before reporting)

`test_ratelimit_sweep.py` (coverage passes + synthetic-route guard raises); `test_input_fuzz.py` (bounded, deterministic — money overflow/negative rejected). **Full `uv run pytest`** (confirm startup assert doesn't break existing app construction). `uv run ruff check . && uv run mypy app tests`.

## 11. Acceptance criteria / DoD

- [ ] Startup assert covers 100% of mutating routes (explicit documented exemptions only); sweep test proves teeth; fuzz rejects negative/overflow money + type confusion, deterministically.
- [ ] Built on `ratelimit.py`'s primitive (no primitive change); full API suite + ruff + mypy green; no router business-logic churn.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P04 — Rate-limit sweep & input fuzz
**STATUS/FILES/DEVIATIONS** (the registry shape + route-id keying; the exemption allowlist; how enforcement wires in without per-router edits; the fuzz determinism approach) **/TESTS** (paste coverage-pass + synthetic-guard-raises + money-fuzz + full-pytest tail) **/EXCERPTS** `assert_all_mutating_routes_covered` + the money-overflow fuzz case — nothing else **/QUESTIONS** (list any route you had to add a policy for that surprised you)
