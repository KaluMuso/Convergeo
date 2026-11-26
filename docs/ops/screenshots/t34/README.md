# T34 admin polish — screenshots

Captured with `docs/ops/screenshots/harness` (loopback Supabase Auth + API fixtures) against `next dev` on `cursor/admin-polish`, signed in as a superadmin. In `next dev` Cloudflare Access is not enforced; the middleware role gate still runs on the verified token. Every route at 360×780 and 1280×800, light and dark, WebP ≤80 KB. No dev-overlay issues on any capture.

| Route                      | Files        | Notes                                                                     |
| -------------------------- | ------------ | ------------------------------------------------------------------------- |
| `/en`                      | `overview-*` | Today board, reconciliation, payout liabilities, orders by status         |
| `/en/kyc`                  | `kyc-*`      | Pending vendor applications; phone card layout under `sm`                 |
| `/en/trials`               | `vendors-*`  | Every seller with plan/trial state (the console has no other seller list) |
| `/en/orders?status=placed` | `orders-*`   | The page lists results only after a search; filtered to placed            |
| `/en/login`                | `login-*`    | Signed out                                                                |
