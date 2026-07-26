# Customer production smoke — cart origin & Cloudinary images

**Purpose:** a focused, read-only smoke test for the two production failure classes
reported on the customer app — **cart-origin failures** (cart/search/PDP calling the
wrong origin) and **Cloudinary-image failures** (blank or fallback product images).
It names the environment variables that drive both, separates what is fixed in **code**
from what an **operator** must set/redeploy, and gives redacted pass/fail probes for the
critical funnel surfaces.

**Scope:** customer app (`apps/customer` on Vercel → `www.vergeo5.com`) + the API origin it
calls (`api.vergeo5.com`). Read-only. **No** env writes, **no** payment calls, **no** deploy
from this runbook — those steps are the operator's and are called out explicitly.

**Pairs with (does not duplicate):** `docs/ops/deploy-verify-runbook.md` (full deploy/rollback and
the `scripts/ops/verify_live.sh` gate matrix), `infra/vercel.md` (project settings),
`docs/ops/media-pipeline.md` (Cloudinary), `docs/ops/security-headers.md` (CSP/`connect-src`).

---

## 1. What actually breaks, and why

Both symptoms trace to **build-time public env** on the customer Vercel project. `NEXT_PUBLIC_*`
values are read by the browser bundle, and Next.js **inlines them at `next build`** — they are
not read at runtime in the browser. A wrong or missing value is therefore frozen into the
deployed JS until the next **rebuild + redeploy**.

### 1a. Cart-origin failures

The cart/search/PDP client calls the API through one resolver,
`apps/customer/lib/api-base-url.ts` → `resolveApiBaseUrl()` (and its `getApiBaseUrl()` /
`absoluteApiUrl()` helpers). The cart request builder is
`apps/customer/app/[locale]/(shop)/_components/cart/mini-cart-drawer.tsx` → `cartRequest()`,
which issues `fetch(\`${getApiBaseUrl()}${path}\`, { credentials: "include", … })`.

Two distinct origin failures are possible in production:

| #      | Trigger                                                                                                    | Browser behaviour                                                                                                                                                                                                                            | Class        |
| ------ | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **C1** | `NEXT_PUBLIC_API_BASE_URL` **missing/blank** in the build                                                  | `getApiBaseUrl()` returns `""` → `fetch("/cart")` is **relative**, so it hits the **customer origin** `https://www.vergeo5.com/cart` (Next 404 HTML) → `ApiError("unknown_error")`. **Never** localhost (the resolver fails closed in prod). | Wrong origin |
| **C2** | `NEXT_PUBLIC_API_BASE_URL` correct, but the **API `CORS_ORIGINS`** does not list the exact customer origin | Cross-origin credentialed request to `api.vergeo5.com` is **blocked by CORS** (no `Access-Control-Allow-Origin` reflected) → `TypeError: Failed to fetch` → `ApiError("network_error")`.                                                     | CORS         |

C2 is real because the cart sends `credentials: "include"` and the API sets
`allow_credentials=True` with an **explicit** origin list
(`services/api/app/main.py`; `settings.py` forbids `*` outside development). Credentialed CORS
requires the API to reflect the **exact** origin — `https://www.vergeo5.com` and
`https://vergeo5.com` are different origins; both apex and `www` must be listed if both serve.

### 1b. Cloudinary-image failures

Image URLs are built by `packages/ui/src/media/cloudinary-url.ts` → `resolveCloudName()`, which
reads `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`. When it is missing/blank, `cldUrl()` **soft-fails to
`""`** and both `CloudinaryImage` (client) and `CloudinaryImageStatic` (RSC) render a **labelled,
non-crashing fallback** (`data-testid="cloudinary-image-fallback"`, `role="img"`,
`aria-label`) instead of a broken `<img>`. So the production symptom is **every product
card/thumbnail showing the fallback tile** rather than a crash.

> Note: `infra/vercel.md`'s env table historically listed only Supabase + API vars. The
> **customer** project must also carry `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` — see §2.

---

## 2. Required environment variables

### 2a. Customer Vercel project — build-time (`NEXT_PUBLIC_*`, inlined at `next build`)

| Name                                                    | Drives                                                 | Read by                                          | Missing/blank in prod build ⇒                                              |
| ------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------ | -------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL`                              | API origin for cart/search/PDP/checkout                | `lib/api-base-url.ts`, `sw.ts`, `next.config.ts` | **C1** — relative fetch to customer origin (fails closed, never localhost) |
| `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`                     | Product image host (`res.cloudinary.com/<cloud>`)      | `packages/ui/.../cloudinary-url.ts`              | All product images render the labelled fallback tile                       |
| `NEXT_PUBLIC_SUPABASE_URL`                              | Browser Supabase client (auth token for cart/checkout) | `packages/auth/src/env.ts`                       | Browser client throws → cart auth attach + login break                     |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`                         | Browser Supabase client (anon key only)                | `packages/auth/src/env.ts`                       | As above                                                                   |
| `NEXT_PUBLIC_VENDOR_APP_URL`                            | "Sell on Vergeo5" CTA link                             | `.../sell/_components/vendor-app.ts`             | CTA fails closed to an unavailable state (never a localhost link)          |
| `NEXT_PUBLIC_VERGEO_ENV`, `NEXT_PUBLIC_VERGEO_BUILD_ID` | `/en/health` fingerprint (optional)                    | `app/[locale]/health/route.ts`                   | Health reports `env/buildId: "unknown"` (non-fatal)                        |

