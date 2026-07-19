# Live Beta Experience Audit — 2026-07-19

**Role:** Convergeo Live Beta Product & Experience Release Lead  
**Mode:** Safe read-only probes + headed browser inspection  
**Repo tip audited:** `6841b1e` (master)  
**Production customer deploy:** `dpl_9uNbPuvwmuWPGZUTZMm564BaVRHW` @ `cc4a824` (pre–categories fix)  
**Decision context:** Staging provisioning paused; goal = useful controlled customer beta without weakening production safety.

---

## Verdict

| Surface  | Live usefulness for invite/demo beta                                   | Blocking UX defects                                                                   |
| -------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Customer | **Conditional** — browse/PDP/cart work; discovery broken on tip deploy | `/categories` **500**; seller CTA unavailable (env); demo imagery + “Verified” badges |
| Vendor   | Login shell OK; deeper UX needs auth                                   | Fail-closed API base still incomplete in many clients                                 |
| Admin    | Access-gated (healthy)                                                 | `/moderation` and `/config` nav hubs 404                                              |
| API      | `/healthz` `/readyz` OK; catalog/search respond                        | Money/KYC routes not launch-cleared (known)                                           |

**Real-money / open launch:** remains **NO-GO** (unchanged from `production-go-no-go.md`).  
**Invite/demo browse (no real money):** viable after Wave 1 deploy + categories promotion + honest copy gates.

---

## Method (read-only)

| Method                                       | Evidence                                                                  |
| -------------------------------------------- | ------------------------------------------------------------------------- |
| `curl -L` HTTP probes                        | customer / vendor / admin / API hosts                                     |
| Vercel `list_deployments`                    | production still on `cc4a824`; #298 not promoted                          |
| Headed browser (desktop ~1280 + mobile ~390) | homepage, categories, PLP, PDP, search, cart, sell, compare, vendor login |
| Code cross-check on master                   | categories fix present; localhost residuals; nav IA                       |

Screenshots (agent host): `/tmp/computer-use/*.webp` from the browser audit session.

---

## Fingerprint (redacted)

| Item                           | Value                                                                                    |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| Customer prod                  | `www.vergeo5.com` → deploy `dpl_9uNb…` / SHA `cc4a824`                                   |
| Categories fix on master       | #298 / `b17c311` (+ tip `6841b1e`) — **not** on production aliases                       |
| Vendor                         | `vendor.vergeo5.com` health/login **200**                                                |
| Admin                          | `admin.vergeo5.com` → Cloudflare Access challenge                                        |
| API                            | `api.vergeo5.com` health **200**; `/catalog/listings` **200**; `/search?q=phone` **200** |
| Feature flags (prior evidence) | `public_launch=false`, `zamtel_collections=false`                                        |
| Money aggregates (prior)       | payments/orders/ledger = 0; `0056` unapplied                                             |

---

## Route integrity (customer production)

| Route                                         | HTTP       | Notes                                                                   |
| --------------------------------------------- | ---------- | ----------------------------------------------------------------------- |
| `/en`                                         | 200        | Hero, category tiles, rails, escrow band                                |
| `/en/health`                                  | 200        | `{"status":"ok","app":"customer"}`                                      |
| `/en/categories` (en/fr/zh)                   | **500**    | Digest `3012388270` — deploy drift vs #298                              |
| `/en/c/electronics`                           | 200        | 22 listings; demo/placeholder imagery                                   |
| `/en/p/tecno-spark-20`                        | 200        | Buy box works; placeholder gallery                                      |
| `/en/search` and `?q=phone`                   | 200 (curl) | Browser once showed 500 — treat as residual risk; harden unavailable UI |
| `/en/cart`                                    | 200        | Honest empty state                                                      |
| `/en/compare`                                 | 200        | Honest empty; no invented data                                          |
| `/en/sell`                                    | 200        | CTA “temporarily unavailable” (CUST-01 env)                             |
| `/en/events`, `/en/directory`, `/en/services` | 200        | Reachable from home                                                     |
| `/en/privacy`, `/en/terms`                    | 404        | Canonical paths are `/en/legal/*` (footer correct)                      |
| `/en/legal/privacy                            | terms      | returns`                                                                | 200 | OK  |
| `localhost:` in HTML                          | **0**      | G2 localhost PASS on sampled pages                                      |

---

## Marketplace-quality evaluation

### Mobile-first visual quality

