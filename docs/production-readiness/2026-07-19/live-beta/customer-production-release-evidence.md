# Customer production release evidence — 2026-07-19

**Role:** Convergeo Customer Production Release Manager  
**Scope:** Customer Vercel app only (`convergeo-customer`). No vendor/admin/API/n8n/DB, no migrations, no payment/`public_launch` flag changes, no source patches during release.  
**Verdict:** **NO-GO** for controlled customer beta promotion beyond what is already live — tip deploy blocked; live PDP conversion path unusable on `www`; Instant Rollback attempted but **not completed** (no Vercel dashboard/CLI credentials in this agent).

This pack does **not** claim real-money readiness or open-launch readiness.

---

## 1. Release identity

| Item                                               | Value                                                                                                                                                                                          |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Preflight candidate (session start tip)            | `b2f6ebbcec3f4f5c9e065bb6aa1862877377a52b` — merge #315 discovery progressive load                                                                                                             |
| Master tip at evidence write                       | `b47436df1650d8dee8e2157e6824a4d27964f14e` — merge #322 PDP/search soft-404 (ahead of candidate; **not** production-deployed — rate limited)                                                   |
| Production **before** this session’s deploy window | `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` @ `8928d6ef13266e8831e4ce760552f6d83e3d502c` (#312 SEO)                                                                                                     |
| Production **observed during verification**        | `dpl_CA2qcVXsCGnaorKCyr1onybCqszs` @ `28f565cbf55b78cbd7fd1074de9e50615b8a18d1` (#319 docs wave-2 runbook) — **aliases:** `www.vergeo5.com`, `vergeo5.com`, `convergeo-customer.vercel.app`, … |
| Rollback target (previous READY production)        | `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` @ `8928d6e…` (also prior candidate `dpl_ANpPCbDPGLEeyHy1h6EbEs5hzQY8` @ `1322c97…`)                                                                         |
| Intentionally deployed by this release manager?    | **No** — tip `b2f6ebb` / `b47436d` blocked; #319 landed via git auto-deploy outside this agent’s CLI action                                                                                    |

Inspector (current prod): https://vercel.com/vergeo-projects/convergeo-customer/CA2qcVXsCGnaorKCyr1onybCqszs  
Inspector (rollback target): https://vercel.com/vergeo-projects/convergeo-customer/7FsK2sJaNsRMzTy6DTpeMP9yect3

---

## 2. Required merge ancestry

Fetched `origin/master`. Confirmed required merges are ancestors of both the preflight candidate and the currently aliased production SHA `28f565c…`:

| PR                                     | Merge SHA (short) | Ancestor of `b2f6ebb` | Ancestor of prod `28f565c` |
| -------------------------------------- | ----------------- | --------------------- | -------------------------- |
| #298 categories server/client boundary | `b17c311…`        | yes                   | yes                        |
| #302 Live Beta Wave 1                  | `d2e940b…`        | yes                   | yes                        |
| #305 PDP repair                        | `11f2f71…`        | yes                   | yes                        |
| #311 search server/client boundary     | `c291a3c…`        | yes                   | yes                        |

Former digests under watch: categories `3012388270`, search `3273208722`.

---

## 3. Phase 1 — Preflight gates (on `b2f6ebb`)

| Gate                               | Result                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `pnpm --filter customer lint`      | **PASS** (exit 0)                                                                                             |
| `pnpm --filter customer typecheck` | **PASS** (exit 0)                                                                                             |
| `pnpm --filter customer test`      | **PASS** — 57 files / 311 tests                                                                               |
| `pnpm --filter customer build`     | **PASS** (exit 0; known CSS `@keyframes` comma warning + local SSR `categories.load_failed` without live API) |

### Production env (key presence only)

| Check                                                  | Result                                                                                                                                                                                                            |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vercel env ls` / `env pull` from this agent           | **BLOCKED** — CLI has no credentials (`vercel login` device flow only)                                                                                                                                            |
| Inference from live SSR behaviour                      | Categories/search/PLP hydrate against live catalogue (not empty fail-closed) ⇒ Production `NEXT_PUBLIC_API_BASE_URL` (or equivalent) is **not** localhost for server render                                       |
| `NEXT_PUBLIC_*` secrets                                | No secret-shaped `NEXT_PUBLIC_*` keys observed in HTML/JS payload scans; cannot dump Production env names without auth                                                                                            |
| Sell / vendor URL                                      | `/en/sell` shows **invite-only seller beta** (honest gating). No `localhost:3001` in page HTML. Full public `NEXT_PUBLIC_VENDOR_APP_URL` enablement remains a founder OPS item (VA-P04), not part of this release |
| Payment / `public_launch` / migrations in this release | **None** intended or performed by this session                                                                                                                                                                    |

Preflight quality gates **PASS**. Env listing incomplete due to missing Vercel token — not treated as a code-gate failure, but recorded as an ops gap.

---

## 4. Phase 2 — Production deployment

| Action                                                         | Result                                                                                                                                                                                          |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deploy tip `b2f6ebb` / later tip `b47436d` with Production env | **BLOCKED** — GitHub commit status `Vercel – convergeo-customer`: _“Deployment rate limited — retry in 24 hours.”_ (`upgradeToPro=build-rate-limit`), observed ~11:56Z and again ~13:27Z on tip |
| Promote Preview (`dpl_KwWpsn…` @ `8ef7bf9`)                    | **Not done** (forbidden — Preview env)                                                                                                                                                          |
| CLI `vercel --prod`                                            | **BLOCKED** — no credentials                                                                                                                                                                    |
| Concurrent production change                                   | Docs merge **#319** (`28f565c`) **did** create `dpl_CA2qcVXs…` with `target=production` and took `www.vergeo5.com` aliases while this session was in preflight/verify                           |

**Rollback status:** Instant Rollback to `dpl_7FsK2sJa…` **REQUIRED by rule** after PDP failure evidence, **NOT EXECUTED** — dashboard/CLI auth unavailable to the agent. Founder/on-call must promote `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` (or a later known-good Production build) immediately.

---

## 5. Phase 3 — Live verification

Artifacts: `/opt/cursor/artifacts/customer-production-release/`  
(`categories-en.webp`, `categories-mobile.webp`, `search-phone-en.webp`, `home-en.webp`, `pdp-tecno-error.webp`, `cart-en.webp`, `sell-en.webp`)

### 5.1 Categories (en / fr / zh)

| Route            | HTTP    | Digest `3012388270` | Content                                                       |
| ---------------- | ------- | ------------------- | ------------------------------------------------------------- |
| `/en/categories` | **200** | **absent**          | Populated (~74 category links; e.g. Groceries & Staples tree) |
| `/fr/categories` | **200** | **absent**          | Populated (localised H1)                                      |
| `/zh/categories` | **200** | **absent**          | Populated (localised H1)                                      |

Browser (share-bypass): PASS — departments/subcategories visible; mobile ~390px shows All Categories + cart.

### 5.2 Search `?q=phone` (en / fr / zh)

| Route                | HTTP    | Digest `3273208722` | Content                                            |
| -------------------- | ------- | ------------------- | -------------------------------------------------- |
| `/en/search?q=phone` | **200** | **absent**          | Results (browser: 11; curl: product hrefs present) |
| `/fr/search?q=phone` | **200** | **absent**          | Results                                            |
| `/zh/search?q=phone` | **200** | **absent**          | Results                                            |

State distinction (en): `q=phone` → results; `q=zzzxqnonexistent999` → zero-results copy; empty `q` → distinct non-results shell (not the former digest crash).

### 5.3 Homepage / PLP / PDP / compare / cart / sell

| Route                  | Result                                        | Notes                                                                                                                                                                                                                                                                                                              |
| ---------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/en`                  | **PASS**                                      | Hero + escrow strip + category tiles; no localhost in HTML                                                                                                                                                                                                                                                         |
| `/en/c/electronics`    | **PASS**                                      | Listing cards present                                                                                                                                                                                                                                                                                              |
| `/en/p/tecno-spark-20` | **FAIL**                                      | Browser: branded error _“Something went wrong”_ (screenshot `pdp-tecno-error.webp`). Runtime logs: `Functions cannot be passed directly to Client Components` … `indicator: function indicator` → digest **`1378788464`**. Curl HTML often **200** with digest embedded (soft RSC failure); conversion UX unusable |
| `/en/p/itel-a70`       | **FAIL** (same digest family in runtime logs) |                                                                                                                                                                                                                                                                                                                    |
| `/en/compare`          | **PASS** (empty/honest shell)                 |                                                                                                                                                                                                                                                                                                                    |
| `/en/cart`             | **PASS**                                      | Empty cart; no localhost in HTML                                                                                                                                                                                                                                                                                   |
| `/en/sell`             | **PASS** (honest invite-only)                 | Not fake payment-success; not claiming open public signup                                                                                                                                                                                                                                                          |

Raw i18n: `catalog.*` keys appear in RSC/message payloads but **not** as visible text nodes on checked routes. No `nav.home` leak observed.

Mobile All Categories + cart chrome: **PASS** on categories (screenshot `categories-mobile.webp`).

### 5.4 Browser / runtime P0 signals

| Signal                                     | Status                                                                                                                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Former digests `3012388270` / `3273208722` | **Not observed** on live categories/search                                                                                                                               |
| New PDP digest `1378788464`                | **Observed** — P0 for conversion                                                                                                                                         |
| Console                                    | CSP noise; **`localhost:8000` `ERR_FAILED`** for cart/healthz from browser client — fail-closed SSR does not fully prevent client probing; treat as remaining beta issue |
| Vercel runtime errors (production, sample) | PDP `indicator` function → Client Component serialization error on aliased production traffic                                                                            |

---

## 6. Rollback

| Step            | Status                                                                   |
| --------------- | ------------------------------------------------------------------------ |
| Rule trigger    | **Met** — core PDP conversion unusable / error UI                        |
| Target          | `dpl_7FsK2sJaNsRMzTy6DTpeMP9yect3` @ `8928d6e…`                          |
| Agent execution | **FAILED** — no Vercel OAuth/token in environment                        |
| Founder action  | Instant Rollback / Promote that deployment to Production aliases **now** |

Note: tip `b47436d` (#322) may address search→PDP soft-404s but is **rate-limited** from deploying; do not promote Preview builds to work around the limit.

---

## 7. Remaining issues (controlled beta)

1. **PDP gallery labels / client boundary (`indicator` function)** — live digest `1378788464`; blocks browse→PDP.
2. **Vercel deployment rate limit** — blocks tip Production builds (~24h retry); also blocked #322 customer deploy.
3. **Client `localhost:8000` fetches** in browser console on protected sessions.
4. **Deployment Protection** — unauthenticated browsers hit Vercel login wall; share-bypass/`web_fetch_vercel_url` required for human QA.
5. **Seller CTA** — invite-only (honest); public vendor URL enablement still founder OPS.
6. **“Verified” wording** in catalogue chrome — continue honesty review (demo vs KYC-verified).
7. **Agent cannot manage Vercel env/deploy/rollback** without a provisioned `VERCEL_TOKEN` (or equivalent).

---

## 8. Controlled-beta go / no-go

| Question                                                            | Answer                                        |
| ------------------------------------------------------------------- | --------------------------------------------- |
| Required PRs #298 / #302 / #305 / #311 on production?               | **Yes** (via `28f565c` and earlier `8928d6e`) |
| Tip master Production-deployed by this release with Production env? | **No** (rate limit)                           |
| Discovery journeys (categories + search) live OK?                   | **Yes** (en/fr/zh)                            |
| Conversion-critical PDP usable?                                     | **No**                                        |
| Rollback completed?                                                 | **No** (auth blocked)                         |
| Real-money / open-launch?                                           | **Not claimed**                               |

### **Controlled-beta: NO-GO**

Do not invite broader beta traffic until:

1. Instant Rollback restores a PDP-usable Production alias **or** a fresh Production deploy of a tip that fixes digest `1378788464` succeeds after the rate-limit window, and
2. Re-probe `/en|/fr|/zh` categories + search (no former digests) **and** at least one valid PDP gallery path in a real browser session, and
3. Confirm no new P0 runtime errors on those routes.

---

## 9. Appendix — commands / probes (names only)

- Quality: `pnpm --filter customer lint|typecheck|test|build` on `b2f6ebb`
- Deploy status: GitHub commit statuses + Vercel MCP `list_deployments` / `get_deployment` / `get_runtime_logs`
- HTTP probes: curl/urllib against `www.vergeo5.com` and deployment hostnames
- Browser: Vercel share URL + computer-use screenshots under `/opt/cursor/artifacts/customer-production-release/`
