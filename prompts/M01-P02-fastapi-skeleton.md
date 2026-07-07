> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P02 — FastAPI service skeleton

## 1. Context
**Wave 0, pebble 2 of 7 (sequential).** Depends on **M01-P01** (monorepo — merged). Establishes the backend skeleton and the **router auto-discovery convention** that keeps every later API pebble conflict-free (nobody edits `main.py` after this). Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P02. Read first: that spec, `CLAUDE.md` (error envelope, security conventions).

## 2. Objective & scope
`services/api`: Python 3.12 + uv project, app factory, fail-fast settings, uniform error envelope, structured JSON logging, `/health` (with git sha), router auto-discovery, ruff/mypy/pytest green.
**Non-goals:** no auth (M04), no DB access/migrations (P03/M03), no domain routers, no rate limiting (M04-P07), no Docker (P07).

## 3. Files (create ONLY these — under `services/api/` unless noted)
- `pyproject.toml` (+ `uv.lock`), `ruff.toml`, `mypy.ini`
- `app/main.py`, `app/core/settings.py`, `app/core/errors.py`, `app/core/logging.py`
- `app/routers/__init__.py`, `app/routers/health.py`
- `tests/test_health.py` (+ `tests/conftest.py` if needed)
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec
- **Settings (`core/settings.py`):** `pydantic-settings`, env-only (`ENV`, `LOG_LEVEL`, `GIT_SHA` optional, Supabase vars declared but optional until P03 wiring). **Fail-fast**: invalid/missing required env → clear startup error (redacted values).
- **Error envelope (`core/errors.py`) — exact shape:** `{"error": {"code": str, "message": str, "details": object}}`. Provide `AppError(code, message, http_status, details)` + handlers for `AppError`, `RequestValidationError` (422, `code="validation_error"`), unhandled `Exception` (500, generic message — real error logged, never leaked), and **404s use the envelope too**.
- **Logging (`core/logging.py`):** structured JSON (ts, level, msg, path, status); no secrets logged.
- **Router auto-discovery (`app/main.py`):** at startup, import every module under `app/routers/` exposing a `router` attribute and `include_router` it. **This is the binding convention — later pebbles add router files, never touch `main.py`.** Document it in a module docstring.
- **Health (`app/routers/health.py`):** `GET /health` → `{"status":"ok","sha":"<GIT_SHA|unknown>"}`.
- **Tooling:** `ruff` + `mypy` strict configs; pytest + httpx `TestClient` harness.

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A (backend). Async endpoints; no blocking calls in the event loop.

## 9. Security
- No secrets in code/logs; env-only. Unhandled exceptions return generic envelope (no stack/internal detail).
- CORS: configurable origin list from settings, default empty/dev-only — never `*` outside dev.

## 10. Tests (RUN before reporting)
- `/health` returns 200 with `status:ok` (+ sha field).
- Unknown route → 404 **in the error envelope shape**.
- Settings validation failure case (missing/invalid env → startup error).
- `AppError` handler → envelope with matching code/status; unhandled exception → 500 generic envelope.
- Auto-discovery: a dummy router module dropped into `app/routers/` during a test is discovered (or equivalent unit proof).
- Commands: `uv run pytest`, `uv run ruff check`, `uv run mypy`.

## 11. Acceptance criteria / DoD
- [ ] `uv run pytest | ruff check | mypy` all green.
- [ ] `/health` 200 incl. git sha.
- [ ] Missing env var → clear startup error.
- [ ] All error paths (404/422/500/AppError) use the exact envelope.
- [ ] Router auto-discovery works and is documented as the convention.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P02 — FastAPI service skeleton
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual pytest/ruff/mypy output
**EXCERPTS:** full code of `core/errors.py` and the auto-discovery block of `main.py` (API-contract surfaces) — nothing else
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
