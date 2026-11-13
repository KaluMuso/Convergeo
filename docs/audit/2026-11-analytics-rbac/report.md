# Convergeo — analytics integration, RBAC and administration audit

Date: 2026-11-13 · Branch: `audit/analytics-rbac` · Base: `origin/release/2026-11-next` @ `ed9d4cbc`
Phase One findings (written before any change): [`phase1-findings.md`](./phase1-findings.md)

## Final status: NOT PRODUCTION READY (as a complete analytics + RBAC implementation)

| Requirement                                             | Verdict                                   | Why                                                                                                                                                                                                                                                       |
| ------------------------------------------------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Access control on what exists (API, database, admin UI) | **CONDITIONALLY READY**                   | Every admin route and the money tables were exercised with real requests and real SQL. One high-severity path was found and closed on this branch (S1). Conditions: merge this branch, apply migration `20261113100000`, take the decisions in section G. |
| Analytics data accuracy                                 | **CONDITIONALLY READY for what is shown** | Nothing is simulated. One truncation bug fixed (A1). "GMV" is order value, not money received (A2).                                                                                                                                                       |
| Analytics coverage and the brief's role model           | **NOT READY**                             | Most requested metrics, date filters, exports, an audit-log viewer and most specialised-role write scopes do not exist in the shipping code. v2 covers part of the analytics gap but is unmerged and admin-only.                                          |

Nothing was deployed. No production, staging, Vercel, Hetzner, n8n or remote database was touched.

## The ten questions

| #   | Question                                                 | Answer                                                                                                                                                                                                                                                                                      |
| --- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Are analytics working end-to-end?                        | **Partly.** The v1 pipeline (browser beacon / server emit → `analytics_events`, `funnel_events`, `search_query_log` → admin API → dashboard) is real and connected. Verified by code path and existing suites, not against live traffic. Only `product_view` is persisted from the browser. |
| 2   | Visible and functional in the Admin Panel?               | **Partly.** One dashboard of seven tiles. Search insights and vendor governance have working, permissioned endpoints that no admin screen calls. No date filters.                                                                                                                           |
| 3   | Figures from real platform activity?                     | **Yes.** No hardcoded, simulated or placeholder values; empty states say they are empty. One accuracy bug (counts capped at 1,000) fixed here.                                                                                                                                              |
| 4   | All required roles implemented?                          | **No.** Super Admin exists (`superadmin`). The other seven exist only as permissions a superadmin can assemble into `rbac_*` roles; Finance, Services and Analytics are read-only by construction. No Customer Support permission exists.                                                   |
| 5   | Does each role have the correct permissions?             | **No by the brief's matrix; yes by least privilege.** Every role reaches exactly what its permission says and nothing more (128 routes × 13 identities). What is missing is breadth, not containment.                                                                                       |
| 6   | Enforced at frontend, backend and database?              | **Yes after this branch for the money tables.** Backend and frontend were already sound. The database let the legacy `admin` role write money tables directly; closed for ledger, payments, payouts and refunds. Other `admin` direct-write tables remain (D1).                             |
| 7   | Can any administrator act outside their authority?       | **Restricted roles and moderators: no** (tested). **Legacy `admin`:** could before this branch (S1); after it, can still write orders, vendors, KYC and config tables at the database, with config changes audited by trigger and the rest not.                                             |
| 8   | Is the Super Admin genuinely in control?                 | **Of roles and permissions, yes** (superadmin-only, re-checked in SQL, audited, last-superadmin protected). **As a control centre, no:** no admin directory with names, no account creation or deactivation, no per-admin effective-permission view, no audit-log or security-event screen. |
| 9   | Are sensitive financial operations adequately protected? | **At the API, yes:** no permission or moderator grant reaches any money mutation. **Gaps:** `admin` equals full money authority with no second approval; audit records lack role, outcome, request id and reason.                                                                           |
| 10  | Is the complete implementation production-ready?         | **No.**                                                                                                                                                                                                                                                                                     |

---

## A. Analytics integration report

### Pipeline (traced in code)

