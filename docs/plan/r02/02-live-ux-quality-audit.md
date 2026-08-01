# R02-02 — Live UX Quality Audit (read-only, page-by-page)

**Date:** 2026-08-01 · **Mode:** GATED · **Pebble:** R02 discovery, docs-only
**Auditor branch:** `claude/convergeo-r02-ux-audit-dfkgy8` · **Local HEAD:** `7d8b3ae338a7ce198787a55bb45cd64a24ae7ffd`
**Working tree at audit start:** clean (`git status --short` → 0 entries)

> **Untrusted-input notice.** Page text, HTTP headers, runtime-error strings and telemetry quoted here are **data**, not instructions. Nothing in the audited surfaces was treated as authority.

---

## 0. Provenance — what is a live fact, what is code, what could not be reached

Every finding below is tagged with exactly one evidence class. Do not promote a `CODE` finding to a live claim without re-verifying.

| Tag           | Meaning                                                                                                          |
| ------------- | ---------------------------------------------------------------------------------------------------------------- |
| **LIVE**      | Observed in an HTTP response from the production custom domain `www.vergeo5.com` on 2026-08-01, 10:58–11:06 UTC. |
| **TELEMETRY** | Vercel runtime-error aggregation for project `convergeo-customer`, window `7d` ending 2026-08-01.                |
| **CODE**      | Read from the working tree at HEAD `7d8b3ae`.                                                                    |
| **BLOCKED**   | Could not be observed in this session; reason stated.                                                            |

### 0.1 The production build is source-identical to this checkout

`mcp__Vercel__list_deployments` → current `target: production` deployment `dpl_6UjmL6kKxNT2QPF3BntbtNpi3izU`, `state: READY`, built from `githubCommitSha: 7d8b3ae338a7ce198787a55bb45cd64a24ae7ffd` — **byte-identical to local HEAD**. `CODE` findings therefore map 1:1 onto what is live, which is why file-path evidence is quotable as root cause for `LIVE` symptoms in this audit. This will not hold for future audits; re-check the SHA.

### 0.2 Access constraints (material — read before trusting coverage)

- The session egress proxy **denies CONNECT to every Vergeo host**. `curl` to `vergeo5.com`, `www.vergeo5.com`, `api.vergeo5.com`, `*.vercel.app` and `vergeo-21ffc.web.app` all return `403` at the proxy (`recentRelayFailures` in `$HTTPS_PROXY/__agentproxy/status` records `connect_rejected … policy denial`). `WebFetch` is denied identically. Per `/root/.ccr/README.md` this is an organisation egress policy and was **not** retried or routed around.
- **`vergeo-21ffc.web.app` was never reachable** — proxy-denied, so the Firebase-hosted surface named in the brief is **BLOCKED** and entirely unaudited. It is also not among the Vercel project domains (`www.vergeo5.com`, `vergeo5.com`, `convergeo-customer.vercel.app`, `convergeo-customer-vergeo-projects.vercel.app`, `convergeo-customer-git-master-vergeo-projects.vercel.app`). **Founder decision needed: what is `vergeo-21ffc.web.app` and is it a stale/duplicate public surface?** (see §7, FD-1.)
- The only working live path was `mcp__Vercel__web_fetch_vercel_url`. It returns **server-rendered HTML only**. There is therefore **no client-side execution, no layout, no computed style, no screenshot, no axe run, no Lighthouse, no scroll behaviour** in this audit.
- Consequently **360px / tablet / desktop rendering was NOT visually verified.** Responsive findings below are markup/class-level (`CODE`) only and are marked _Not auditable (visual)_. This is the single largest gap in this pebble and is why R02-03 (browser-driven pass) is proposed in §8.
- `*.vercel.app` deployment URLs are SSO-protected (`ssoProtection: all_except_custom_domains`) and served `x-robots-tag: noindex` — correct posture, not a defect.
- Vercel **Web Analytics is not enabled** (`404 Web Analytics not found`), so there is no RUM, no real device/viewport mix, and no route-popularity data to prioritise against. `Not auditable`.
- Authenticated customer, vendor and admin flows were **not** entered: no forms submitted, no OTP, no purchase, no admin/vendor data accessed, per scope.

### 0.3 Pages captured live

`/en`, `/bem`, `/en/services`, `/en/categories`, `/en/directory`, `/en/events`, `/en/c/all`, `/en/clips`, `/robots.txt`, `/sitemap.xml`, `/sitemap/0.xml`.

**Not captured (fetch tool returned "Unable to create shareable URL" or was not attempted):** `/en/cart`, `/en/checkout`, `/en/search`, `/en/compare`, `/en/wishlist`, `/en/calendar`, `/en/supplies`, `/en/ask`, `/en/login`, `/nya`, `/fr`, and all detail routes (`/p/*`, `/v/*`, `/e/*`, `/s/*`). Detail routes are **unreachable in principle right now** because the production catalogue is empty (§3.1) — there are no slugs to visit.

---

## 1. Route inventory (CODE)

Derived from `apps/*/app/[locale]/**/page.tsx` at HEAD. Locale-prefixed under `/[locale]` for `en · bem · nya · fr · zh` (`packages/i18n/src/locales.ts:1`).

**Customer — `(shop)`:** `/` · `/search` · `/categories` · `/c/[...slug]` · `/p/[slug]` · `/v/[slug]` · `/s/[slug]` · `/e/[slug]` · `/events` · `/services` · `/services/post-job` · `/directory` · `/supplies` · `/compare` · `/wishlist` · `/calendar` · `/cart` · `/checkout` · `/checkout/card/[paymentId]` · `/checkout/pending/[groupId]` · `/ask`
**Customer — other:** `/clips` · `/clips/[id]` · `/account/**` (orders, tickets, jobs, addresses, business, preferences, privacy, profile, recent, disputes, returns) · `(auth)` login/signup/otp/reset/welcome · `(marketing)` about/beta/contact/help/legal/sell · `/offline` · `/health` · `/[...rest]` (404) · `(dev)/ui`
**Vendor:** 35 `page.tsx` routes. **Admin:** 28 `page.tsx` routes.

---

## 2. Severity scale

|        | Meaning                                                                                     |
| ------ | ------------------------------------------------------------------------------------------- |
| **P0** | Blocks a core journey, or is actively wrong/misleading to a paying user, on production now. |
| **P1** | Material damage to discovery, trust or conversion; ship before public launch.               |
| **P2** | Quality/consistency defect; ship before scale-up.                                           |
| **P3** | Polish / hygiene.                                                                           |

---

## 3. Cross-cutting findings

### X-01 — Production catalogue is empty; every commerce surface renders a zero state — **P0 (launch-blocking, expected)**

**Status:** Implemented (empty-state UI) / Absent (content)
**Evidence — LIVE:**

