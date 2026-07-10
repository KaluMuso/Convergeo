# Performance budgets (CI)

Wave 10 (`M16-P01`) enforces Vergeo5 performance budgets on every pull request via [`.github/workflows/perf.yml`](../../.github/workflows/perf.yml). Thresholds are **config-file-tunable** in [`lighthouserc.json`](../../lighthouserc.json) (`vergeo.bundle` and `ci.assert`).

## Budgets

| Metric                        | Threshold                                          | Scope                                        |
| ----------------------------- | -------------------------------------------------- | -------------------------------------------- |
| First-load JS                 | **≤ 150 KB gz** per route (default)                | `apps/customer` App Router pages             |
| LCP                           | **≤ 2.5 s**                                        | Home, PLP, PDP, search, checkout (`/en/...`) |
| Lighthouse mobile Performance | **≥ 90**                                           | Same five URLs                               |
| Lighthouse SEO                | **≥ 95**                                           | Same five URLs                               |
| Lighthouse Accessibility      | **≥ 95**                                           | Same five URLs                               |
| Images                        | No raw `<img>`; no unoptimized raster in `public/` | `apps/customer/app`                          |

### Lighthouse profile

- **Fast-3G / 360×740** mobile emulation (`lighthouserc.json` → `vergeo.lighthouse.profile`)
- RTT **150 ms**, downlink **1.6 Mbps**, **4×** CPU slowdown
- Runs against a **local production build** (`pnpm --filter customer build && start` on port 3000) — no staging URL required

### Bundle measurement

`scripts/ci/bundle-guard.mjs` reads `apps/customer/.next/app-build-manifest.json`, sums **gzip-compressed** sizes of all `.js` chunks listed for each `*/page` route, and compares to:

1. **Absolute ceiling** — `vergeo.bundle.defaultMaxKbGz` (150) or a per-route `maxKbGz` override
2. **Regression vs base** — on PRs, rebuilds the base commit and fails if any route grows more than **0.5 KB gz** vs base (reports **route name + delta**)

Per-route overrides **require** a `justification` string in config. Routes above 150 KB gz at M16-P01 merge carry baseline ceilings documented in `lighthouserc.json` with a target to return to 150 KB gz.

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

| Route          | URL                                      |
| -------------- | ---------------------------------------- |
| Home           | `http://localhost:3000/en`               |
| PLP            | `http://localhost:3000/en/c/electronics` |
| PDP            | `http://localhost:3000/en/p/itel-a70`    |
| Search         | `http://localhost:3000/en/search`        |
| Checkout entry | `http://localhost:3000/en/checkout`      |

## Related

- Convention #7 in [`CLAUDE.md`](../../CLAUDE.md)
- Pebble spec: [`docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md`](../plan/02-pebbles/M16-perf-pwa-launch-qa.md) §M16-P01
- PWA / serwist budgets: **M16-P02** (separate pebble)