| Stage             | Implementation                                                                                                                                                  | State                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Capture (browser) | `packages/analytics/src/track.ts`: queue → `navigator.sendBeacon` batch of ≤20; GA4 mirror only with consent                                                    | Works; server beacon is consent-independent and anonymised        |
| Ingest            | `POST /analytics/collect`: per-IP rate limit, batch cap, props size cap, PII-key rejection; **persists only `product_view`**                                    | Works; other client events are accepted and dropped by design     |
| Capture (server)  | Funnel (`cart_add`, `checkout_start`, `payment_start`, `order_placed`) and search written server-side                                                           | Works                                                             |
| Storage           | `analytics_events`, `funnel_events`, `search_query_log`, `listing_analytics`; view `analytics_event_stream` (security invoker)                                  | RLS: admin read, service-role write                               |
| Aggregation       | None scheduled in v1; every read aggregates on demand. A retention tick clears person links                                                                     | No rollups                                                        |
| Admin API         | `GET /admin/dashboard` (5-minute cache), `/admin/search-insights/{top-terms,zero-results,ask-cost}?days=`, `/admin/clip-analytics`, `/admin/governance/vendors` | Permission `analytics.read`                                       |
| Admin UI          | Home dashboard: reconciliation, payout liabilities, orders by status, GMV, catalogue counts, AI usage, funnel                                                   | Loading, error, permission-denied and honest-empty states present |

### Metric by metric

| Area              | Real and shown                                                          | Real, endpoint only                                                | Missing                                                                                                                         |
| ----------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| Platform-wide     | Vendor, listing, product counts                                         | —                                                                  | Registered customers, active/inactive users, registrations over time, DAU/WAU/MAU, retention, geography                         |
| Marketplace       | Orders by status; checkout started/completed, orders placed/completed   | Top search terms, zero-result terms; listing views (vendor-facing) | Services and events totals, listing status breakdown, category performance, conversion rates, cart activity, vendor performance |
| Financial         | Order value ("GMV"), escrow held, released-unpaid, reconciliation state | Ask AI cost per day                                                | Platform revenue, commission earned, payment success/failure rate, refunds, cancellations, settlements, trends                  |
| Vendor            | —                                                                       | Vendor governance list                                             | KYC pipeline counts, sales, ratings, payout performance                                                                         |
| Services / events | —                                                                       | —                                                                  | All                                                                                                                             |
| Operational       | Reconciliation mismatch, AI kill-switch                                 | Clip analytics                                                     | Failed transactions, API/auth errors, escrow exceptions, complaints                                                             |

### Accuracy

- **A1 — fixed.** Order-status and funnel counts read rows through PostgREST, capped at `max_rows = 1000` (`supabase/config.toml`). Now SQL aggregates.
- **A2 — open.** The GMV tile sums items plus delivery fee for every non-cancelled order: unpaid `placed` orders and refunded orders count. It is order value. Escrow held and released-unpaid are ledger-derived and kept separate. Platform revenue is not shown anywhere. The tile's empty-state text calls it "ledger-backed", which it is not.
- **A3 — open.** All-time totals only; no date ranges. Timestamps are UTC; the reconciliation tile uses the previous UTC day.
- Updates are automatic: live queries behind a 5-minute in-process cache; the reconciliation tile bypasses the cache.
- Performance: full-table aggregates on each uncached load. Fine at pilot volume; needs rollups later.
- Reconciliation: count tiles equal `count(*) FILTER` over the same tables (DB test seeds past the 1,000 cap). GMV, escrow and liabilities were checked by reading the SQL, not against production data.

### v2 Intelligence Engine (branches `feat/intel-1b-05-admin-ui`, `-1b-06-founder-decisions`, `-1a-08-09-identify-optout`)

Read, not merged or run. Adds an event envelope and registry, `analytics_event_log`, daily rollups, commercial metrics with payment reconciliation, a Lusaka reporting day, k-thresholds on search terms and four admin screens, behind flags.

- v2 gates `/admin/analytics/*` with `require_role("admin","superadmin")` and adds nothing to the permission map, so a role with only `analytics.read` is refused on every v2 screen. Those routes also need rows in `tests/test_admin_role_route_matrix.py`, which fails on unclassified routes by design.
- A1 was fixed by cherry-picking v2's own commits, so both sides carry the same change.
- v2 also edits `tests/rls/test_matrix.py`, `test_schema_convergence.py` and `test_reconcile_staging_migrations.py`; expect mechanical conflicts.
- Migration timestamps do not collide (v2: `20261112…`; here: `20261113100000`).

---

## B. RBAC implementation report

### Roles that exist

| Role                 | Kind                       | Authority                                                                                                                                   |
| -------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `superadmin`         | fixed                      | Everything at the API, plus role and permission management                                                                                  |
| `admin`              | fixed (legacy)             | Everything at the API except role management. Also holds direct database policies (S1, D1)                                                  |
| `moderator`          | fixed                      | Canonical product queue and status, Q&A moderation, product relations; read KYC, licences, intake, vendors; vendor status; intake decisions |
| `rbac_*`             | configurable by superadmin | Any non-empty subset of 8 permissions                                                                                                       |
| `customer`, `vendor` | fixed                      | No admin access                                                                                                                             |