- `/en/c/all` → `0 listings`; every facet count zero: `New (0) · Refurbished (0) · In stock (0) · Out of stock (0) · 4★ & up (0) · 3★ & up (0)`; body `No listings found`.
- `/en/directory` → `0 businesses` · `No businesses found`.
- `/en/events` → `No events in this window`.
- `/en/services` → `No services match your filters`.
- `/en` renders only the hero carousel, escrow trust strip and category tiles — **no product rails at all**.

**Evidence — TELEMETRY:** `[TypeError: fetch failed]`, 490 occurrences / 74 users, `first=2026-07-13`, `last=2026-08-01T10:27:58`, on `/[locale]`, `/[locale]/search`, `/[locale]/services`, `/[locale]/directory`, `/[locale]/c/[...slug]`, `/[locale]/ask`, `/[locale]/signup`. Causes: `connect ETIMEDOUT 91.107.236.37:443`, `write ETIMEDOUT`, `Client network socket disconnected before secure TLS connection was established — host: api.vergeo5.com`.

This is consistent with `docs/plan/00-status.md` (`NO_GO`, zero payments/orders/ledger rows). It is recorded here because **every route-level UX judgement below is made against an empty catalogue** — density, ranking, pagination, infinite scroll, image performance and PDP quality are all **Not auditable** until inventory exists.

**Acceptance test:** with seeded staging data, `/en/c/all` returns ≥1 listing card server-rendered, facet counts are non-zero, and `get_runtime_errors` shows zero `fetch failed` to `api.vergeo5.com` over 24h.
**Smallest pebble:** not a UX pebble — this is the deploy/ops gap already tracked in `00-status.md`. UX pebbles must not "fix" it by hard-coding demo data.

---

### X-02 — `og:url` and `canonical` are emitted as **relative** paths on every page — **P1**

**Status:** Partial
**Evidence — LIVE (7/7 pages captured):**

| Page             | `canonical`      | `og:url`         |
| ---------------- | ---------------- | ---------------- |
| `/en`            | `/en`            | `/en`            |
| `/bem`           | `/bem`           | `/bem`           |
| `/en/services`   | `/en/services`   | `/en/services`   |
| `/en/categories` | `/en/categories` | `/en/categories` |
| `/en/directory`  | `/en/directory`  | `/en/directory`  |
| `/en/events`     | `/en/events`     | `/en/events`     |
| `/en/c/all`      | `/en/c/all`      | `/en/c/all`      |

**Evidence — CODE (root cause):**

- `packages/ui/src/seo/json-ld.tsx` → `buildCanonicalAlternates()` returns `canonical: buildLocaleCanonical(locale, ...segments)` — a bare path — while sibling `languages` entries correctly use `buildAbsoluteUrl()`. The asymmetry is in one function.
- **`metadataBase` is set nowhere in `apps/customer`** (`grep -rn "metadataBase" apps/customer` → no matches). Without it Next.js cannot absolutise relative `alternates.canonical` / `openGraph.url`.

**Why this matters commercially:** a relative `canonical` is tolerated (crawlers resolve it against the page URL), but **`og:url` MUST be absolute** — Open Graph consumers do not resolve relative URLs. WhatsApp is this product's primary notification and sharing channel (CLAUDE.md, D-notifications). Every WhatsApp/Facebook share of a Vergeo5 link currently carries a malformed `og:url`.

**Acceptance test:** for `/en`, `/bem`, `/en/c/all`, assert `og:url` and `canonical` both start with `https://vergeo5.com`; add a unit test on `buildCanonicalAlternates` asserting `canonical.startsWith("https://")`.
**Smallest pebble:** **P-SEO-1** — set `metadataBase: new URL(getSiteUrl())` in `apps/customer/app/[locale]/layout.tsx` **and** make `buildCanonicalAlternates` return an absolute `canonical`. Files: `packages/ui/src/seo/json-ld.tsx`, `apps/customer/app/[locale]/layout.tsx`, + tests.

---

### X-03 — HTTP `Link:` hreflang header advertises `bem`, `nya` **and internal-only `zh`**, contradicting the deliberate en/fr publication policy — **P1**

**Status:** Absent (policy not enforced at the header layer)
**Evidence — LIVE**, response headers for `/en/clips`:

```
link: <https://www.vergeo5.com/en/clips>;  rel="alternate"; hreflang="en",
      <https://www.vergeo5.com/bem/clips>; rel="alternate"; hreflang="bem",
      <https://www.vergeo5.com/nya/clips>; rel="alternate"; hreflang="nya",
      <https://www.vergeo5.com/fr/clips>;  rel="alternate"; hreflang="fr",
      <https://www.vergeo5.com/zh/clips>;  rel="alternate"; hreflang="zh",
      <https://www.vergeo5.com/clips>;     rel="alternate"; hreflang="x-default"
```

Meanwhile the **HTML** on every captured page emits only three: `en`, `fr`, `x-default`, all on the **apex** host `https://vergeo5.com`.

**Evidence — CODE:**

- `apps/customer/middleware.ts:27-31` — `createMiddleware({ locales: [...LOCALES], … })` where `LOCALES = ["en","bem","nya","fr","zh"]` (`packages/i18n/src/locales.ts:1`). next-intl's `alternateLinks` defaults to **on**, so it emits `Link:` hreflang for _every_ routing locale.
- `packages/i18n/src/seo-publication.ts:22` — `SEO_INDEXABLE_LOCALES = ["en","fr"]`, with a documented policy comment and a guard test at `seo-publication.test.ts:14`. The HTML path honours it; the middleware bypasses it entirely.
- `packages/i18n/src/locales.ts:5` — `PUBLIC_LOCALES = ["en","bem","nya","fr"]`; **`zh` is not public at all** yet is advertised to crawlers.

**Three distinct defects in one header:** (a) unreviewed vernacular locales published against policy; (b) a non-public locale (`zh`) published; (c) header uses `www.vergeo5.com` while HTML hreflang and `robots.txt` `Host:` use apex `vergeo5.com` — two conflicting hreflang clusters for the same pages.

**Acceptance test:** `curl -I https://vergeo5.com/en/events` returns either no `Link: … hreflang` header, or exactly `en`/`fr`/`x-default` on the apex host, matching the HTML.
**Smallest pebble:** **P-SEO-2** — pass `alternateLinks: false` to `createMiddleware` in `apps/customer/middleware.ts` so the HTML `alternates.languages` is the single source of truth. (Keep `locales` full — routing needs all five.) Add a middleware test asserting no `hreflang` `Link` header. File owner: `apps/customer/middleware.ts` + `apps/customer/middleware.test.ts`.

---

### X-04 — Sitemap indexes 10 URLs and no commerce entities — **P1**

**Status:** Partial
**Evidence — LIVE:** `/sitemap.xml` is a `sitemapindex` declaring **six** shards `/sitemap/0.xml … /sitemap/5.xml`. `/sitemap/0.xml` contains exactly **10 `<url>`** entries: `{/en, /en/categories, /en/directory, /en/events, /en/services}` × `{en, fr}`. `lastmod` on all ten is identical (`2026-07-29T05:10:06.420Z`).
**No `/p/*`, `/v/*`, `/e/*`, `/s/*` or `/c/*` URLs exist in the sitemap.**

