# Customer production release evidence — 2026-07-19 (session 2)

**Role:** Convergeo Customer Production Release Manager  
**Scope:** Customer Vercel app only (`convergeo-customer` / `prj_lK6jnhAfVmhtaDZdMsIUF7LswgTP`). No vendor/admin/API/n8n/DB, no migrations, no payment/`public_launch` flag changes, no source patches during release.  
**Verdict:** **NO-GO** for controlled customer beta — tip Production deploy blocked; live PDP conversion path unusable; Instant Rollback required but **not executable** from this agent.

This pack does **not** claim real-money readiness or open-launch readiness.

---

## 1. Release identity

| Item                                  | Value                                                                                                                                                                          |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Candidate master SHA (preflight tip)  | `a99777ab11d6f4ff1094e1a2d2406245c0d91a5e` — merge #327 vision-audit Wave-1 evidence                                                                                           |
| Currently deployed production         | `dpl_CA2qcVXsCGnaorKCyr1onybCqszs` @ `28f565cbf55b78cbd7fd1074de9e50615b8a18d1` (#319 docs wave-2 runbook)                                                                     |
| Production aliases                    | `www.vergeo5.com`, `vergeo5.com`, `convergeo-customer.vercel.app`, `convergeo-customer-vergeo-projects.vercel.app`, `convergeo-customer-git-master-vergeo-projects.vercel.app` |
| Production health `buildId`           | `28f565cbf55b78cbd7fd1074de9e50615b8a18d1` (`GET /en/health` → `env=production`)                                                                                               |
| Previous production (rollback target) | `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` @ `8928d6ef13266e8831e4ce760552f6d83e3d502c` (#312 SEO) — still READY, `isRollbackCandidate: true`                                          |
| Deployed by this release manager?     | **No** — tip deploy blocked (rate limit + no `VERCEL_TOKEN`)                                                                                                                   |
| Commits on tip not in production      | Includes #320–#327; customer-relevant: #322 PDP/search soft-404, #321 sitemap root, #324 API UUID lookup (API out of scope for this release)                                   |

Inspector (current prod): https://vercel.com/vergeo-projects/convergeo-customer/CA2qcVXsCGnaorKCyr1onybCqszs  
Inspector (rollback target): https://vercel.com/vergeo-projects/convergeo-customer/7FsK2sJaNsRMzTy6DTpeMP9yect3  
Ephemeral hostname (current prod): `https://convergeo-customer-fjc2muxye-vergeo-projects.vercel.app`

---

## 2. Required merge ancestry

Fetched `origin/master` at session start. All four required merges are ancestors of tip `a99777a` **and** of currently aliased production `28f565c`:

| PR                                     | Merge SHA                                  | Ancestor of tip `a99777a` | Ancestor of prod `28f565c` |
| -------------------------------------- | ------------------------------------------ | ------------------------- | -------------------------- |
| #298 categories server/client boundary | `b17c311c857b9b610b0a8003e291c81ad2da1e15` | yes                       | yes                        |
| #302 Live Beta Wave 1                  | `d2e940b424b686c72b69e86b352982b361080f03` | yes                       | yes                        |
| #305 PDP repair                        | `11f2f7126fc8d01a75928f4cc3ed795fa9825c03` | yes                       | yes                        |
| #311 search server/client boundary     | `c291a3c6f8ef63c015702be4a64331d19e58815d` | yes                       | yes                        |

Former digests under watch: categories `3012388270`, search `3273208722`.  
Live PDP P0 digest observed this session: `1378788464` (gallery `indicator` function → Client Component).

**Tip caveat (no patch applied):** tip `page.tsx` still passes `indicator: (current, total) => t(...)` into a client tree (`apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx` ~L544). A tip Production deploy alone is **not** proven to clear digest `1378788464`; soft-404 fixes (#322) are on tip but **not** the indicator serialization boundary.

---

## 3. Phase 1 — Preflight gates (on `a99777a`)

| Gate                               | Result                                                                                                                                                           |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm --filter customer lint`      | **PASS** (exit 0)                                                                                                                                                |
| `pnpm --filter customer typecheck` | **PASS** (exit 0)                                                                                                                                                |
| `pnpm --filter customer test`      | **PASS** — 61 files / 332 tests                                                                                                                                  |
| `pnpm --filter customer build`     | **PASS** (exit 0; known CSS `@keyframes` comma warning; local SSR `categories.load_failed` without live API; `metadataBase` localhost warning during static gen) |

### Production env (key presence only — no secret values)

| Check                                                  | Result                                                                                                                                              |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vercel env ls` / CLI auth                             | **BLOCKED** — no `VERCEL_TOKEN`; `vercel whoami` → no credentials; REST create-deploy → `missingToken`                                              |
| API base (from live HTML)                              | `https://api.vergeo5.com` present in search SSR payload — **not** localhost                                                                         |
| Vendor / sell CTA                                      | `/en/sell` honest **invite-only seller beta**; no `localhost:3001` in HTML                                                                          |
| `NEXT_PUBLIC_*` secret-shaped assignments in HTML      | **None** observed in scanned payloads                                                                                                               |
| Payment / `public_launch` / migrations in this release | **None** intended or performed                                                                                                                      |
| Browser console `localhost:8888/cart-1`                | Observed on protected sessions (devtools/extension-class noise); **not** treated as Production `NEXT_PUBLIC_API_BASE_URL` (API host verified above) |

Preflight quality gates **PASS**. Deploy credentials / rate-limit are Phase-2 blockers (below), not code-gate failures.

---

## 4. Phase 2 — Production deployment

| Action                                                     | Result                                                                                                                                                                                      |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deploy tip `a99777a` with Production env (git integration) | **BLOCKED** — GitHub commit status `Vercel – convergeo-customer`: _“Deployment rate limited — retry in 24 hours.”_ (`upgradeToPro=build-rate-limit`), status updated `2026-07-19T14:09:29Z` |
| Same rate limit on related tip SHAs                        | Also failed for `b47436d`, `a9d30aa`, `05d3cf7`                                                                                                                                             |
| CLI `vercel --prod`                                        | **BLOCKED** — no credentials                                                                                                                                                                |
| Promote Preview (e.g. `dpl_KwWpsn…` @ `8ef7bf9`)           | **Not done** (forbidden — Preview env vars)                                                                                                                                                 |
| Source patch / empty commit to re-trigger                  | **Not done** (release rule: no source patches)                                                                                                                                              |
| Vendor / admin / API / migrations / payment flags          | **Not touched**                                                                                                                                                                             |

**Deployed SHA this session:** _(none — production remains `28f565c` / `dpl_CA2qcVXs…`)_  
**Previous SHA kept available for rollback:** `dpl_7FsK2sJa…` @ `8928d6e…` (READY).

---

## 5. Phase 3 — Live verification (production aliases @ `28f565c`)

Artifacts: `/opt/cursor/artifacts/customer-production-release-2026-07-19/`  
(`01-en-categories.webp` … `12-mobile-390px-categories.webp`, plus console captures)

Share-bypass used for browser QA (Deployment Protection). HTTP probes also used `web_fetch_vercel_url` + direct HTTPS.

### 5.1 Categories (en / fr / zh)

| Route            | HTTP    | Digest `3012388270` | Content                                                      |
| ---------------- | ------- | ------------------- | ------------------------------------------------------------ |
| `/en/categories` | **200** | **absent**          | Populated (~148 `/en/c/` links; departments + subcategories) |
| `/fr/categories` | **200** | **absent**          | Populated (FR H1 / tree)                                     |
| `/zh/categories` | **200** | **absent**          | Populated (ZH H1 / tree)                                     |

Browser: PASS — populated, not broken; mobile ~390px shows All Categories bottom nav + cart chrome (`12-mobile-390px-categories.webp`).

### 5.2 Search `?q=phone` (en / fr / zh)

| Route                | HTTP    | Digest `3273208722` | Content                                           |
| -------------------- | ------- | ------------------- | ------------------------------------------------- |
| `/en/search?q=phone` | **200** | **absent**          | Results (browser ~11; HTML product hrefs present) |
| `/fr/search?q=phone` | **200** | **absent**          | Results                                           |
| `/zh/search?q=phone` | **200** | **absent**          | Results                                           |

State distinction (en): `q=phone` → results; `q=zzzxqnonexistent999` → honest zero-results copy; empty `q` → distinct non-results shell (no former digest crash).

### 5.3 Homepage / PLP / PDP / compare / cart / sell

| Route                  | Result   | Notes                                                                                                                                                                                |
| ---------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/en`                  | **PASS** | Hero + escrow strip + category tiles; no localhost in HTML                                                                                                                           |
| `/en/c/electronics`    | **PASS** | Listing cards present (~22 product hrefs)                                                                                                                                            |
| `/en/p/tecno-spark-20` | **FAIL** | Browser: branded _“Something went wrong”_ (`08-product-500-error.webp`). Runtime logs + HTML embed digest **`1378788464`** (`indicator: function indicator`). Conversion UX unusable |
| `/en/p/itel-a70`       | **FAIL** | Same digest family in runtime logs / HTML                                                                                                                                            |
| `/en/compare`          | **PASS** | Empty/honest shell                                                                                                                                                                   |
| `/en/cart`             | **PASS** | Empty cart; no localhost in HTML                                                                                                                                                     |
| `/en/sell`             | **PASS** | Honest invite-only seller beta — not fake payment-success; not open public signup                                                                                                    |

Raw i18n: `catalog.*` keys appear in RSC/message payloads but **not** as visible text nodes on checked routes. No `nav.home` leak in browser.

No fake payment-success or verified-vendor claims observed on checked conversion surfaces.

### 5.4 Browser / runtime P0 signals

| Signal                                     | Status                                                                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Former digests `3012388270` / `3273208722` | **Not observed** on live categories/search (en/fr/zh)                                                                    |
| PDP digest `1378788464`                    | **Observed** — Vercel runtime errors on `/[locale]/p/[slug]` (latest sample `14:30:31Z` this session); P0 for conversion |
| Homepage `INVALID_MESSAGE` cluster         | High volume on `/[locale]` (i18n) — remaining beta debt; not the former categories/search digests                        |
| Search `SEARCH_KINDS` / `3273208722`       | Historical cluster last seen on older deployment `dpl_ANpPCb…`; **not** reproducing on current aliased prod probes       |
| Console                                    | CSP noise; `localhost:8888/cart-1` ERR_FAILED on browser sessions                                                        |
| Deployment Protection                      | Unauthenticated browsers hit Vercel login wall; share-bypass / `web_fetch_vercel_url` required for QA                    |

---

## 6. Rollback

| Step                   | Status                                                                                                                                                                                                           |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rule trigger           | **Met** — core PDP conversion unusable (digest `1378788464` / error UI)                                                                                                                                          |
| Target                 | `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` @ `8928d6e…` (previous READY production)                                                                                                                                      |
| Agent execution        | **FAILED** — no Vercel OAuth/token; MCP has no promote/rollback tool; CLI unauthenticated                                                                                                                        |
| Founder action **now** | Instant Rollback / point aliases to `dpl_7FsK2sJa…` **or** wait for rate-limit reset and Production-deploy a tip that also fixes digest `1378788464` (code fix required — out of scope for this release session) |

Note: rolling back to `8928d6e` may restore an earlier PDP state but does **not** by itself prove a fixed gallery boundary; re-probe PDP after any alias change. Do **not** promote Preview builds to work around the rate limit.

---

## 7. Remaining issues (controlled beta)

1. **PDP gallery `indicator` Client Component boundary** — live digest `1378788464`; blocks browse→PDP; still present in tip source pattern (no patch in this release).
2. **Vercel free-tier deployment rate limit** — blocks tip Production builds (~24h from status); also blocks related customer git deploys.
3. **No agent `VERCEL_TOKEN`** — cannot deploy, env-list, promote, or Instant Rollback from this environment.
4. **Homepage `INVALID_MESSAGE` volume** — i18n runtime cluster on `/[locale]`.
5. **Deployment Protection** — share-bypass required for unauthenticated human QA.
6. **Seller CTA** — invite-only (honest); public vendor URL enablement remains founder OPS (VA-P04), not this release.
7. **Tip vs prod drift** — soft-404 / sitemap fixes on tip not Production-deployed.

---

## 8. Controlled-beta go / no-go

| Question                                                         | Answer                              |
| ---------------------------------------------------------------- | ----------------------------------- |
| Required PRs #298 / #302 / #305 / #311 on production?            | **Yes** (via `28f565c` and earlier) |
| Tip master Production-deployed this session with Production env? | **No** (rate limit + no token)      |
| Discovery journeys (categories + search) live OK?                | **Yes** (en/fr/zh)                  |
| Conversion-critical PDP usable?                                  | **No**                              |
| Rollback completed?                                              | **No** (auth blocked)               |
| Real-money / open-launch?                                        | **Not claimed**                     |

### **Controlled-beta: NO-GO**

Do not invite broader beta traffic until:

1. Instant Rollback restores a PDP-usable Production alias **or** a fresh Production deploy succeeds after the rate-limit window **and** includes a fix for digest `1378788464`, and
2. Re-probe `/en|/fr|/zh` categories + search (no former digests) **and** at least one valid PDP gallery path in a real browser session, and
3. Confirm no new P0 runtime errors on those routes.

---

## 9. Appendix — commands / probes (names only)

- Quality: `pnpm --filter customer lint|typecheck|test|build` on `a99777a`
- Ancestry: `git merge-base --is-ancestor` for PR merge SHAs; `gh pr view` merge commits
- Deploy status: GitHub commit statuses + Vercel MCP `list_deployments` / `get_deployment` / `get_runtime_errors` / `get_runtime_logs`
- HTTP probes: urllib/curl + `web_fetch_vercel_url` against `www.vergeo5.com`
- Browser: Vercel share URL + computer-use screenshots under `/opt/cursor/artifacts/customer-production-release-2026-07-19/`
- Health: `GET /en/health` → `buildId=28f565c…`