### Mapping to the brief's roles

| Brief role             | Exists as                    | Gap                                                                                                                             |
| ---------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Super Admin            | `superadmin`                 | No admin directory, account lifecycle, or audit/security screens                                                                |
| Finance Admin          | `rbac_*` + `finance.read`    | Reads orders and disputes only. No ledger, payout, refund or reconciliation views; no financial operation short of full `admin` |
| Product Admin          | `rbac_*` + `products.manage` | Canonical catalogue only. No category management, no listing-reports queue, no product analytics                                |
| Vendor Admin           | `rbac_*` + `vendors.manage`  | Complete for onboarding, KYC, licences, business buyers, intake, vendor status. No vendor analytics                             |
| Analytics Admin        | `rbac_*` + `analytics.read`  | Read-only as intended, but the dashboard includes ledger figures (S3). No exports                                               |
| Services Admin         | `rbac_*` + `services.read`   | One read-only list                                                                                                              |
| Events Admin           | `rbac_*` + `events.manage`   | High-value event verification only                                                                                              |
| Customer Support Admin | —                            | No permission; support tools and disputes are unrestricted-only                                                                 |

No seeded `rbac_*` roles ship; the migration deliberately contains no grants.

### Enforcement by layer

| Layer            | Finding                                                                                                                                                                                                                | Evidence                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Frontend         | Nav filtered from `/admin/me/permissions`; direct URLs without the capability render a denial; fails closed while grants load; no direct database client in the admin app                                              | `admin-shell.tsx`, `admin-nav-capabilities.ts`; admin vitest 270 passed |
| Backend          | Every `/admin` route authenticates (anonymous → 401 on all 128) and authorises server-side. Restricted roles reach only explicitly mapped (method, path) pairs; unmapped routes deny; read permissions carry no writes | `tests/test_admin_role_route_matrix.py`, 17 passed                      |
| Session          | Roles reloaded from `user_roles` on every request; token claims never trusted; revocation takes effect on the next request with the same token                                                                         | `test_disposable_revocation_and_update_use_unchanged_jwt` (PG16 copy)   |
| Database         | RLS on every table; `user_roles`, `admin_roles`, `audit_log` unreachable by any browser token; `manage_admin_role` not executable by `authenticated` and re-checks superadmin itself                                   | `tests/rls`, direct probe                                               |
| Service-role key | Server-side only; import guard test passes                                                                                                                                                                             | `test_service_role_import_guard.py`                                     |

### Escalation tests requested by the brief

| Attempt                                                  | Result                                                                                                                                                                                   |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product Admin promotes itself to Super Admin             | Denied: API 403 on all six `/admin/roles*` routes; insert into `user_roles` rejected by RLS; `manage_admin_role` permission denied                                                       |
| Vendor Admin calls Finance endpoints                     | Denied (403)                                                                                                                                                                             |
| Analytics Admin releases escrow                          | Denied (403), as on every other money mutation                                                                                                                                           |
| Finance Admin changes permissions                        | Denied (403)                                                                                                                                                                             |
| Administrator reads another administrator's resources    | No per-admin resources exist; role assignments are superadmin-only                                                                                                                       |
| Suspended administrator keeps a session                  | Role revocation takes effect on the next API call. The UI shell loads until the token refreshes but shows no data. A Supabase ban without role revocation is not checked by the API (D4) |
| Role forged in the browser or JWT claims                 | No effect: signature verified against JWKS; roles come from the database                                                                                                                 |
| Direct API call bypassing hidden buttons                 | Covered by the route matrix                                                                                                                                                              |
| **Legacy `admin` writes money tables through PostgREST** | **Succeeded before this branch; denied after** (S1)                                                                                                                                      |

---

## C. Role–permission matrix (verified, as implemented after this branch)

**Full** = every operation the module has; **R** = read; **—** = 403. Source of truth: `tests/test_admin_role_route_matrix.py`; raw results in `evidence-api-role-probe.txt`.

