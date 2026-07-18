# Customer panel change report — 2026-07-18

**Branch:** `cursor/panel-customer-a8a6`  
**PR:** https://github.com/KaluMuso/Convergeo/pull/289  
**Scope:** `apps/customer` + customer-required `packages/i18n` strings + colocated tests  
**Out of scope (honoured):** DB schema, payment provider config, vendor/admin apps, deployment/Vercel env

---

## Changed files

| Path                                                                        | Change                                                             |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `apps/customer/app/[locale]/(shop)/categories/page.tsx`                     | **CUST-03** locale categories browse from live Supabase tree       |
| `apps/customer/app/[locale]/(shop)/categories/categories-page.test.ts`      | Tree / empty-state unit coverage                                   |
| `apps/customer/app/[locale]/(shop)/compare/page.tsx`                        | **CUST-04** compare route + honest empty/unavailable/single-seller |
| `apps/customer/app/[locale]/(shop)/compare/_components/compare-results.tsx` | Client wrapper for PDP comparison table                            |
| `apps/customer/app/[locale]/(shop)/compare/compare-page.test.ts`            | Slug validation + multi-listing gate tests                         |
| `apps/customer/app/[locale]/(shop)/calendar/page.tsx`                       | **CUST-10** permanent redirect → `/events?date_window=all`         |
| `apps/customer/app/[locale]/(shop)/calendar/calendar-page.test.ts`          | Redirect target contract                                           |
| `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx`                       | PDP “Compare sellers” entry when `listing_count > 1`               |
| `apps/customer/app/[locale]/(shop)/_components/category-mega-menu.tsx`      | “View all categories” → `/categories`                              |
| `apps/customer/app/[locale]/(shop)/_components/category-mega-menu.test.tsx` | Assert view-all href                                               |
| `apps/customer/app/[locale]/(shop)/_components/desktop-header.tsx`          | Pass `viewAllCategories` label                                     |
| `apps/customer/app/[locale]/(shop)/layout.tsx`                              | Wire mega-menu label                                               |
| `apps/customer/app/[locale]/(shop)/_components/merch-data.ts`               | Export `fetchCategories` for browse page                           |
| `apps/customer/app/[locale]/(shop)/checkout/_lib/payment-outcome.ts`        | **CUST-08** card/MoMo outcome rules (no false success)             |
| `apps/customer/app/[locale]/(shop)/checkout/_lib/payment-outcome.test.ts`   | Failure-path outcome tests                                         |
| `apps/customer/app/[locale]/(shop)/checkout/card/[paymentId]/page.tsx`      | Success only if `order_confirmed`; API fail-closed                 |
| `apps/customer/app/[locale]/(shop)/checkout/_components/ussd-wait.tsx`      | Confirming state (not paid claim); API fail-closed                 |
| `apps/customer/app/[locale]/(shop)/checkout/pending/[groupId]/page.tsx`     | Confirming i18n labels                                             |
| `apps/customer/lib/api-base-url.ts`                                         | Production never falls back to `localhost:8000`                    |
| `apps/customer/lib/api-base-url.test.ts`                                    | Prod/dev resolution tests                                          |
| `apps/customer/sw.ts` / `sw.test.ts`                                        | Catalog cache pattern includes new routes                          |
| `packages/i18n/messages/{en,fr,zh}/catalog.json`                            | Browse/compare copy + **CUST-07** hero logistics wording           |
| `packages/i18n/messages/{en,fr,zh}/checkout.json`                           | Confirming + order-confirmed success copy                          |

---

## Evidence-backed requirements implemented

| Backlog ID         | Pri | Evidence (from panel-backlogs / release-gates)         | Implementation                                                                                                                                                         | Acceptance met?                                                                                           |
| ------------------ | --- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **CUST-03**        | P1  | product RB-PS-012: `/en/categories` 404; depends: none | New SSG route; tree via public RLS `categories` read (same source as mega-menu/home)                                                                                   | **Yes (code)** — `/en/categories` builds; navigable roots+children; empty state when tree empty           |
| **CUST-04**        | P1  | `/en/compare` 404; comparison API PARTIAL              | Route + PDP entry; uses `GET /products/{slug}/comparison`; empty/single-seller/unavailable honest                                                                      | **Yes (code)** — usable when ≥2 listings; honest empty otherwise (ops seed still needed for demo density) |
| **CUST-07**        | P1  | blueprint BL-P1-06 superseded stack/logistics claims   | Hero subtitle no longer implies “fast delivery” fleet; locked Lusaka delivery / nationwide pickup                                                                      | **Yes** — banned Yango/Django/Meilisearch/own-fleet/direct-telco absent; soft delivery claim tightened    |
| **CUST-08**        | P0* | foundation R2; G4 false-success; MR-B01                | Card: `resolveCardVerifyViewState` requires `order_confirmed`. MoMo: payment `success` → confirming + order redirect, never `payment-success` paid claim. COD separate | **Partial** — UI hardened with live contracts; full ledger confirmation still needs API MR-B01            |
| **CUST-10**        | P2  | events F027 `/en/calendar` 404                         | Permanent redirect to events date browse                                                                                                                               | **Yes** — no dead calendar 404; no fake calendar grid                                                     |
| **G2 / localhost** | P0  | release-gates G2; mandatory check                      | Checkout paths use `resolveApiBaseUrl()` (null in prod if unset). Vendor CTA already fail-closed (CUST-01 code)                                                        | **Yes (code)** — no new localhost portal links; prod API unset → error/unavailable, not loopback          |

