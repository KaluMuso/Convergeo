# Stack version and security audit, and upgrade plan

Date: 2026-11-15 · Branch `chore/stack-security-audit` · Scope: audit only, no dependency changes were needed.

Sources: lockfiles in this repo (`pnpm-lock.yaml`, `services/api/uv.lock`), `npm view` / `pip index` on 2026-11-15, nextjs.org/blog (November 2026 Security Release, Next.js 16.4), tailwindcss.com/blog/tailwindcss-v4-3, fastapi.tiangolo.com/release-notes, and Starlette advisories (GitHub/OSV/GitLab advisory mirrors). The github.com advisory pages themselves could not be fetched (fetch permission was not granted), so Starlette and Pydantic data comes from mirrors (osv.dev, advisories.gitlab.com, corgea, vuln.today).

## 1. Installed versions (from lockfiles)

All three apps resolve to identical versions (single workspace lock; `node_modules` was not installed in the audit worktree, so these are lockfile-resolved, not `require()`d).

| Package | customer | vendor | admin | Latest on npm (2026-11-15) |
|---|---|---|---|---|
| next | 15.5.29 (pnpm-patched, `patches/next.patch`) | 15.5.29 | 15.5.29 | 15.5.29 on the 15.x line; 16.4.5 on 16.x |
| react / react-dom | 19.3.1 | 19.3.1 | 19.3.1 | 19.3.1 |
| tailwindcss | 4.3.3 | 4.3.3 | 4.3.3 | 4.3.5 |
| @tailwindcss/postcss | 4.3.3 | 4.3.3 | 4.3.3 | follows tailwindcss |
| next-intl | 4.14.9 | 4.14.9 | 4.14.9 | 4.15.1 |
| @serwist/next | 9.5.12 | not used | not used | 9.5.13 |
| @supabase/supabase-js | 2.116.0 (via `packages/auth`) | 2.116.0 | 2.116.0 | 2.119.0 |

Backend (`services/api/uv.lock`):

| Package | Locked | Latest on PyPI |
|---|---|---|
| fastapi | 0.139.0 | 0.163.0 |
| pydantic | 2.13.4 (pydantic-core 2.46.4) | 2.14.3 |
| starlette | 1.3.1 | 1.10.0 |
| uvicorn | 0.50.2 | 0.54.0 |
| httpx | 0.28.1 | n/a (not checked) |

## 2. Founder-note claims

| Claim | Verdict |
|---|---|
| Next.js 16.4 exists | TRUE. 16.4 shipped 2026-10-06 (React 19.3, Cache Components recommended). 16.4.5 is the current Active LTS patch. |
| Tailwind 4.3.2 | PARTLY TRUE / outdated. 4.3 is real (scrollbar utilities, `@container-size`, `zoom-*`, `tab-*`). 4.3.2 is not the current patch: we are on 4.3.3 and npm latest is 4.3.5. |
| FastAPI 0.162.x | TRUE as a series (0.162.0 on 2026-10-23 to 0.162.7 on 2026-11-13), but already superseded: PyPI latest is 0.163.0. We are on 0.139.0, 23 minors behind. |
| "November 2026 Next.js security release" | TRUE. Published 2026-11-03: 7 advisories (below), fixed in 16.4.5 and 15.5.29. |

## 3. Security findings

### Next.js November 2026 release (fixed in 15.5.29 and 16.4.5)

We are on 15.5.29, so the fixes are already applied. No bump was made. Relevance to us:

- GHSA-mfr8-8qww-v76h (High), GHSA-vc7v-qv4w-wrv8, GHSA-rhh4-g77r-r9qj and the shared-shell poisoning issue only affect apps with Cache Components / `use cache` enabled. We do not use them on 15.x. This matters for the Next 16 plan: do not enable Cache Components casually.
- GHSA-pc58-hwjq-p385 (stale compressed response framing, self-hosted behind an HTTP/1.1 proxy): relevant to admin/vendor on OCI behind Caddy only if a route returns a fetched `Response` unchanged. Patched anyway.
- GHSA-f3mh-rxg3-f5g2 (`x-middleware-set-cookie` leaks via Edge routes): patched; avoid `NextResponse.cookies.set` in Edge route handlers regardless.
- GHSA-7qx7-33qx-rqx2 (SVG bypass in image optimization): patched.

