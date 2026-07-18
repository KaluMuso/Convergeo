# Executive Baseline — Vergeo5 Production Readiness (2026-07-18)

**Verdict:** The public customer site, vendor/admin Vercel apps, API health plane, and Supabase project are **live**, but the environment is a **demo catalogue** with **zero money operations**, **incomplete automation**, **schema drift vs git**, and **unproven prepaid ledger + observability**. Safe for parallel document audits; **not** ready to treat as a conclusive real-money production system.

---

## One-page snapshot

| Area           | Baseline fact                                                                             | Label                   |
| -------------- | ----------------------------------------------------------------------------------------- | ----------------------- |
| Customer       | `www.vergeo5.com` healthy; Cloudflare + Vercel; prod SHA `8cc1fa0`                        | VERIFIED                |
| Vendor         | `vendor.vergeo5.com` live (login-gated); prod SHA `8cc1fa0`                               | VERIFIED                |
| Admin          | Access-gated (`admin.vergeo5.com` / vercel.app 403); prod SHA `8cc1fa0`                   | VERIFIED                |
| API            | `api.vergeo5.com` `/healthz`+`/readyz` ok via Caddy; **image SHA unknown**                | PARTIAL / NOT_AUDITABLE |
| Database       | Supabase `dpadrlxukcjbewpqympu` healthy; applied ≤0050 + odd 0052; **missing 0051/53–55** | CONFLICT                |
| Catalogue      | 3 demo vendors, 134 listings, 134 `demo/` images; 0 orders/payments/ledger                | VERIFIED                |
| n8n            | Only dispatch + payment reconciliation active; escrow/tickets/backups absent              | VERIFIED MISSING        |
| Seller CTA     | No localhost leak; signup CTA unavailable (env unset)                                     | PARTIAL                 |
| Prepaid ledger | Success path updates payment status only (code); no live paid proof                       | PARTIAL                 |
| Observability  | No Vergeo5 Sentry projects; analytics tables empty                                        | MISSING / PARTIAL       |
| Flags          | `public_launch=false` (invite gate still on)                                              | VERIFIED                |
| Contract       | Evidence labels + SoT hierarchy in `document-audit-contract.md`                           | —                       |

**Parallel-session rule:** Prefer live evidence over git. Record NOT_AUDITABLE instead of guessing. Do not overwrite this foundation folder.

---

## Safe commands / queries for later sessions

### HTTP (no auth)

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -I https://www.vergeo5.com/en | head -40
curl -sS -m 15 https://api.vergeo5.com/healthz
curl -sS -m 15 https://api.vergeo5.com/readyz
curl -sS -m 20 "https://api.vergeo5.com/catalog/listings?limit=1" | python3 -c 'import sys,json;d=json.load(sys.stdin);print({k:d.get(k) for k in ("total","next_cursor")})'
curl -sS -m 15 -o /tmp/sell.html -w "%{http_code}\n" https://www.vergeo5.com/en/sell
python3 -c 'from pathlib import Path;h=Path("/tmp/sell.html").read_text();print("localhost", "localhost:3001" in h);print("unavailable", h.count("unavailable"))'
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://vendor.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://convergeo-admin.vercel.app/en/health
```

### Vercel MCP / API (read-only)

- `list_teams` → `list_projects(teamId)` → `list_deployments(projectId, teamId)` → record production `githubCommitSha`
- Projects: `convergeo-customer`, `convergeo-vendor`, `convergeo-admin`

### n8n MCP (read-only)

- `search_workflows` (limit 100) — compare names/active to `docs/ops/n8n-workflows.md`
- `get_workflow_details` for diffs — **do not** publish/activate/execute

### Supabase SQL (always read-only)

```sql
BEGIN READ ONLY;

-- Applied migrations
SELECT version, name
FROM supabase_migrations.schema_migrations
ORDER BY version;

-- Drift probes vs repo tip
SELECT
  to_regclass('public.translation_overrides') IS NOT NULL AS has_translation_overrides,
  to_regclass('public.product_relations') IS NOT NULL AS has_product_relations,
  EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname ILIKE '%custom_access_token%'
  ) AS has_role_hook;