| Module                                                                       | superadmin | admin | moderator      | finance.read | products.manage | vendors.manage | analytics.read | services.read | events.manage | ads.manage | inventory.read |
| ---------------------------------------------------------------------------- | ---------- | ----- | -------------- | ------------ | --------------- | -------------- | -------------- | ------------- | ------------- | ---------- | -------------- |
| Dashboard, search insights, clip analytics, vendor governance                | Full       | Full  | —              | —            | —               | —              | R              | —             | —             | —          | —              |
| Orders: search, detail                                                       | Full       | Full  | —              | R            | —               | —              | —              | —             | —             | —          | —              |
| Orders: dispatch, intervene, escrow, COD confirm/refuse                      | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Refund execution                                                             | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Disputes: list, detail                                                       | Full       | Full  | —              | R            | —               | —              | —              | —             | —             | —          | —              |
| Disputes: decide                                                             | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Vendors: list, KYC view                                                      | Full       | Full  | R              | —            | —               | R              | —              | —             | —             | —          | —              |
| Vendors: status (suspend/restore)                                            | Full       | Full  | Edit           | —            | —               | Edit           | —              | —             | —             | —          | —              |
| KYC, licences: queues and detail                                             | Full       | Full  | R              | —            | —               | R              | —              | —             | —             | —          | —              |
| KYC, licences: approve, reject, resubmit, suspend, revoke                    | Full       | Full  | —              | —            | —               | Full           | —              | —             | —             | —          | —              |
| Business buyers: list, verify, reject                                        | Full       | Full  | —              | —            | —               | Full           | —              | —             | —             | —          | —              |
| WhatsApp intake: review, approve, reject, attach                             | Full       | Full  | Full           | —            | —               | Full           | —              | —             | —             | —          | —              |
| Canonical products: queue, duplicates, status                                | Full       | Full  | Approve/Reject | —            | Full            | —              | —              | —             | —             | —          | —              |
| Products: search, relations read, merge                                      | Full       | Full  | —              | —            | Full            | —              | —              | —             | —             | —          | —              |
| Product relations write; Q&A moderation                                      | Full       | Full  | Edit           | —            | Edit            | —              | —              | —             | —             | —          | —              |
| Listing reports: dismiss, unpublish, remove, warn, suspend                   | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Services oversight                                                           | R          | R     | —              | —            | —               | —              | —              | R             | —             | —          | —              |
| Inventory oversight                                                          | R          | R     | —              | —            | —               | —              | —              | —             | —             | —          | R              |
| Events: high-value queue and verification                                    | Full       | Full  | —              | —            | —               | —              | —              | —             | Full          | —          | —              |
| Merchandising, home feed, ad placements, flash deals                         | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | Full       | —              |
| Clips moderation and reports                                                 | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Courier dispatch board                                                       | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Support: lookup, log, send                                                   | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Platform configuration: categories, commissions, zones, flags, platform keys | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Translations                                                                 | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Kill-switch resets (AI spend, clips)                                         | Full       | Full  | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Roles and permissions: define, assign, revoke                                | Full       | —     | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| Own effective permissions                                                    | R          | R     | R              | R            | R               | R              | R              | R             | R             | R          | R              |
| Money tables at the database (ledger, payments, payouts, refunds)            | —          | R     | —              | —            | —               | —              | —              | —             | —             | —          | —              |
| `user_roles`, `admin_roles`, `audit_log` at the database                     | —          | —     | —              | —            | —               | —              | —              | —             | —             | —          | —              |

No role has these because the operation does not exist: export (any module), customer management (list, suspend, restore), audit-log read, admin account create/deactivate, service or event listing approval, deletes of orders, vendors or products (by design).

---

## D. Security findings (prioritised)

