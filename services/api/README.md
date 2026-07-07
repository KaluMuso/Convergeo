# Vergeo5 API

FastAPI backend for Vergeo5 (`services/api`).

## Requirements

- Python 3.12 (`uv` recommended)
- Environment variables (see `.env.example` at repo root)

Required for startup:

| Variable                    | Description                                                  |
| --------------------------- | ------------------------------------------------------------ |
| `SUPABASE_URL`              | Supabase project URL                                         |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only service role key                                 |
| `SUPABASE_ANON_KEY`         | Supabase anon key                                            |
| `ENV`                       | `development` \| `staging` \| `production`                   |
| `LOG_LEVEL`                 | Python log level (default `INFO`)                            |
| `CORS_ORIGINS`              | Comma-separated allowed origins (no `*` outside development) |

## Commands

```bash
cd services/api
uv sync
uv run pytest
uv run ruff check .
uv run mypy app tests scripts
uv run uvicorn app.main:app --reload
```

Makefile wrappers (from repo root):

```bash
make api-test
make api-lint
make api-typecheck
```

## OpenAPI export

```bash
uv run python scripts/export_openapi.py
```

Writes `services/api/openapi.json`. Future `pnpm gen:types` in `packages/types` will consume this schema alongside Supabase-generated DB types (handshake documented in `packages/types/README.md`).

## Architecture notes

- `create_app()` factory with router auto-discovery under `app/routers/`.
- Standard error envelope: `{"error": {"code", "message", "details", "request_id"}}`.
- `X-Request-ID` middleware propagates request IDs to logs and responses.
- Supabase service-role client (`app/supabase_client.py`) is **server-only** and bypasses RLS — callers must enforce authz.
