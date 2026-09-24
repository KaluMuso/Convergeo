# AGENTS.md

Project overview, decisions, and conventions live in `CLAUDE.md` and `docs/`. Standard commands are in `README.md` (JS/TS) and `services/api/README.md` (Python API).

## Git branching and cloud task identity

- An explicit user-specified source branch, commit and PR target take precedence over generic branching defaults.
- For the PR #714 release continuation, select `hardening/20260924-converged-implementation` in the cloud task's source selector. Its parent PR targets `staging`; this does not make `staging` the implementation source. Do not reconstruct the candidate from `master` or S3.
- Before editing, record `git rev-parse HEAD`, `git rev-parse HEAD^{tree}` and the working-tree status, and compare them with the task's expected identity. On a mismatch, stop before editing and request the correct task source.
- A temporary local branch named `work`, a detached checkout, or no configured shell remote is not by itself an identity failure. Verify the actual source commit/tree; do not rename a branch and claim that changed its contents.
- Use only the available, authorized repository publication control. A returned PR title/body without a URL or remotely verified ref is not publication proof. Do not bypass network controls or request production credentials to repair a task checkout.
- Do not merge into `staging` or `master`, dispatch deployments, mutate shared databases, or activate money without the corresponding explicit authorization. Preserve the candidate's branch-specific deployment guards.
- For unrelated work without a specified base, the default is `master`; use `cursor/<descriptive-name>-<suffix>` only for Cursor tasks. Never use the deleted `claude/nice-knuth-ijvthu` branch.

## Cursor Cloud specific instructions

Environment refresh (nvm node + pnpm, uv + API deps) is handled by the startup update script. Notes below are the non-obvious caveats for running/testing in this VM.

### Toolchain / PATH gotchas

- The VM enforces its own `node` shim at `/exec-daemon/node`, which sits ahead of nvm on `PATH`. The repository and nvm both target Node 22; a newer compatible shim may still appear first. `pnpm`/`corepack` come from the nvm-managed Node 22 install.
- Interactive login shells (`bash -l`) already source nvm and `~/.local/bin/env` via `~/.bashrc`, so `pnpm` and `uv` are on `PATH`. For non-login shells, prepend: `export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; export PATH="$HOME/.local/bin:$PATH"`.

### Services (all run in dev mode)

| Service        | Dir            | Dev command                                         | Port |
| -------------- | -------------- | --------------------------------------------------- | ---- |
| customer (web) | repo root      | `pnpm dev` (turbo runs all 3 Next.js apps together) | 3000 |
| vendor (web)   | repo root      | (started by `pnpm dev`)                             | 3001 |
| admin (web)    | repo root      | (started by `pnpm dev`)                             | 3002 |
| API (FastAPI)  | `services/api` | `uv run uvicorn app.main:app --reload --port 8000`  | 8000 |

- Next.js apps are locale-prefixed: hit `/en` (also `/bem`, `/nya`, `/fr`), not `/`. Health check per app: `GET /<locale>/health`.
- API health/readiness paths are `GET /healthz` and `GET /readyz` (not `/health`). Swagger UI at `/docs`.

### API startup env vars

- `app/settings.py` requires `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` or the server exits at startup. For local dev/testing without a real Supabase project, dummy values are fine, e.g. `SUPABASE_URL=https://example.supabase.co SUPABASE_SERVICE_ROLE_KEY=dev SUPABASE_ANON_KEY=dev`. `CORS_ORIGINS` may not contain `*` unless `ENV=development`.
- Pytest does not need real env vars — `tests/conftest.py` sets safe defaults.

### Lint/test/build

- JS/TS: `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` (turbo, all workspaces). Inspect the current workspace test scripts; do not assume only one app has tests.
- API: from `services/api`, `uv run ruff check .`, `uv run mypy app tests scripts`, `uv run pytest` (Makefile wrappers `make api-lint|api-test|api-typecheck` are still placeholders — call `uv run ...` directly).
- The i18n messages live in `packages/i18n/messages/<locale>/<namespace>.json` (17 namespaces, nested keys). EN is the source-of-truth with full coverage and `fr`/`zh` are complete; `bem`/`nya` are partial (13/17 namespaces — `admin`/`ai`/`legal`/`vendor` still EN-only) and fall back to EN via runtime deep-merge (`packages/i18n/src/request.ts`), so a missing vernacular key renders English, never a raw key path.
