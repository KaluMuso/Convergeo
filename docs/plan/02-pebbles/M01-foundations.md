# M01 — Foundations & Infrastructure — Pebbles

7 pebbles · **Wave 0, strictly sequential** (each builds on the previous). Conventions established here bind all later pebbles: router auto-discovery (nobody edits `main.py`), one migration file per pebble (`NNNN_slug.sql`, additive after M03), no barrel files in packages (deep imports only), i18n messages split per-namespace file.

---

### M01-P01 — Monorepo scaffold `M`
**Deps:** none · **Files:** root `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `.gitignore`, `.editorconfig`, `.nvmrc`, `Makefile`, `README.md`, `packages/config/` (package.json, `tsconfig.base.json`, `eslint.config.mjs` preset incl. placeholder slot for no-hardcoded-strings rule, `prettier.config.mjs`)
pnpm + turborepo workspace (`apps/*`, `packages/*`, `services/*`); TS strict base config; turbo pipelines dev/build/lint/typecheck/test with caching; Makefile targets (`make dev`, `make test`).
**AC:** `pnpm i` clean install; `pnpm lint|typecheck|test|build` execute across (empty) workspaces; Node + pnpm versions pinned.
**Tests:** CI script asserts `turbo run build --dry-run` resolves the workspace graph.

### M01-P02 — FastAPI service skeleton `M`
**Deps:** P01 · **Files:** `services/api/pyproject.toml`, `services/api/app/main.py`, `app/core/settings.py`, `app/core/errors.py`, `app/core/logging.py`, `app/routers/__init__.py`, `app/routers/health.py`, `services/api/tests/test_health.py`, `services/api/ruff.toml`, `services/api/mypy.ini`
Python 3.12 + uv; pydantic-settings (fail-fast on bad env); uniform error envelope `{"error":{"code","message","details"}}`; structured JSON logging; `/health` (+git sha); **router auto-discovery**: `main.py` imports every module under `app/routers/` exposing `router` — later pebbles add routers without touching shared files.
**AC:** `uv run pytest|ruff check|mypy` green; `/health` 200; missing env var → clear startup error.
**Tests:** health 200; 404 uses error envelope; settings validation failure case.

### M01-P03 — Supabase pipeline & base migration `S`
**Deps:** P01 · **Files:** `supabase/config.toml`, `supabase/migrations/0001_extensions.sql`, `scripts/gen-types.sh`, `packages/types/` (package.json, `src/db.ts` placeholder), `docs/ops/supabase-workflow.md`
Supabase CLI local stack; `0001` enables `pgcrypto`, `pg_trgm`, `vector`; migration naming convention `NNNN_slug.sql` (one file per pebble; additive-only after M03 merges); typegen script → `packages/types/src/db.ts`; reset/diff/push + staging/prod project workflow documented.
**AC:** `supabase db reset` clean; typegen output compiles; doc sufficient for a fresh session.
**Tests:** CI job: db reset + typegen drift check (fails if committed types stale).

### M01-P04 — Customer app shell `M`
**Deps:** P01, P03 · **Files:** `apps/customer/` (app router skeleton: `app/[locale]/layout.tsx`, `page.tsx` placeholder, `next.config.ts`, `tailwind.config.ts`, `middleware.ts` locale stub, `vercel.json`), `packages/ui/` (package.json, `tailwind-preset.ts` **stub** — real tokens M02-P01), `packages/i18n/` (package.json, `messages/en/common.json`, next-intl request config)
Next.js 15 App Router, TS strict, Tailwind 4 consuming the ui preset, next-intl wired (EN), mobile viewport meta, 360px-first placeholder page with zero hardcoded strings.
**AC:** `pnpm dev --filter customer` renders localized placeholder; `pnpm build` green; strings come from `common.json`.
**Tests:** vitest smoke render; missing-i18n-key failure case.

### M01-P05 — Vendor & admin app shells `S`
**Deps:** P04 · **Files:** `apps/vendor/` and `apps/admin/` (same skeleton pattern as customer; admin: `robots.txt` noindex, standalone output for Docker, separate origin/port config)
Clones the P04 pattern; admin is deliberately austere (no SEO, no PWA).
**AC:** both apps dev + build green; admin marked noindex; all three apps run concurrently via `pnpm dev`.
**Tests:** smoke render each; admin robots/noindex asserted.

### M01-P06 — CI pipeline `M`
**Deps:** P02–P05 · **Files:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml` (stub jobs), `.gitleaks.toml`, `scripts/ci/`
PR workflow: turbo-affected JS lint/typecheck/vitest/build · Python ruff/mypy/pytest · `supabase db reset` + typegen drift · gitleaks secret scan · `pnpm audit`/`uv` dependency audit · concurrency-cancel. Required-checks list documented in README.
**AC:** CI green on repo as of P05; a planted dummy secret on a test branch is caught by gitleaks (dry run documented in PR).
**Tests:** the workflows themselves + fixture tests for `scripts/ci/`.

### M01-P07 — OCI runtime, deploy, backups & rollback `L`
**Deps:** P06 · **Files:** `infra/docker-compose.yml`, `infra/Caddyfile`, `infra/.env.example`, `services/api/Dockerfile`, `infra/deploy.sh`, `infra/backup/pg-dump.sh`, `infra/n8n/backup-nightly.json`, `docs/ops/runbook-deploy-rollback.md`, `docs/ops/runbook-dns-cloudflare.md`
Compose (api, caddy, n8n; pinned image digests); Caddy TLS + baseline security headers; `deploy.sh` = tagged image pull + `compose up -d`, `deploy.sh rollback <tag>`; nightly pg_dump → OCI Object Storage (14-day retention) via n8n; Cloudflare DNS/proxy runbook. **No console-clicked config anywhere** — everything reproducible from this directory.
**AC:** staging deploy + rollback executed and transcribed in runbook; backup object lands in bucket; `docker compose config` valid.
**Tests:** compose config validation + shellcheck in CI.
