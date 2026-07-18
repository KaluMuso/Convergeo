# Access & RLS Inventory — Vergeo5

**Audit date:** 2026-07-18 · **Live project:** `dpadrlxukcjbewpqympu`  
**Mode:** READ-ONLY

---

## 1. Audit principal capabilities (this session)

| Access                                | Available?   | Notes                                |
| ------------------------------------- | ------------ | ------------------------------------ |
| Public customer/API HTTP              | yes          | health, catalog                      |
| Vercel team API (deployments/domains) | yes          | Vergeo Projects                      |
| Supabase project SQL (operator)       | yes          | used only for read-only SELECT       |
| n8n MCP list/detail workflows         | yes          | no activate/execute used             |
| Sentry org list/projects              | yes          | no Vergeo5 projects                  |
| GHCR private manifests                | **no**       | `UNAUTHORIZED`                       |
| API host SSH / `API_IMAGE_TAG`        | **no**       | NOT_AUDITABLE for API SHA            |
| Vercel env var _values_               | **not read** | by policy; behavior inferred         |
| Cloudflare Access admin console       | **no**       | only challenge responses observed    |
| Lenco dashboard / live payments       | **no**       | 0 payment rows; no payment tests run |
| OCI Object Storage backups            | **no**       | backup workflow absent in n8n        |

---

## 2. Application access surfaces

| Surface                  | Authn                                                       | Authz                               | Live observation                     |
| ------------------------ | ----------------------------------------------------------- | ----------------------------------- | ------------------------------------ |
| Customer web             | Supabase Auth (phone OTP/email/Google)                      | customer role + RLS via API         | Public browse works; `/en/health` ok |
| Vendor web               | Supabase Auth + middleware role gate                        | vendor owner scope                  | Unauth → login redirect              |
| Admin web                | Supabase Auth + **Cloudflare Access** (+ optional Caddy IP) | admin role                          | Access challenge / 403 without CF    |
| Public API reads         | anon/optional JWT                                           | RLS + service patterns              | Catalog public                       |
| Mutating API             | JWT + `require_role`                                        | authz matrix + rate limits          | not exercised                        |
| Internal ticks           | `X-Internal-Token`                                          | per-token env                       | n8n calls recon + dispatch only      |
| Supabase Storage private | signed URLs / service role                                  | KYC / order-evidence buckets (docs) | bucket contents NOT_AUDITABLE here   |

---

## 3. RLS posture (live)

### 3.1 Tables with RLS enabled + FORCE (typical)

Nearly all public business tables have `rls_enabled=true` and `rls_forced=true` with one or more policies (customer/vendor/admin/public-read patterns from migrations).

### 3.2 RLS enabled, **zero client policies** (service-role only by design)

Supabase advisor + `pg_class`/`pg_policies` agree:

| Table                 | Advisor                | Interpretation                      |
| --------------------- | ---------------------- | ----------------------------------- |
| `audit_log`           | RLS enabled, no policy | service-role writes; clients denied |
| `notification_outbox` | same                   | dispatcher only                     |
| `rate_counters`       | same                   | auth rate limiting                  |
| `stock_reservations`  | same                   | checkout holds                      |
| `user_roles`          | same                   | role grants not client-writable     |

Also noted with policy_count 0 in earlier inventory join: same set.

**Status:** VERIFIED intentional hard-deny for anon/authenticated direct table access (service role bypasses RLS).

### 3.3 FORCE RLS exceptions

| Table                     | `relforcerowsecurity` | Status                        |
| ------------------------- | --------------------- | ----------------------------- |
| `product_relations`       | false                 | PARTIAL — verify threat model |
| `ticket_type_instances`   | false                 | PARTIAL                       |
| `ticket_type_price_tiers` | false                 | PARTIAL                       |

### 3.4 Security advisor WARN findings (live)

| Finding                                              | Detail                                                              | Impact                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `extension_in_public`                                | `pg_trgm`, `vector` in `public`                                     | hygiene                                                                     |
| `anon_security_definer_function_executable`          | `has_role(text)`, `is_verified_business(uuid)` executable by `anon` | review EXECUTE grants (migration `0050` intended revoke — confirm coverage) |
| `authenticated_security_definer_function_executable` | same functions for `authenticated`                                  | same                                                                        |
| `auth_leaked_password_protection`                    | disabled                                                            | Auth hygiene                                                                |

Migration `0050_revoke_definer_execute_from_public` **is applied**; residual advisor WARNs ⇒ **PARTIAL/CONFLICT** — either incomplete revoke set or advisor still flags needed RPCs.

### 3.5 Role hook gap

Repo migration `0051_custom_access_token_role_hook` **not applied**. Function absent. Middleware still depends on `app_metadata.roles` for vendor/admin edge gates → **role provisioning remains manual** until hook applied **and** enabled in Auth dashboard (hook is dormant-by-design even after migrate).

---

## 4. Policy patterns by domain (summary)

Exact policy SQL not dumped (large; contains expressions). Patterns from migrations + live policy existence:

| Domain                     | Typical policies                                  |
| -------------------------- | ------------------------------------------------- |
| Customer carts/addresses   | owner `auth.uid()` CRUD                           |
| Catalogue public read      | published/active select for anon/authenticated    |
| Vendor listings/events     | owner vendor write; public read when published    |
| Orders                     | customer read own; vendor read own; admin all     |
| Payments                   | customer/admin read patterns; writes service-role |
| Ledger / outbox / webhooks | deny clients (0 policies)                         |
| Admin config/flags         | admin role via `has_role('admin')`                |
| Analytics                  | admin read; service-role write                    |

Full policy name listing available via safe query:

```sql
BEGIN READ ONLY;
SELECT tablename, policyname, cmd, roles::text
FROM pg_policies WHERE schemaname='public'
ORDER BY tablename, policyname;
COMMIT;
```

---

## 5. What later sessions must not assume

- Operator SQL access ≠ customer/vendor RLS view.
- Presence of a table in repo migrations ≠ applied on live.
- JWT `app_metadata.roles` may lag `user_roles` until 0051 applied + hook enabled.
- Admin Access bypass / `NEXT_PUBLIC_ADMIN_BYPASS` must never be enabled in production (env name only inventoried).