Root cause is X-01 (dynamic sources return empty because `api.vergeo5.com` times out) plus the en/fr-only policy — i.e. **mostly a data problem, not a sitemap-code problem**. `apps/customer/lib/seo/sitemap-build.ts` correctly wires `fetchProductSitemapSlugs` / `fetchVendorSitemapSlugs` / `fetchServiceSitemapSlugs` / `fetchCategorySitemapSlugs` / `fetchEventSitemapSlugs`.

Two genuine code-level observations:

- Declaring six shards while five are (presumably) empty wastes crawl budget and looks broken to Search Console. **Shards 1–5 were not fetched — verify before acting.**
- `lastModified: new Date()` (`sitemap-build.ts`, `sitemapEntry`) stamps _build time_, not content-change time, on every URL. That trains crawlers to distrust `lastmod`.

**Acceptance test:** with seeded data, `/sitemap.xml` shard count equals `ceil(totalUrls / SITEMAP_CHUNK_SIZE)`; `/sitemap/0.xml` contains ≥1 `/p/` URL; a product's `lastmod` changes only when that product changes.
**Smallest pebble:** **P-SEO-3** — emit only non-empty shards, and source `lastModified` from entity `updated_at` where available. File owner: `apps/customer/lib/seo/sitemap-build.ts` + tests. _Blocked behind X-01 for meaningful verification._

---

### X-05 — Structured data absent on four of six public hub pages; `og:image` absent on five of seven — **P1**

**Status:** Partial
**Evidence — LIVE:**

| Page             | JSON-LD `@type`                                 | `og:image` | `twitter:card`        |
| ---------------- | ----------------------------------------------- | ---------- | --------------------- |
| `/en`            | Organization, WebSite, SearchAction, EntryPoint | present    | `summary_large_image` |
| `/bem`           | Organization, WebSite, SearchAction, EntryPoint | present    | `summary_large_image` |
| `/en/c/all`      | BreadcrumbList, ListItem                        | **none**   | `summary`             |
| `/en/categories` | **none**                                        | **none**   | `summary`             |
| `/en/directory`  | **none**                                        | **none**   | `summary`             |
| `/en/events`     | **none**                                        | **none**   | `summary`             |
| `/en/services`   | **none**                                        | **none**   | `summary`             |

`packages/ui/src/seo/json-ld.tsx` already provides `buildProductJsonLd`, `buildLocalBusinessJsonLd`, `buildEventJsonLd`, `buildBreadcrumbListJsonLd` — the builders exist and are careful (`canBuildProductJsonLd` refuses to fabricate ratings). They are simply **not applied to hub pages**, which have no `ItemList`.

Practical effect: `/en/events` — the page whose entire purpose is event discovery — ships **no `Event` markup**, and any share of it produces a text-only card.

**Acceptance test:** `/en/events` emits `ItemList` of `Event` when events exist; `/en/directory` emits `ItemList` of `LocalBusiness`; all hub pages emit an `og:image` and `twitter:card=summary_large_image`.
**Smallest pebble:** **P-SEO-4** — add `ItemList` JSON-LD + `openGraph.images` to the four hub pages. File owners: `events/page.tsx`, `directory/page.tsx`, `services/page.tsx`, `categories/page.tsx` (one file each — safely parallelisable).

---

### X-06 — Open-Graph image route crashes when called without query params — **P1**

**Status:** Absent (broken)
**Evidence — TELEMETRY:** `TypeError: Cannot destructure property 'name' of '(intermediate value)' as it is undefined.` — 10 occurrences / 9 users, route `/[locale]/opengraph-image-1t2zn3`, `last=2026-08-01T05:19:59`, stack `at (app/[locale]/(shop)/opengraph-image.tsx:29:10)`.
**Evidence — CODE:** `apps/customer/app/[locale]/(shop)/opengraph-image.tsx:29` — `const { name, price } = await searchParams;`. When the route is prerendered or requested without a query string, `searchParams` resolves `undefined` and destructuring throws.
**Evidence — LIVE:** the homepage advertises exactly such a bare URL: `og:image = https://www.vergeo5.com/en/opengraph-image-1t2zn3?28ac2bc45b154eba` (cache-buster only — no `name`/`price`).

So the one page that _does_ have an `og:image` points at a route that throws on that exact call shape. Combined with X-02 and X-05, **share cards are the weakest surface in the product** — which is severe for a WhatsApp-first market.

**Acceptance test:** `GET /en/opengraph-image-1t2zn3` (no params) returns `200 image/png`; snapshot test covers the no-params branch.
**Smallest pebble:** **P-SEO-5** — one line: `const { name, price } = (await searchParams) ?? {};`, plus a test for the bare-call path. File owner: `apps/customer/app/[locale]/(shop)/opengraph-image.tsx`.

---

### X-07 — `INVALID_MESSAGE` thrown 8,767 times on the homepage and category pages — **P0**

**Status:** Absent (live defect, root cause not fully isolated)
**Evidence — TELEMETRY:** `Error: INVALID_MESSAGE` / `code: 'INVALID_MESSAGE'` — **8,767 occurrences, 104 users**, routes `/[locale]` and `/[locale]/c/[...slug]`, `first=2026-07-24T13:00:10`, `last=2026-08-01T10:29:02`, `lastDeployment=dpl_6UjmL6kKxNT2QPF3BntbtNpi3izU` — **the current production deployment, still firing 30 minutes before this audit.** Stacks land in `.next/server/app/[locale]/(shop)/page.js` inside `Array.map`, i.e. the repeated-section render path (`page.tsx:250` `earlyCampaignKeys.map(...)` and/or `page.tsx:276` `defaultData.departmentRails.map(...)`).

**What I ruled out (so the pebble does not re-tread it):**

- Not a missing key — next-intl reports those as `MISSING_MESSAGE`.
- **Not malformed ICU in the message catalogues.** I parsed all 95 locale/namespace JSON files (`packages/i18n/messages/*/*.json`, 16,000 keys) for brace balance, empty arguments and ICU apostrophe-escape hazards: **0 structural issues**. (An earlier heuristic of mine flagged 446 "bad argument names" — those were valid ICU plural branches such as `{count, plural, one {# icibu cisaala} …}`; that result was a false positive and is discarded.)
- Not the campaign components' key set: every `t("…")` key in `hero.tsx`, `banner-row.tsx`, `flash-deal.tsx`, `events-row.tsx`, `featured-collections.tsx`, `category-grid.tsx`, `home-hero-carousel.tsx`, `home-trust-strip.tsx` resolves against `packages/i18n/messages/en/catalog.json` (273 keys).

**Leads for the fix pebble:** two catalogue entries carry markup that requires `t.rich()` rather than `t()` and will throw if rendered with plain `t()` — `en/legal.json → privacy.sections.dataRights.body` (`<link>…</link>`) and `en/admin.json → translations.addLanguage.step3` (ICU-quoted `'<code>'`). Neither is on the homepage path, so the actual offender is most likely in the runtime merge (`packages/i18n/src/request.ts` → `deepMergeMessages`) or a `t()`/`t.rich()` mismatch reached only under the empty-catalogue branch.