Note: the article's example command comment says "16.5" for the 16.x install line; the actual patched 16.x version is 16.4.5.

### Starlette (locked 1.3.1)

The June 2026 batch is all fixed at or below 1.3.1: CVE-2026-48710 (Host header, fixed 1.0.1), CVE-2026-48817 (HTTPEndpoint method dispatch, fixed 1.1.0), CVE-2026-54283 (urlencoded form limits ignored, fixed 1.3.1), CVE-2026-54282 and CVE-2026-48818 (Windows UNC StaticFiles, not applicable on Linux). Nothing outstanding affects 1.3.1 that I could find. Starlette 1.10.0 exists but is not security-driven.

### Pydantic (2.13.4)

No advisory against `pydantic` itself turned up. The 2026 CVEs found were for `pydantic-ai`, which we do not use.

### FastAPI (0.139.0)

No security section in the 0.158 to 0.162 notes. Nothing forces an upgrade.

### pnpm audit --prod

2 moderate findings, both transitive build tooling: `glob` (AbortSignal cancellation bypass) and `minimatch` (globparts DoS). Not reachable at runtime in the deployed apps. Track via a future `pnpm.overrides` once the parent that pins them is identified (not done here to keep this change minimal).

### Result

No patch exists within our current majors that we lack, so no dependency, lockfile or code changes were made and the build/test suites were not re-run (nothing to verify).

## 4. Adopt now inside current majors

### Tailwind 4.3.x (we are on 4.3.3; bump to 4.3.5 is a safe patch)

- Container queries (`@container`, `@sm:`, `@container-size` with `cqb`/`cqh`): component-level responsiveness in `packages/ui` cards and product grids, so one component works in 360px list and wide grid contexts without page-level breakpoints.
- `has-*`, `user-invalid:` / `user-valid:`: form styling that only shows errors after interaction (checkout, KYC, vendor listing forms), no JS state.
- `scrollbar-thin`, `scrollbar-gutter-stable`: stop layout shift in vendor/admin tables and drawers.
- `tabular-nums` (and `font-features-["tnum"]`): align ZMW amounts in tables, invoices, ledgers; pair with `formatK()`.
- `motion-safe:` / `motion-reduce:`: guard animations for the A11y >= 95 budget.
- Logical properties (`mbs-*`, `inset-s-*`): useful groundwork for RTL-agnostic layouts; `start-*`/`end-*` are deprecated in 4.2+, so grep for them.
- `@tailwindcss/webpack` loader (4.2): possible build-speed win if we leave PostCSS; low priority.

Do via a design-token-respecting pebble: new utilities must use `packages/ui` tokens (convention 8).

### FastAPI (we are on 0.139.0; the newest features need a bump, which is a minor-version risk, not a security one)

- Parameter models (`Query()/Header()/Cookie()` as Pydantic models): replace long repeated list/filter query signatures on catalog and admin list endpoints.
- Router-level dependencies (`APIRouter(dependencies=[...])`): centralise authz and rate-limit dependencies so a new endpoint cannot forget them (convention 3). Already supported on our version.
- OpenTelemetry: add OTel instrumentation to match `docs/plan/analytics-observability-plan.md`, within the $50/mo ceiling (export to a free-tier backend or Sentry).
- SSE (`EventSourceResponse` / streaming): "Ask Vergeo" RAG token streaming and order/payment status push; saves polling bytes on 3G.
- Housekeeping: 0.162.6 drops Python 3.10 (we require 3.12, fine); 0.162.3 pulls Pydantic 2.14.3. Plan a bump to the latest 0.16x with the full pytest suite, ideally together with Starlette 1.x current and uvicorn 0.54.
- Optional patch bumps: next-intl 4.15.1, @serwist/next 9.5.13, supabase-js 2.119.0. Do these as one chore PR with typecheck, builds and vitest.

