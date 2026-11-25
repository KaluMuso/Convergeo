# T33 vendor polish — screenshots

Captured with `docs/ops/screenshots/harness` (loopback Supabase Auth + API fixtures) against `next dev` on `cursor/vendor-polish`, signed in as a KYC-approved vendor ("Mwila's Phone Hub", Cairo Road). Every route at 360×780 and 1280×800, light and dark, WebP ≤80 KB. No dev-overlay issues on any capture.

| Route           | Files         | Notes                                                        |
| --------------- | ------------- | ------------------------------------------------------------ |
| `/en`           | `home-*`      | Stat cards, quick actions, next steps, orders to action      |
| `/en/listings`  | `products-*`  |                                                              |
| `/en/orders`    | `orders-*`    | Queue in mixed states                                        |
| `/en/profile`   | `profile-*`   |                                                              |
| `/en/payouts`   | `payouts-*`   | Needs `NEXT_PUBLIC_VENDOR_PAYOUTS_ENABLED=true` (pilot flag) |
| `/en/analytics` | `analytics-*` |                                                              |
| `/en/login`     | `login-*`     | Signed out                                                   |