### Mandatory checks (task brief)

| Check                                                  | Status                                                                                   |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Never display fake checkout/payment success            | **Met in UI** — card success gated on `order_confirmed`; MoMo shows confirming, not paid |
| Remove production localhost / invalid portal fallbacks | **Met for touched paths** — API base fail-closed; sell CTA pre-existing fail-closed      |
| Preserve auth / a11y / loading / empty / error / retry | Preserved on pending shell, card page, categories/compare empties                        |
| No mock data as API substitute                         | Categories from Supabase; compare from live comparison API or honest empty               |
| Tests for changed critical flows                       | Added/extended (see below)                                                               |

---

## Tests run / results

| Command                                              | Result                                                                                                                          |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm --filter customer lint`                        | **PASS**                                                                                                                        |
| `pnpm --filter customer typecheck`                   | **PASS**                                                                                                                        |
| `pnpm --filter customer test`                        | **PASS** — 36 files / **207** tests                                                                                             |
| `NODE_ENV=production … pnpm --filter customer build` | **PASS** — includes `/[locale]/categories`, `/compare`, `/calendar`; `public/sw.js` emitted (gitignored build artifact, ~51 KB) |

New / adjusted critical-flow tests:

- `checkout/_lib/payment-outcome.test.ts` — success only with `order_confirmed`; MoMo confirming ≠ paid; COD isolation
- `lib/api-base-url.test.ts` — production null vs dev localhost
- `categories-page.test.ts`, `compare-page.test.ts`, `calendar-page.test.ts`
- mega-menu view-all link; SW catalog routes for new paths

---

## Deferred dependencies

| Item                                  | Why deferred                                                                                                                     | Owner            |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| **CUST-01** seller CTA live           | Needs Vercel `NEXT_PUBLIC_VENDOR_APP_URL=https://vendor.vergeo5.com` + redeploy; code already fail-closed (no localhost in prod) | Founder / Vercel |
| **CUST-02** demo catalogue disclosure | Merch decision MR-D01 (label vs exclude); not unilaterally decided here                                                          | Merch / Founder  |
| **CUST-05** SW 200 on production      | Serwist wired; `sw.js` generated by production build; live probe needs deploy                                                    | Deploy           |
| **CUST-06** Events Phase-1 lenses     | Depends on events supply + MR-W02 for paid                                                                                       | Ops / Events     |
| **CUST-08 full / CUST-09 escrow**     | Ledger post confirmation not on payment-status contract (MR-B01 / MR-W01)                                                        | Payments / API   |
| **CUST-11** Lighthouse budgets        | Egress / CI advisory                                                                                                             | Perf             |
| **CUST-12** wishlist                  | Hearts already gated off without handler; persistence API OUT — no half-affordance shipped                                       | Product (OUT)    |

---

## Release risks

1. **G4 still FAIL until MR-B01** — UI no longer claims paid on provider success alone, but MoMo status `success` still redirects to the order page without a ledger field on `/payments/status`. Residual risk: buyer may infer payment complete from order page if order copy is optimistic.
2. **CUST-01 / G10 still FAIL in production** until vendor env is set — marketing `/sell` page works; signup CTA stays “temporarily unavailable” by design.
3. **Demo catalogue (CUST-02 / G11)** still public — this PR does not label or hide `demo/` imagery.
4. **Compare density** depends on multi-listing seed; empty/single-seller states are honest but UX may look sparse until ops seed.
5. **SW installability** requires a production deploy that includes the serwist-generated `public/sw.js` (confirmed locally in this build).

**Deploy:** not performed (per brief).