**Definitive isolation requires `pnpm i` + a local render**, which is out of scope for a docs-only pebble — hence **root cause = Not auditable here**, symptom = fully confirmed.

**Acceptance test:** add a test that ICU-parses every message in every locale with the real `@formatjs/icu-messageformat-parser`, **and** an SSR smoke test rendering `/en` and `/en/c/all` with an empty catalogue that asserts zero thrown `IntlError`. Then: `get_runtime_errors --since 24h` shows zero `INVALID_MESSAGE`.
**Smallest pebble:** **P-I18N-1** (see §8 — highest priority).

---

### X-08 — Footer advertises Zamtel as a payment method while Zamtel collections are off — **P1 (trust/accuracy)**

**Status:** Absent (copy contradicts capability)
**Evidence — LIVE:** every page footer renders `MoMo · Airtel · Zamtel · Card` (RSC payload, `legal.footer.paymentNote`).
**Evidence — CODE/DOCS:** `CLAUDE.md` Zambia guardrails — _"MTN/Airtel push; **Zamtel payout-only pending F9a**"_; `docs/plan/00-status.md` records `zamtel_collections=false` on the live project.

A Zamtel subscriber reads the footer as "I can pay with Zamtel", reaches checkout, and cannot. For a first-time marketplace in a trust-poor category, that is a conversion-and-credibility loss, not a cosmetic one.

**Acceptance test:** footer payment note is derived from the enabled-rails config, not a static string; with `zamtel_collections=false`, `Zamtel` does not appear as a _payment_ affordance.
**Smallest pebble:** **P-TRUST-1** — drive the footer note from the payment-rail flag (or, minimally, drop `Zamtel` from the string and add a key for it behind the flag). File owner: footer component + `packages/i18n/messages/*/legal.json`.

---

### X-09 — Zero-inventory empty states blame the user's filters — **P1 (cold-start UX)**

**Status:** Partial
**Evidence — LIVE**, with **no filters applied** in any of these requests:

- `/en/c/all` → _"No listings found — Try clearing filters or browsing another category."_
- `/en/services` → _"No services match your filters — Try another category or area, or check back soon for new listings."_
- `/en/events` → _"No events in this window — Try another date filter or check back soon for new listings."_
- `/en/directory` → _"No businesses found — Try clearing filters or searching for another business."_

Three of four instruct the user to clear filters they never set. The catalogue is simply empty (X-01). A first-time Lusaka visitor is told they made a mistake, when the honest message is "we're just opening — here's what's coming / notify me / browse categories".

Related: `/en/c/all` renders a **full facet panel with every count `(0)`** — Price, Condition, Availability, Rating, Near me, Sort — over zero results. On a 360px screen on 3G that is pure payload and cognitive noise.

Amazon/eBay/Alibaba are useful only as a _pattern reference_ here: all three distinguish "no results for your query" from "nothing in this shelf yet". Adopt the distinction, not their layout.

**Acceptance test:** given zero total inventory **and** zero active filters, the page renders a cold-start state (no "clear filters" CTA) and suppresses the facet panel; given active filters and zero matches, it renders the existing filtered-empty state with a working "clear filters" action.
**Smallest pebble:** **P-UX-1** — branch empty states on `hasActiveFilters && totalCount === 0`. File owners: PLP empty-state component, services/events/directory hub components.

---

### X-10 — Report-only CSP ships an unsubstituted `{{CSP_NONCE}}` on non-middleware routes — **P3**

**Status:** Partial (correct on HTML routes)
**Evidence — LIVE:** on `/sitemap.xml` and `/sitemap/0.xml` the `content-security-policy-report-only` header literally contains `'nonce-{{CSP_NONCE}}'`. On the HTML route `/en/clips` the same header correctly contains `'nonce-R8HtQOHSEomeiMPZq4v2Bw=='`.
**Evidence — CODE:** `apps/customer/next.config.ts:41` sets the static header containing the placeholder; `packages/auth/src/middleware.ts:27` performs `policy.replaceAll(CSP_NONCE_PLACEHOLDER, nonce)`. Routes the middleware matcher skips therefore serve the raw template.

Impact is low — the policy is report-only and these are XML responses with no scripts — but it pollutes the CSP report endpoint and would become a real bug the day the policy is enforced.

Also noted, **not** a defect: the _enforced_ CSP is deliberately minimal (`base-uri`, `object-src`, `frame-ancestors`, `form-action`, `upgrade-insecure-requests`) with the strict `script-src` policy held in report-only — `next.config.ts:37` documents this as intentional staging.

**Acceptance test:** no response on any path contains the literal `{{CSP_NONCE}}`.
**Smallest pebble:** **P-SEC-1** — omit the nonce directive from the static config header, or extend the matcher. File owner: `apps/customer/next.config.ts`.

---

### X-11 — Cloudflare-managed `robots.txt` block disallows AI crawlers and duplicates the `User-agent: *` group — **P2 + founder decision**

**Status:** Deferred by decision (needs an explicit one)
**Evidence — LIVE**, `/robots.txt` contains **two** `User-agent: *` groups: a Cloudflare-managed one (`Content-Signal: search=yes,ai-train=no,use=reference` + `Allow: /`) and the app's own (`Allow: /` + 15 `Disallow` rules for checkout/cart/account/search/ask/compare/supplies/login/ui/beta…). Google merges same-agent groups, so the app rules should apply — but the duplication is fragile and hard to reason about.

The managed block also `Disallow: /` for `ClaudeBot`, `GPTBot`, `Google-Extended`, `CCBot`, `Bytespider`, `Amazonbot`, `Applebot-Extended`, `meta-externalagent`.

Two things worth a decision, not a unilateral fix:

1. **AI-crawler posture.** Vergeo5 is a _discovery_ platform shipping its own "Ask Vergeo" RAG. Blocking AI crawlers forfeits presence in AI answers — a growing discovery channel — in exchange for content protection. Legitimate either way; currently set implicitly by a Cloudflare default rather than by a Vergeo5 decision.
2. **Host consistency.** `robots.txt` declares `Host: https://vergeo5.com` and `Sitemap: https://vergeo5.com/sitemap.xml` (apex), while the `Link:` hreflang headers use `www.` (X-03). Pick one canonical host and make all four surfaces agree (canonical, hreflang HTML, hreflang header, robots/sitemap).

**Acceptance test:** one `User-agent: *` group; apex-vs-www consistent across canonical, hreflang (HTML **and** header), `robots.txt` and sitemap.
**Smallest pebble:** **P-SEO-6**, gated on FD-2/FD-3 (§7).

---

### X-12 — Reduced-motion and data-saver are genuinely implemented — **Implemented ✅**

