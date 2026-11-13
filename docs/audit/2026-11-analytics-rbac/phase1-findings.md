# Phase One — discovery and initial findings (read-only)

Audit: analytics integration, RBAC and administration. Base: `origin/release/2026-11-next` @ `ed9d4cbc`.
Branch: `audit/analytics-rbac`. Date: 2026-11-13. Nothing in this phase modified application code.

Environment used: local PostgreSQL **16.15** cluster, disposable database `vergeo5_audit_rbac`
(all 153 migrations replayed with `scripts/ci/migration-replay.sh`, exit 0). No production, staging,
Vercel, Hetzner, n8n or remote database was touched.

## 1. Architecture as found

| Layer                       | What exists                                                                                                                                                                                                                                                                                                                                                                                                                                        | Where                                                                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Identity                    | Supabase JWT (RS256/ES256, JWKS-verified, issuer + audience checked). Roles are **not** read from the token: every request reloads `public.user_roles` with the service-role client.                                                                                                                                                                                                                                                               | `services/api/app/core/auth.py`                                                       |
| Roles                       | Fixed: `customer`, `vendor`, `moderator`, `admin`, `superadmin`. Configurable: `rbac_*` rows in `public.admin_roles`, each a set of permissions.                                                                                                                                                                                                                                                                                                   | `supabase/migrations/20261009100000_configurable_admin_roles.sql`                     |
| Permissions                 | 8 keys: `finance.read`, `events.manage`, `products.manage`, `services.read`, `vendors.manage`, `ads.manage`, `analytics.read`, `inventory.read`.                                                                                                                                                                                                                                                                                                   | `ADMIN_PERMISSIONS`, `_ADMIN_ROUTE_PERMISSIONS`                                       |
| API gate                    | `require_admin_scope` on the shared `/admin` router: `admin`/`superadmin` pass; anyone else needs the route to be in an explicit (method, path) → permission map. Unmapped routes deny. Role management is `require_role("superadmin")` and re-checked inside the SQL function.                                                                                                                                                                    | `auth.py`, `admin_base.py`, `admin_roles.py`                                          |
| Admin UI                    | 19 nav modules. Shell asks `GET /admin/me/permissions`, filters nav, blocks direct URLs, fails closed while grants are loading. No direct database access from the admin app (no `.from(`/`.rpc(` calls); everything goes through the API. Cloudflare Access assertion verified in middleware in production.                                                                                                                                       | `apps/admin/middleware.ts`, `admin-shell.tsx`, `lib/admin-nav-capabilities.ts`        |
| Database                    | RLS on every table. `has_role()` reads `user_roles` (not JWT claims). `user_roles`, `admin_roles`, `audit_log` are service-role only. `manage_admin_role()` is service-role only, takes an advisory lock, and writes `audit_log` in the same transaction. Last-superadmin trigger.                                                                                                                                                                 | migrations                                                                            |
| Audit                       | `public.audit_log` (actor, action, entity_type, entity_id, before, after, at). `AdminAuditedRoute` + `AdminAuditRecorder` force a row on mutating routes of the shared router. `config_audit` trigger on 7 config tables.                                                                                                                                                                                                                          | `core/admin_audit.py`                                                                 |
| Analytics v1 (shipping)     | Capture: `packages/analytics` `track()` → `sendBeacon` → `POST /analytics/collect` (only `product_view` persisted) → `analytics_events`; funnel and search are written server-side to `funnel_events`, `search_query_log`; `analytics_event_stream` view unions the three; `listing_analytics` for vendor views. Read: `GET /admin/dashboard`, `/admin/search-insights/*`, `/admin/clip-analytics`, `/admin/governance/vendors`, vendor analytics. | `routers/analytics_collect.py`, `services/analytics/*`, `routers/admin_dashboards.py` |
| Analytics v2 (not shipping) | Stage 1A/1B on `feat/intel-*` branches: event envelope, `analytics_event_log`, daily rollups, commercial metrics, `/admin/analytics/*` and four admin screens, all behind flags.                                                                                                                                                                                                                                                                   | read with `git show`, not merged                                                      |

## 2. What was executed in Phase One

| Check                                                                                                                                                                                                   | Result                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Migration replay on disposable DB                                                                                                                                                                       | 153 files, exit 0                                                                                                                                                                                  |
| `tests/rls` (RLS isolation matrix and companions) against the disposable DB                                                                                                                             | **3664 passed, 1 skipped** in 744 s                                                                                                                                                                |
| `tests/test_configurable_admin_roles.py`                                                                                                                                                                | **14 passed**; 153 disposable cases **errored at the fixture guard** — the harness asserts PostgreSQL 17 and a database named `postgres`; local is 16.15. Not a product failure. See NOT TESTABLE. |
| Live HTTP probe: every `/admin` route (130) × 13 identities (customer, vendor, moderator, admin, superadmin, 8 single-permission `rbac_*` roles) = 1,690 requests through the real app with real guards | `evidence-api-role-probe.txt` (D = 403)                                                                                                                                                            |
| Direct database probe as `authenticated` with each admin identity, rolled back                                                                                                                          | `evidence-db-direct-write-probe.txt`                                                                                                                                                               |

## 3. Initial findings

Severity is my assessment; status is as of Phase One (before remediation).

### Security / RBAC

