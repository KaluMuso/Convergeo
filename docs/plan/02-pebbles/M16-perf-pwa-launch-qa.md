# M16 — Performance, PWA, Content, Analytics & Launch QA — Pebbles

9 pebbles. P01 (budgets) lands as early as its wave allows so budgets police subsequent waves per-PR; the rest close out launch. This mountain owns the go/no-go.

---

### M16-P01 — Performance budgets in CI `M`
**Deps:** M01-P06, M05 routes exist · **Files:** `.github/workflows/perf.yml` (Lighthouse CI: Fast-3G/360px profile vs staging preview — LCP ≤2.5s, Perf ≥90, SEO ≥95, A11y ≥95 on home/PLP/PDP/search/checkout-entry), `lighthouserc.json`, `scripts/ci/bundle-guard.mjs` (**per-route JS ≤150KB gz customer app** — fails PR with diff vs base), `scripts/ci/image-lint.mjs` (no raw `<img>`, no unoptimized public images), budget doc `docs/ops/performance-budgets.md`
Budgets enforced per-PR from merge onward (M16 risk mitigation: not retrofitted).
**AC:** violating PR fails with named route + delta; all current routes green at merge; thresholds config-file-tunable with justification note required.
**Tests:** guard scripts against fixture bundles (pass/fail cases), LHCI config smoke.

### M16-P02 — PWA `M`
**Deps:** M05 complete · **Files:** `apps/customer/sw.ts` (serwist: precache shell, runtime cache — catalog pages stale-while-revalidate, images cache-first capped, API network-first), `apps/customer/app/manifest.ts`, install prompt `(shop)/_components/install-prompt.tsx` (dismissible, frequency-capped), offline fallback `app/[locale]/offline/page.tsx`, integrates wallet/scanner SW fragments (M10) into one config
Offline tolerance: browsed pages readable offline with "you're offline" banner; cart/checkout require connection (honest messaging).
**AC:** installable (Lighthouse PWA pass); airplane-mode: previously-viewed PDP renders; SW update flow safe (skip-waiting prompt); no stale-price sales (checkout always network).
**Tests:** SW caching rules unit tests, offline navigation, update lifecycle, wallet-fragment coexistence.

### M16-P03 — i18n completeness & formatting audit `S`
**Deps:** all UI merged · **Files:** `scripts/ci/i18n-lint.mjs` (**hardcoded-string sweep across apps — builds on M02-P02 eslint rule, adds template/aria/meta coverage**; missing-key detection: used-vs-defined diff; pseudo-locale build `en-XA` bracketed), `packages/i18n/pseudo.ts`, CI wiring in `perf.yml` (same workflow file as P01 — **same mountain, sequenced within wave or same PR batch**), audit fixes doc `docs/plan/i18n-audit.md`
ZMW/date audit: grep for raw `toLocaleString`/`Intl.` outside packages/i18n + raw "K" prefixing (formatK bypass).
**AC:** zero hardcoded strings repo-wide (CI green); pseudo-locale renders every screen without raw EN; zero formatK bypasses.
**Tests:** lint fixtures, missing-key detection, pseudo-locale smoke.

### M16-P04 — Content pages `M`
**Deps:** M02, M15-P06 · **Files:** `apps/customer/app/[locale]/(marketing)/about/page.tsx`, `contact/page.tsx` (WhatsApp-first contact + form → outbox email), `help/page.tsx` + `help/[slug]/page.tsx` (FAQ seed: ~20 articles from decisions — escrow explainer, COD rules, returns lanes, tickets, vendor how-to), `apps/customer/app/not-found.tsx`, `error.tsx` (branded 404/500, i18n), `packages/i18n/messages/en/marketing.json`
Help center = markdown/MDX content collection (founder-editable via repo); escrow trust explainer is the flagship article.
**AC:** FAQ searchable (client-side index); 404/500 branded with recovery links; contact form delivers via outbox.
**Tests:** MDX render, FAQ search, error page render, form validation.