The production value for the current deployment is `NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com`
and `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=convergeo`. Never place server secrets (service role,
Lenco, Cloudinary **secret**) in `NEXT_PUBLIC_*`.

> **Do not confuse apps:** the **admin** app reads `NEXT_PUBLIC_VERGEO_API_URL`
> (`apps/admin/lib/api-base-url.ts`); the **customer** app reads `NEXT_PUBLIC_API_BASE_URL`.
> Setting the admin name on the customer project has no effect (C1).

### 2b. API host (Hetzner/OCI) — runtime (`infra/.env`, read per-process)

| Name             | Drives                                                       | Read by                                   | Wrong/missing ⇒                                               |
| ---------------- | ------------------------------------------------------------ | ----------------------------------------- | ------------------------------------------------------------- |
| `CORS_ORIGINS`   | Comma-separated allowlist of browser origins                 | `services/api/app/settings.py`, `main.py` | **C2** — cart/search fetches blocked by CORS                  |
| `CLOUDINARY_URL` | Server-side signing for uploads (not public image reads)     | `app/media/cloudinary_signing.py`         | Vendor uploads fail; **does not** affect public image display |
| `ENV`            | `development`/`staging`/`production`; gates the `*` CORS ban | `settings.py`                             | `*` allowed only in development                               |

`CORS_ORIGINS` for production must include every customer/vendor/admin origin that makes
credentialed calls, e.g. `https://www.vergeo5.com,https://vergeo5.com` (+ vendor/admin hosts).

---

## 3. Build-time vs runtime — the operator-critical distinction

| Layer                             | Variables                                                                 | When read                               | To change a value you must…                                                                                                                                  |
| --------------------------------- | ------------------------------------------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Customer browser bundle**       | all `NEXT_PUBLIC_*` + `NODE_ENV`                                          | **Build time** (`next build` on Vercel) | Edit env in Vercel **then trigger a new Production deploy/rebuild.** Editing the var alone does nothing — the old value stays inlined in the shipped chunks. |
| **Customer server (per request)** | `/en/health` fingerprint; `next.config.ts` `rewrites()` (analytics proxy) | Request/startup                         | New deploy picks it up.                                                                                                                                      |
| **API host**                      | `CORS_ORIGINS`, `CLOUDINARY_URL`, `ENV`, `INTERNAL_*`                     | **Runtime** on the VM                   | Edit `infra/.env` then **recreate** the container (`docker compose up -d api`), not a bare restart — see `deploy-verify-runbook.md` §2.1.                    |

**Why localhost can never leak in production:** `resolveApiBaseUrl()` only returns
`http://localhost:8000` when `NODE_ENV !== "production"`, and `getVendorAppUrl()` only returns
`http://localhost:3001` under the same condition. `next build` always compiles with
`NODE_ENV=production`, so a production bundle fails **closed** (relative same-origin / unavailable
state) rather than to a loopback. This is enforced by tests — see §6.

---

## 4. Redacted operator commands (read-only)

Run from an operator network with outbound access (agent sandboxes may be egress-blocked; a
`403 CONNECT` is the proxy, not an outage). None of these mutate state or send payments.

```bash
# --- API liveness -------------------------------------------------------------
curl -fsS https://api.vergeo5.com/healthz        # expect {"status":"ok"}
curl -fsS https://api.vergeo5.com/health         # alias, expect {"status":"ok"}

# --- CORS preflight for the cart (the C2 check) -------------------------------
# Simulates the browser's credentialed preflight from the customer origin.
curl -sS -i -X OPTIONS "https://api.vergeo5.com/cart" \
  -H "Origin: https://www.vergeo5.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  | grep -i "access-control-allow-"
# expect: access-control-allow-origin: https://www.vergeo5.com
#         access-control-allow-credentials: true

# --- Customer homepage: origin + image sanity ---------------------------------
curl -fsS https://www.vergeo5.com/en -o /tmp/home.html
grep -c 'localhost:8000' /tmp/home.html                       # expect 0  (C1 guard)
grep -oE 'res\.cloudinary\.com/[a-z0-9_-]+' /tmp/home.html | sort -u   # expect res.cloudinary.com/convergeo

# --- Reuse the shared verifier's localhost + health gates ---------------------
CHECK_LOCALHOST=1 CUSTOMER_URL=https://www.vergeo5.com \
  API_BASE_URL=https://api.vergeo5.com bash scripts/ops/verify_live.sh   # G1 + G2 rows
```

Cart add/remove and checkout entry are verified in a real browser (§5) — do **not** script
authenticated cart mutations or any payment call from this runbook.

---

## 5. Pass / fail checks

