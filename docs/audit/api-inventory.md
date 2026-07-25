# API Inventory

**Source of truth (production):** `GET https://api.vergeo5.com/openapi.json`  
**Captured:** 2026-07-24 — **256 paths, 287 operations**  
**CI authz matrix:** 227 route×method entries (`services/api/tests/test_authz_matrix.py`)

Full machine-readable list: [`inventory.json`](./inventory.json) → `api_endpoints`

---

## Summary by auth class

| Auth class       | Count | Description                                         |
| ---------------- | ----- | --------------------------------------------------- |
| `public-open`    | 33    | No bearer (cart guest, search, webhooks verify)     |
| `auth-any`       | 80    | Valid Supabase JWT                                  |
| `role`           | 76    | JWT + `customer`/`vendor`/`admin` from `user_roles` |
| `internal-token` | 34    | `X-Internal-Token` per cron                         |
| `webhook-signed` | 3     | Lenco, WhatsApp signatures                          |
| `signed-link`    | 1     | Invoice download HMAC                               |

---

## Domain inventory

### Health & ops

- `GET /healthz`, `/readyz`, `/health`, `/fingerprint` — public

### Account (`account.py`, `privacy.py`)

- Profile, addresses, preferences, onboarding, wishlist, recently-viewed, export, delete

### Cart & catalog (`cart.py`, `catalog.py`)

- Guest-capable cart CRUD, merge-on-login, revalidate
- `GET /catalog/listings`

### Checkout & orders (`checkout.py`, `checkout_payment.py`, `orders_create.py`, `customer_orders.py`)

- Multi-step checkout session, payment options, order creation
- Customer order list/detail, confirm-received, evidence

### Payments (`payment_status.py`, `payments_card.py`, `webhooks_lenco.py`)

- MoMo status polling, card session/verify, Lenco webhook

### Discovery (`products.py`, `search.py`, `directory.py`, `services_listings.py`, `events_public.py`, `comparison.py`, `ask.py`)

- PDP, search+suggest, vendor directory, services, events, Ask Vergeo RAG

### Reviews & returns (`reviews.py`, `service_reviews.py`, `returns.py`)

- Verified purchase reviews, service reviews, return lanes

### RFQ (`jobs.py`, `quotes.py`, `rfq_engagement.py`, `job_completion.py`)

- Job posting, quotes, accept, complete, confirm

### Vendor (`vendor_*.py`, `listing_*.py`, `organiser_*.py`, `ticket_*.py`, `pickup_verify.py`)

- Profile, listings CRUD/import, orders queue, payouts, analytics, events, tickets, pickup verify

### KYC & business (`kyc.py`, `kyc_media.py`, `business.py`, `beta.py`)

- Vendor KYC lifecycle, B2B buyer apply, beta invites

### Admin (67 operations in production OpenAPI)

- `/admin/dashboard`, `/admin/kyc/*`, `/admin/orders/*`, `/admin/disputes/*`
- `/admin/config/*`, `/admin/flags/*`, `/admin/products/*`, `/admin/merch/*`
- `/admin/support/*`, `/admin/business/*`, `/admin/translations/overrides`
- `/admin/search-insights/*`, `/admin/governance/vendors`

### Internal / n8n (34 operations)

| Endpoint prefix                       | Token env                        | Purpose                   |
| ------------------------------------- | -------------------------------- | ------------------------- |
| `/internal/dispatch/tick`             | `INTERNAL_DISPATCH_TOKEN`        | Notification outbox drain |
| `/internal/payouts/*`                 | `INTERNAL_PAYOUTS_TOKEN`         | Payout batch/retry        |
| `/internal/payment-sweeper/tick`      | `INTERNAL_PAYMENT_SWEEPER_TOKEN` | Stale payment sweep       |
| `/internal/reconciliation/*`          | `INTERNAL_RECONCILIATION_TOKEN`  | Lenco vs ledger           |
| `/internal/stock-sweeper/tick`        | `INTERNAL_STOCK_SWEEPER_TOKEN`   | Reservation expiry        |
| `/internal/embeddings/tick`           | `INTERNAL_EMBEDDINGS_TOKEN`      | Search embedding backfill |
| `/internal/n8n/*`                     | `INTERNAL_N8N_TOKEN`             | Operational nudges        |
| `/internal/digest`                    | `INTERNAL_DIGEST_TOKEN`          | Founder daily digest      |
| `/internal/analytics/retention-tick`  | `INTERNAL_ANALYTICS_TOKEN`       | DPA retention             |
| `/internal/order-jobs/*`              | `INTERNAL_ORDER_JOBS_TOKEN`      | Auto-confirm/release      |
| `/internal/funnel/abandon-tick`       | `INTERNAL_FUNNEL_TOKEN`          | Abandoned checkout        |
| `/internal/privacy/export-purge-tick` | `INTERNAL_PRIVACY_TOKEN`         | DPA purge                 |
| `/internal/tickets/*`                 | `INTERNAL_TICKETS_ISSUE_TOKEN`   | Ticket issue/release      |

### Webhooks & analytics

- `POST /webhooks/lenco` — payment events
- `GET/POST /webhooks/whatsapp` — Meta webhook
- `POST /analytics/collect` — client beacon (rate-limited)

---

## Production availability probes (2026-07-24)

| Endpoint                       | Status | Notes                       |
| ------------------------------ | ------ | --------------------------- |
| `GET /healthz`                 | 200    | `{"status":"ok"}`           |
| `GET /search?q=phone`          | 200    | Returns results             |
| `GET /merch/slots`             | 200    | Hero slots active           |
| `GET /admin/dashboard`         | 401    | Route exists, auth required |
| `GET /admin/kyc`               | 401    | Route exists                |
| `GET /vendor/orders/dashboard` | 401    | Route exists                |

---

## Security observations

| Finding                                                                                 | Severity                      |
| --------------------------------------------------------------------------------------- | ----------------------------- |
| All mutating routes covered by rate-limit policy (`assert_all_mutating_routes_covered`) | ✅                            |
| Authz matrix: 1362 persona×route cells tested                                           | ✅                            |
| `auth_guard.py` OTP quota endpoint                                                      | Rate-limit only (intentional) |
| Service-role client bypasses RLS — API authz is authoritative                           | INFO                          |
| Internal tokens fail-closed in staging/prod                                             | ✅                            |

---

## Tests

- **152** pytest files under `services/api/tests/`
- Key: `test_authz_matrix.py`, `tests/rls/test_matrix.py`, payment/webhook suites
- Admin routers tested in isolation (`test_admin_*.py`)

---

## Router source files

91 modules in `services/api/app/routers/`. Discovery via `discover_routers()` in `app/main.py` — auto-imports modules exporting top-level `router`.

**Note:** Admin sub-routers attach via `admin_router.include_router()` side-effects when their modules are imported. Production OpenAPI confirms full admin surface is served.
