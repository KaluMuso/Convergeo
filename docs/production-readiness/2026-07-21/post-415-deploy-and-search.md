# Post-#415 deploy + search honesty (2026-07-21)

**UTC:** 2026-07-22T12:25Z (updated)  
**Master tip:** `dd14b4c` (merge #480 — OpenRouter embedding model fix at 384 dims)

## 1. API deploy — **live on #480 image**

| Probe                          | Result (2026-07-22T12:25Z)                                                                                       |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| GHCR digest (founder redeploy) | `sha256:95c002f6763764b52bbec013d1c5cf760790c6e72cbcc3b80127d7d314537ed2`                                        |
| Manual embeddings tick         | `{processed:64, dead:0}` per batch — **working**                                                                 |
| `GET /search?q=tea`            | **`degraded=false`**, `total=4` (later probes `total=10`)                                                        |
| `GET /fingerprint`             | `git_sha=unknown` — **G9 open** until redeploy passes `GIT_SHA` (see PR for `redeploy-api.sh` + Dockerfile bake) |

**Founder shell tip:** quote CIDRs in `~/vergeo5-api.env`:

```bash
ADMIN_ALLOWED_IPS="127.0.0.1/32 10.0.0.0/8"
set -a; source ~/vergeo5-api.env; set +a
```

Pin immutable deploys (clears G9 once fingerprint PR merges + next image build):

```bash
./redeploy-api.sh dd14b4c3a3a382494a75effa905e4779605d33e7
curl -sS https://api.vergeo5.com/fingerprint
```

## 2. DB — demo service tagged (done)

Live `services` row `1be21900-7a4f-48ee-bee5-19f770b75e55` has `portfolio_images = ['demo/services/tech-services']`. Exclusion requires API code (#415) on the live host.

## 3. Embeddings / search — **RESOLVED**

| Item                                     | State (2026-07-22T12:25Z)                                                                                 |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `search_documents` with embedding        | **288 / 288**                                                                                             |
| `embedding_jobs`                         | **288 done**, 0 queued, 0 dead                                                                            |
| Root cause                               | `thenlper/gte-small` not on OpenRouter → **#480** uses `openai/text-embedding-3-small` + `dimensions=384` |
| n8n embeddings cron (`oqjfSdMXClfsf3qd`) | **published** (schedule every 5m)                                                                         |

## 4. Merged this session

| PR   | Title                                                      |
| ---- | ---------------------------------------------------------- |
| #437 | FIX-I — STOP marketing consent at enqueue + dispatch       |
| #480 | fix(api): OpenRouter embedding model at 384 dims (LIVE-12) |

## 5. Frontends

Vercel production deploys rate-limited (24h). GitHub CI (Python API, perf budgets) is the merge gate.

## 6. Gates

| Gate                         | Verdict                                                                |
| ---------------------------- | ---------------------------------------------------------------------- |
| LIVE-12 (search honesty)     | **PASS** — `degraded=false`, embeddings drained                        |
| G9 (deploy fingerprint)      | **PARTIAL** — API healthy; `git_sha` still unknown until next redeploy |
| FD-04 / G11 (demo exclusion) | **PARTIAL** — code on master; live verify after API redeploy           |
| FIX-I (marketing consent)    | **LIVE** (#437 on deployed image)                                      |
| F9b (Lenco sandbox)          | **OPEN** — money drills still founder-gated                            |
| `public_launch`              | **false**                                                              |

## 7. Next launch-critical (not code)

1. **F9b** — Lenco sandbox creds + staging money drill (S1–S6)
2. **G6/G7** — Sentry ingest + dated backup restore drill
3. **F5** — WhatsApp template approval (event cancel templates already coded as `event_cancelled` / `event_schedule_changed`)
4. Promote customer/vendor/admin Vercel prod when rate-limit clears
