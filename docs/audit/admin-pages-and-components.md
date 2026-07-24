# Admin Application — Pages & Components Audit

**Application:** Admin (`apps/admin`)  
**Base URL:** `https://admin.vergeo5.com/{locale}`  
**Auth:** Cloudflare Access (production) + Supabase `admin` role

---

## Route inventory (22 pages)

| Route                             | Page name             | Source file                      | Rendering       | APIs                                    | State                     |
| --------------------------------- | --------------------- | -------------------------------- | --------------- | --------------------------------------- | ------------------------- |
| `/[locale]`                       | Dashboard             | `app/[locale]/page.tsx`          | Server→Client   | `GET /admin/dashboard`                  | Working (needs auth)      |
| `/[locale]/login`                 | Login                 | `(auth)/login/page.tsx`          | Server          | Supabase                                | Behind CF Access          |
| `/[locale]/kyc`                   | KYC queue             | `kyc/page.tsx`                   | Server→Client   | `GET /admin/kyc`                        | Working                   |
| `/[locale]/kyc/[id]`              | KYC review            | `kyc/[id]/page.tsx`              | Server→Client   | Approve/reject/suspend                  | Working                   |
| `/[locale]/business`              | B2B buyers queue      | `business/page.tsx`              | Server→Client   | `GET /admin/business`                   | Working                   |
| `/[locale]/moderation`            | Moderation hub        | `moderation/page.tsx`            | Server          | Links only                              | Working                   |
| `/[locale]/moderation/products`   | Product moderation    | `moderation/products/page.tsx`   | Server→Client   | Duplicates, merge, relations            | Working                   |
| `/[locale]/moderation/flags`      | Content flags         | `moderation/flags/page.tsx`      | Server→Client   | `GET /admin/flags`                      | Working                   |
| `/[locale]/disputes`              | Dispute queue         | `disputes/page.tsx`              | Server→Client   | `GET /admin/disputes`                   | Working                   |
| `/[locale]/disputes/[id]`         | Dispute decision      | `disputes/[id]/page.tsx`         | Server→Client   | `POST .../decide`                       | Working                   |
| `/[locale]/orders`                | Order search          | `orders/page.tsx`                | Server→Client   | `GET /admin/orders/search`              | Working                   |
| `/[locale]/orders/[id]`           | Order intervention    | `orders/[id]/page.tsx`           | Server→Client   | Escrow, dispatch, intervene             | Working                   |
| `/[locale]/config`                | Config hub            | `config/page.tsx`                | Server          | Links                                   | Working                   |
| `/[locale]/config/flags`          | Feature flags         | `config/flags/page.tsx`          | Server→Client   | PATCH flags                             | Working                   |
| `/[locale]/config/commissions`    | Commissions           | `config/commissions/page.tsx`    | Server→Client   | PATCH commissions                       | Working                   |
| `/[locale]/config/delivery-zones` | Delivery zones        | `config/delivery-zones/page.tsx` | Server→Client   | PATCH zones                             | Working                   |
| `/[locale]/config/categories`     | Category tree         | `config/categories/page.tsx`     | Server→Client   | CRUD + reorder                          | Working                   |
| `/[locale]/config/platform`       | Platform config       | `config/platform/page.tsx`       | Server→Client   | PATCH platform                          | Working                   |
| `/[locale]/merch`                 | Merchandising         | `merch/page.tsx`                 | Server→Client   | Slots, hero, mega menu                  | Working                   |
| `/[locale]/theme`                 | Theme presets         | `theme/page.tsx`                 | **Server only** | None — read-only                        | INFO — deploy to activate |
| `/[locale]/translations`          | Translation overrides | `translations/page.tsx`          | Server→Client   | `GET/PUT /admin/translations/overrides` | Working                   |
| `/[locale]/support`               | Support inbox         | `support/page.tsx`               | Server→Client   | Lookup, send, log                       | Working                   |

**Not implemented in UI (API exists):** audit logs browser, automation monitoring, user management, vendor management (governance API exists), reports, security settings, feature-flag A/B beyond config.

---

## Shell components

| Component          | File                               | Notes                                      |
| ------------------ | ---------------------------------- | ------------------------------------------ |
| AdminShell         | `_components/admin-shell.tsx`      | 11-item sidebar                            |
| DashboardBoard     | `_components/DashboardBoard.tsx`   | GMV, orders, payouts, reconciliation tiles |
| AdminLoadFailure   | `_components/AdminLoadFailure.tsx` | Permission vs retryable                    |
| dashboard-truth.ts | `_components/dashboard-truth.ts`   | No fake reconciliation "balanced" state    |

### Dashboard tiles

`GmvTile`, `OrdersStatusTile`, `PayoutLiabilitiesTile`, `ReconciliationTile`, `CatalogCountsTile`, `AiUsageTile`, `FunnelTile`

---

## Security layers

1. **Cloudflare Access** — `Cf-Access-Jwt-Assertion` verified via JWKS (`lib/cf-access.ts`)
2. **Dev bypass** — `NEXT_PUBLIC_ADMIN_BYPASS=true` + non-production only
3. **Supabase middleware** — `admin` role required
4. **API** — `require_role("admin")` on all `/admin/*` routes
5. **CSP** — Stricter than customer; `frame-ancestors 'none'`
6. **robots.txt** — `disallow: /`

---

## API base URL

Admin uses `NEXT_PUBLIC_VERGEO_API_URL` (not `NEXT_PUBLIC_API_BASE_URL`). Fails closed in production if unset.

---

## Production evidence

- `GET https://admin.vergeo5.com/en/health` → 302 (CF Access)
- Login redirects to Cloudflare Access gate
- Production API: `GET /admin/dashboard` → **401** without token (route exists per OpenAPI)

---

## Gaps vs requested admin areas

| Requested area              | Status                                                 |
| --------------------------- | ------------------------------------------------------ |
| User management             | **NOT_IMPLEMENTED** in admin UI                        |
| Vendor management (non-KYC) | Partial — governance API only                          |
| Payment monitoring          | Partial — dashboard + order detail                     |
| Refunds UI                  | **NOT_IMPLEMENTED** — API `POST /refunds/execute` only |
| Audit logs UI               | **NOT_IMPLEMENTED**                                    |
| Automation monitoring       | **NOT_IMPLEMENTED**                                    |
| Roles & permissions UI      | **NOT_IMPLEMENTED** — single admin role                |
| System health               | Partial — dashboard tiles only                         |