### M16-P05 — Analytics `M`
**Deps:** M07-P08 · **Files:** `packages/analytics/` (GA4 wrapper: consent-aware, data-frugal beacon batching), server event log extension `services/api/app/services/analytics/events.py` (search terms, zero-results, funnel steps, AI usage — unifies M06-P06 + M07-P08 streams into one queryable schema), migration `00xx_analytics_unify.sql`, GA4 wiring in customer app layout (`app/[locale]/layout.tsx` — **modify; coordinate wave**), `docs/ops/analytics-events.md` (event dictionary)
Server-side log is source of truth (ad-blocker-proof); GA4 = convenience mirror; consent banner minimal (DPA-aligned).
**AC:** funnel queryable end-to-end (search→PDP→cart→pay) from server log; GA4 receives mirrored events; consent refusal disables GA4 only (server log anonymized regardless).
**Tests:** event schema conformance, consent gating, dictionary-vs-code drift check.

### M16-P06 — Observability `M`
**Deps:** M01-P07 · **Files:** `services/api/app/core/sentry.py` (+init in settings — **only file in `app/core/` this wave**), Sentry client config all 3 apps (`sentry.client.config.ts` × 3 + next.config wiring), `infra/uptimerobot.md` (monitors: API health, 3 origins, webhook endpoint — setup transcript), structured log conventions `docs/ops/observability.md` (+ error-budget: 99.5% API availability target, alert thresholds → founder WhatsApp via n8n `infra/n8n/uptime-alert.json`)
PII scrubbing in Sentry (phone numbers, addresses masked); release tagging from git sha; source maps uploaded on deploy.
**AC:** thrown test error appears in Sentry with release + scrubbed PII (all 4 targets); uptime alert fires on induced downtime (staging drill); error-budget doc has numbers not vibes.
**Tests:** scrubber unit tests, init smoke per app, alert workflow payload.

### M16-P07 — E2E suite (Playwright) `L`
**Deps:** everything on staging · **Files:** `e2e/` (playwright.config.ts — Fast-3G + 360px project; specs: `shop-checkout-momo.spec.ts` (browse→search→PDP→cart→checkout→**Lenco sandbox pay**→confirmation→WhatsApp-mock assertion), `shop-cod.spec.ts`, `vendor-sell.spec.ts` (onboard-approved fixture→list→receive order→ship), `event-ticket.spec.ts` (buy→wallet→scanner verify→duplicate rejected), `auth-otp.spec.ts`), fixtures/seed hooks `e2e/fixtures/`, CI job `.github/workflows/e2e.yml` (staging, nightly + pre-release)
Sandbox-safe: Lenco sandbox refs, WhatsApp mock adapter flag, deterministic seed reset per run.
**AC:** M16 success criterion: suite green on staging against Lenco sandbox; failure artifacts (trace/video) uploaded; runtime <15min.
**Tests:** the suite itself + seed-reset idempotency.

### M16-P08 — Load test `M`
**Deps:** P07 · **Files:** `load/k6/checkout-load.js` (**100 concurrent checkout**: cart→reserve→order→payment-initiate against staging w/ Lenco stub), `load/k6/browse-load.js` (search+PLP read mix), `load/README.md` (run procedure, pass thresholds, tuning log), findings doc `docs/ops/load-test-results.md`
Stubs Lenco (no sandbox hammering); focuses on our races: reservations, order creation, ledger postings, invoice counters under load.
**AC:** M16 success criterion: p95 <500ms at 100cc checkout; **zero oversells/ledger imbalances/invoice gaps under load** (post-run invariant queries); findings + fixes logged.
**Tests:** k6 thresholds encoded, post-run invariant check script.

### M16-P09 — Beta tooling & go/no-go `M`
**Deps:** P01–P08 · **Files:** `services/api/app/routers/beta.py` + migration `00xx_beta_invites.sql` (invite codes, capacity, gate middleware flag-controlled), invite gate UI `apps/customer/app/[locale]/(marketing)/beta/page.tsx`, feedback widget `packages/ui/src/feedback-widget.tsx` (floating, screenshots optional → admin/outbox), `docs/plan/launch-checklist.md` (**go/no-go: every M-success-criterion, founder gates F1–F9 status, budgets green, E2E green, restore drill done, counsel F4, sign-off lines**)
Gate = feature flag: beta (invite-only) → public (flag off, no deploy); feedback lands where founder looks (admin + digest).
**AC:** M16 success criterion: cohort invitable/gated; flag-flip opens public; checklist enumerates every launch gate with evidence links; feedback round-trips.
**Tests:** gate middleware (valid/invalid/exhausted codes), flag behavior, widget submission.