| #   | Surface               | Probe (redacted)                                                       | PASS                                                                                                     | FAIL ⇒ likely cause                                                                                                                                                          |
| --- | --------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **healthz**           | `curl -fsS …/healthz`                                                  | HTTP 200 `{"status":"ok"}`                                                                               | non-200/timeout ⇒ API down or Caddy upstream (deploy-verify §7)                                                                                                              |
| 2   | **CORS**              | OPTIONS preflight to `…/cart` with customer `Origin` (§4)              | `access-control-allow-origin` reflects the origin **and** `…-allow-credentials: true`                    | header absent ⇒ **C2**: add origin to API `CORS_ORIGINS`, recreate container                                                                                                 |
| 3   | **Homepage**          | `GET /en` HTML                                                         | 200; `res.cloudinary.com/convergeo` present; **0** `localhost:8000`                                      | fallback tiles / no cloudinary host ⇒ missing `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`; product rails empty ⇒ **C1/C2** (home fetches `/catalog/listings`)                        |
| 4   | **Search thumbnails** | `GET /en/search?q=phone` HTML                                          | 200; result cards carry `res.cloudinary.com/convergeo` `<img>`; no bulk fallback labels                  | every card shows fallback ⇒ missing cloud name; zero results / error tab ⇒ **C1/C2** on `/search`                                                                            |
| 5   | **PDP**               | `GET /en/p/tecno-spark-20` HTML                                        | 200; gallery `<img>` on `res.cloudinary.com/convergeo`; buyer-trust/escrow copy present; no error digest | blank gallery (only fallback) ⇒ cloud name; "Something went wrong" ⇒ separate PDP RSC digest (`docs/production-readiness/2026-07-19/live-beta/pdp-1378788464-root-cause.md`) |
| 6   | **Cart add/remove**   | Browser + DevTools Network: add then remove an item                    | requests go to `https://api.vergeo5.com/cart*`, HTTP 200, response carries `Access-Control-Allow-Origin` | request URL is `www.vergeo5.com/cart` ⇒ **C1**; blocked/red in console ⇒ **C2**; 401 loop ⇒ missing `NEXT_PUBLIC_SUPABASE_*`                                                 |
| 7   | **Checkout entry**    | Browser: open `/en/checkout` with a non-empty cart (no payment submit) | page 200; contact/fulfilment step renders; cart total shown                                              | crash/blank ⇒ upstream cart fetch failed (**C1/C2**); do not proceed to payment for this smoke                                                                               |

A green row on 1–7 clears the two reported failure classes for the deployed build. Rows 3–5 are
scriptable read-only; rows 6–7 are manual browser checks (kept read-only — no mutation scripted).

---

## 6. What is guaranteed by code vs by the operator

### Code (shipped in this change — proven by tests)

- **Localhost is impossible in a production browser build.**
  - `apps/customer/lib/api-base-url.test.ts` — production matrix (var absent/undefined/empty/
    whitespace) asserts `resolveApiBaseUrl → null`, `getApiBaseUrl → ""`, `absoluteApiUrl → null`,
    none matching `localhost`; loopback default only under non-production `NODE_ENV`.
  - `apps/customer/lib/no-localhost-in-browser-build.test.ts` — scans **every** browser-reachable
    customer source file and fails if any loopback literal exists outside the two audited,
    `NODE_ENV`-guarded resolvers (`api-base-url.ts`, `vendor-app.ts`). Catches a future
    `fetch("http://localhost…")` before it can ship.
- **A missing Cloudinary cloud name renders a visible, non-crashing fallback.**
  - `packages/ui/src/media/cloudinary-image.test.tsx` (client) and
    `cloudinary-image-static.test.tsx` (RSC) — with the cloud name unset, no throw, no `<img>`,
    and a labelled `role="img"` fallback renders; `cloudinary-url.test.ts` proves `cldUrl()`
    soft-fails to `""`.

These prove the app **degrades safely**. They do **not** and cannot assert that the correct
production values are set — that is operator work below.

### Operator (staging/production — not doable from code)

1. Set `NEXT_PUBLIC_API_BASE_URL=https://api.vergeo5.com` and
   `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME=convergeo` (+ Supabase public vars) on the **customer**
   Vercel project, then **trigger a Production redeploy** (build-time inlining — §3).
2. Ensure API `CORS_ORIGINS` on the VM lists the exact customer origin(s); **recreate** the
   container after editing `infra/.env`.
3. Run §4/§5. Record evidence under `docs/production-readiness/<date>/`.
4. Rollback if a row fails: `deploy-verify-runbook.md` §3.3 (Vercel) / §2.3 (API).

Live probes and any real cart mutation must be executed by the operator against production;
this runbook does not claim live results and none are asserted here without recorded evidence.

---

## 7. Cross-references

- `docs/ops/deploy-verify-runbook.md` — deploy/rollback + `verify_live.sh` gate matrix (G1/G2).
- `infra/vercel.md` — Vercel project settings + env names.
- `docs/ops/media-pipeline.md` — Cloudinary pipeline and signing.
- `docs/ops/security-headers.md` — CSP; `connect-src`/`img-src` must allow the API + `res.cloudinary.com`.
- `docs/production-readiness/2026-07-19/live-beta/pdp-1378788464-root-cause.md` — distinct PDP RSC digest (not cart/Cloudinary).
