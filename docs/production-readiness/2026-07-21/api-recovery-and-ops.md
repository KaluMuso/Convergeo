# API recovery + ops activation (2026-07-21)

**UTC:** 2026-07-21T11:27Z onward  
**Master tip at write:** post-#398/#399 (see git)

## 1. G1 API health — PASS (recovered)

| Probe                                     | Result                                                                                   |
| ----------------------------------------- | ---------------------------------------------------------------------------------------- |
| `GET https://api.vergeo5.com/healthz`     | **200** `{"status":"ok"}`                                                                |
| `GET https://api.vergeo5.com/readyz`      | **200** `{"status":"ok"}`                                                                |
| `GET https://api.vergeo5.com/fingerprint` | **200** `env=production`, `supabase_project_ref=dpadrlxukcjbewpqympu`, `git_sha=unknown` |
| Host SSH from agent                       | still denied (host key / key) — recovery was founder-side                                |

Prior session (2026-07-20): healthz/readyz **502**.

## 2. Live discovery honesty

| Probe                           | Result                                                                           |
| ------------------------------- | -------------------------------------------------------------------------------- |
| `GET /search?q=phone&limit=5`   | **200**, `degraded=true`, 1 service hit titled `Laptop & Phone Repair (demo)`    |
| `GET /catalog/listings?limit=5` | **200**, `total=0` items (demo product listings excluded / empty)                |
| Customer prod `/en/health`      | **200** `buildId=cde40bf…` — **behind** master (promote blocked by OG edge size) |

`degraded=true` expected until embeddings cron produces query embeddings + OpenRouter key healthy (CCP-05). Demo **service** title still surfaces — product demo exclusion (#368) does not strip service titles containing `(demo)`.

## 3. DB tip

Live `schema_migrations` tip: `0066_user_wishlist_recently_viewed` (after #394). Prior `0064` FORCE RLS + `0065` source_key remain applied.

## 4. n8n non-money activation (this session)

Published (active) via MCP after API 200:

| Workflow ID        | Name                  | Active  |
| ------------------ | --------------------- | ------- |
| `sevKtX1AmimQCWsG` | notification dispatch | **yes** |
| `oqjfSdMXClfsf3qd` | embeddings cron       | **yes** |
| `F25zEWiPoIveARys` | reservation sweeper   | **yes** |
| `8drZTFO79pwMPfZy` | analytics retention   | **yes** |
| `rb5d4LHlXAOqkfPX` | admin digest          | **yes** |
| `zkIe2zW72qp5fcli` | operational nudges    | **yes** |

**Left unpublished (money / alert):**

| Workflow ID        | Name                         | Reason                                     |
| ------------------ | ---------------------------- | ------------------------------------------ |
| `C1MpTNjrfLACMG3f` | payment reconciliation crons | money path — wait F9b + sandbox drills     |
| `LVuHqWgT1tqjYOtc` | shared error alert           | WhatsApp delivery credential not confirmed |

## 5. Frontend promote blocker

Vercel production deploy `dpl_Ev4Vov93…` @ `3afdba0` → `ERROR`  
`NOW_SANDBOX_WORKER_MAX_MIDDLEWARE_SIZE` — Edge Function `[locale]/opengraph-image-1t2zn3` **1.07 MB** > 1 MB plan limit.

Fix PR: `cursor/fix-og-edge-size-da3e` (slim OG imports). After merge, redeploy customer/vendor/admin to master tip. Rollback candidate remains `dpl_6Pgevsi…` @ `cde40bf`.

## 6. Flags

`public_launch` unchanged (invite-only sell CTA still disabled). No production Lenco charges from this session.

## 7. Next

1. Merge OG size fix → promote frontends.
2. Land UI density PR.
3. Re-probe search `degraded` after embeddings ticks.
4. F9b sandbox money drills when founder provides Lenco sandbox creds.
5. Keep money n8n unpublished until S1/S2 pass.