| ID  | Severity            | Finding                                                                                                                                                                                                                                                                                                                                                                      | Status                 |
| --- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| S1  | **High**            | Legacy `admin` could write `ledger_accounts`, `ledger_transactions`, `ledger_postings`, `payments`, `payouts`, `refunds` through PostgREST with a browser token (policy `*_admin_all` plus write grants). Executed on a disposable database: balanced fake ledger transaction inserted; all ledger accounts deleted. Bypassed state machines, payout guards and `audit_log`. | **Fixed** — `1d418b14` |
| S1b | **High (residual)** | The same pattern remains on about 75 other tables, including `orders`, `order_items`, `invoices`, `invoice_counters`, `vendors`, `kyc_records`, `disputes`, `tickets`, `profiles`, `addresses`; guard triggers on orders, vendors and KYC explicitly exempt `admin`. Config tables are also writable but trigger-audited to `config_audit`.                                  | **Open — D1**          |
| S2  | Medium              | `admin` is full money authority (refunds, escrow, disputes, COD, commission rates, flags); no maker-checker, no finance-operations permission                                                                                                                                                                                                                                | Open — D2              |
| S3  | Medium              | `analytics.read` returns escrow held, unpaid liabilities, order value and the reconciliation report (provider account id, discrepancies)                                                                                                                                                                                                                                     | Open — D3              |
| S4  | Medium              | No `audit_log` row for translation override upsert/delete or admin COD confirm/refuse (ledger legs booked as SYSTEM)                                                                                                                                                                                                                                                         | **Fixed** — `9f1db4fc` |
| S5  | Medium              | Audit record lacks role-at-time, outcome, request id and reason; denied and failed attempts are not recorded; no append-only trigger; no read API or screen; no retention rule. Login success/failure lives only in Supabase Auth logs                                                                                                                                       | Open                   |
| S6  | Low                 | `moderator` is told it has `vendors.manage` but is refused KYC decisions, licences and business buyers; a custom role with the same permission is allowed. Fails closed                                                                                                                                                                                                      | Open                   |
| S7  | Low                 | `/internal/analytics` and `/internal/funnel` compare the shared token with `!=` rather than constant-time                                                                                                                                                                                                                                                                    | Open                   |
| S8  | Low                 | The API does not check whether a Supabase user is banned                                                                                                                                                                                                                                                                                                                     | Open — D4              |

Verified sound: anonymous, customer and vendor denial on all 128 admin routes; no cross-permission reach for any restricted role; superadmin-only role management, enforced again inside the SQL function with an advisory lock and same-transaction audit; last-superadmin protection; assigned roles cannot be deleted; unknown permissions rejected by a table constraint; `audit_log` not readable or writable by any client role. Cloudflare Access verification was read in code only.

---

## E. Remediation report

### Commits on `audit/analytics-rbac` (pushed)

| Commit                                         | Change                                                                                                                                                                                      |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `3e134100`, `8f2e741e`                         | docs: Phase One findings and evidence files; formatting                                                                                                                                     |
| `75279958`, `bf872907`, `9535dc45`, `a4d78117` | A1: dashboard counts as SQL aggregates. Cherry-picked from v2 (`e88bb990`, `38f69caf`, `8efe087c`, `530227d1`); one formatting-only conflict resolved to v2's text                          |
| `9f1db4fc`                                     | S4: `audit_log` rows for translation overrides and admin COD confirm/refuse                                                                                                                 |
| `1d418b14`                                     | S1: migration making admins read-only on six money tables; RLS matrix expectations tightened; regression suite; role × route acceptance matrix; migration inventory tests registered at 154 |

### Files

- `services/api/app/routers/admin_dashboards.py`, `admin_translations.py`, `cod.py`
- `supabase/migrations/20261113100000_admin_money_tables_read_only.sql` (idempotent; manual down documented in the file and exercised)
- Tests added: `tests/test_admin_audit_coverage.py` (9), `tests/test_admin_role_route_matrix.py` (17), `tests/rls/test_admin_money_tables_read_only.py` (31), `tests/rls/test_admin_dashboard_counts_db.py` (from v2)
- Tests changed: `tests/rls/test_matrix.py` (six tables now select-only for every signed-in persona), `tests/test_admin_translations.py` (fixture gains an audit sink), `tests/test_admin_dashboards.py`, `tests/test_internal_digest.py` (from v2), `tests/test_schema_convergence.py`, `tests/test_reconcile_staging_migrations.py` (inventory 153 → 154)

No test or control was weakened; the only expectation changes move cells from permit to deny.

### Required at integration

The new migration makes 8 additional `scripts/ci` inventory self-tests fail (11 failing with it, 3 without, in this environment) until the migration inventories are requalified to 154, as was done for 153 in `ac352b97`. That procedure needs the Docker-based gates and was not attempted here.

### Regression proof (fails before, passes after)

| Fix | Before                                                         | After     |
| --- | -------------------------------------------------------------- | --------- |
| A1  | Base `admin_dashboards.py`: 1 failed, 19 errors, 1 passed      | 29 passed |
| S4  | Base routers: 4 failed, 5 passed                               | 9 passed  |
| S1  | Previous schema (documented down applied): 25 failed, 6 passed | 31 passed |

### Test runs (exact)