## 5. Next.js 16 upgrade plan (do NOT do now)

Target: 16.4.5 (Active LTS), React 19.3.1 (already on it). Next 15.5 stays on Maintenance LTS, so there is no urgency; schedule after launch stabilisation. Pause rule: never mix with a feature wave.

### Steps

1. Branch `chore/next-16`, one app at a time: vendor first (lowest SEO risk), then admin, then customer last.
2. Read the official 16 upgrade guide; run `npx next@canary upgrade --agent=latest` in a scratch branch to get the version-specific checklist and codemods, review its output rather than applying blindly.
3. Remove `patches/next.patch` and `patchedDependencies` entry (it patches the 15.5.29 font loader and will not apply); verify whether the font-format fix is upstream in 16.4.5, else re-create the patch.
4. Bump `next` to 16.4.5 in all three apps and `packages/auth|i18n|ui` peer ranges; `pnpm install --frozen-lockfile=false`.
5. Rename `middleware.ts` to `proxy.ts` in each app (Next 16 convention; Node runtime). Re-verify CSP headers, locale routing, admin allowlist and auth refresh logic; add a test per app.
6. Fix async request APIs (params, searchParams, cookies, headers are async), image config changes, and removed/renamed config flags per the guide.
7. Keep Cache Components OFF in the first pass (`cacheComponents: false`). Treat it as a separate project (below).
8. Typecheck, lint, vitest, build, then `pnpm e2e` on preview deployments; compare Lighthouse and the 150KB gz route budget against the 15.5 baseline.
9. Promote vendor/admin first on OCI; customer on Vercel via preview, then promote. Keep the previous deployment for instant rollback.

### Risks

- proxy.ts: auth, CSP and next-intl locale negotiation currently live in `middleware.ts`. next-intl's middleware helper must be wired through `proxy.ts`; confirm the supported next-intl release (4.15.x is current; test with 4.14.9 first to isolate).
- Cache Components: the November advisories were mostly in this feature. If adopted later, it conflicts with our per-user pages (carts, orders) unless carefully scoped with `use cache` and Suspense; Next 17 will make it the default, so plan it, but separately. Never pass binary args to `use cache` functions keyed by user.
- Serwist: `@serwist/next` wraps the webpack build. Next 16 defaults to Turbopack for build; Serwist's Next plugin is webpack-based, so either build with `--webpack` or move to the Serwist Turbopack integration (`@serwist/turbopack`) and re-test `apps/customer/sw.ts` and `sw.test.ts`, offline fallback and precache manifest. Highest-risk item for the customer app. Check Serwist release notes for 16.4 support before starting.
- next-intl: verify plugin (`createNextIntlPlugin`) with Turbopack and the request config. Run the i18n lint and message-key tests.
- Bundle budget: 16.4 reduces output (shared Turbopack runtime, export mangling), but Turbopack chunking differs from webpack, so re-measure every customer route against the 150KB gz limit; the CI budget script may parse webpack-specific manifests.
- Tailwind: `@tailwindcss/postcss` works in Next 16, but confirm with Turbopack's PostCSS worker handling.
- Windows/AVIF/image changes: re-check `images` config (SVG disabled, remote patterns) after the upgrade.
- Self-hosted behind Caddy (admin/vendor): re-test response compression and proxy behaviour (see GHSA-pc58-hwjq-p385).

### Exit criteria

Typecheck, lint, vitest, e2e green; Lighthouse mobile Perf >= 90, SEO >= 95, A11y >= 95; customer routes <= 150KB gz; PWA install and offline verified; rollback rehearsed.
