> **Prepend `prompts/_header.md`.** This is a **follow-up on the existing CR-C branch** (`cursor/search-degraded-fallback-8a6a`, PR #473) — check that branch out and push onto it so the PR updates; do NOT branch from master. **Touch ONLY the files below.** Foreground blocking; run the search + health tests before reporting.

# CR-C2 — Decouple `/readyz` overall status from search + drop out-of-scope file

## Finding (review of PR #473)

Two issues from the CR-C review:

1. **`/readyz` overall `status` now flips to `"degraded"` whenever the search-RPC probe fails.** But `/readyz` is a black-box liveness contract consumed by (a) `infra/uptimerobot.md` monitor #5 (keyword `ok`), (b) the `verify_live.sh` **G1** gate in PR #469 (asserts body contains `"status":"ok"`), and (c) the staging deploy smoke gate. Search has graceful FTS fallback and must **never** mark the platform unready — otherwise an OpenRouter outage or a 2s probe timeout produces false-down pages and fails the launch verifier while API + DB + frontends are all healthy. The container HEALTHCHECK uses `/healthz`, so this is a monitoring/verifier-coupling bug, not a restart loop — but it still breaks the contract.
2. **`_search_vector_rpc_present()` runs a real `search_rrf` query on every `/readyz` hit** (UptimeRobot calls it every 60s) — needless DB load + pollutes search telemetry.
3. **PR #473 also modifies `services/api/tests/test_kyc_state.py`** (a docstring), which is out of scope and collides with PR #470 touching the same file. Revert it here.

## Required fix

- In `services/api/app/routers/health.py`, `/readyz`: **overall `status` must be driven by Supabase reachability only.** Keep `search_rpc` and `search_embedding` as **informational sub-fields**, but they must NOT influence overall `status`:
  ```python
  overall_ok = supabase_ok   # NOT: supabase_ok and search_rpc_ok
  ```
- **Do not run `search_rrf` on the default `/readyz` hot path.** Make the vector-RPC probe opt-in: only execute `_search_vector_rpc_present()` when the caller passes `?checks=search` (default omits it and reports `search_rpc: "unchecked"`). The embedding-config check (`_search_embedding_configured()`, env-only, cheap) may stay unconditional. This keeps the 60s UptimeRobot probe cheap and side-effect-free.
- **Revert the `services/api/tests/test_kyc_state.py` docstring change** so this branch stops touching that file (it belongs to no assigned pebble and conflicts with PR #470).
- Update `services/api/tests/test_search_degraded.py`:
  - `test_readyz_includes_search_subchecks` → assert overall `status == "ok"` when Supabase is reachable **even if `search_embedding`/`search_rpc` are degraded** (the whole point).
  - Add a case: `/readyz` (no `?checks=search`) does **not** call `search_rrf` (assert the RPC handler was not invoked), and `search_rpc` reports `"unchecked"`.
  - `/readyz?checks=search` still surfaces `search_rpc` ok/degraded.
- Leave `run_search` fallback logic and `embedding_client.py` **unchanged** — they were correct.

## Files (ONLY)

- Modify `services/api/app/routers/health.py`
- Modify `services/api/tests/test_search_degraded.py`
- Revert `services/api/tests/test_kyc_state.py` to master (remove the docstring change)
- **Do NOT touch** `services/api/app/services/search/*` (correct as-is), migrations, `main.py`, apps.

## Tests (RUN)

- `/readyz` returns `status: ok` when Supabase reachable regardless of search sub-check state; default `/readyz` does not invoke `search_rrf`; `/readyz?checks=search` reports the search RPC state. Existing degraded-search tests still pass. Full `uv run pytest -k "search or readyz or health"` + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS / TESTS (paste readyz-stays-ok-when-search-degraded + no-search_rrf-on-default assertions + tail) / EXCERPTS (the `overall_ok` line + the opt-in gate) / QUESTIONS.
