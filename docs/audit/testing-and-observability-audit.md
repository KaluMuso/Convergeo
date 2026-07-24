# Testing & Observability Audit

---

## Test inventory summary

| Category              | Count     | Location                           |
| --------------------- | --------- | ---------------------------------- |
| API pytest files      | **152**   | `services/api/tests/`              |
| Customer vitest tests | **~100+** | `apps/customer/**/*.test.{ts,tsx}` |
| UI package tests      | **~53**   | `packages/ui/src/**/*.test.tsx`    |
| E2E Playwright specs  | **8**     | `e2e/specs/`                       |
| Supabase pgTAP        | **15**    | `supabase/tests/`                  |
| Load tests (k6)       | **2**     | `load/k6/`                         |

---

## API tests (Python)

### Security & authz

| Test                       | Coverage                                 |
| -------------------------- | ---------------------------------------- |
| `test_authz_matrix.py`     | 227 routes × 6 personas (517 test cases) |
| `tests/rls/test_matrix.py` | DB RLS isolation matrix                  |
| `test_force_rls_d32.py`    | FORCE RLS launch tables                  |
| `test_env_guards.py`       | Staging/production separation            |

### Payments & money

| Test                                       | Coverage                    |
| ------------------------------------------ | --------------------------- |
| `test_lenco_client.py`, `test_webhooks.py` | Lenco integration           |
| `test_payments_*`, `test_payouts.py`       | Payment lifecycle           |
| `test_ledger.py`, `test_refunds.py`        | Double-entry, refunds       |
| `test_cod.py`                              | Cash on delivery            |
| Money DB triggers (CI job)                 | Release/accounting triggers |

### Domain

| Area            | Key tests                                                        |
| --------------- | ---------------------------------------------------------------- |
| Orders/checkout | `test_checkout*.py`, `test_order_*.py`, `test_reservations.py`   |
| Vendor/KYC      | `test_vendor_*.py`, `test_kyc_*.py`                              |
| Events/tickets  | `test_ticket_*.py`, `test_organiser_*.py`                        |
| Search/AI       | `test_search*.py`, `test_ask*.py`, `evals/test_ask_grounding.py` |
| Notifications   | `test_whatsapp_adapter.py`, `test_notification_*.py`             |
| Admin           | `test_admin_*.py` (isolated app fixtures)                        |
| Internal/cron   | `test_internal_*.py`, `test_n8n_registry.py`                     |

---

## Frontend tests

### Customer app (vitest)

- Checkout payment steps, USSD wait, cart components
- Search filters, PLP, PDP reviews
- Account components, privacy, engagement
- SEO: robots, sitemap, branded error pages
- Service worker rules (`sw.test.ts`)

### Shared UI (`packages/ui`)

- Every component has paired `.test.tsx`
- Design tokens, seasonal theme, motion CSS

### Vendor/Admin

- Middleware tests (`middleware.test.ts`)
- Limited page-level tests vs customer

---

## E2E tests (Playwright)

| Spec                             | Critical path           |
| -------------------------------- | ----------------------- |
| `critical-path.spec.ts`          | End-to-end shop journey |
| `shop-checkout-momo.spec.ts`     | MoMo checkout           |
| `shop-cod.spec.ts`               | COD flow                |
| `checkout-false-success.spec.ts` | Payment honesty         |
| `auth-otp.spec.ts`               | Phone OTP login         |
| `event-ticket.spec.ts`           | Ticket purchase         |
| `vendor-sell.spec.ts`            | Vendor onboarding entry |
| `a11y-smoke.spec.ts`             | Accessibility smoke     |

**CI:** `.github/workflows/e2e.yml` on PRs.

---

## Database tests

### pgTAP (`supabase/tests/`)

Covers migrations: 0002–0012, 0034, 0039, 0056, seed.

**Gap:** No pgTAP for 0013–0070 (except spot checks).

### CI `db` job

- `supabase db reset`
- Typegen drift check on `packages/types/src/db.ts`

### CI `rls` job

- Curated DB-backed integration set
- Demo seed + broad RLS advisory

---

## Critical flow → test coverage map

| Flow              | Unit              | Integration | E2E            | Production verified |
| ----------------- | ----------------- | ----------- | -------------- | ------------------- |
| Customer login    | ✅ OTP forms      | ✅ authz    | ✅ auth-otp    | ✅ login page loads |
| Product search    | ✅ search tests   | ✅ API      | ❌             | ⚠️ images broken    |
| Add to cart       | ✅ cart tests     | ✅ API      | ❌             | ❌ cart broken      |
| Checkout MoMo     | ✅ checkout tests | ✅ API      | ✅ momo spec   | BLOCKED_UNSAFE      |
| Payment webhook   | ✅ webhooks       | ✅          | ❌             | 0 webhooks in DB    |
| Vendor KYC        | ✅ kyc tests      | ✅ RLS      | ✅ vendor-sell | 0 KYC records       |
| Admin KYC approve | ✅ admin_kyc      | ✅          | ❌             | BLOCKED_UNSAFE      |
| Escrow release    | ✅ ledger         | ✅ triggers | ❌             | NOT_DEPLOYED        |
| Notifications     | ✅ adapters       | ✅ dispatch | ❌             | 0 outbox rows       |
| Ask Vergeo        | ✅ + evals        | ✅          | ❌             | Working             |

---

## Observability

### Error tracking

| Component    | Implementation                                                     |
| ------------ | ------------------------------------------------------------------ |
| API          | Sentry (`core/sentry.py`)                                          |
| Customer     | `app/sentry-init.tsx`, test route `/api/observability/sentry-test` |
| Vendor/Admin | Sentry test routes                                                 |

### Logging

- Structured logging via `app/logging.py`
- Request ID middleware (`RequestIdMiddleware`)

### Audit logs

- `audit_log` table — admin mutations via `AdminAuditedRoute`
- `order_events`, `config_audit` — domain audit trails
- **No admin UI** for audit log browsing

### Metrics & traces

- Sentry traces sample rate configurable (`SENTRY_TRACES_SAMPLE_RATE`)
- No dedicated metrics dashboard verified

### Health & uptime

| Endpoint              | App                     |
| --------------------- | ----------------------- |
| `/en/health`          | Customer, vendor, admin |
| `/healthz`, `/readyz` | API                     |

### Alerting

| Alert                           | Status                                  |
| ------------------------------- | --------------------------------------- |
| n8n workflow failure            | ❌ Error handler inactive               |
| Payment reconciliation mismatch | Digest + reconciliation report (0 rows) |
| Payout failure                  | n8n nudge (1h) — active                 |
| DB backup miss                  | Backup workflow inactive                |

---

## Coverage gaps (priority)

| Gap                                                             | Severity        |
| --------------------------------------------------------------- | --------------- |
| Cart production failure has no synthetic monitor                | P0              |
| No E2E for vendor payouts/events/disputes                       | P2              |
| pgTAP gap for migrations 0013–0070                              | P2              |
| No RLS tests in CI for migration 0071                           | P1 (after sync) |
| Mobile Lighthouse perf budget — CI exists but prod not verified | P2              |
| Admin UI untested in E2E                                        | P2              |

---

## Recommendations

1. Add synthetic check: `GET /en/cart` + API `GET /cart` from edge
2. Extend E2E to vendor order fulfilment smoke
3. Add pgTAP for money gate migrations
4. Activate n8n error workflow + Sentry alert rules for P0 paths