**Strengths:** Mobile homepage stacks cleanly; bottom nav present; escrow band readable; design tokens coherent.  
**Gaps:** Bottom nav has **duplicate Account destinations** (Orders + Account both → `/account`); **no Categories entry** on mobile despite desktop mega-menu; product imagery is demo/placeholder (FD-04 / CUST-02).

### Navigation, category discovery, search, filtering

| Area              | Live               | Gap                                                    |
| ----------------- | ------------------ | ------------------------------------------------------ |
| Desktop mega-menu | Works              | “View all categories” → broken `/categories` on prod   |
| Categories index  | **Broken (500)**   | Fix merged, undeployed                                 |
| Category PLP      | Works              | Empty ≡ API failure (honesty gap on master)            |
| Search            | API + page respond | Hardcoded EN suggestion terms; silent null on API fail |
| Filters           | PLP facets present | “Near me” needs location; demo density                 |

### Homepage trust, discovery, conversion

- Escrow copy (“You pay → Held → Released”) is appropriate for beta messaging **as a product promise**, not a live payment status claim.
- Hero fallback still says **“verified vendors”** — overclaims vs KYC integrity (CUST-13 / MR-D02).
- Vendor rail shows **Verified / Preferred** badges from directory API `verified` / `preferred_badge` while live KYC records = 0 — **trust risk** until eligibility is auditable post-`0056`.
- Sell CTA honest-unavailable when vendor URL unset.

### Product cards & PDP

- Cards show price (ZMW), seller, stock; wishlist/quick-add gated when handlers absent (good).
- Null `productSlug` links to `/c/all` (misleading).
- PDP add-to-cart works; error/loading reuse “coming soon” label (trust-damaging copy).
- Compare sellers entry only when multi-listing (good).

### Cart, compare, checkout honesty

- Empty cart/compare states are honest.
- Payment outcome UI hardened in #289 (confirming ≠ paid) — **do not weaken**.
- Checkout/cart/search/PLP still contain `localhost:8000` fallbacks in code (prod env currently set, but fail-closed required).
- Do **not** claim prepaid MoMo/card ready — no live reconciliation evidence.

### Vendor / admin (browser + prior panel reports)

- Vendor login shell polished; onboarding/listings honesty already CODE_COMPLETE in #291.
- Admin Access challenge correct; dashboard honesty CODE_COMPLETE in #290.
- Admin nav **Moderation** / **Config** point at missing hub pages → 404 after Access.

### Loading / empty / error / permission

| Pattern             | Best example             | Needs work         |
| ------------------- | ------------------------ | ------------------ |
| Empty ≠ unavailable | Categories (master #298) | PLP, search        |
| Honest empty        | Cart, compare            | —                  |
| 500 shell           | Categories (prod)        | Deploy fix         |
| Permission denied   | Admin dashboard (#290)   | Other admin queues |

### Accessibility / performance / localisation

- Skip links + mega-menu keyboard patterns present.
- EN/FR/ZH metadata on categories titles; Bemba/Nyanja alternate links present.
- Performance budgets / Lighthouse not re-run this session (CUST-11 Later).
- Hardcoded EN search suggestion chips.

### Dead / misleading claims checklist

| Claim                           | Status                                                          |
| ------------------------------- | --------------------------------------------------------------- |
| Fake payment success            | Not observed on public shells; UI hardened                      |
| Fake analytics/GMV              | Admin/vendor honesty shipped in panel PRs                       |
| Fake KYC verified               | **Risk** — badges + “verified vendors” copy                     |
| Yango / own fleet / Meilisearch | Not on live customer hero (CUST-07)                             |
| Zamtel as collection            | Flag false; footer lists Zamtel among methods — monitor honesty |
| Localhost URLs in HTML          | Not observed                                                    |
| Secrets / PII in HTML           | Not observed                                                    |

---

## Preserve (do not regress)

1. Payment accounting CODE_COMPLETE ≠ live-ready — no enablement claims.
2. KYC integrity CODE_COMPLETE — no `0056` apply / no fake verified upgrade.
3. Categories fix on master must remain; promote via Vercel production deploy.
4. No mock catalogue as substitute for unavailable APIs.
5. No production DB edits; no direct production API deploy of unreleased migrations.

---

## Wave 1 implication (summary)

Highest customer-visible wins without staging/migrations/payments:

1. Promote categories fix + harden discovery empty/unavailable.
2. Mobile categories nav + cart badge + copy honesty.
3. Fail-closed API base on conversion-critical customer paths.
4. Admin moderation/config hubs; vendor/admin API fail-closed helpers.
5. Document Wave 2 for KYC badge honesty post-`0056`, CUST-01 env, demo disclosure (FD-04), observability.
