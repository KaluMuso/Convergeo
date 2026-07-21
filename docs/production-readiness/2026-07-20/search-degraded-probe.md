# CCP-05 — Search `degraded` live probe evidence

**Date:** 2026-07-20T19:17Z  
**Branch:** `cursor/ccp-05-search-degraded-da3e`  
**Programme item:** CCP-05 / LIVE-12 / VF-P04 / MR-B07  
**Board crosswalk:** `current-implementation-board.md` → LIVE-12

---

## Final gate stance

| Gate / item    | Verdict                                  | Why                                                                                                                                          |
| -------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **LIVE-12**    | **FAIL** (honest `degraded=true`)        | API healthy (2026-07-21); live `/search` returns 200 with `degraded: true`. Semantic lane blocked by missing/invalid OpenRouter on API host. |
| **CCP-05 DoD** | **PARTIAL** → code follow-up in progress | Live re-probe done; root cause confirmed (H2). Fail-closed tick + requeue SQL shipped so a broken key cannot burn the job queue to `dead`.   |

Do **not** claim `degraded=false` or LIVE-12 PASS until `OPENROUTER_API_KEY` is set and document embeddings drain (`search_documents.embedding` non-null).

---

## 1. Live probes (2026-07-20T19:17Z)

All requests from Cursor Cloud agent VM; no auth required for public `/search`.

| #   | Request                                              | HTTP    | Body / headers                              | Notes                       |
| --- | ---------------------------------------------------- | ------- | ------------------------------------------- | --------------------------- |
| 1   | `GET https://api.vergeo5.com/search?q=test&limit=5`  | **502** | empty; `server: Caddy`; `content-length: 0` | Primary probe — **blocked** |
| 2   | `GET https://api.vergeo5.com/search?q=phone&limit=5` | **502** | empty                                       | Same                        |
| 3   | `GET https://api.vergeo5.com/search/suggest?q=pho`   | **502** | empty                                       | Suggest also down           |
| 4   | `GET https://api.vergeo5.com/healthz`                | **502** | empty                                       | Liveness down               |
| 5   | `GET https://api.vergeo5.com/readyz`                 | **502** | empty                                       | Readiness down              |

**Observed `degraded` on live:** **NOT_AUDITABLE** — no JSON returned.

**Historical context (not re-verified this session):** board fingerprint (Prompt 12) and 07-19 probes reported `degraded=true` when API was intermittently reachable. This session confirms API is fully unreachable (upstream not serving).

---

## 2. Investigation checklist (code + repo ops)

| #   | Check                                                        | Result                               | Evidence                                                                                                  |
| --- | ------------------------------------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| 1   | FTS/RRF returns rows when query embedding is `None`          | **PASS** (unit tests)                | `test_embedding_failure_degrades_without_500` — HTTP 200, `degraded=true`, `total>=1`                     |
| 2   | Query embedding path (`OPENROUTER_API_KEY`, model, dims=384) | **CODE_OK** / **LIVE_UNKNOWN**       | `embedding_client.py`: key missing → `None`; timeout default 2s; dim mismatch → `None`                    |
| 3   | Document embeddings cron + `INTERNAL_EMBEDDINGS_TOKEN`       | **REPO_INACTIVE** / **LIVE_MISSING** | `infra/n8n/embeddings-cron.json` → `"active": false`; n8n fleet verify: workflow **not imported** on live |
| 4   | Provider errors/timeouts degrade honestly                    | **PASS** (code + tests)              | Exceptions logged; `degraded=true`; no 500                                                                |
| 5   | UI never fakes green                                         | **PASS** (code)                      | Customer `results-tabs.tsx` shows banner when `response.degraded`                                         |

**No application code bug identified** — degraded semantics match programme intent. No code change in this PR.

---

## 3. Code path (degraded semantics)

### 3.1 `run_search` — degraded flag

File: `services/api/app/services/search/__init__.py`

```python
embedding = await fetcher(trimmed)  # fetch_query_embedding by default
# on exception: embedding = None (logged)
degraded = embedding is None and bool(trimmed)
```

