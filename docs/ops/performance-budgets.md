# Performance budgets (CI)

Wave 10 (`M16-P01`) enforces Vergeo5 performance budgets on every pull request via [`.github/workflows/perf.yml`](../../.github/workflows/perf.yml). Thresholds are **config-file-tunable** in [`lighthouserc.json`](../../lighthouserc.json) (`vergeo.bundle` and `ci.assert`).

> **Blocking vs advisory.** The **bundle guard (≤150 KB gz per route) and image lint are hard per-PR gates** — a violation fails the PR. **Lighthouse is also blocking** (`perf.yml` → step "Lighthouse CI (blocking — see lighthouserc.json)"; the step is **not** `continue-on-error`). It asserts against the **CI-enforced floors** in `lighthouserc.json` (`ci.assert.assertMatrix` / `vergeo.lighthouse.ciEnforced`), which are deliberately looser than the production targets below — LHCI on a cold local `next start` (cloudinary `demo` images, no CDN, 4× CPU throttle) under-scores vs production, so the floors gate on regressions without false-failing on the local-throttle penalty. `scripts/ci/validate-lighthouserc.mjs` fails CI if any assertion is downgraded below `error` (the sole waiver: checkout-route SEO, which is `noindex` by design). The **targets** table below is the production goal; the **floors** table is what actually fails a PR.

## Budgets

**Production targets** — the goal, reported per-PR:

| Metric                        | Target                                             | Scope                                        |
| ----------------------------- | -------------------------------------------------- | -------------------------------------------- |
| First-load JS                 | **≤ 150 KB gz** per route (default)                | `apps/customer` App Router pages             |
| LCP                           | **≤ 2.5 s**                                        | Home, PLP, PDP, search, checkout (`/en/...`) |
| Lighthouse mobile Performance | **≥ 90**                                           | Same five URLs                               |
| Lighthouse SEO                | **≥ 95**                                           | Same five URLs                               |
| Lighthouse Accessibility      | **≥ 95**                                           | Same five URLs                               |
| Images                        | No raw `<img>`; no unoptimized raster in `public/` | `apps/customer/app`                          |

**CI-enforced floors** — `lighthouserc.json` → `ci.assert.assertMatrix` (`vergeo.lighthouse.ciEnforced`); a PR fails below these. All `error`-level unless noted:

| Assertion                        | Floor                                              | Notes                                                        |
| -------------------------------- | -------------------------------------------------- | ------------------------------------------------------------ |
| First-load JS                    | **≤ 150 KB gz**                                    | Hard `bundle-guard.mjs` gate on every `*/page` route         |
| LCP (`largest-contentful-paint`) | **≤ 6500 ms**                                      | Local-throttle floor, **not** the 2.5 s production target    |
| `categories:performance`         | **≥ 0.50**                                         | Local under-scoring vs prod                                  |
| `categories:accessibility`       | **≥ 0.90**                                         |                                                              |
| `categories:best-practices`      | **≥ 0.85**                                         |                                                              |
| `categories:seo`                 | **≥ 0.75** (catalog/PDP/search), **≥ 0.40** (home) | Checkout SEO waived to `warn` — route is `noindex` by design |

### Lighthouse profile

- **Fast-3G / 360×740** mobile emulation (`lighthouserc.json` → `vergeo.lighthouse.profile`)
- RTT **150 ms**, downlink **1.6 Mbps**, **4×** CPU slowdown
- **3 runs per URL** with **median** aggregation on `categories:performance` and `largest-contentful-paint` (LHCI default `optimistic` on single runs was flaking at the perf≥0.50 floor; thresholds unchanged)
- Runs against a **local production build** (`pnpm --filter customer build && start` on port 3000) with the **FastAPI dev API** on `:8000` backed by a seeded local Supabase stack (`supabase db start && db reset`) so PLP/PDP routes resolve — no Vercel preview required.

### Bundle measurement

`scripts/ci/bundle-guard.mjs` reads `apps/customer/.next/app-build-manifest.json`, sums **gzip-compressed** sizes of all `.js` chunks listed for each `*/page` route, and compares to:

1. **Absolute ceiling** — `vergeo.bundle.defaultMaxKbGz` (150) or a per-route `maxKbGz` override
2. **Regression vs base** — on PRs, rebuilds the base commit and fails if any **audited shop route** (`vergeo.bundle.auditRoutes`) grows more than **`REGRESSION_TOLERANCE_KB` (2.0 KB gz)** vs base (reports **route name + delta**). The tolerance was raised from 0.5 → 2.0 KB to absorb the one-time serwist/PWA shared-runtime baseline shift (M16-P02); it still catches real >2 KB regressions. Absolute ceilings still apply to every `*/page` route.

Per-route overrides take a `justification` string in config, but **`vergeo.bundle.routes` is now `{}`** — the 2026-07 auth code-split (lazy `getBrowserClient`) dropped every customer route under the 150 KB target, so the previous baseline ceilings (up to 197 KB) were removed and the default 150 now genuinely gates every route (see `lighthouserc.json` → `reductionNote`).

## Changing a budget

1. Edit [`lighthouserc.json`](../../lighthouserc.json):
   - **Bundle:** `vergeo.bundle.defaultMaxKbGz` or `vergeo.bundle.routes["/<route>/page"].maxKbGz`
   - **Lighthouse:** `ci.assert.assertions` (e.g. `largest-contentful-paint`, `categories:performance`)
2. Add or update the matching **`justification`** field (required for bundle overrides; document Lighthouse changes in `vergeo.lighthouse.justification` or the PR description).
3. Run locally:
   ```bash
   pnpm --filter customer build
   node scripts/ci/bundle-guard.mjs
   node scripts/ci/image-lint.mjs
   pnpm --filter customer start &
   pnpm exec lhci autorun --config=lighthouserc.json
   ```
4. Open a PR — `perf.yml` must be green.

**Do not** relax budgets without a written justification (perf regression, new feature scope, or measured false positive).

## Scripts

| Script                                         | Purpose                                           |
| ---------------------------------------------- | ------------------------------------------------- |
| `node scripts/ci/bundle-guard.mjs`             | Per-route JS budget + optional `--baseline` delta |
| `node scripts/ci/bundle-guard.mjs --self-test` | Pass/fail fixture cases                           |
| `node scripts/ci/image-lint.mjs`               | Raw `<img>` + `public/` raster scan               |
| `node scripts/ci/image-lint.mjs --self-test`   | Pass/fail fixture cases                           |
| `pnpm exec lhci autorun`                       | Lighthouse CI (uses `lighthouserc.json`)          |

## Audited shop URLs (Lighthouse)

| Route          | URL                                        |
| -------------- | ------------------------------------------ |
| Home           | `http://localhost:3000/en`                 |
| PLP            | `http://localhost:3000/en/c/electronics`   |
| PDP            | `http://localhost:3000/en/p/smartphone-x1` |
| Search         | `http://localhost:3000/en/search`          |
| Checkout entry | `http://localhost:3000/en/checkout`        |

## Related

- Convention #7 in [`CLAUDE.md`](../../CLAUDE.md)
- Pebble spec: [`docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md`](../plan/02-pebbles/M16-perf-pwa-launch-qa.md) §M16-P01
- PWA / serwist budgets: **M16-P02** (separate pebble)
