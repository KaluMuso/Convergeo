> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (**batch 2** — dispatched AFTER M16-P02 PWA merges, since you both wrap the customer `next.config.ts`). **Touch ONLY your files below.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (`git worktree add /tmp/base origin/master`). **⚠ DEFERRED-AC:** "thrown error appears in live Sentry / uptime alert fires" needs a real Sentry DSN + UptimeRobot this build env lacks — build the code/config/docs + scrubber unit tests, and mark the live-capture AC founder-gated. **Run `pnpm build/typecheck/lint` (all 3 apps) + `uv run pytest` on your new tests before reporting.**

# M16-P06 — Observability

## 1. Context

**Grounded against as-built `master`:**

- **M16-P02 (PWA) has merged and now owns/edits `apps/customer/next.config.ts`** (serwist + `withNextIntl` + `headers()`). **Compose `withSentryConfig` AROUND the existing customer config — preserve serwist + next-intl + headers.** vendor/admin `next.config.ts` are unedited this wave (yours to wrap for Sentry).
- **No Sentry yet** (`services/api/app/core/sentry.py` absent; no `sentry.client.config.ts`). **`app/core/sentry.py` is the ONLY file you add under `app/core/` this wave.**
- CSP (M15-P03) is nonce-based per app — **Sentry's ingest domain must be allowed in `connect-src`**; but `next.config.ts` CSP is owned by M15-P03/M16-P02 — add the Sentry `connect-src` allowance MINIMALLY within the next.config you're already editing for Sentry wiring, noting it (do NOT restructure the CSP).
  Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P06.

## 2. Objective & scope

Sentry across API + 3 apps (PII-scrubbed: phone/address masked; release = git sha; source maps on deploy), UptimeRobot monitor setup doc (API health, 3 origins, webhook — setup transcript), structured-log + error-budget doc (99.5% API availability, alert thresholds → founder WhatsApp via n8n), and the alert n8n workflow.
**Non-goals:** no app business logic change, no new route, no migration, no live DSN committed (env only). Live capture/alert-firing is founder-gated.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/core/sentry.py` (init + PII scrubber `before_send`) · `apps/customer/sentry.client.config.ts` + `apps/vendor/sentry.client.config.ts` + `apps/admin/sentry.client.config.ts` · `infra/uptimerobot.md` (monitors + setup transcript) · `docs/ops/observability.md` (structured-log conventions + error-budget numbers + alert thresholds) · `infra/n8n/uptime-alert.json` (n8n workflow: downtime → founder WhatsApp) · `services/api/tests/test_sentry_scrubber.py`
- **Modify:** `services/api/app/core/settings.py` (init Sentry from env — DSN/env/release; no-op when DSN unset) · `apps/{customer,vendor,admin}/next.config.ts` (wrap `withSentryConfig`, preserve existing wrappers/headers; add Sentry `connect-src` to CSP minimally) · `apps/{customer,vendor,admin}/package.json` (+`@sentry/nextjs`) + `services/api/pyproject.toml` (+`sentry-sdk`) + `pnpm-lock.yaml`/`uv.lock` (scoped to the new deps)
  **Guardrail: nothing else. Do NOT touch other `app/core/*` files, db.ts, migrations, `ci.yml`/`perf.yml`/`e2e.yml`, PWA `sw.ts`/`manifest.ts`, other pebbles' files.**

## 4. Implementation spec

- **`sentry.py`:** `init_sentry(settings)` — DSN/environment/release(git sha) from env; **`before_send` scrubber masks PII** (phone numbers, addresses, emails, tokens) in event + breadcrumbs; sample rates from config; **no-op when `SENTRY_DSN` unset** (dev/CI safe). Call from `settings.py`/app startup.
- **`sentry.client.config.ts` ×3:** client init with the same PII scrubbing; release tagging; tunnel/`connect-src` respected; admin can be stricter.
- **next.config wiring:** `withSentryConfig(existingConfig)` preserving serwist(customer)/next-intl/headers; source-map upload on deploy (auth-token from env, gated so a missing token doesn't break the build); add the Sentry ingest host to `connect-src` (minimal).
- **`observability.md`:** structured-log field conventions; **error budget = 99.5% API availability** with concrete alert thresholds; runbook link to M15-P09.
- **`uptimerobot.md` + `uptime-alert.json`:** monitors (API `/health`, 3 origins, webhook endpoint); the n8n workflow payload that pages the founder on WhatsApp when a monitor trips (matches the outbox/WhatsApp contract).

## 5–9. Security etc.

**PII scrubbing is the core invariant** — assert in `test_sentry_scrubber.py` that phone/address/email/token are masked in both event body and breadcrumbs; DSN/auth-token from env only (never committed); Sentry no-ops without a DSN (CI-safe); source-map upload gated on an env token; CSP `connect-src` widened minimally (not opened up). Live capture + alert-firing = founder-gated (needs real DSN/UptimeRobot).

## 10. Tests (RUN before reporting)

`uv run pytest services/api/tests/test_sentry_scrubber.py -q` (phone/address/email/token masked in event + breadcrumb; no-op when DSN unset); `uv run ruff check . && uv run mypy app tests` (API); **`pnpm --filter customer build`, `--filter vendor build`, `--filter admin build`** (Sentry wrap doesn't break any build; customer still has serwist+headers); `pnpm typecheck/lint`. Validate `uptime-alert.json` is valid JSON.

## 11. Acceptance criteria / DoD

- [ ] Sentry init on all 4 targets with PII scrubber (unit-proven); release=git sha; source maps gated on env; error-budget doc has numbers; uptime monitors + n8n WhatsApp alert defined.
- [ ] **Live-capture + alert-fire AC marked founder-gated (needs DSN/UptimeRobot);** all 3 app builds green (serwist+headers preserved on customer); API scrubber tests + ruff + mypy green; no committed DSN.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P06 — Observability
**STATUS/FILES/DEVIATIONS** (the scrubber masking set; how you wrapped Sentry around M16-P02's serwist config without breaking headers/CSP; the error-budget numbers; what's founder-gated) **/TESTS** (paste scrubber test + the three app builds + json-valid) **/EXCERPTS** the `before_send` PII scrubber + the customer next.config composition (serwist+sentry+headers) — nothing else **/QUESTIONS** (state live-capture/alert-fire is founder-gated on DSN + UptimeRobot)