- **S1 — HIGH — legacy `admin` role can write money tables directly, outside the API.**
  RLS policies `*_admin_all` (`FOR ALL ... has_role('admin')`) exist on `ledger_accounts`, `ledger_transactions`,
  `ledger_postings`, `payments`, `payouts`, `refunds`, `orders`, `invoices`, `kyc_records`, `vendors`, and ~70 other
  tables, and `authenticated` holds INSERT/UPDATE/DELETE grants. Executed on the disposable DB: an `admin` identity
  inserted a balanced ledger transaction with two postings (2 rows), deleted all 4 `ledger_accounts` rows, and updated
  13 feature flags, 30 platform-config rows and 9 commission rates. The order, vendor and KYC guard triggers explicitly
  exempt `has_role('admin')`. None of this passes the API's state machines, payout guards or `audit_log`
  (config tables do still hit the `config_audit` trigger). `moderator`, `superadmin`-only, `rbac_*` and customer
  identities were all denied (0 rows / RLS violation). The RLS matrix currently encodes admin write as expected.
- **S2 — MEDIUM — no separation between "admin" and money authority.** `admin` and `superadmin` are both
  unrestricted at the API: refunds execute, escrow, dispute decisions, COD confirmation, commission rates, flags.
  Only role management is superadmin-only. Restricted `rbac_*` roles are read-only on finance, which is conservative,
  but there is no way to give someone finance _operations_ without giving them everything.
- **S3 — MEDIUM — `analytics.read` exposes ledger figures.** `GET /admin/dashboard` returns escrow held,
  released-unpaid liabilities, GMV and the reconciliation report (provider account id, discrepancies) to any role with
  `analytics.read`. The brief asks for financial analytics only when explicitly authorised.
- **S4 — MEDIUM — audit gaps on two mutation paths (confirmed in code).**
  `PUT`/`DELETE /admin/translations/overrides` write no `audit_log` row (delete leaves no trace at all).
  `POST /admin/orders/{id}/cod/confirm-collection` and `/refuse-collection` are money actions with no `audit_log` row;
  `confirm_cod_collection` discards `actor_id` and transitions the order as SYSTEM.
- **S5 — LOW — audit record is thin.** No role-at-time, outcome, request id or reason column; no append-only
  trigger (client roles cannot touch the table, service role can). No API or UI to read the audit log.
- **S6 — LOW — moderator inconsistency.** `/admin/me/permissions` reports `products.manage` + `vendors.manage`
  for `moderator`, so the UI shows KYC and Business, but KYC decisions, licences and `/admin/business` require `admin`
  and return 403. An `rbac_*` role with `vendors.manage` _can_ approve KYC. Fails closed; confusing.
- **S7 — LOW — internal token comparison is not constant-time** (`provided != expected`) on `/internal/analytics`
  and `/internal/funnel`.

Verified good at this stage: no route in `/admin` is reachable by customer or vendor; no restricted role reaches
a route outside its permission; no identity other than superadmin reaches `/admin/roles*`; nobody can read or write
`user_roles`, `admin_roles` or `audit_log` from a browser token; `manage_admin_role` is not executable by
`authenticated`; JWT role claims are never trusted by the API.

### Analytics

- **A1 — HIGH (accuracy) — dashboard order and funnel counts truncate at 1,000 rows.** `_orders_by_status` and
  `_funnel_snapshot` select every row through PostgREST; `supabase/config.toml` sets `max_rows = 1000`. Counts are
  silently wrong past 1,000 orders or checkout groups. Already fixed on the v2 branch (commit `e88bb990`), not on the
  shipping base.
- **A2 — MEDIUM (money semantics) — "GMV" is order value, not money.** It sums items + delivery fee over every
  non-cancelled order, including `placed` orders that were never paid and orders later refunded. The tile's empty
  state calls it a "ledger-backed aggregate"; it is not. Escrow and released-unpaid are correctly ledger-derived
  and kept separate. Platform revenue / commission earned is not shown anywhere.
- **A3 — MEDIUM — no date filters, no time series, all-time totals only**, 5-minute process cache.
- **A4 — MEDIUM — most of the brief's metrics do not exist in v1**: registered customers, active users,
  DAU/WAU/MAU, retention, registrations over time, geography, category performance, conversion rates, payment
  success/failure, refunds, settlements, service bookings, event attendance, exports. `search-insights` and
  `governance/vendors` endpoints exist and are permissioned but no admin screen calls them.
- **A5 — INFO — nothing is hardcoded or simulated.** Every tile reads the database; empty states say so.

### v2 interaction (read from branches, not merged)

- v2 `/admin/analytics/*` is gated `require_role("admin","superadmin")` and is absent from the permission map, so
  an `rbac_*` role with `analytics.read` gets 403 on all v2 screens.
- v2 edits `admin_dashboards.py`, `tests/rls/test_matrix.py` and `admin-nav-capabilities.ts`; remediation here is
  kept to identical or non-overlapping hunks.
- v2 migrations use `20261112120000`–`20261112150200`; audit migrations use timestamps after `20261113000000`.

## 4. NOT TESTABLE (so far)

- The 153 disposable cases of the CI job "Platform RBAC SQL and direct API acceptance" as written: they require
  PostgreSQL 17 and a database named `postgres`. Only PostgreSQL 16 is installed and Docker is unavailable.
- "Critical real-stack execution" (needs PostgREST in Docker).
- Anything on live systems: real login-attempt logging (Supabase Auth), Cloudflare Access in front of the deployed
  admin, production data reconciliation, n8n schedules.

## 5. Planned remediation (Phase Nine), confirmed and safely fixable only

1. A1 — bring the shipping base to the same dashboard-count code as v2 (identical change, so v2 merges cleanly).
2. S4 — `audit_log` rows for translation overrides and admin COD actions, with regression tests.
3. S1 — additive migration making `admin` read-only at the database on the ledger, payments, payouts and refunds
   tables, with RLS regression tests and the matrix expectation tightened.
4. A role × route acceptance matrix test that pins the probe above so a new admin route cannot ship unmapped.

S2, S3, A2 and the audit-record schema are reported for a founder decision rather than changed.
