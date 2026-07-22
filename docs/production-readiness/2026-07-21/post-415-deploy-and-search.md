# Post-#415 deploy + search honesty (2026-07-21)

**UTC:** 2026-07-21T21:15Z (updated)  
**Master tip:** `65908f1` (merge #437 FIX-I marketing consent + prior discovery/search stack)

## 1. API deploy gap — still BLOCKING for FIX-H / FIX-I / embeddings live

| Probe                                     | Result                                         |
| ----------------------------------------- | ---------------------------------------------- |
| `GET https://api.vergeo5.com/fingerprint` | **200** `git_sha=unknown`, `image_tag=unknown` |
| `GET /search?q=tea`                       | **200**, `degraded=true`, `total=2`            |
| `GET /search?q=laptop`                    | _(re-probe after redeploy)_                    |

**Root cause:** production API container has **not** been redeployed since master advanced (#415 FIX-H, #409 fail-closed embeddings, #437 FIX-I). GHCR image rebuilds on every `services/api` push — latest image should exist after #437 merge.

**Founder action (Hetzner `api.vergeo5.com`, ~3 min):**

```bash
# 1) Add OpenRouter key (value from Cursor env / secret store — never commit)
grep -q '^OPENROUTER_API_KEY=' ~/vergeo5-api.env || \
  echo 'OPENROUTER_API_KEY=PASTE_KEY_HERE' >> ~/vergeo5-api.env
# Or edit in place: nano ~/vergeo5-api.env

# 2) Pull + recreate container (infra/redeploy-api.sh)
./redeploy-api.sh latest

# 3) Verify
curl -fsS https://api.vergeo5.com/fingerprint | jq .
curl -fsS 'https://api.vergeo5.com/search?q=tea&limit=1' | jq '{degraded,total}'
```

**Expected after redeploy + key:**

- `GET /search?q=laptop` → `total=0` (demo service excluded — FIX-H)
- Marketing STOP suppresses nudges at dispatch/enqueue — FIX-I
- Embeddings tick can drain queued jobs when cron is published

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
