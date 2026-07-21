# Frontend promote tips + search re-probe (2026-07-21)

**UTC:** 2026-07-21T12:30Z  
**Master tip at write:** `d7891b8` (merge #400 recently-viewed + PLP quick-add)

## 1. Frontend production tips

| App      | Probe                                       | Result                                                           |
| -------- | ------------------------------------------- | ---------------------------------------------------------------- |
| Customer | `GET https://www.vergeo5.com/en/health`     | **200** `buildId=d7891b8707a17e5d3dbf20c7665f0c3f5c76f714`       |
| Vendor   | `GET https://vendor.vergeo5.com/api/health` | **200** `buildId=d7891b8707a17e5d3dbf20c7665f0c3f5c76f714`       |
| Admin    | `GET https://admin.vergeo5.com/api/health`  | Cloudflare Access **302** (not anonymously auditable from agent) |

Customer + vendor are **on the same tip** as master after #400 (+ prior OG slim #402 + density #403). Prior tip was `dc89f11` (ops evidence only).

`public_launch` unchanged (invite-only).

## 2. Search / catalog honesty

| Probe                                             | Result                                                                                   |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz` / `/readyz` | **200**                                                                                  |
| `GET /fingerprint`                                | **200** `env=production`, `supabase_project_ref=dpadrlxukcjbewpqympu`, `git_sha=unknown` |
| `GET /search?q=laptop&limit=3`                    | **200**, `degraded=true`, 1 hit — service `Laptop & Phone Repair (demo)`                 |
| `GET /catalog/listings?limit=3`                   | **200**, staging-drill fixtures present (e.g. Tea & Coffee / Footwear / Flour)           |

### Gate stance

| Item    | Verdict     | Notes                                                                                           |
| ------- | ----------- | ----------------------------------------------------------------------------------------------- |
| LIVE-12 | **FAIL**    | Live `degraded=true` still — do **not** claim green search                                      |
| Catalog | **PARTIAL** | Drill fixtures visible after #401; demo **service** titles still surface in search              |
| CCP-05  | **PARTIAL** | API recovered vs 2026-07-20 502; embeddings cron published but query embeddings not yet healthy |

Root causes still: OpenRouter / query embedding path and/or document embeddings coverage. Product demo Cloudinary exclusion does not strip service titles containing `(demo)`.

## 3. Bundle follow-up

#400 merged with a known Bundle/LH regression (static `mini-cart-drawer` import on `ListingCard` attached the ~6 KB gz cart chunk to audited `/page` graphs). Fix: **#406** — dynamic import of cart actions (measured home +1.4 KB / PLP +0.2 KB vs master).

Vercel customer preview for #406 hit **Deployment rate limited — retry in 24 hours**; GitHub Performance budgets remain the merge gate for the fix.

## 4. Next

1. Merge #406 when Bundle/LH green (ignore Vercel rate-limit if not required).
2. Re-probe `degraded` after embeddings ticks + confirm `OPENROUTER_API_KEY` on API host.
3. PDP polish #407 (preferred seller + sticky stock) — UI only.
4. F9b Lenco sandbox money drills remain founder-gated; keep payment recon n8n unpublished.