-- Aggregates only (no PII)
SELECT
  (SELECT count(*)::int FROM vendors) AS vendors,
  (SELECT count(*)::int FROM vendor_listings) AS listings,
  (SELECT count(*)::int FROM listing_images WHERE cloudinary_public_id LIKE 'demo/%') AS demo_images,
  (SELECT count(*)::int FROM orders) AS orders,
  (SELECT count(*)::int FROM payments) AS payments,
  (SELECT count(*)::int FROM ledger_transactions) AS ledger_txns,
  (SELECT count(*)::int FROM tickets) AS tickets;

SELECT flag, enabled FROM feature_flags ORDER BY flag;

-- RLS policy inventory (metadata only)
SELECT tablename, policyname, cmd, roles::text
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;

-- RLS enablement / policy counts
WITH pol AS (
  SELECT tablename, count(*) AS policy_count
  FROM pg_policies WHERE schemaname = 'public' GROUP BY tablename
)
SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced,
       coalesce(p.policy_count, 0) AS policy_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pol p ON p.tablename = c.relname
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;

COMMIT;
```

Also: Supabase MCP `list_migrations`, `list_tables`, `get_advisors` (security) — read-only.

### Repo comparisons (local)

```bash
git rev-parse HEAD
ls supabase/migrations | wc -l
ls infra/n8n/*.json
rg -n "continue-on-error" .github/workflows/*.yml
rg -n "post_transaction|CHARGE_RECEIVED|ESCROW_HOLD" services/api/app/services/payments services/api/app/routers -g'*.py'
```

---

## Missing access / evidence (blocks conclusive audit)

1. **API container git SHA / image digest** (GHCR auth or host `API_IMAGE_TAG` / `docker inspect`)
2. **Vercel/API env values** (confirm `NEXT_PUBLIC_VENDOR_APP_URL`, Lenco, WhatsApp, Sentry DSNs) — read via dashboard least-privilege, never paste secrets into reports
3. **Sandbox prepaid MoMo/card end-to-end** proving ledger rows on success
4. **n8n credential health / execution success rates** (optional metadata); OCI backup object listing
5. **GitHub branch protection** actual required-check configuration
6. **UptimeRobot monitor state**
7. **Cloudflare Access policy details** (beyond challenge observation)
8. **Private storage bucket contents / KYC** (out of scope unless needed; keep redacted)
9. **Whether Auth custom access token hook is enabled** (after 0051 apply)

---

## Prioritized release blockers

| P   | Blocker                                                                                 | Why                             |
| --- | --------------------------------------------------------------------------------------- | ------------------------------- |
| P0  | Prepaid success → ledger posting unproven / likely missing                              | Money + escrow integrity        |
| P0  | n8n missing escrow auto-release + ticket issuance                                       | Core trust / events money paths |
| P0  | DB migration drift (`0051`, `0053`–`0055`; `0052` version skew)                         | Runtime ≠ git assumptions       |
| P1  | Seller CTA unavailable (`NEXT_PUBLIC_VENDOR_APP_URL`)                                   | Vendor acquisition broken       |
| P1  | Demo seed catalogue (134 demo images) before real-money public positioning              | Trust / SEO / compliance optics |
| P1  | No Vergeo5 Sentry projects / DSN wiring                                                 | Blind production                |
| P1  | Backup workflow not present in n8n (host cron unproven)                                 | RPO                             |
| P2  | CI `secret-scan` / Lighthouse / i18n non-blocking; branch-protection bypass unconfirmed | Regression risk                 |
| P2  | `public_launch=false` vs public DNS (invite vs open) clarity                            | Product gate                    |
| P3  | Wishlist/referrals/etc. only if business docs claim v1 inclusion                        | Scope alignment                 |

---

## Foundation file index

| File                           | Contents                                                 |
| ------------------------------ | -------------------------------------------------------- |
| `document-audit-contract.md`   | Labels, SoT hierarchy, row format, data classes, privacy |
| `architecture-inventory.md`    | Apps/services/env names/CI/deploy                        |
| `production-evidence.md`       | Live URLs, SHAs, migrations, n8n, demo counts            |
| `database-schema-inventory.md` | Tables by domain                                         |
| `access-and-rls-inventory.md`  | What we could/couldn’t read; RLS posture                 |
| `critical-risk-register.md`    | Known risks with evidence statuses                       |
| `executive-baseline.md`        | This page                                                |