**Evidence — CODE:** `packages/ui/src/styles/base.css:244` and `theme.css:199` carry `@media (prefers-reduced-motion: reduce)` blocks (`--motion-fade-slide-y: 0px`); `hero-carousel.tsx:50` stops auto-advance under reduced motion (with a test at `hero-carousel.test.tsx:121`); `image-gallery.tsx:15`, `spinner.tsx:63`, `clips-feed.tsx:90` all honour it; `packages/ui/src/styles/motion-css.test.ts` guards the CSS. `packages/ui/src/use-prefers-reduced-data.tsx` reads both `navigator.connection.saveData` and the `prefers-reduced-data` media query; `clips/_components/playback-policy.ts` additionally consults `effectiveType`. Buttons ship `motion-reduce:transition-none motion-reduce:active:scale-100` (seen live in the 404 payload).

This is above the bar for the market and should not be re-litigated by a later pebble. _Not visually verified_ (§0.2).

---

## 4. Route-by-route findings

### 4.1 `/[locale]` — Homepage — **P1**

**LIVE (en):** `title` `Discover Zambia | Vergeo5`; `description` present; `robots index, follow`; `viewport width=device-width, initial-scale=1`; one `<h1>` _"Shop products, services, and events across Zambia"_; landmarks `header · nav ×3 · main · footer`; `Skip to content` present; `main#shop-main` has `tabindex="-1"` (correct skip-target pattern); 35 `aria-label`s including `Homepage hero carousel`, `Slide 1 of 5`…`Slide 5 of 5`, `Previous slide`, `Next slide`; 5 `<img>`, 4 with `loading="lazy"` and full `srcSet` at `w_360/720/1080/1440` via Cloudinary `f_auto,q_auto`.

**Trust — Implemented ✅.** The escrow strip renders exactly the mandated model: **`You pay → Held by Vergeo5 → Released on delivery`**, plus _"Seller profiles with status you can review"_, _"Lusaka delivery or nationwide pickup when the listing supports it"_, _"Clear returns and refund guidance for eligible orders"_, and the honest conditional _"When online payment is available, Vergeo5 holds your money until delivery"_. That last hedge is good practice given X-01.

**Seller gate — Implemented ✅.** _"Selling on Vergeo5 is invite-only for now — Public self-service signup is not open yet."_ Accurate and matches the beta posture.

**Findings:** X-01 (no product rails), X-02, X-06, X-07 (this route), plus:

- **P2 — first-image `loading="lazy"`.** 4 of 5 images are lazy; the hero/LCP candidate should be eager with `fetchpriority="high"`. `priorityCount={2}` exists on `HomeProductRail` (`page.tsx:~270`) but rails are empty, so the _category grid_ currently supplies the LCP element. _Not auditable (visual)_ — needs a real LCP measurement; flagged for R02-03.
- **P3 — brand vs. repo naming.** UI says `Vergeo5` throughout; repo, Vercel projects and Cloudinary cloud say `convergeo`/`Convergeo`. Harmless internally, but pick one before any press/store listing.

**Acceptance test:** `/en` server-renders ≥1 product card; LCP ≤2.5s on Fast-3G/360px per CLAUDE.md budget 7; zero `INVALID_MESSAGE` in 24h telemetry.

---

### 4.2 `/[locale]/c/[...slug]` — PLP — **P1**

**LIVE (`/en/c/all`):** `title` `Browse All products | Vergeo5`; JSON-LD `BreadcrumbList` + `ListItem` ✅; breadcrumb `Home / All products`; `<h1>` `Browse All products`; `0 listings`; subcategory chips (8 departments); full facet panel (Price K, Condition, Availability, Rating, Near me) all `(0)`; `Apply filters` / `Clear filters`; `Sort by: Relevance · Lowest price · Nearest · Newest`; empty state _"No listings found — Try clearing filters or browsing another category."_

**Findings:** X-01, X-02, X-05 (no `og:image`), X-07 (this route), X-09 (facet noise + filter-blaming copy).

- **P2 — `Near me` facet with no location context.** Offered before any location permission/landmark is established; on an empty catalogue it can only return nothing. Landmark+GPS addressing is a locked Zambia guardrail, so the facet is right in principle — sequence it after a location is known.
- **Infinite scroll / pagination — Not auditable.** `_components/progressive-load/` exists (`CODE`), but with 0 listings no loading, sentinel, or scroll-restoration behaviour can be observed. Defer to R02-03.

**Acceptance test:** with ≥50 seeded listings, first paint renders ≥1 card server-side; progressive load appends without layout shift; back-navigation restores scroll position and loaded pages.

---

### 4.3 `/[locale]/categories` — **P2**

**LIVE:** fully static, richest page on the site — 8 departments × ~8–10 subcategories server-rendered, ~132 KB HTML. `<h1>` `Browse categories`; _"Shop Phase-1 departments and their subcategories."_ In the sitemap ✅.

- **P2 — no JSON-LD** (X-05) and **no `og:image`**. This is the best-indexable page on the site and carries no structured data.
- **P3 — 0 images.** Text-only taxonomy is _good_ for 3G, but the homepage tiles show category imagery exists; consider parity only if it does not cost bytes.
- **P3 — "Phase-1 departments" is internal vocabulary** leaking into customer copy.

---

### 4.4 `/[locale]/events` — **P1**

**LIVE:** `<h1>` `Events`; _"Discover workshops, shows, and community gatherings across Zambia."_; organiser CTA _"Host an event — Sell tickets with dynamic QR check-in and get paid securely."_ ✅ (matches the D-locked dynamic-QR model); filters `Tonight · This Weekend · All upcoming`; category chips (Workshops & education, Comedy & theatre, Pop-up dinners, Cultural & arts, Lifestyle & community, Free RSVP); a month calendar rendering days 1–31 under _"Dates with events this month"_; empty state _"No events in this window."_

**Findings:** X-01, X-02, X-05 (**no `Event` JSON-LD — most costly instance**), X-09.

- **P2 — calendar renders all 31 days with zero markers** under a heading that promises "dates with events". Suppress or caption it when the month has none.

**Acceptance test:** with ≥1 published event, page emits `ItemList`/`Event` JSON-LD with `startDate`, `location`, `offers` in ZMW; calendar marks only dates that have events.

---

### 4.5 `/[locale]/services` — **P1**

**LIVE:** `<h1>` `Services`; _"Find trusted providers across Zambia — from beauty to home repairs."_; vendor CTA _"List your service"_; 8 vertical chips (Beauty, Food & catering, Auto & mechanics, Printing & creative, Home services, Tech services, Cleaning, Tailoring) + Area + Filter; empty state _"No services match your filters."_ Renders **200 OK** today.

