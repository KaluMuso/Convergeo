> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# CR-C — Search resilience: never return empty on a partial outage

## Finding

Hybrid search (Postgres FTS + pg_trgm + pgvector, RRF fusion) and Ask-Vergeo RAG are built under `services/api/app/services/search/` + `app/routers/search.py` + `app/routers/ask/`. Recent ops history ("search degraded probe (CCP-05)") shows the **live path degrades** — most likely when the embedding/vector leg is unavailable (embedding provider quota/latency), which can collapse results. Intent-based discovery is a core concept moat; a search that returns empty on a partial outage is a launch-blocker-class UX failure.

## Required fix

- **Graceful degradation:** when the vector/embedding leg fails or times out (bounded timeout), the query MUST fall back to **FTS + pg_trgm only** and still return ranked results — never raise, never return empty because embeddings were down. Log the degradation and surface a machine-readable `degraded: true` + `mode` in the search response envelope.
- **Health probe:** expose the search subsystem's health (embedding-leg reachable? vector index present?) via the existing readiness/health surface so the degraded state is observable (feeds the ops `/readyz` story — do not build a new health router, extend the existing one if present, else add a single `search_health.py`).
- **Client hint (optional, if a tiny customer change is in the same PR budget):** if the response is `degraded`, the results UI may show a subtle "showing best matches" note — otherwise leave the UI untouched and keep this an API-only pebble.
- Keep RRF weights and ranking identical in the happy path; this is purely additive fallback + observability. No money, no auth changes.

## Files (ONLY)

- Modify `services/api/app/routers/search.py` and the relevant module(s) under `services/api/app/services/search/` (query builder / embedding client)
- Add/extend `services/api/tests/test_search_degraded.py`
- If a health surface exists, extend it; else add `services/api/app/routers/search_health.py`
- **Do NOT touch** the `ask/` RAG routers, migrations, ledger/orders, or `main.py`.

## Tests (RUN)

- Force the embedding leg to raise/timeout → assert the endpoint returns **non-empty** FTS-only results with `degraded: true`. Happy path → `degraded: false`, RRF ranking unchanged. Health probe reports the degraded subsystem. Full `uv run pytest` + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (timeout budget + how fallback is triggered) / TESTS (paste degraded-non-empty + happy-path + health assertions + pytest tail) / EXCERPTS (the fallback branch) / QUESTIONS.
