# CI speed matrix (T40)

Path-aware tier selection keeps **required check names unchanged** while skipping expensive jobs on pull requests that cannot affect them. Skipped jobs report **success** (GitHub `skipped`), so branch protection never hangs on missing contexts. Master pushes and the nightly schedule still run the **full** matrix (fail-open when the diff is unknown).

## How scope is decided

| Layer                           | Role                                                                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `dorny/paths-filter@0e4a8c6e`   | Fast `api`, `db`, `web`, `docs` flags on pull requests (logged + exposed as job outputs).                             |
| `scripts/ci/detect_ci_scope.py` | Authoritative tier flags (`run_js`, `run_python`, `run_db_light`, …) from the git diff; infra/unknown diff fail-open. |

### Path → tier mapping (pull requests)

| Path bucket                                         | dorny filter | Heavy DB jobs (`run_db_light` / `run_typegen`)   | Perf (`run_perf`)                                  |
| --------------------------------------------------- | ------------ | ------------------------------------------------ | -------------------------------------------------- |
| `services/api/**`, `infra/api.Dockerfile`           | `api`        | Yes                                              | No (unless `apps/**` or `packages/**` also change) |
| `supabase/**`, `packages/types/**`, `scripts/ci/**` | `db`         | Yes                                              | No                                                 |
| `apps/**`, `packages/**`                            | `web`        | No                                               | Yes into `master` (or money paths)                 |
| Markdown / `prompts/**` only                        | `docs`       | **Docs-only lane** — secret scan + **lint only** | Skipped                                            |

Heavy jobs gated by `run_db_light`: Migration replay, RLS matrix, Money DB-trigger integration, COD production-container smoke. Typegen drift uses `run_typegen` (subset of schema/typegen inputs).

## Docs-only lane

When every changed file matches documentation patterns, CI runs:

1. **Secret scan (gitleaks)** — unchanged, always on.
2. **JavaScript / TypeScript** — `pnpm turbo run lint` only (no typecheck, test, or build).

All other required checks are skipped and count as green.

## Caching & warm-up (T40)

- **pnpm**: `actions/setup-node` with `cache: pnpm` on JS jobs (already present; unchanged).
- **uv**: `enable-cache: true` on `astral-sh/setup-uv` everywhere it was missing (`deps-audit`).
- **Docker**: `scripts/ci/warm-ci-docker-images.sh` prefetches `pgvector/pgvector:0.8.0-pg17-trixie` before DB-heavy jobs; Buildx GHA cache retained for COD image builds.

## Example PR wall-clock (GitHub Actions, 2025-11)

Measurements are workflow run duration (`run_started_at` → `updated_at`) on merged PRs **before** T40 landed on master. **After** targets assume this branch’s gates (not yet measured on Actions).

| Example   | PR                                                     | Scope                  | Before (observed)                       | After (target)           | Notes                                                             |
| --------- | ------------------------------------------------------ | ---------------------- | --------------------------------------- | ------------------------ | ----------------------------------------------------------------- |
| Docs-only | [#852](https://github.com/KaluMuso/Convergeo/pull/852) | `docs/**`, PNGs        | CI ~1.2 min*                            | **≤5 min**               | *Pre-T40 run failed early but still scheduled the full job graph. |
| UI-only   | [#871](https://github.com/KaluMuso/Convergeo/pull/871) | customer + i18n        | CI ~17 min, perf ~19 min (wall ~19 min) | **≤12 min**              | Skips DB/typegen/real-stack when no `api`/`db` paths.             |
| API + DB  | [#856](https://github.com/KaluMuso/Convergeo/pull/856) | logistics + migrations | CI ~17.5 min, perf ~11 min              | **Unchanged protection** | Full heavy tier; perf skipped when no `apps/**`/`packages/**`.    |

## Aggregator pattern

The **Python API** job remains the required context name. It accepts `python-shard` **skipped** when `run_python` is false (docs-only and other lanes), matching how other required checks rely on job-level `if:` + skip semantics.

## Related files

- `.github/workflows/ci.yml` — `changes` job + tier gates
- `.github/workflows/perf.yml` — perf tier gate
- `scripts/ci/detect_ci_scope.py` — tier logic unit-tested in CI
- `docs/ops/ci.md` — human checklist of required checks (names unchanged)
