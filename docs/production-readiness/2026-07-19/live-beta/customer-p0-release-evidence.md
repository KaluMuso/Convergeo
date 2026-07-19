# Customer P0 production release evidence — 2026-07-19

**Role:** Convergeo Customer P0 Production Release Manager  
**Scope:** Customer Vercel app only (`convergeo-customer`). No vendor/admin/API/DB/n8n/payments/flags/`public_launch`. No Preview promotion.  
**Verdict:** **Customer controlled-beta: NO-GO**  
**Deploy outcome:** **BLOCKED_EXTERNAL** — Vercel customer git deploy rate-limited + agent has no `VERCEL_TOKEN`.

This pack does **not** claim real-money readiness or open-launch readiness.

---

## 1. Release identity

| Item                                          | Value                                                                                                              |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Candidate (`origin/master`)                   | `619c994037f58f3e20d81f91ad72f5953bb5261b` — merge #330 PDP digest hotfix                                          |
| Evidence recorded (UTC)                       | `2026-07-19T17:22:49Z`                                                                                             |
| Currently aliased production                  | `dpl_CA2qcVXsCGnaorKCyr1onybCqszs` @ `28f565cbf55b78cbd7fd1074de9e50615b8a18d1` (#319 docs)                        |
| Production health `buildId`                   | `28f565cbf55b78cbd7fd1074de9e50615b8a18d1` (`GET /en/health`)                                                      |
| Deployed by this session?                     | **No**                                                                                                             |
| Deployed SHA                                  | _(none — blocked)_                                                                                                 |
| Previous production (allowed rollback record) | `dpl_ANpPCbDPGLEeyHy1h6EbEs5hzQY8` @ `1322c97f7c77fbfdbae8e7cf48935efbebeddd6c` (#309) — **not** used this session |
| Explicitly excluded rollback target           | `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` (per release instruction)                                                       |

Inspector (current prod): https://vercel.com/vergeo-projects/convergeo-customer/CA2qcVXsCGnaorKCyr1onybCqszs

---

## 2. Required merge ancestry

Fetched `origin/master`. Confirmed required merges are ancestors of candidate `619c994`:

| PR                                  | Merge SHA                       | Ancestor of candidate |
| ----------------------------------- | ------------------------------- | --------------------- |
| #298 categories RSC boundary        | `b17c311…`                      | **yes**               |
| #302 Live Beta Wave 1               | `d2e940b…`                      | **yes**               |
| #305 PDP resilience/trust           | `11f2f71…`                      | **yes**               |
| #311 search RSC boundary            | `c291a3c…`                      | **yes**               |
| #330 PDP digest `1378788464` hotfix | `619c994…` (merge commit = tip) | **yes**               |

---

## 3. Preflight gates (on `619c994`)

| Gate                               | Result                                                             |
| ---------------------------------- | ------------------------------------------------------------------ |
| `pnpm --filter customer lint`      | **PASS**                                                           |
| `pnpm --filter customer typecheck` | **PASS**                                                           |
| `pnpm --filter customer test`      | **PASS** — 63 files / 340 tests                                    |
| `pnpm --filter customer build`     | **PASS** (with `NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com`) |

### Production env (key presence / live inference only)

| Check                                               | Result                                                                       |
| --------------------------------------------------- | ---------------------------------------------------------------------------- |
| API base in live HTML                               | `https://api.vergeo5.com` present on search/PLP payloads — **not** localhost |
| Localhost in scanned route HTML                     | **absent** on homepage / categories / search / PDP / cart / sell probes      |
| `NEXT_PUBLIC_*` secret-shaped assignments in HTML   | **none** observed                                                            |
| Sell / vendor CTA                                   | `/en/sell` honest **invite-only** seller beta; no `localhost:3001`           |
| Payment / `public_launch` / migrations this session | **none**                                                                     |
| `vercel env ls` / CLI deploy auth                   | **BLOCKED** — no credentials (`vercel whoami` → no token)                    |

Quality gates **PASS**. Deploy path **BLOCKED_EXTERNAL**.

---

## 4. Deploy attempt

| Action                                            | Result                                                                                                                                                                                 |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Git-integrated Production deploy of tip `619c994` | **BLOCKED_EXTERNAL** — GitHub status `Vercel – convergeo-customer`: _“Deployment rate limited — retry in 24 hours.”_ (`updated_at` `2026-07-19T15:24:53Z`, coincident with #330 merge) |
| CLI `vercel --prod`                               | **BLOCKED_EXTERNAL** — no `VERCEL_TOKEN`                                                                                                                                               |
| Promote Preview                                   | **Not done** (forbidden)                                                                                                                                                               |
| Vendor / admin / API / DB / n8n / flags           | **Not touched**                                                                                                                                                                        |

**No new deployment ID/time.** Production aliases remain on `dpl_CA2qcVXs…` @ `28f565c`.

---

## 5. Live acceptance probes (current production @ `28f565c` — not tip)

These are **baseline** probes of the still-live production SHA. They are **not** acceptance of candidate `619c994` (undeployed).

| Route                        | HTTP | Digests / notes                                                 |
| ---------------------------- | ---- | --------------------------------------------------------------- |
| `/en`, `/fr`, `/zh`          | 200  | No former digests; no localhost in HTML                         |
| `/en\|fr\|zh/categories`     | 200  | Digest `3012388270` **absent**                                  |
| `/en\|fr\|zh/search?q=phone` | 200  | Digest `3273208722` **absent**; `api.vergeo5.com` present       |
| `/en\|fr/p/tecno-spark-20`   | 200  | Digest **`1378788464` PRESENT** — P0 still live                 |
| `/zh/p/tecno-spark-20`       | 200  | Digest not embedded in this sample (en/fr fail; tip undeployed) |
| `/en\|fr/p/itel-a70`         | 200  | Digest **`1378788464` PRESENT**                                 |
| `/zh/p/itel-a70`             | 200  | Digest not embedded in this sample                              |
| `/en/c/electronics`          | 200  | PLP OK                                                          |
| `/en/compare`, `/en/cart`    | 200  | Honest empty shells                                             |
| `/en/sell`                   | 200  | Invite-only CTA (honest)                                        |

**Candidate tip acceptance:** **not runnable on production** until a Production deploy of `619c994` succeeds. Local smoke of the hotfix was previously recorded in `pdp-1378788464-root-cause.md` (not a substitute for live Production acceptance).

---

## 6. Rollback

| Rule                                                          | Status                                                                                                                                                             |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Roll back only if newly deployed candidate fails acceptance   | **N/A** — no new deploy                                                                                                                                            |
| Do not use `dpl_7FsK2sJa…`                                    | **Honoured**                                                                                                                                                       |
| Recorded previous READY production (if a future deploy fails) | Prefer immediate pre-deploy production (`dpl_CA2qcVXs…` once tip ships), else `dpl_ANpPCb…` @ `1322c97` — **not** independently proven free of digest `1378788464` |

---

## 7. Remaining blockers

1. **BLOCKED_EXTERNAL — Vercel free-tier deploy rate limit** on `convergeo-customer` (retry ~24h from `15:24:53Z` status).
2. **BLOCKED_EXTERNAL — no agent `VERCEL_TOKEN`** for CLI/API Production deploy or Instant Rollback.
3. **Live PDP P0** on current production (`28f565c`): digest `1378788464` still present on Tecno/Itel en/fr PDPs until tip `#330` / `619c994` is Production-deployed and re-probed.
4. Deployment Protection / share-bypass still required for unauthenticated browser QA.

---

## 8. Conclusion

### Customer controlled-beta: **NO-GO**

| Field                      | Value                                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Deployed SHA               | **none** (production remains `28f565c`)                                                                        |
| Candidate SHA ready in git | `619c994` (#330 + required ancestors)                                                                          |
| Route evidence             | Discovery OK on live prod; PDP digest `1378788464` still live on en/fr Tecno/Itel; tip not production-deployed |
| Remaining blockers         | Vercel rate limit + missing deploy credentials; live PDP P0 until tip ships                                    |

**Founder next step:** After rate-limit reset (or with a provisioned `VERCEL_TOKEN`), Production-deploy customer from `619c994` with Production env, then re-run the acceptance matrix in §5 against the new `buildId` (gallery indicator visible; digests `3012388270` / `3273208722` / `1378788464` absent).