- Empty/whitespace query → `degraded=false` (no semantic lane attempted).
- Non-empty query + `embedding is None` → `degraded=true` (keyword + trgm lanes only via `search_rrf` without `query_embedding`).
- Non-empty query + 384-d vector → `degraded=false`.

### 3.2 Query embedding fetcher

File: `services/api/app/services/search/embedding_client.py`

| Condition                                    | Returns             | Effect on search |
| -------------------------------------------- | ------------------- | ---------------- |
| `OPENROUTER_API_KEY` unset/empty             | `None`              | `degraded=true`  |
| OpenRouter HTTP error / timeout (2s default) | `None`              | `degraded=true`  |
| Response not 384-d `thenlper/gte-small`      | `None`              | `degraded=true`  |
| Success                                      | `list[float]` (384) | `degraded=false` |

Model/url overridable via `SEARCH_EMBEDDING_MODEL`, `SEARCH_EMBEDDING_URL`, `SEARCH_EMBEDDING_TIMEOUT_SECONDS`.

### 3.3 Document embeddings (index lane — separate from query `degraded`)

| Piece                                           | Role                                                                                                                         |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `POST /internal/embeddings/tick`                | `routers/internal_embeddings.py` — claims jobs, calls `process_embedding_tick`                                               |
| `services/api/app/services/embeddings/batch.py` | Batch embed via `embed_texts_with_fallback` (document lane; 30s timeout, retries)                                            |
| `infra/n8n/embeddings-cron.json`                | Schedule every 5m → `POST {$env.API_URL}/internal/embeddings/tick` with `X-Internal-Token: {$env.INTERNAL_EMBEDDINGS_TOKEN}` |

**Important distinction:** query-time `degraded` reflects **query** embedding fetch. Document cron keeps `search_documents.embedding` fresh for the **vector lane** in `search_rrf`. Both need OpenRouter + healthy API; cron inactive hurts semantic recall even if query embedding succeeds.

### 3.4 Router surface

`GET /search?q=…` → `run_search` (`routers/search.py`). No server-side override of `degraded`.

### 3.5 Tests (existing — no new regression needed)

- `test_semantic_query_returns_dress_results` → `degraded=false` when fetcher returns vector.
- `test_embedding_failure_degrades_without_500` → `degraded=true`, status 200.

---

## 4. Root-cause hypotheses (ranked)

| Rank   | Hypothesis                                           | Likelihood                         | Evidence                                                                                                   | Fix owner                                                             |
| ------ | ---------------------------------------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| **H1** | **API container/upstream down** (Caddy 502)          | **Confirmed**                      | All probes 502; matches board Prompt 6/12                                                                  | **FOUNDER** — DEP-03: restore API on OCI, pin digest                  |
| **H2** | **`OPENROUTER_API_KEY` missing/invalid on API host** | **Probable** when API returns      | Key absent → query embedding skipped; `degraded=true` for non-empty `q`                                    | **FOUNDER** — set env on API compose; never commit                    |
| **H3** | **Embeddings n8n workflow not imported/active**      | **Confirmed (repo + fleet audit)** | `embeddings-cron.json` `active: false`; live n8n missing workflow (`n8n-fleet-import-verify.md` §2 row 11) | **FOUNDER** — DEP-02: import + activate + `INTERNAL_EMBEDDINGS_TOKEN` |
| **H4** | OpenRouter provider outage / rate limit              | Possible                           | Would manifest as logged warnings + `degraded=true` while API up                                           | Monitor after H1–H3                                                   |
| **H5** | Stale/missing document embeddings in DB              | Possible secondary                 | Cron inactive; vector lane weak even if query embed works                                                  | Re-probe `search_rrf` + job queue after H3                            |

**Not a code defect:** degraded flag logic and honest UI banner are intentional and tested.

---

## 5. FOUNDER_REQUIRED actions

