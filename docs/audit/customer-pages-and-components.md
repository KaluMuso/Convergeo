# Customer Application — Pages & Components Audit

**Application:** Customer (`apps/customer`)  
**Base URL:** `https://www.vergeo5.com/{locale}`  
**Locales:** `en`, `bem`, `nya`, `fr`, `zh`

---

## Route inventory (58 pages)

Route groups `(shop)`, `(auth)`, `(marketing)`, `(dev)` are omitted from URLs.

### Commerce & discovery `(shop)`

| Route                                  | Page name           | Source file                                  | Rendering             | Access         | Data source                       | Current state                         |
| -------------------------------------- | ------------------- | -------------------------------------------- | --------------------- | -------------- | --------------------------------- | ------------------------------------- |
| `/[locale]`                            | Homepage            | `app/[locale]/(shop)/page.tsx`               | Server                | Public         | API `/merch/slots`, catalog       | **Working**                           |
| `/[locale]/search`                     | Search              | `(shop)/search/page.tsx`                     | Server                | Public         | `GET /search`, `/search/suggest`  | **Partial** — images broken (R-002)   |
| `/[locale]/categories`                 | Categories index    | `(shop)/categories/page.tsx`                 | Server                | Public         | Categories API                    | **Working**                           |
| `/[locale]/c/[...slug]`                | Category PLP        | `(shop)/c/[...slug]/page.tsx`                | Server                | Public         | `GET /catalog/listings`           | **Working**                           |
| `/[locale]/p/[slug]`                   | Product detail      | `(shop)/p/[slug]/page.tsx`                   | Server                | Public         | `GET /products/{slug}`            | **Working**                           |
| `/[locale]/compare`                    | Comparison          | `(shop)/compare/page.tsx`                    | Server                | Public         | `GET /products/{slug}/comparison` | **Working**                           |
| `/[locale]/cart`                       | Cart                | `(shop)/cart/page.tsx`                       | Server shell + client | Public         | `GET /cart`                       | **Broken** — localhost API (R-001)    |
| `/[locale]/checkout`                   | Checkout            | `(shop)/checkout/page.tsx`                   | Server                | Auth preferred | Checkout session APIs             | **BLOCKED_UNSAFE** without login      |
| `/[locale]/checkout/card/[paymentId]`  | Card payment return | `(shop)/checkout/card/[paymentId]/page.tsx`  | Client                | Public         | Lenco verify                      | CSP expanded in middleware            |
| `/[locale]/checkout/pending/[groupId]` | USSD wait           | `(shop)/checkout/pending/[groupId]/page.tsx` | Server                | Public         | `GET /payments/status`            | **Working** (code)                    |
| `/[locale]/directory`                  | Vendor directory    | `(shop)/directory/page.tsx`                  | Server                | Public         | `GET /directory`                  | **Working**                           |
| `/[locale]/v/[slug]`                   | Vendor profile      | `(shop)/v/[slug]/page.tsx`                   | Server                | Public         | `GET /directory/{slug}`           | **Working**                           |
| `/[locale]/services`                   | Services browse     | `(shop)/services/page.tsx`                   | Server                | Public         | `GET /services`                   | **Working**                           |
| `/[locale]/services/post-job`          | Post RFQ job        | `(shop)/services/post-job/page.tsx`          | Server                | Public         | `POST /jobs`                      | **Working** (auth at submit)          |
| `/[locale]/s/[slug]`                   | Service detail      | `(shop)/s/[slug]/page.tsx`                   | Server                | Public         | `GET /services/{slug}`            | **Working**                           |
| `/[locale]/events`                     | Events browse       | `(shop)/events/page.tsx`                     | Server                | Public         | `GET /events`                     | **Working**                           |
| `/[locale]/e/[slug]`                   | Event detail        | `(shop)/e/[slug]/page.tsx`                   | Server                | Public         | `GET /events/{slug}`              | **Working**                           |
| `/[locale]/supplies`                   | B2B supplies        | `(shop)/supplies/page.tsx`                   | Server                | B2B gated      | `GET /business/status`            | **Partial** — needs verified business |
| `/[locale]/wishlist`                   | Wishlist            | `(shop)/wishlist/page.tsx`                   | Server                | Soft auth      | `GET/PUT /account/wishlist`       | **Working**                           |
| `/[locale]/ask`                        | Ask Vergeo AI       | `(shop)/ask/page.tsx`                        | Server                | Public         | `POST /ask`                       | **Working**                           |
| `/[locale]/calendar`                   | Calendar            | `(shop)/calendar/page.tsx`                   | Server                | Redirect       | → `/events?date_window=all`       | **Redirect only**                     |

