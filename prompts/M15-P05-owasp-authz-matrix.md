> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel **batch 2** — dispatched only AFTER M11-P05 + M15-P07 merge, so the route × role set is COMPLETE). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-17 editor of `.github/workflows/ci.yml`** (M15-P03/P04 deferred their CI wiring to you — see below). **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master`, never stash). **⚙ CI GATING:** `test_authz_matrix.py` must be isolation-clean. **Run the FULL `uv run pytest` before reporting.**

# M15-P05 — OWASP audit, pen-test-lite & CI security gates

## 1. Context

**Grounded against as-built `master`:**

- **`.github/workflows/ci.yml` current state (READ IT FIRST):** `deps-audit` job already runs `pnpm audit --audit-level=high` + `pip-audit` but both are `continue-on-error: true` (non-blocking); `secret-scan` (gitleaks) is `continue-on-error: true`. Your job: make the security audits **fail-on-high** (flip the relevant `continue-on-error` to blocking, or add a blocking step) and add the authz-matrix test + header-check to the pipeline. Optional `zap-baseline` job.
- **Two Wave-17 siblings deferred their CI wiring to you (converger-style, but you own ci.yml):** M15-P03 shipped `scripts/ci/check-headers.mjs` (wire it into a CI step); M15-P04 shipped the rate-limit sweep + fuzz tests (ensure `test_ratelimit_sweep.py` + `tests/fuzz` run — they run under the existing `python` pytest job automatically, but confirm and add the fuzz path if it's excluded). **Only add the wiring; do NOT edit their files.**
- **Route × role set is complete at batch-2 dispatch.** Build the authz matrix over EVERY route × EVERY role from the OpenAPI schema.
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P05.

## 2. Objective & scope

OWASP Top-10 audit doc (each item → code/test evidence or finding+fix ref), a pen-test-lite script (authz-matrix probe every route × role, IDOR probes on id params, SSRF/redirect checks), a route×role authz matrix TEST, and CI security gates (deps fail-on-high + header-check + authz matrix wired; zap-baseline optional).
**Non-goals:** no app logic fix (findings → doc + fix-prompt references for a later wave), no change to sibling files, no new business route.

## 3. Files (create/modify ONLY these)

- **Create:** `docs/ops/owasp-audit.md` (Top-10 checklist vs codebase — evidence links or finding+fix ref) · `scripts/security/pentest-lite.sh` (authz-matrix probe every route × role from OpenAPI; IDOR probes on `{id}` params; SSRF/open-redirect checks) · `services/api/tests/test_authz_matrix.py` (every route × role → expected allow/deny)
- **Modify:** `.github/workflows/ci.yml` (deps-audit → fail-on-high blocking; add a step running `node scripts/ci/check-headers.mjs`; ensure `test_authz_matrix.py` + `tests/fuzz` execute in a blocking job; optional `zap-baseline` job as non-blocking)
  **Guardrail: nothing else. Do NOT edit `check-headers.mjs` (M15-P03 owns it), `ratelimit_policies.py`/fuzz tests (M15-P04 owns them), app routers, db.ts, migrations. If the authz matrix reveals a real vuln, DOCUMENT it (owasp-audit.md) + write a failing/xfail test — do NOT fix app code this wave.**

## 4. Implementation spec

- **`test_authz_matrix.py`:** enumerate routes from the FastAPI/OpenAPI schema; for each (route, role∈{anon,customer,other-customer,vendor,other-vendor,admin}) assert the expected status class (allow vs 401/403/404). Mirror the RLS-matrix EXPECTATIONS style. IDOR: for `{id}` routes, a different owner's id → 403/404 (never 200 with another user's data). This is the enforcement backbone — it must be DB-isolation-clean (converger wires it into the rls blocking step; it also runs under `python` if no DB needed — prefer no-DB via dependency overrides where feasible).
- **`pentest-lite.sh`:** runnable against a local server; probes the authz matrix, IDOR on id params, SSRF/open-redirect on any URL-accepting field; emits a report; non-zero exit on a high finding.
- **`owasp-audit.md`:** Top-10 rows, each → evidence (code/test path) or a finding + a `prompts/fixes/*` reference to open later.
- **`ci.yml`:** flip deps-audit high findings to blocking; add `node scripts/ci/check-headers.mjs`; confirm `test_authz_matrix.py` + `tests/fuzz` run in a required job. Keep the CLI pin (`supabase/setup-cli@v2` version `2.109.1`) and existing job structure — additive edits only, no reshaping the file.

## 5–9. Security etc.

Authz matrix covers 100% of routes × roles (IDOR/403 asserted); deps fail-on-high blocking; header-check blocking; findings documented (not silently fixed) with fix-prompt refs; pentest script non-zero on high; no secrets in CI (dummy values only, per existing db/rls jobs).

## 10. Tests (RUN before reporting)

`test_authz_matrix.py` (full route×role — green, or xfail-documented for any real finding); `bash scripts/security/pentest-lite.sh` against a local server (report clean or documented); validate the ci.yml edit with `actionlint` if available or a YAML parse. **Full `uv run pytest`.** Confirm the deps-audit flip doesn't red the pipeline on a pre-existing high (if it does, document + pin/ignore with justification, don't silently `continue-on-error` again).

## 11. Acceptance criteria / DoD

- [ ] Authz matrix 100% route×role (IDOR asserted); OWASP Top-10 doc with evidence/finding refs; pentest-lite script; deps fail-on-high + header-check + authz matrix wired into CI (blocking).
- [ ] No app-code fixes (findings documented + fix-prompt refs); no sibling-file edits; full API suite green; ci.yml edit is additive + valid.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P05 — OWASP audit, pen-test-lite & CI security gates
**STATUS/FILES/DEVIATIONS** (route×role coverage count; any IDOR/authz findings + how you documented vs fixed; the exact ci.yml steps added; whether deps fail-on-high surfaced a pre-existing high) **/TESTS** (paste authz-matrix summary + pentest-lite output + full-pytest tail) **/EXCERPTS** the authz-matrix EXPECTATIONS + IDOR assertion + the ci.yml diff — nothing else **/QUESTIONS** (list any finding needing a founder decision)