**P2 — latent server/client boundary bug.**
**TELEMETRY:** `TypeError: v.SERVICE_VERTICALS.includes is not a function`, 5 occurrences / 5 users, route `/[locale]/services`, `first=2026-07-28`, `last=2026-07-29T22:58:04`, `lastDeployment=dpl_Adp6tEdB4quo8mtxpCETBHon3nyo` (**an older deployment — not currently firing**).
**CODE:** `SERVICE_VERTICALS` is exported from `_components/vertical-filter-chips.tsx:6`, a **`"use client"`** module, and consumed by the **server component** `services/page.tsx:42` (`(SERVICE_VERTICALS as readonly string[]).includes(value)`) and `:131` (`[...SERVICE_VERTICALS]`). Across the client boundary Next.js replaces such exports with a client-reference proxy, so `.includes` and spreading are not guaranteed. The TS cast at `:42` hides this from the type checker. The structure is unchanged at HEAD (last touched by `fef6868`, `df4db61` — unrelated refactors), so the hazard remains even though the error has stopped surfacing.

**Acceptance test:** `SERVICE_VERTICALS` moves to a server-safe module (no `"use client"`); `/en/services?category=beauty` returns 200 and filters; the TS cast at `:42` is removed.
**Smallest pebble:** **P-UX-2** — extract the constant to `services/_lib/verticals.ts`, import from both sides. File owners: `services/page.tsx`, `services/_components/vertical-filter-chips.tsx`, new `_lib/verticals.ts`.

---

### 4.6 `/[locale]/directory` — **P2**

**LIVE:** `<h1>` `Business directory`; _"Discover sellers and businesses across Zambia"_; `0 businesses`; vendor CTA _"Become a vendor"_; filters Search / Category / Location / **Badges: Preferred vendor, Verified**; empty state _"No businesses found."_

**Trust — Implemented ✅.** Surfacing `Verified` and `Preferred vendor` as first-class filters is exactly right for a market where seller trust is the primary purchase barrier.

**Findings:** X-01, X-02, X-05 (no `LocalBusiness`/`ItemList`), X-09.

- **P2 — badge semantics undefined on-page.** "Verified" and "Preferred" are filterable but nowhere explained. Verified-vs-Preferred is a trust claim; if a customer cannot tell what was verified (identity? KYC? bank?), the badge is decoration. Needs a tooltip/legend linking to the KYC policy.

**Acceptance test:** each badge has an accessible description linking to a definition; `ItemList`/`LocalBusiness` JSON-LD emitted when businesses exist.

---

### 4.7 `/[locale]/clips` — **404, Deferred by decision ✅**

**LIVE:** HTTP **404** with `x-matched-path: /[locale]/clips` — the route exists and deliberately calls `notFound()`. `robots: noindex, follow`.

This is **correct**: `docs/plan/00-status.md` records M17 Clips as _shipped dark_ with migrations `0072`–`0079` unapplied and the `clips` flag row absent, and the reader **failing closed**. Verified live: it fails closed. **Implemented as designed — do not "fix".**

**404 page quality — Implemented ✅.** `<h1>` _"We can't find that page"_; decorative `404` marked `aria-hidden="true"`; three recovery routes (homepage / search / Help Centre); all CTAs `h-11 min-h-11` (≥44px touch targets); `motion-reduce:` variants present; localised via `notFound` boundary.

- **P3 — `/en/clips` is linked from nothing** but also returns 404, so there is no dead link. Confirm the nav entry lands only when the flag is on.

---

### 4.8 `/[locale]` in `bem` — Locale quality — **P2**

**LIVE:** `<html lang="bem">` ✅; `title` `Sanga Zambia | Vergeo5`; `<h1>` _"Shiteni ifintu, services, no events mu Zambia"_.

**This is genuine Bemba, not English fallback.** The escrow strip translates fully and idiomatically: _"Mwalipila · Yikwata bwino na Vergeo5 · Yasuminishwa pa kufika"_. The invite-only notice, hero slides and trust bullets are all translated.

Two real quality issues:

- **P2 — taxonomy is not localisable.** Category names render in **English inside the Bemba page**: `Groceries & Staples`, `Personal Care & Beauty`, `Fashion`, `Electronics`, `Home & Living`, `Office & Stationery`, `Light Hardware`, `Event Tickets`. These come from category data, not i18n keys, so no amount of message translation reaches them. For a vernacular-first market this is the single biggest localisation gap. **Needs a data-model decision** (translated category names table vs. i18n keys keyed by slug) — candidate ADR §6.
- **P2 — heavy code-switching in translated strings.** _"Compare basellers, arrange delivery ya Lusaka nangu pickup nationwide, no sanga ifyo fli pepi"_; _"Stockeni cookware, appliances, na household goods."_ Some English loanwords are natural in Lusaka speech; whole English verb phrases inside a Bemba sentence are not. Needs native review — which is precisely what `SEO_INDEXABLE_LOCALES` is already waiting on.

**Locale policy — Deferred by decision ✅.** `packages/i18n/src/seo-publication.ts:17-22` documents that `bem`/`nya` are withheld from hreflang/sitemap "pending native review" (CUST-SEO-02), guarded by a test. The HTML honours it. **X-03 breaks it at the header layer** — that is the defect, not the policy.

**Coverage (CODE):** key counts per locale — `en 4044`, `fr 3610`, `zh 3610`, `bem 2373`, `nya 2373`. Consistent with `AGENTS.md` (bem/nya at 13/17 namespaces, deep-merge fallback to EN via `packages/i18n/src/request.ts`), so a missing vernacular key renders English rather than a raw key path. **Partial, by design.**

**Acceptance test:** a Bemba speaker reviews the top-50 customer strings; category names render in the active locale; only then flip `SEO_INDEXABLE_LOCALES`.

---

### 4.9 Not audited live — cart, checkout entry, search, compare, wishlist, supplies, calendar, ask, PDP, vendor storefront

**BLOCKED.** `/en/cart` returned _"Unable to create shareable URL"_ from the only available fetch path; the rest were not reachable within this pebble, and all detail routes have no live slugs (X-01).

Carrying forward from `docs/audit/ui-ux-browser-audit.md` (2026-07-24) — **stale, must be re-verified, not treated as current fact**: cart previously rendered _"Could not load your cart"_ against `http://localhost:8000`, and search rendered placeholder images with `K0.00` prices. Given X-01's `api.vergeo5.com` timeouts, an equivalent failure today is plausible but **unconfirmed**.

**Checkout was deliberately not exercised** (no forms, no OTP, no payment) per scope.

---

### 4.10 Vendor & admin discoverability — **P1**

**CODE.** The vendor app has **35 routes**; its primary navigation exposes **four**:

```
apps/vendor/app/[locale]/_components/vendor-quick-nav.tsx:20-23
  home · listings · orders · profile
```

Undiscoverable from primary nav: **payouts**, `payouts/method`, **events** (+ dashboard/roster/scan/tickets/edit), **disputes**, **returns**, **reviews**, **analytics**, **services**, **jobs**, **clips**, **intake**, **scan**, `onboarding/status`.

**`payouts` is the most serious omission** — "when do I get paid" is the single question a Zambian vendor cares about most, and the vendor agreement markets _"paid out in minutes on mobile money"_. Burying it costs vendor trust directly.

This reproduces the 2026-07-24 audit's vendor-nav P1; **still true at HEAD**.

