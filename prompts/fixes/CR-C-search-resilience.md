> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# CR-C — Search resilience: never return empty on a partial outage

## Finding

Hybrid search (Postgres FTS + pg_trgm + pgvector, RRF fusion) lives in `services/api/app/services/search/` (`__init__.py` = `run_search`, `embedding_client.py` = `fetch_query_embedding` → `list[float] | None`, `query_builder.py`, `synonyms.py`) behind `app/routers/search.py`. **`SearchResponse` already declares `degraded: bool = False`** (`__init__.py`) — so the envelope exists, but recent ops history ("search degraded probe (CCP-05)") shows the live path still collapses when the embedding/vector leg is unavailable (provider quota/latency). **The fix is to guarantee the fallback actually fires, sets `degraded=True`, and never returns empty — not to add a new field.** Intent-based discovery is a core concept moat; empty results on a partial outage is a launch-blocker-class UX failure.

## Required fix

- **Guarantee graceful degradation in `run_search`:** when `fetch_query_embedding` returns `None`, raises, or exceeds a **bounded timeout**, the query MUST complete on **FTS + pg_trgm only**, still return ranked results, and set `degraded=True` on the response. It must never raise out of `run_search` because embeddings were down, and never return an empty list solely due to the missing vector leg. Log the degradation (structured, once per request). Confirm `fetch_query_embedding` wraps its provider call in a timeout + catches transport errors → returns `None` (don't let it bubble).
- **Health probe:** add a search-subsystem check (embedding-leg reachable? vector RPC present?) to the **existing** `app/routers/health.py` — extend `/readyz` (or add a `search` sub-check to it). **Do NOT create a new health router** (`healthz`/`health`/`readyz`/`fingerprint` already live there).
- **Client hint (optional, only if it fits this PR):** when `degraded` is true the results UI may show a subtle "showing best matches" note — otherwise keep this API-only.
- Keep RRF weights and happy-path ranking identical; this is additive fallback + observability. No money, no auth changes.

## Files (ONLY)

- Modify `services/api/app/services/search/__init__.py` (`run_search` fallback) and `services/api/app/services/search/embedding_client.py` (timeout + None-on-error)
- Extend `services/api/app/routers/health.py` (search sub-check on `/readyz`)
- Add/extend `services/api/tests/test_search_degraded.py`
- **Do NOT touch** `search.py` route signature, the `ask/` RAG routers, `query_builder.py` ranking, migrations, ledger/orders, or `main.py`.

## Tests (RUN)

- Monkeypatch `fetch_query_embedding` to raise / return `None` / sleep past the timeout → assert `run_search` returns **non-empty** FTS-only results with `degraded=True`. Happy path → `degraded=False`, RRF ranking unchanged (snapshot the ordering). `/readyz` reports the search sub-check. Full `uv run pytest` + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (timeout budget + how fallback is triggered) / TESTS (paste degraded-non-empty + happy-path + health assertions + pytest tail) / EXCERPTS (the fallback branch) / QUESTIONS.
