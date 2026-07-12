> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (parallel batch 1). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (`git worktree add /tmp/base origin/master`). **⚠ DEFERRED-AC:** the suite going GREEN on deployed staging against Lenco sandbox needs infra + Lenco-sandbox creds (founder gate F9b) this build env lacks — build the full suite + config + fixtures + CI job, smoke-validate what you can against a LOCAL dev server, and mark the staging-green + Lenco-sandbox-pay AC as founder/staging-gated. Do NOT block the PR on staging.

# M16-P07 — E2E suite (Playwright)

## 1. Context

**Grounded against as-built `master`:** three apps (`apps/customer|vendor|admin`, Next 15, `[locale]/` routing); FastAPI API; critical flows all built through Wave 17 (browse→PDP→cart→checkout→MoMo/COD; vendor onboard→list→order→ship; event ticket buy→wallet→scanner-verify→duplicate-reject; auth OTP). **Chromium is pre-installed** (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`; do NOT run `playwright install`). **No `e2e/` dir yet.** Lenco has a sandbox (creds = founder gate F9b, not in this env); WhatsApp uses a mock adapter flag. **No deployed staging is reachable here** — so specs must be written against the staging contract but validated locally where feasible (dev server / mock), with the staging-green run founder-gated.
Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P07.

## 2. Objective & scope

A Playwright E2E suite (Fast-3G + 360px project) covering the critical paths: `shop-checkout-momo` (browse→search→PDP→cart→checkout→Lenco-sandbox-pay→confirmation→WhatsApp-mock assertion), `shop-cod`, `vendor-sell` (approved-vendor fixture→list→receive→ship), `event-ticket` (buy→wallet→scanner-verify→duplicate-rejected), `auth-otp`; deterministic seed/reset fixtures; a CI job (`e2e.yml`, staging + nightly/pre-release) with trace/video artifact upload; runtime target <15min.
**Non-goals:** no app code change, no new business route, no editing `ci.yml`/`perf.yml` (create a NEW `e2e.yml`), no real Lenco/WhatsApp creds committed.

## 3. Files (create/modify ONLY these)

- **Create:** `e2e/playwright.config.ts` (Fast-3G + 360px project; `use.baseURL` from `E2E_BASE_URL` env; `executablePath: '/opt/pw-browsers/chromium'` if the pinned version needs it — do NOT trigger a browser download) · `e2e/specs/{shop-checkout-momo,shop-cod,vendor-sell,event-ticket,auth-otp}.spec.ts` · `e2e/fixtures/` (seed + reset hooks, WhatsApp-mock adapter flag, Lenco-sandbox-ref helpers — all env-driven, no committed creds) · `.github/workflows/e2e.yml` (staging job, `schedule` nightly + a pre-release trigger; upload trace/video on failure) · `e2e/README.md` (how to run locally vs staging; which env vars gate the Lenco-sandbox + WhatsApp-mock paths) · optional `e2e/package.json` (+`@playwright/test` pinned)
  **Guardrail: nothing else. Do NOT touch app source, db.ts, migrations, `ci.yml`, `perf.yml`, other pebbles' files.**

## 4. Implementation spec

- **`playwright.config.ts`:** a Fast-3G/360px project (throttle + viewport), `baseURL` from `E2E_BASE_URL`, retries on CI, trace `on-first-retry`, video `retain-on-failure`, reporter with artifact output. Use the pre-installed Chromium (no download).
- **Specs:** write against the staging contract. Guard the founder-gated legs behind env flags — e.g. the `shop-checkout-momo` Lenco-sandbox pay step runs only when `LENCO_SANDBOX=1` + creds are present, else the spec asserts up to the pay-initiation boundary and `test.skip()`s the live-pay leg with a clear annotation. WhatsApp assertions use the mock-adapter flag. Deterministic seed reset per run (idempotent).
- **`fixtures/`:** seed hooks (approved-vendor, a buyable listing, an event with tickets), reset-between-runs idempotency, env-driven creds (never committed). WhatsApp mock adapter toggle.
- **`e2e.yml`:** runs against `E2E_BASE_URL` (staging secret), nightly `schedule` + a manual/pre-release `workflow_dispatch`; uploads trace/video artifacts on failure; NOT a required per-PR gate (staging-dependent). Keep any Supabase-CLI pin consistent with the repo (`2.109.1`) if used.
- **Local smoke:** validate the suite loads + at least the non-payment flows run against a local dev server (or `--list` + a config typecheck if a full local stack isn't feasible here). Document exactly what you validated vs. deferred.

## 5–9. Security etc.

No committed Lenco/WhatsApp creds (env/secrets only); Lenco-sandbox pay leg gated behind an env flag (never hammers a real endpoint from CI-per-PR); deterministic seed reset (no cross-run bleed); trace/video artifacts scrub or avoid real PII (use seed fixtures); the staging-green AC is founder/staging-gated (not faked).

## 10. Tests (RUN before reporting)

`pnpm exec playwright test --list` (suite discovers all specs); typecheck the config + specs; run the non-payment flows against a local dev server if feasible (paste result); `python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e.yml')); print('yaml ok')"`. Clearly state which specs ran locally vs. are staging/founder-gated.

## 11. Acceptance criteria / DoD

- [ ] All 5 critical-path specs written (Fast-3G/360px project); deterministic seed reset; trace/video artifact upload; `e2e.yml` nightly + pre-release; Lenco-sandbox + WhatsApp-mock legs env-gated.
- [ ] **Staging-green + Lenco-sandbox-pay AC clearly marked founder/staging-gated (F9b);** suite discovers + typechecks; e2e.yml valid; no committed creds.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P07 — E2E suite (Playwright)
**STATUS/FILES/DEVIATIONS** (the 5 specs + what each asserts; how the Lenco-sandbox/WhatsApp-mock legs are env-gated; seed-reset idempotency; what ran locally vs deferred) **/TESTS** (paste `playwright test --list` + any local run + e2e.yml yaml-ok) **/EXCERPTS** the checkout-momo spec's env-gated pay leg + the seed-reset fixture — nothing else **/QUESTIONS** (state that staging-green is founder-gated on staging deploy + F9b Lenco sandbox creds)