| ID           | Action                                                                                                           | Blocks                     |
| ------------ | ---------------------------------------------------------------------------------------------------------------- | -------------------------- |
| **FR-SD-01** | Restore `api.vergeo5.com` to HTTP 200 on `/healthz` and `/readyz` (DEP-03)                                       | Live degraded probe        |
| **FR-SD-02** | Set `OPENROUTER_API_KEY` on API host (production secret store)                                                   | Query semantic lane        |
| **FR-SD-03** | Import `infra/n8n/embeddings-cron.json`; set `API_URL`, `INTERNAL_EMBEDDINGS_TOKEN`; set `active: true` (DEP-02) | Document embedding backlog |
| **FR-SD-04** | After H1–H3: re-run live probe below and attach JSON snippet to this doc or a follow-up evidence PR              | LIVE-12 close              |

### Re-probe script (post-recovery)

```bash
# Expect HTTP 200 and JSON with "degraded" boolean
curl -sS "https://api.vergeo5.com/search?q=phone&limit=5" | jq '{degraded, total, query}'

# Health preflight
curl -sS -o /dev/null -w "%{http_code}\n" https://api.vergeo5.com/healthz
curl -sS -o /dev/null -w "%{http_code}\n" https://api.vergeo5.com/readyz
```

**Pass criteria for LIVE-12 (when API up):**

- `/search?q=<nonempty>` returns 200.
- If OpenRouter + cron healthy: `degraded: false` for typical queries.
- If key still missing: `degraded: true` is **honest PASS** (banner shown) — not a failure to fix by faking false.
- FTS still returns rows in degraded mode (regression guard).

---

## 6. Dependencies

| Dep                   | Status                     | Impact on search degraded    |
| --------------------- | -------------------------- | ---------------------------- |
| DEP-02 n8n fleet      | BLOCKED_EXTERNAL (API 502) | Embeddings cron not live     |
| DEP-03 API digest/pin | OPEN                       | Blocks all live verification |
| OpenRouter quota      | UNKNOWN                    | Query + document embeds      |

---

## 7. Verdict summary

| Question                       | Answer                                                |
| ------------------------------ | ----------------------------------------------------- |
| Is live `/search` healthy?     | **No** — 502                                          |
| Is `degraded` observable live? | **No** — NOT_RUN                                      |
| Is code honest?                | **Yes** — never fakes `degraded=false`                |
| Code change needed?            | **No** — investigation only                           |
| LIVE-12 status                 | **FAIL** (blocked); re-open verification after DEP-03 |

---

_Investigation evidence only. No runtime secrets committed._

---

## 8. Live refresh (2026-07-21) — API healthy

| Check                          | Result                                                                                                         |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `GET /healthz` / `/readyz`     | **200**                                                                                                        |
| `GET /search?q=tea&limit=1`    | **200**, `degraded: true`, `total: 2` (FTS/keyword lane OK)                                                    |
| `search_documents`             | **288** rows, **0** with `embedding`                                                                           |
| `embedding_jobs` (mid-session) | `dead=176`, `queued≈112` — last_error `Primary and fallback embedding providers failed`                        |
| n8n embeddings cron            | Was published; tick returned `{processed:0, dead:26}` — **unpublished** same session to stop burning the queue |
| Query + document lanes         | Both need `OPENROUTER_API_KEY` on API host (**FR-SD-02** still open)                                           |

### Code follow-up (this PR)

1. `process_embedding_tick` skips claim when key missing (no attempt burn).
2. Config errors after claim re-queue without incrementing `attempts`.
3. `embed_texts_with_fallback` raises clear `OPENROUTER_API_KEY is not configured` instead of wrapping as generic provider failure.
4. Ops SQL: `scripts/ops/requeue-dead-embedding-jobs.sql` — run **after** key is set, then re-publish embeddings cron.

### Founder order (updated)

1. Set `OPENROUTER_API_KEY` on API host + restart container.
2. Apply `scripts/ops/requeue-dead-embedding-jobs.sql`.
3. Re-publish n8n `Vergeo5 — embeddings cron` (`oqjfSdMXClfsf3qd`).
4. Confirm `GET /search?q=phone` → `degraded: false` and `search_documents.embedding` counts rising.