### Authentication `(auth)`

| Route                              | Source                                   | Rendering | Access             |
| ---------------------------------- | ---------------------------------------- | --------- | ------------------ |
| `/[locale]/login`                  | `(auth)/login/page.tsx`                  | Server    | Public             |
| `/[locale]/signup`                 | `(auth)/signup/page.tsx`                 | Server    | Public             |
| `/[locale]/otp`                    | `(auth)/otp/page.tsx`                    | Server    | Requires `?phone=` |
| `/[locale]/reset-password`         | `(auth)/reset-password/page.tsx`         | Server    | Public             |
| `/[locale]/reset-password/confirm` | `(auth)/reset-password/confirm/page.tsx` | Server    | Public             |
| `/[locale]/welcome`                | `(auth)/welcome/page.tsx`                | Server    | **Auth required**  |

### Marketing & legal

| Route                            | Source                         | Access                       |
| -------------------------------- | ------------------------------ | ---------------------------- |
| `/[locale]/about`                | `(marketing)/about/page.tsx`   | Public                       |
| `/[locale]/sell`                 | `(marketing)/sell/page.tsx`    | Public — vendor recruitment  |
| `/[locale]/beta`                 | `(marketing)/beta/page.tsx`    | Public — beta gate           |
| `/[locale]/contact`              | `(marketing)/contact/page.tsx` | Public — `POST /api/contact` |
| `/[locale]/help`, `/help/[slug]` | `(marketing)/help/`            | Public                       |
| `/[locale]/legal/*`              | `(marketing)/legal/`           | Public                       |
| `/[locale]/terms`, `/privacy`    | Aliases → `/legal/*`           | Redirect                     |

### Account (auth via layout)

All under `app/[locale]/account/` — protected by `requireAuthenticatedAccount()` in `account/layout.tsx`.

| Route                  | Source                              | Key APIs                      |
| ---------------------- | ----------------------------------- | ----------------------------- |
| `/account`             | `account/page.tsx`                  | Profile overview              |
| `/account/profile`     | `account/profile/page.tsx`          | `GET/PATCH /account/profile`  |
| `/account/addresses`   | `account/addresses/page.tsx`        | Address CRUD                  |
| `/account/preferences` | `account/preferences/page.tsx`      | Preferences                   |
| `/account/privacy`     | `account/privacy/page.tsx` (client) | Export/delete                 |
| `/account/orders`      | `account/orders/page.tsx`           | `GET /account/orders`         |
| `/account/orders/[id]` | `account/orders/[id]/page.tsx`      | Order detail, dispute, return |
| `/account/jobs`        | `account/jobs/page.tsx`             | RFQ jobs                      |
| `/account/tickets`     | `account/tickets/page.tsx`          | Event tickets wallet          |
| `/account/business`    | `account/business/page.tsx`         | B2B apply                     |
| `/account/recent`      | `account/recent/page.tsx`           | Recently viewed               |
| `/account/wishlist`    | Redirect to shop wishlist           | —                             |

### Special routes

| Route                 | File                   | Purpose                              |
| --------------------- | ---------------------- | ------------------------------------ |
| `/[locale]/offline`   | `offline/page.tsx`     | PWA offline fallback (client)        |
| `/[locale]/ui`        | `(dev)/ui/page.tsx`    | Design preview — **blocked in prod** |
| `/[locale]/[...rest]` | `[...rest]/page.tsx`   | Catch-all 404                        |
| `/[locale]/health`    | `health/route.ts`      | Health check                         |
| `/api/contact`        | `api/contact/route.ts` | Resend email                         |
| `/sitemap.xml`        | `sitemap.xml/route.ts` | SEO                                  |