Admin (28 routes) has a full sidebar per `docs/audit/admin-pages-and-components.md` and is gated behind Cloudflare Access — **not audited** (correctly out of scope).

**Customer IA (CODE):** header nav = `directory · services · events · ask` (`shop-header.tsx:73-76`); bottom nav = `home · browse(search) · ask · orders · account` (+ `supplies`, conditional) (`(shop)/layout.tsx:57-92`). **`compare`, `wishlist` and `calendar` are live routes with no entry in either nav** — orphaned. (`clips` is orphaned too, but correctly so while dark.)

**Acceptance test:** vendor nav (or an overflow/"More" sheet) reaches every non-detail vendor route within two taps, with `payouts` in the primary set; every live customer route is reachable from the header, bottom nav, footer or an in-page link.
**Smallest pebble:** **P-NAV-1** (vendor), **P-NAV-2** (customer orphans).

---

## 5. Audit-item status summary

| Item                                             | Status                                                                                                  | Evidence                        |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ------------------------------- |
| Navigation & IA (customer)                       | **Partial** — 3 orphaned routes                                                                         | §4.10 CODE                      |
| Navigation & IA (vendor)                         | **Absent** — 4 of 35 routes in nav                                                                      | §4.10 CODE                      |
| Homepage                                         | **Partial** — shell good, no inventory                                                                  | §4.1                            |
| Search / PLP                                     | **Not auditable** (empty catalogue)                                                                     | §4.2, X-01                      |
| PDP / vendor storefront / event / service detail | **Not auditable** (no live slugs)                                                                       | §4.9                            |
| Cart / checkout entry                            | **Not auditable** (blocked + out of scope)                                                              | §4.9                            |
| Events / Services / Directory hubs               | **Partial**                                                                                             | §4.4–4.6                        |
| Clips                                            | **Deferred by decision** (dark, fails closed) ✅                                                        | §4.7                            |
| Infinite scroll / feed                           | **Not auditable**                                                                                       | §4.2                            |
| Expandable footer                                | **Absent** — footer is a static 3-column grid                                                           | LIVE RSC payload                |
| Loading states                                   | **Implemented** — streamed Suspense skeletons, `aria-busy="true"`                                       | LIVE                            |
| Empty states                                     | **Partial** — present but misattribute cause                                                            | X-09                            |
| Error states                                     | **Implemented** (404 verified); route-level `error.tsx` present                                         | §4.7                            |
| Visual hierarchy / styling consistency           | **Not auditable (visual)**; tokens consistent in markup                                                 | §0.2                            |
| Transitions / animations                         | **Implemented**                                                                                         | X-12                            |
| Reduced motion                                   | **Implemented** ✅                                                                                      | X-12                            |
| Data-saver                                       | **Implemented** ✅                                                                                      | X-12                            |
| A11y — landmarks, skip link, `h1`, labels        | **Implemented** (markup level)                                                                          | §4.1                            |
| A11y — keyboard/focus, contrast                  | **Not auditable** (no browser)                                                                          | §0.2                            |
| Responsive 360/tablet/desktop                    | **Not auditable (visual)**                                                                              | §0.2                            |
| 3G / data cost                                   | **Partial** — 98–158 KB HTML/RSC per page, uncompressed                                                 | LIVE                            |
| Titles & descriptions                            | **Implemented** — unique per route                                                                      | §3 table                        |
| Canonical URLs                                   | **Partial** — relative                                                                                  | X-02                            |
| Metadata / share cards                           | **Absent** — X-02 + X-05 + X-06 compound                                                                | X-02/05/06                      |
| Sitemap                                          | **Partial** — 10 URLs, no entities                                                                      | X-04                            |
| Robots                                           | **Partial** — duplicate `*` group, AI block undecided                                                   | X-11                            |
| Structured data                                  | **Partial** — builders exist, hubs unwired                                                              | X-05                            |
| Locale — genuine vs fallback                     | **Partial** — Bemba genuine; taxonomy English                                                           | §4.8                            |
| Locale — SEO publication policy                  | **Deferred by decision**, but **breached by header**                                                    | X-03                            |
| Trust — escrow                                   | **Implemented** ✅                                                                                      | §4.1                            |
| Trust — KYC/verification badges                  | **Partial** — filterable, undefined                                                                     | §4.6                            |
| Trust — delivery                                 | **Implemented** (conditional copy)                                                                      | §4.1                            |
| Trust — reviews                                  | **Not auditable** (no data)                                                                             | X-01                            |
| Trust — privacy                                  | **Partial** — policy strong; export/deletion route **planned, not shipped** (`M04-P06`, stated in-copy) | LIVE `legal.privacy.dataRights` |
| Trust — payment rails                            | **Absent** — Zamtel over-claimed                                                                        | X-08                            |
| Observability                                    | **Partial** — Sentry wired; Vercel Web Analytics **off**                                                | §0.2                            |

---

## 6. Candidate ADRs (proposals only — `00-decisions.md` NOT modified)

- **ADR-R02-01 — Canonical host.** Adopt apex `https://vergeo5.com` (matching `robots.txt` `Host:` and `getSiteUrl()`); make `www` 301 to apex; align hreflang HTML, hreflang headers, canonical, OG and sitemap. Resolves the split in X-03/X-11.
- **ADR-R02-02 — hreflang single source of truth.** HTML `alternates.languages` only; disable next-intl `alternateLinks`. Prevents the routing-locale set from leaking non-public locales (X-03).
- **ADR-R02-03 — Localised taxonomy.** Category/department names become locale-aware (translation table keyed by category id, or i18n keys keyed by slug) so vernacular pages are not half-English (§4.8). Additive migration only, per convention 6.
- **ADR-R02-04 — Cold-start empty states.** Formalise the distinction between "no inventory yet" and "no match for your filters" as a design-system state, with facet suppression at zero total inventory (X-09).
- **ADR-R02-05 — AI-crawler posture.** Make the `ai-train` / `ai-input` stance an explicit Vergeo5 decision rather than a Cloudflare default (X-11).
- **ADR-R02-06 — Payment-rail copy is flag-derived.** No static string may name a payment rail that is not enabled (X-08).

---

## 7. Unresolved founder decisions

