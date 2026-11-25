# T32 customer polish — screenshots

Captured with `docs/ops/screenshots/harness` (loopback Supabase Auth + API fixtures, signed in as a customer where marked) against `next dev` on `cursor/customer-polish`. Every route at 360×780 and 1280×800 (home 1000–1400 tall), light and dark, WebP ≤80 KB. No dev-overlay issues on any capture.

| Route                  | Files          | Signed in | Notes                                           |
| ---------------------- | -------------- | --------- | ----------------------------------------------- |
| `/en`                  | `home-*`       | no        | Hero illustration, rails from fixtures          |
| `/en` (API empty/down) | `home-empty-*` | no        | Every API call 404s; illustrated empty rails    |
| `/en/account`          | `account-*`    | yes       |                                                 |
| `/en/account/orders`   | `orders-*`     | yes       | Paid (escrow), on the way, delivered, cancelled |
| `/en/cart`             | `cart-*`       | yes       | 3 items from 2 sellers                          |
| `/en/vendors`          | `vendors-*`    | no        |                                                 |
| `/en/search?q=laptop`  | `search-*`     | no        |                                                 |
| `/en/categories`       | `categories-*` | no        |                                                 |
| `/en/help`             | `help-*`       | no        |                                                 |

Out of scope in this pass: product, service and event detail pages (`p/`, `s/`, `e/`, `_components/pdp`) while #889 and #890 are open.
