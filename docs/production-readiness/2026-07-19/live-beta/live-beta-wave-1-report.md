# Live Beta Wave 1 Report — 2026-07-19

**Branch:** `cursor/live-beta-wave-1-0d65`  
**Scope:** Customer discovery/trust/conversion + vendor/admin fail-closed API bases + admin nav hubs + live-beta docs  
**Not done:** production deploy, `0056`, payment enablement, staging plane, wishlist/RBAC

---

## Summary

Wave 1 implements the highest-value P0/P1 frontend work that does not require migrations or real-money enablement. Categories 500 remains a **production deploy drift** issue (#298 already on master); this PR keeps that fix and hardens surrounding discovery/conversion honesty so Preview and the next production promotion are beta-ready.

---

## Backlog items shipped

| ID       | Item                                                              | Status                                         |
| -------- | ----------------------------------------------------------------- | ---------------------------------------------- |
| LB-P0-02 | Customer fail-closed API base (cart/checkout/PLP/search/PDP/shop) | Done                                           |
| LB-P0-03 | Search + PLP empty ≠ unavailable                                  | Done                                           |
| LB-P0-04 | Vendor fail-closed API base                                       | Done                                           |
| LB-P0-05 | Admin fail-closed API base                                        | Done                                           |
| LB-P0-06 | Soften “verified vendors” overclaim (copy)                        | Done (badge gate remains Wave 2 / post-`0056`) |
| LB-P1-01 | Mobile categories bottom-nav; remove duplicate Account tab        | Done                                           |
| LB-P1-02 | Live cart badge on mobile TopNav                                  | Done                                           |
| LB-P1-03 | Product card null-slug no longer links to `/c/all`                | Done                                           |
| LB-P1-04 | PDP loading/error ≠ “coming soon”                                 | Done                                           |
| LB-P1-05 | Search suggestion terms i18n (en/fr/zh)                           | Done                                           |
| LB-P1-06 | Services rail title without false geo                             | Done                                           |
| LB-P1-07 | Admin Moderation + Config hub pages                               | Done                                           |
| LB-P0-01 | Promote categories fix to production                              | **Ops** — checklist only                       |

---

## Key code changes

- `apps/customer/.../layout.tsx` + `mobile-top-nav.tsx` — categories tab + live cart count
- `apps/customer/.../c/[...slug]/page.tsx` — unavailable EmptyState + fail-closed API
- `apps/customer/.../search/page.tsx` — unavailable EmptyState + i18n suggestions
- `apps/customer/.../plp/listing-grid.tsx` — null-slug safety
- `apps/customer/.../pdp/buy-box.tsx` — adding / error labels
- `apps/customer/lib/api-base-url.ts` — used across conversion-critical shop clients
- `apps/vendor/lib/api-base-url.ts` — replaces localhost fallbacks
- `apps/admin/lib/api-base-url.ts` + `moderation/page.tsx` + `config/page.tsx`
- `packages/i18n/messages/{en,fr,zh}/{catalog,search,admin,marketing,directory}.json`

---

## Verification

| Check                                             | Result                                                                                    |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `pnpm --filter customer lint`                     | PASS                                                                                      |
| `pnpm --filter vendor lint`                       | PASS                                                                                      |
| `pnpm --filter admin lint`                        | PASS (3 pre-existing hardcoded-string warnings in KYC DecisionPanel)                      |
| `pnpm --filter customer\|vendor\|admin typecheck` | PASS                                                                                      |
| `pnpm --filter customer test`                     | PASS — 230 tests                                                                          |
| `pnpm --filter vendor test`                       | PASS — 85 tests                                                                           |
| `pnpm --filter admin test`                        | PASS — 39 tests                                                                           |
| Production builds (customer/vendor/admin)         | PASS                                                                                      |
| Local `next start` `/en\|fr\|zh/categories`       | **200**, `categories-unavailable-upstream` (dummy Supabase) — **not** digest `3012388270` |
| Local PLP `/en/c/electronics`                     | **200**, listings from live API                                                           |
| Local search `?q=phone`                           | **200**                                                                                   |
| Localhost in HTML                                 | **0** on sampled local pages                                                              |
| Production deploy                                 | **Not performed**                                                                         |

---

## Preview URLs

Filled after push / Vercel Preview READY (see PR description). Expected pattern:

- Customer: `https://convergeo-customer-*-vergeo-projects.vercel.app`
- Vendor: `https://convergeo-vendor-*-vergeo-projects.vercel.app`
- Admin: `https://convergeo-admin-*-vergeo-projects.vercel.app` (Access may still challenge)

---

## Recommended Wave 2 (independent PRs)

### Customer

1. CUST-01 — set `NEXT_PUBLIC_VENDOR_APP_URL` + re-probe sell CTA
2. Storefront verified/preferred badge honesty after KYC API live (`CUST-13`)
3. Investigate intermittent search 500 seen once in headed browser (runtime logs)
4. Cart free-delivery nudge honesty vs zone fees
5. Optional `/privacy` → `/legal/privacy` redirects

### Vendor

1. Services / jobs EmptyState + ErrorState + retry parity
2. Returns / disputes / reviews queue honesty parity
3. Listings manage: pause/unpause from list

### Admin

1. Permission-denied parity on KYC / disputes / flags / business / support
2. Empty vs error copy on those queues
3. MerchBoard customer URL fail-closed (still has `localhost:3000` residual)

### Operations

1. Promote Wave 1 + categories fix to customer production aliases
2. Re-probe en/fr/zh `/categories` → 200
3. Do **not** apply `0056` or enable prepaid until staging evidence + FD-12
4. Sentry DSNs + uptime monitors + backup proof

---

## Production rollout checklist (frontend only)

1. Merge this PR after Preview sign-off.
2. Confirm `convergeo-customer` production deploy SHA includes Wave 1 (≥ tip with categories fix).
3. Probe `https://www.vergeo5.com/{en,fr,zh}/categories` → **200**, no digest `3012388270`.
4. Probe home, PLP, PDP, search, cart, sell — no localhost; honest empty/unavailable.
5. Confirm vendor/admin production deploys include fail-closed API base.
6. **Do not** flip money flags or `public_launch`.
7. **Do not** apply migration `0056` in this rollout.
8. File post-deploy note under `docs/production-readiness/2026-07-19/production/`.