| Suite                                                                                                          | Result                                                                                                                                                                         |
| -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Migration replay on disposable PG 16.15                                                                        | 153 files exit 0 before; 154 files exit 0 after                                                                                                                                |
| `tests/rls` full, before any change                                                                            | 3664 passed, 1 skipped (744 s)                                                                                                                                                 |
| `tests/rls` full, after migration, on a freshly rebuilt database                                               | 3696 passed, 1 skipped (876 s)                                                                                                                                                 |
| `tests/test_admin_role_route_matrix.py`                                                                        | 17 passed (281 s)                                                                                                                                                              |
| `tests/test_authz_matrix.py`                                                                                   | 1000 passed, run as two slices (425 + 575)                                                                                                                                     |
| 22 admin, analytics, auth and inventory files without a database                                               | 263 passed, 153 skipped, 2 failed — the 2 are DB-backed retention tests that pass when given the database                                                                      |
| 10 DB-backed files (analytics, search, funnel, ledger, COD, refunds, payouts, KYC) on the migrated database    | 159 passed, 1 failed — `test_cod.py::TestCodRefusalReversal::test_refusal_reverses_receivable_and_cancels_order`, which fails identically without the migration (pre-existing) |
| `tests/test_configurable_admin_roles.py` as written                                                            | 14 passed; 153 need PG17                                                                                                                                                       |
| Same file, scratch copy with only the PG-version and database-name guards changed, PG 16, S1 migration applied | 167 passed (211 s) — supporting evidence, not the CI gate                                                                                                                      |
| `ruff check` and `mypy` on every changed file                                                                  | clean                                                                                                                                                                          |
| Admin app `vitest`                                                                                             | 26 files, 270 passed — run in worktree `wt-next`, whose `apps/admin` is identical to this base                                                                                 |
| `tsc --noEmit -p apps/admin`                                                                                   | exit 0 (same worktree)                                                                                                                                                         |

### NOT TESTABLE

| Item                                                                               | Reason                                                                                           |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| CI job "Platform RBAC SQL and direct API acceptance" as defined                    | Requires PostgreSQL 17 and a database named `postgres`; only 16.15 installed, Docker unavailable |
| CI job "Critical real-stack execution" and the migration inventory requalification | Need Docker                                                                                      |
| Behaviour through real PostgREST and Supabase default privileges                   | Tested as the `authenticated` role in Postgres with the CI shim only                             |
| Dashboard totals against production; live ingestion volumes                        | No production access by instruction                                                              |
| Login logging, Cloudflare Access at the edge, n8n schedules                        | Live systems                                                                                     |
| v2 analytics behaviour                                                             | Read from branches only                                                                          |

---

## F. Final acceptance

Reliable today on this evidence: each role is contained to exactly its grants; role management cannot be reached or forged by anyone but a superadmin; the audit log cannot be tampered with from a browser; the dashboard shows real numbers.

Not ready: the specialised role model the brief describes, analytics breadth, exports, audit-log visibility and depth, and separation of financial authority from general administration.

Recommended order: (1) merge this branch and apply the migration before anyone other than the founder holds `admin`; (2) D1 for the remaining direct-write tables; (3) audit-record schema and a read-only audit screen; (4) land v2 and map `analytics.read` to it; (5) new permissions for finance operations, support, services and events.

## G. Decisions needed from the founder

| #   | Decision                                                                                                                                  | Recommendation                                                                                                                                                                                               |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| D1  | Should legacy `admin` keep direct database write access to orders, invoices, vendors, KYC, disputes, tickets, profiles and config tables? | No. Repeat the S1 treatment table by table, starting with `orders`, `order_items`, `invoices`, `invoice_counters`, `kyc_records`, `vendors`, after checking no runbook relies on an admin token writing them |
| D2  | Should money operations need a narrower role than `admin`, and refunds and dispute payouts a second approver?                             | Yes to the permission before a second person holds `admin`; second approver once volume justifies it                                                                                                         |
| D3  | May a role with only `analytics.read` see escrow, liabilities and reconciliation detail?                                                  | No: require `finance.read` for those tiles. It changes the dashboard response shape v2 also touches, so sequence it with v2                                                                                  |
| D4  | Is "deactivate an administrator" role revocation (immediate today) or a Supabase ban (not checked by the API)?                            | Make revocation the procedure; add a ban check only if bans will be used                                                                                                                                     |
| D5  | Relabel the GMV tile "Order value (not cancelled)" now, or wait for v2's paid-order metrics?                                              | Relabel now; it is a copy change                                                                                                                                                                             |
| D6  | Which missing roles does the pilot need (finance operations, support, services, events)?                                                  | Only those with a named person; each is a new permission plus route-map rows and a matrix row                                                                                                                |
