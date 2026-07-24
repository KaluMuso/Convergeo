# Platform Risk Register

**Audit date:** 2026-07-24  
**Classification:** P0 Critical → P3 Low, plus special statuses

---

## P0 — Critical

### R-001: Customer cart broken in production

| Field           | Value                                                                                                                   |
| --------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Severity**    | P0                                                                                                                      |
| **Application** | Customer                                                                                                                |
| **Flow**        | Cart, checkout entry                                                                                                    |
| **Evidence**    | Browser: `GET http://localhost:8000/cart` ERR_CONNECTION_REFUSED; error UI "Could not load your cart"                   |
| **Impact**      | Complete cart failure — blocks core commerce journey                                                                    |
| **Root cause**  | `NEXT_PUBLIC_API_BASE_URL` missing or wrong at Vercel build time; client falls back to localhost in non-prod build path |
| **Fix**         | Set env in Vercel production; rebuild customer app                                                                      |
| **Owner**       | Platform / DevOps                                                                                                       |
| **Verify**      | Cart page loads; network shows `api.vergeo5.com/cart`                                                                   |

---

## P1 — High

### R-002: Search product images not rendering

| Field           | Value                                                                                     |
| --------------- | ----------------------------------------------------------------------------------------- |
| **Severity**    | P1                                                                                        |
| **Application** | Customer                                                                                  |
| **Flow**        | Search, product discovery                                                                 |
| **Evidence**    | /en/search?q=phone — placeholder boxes, K0.00 prices                                      |
| **Impact**      | Poor discovery UX, reduced conversion                                                     |
| **Root cause**  | Likely missing `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` or broken image URLs in search results |
| **Fix**         | Verify Cloudinary env at build; inspect search API image fields                           |
| **Verify**      | Search results show product thumbnails                                                    |

### R-003: Migration drift (0071 missing from repo)

| Field           | Value                                                                         |
| --------------- | ----------------------------------------------------------------------------- |
| **Severity**    | P1                                                                            |
| **Application** | Database                                                                      |
| **Evidence**    | Supabase prod: `0071_vendor_listing_compare_at`; repo stops at `0070`         |
| **Impact**      | Schema drift; CI cannot reproduce prod; compare-at pricing may break on reset |
| **Fix**         | Pull migration from prod; commit to `supabase/migrations/`                    |
| **Verify**      | `supabase migration list` matches prod                                        |

### R-004: Vendor navigation IA gap

| Field           | Value                                                                |
| --------------- | -------------------------------------------------------------------- |
| **Severity**    | P1                                                                   |
| **Application** | Vendor                                                               |
| **Evidence**    | 15+ routes with no quick-nav link (events, payouts, analytics, etc.) |
| **Impact**      | Vendors cannot discover key features                                 |
| **Fix**         | Expand nav or add "More" hub                                         |
| **Verify**      | User testing reaches payouts/events from UI                          |

### R-015: Database backup workflow inactive

| Field           | Value                                               |
| --------------- | --------------------------------------------------- |
| **Severity**    | P1                                                  |
| **Application** | Automation                                          |
| **Evidence**    | n8n workflow `OAdOD4kmIbSNehkJ` active=false        |
| **Impact**      | No independent pg_dump backup beyond Supabase PITR  |
| **Fix**         | Configure SSH + WhatsApp creds; activate workflow   |
| **Verify**      | Manual drill `POST /webhook/backup-manual` succeeds |

---

## P2 — Medium

### R-005: CSP report-only violations

| **Severity** | P2 | **App** | Customer | **Evidence** | 12–79 console errors/page for GTM, Supabase, localhost |

### R-006: Supabase SECURITY DEFINER RPC exposure

| **Severity** | P2 | **Evidence** | Advisor: anon can execute `has_role`, `search_query_facets`, etc. |

### R-010: Customer auth layout-only

| **Severity** | P2 | **Evidence** | Middleware refreshes session but doesn't gate routes |

### R-011: JWT roles vs DB roles in middleware

| **Severity** | P2 | **Evidence** | Middleware uses `app_metadata.roles`; API uses `user_roles` table |

### R-016: n8n error handler unpublished

| **Severity** | P2 | **Evidence** | Workflow `LVuHqWgT1tqjYOtc` inactive |

### R-020: No vendor staff/RBAC

| **Severity** | P2 | **Status** | NOT_IMPLEMENTED (documented VEND-10) |

### R-021: Mobile viewport audit incomplete

| **Severity** | P2 | **Status** | BLOCKED_EXTERNAL |

---

## P3 — Low

### R-013: Leaked password protection disabled

| **Severity** | P3 | **Evidence** | Supabase auth advisor |

### R-017: Notification permission on page load

| **Severity** | P3 | **App** | Customer homepage |

### R-018: pgTAP coverage gap (0013–0070)

| **Severity** | P3 |

### R-019: Admin audit log UI missing

| **Severity** | P3 | **Status** | NOT_IMPLEMENTED |

### R-021: PDF payout statement stub

| **Severity** | P3 |

### R-022: T2 KYC upgrade stub copy

| **Severity** | P3 |

---

## INFO

### R-030: Zero production orders/payments

Pre-launch state — 0 rows in `orders`, `payments`, `payouts`. Money paths untested in prod.

### R-031: Production API fully serves admin routes

OpenAPI: 67 admin operations; probes return 401 not 404.

### R-032: Seed/demo catalog data

150 products, 134 listings — likely demo seed, not live merchant inventory.

---

## BLOCKED_EXTERNAL

| ID    | Item                    | Reason                       |
| ----- | ----------------------- | ---------------------------- |
| B-001 | Vercel env var values   | Secrets not exposed via MCP  |
| B-002 | Mobile 390px UI audit   | Device emulation unavailable |
| B-003 | Admin authenticated UI  | CF Access + no credentials   |
| B-004 | Lenco live payment test | Real-money prohibited        |

---

## NOT_DEPLOYED

| ID    | Item                  | Evidence                   |
| ----- | --------------------- | -------------------------- |
| N-001 | End-to-end money flow | 0 payments in DB           |
| N-002 | KYC approval workflow | 0 kyc_records              |
| N-003 | Notification delivery | 0 notification_outbox rows |
| N-004 | Independent DB backup | Workflow inactive          |

---

## NOT_IMPLEMENTED

| ID    | Feature                                                 |
| ----- | ------------------------------------------------------- |
| I-001 | Admin user management UI                                |
| I-002 | Admin audit log browser                                 |
| I-003 | Admin refunds UI                                        |
| I-004 | Vendor staff/RBAC                                       |
| I-005 | Fine-grained admin roles (support/finance/KYC reviewer) |
| I-006 | Automation monitoring dashboard                         |
