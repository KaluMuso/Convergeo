# AGENTS.md

Project overview, decisions, and conventions live in `CLAUDE.md` and `docs/`. Standard commands are in `README.md` (JS/TS) and `services/api/README.md` (Python API).

## Cursor Cloud specific instructions

Environment refresh (nvm node + pnpm, uv + API deps) is handled by the startup update script. Notes below are the non-obvious caveats for running/testing in this VM.

### Toolchain / PATH gotchas

- The VM enforces its own `node` shim at `/exec-daemon/node` (currently v22), which sits ahead of nvm on `PATH`. So `node -v` reports v22 even though `.nvmrc` pins 20; this is expected and harmless — the toolchain (build/tests/dev) works on it. `pnpm`/`corepack` come from the nvm-managed Node 20 install.
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

- JS/TS: `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` (turbo, all workspaces). Only the `customer` app currently has vitest tests.
- API: from `services/api`, `uv run ruff check .`, `uv run mypy app tests scripts`, `uv run pytest` (Makefile wrappers `make api-lint|api-test|api-typecheck` are still placeholders — call `uv run ...` directly).
- The i18n messages (`packages/i18n/messages/*/common.json`) currently use flat dotted keys, so some pages render raw keys (e.g. `nav.home`) — this is the current scaffold state, not an environment problem.