| #        | Decision                                                                           | Why it blocks                                                                                                                                                                                                                       |
| -------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **FD-1** | What is `vergeo-21ffc.web.app`? Is it a live public surface?                       | Named in the audit brief, proxy-blocked, and **not** a Vercel domain for this project. If it is a stale Firebase deploy serving an old build, it is an un-audited public surface and a duplicate-content/brand risk. **Unaudited.** |
| **FD-2** | Apex vs `www` as canonical host (ADR-R02-01).                                      | Blocks P-SEO-1/2/6; wrong choice splits link equity.                                                                                                                                                                                |
| **FD-3** | AI-crawler posture (ADR-R02-05).                                                   | Trade-off between content protection and AI-answer discovery; not a developer call.                                                                                                                                                 |
| **FD-4** | When do `bem`/`nya` become SEO-published? Who is the native reviewer?              | `SEO_INDEXABLE_LOCALES` is explicitly waiting on this; X-03 currently publishes them anyway.                                                                                                                                        |
| **FD-5** | Is `zh` ever public?                                                               | It is in `LOCALES` but not `PUBLIC_LOCALES`, yet is advertised to crawlers today.                                                                                                                                                   |
| **FD-6** | Zamtel: remove from footer, or gate behind the flag? (X-08)                        | Copy currently over-claims a capability.                                                                                                                                                                                            |
| **FD-7** | Enable Vercel Web Analytics (or equivalent RUM)?                                   | Without it there is no field data for the CLAUDE.md perf budgets and no way to prioritise UX work by traffic. Budget ceiling $50/mo applies.                                                                                        |
| **FD-8** | Badge semantics: what exactly does "Verified" vs "Preferred vendor" assert? (§4.6) | Trust claim with legal/consumer-protection weight; needs a definition before it is shown publicly.                                                                                                                                  |

Existing founder actions **F4** (Zambian counsel review of legal copy — surfaced live as _"Pending legal review (F4)"_) and **F9a** (Zamtel collections) remain open and are corroborated by this audit.

---

## 8. Proposed implementation pebbles

One pebble = one branch = one PR (`M{nn}-P{nn}: {title}`), exclusive file ownership per wave.

### Wave 1 — live defects, no dependencies (fully parallel)

| Pebble       | Title                                              | Exclusive files                                                                                                                                     | Sev    |
| ------------ | -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| **P-I18N-1** | Eliminate live `INVALID_MESSAGE` on `/` and `/c/*` | `packages/i18n/src/request.ts`, `packages/i18n/src/deep-merge.ts`, new `packages/i18n/src/icu-parse.test.ts`, new SSR smoke test in `apps/customer` | **P0** |
| **P-SEO-5**  | Fix OG image crash on bare call                    | `apps/customer/app/[locale]/(shop)/opengraph-image.tsx` (+ test)                                                                                    | P1     |
| **P-UX-2**   | Move `SERVICE_VERTICALS` off the client boundary   | `services/page.tsx`, `services/_components/vertical-filter-chips.tsx`, new `services/_lib/verticals.ts`                                             | P2     |
| **P-SEC-1**  | Stop serving literal `{{CSP_NONCE}}`               | `apps/customer/next.config.ts` (+ test)                                                                                                             | P3     |

> **P-I18N-1 must land first in review order** — it is the only P0 that is a _code_ defect (X-01 is an ops gap). It requires `pnpm i`; budget for that.

### Wave 2 — SEO correctness (needs FD-2 for host; otherwise parallel)

| Pebble      | Title                                        | Exclusive files                                                            | Depends on       |
| ----------- | -------------------------------------------- | -------------------------------------------------------------------------- | ---------------- |
| **P-SEO-1** | Absolute canonical + `metadataBase`          | `packages/ui/src/seo/json-ld.tsx`, `apps/customer/app/[locale]/layout.tsx` | FD-2             |
| **P-SEO-2** | Disable next-intl `alternateLinks`           | `apps/customer/middleware.ts`, `apps/customer/middleware.test.ts`          | FD-2, FD-4, FD-5 |
| **P-SEO-6** | Single `User-agent: *` group; host alignment | `apps/customer/app/robots.ts` (or equivalent) + Cloudflare config note     | FD-2, FD-3       |

> P-SEO-1 and P-SEO-2 touch disjoint files and may run concurrently, but **both must be verified together** — they are the two halves of one hreflang/canonical story.

### Wave 3 — hub-page enrichment (one file each; fully parallel)

| Pebble       | Title                                                        | Exclusive files              |
| ------------ | ------------------------------------------------------------ | ---------------------------- |
| **P-SEO-4a** | `ItemList`/`Event` JSON-LD + `og:image` on events            | `(shop)/events/page.tsx`     |
| **P-SEO-4b** | `ItemList`/`LocalBusiness` JSON-LD + `og:image` on directory | `(shop)/directory/page.tsx`  |
| **P-SEO-4c** | JSON-LD + `og:image` on services                             | `(shop)/services/page.tsx`   |
| **P-SEO-4d** | JSON-LD + `og:image` on categories                           | `(shop)/categories/page.tsx` |

Depends on **P-SEO-1** (needs absolute URLs) and, for services, **P-UX-2** (same file — must not overlap; sequence P-UX-2 → P-SEO-4c).

### Wave 4 — trust & IA

| Pebble        | Title                                               | Exclusive files                                                                | Depends on |
| ------------- | --------------------------------------------------- | ------------------------------------------------------------------------------ | ---------- |
| **P-TRUST-1** | Flag-derive footer payment rails                    | footer component, `packages/i18n/messages/*/legal.json`                        | FD-6       |
| **P-TRUST-2** | Define Verified / Preferred badges in-page          | `(shop)/_components/directory/*`                                               | FD-8       |
| **P-NAV-1**   | Vendor nav reaches all 35 routes; `payouts` primary | `apps/vendor/app/[locale]/_components/vendor-quick-nav.tsx` (+ overflow sheet) | —          |
| **P-NAV-2**   | Surface `compare`/`wishlist`/`calendar`             | `(shop)/layout.tsx`, `(shop)/_components/shop-header.tsx`                      | —          |
| **P-UX-1**    | Cold-start vs filtered empty states                 | PLP empty-state component + 3 hub components                                   | ADR-R02-04 |

### Wave 5 — gated on inventory (X-01) and a browser

| Pebble      | Title                                                                                                                | Depends on                                         |
| ----------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| **P-SEO-3** | Sitemap: non-empty shards + real `lastmod`                                                                           | X-01 resolved                                      |
| **R02-03**  | Browser-driven pass: 360/tablet/desktop screenshots, axe, Lighthouse, keyboard/focus, contrast, infinite scroll, LCP | X-01 + an environment with egress to `vergeo5.com` |

**R02-03 is the necessary complement to this pebble.** Roughly half the brief — visual hierarchy, contrast, keyboard/focus, responsive behaviour, feed behaviour, LCP — is structurally unanswerable from server HTML alone (§0.2), and none of it should be signed off on the strength of this document.

### Dependency graph

```
P-I18N-1 ─┐
P-SEO-5  ─┤ (Wave 1, parallel)
P-UX-2   ─┼──────────────► P-SEO-4c
P-SEC-1  ─┘
FD-2 ──► P-SEO-1 ──► P-SEO-4a / 4b / 4d
     └─► P-SEO-2
FD-3 ──► P-SEO-6
X-01 ──► P-SEO-3, R02-03
```

---

## 9. What this audit did not do

No application code, migration, workflow, config, flag, secret or infrastructure setting was touched. Nothing was deployed, seeded, merged or paid. No form was submitted, no OTP requested, no authenticated vendor/admin data accessed. No PR opened. `docs/plan/00-status.md` and `docs/plan/00-decisions.md` are unmodified; every proposed decision is a candidate ADR in §6.
