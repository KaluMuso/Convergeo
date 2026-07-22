# Post-#415 deploy + search honesty (2026-07-21)

**UTC:** 2026-07-22T11:55Z (updated)  
**Master tip:** `dd14b4c` (merge #480 — OpenRouter embedding model fix at 384 dims)

## 1. API deploy — **redeploy required after #480**

| Probe                                     | Result (2026-07-22T11:55Z)                     |
| ----------------------------------------- | ---------------------------------------------- |
| `GET https://api.vergeo5.com/fingerprint` | **200** `git_sha=unknown`, `image_tag=unknown` |
| GHCR `API image` for `dd14b4c`            | **built** (run 29917287306 success)            |
| Live embeddings tick (n8n exec 14613)     | `{processed:0}` — **still old image**          |

**Founder:** pull the **new** image (your earlier redeploy was before #480 merged):

```bash
./redeploy-api.sh latest   # must show a new digest, not "Image is up to date" from pre-#480

# Load env into shell (fixes "unauthorized" when $INTERNAL_EMBEDDINGS_TOKEN unset)
set -a; source ~/vergeo5-api.env; set +a

curl -sS -X POST https://api.vergeo5.com/internal/embeddings/tick \
  -H "X-Internal-Token: $INTERNAL_EMBEDDINGS_TOKEN"
# expect: {"processed":>0,"dead":0,"cost_usd":...}

curl -sS 'https://api.vergeo5.com/search?q=tea'   # no jq needed
```

## 2. DB — demo service tagged (done)

Live `services` row `1be21900-7a4f-48ee-bee5-19f770b75e55` has `portfolio_images = ['demo/services/tech-services']`. Exclusion requires API code (#415) on the live host.

## 3. Embeddings / search degraded

| Item                                     | State (2026-07-21T21:15Z)                                                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `search_documents` with embedding        | **0 / 288**                                                                                                                     |
| `embedding_jobs` queued                  | **288** (requeued; attempts reset 2026-07-22 after provider-failure diagnosis)                                                  |
| `embedding_jobs` dead                    | **0**                                                                                                                           |
| Root cause (2026-07-22)                  | Default model `thenlper/gte-small` is **not on OpenRouter** → PR switches to `openai/text-embedding-3-small` + `dimensions=384` |
| n8n embeddings cron (`oqjfSdMXClfsf3qd`) | **unpublished** — publish only after `OPENROUTER_API_KEY` live on API host + successful manual tick                             |

**Activation sequence (after API redeploy + key):**

1. ~~`requeue-dead-embedding-jobs.sql`~~ **done** (288 queued)
2. Manual smoke: `POST https://api.vergeo5.com/internal/embeddings/tick` with `X-Internal-Token: $INTERNAL_EMBEDDINGS_TOKEN` — expect `processed > 0`, jobs move to `done`
3. Publish embeddings cron (`oqjfSdMXClfsf3qd`) via n8n
4. Wait 1–2 ticks (~10 min); re-probe `GET /search?q=tea` → `degraded=false` when `search_documents.embedding` non-null

**#409** fail-closed: tick skips claim when key missing — safe to publish cron only after step 2 passes.

## 4. Merged this session

| PR   | Title                                                |
| ---- | ---------------------------------------------------- |
| #437 | FIX-I — STOP marketing consent at enqueue + dispatch |

## 5. Frontends

Vercel production deploys rate-limited (24h). GitHub CI (Python API, perf budgets) is the merge gate.

## 6. Gates

| Gate                         | Verdict                                                           |
| ---------------------------- | ----------------------------------------------------------------- |
| LIVE-12 (search honesty)     | **FAIL** — `degraded=true`; embeddings backlog queued, 0 embedded |
| FD-04 / G11 (demo exclusion) | **PARTIAL** — code on master; live verify after API redeploy      |
| FIX-I (marketing consent)    | **CODE_MERGED** (#437) — live after API redeploy                  |
| F9b (Lenco sandbox)          | **OPEN** — money drills still founder-gated                       |
| `public_launch`              | **false**                                                         |