---

## Component inventory

**Note:** No top-level `apps/customer/components/` — all UI in `app/**/_components` (26 directories, 80+ shop components).

### Navigation & chrome

| Component          | File                                        | Used on        | Client/Server |
| ------------------ | ------------------------------------------- | -------------- | ------------- |
| Shop header        | `(shop)/_components/shop-header.tsx`        | Shop layout    | Client        |
| Bottom nav         | `(shop)/_components/bottom-nav-client.tsx`  | Shop layout    | Client        |
| Category mega menu | `(shop)/_components/category-mega-menu.tsx` | Header         | Client        |
| Locale switcher    | `[locale]/_components/locale-switcher.tsx`  | Footer         | Client        |
| Account nav        | `account/_components/account-nav.tsx`       | Account layout | Client        |

### Product & discovery

| Component            | File                                      | API dependency                |
| -------------------- | ----------------------------------------- | ----------------------------- |
| Listing card/grid    | `(shop)/_components/plp/listing-card.tsx` | Catalog/search                |
| PDP gallery, buy box | `(shop)/_components/pdp/*`                | `/products/{slug}`            |
| Search input/results | `(shop)/_components/search/*`             | `/search`                     |
| Compare table        | `(shop)/_components/pdp/comparison.tsx`   | `/products/{slug}/comparison` |
| Ask thread           | `(shop)/_components/ask/ask-thread.tsx`   | `POST /ask`                   |

### Cart & checkout

| Component        | File                                           | Risk                                         |
| ---------------- | ---------------------------------------------- | -------------------------------------------- |
| Mini cart drawer | `(shop)/_components/cart/mini-cart-drawer.tsx` | Uses `getApiBaseUrl()` — **P0 if env wrong** |
| Vendor groups    | `(shop)/_components/cart/vendor-groups.tsx`    | Cart page host                               |
| Checkout steps   | `(shop)/checkout/_components/step-*.tsx`       | Payment honesty                              |
| USSD wait        | `(shop)/checkout/_components/ussd-wait.tsx`    | MoMo push state                              |

### States & trust

| Component          | Package/file                         | Notes                            |
| ------------------ | ------------------------------------ | -------------------------------- |
| EmptyState         | `@vergeo/ui/empty-state`             | Used cart, search zero-results   |
| Skeleton           | `@vergeo/ui/skeleton`                | PLP, PDP loading                 |
| Error boundary     | `[locale]/error.tsx`                 | Branded errors                   |
| Demo listing badge | `(shop)/_components/demo-listing.ts` | Hides Cloudinary `demo/` in prod |

### Shared design system (`packages/ui` — 60 components)

Key customer-facing: `product-card`, `vendor-card`, `event-card`, `service-card`, `price-block`, `star-rating`, `bottom-nav`, `app-header`, `footer`, `cloudinary-image`, `modal`, `confirm-dialog`, `toast`, `pagination`, `search-field`, `otp-field`, hero variants under `merch/`.

---

## Unreachable / duplicate routes

| Route                             | Issue                                               |
| --------------------------------- | --------------------------------------------------- |
| `/calendar`                       | Redirect only — linked in robots disallow           |
| `/terms`, `/privacy`              | Permanent redirect to `/legal/*`                    |
| `/ui`                             | `notFound()` unless `NEXT_PUBLIC_ENABLE_UI_PREVIEW` |
| Account wishlist vs shop wishlist | Possible duplication — account may redirect         |

---

## Production evidence

| Check               | Result                                       |
| ------------------- | -------------------------------------------- |
| Homepage `GET /en`  | 200, carousel renders                        |
| Search `?q=phone`   | 200, **placeholder images**                  |
| Cart `/en/cart`     | Error UI, **localhost:8000/cart** in network |
| Bemba `/bem`        | Translations render correctly                |
| Health `/en/health` | 200                                          |

See [ui-ux-browser-audit.md](./ui-ux-browser-audit.md) for full browser findings.
