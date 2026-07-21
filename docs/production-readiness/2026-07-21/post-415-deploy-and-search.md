# Post-#415 deploy + search honesty (2026-07-21)

**UTC:** 2026-07-21T16:35Z  
**Master tip:** `38003ae` (merge #415 FIX-H demo service/event exclusion)

## 1. API deploy gap — BLOCKING for FIX-H live

| Probe                                     | Result                                                         |
| ----------------------------------------- | -------------------------------------------------------------- |
| `GET https://api.vergeo5.com/fingerprint` | **200** `git_sha=unknown`, `image_tag=unknown`                 |
| `GET /search?q=laptop`                    | **200**, `degraded=true`, **1 demo service hit** still present |
| `GET /services`                           | **200**, `total=1` (demo service still listed)                 |

**Root cause:** production API container has **not** been redeployed since #415 merged. Code on master filters demo services/events; live host is behind.

**Founder action (Hetzner, ~2 min):**

```bash
# On api.vergeo5.com host (see infra/redeploy-api.sh)
./redeploy-api.sh latest
# Or pin: ./redeploy-api.sh 38003ae
```

`api-image.yml` builds `ghcr.io/kalumuso/convergeo-api:latest` on every `services/api` push to master — image for #415 should already exist.

**Expected after redeploy:**

- `GET /search?q=laptop` → `total=0` (demo service excluded)
- `GET /services` → `total=0`
- `GET /catalog/listings?limit=5` → staging-drill fixtures still visible (unchanged)

## 2. DB — demo service tagged (done)

Live `services` row `1be21900-7a4f-48ee-bee5-19f770b75e55` now has `portfolio_images = ['demo/services/tech-services']` and `search_upsert_service` was re-run. Exclusion depends on API code (#415), not DB alone.

## 3. Embeddings / search degraded

| Item                                     | State                                                                                                                           |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `search_documents` with embedding        | **0**                                                                                                                           |
| `embedding_jobs` dead                    | **176+** (provider failures)                                                                                                    |
| `embedding_jobs` queued                  | **112+**                                                                                                                        |
| n8n embeddings cron (`oqjfSdMXClfsf3qd`) | **unpublished** again (2026-07-21T16:32Z) — was re-activated earlier; unpublished until `OPENROUTER_API_KEY` is set on API host |

**#409** fail-closed logic is on master but **not live** until API redeploy. Keep cron unpublished until:

1. API redeployed to master tip
2. `OPENROUTER_API_KEY` set in `~/vergeo5-api.env`
3. `scripts/ops/requeue-dead-embedding-jobs.sql` applied
4. Embeddings cron re-published
5. Re-probe `GET /search?q=tea` → `degraded=false`

## 4. Frontends

Customer prod was on `a111632` earlier today (post-#410). Vercel rate-limit may block new production builds — GitHub Performance budgets remain authoritative for merge.

## 5. Open draft PRs (discovery polish)

| PR   | Branch                                     | CI                     | Notes                                    |
| ---- | ------------------------------------------ | ---------------------- | ---------------------------------------- |
| #416 | `cursor/fix-cloudinary-max-file-size-9e0c` | green (pending Python) | Cloudinary signed upload `max_file_size` |
| #417 | `cursor/discovery-browse-polish-7f31`      | green (pending Python) | Stretched-link cards + back-to-top       |
| #418 | `cursor/discovery-locale-switcher-7f31`    | lint fix pushed        | Footer locale switcher                   |
| #419 | `cursor/discovery-search-filters-7f31`     | lint fix pushed        | Search price/category filters            |

## 6. Gates

| Gate                         | Verdict                                                           |
| ---------------------------- | ----------------------------------------------------------------- |
| LIVE-12 (search honesty)     | **FAIL** — `degraded=true`; demo service still visible pre-deploy |
| FD-04 / G11 (demo exclusion) | **PARTIAL** — code merged (#415); live verify after API redeploy  |
| F9b (Lenco sandbox)          | **OPEN** — money drills still founder-gated                       |
| `public_launch`              | **false**                                                         |
