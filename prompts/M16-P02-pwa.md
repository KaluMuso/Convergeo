> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 18 (parallel batch 1). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-18 editor of `apps/customer/next.config.ts`** (M16-P06 Sentry wraps it in batch 2, AFTER you merge). **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master` to compare). **Run `pnpm --filter customer build/typecheck/lint/test` before reporting.**

# M16-P02 — PWA (serwist)

## 1. Context

**Grounded against as-built `master`:**

- **`apps/customer/next.config.ts` exists** using `export default withNextIntl(nextConfig)` and an `async headers()` block (from M15-P03 — CSP/HSTS). **Compose serwist AROUND the existing config — `withNextIntl(withSerwist(nextConfig))` (or the serwist-recommended order) — and PRESERVE the `headers()`/CSP block untouched.** The CSP already allows `worker-src 'self' blob:` and `manifest-src 'self'` (M15-P03).
- **A partial SW fragment already exists: `apps/customer/sw-wallet.ts`** (M10 wallet offline cache). **Integrate it into ONE unified `apps/customer/sw.ts`** — do NOT leave two competing service workers. If the wallet route caching lives in `sw-wallet.ts`, fold its rules into the unified serwist config (and delete/replace `sw-wallet.ts` if it becomes dead — note it in the report).
- Serwist is the LOCKED PWA lib (CLAUDE.md D22).
  Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P02.

## 2. Objective & scope

Installable PWA: serwist SW (precache app shell; runtime caching — catalog pages stale-while-revalidate, images cache-first capped, API network-first, **checkout ALWAYS network — no stale-price sales**), web manifest, dismissible frequency-capped install prompt, branded offline fallback, and the M10 wallet/scanner SW fragment folded into one config.
**Non-goals:** no Sentry wiring (M16-P06 batch 2), no new business route, no CSP change (M15-P03 already allows SW/manifest), no bundle-budget regression beyond a documented ceiling bump.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/sw.ts` (unified serwist SW) · `apps/customer/app/manifest.ts` (Next metadata manifest) · `apps/customer/app/[locale]/(shop)/_components/install-prompt.tsx` (dismissible, frequency-capped via localStorage) · `apps/customer/app/[locale]/offline/page.tsx` (branded "you're offline", i18n)
- **Modify:** `apps/customer/next.config.ts` (compose `withSerwist` — PRESERVE `headers()`/CSP + `withNextIntl`) · `apps/customer/sw-wallet.ts` (fold into `sw.ts`; delete if fully absorbed — note it) · `apps/customer/package.json` (+`@serwist/next`/`serwist` dep if not present — mechanically required) · `pnpm-lock.yaml` (scoped to the serwist dep) · i18n: append offline/install keys to an EXISTING customer namespace (prefer `common`; do NOT create a namespace or touch `marketing.json`/`legal`)
  **Guardrail: nothing else. Do NOT touch `app/[locale]/layout.tsx`, other apps, db.ts, migrations, `perf.yml` (M16-P03 owns it this wave), other next.config files.**

## 4. Implementation spec

- **`sw.ts` (serwist):** precache the build manifest (app shell); runtime caches — **catalog/PDP GET = StaleWhileRevalidate**, **images = CacheFirst with an entry cap + expiration**, **API GET = NetworkFirst**, **checkout/cart/payment/auth = NetworkOnly (never cached — no stale prices, honest offline messaging)**. Fold the `sw-wallet.ts` wallet-offline rules in. `skipWaiting`/`clientsClaim` behind a safe update-prompt flow (no silent skip-waiting that could serve a half-updated app).
- **`manifest.ts`:** name/short_name, theme/background per `packages/ui` tokens, icons (reuse existing public icons; do NOT add binary assets you can't verify — reference existing ones), `display: standalone`, `start_url` locale-aware.
- **`install-prompt.tsx`:** capture `beforeinstallprompt`, show a dismissible CTA, frequency-cap re-prompts (localStorage timestamp), 360px-first, i18n keys.
- **`offline/page.tsx`:** branded offline fallback with a "you're offline — previously viewed pages still work" message + a retry/home link; i18n.
- **Update lifecycle:** a safe SW-update prompt (new version available → user-triggered reload), no forced skip-waiting.

## 5–9. Security etc.

Checkout/cart/payment/auth are NetworkOnly (a hard invariant — assert in the SW-rules test that these routes are NOT cached); no stale prices ever served; install prompt frequency-capped (no nag); offline messaging honest (no fake "success" offline); no secrets in SW; CSP already permits `worker-src`/`manifest-src` (do not change it).

## 10. Tests (RUN before reporting)

SW caching-rules unit tests: catalog=SWR, images=CacheFirst-capped, **checkout/cart/payment=NetworkOnly (assert not cached)**, wallet-fragment rules present (coexistence). Offline navigation renders a previously-cached PDP + the offline fallback. Update lifecycle (new SW → prompt, not silent). `pnpm --filter customer build` (note the PWA/SW bundle impact + any per-route gz delta; if a route crosses its ceiling, FLAG for the converger to bump `lighthouserc.json` — you do NOT own it), `pnpm --filter customer typecheck/lint/test`.

## 11. Acceptance criteria / DoD

- [ ] Installable (manifest + SW registered); airplane-mode previously-viewed PDP renders + offline fallback; SW update flow safe (no silent skip-waiting); **checkout/cart/payment ALWAYS network (no stale-price sale)**; wallet fragment coexists in one SW.
- [ ] `headers()`/CSP preserved in next.config; customer build + tests green; bundle deltas reported (ceiling bumps flagged for converger).

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P02 — PWA
**STATUS/FILES/DEVIATIONS** (the serwist next.config composition preserving headers; how you folded `sw-wallet.ts`; the runtime-cache rule table; the update-prompt flow; per-route gz deltas) **/TESTS** (paste SW-rules incl. the checkout=NetworkOnly assertion + offline-nav + update-lifecycle + build bundle line) **/EXCERPTS** the runtime-cache rule table (esp. the NetworkOnly checkout rule) + the next.config composition — nothing else **/QUESTIONS** (flag any bundle ceiling that needs a converger bump)
