# Vergeo5 Release Certification Suite

Independent, repeatable release-certification architecture for promotion decisions.
This suite makes failures undeniable — it does not rely on another agent's claims.

## Test pyramid

```
                    ┌─────────────────────┐
                    │  L3 Browser E2E     │  Playwright @ e2e/specs/
                    │  (synthetic, mobile)│  Stops before real-money unless sandbox
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  L2 Integration     │  pytest API domains (manifest below)
                    │  cart/checkout/RFQ  │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────▼──────────────────────┐
        │  L1 Static                                     │
        │  lint · typecheck · unit · deps · i18n ·      │
        │  migration replay · RLS                        │
        └───────────────────────────────────────────────┘
```

## Gate status vocabulary (no false green)

Every gate resolves to exactly one of:

| Status                 | Meaning                                                            |
| ---------------------- | ------------------------------------------------------------------ |
| `PASS`                 | Gate exercised and satisfied                                       |
| `FAIL`                 | Gate exercised and failed                                          |
| `BLOCKED_EXTERNAL`     | Cannot run without external creds/infra (staging, Lenco F9b, etc.) |
| `NOT_RUN`              | Deliberately skipped (e.g. `--skip-e2e`)                           |
| `UNKNOWN`              | Ran but result inconclusive                                        |
| `MEASUREMENT_UNSTABLE` | Infrastructure variance prevents strict blocking                   |

**Never** translate the latter four into `PASS`.

## Orchestrator

```bash
# Full local certification (static + integration; E2E if customer app running)
bash scripts/qa/release-certify.sh

# Static layer only (fast)
bash scripts/qa/release-certify.sh --layer static

# Against staging deploy
E2E_BASE_URL=https://staging.vergeo5.com bash scripts/qa/release-certify.sh --environment staging

# Skip browser (no local dev server)
bash scripts/qa/release-certify.sh --skip-e2e
```

Outputs:

- `scripts/qa/evidence/gate-*.json` — per-gate fragments
- `scripts/qa/evidence/release-certificate.json` — machine-readable certificate
- `scripts/qa/evidence/release-certificate.md` — human-readable summary

## Layer 1 — Static gates

| Gate ID            | Source                                            |
| ------------------ | ------------------------------------------------- |
| `lint`             | `pnpm lint`                                       |
| `typecheck`        | `pnpm typecheck`                                  |
| `unit-js`          | `pnpm test`                                       |
| `unit-api`         | `uv run pytest` (excl. rls/evals)                 |
| `i18n-parity`      | `scripts/ci/i18n-lint.mjs`                        |
| `migration-replay` | `scripts/ci/migration-replay.sh` (needs Postgres) |
| `rls-isolation`    | `pytest tests/rls` (needs local Supabase)         |
| `deps-audit`       | `pnpm audit` (authoritative in CI with allowlist) |

Mirrors `.github/workflows/ci.yml` jobs.

## Layer 2 — Integration gates

Domain manifest: `scripts/qa/integration-manifest.json`

| Gate ID        | Domain                           |
| -------------- | -------------------------------- |
| `int-cart`     | Cart + RFQ merge                 |
| `int-checkout` | Checkout + payment               |
| `int-rfq`      | RFQ threads + checkout integrity |
| `int-returns`  | Returns lanes 1 & 2              |
| `int-orders`   | Vendor order queue               |
| `int-reviews`  | Review aggregates                |
| `int-authz`    | Route × role matrix              |

## Layer 3 — Browser E2E

Standalone package: `e2e/` (not in pnpm workspace).

| Spec                        | Journey                                                                    |
| --------------------------- | -------------------------------------------------------------------------- |
| `browse-journey.spec.ts`    | HOME → SEARCH → CATEGORY → PDP → CART → CHECKOUT                           |
| `mobile-layout.spec.ts`     | Overflow, touch targets, sticky controls @ 5 viewports                     |
| `data-quality.spec.ts`      | K0.00, missing images, dead PDPs, demo badges                              |
| `ux-surfaces.spec.ts`       | Wishlist, compare, vendor storefront, offline, orders                      |
| `a11y-smoke.spec.ts`        | axe wcag2a/aa critical+serious                                             |
| `performance-smoke.spec.ts` | Web Vitals candidates (LCP, CLS) — reports MEASUREMENT_UNSTABLE when noisy |

### Mobile viewports (Playwright projects)

| Project              | Size                       |
| -------------------- | -------------------------- |
| `mobile-fast-3g-360` | 360×800 (primary, Fast-3G) |
| `mobile-390`         | 390×844                    |
| `mobile-430`         | 430×932                    |
| `tablet-768`         | 768×1024                   |
| `desktop-1440`       | 1440×900                   |

## Certificate schema

```json
{
  "schema_version": 1,
  "certification": "CERTIFIABLE_AFTER_INTEGRATION | BASELINE_FAILING | BLOCKED_EXTERNAL",
  "identity": { "sha", "branch", "environment", "generated_at" },
  "gates": { "<gate-id>": { "status", "layer", "detail", "duration_ms" } },
  "sections": { "security", "database", "ux", "a11y", "performance", "data_quality", "payments", "recovery" },
  "summary": { "pass", "fail", "blocked_external", "not_run", "unknown", "measurement_unstable" }
}
```

## CI integration

- **Per-PR blocking**: `.github/workflows/ci.yml`, `perf.yml` (Layer 1 + perf/a11y subset)
- **Nightly staging E2E**: `.github/workflows/e2e.yml`
- **Release certification**: `.github/workflows/release-certify.yml` (on-demand + weekly)

## Payments & recovery

| Gate              | Requirement                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| `payment-sandbox` | `LENCO_ENV=sandbox` + `LENCO_API_TOKEN` (F9b founder gate)                |
| `backup-drill`    | `scripts/ops/backup_drill.sh` (dry-run locally; live drill founder-gated) |

## Remaining coverage gaps

See certificate `sections` rollup and `docs/production-readiness/` for P0 items.
Key gaps tracked by this suite as `BLOCKED_EXTERNAL` until infra lands:

- Full Lenco sandbox charge on deployed staging (F9b)
- WhatsApp mock receipt assertions
- Dedicated inventory/reservation integration module
- Production backup/restore dated evidence (G7)
