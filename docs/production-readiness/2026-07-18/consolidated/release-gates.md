# Release Gates — Vergeo5 / Convergeo

**Date:** 2026-07-18  
**Purpose:** Exact automated and manual evidence required before real-money / public release.  
**Rule:** A gate is **PASS** only with VERIFIED evidence. PARTIAL / NOT_AUDITABLE = **FAIL**.  
**While any P0 gate fails, the system is not production-ready** (no readiness %).

Related: `master-reconciliation-register.md` · `production-readiness-scorecard.md`

---

## Gate statuses

| Status | Meaning                                                                                      |
| ------ | -------------------------------------------------------------------------------------------- |
| PASS   | VERIFIED evidence attached (link, SHA, query result, screenshot path, test log)              |
| FAIL   | Missing, broken, or contradicted                                                             |
| WAIVED | Founder-signed waiver with expiry + residual risk (rare; never for ledger/RLS/false-success) |

---

## P0 gates (must all PASS)

### G0 — Authentication and authorization / RLS

| Check                                                 | Automated evidence                                     | Manual evidence                  | Pass criteria                                         |
| ----------------------------------------------------- | ------------------------------------------------------ | -------------------------------- | ----------------------------------------------------- |
| RLS enabled on public business tables                 | SQL: `relrowsecurity` inventory                        | —                                | No unexpected `rls_enabled=false` on money/PII tables |
| FORCE RLS decision on ticket tier + product_relations | SQL: `relforcerowsecurity`                             | Security note                    | `true` **or** signed exception (MR-R01/R02)           |
| Role isolation                                        | API/RLS test suite (customer/vendor/admin)             | Attempt cross-tenant read → deny | Isolation tests green                                 |
| Role provisioning path                                | Migration `0051` applied **or** documented manual path | Auth hook enabled if using 0051  | JWT/`user_roles` consistent (MR-S02)                  |
| Admin Access                                          | HTTP: Access challenge without token                   | Access policy review             | Unauthenticated admin blocked                         |

```sql
-- Automated probe (READ ONLY)
BEGIN READ ONLY;
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='public' AND c.relkind='r'
  AND c.relname IN (
    'orders','payments','ledger_transactions','ledger_postings',
    'tickets','ticket_type_instances','ticket_type_price_tiers',
    'user_roles','vendors','vendor_listings','kyc_records','product_relations'
  )
ORDER BY 1;
COMMIT;
```

```bash
# Admin must not be anonymously open
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
# Expect 302/401/403 (Access), not 200 app shell for anonymous.
```

**Current:** FAIL (migration drift, FORCE RLS false on ticket tiers, role hook absent).

---

### G1 — Customer / vendor / admin route integrity

| Check                         | Automated                                                    | Manual                          | Pass criteria                                                |
| ----------------------------- | ------------------------------------------------------------ | ------------------------------- | ------------------------------------------------------------ |
| Customer health               | `GET /en/health` → 200                                       | Spot-check home + catalog       | `{"status":"ok","app":"customer"}`                           |
| Vendor health                 | `GET /en/health` → auth redirect OK                          | Login empty-state               | App reachable; no 5xx                                        |
| Admin health                  | Access challenge                                             | Access login → health/dashboard | No anonymous data leak                                       |
| Critical customer routes      | Script HTTP codes for `/en`, `/en/sell`, catalog-linked PDPs | —                               | No unexpected 5xx; sell CTA policy met (G2)                  |
| Deploy SHA parity (frontends) | Vercel production SHAs                                       | —                               | customer/vendor/admin SHAs recorded + match intended release |
| API health                    | `/healthz` + `/readyz` 200                                   | —                               | OK behind Caddy                                              |

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://vendor.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
curl -sS -m 15 https://api.vergeo5.com/healthz
curl -sS -m 15 https://api.vergeo5.com/readyz
```

**Current:** Conditional PASS on health shells; FAIL overall until sell CTA + API SHA recorded.

---

### G2 — No localhost production links

| Check                                 | Automated                                              | Manual        | Pass criteria                     |
| ------------------------------------- | ------------------------------------------------------ | ------------- | --------------------------------- |
| Customer HTML has no `localhost:3001` | Grep sell + home HTML                                  | —             | Zero matches                      |
| Seller CTA points to vendor prod      | Parse CTA href                                         | Click-through | `https://vendor.vergeo5.com…`     |
| Source maps / public env              | Build grep for localhost in prod bundles if applicable | —             | No prod localhost vendor/API URLs |

```bash
curl -sS -m 15 -o /tmp/sell.html https://www.vergeo5.com/en/sell
python3 -c 'from pathlib import Path;h=Path("/tmp/sell.html").read_text();
import sys; bad="localhost:3001" in h or "127.0.0.1" in h; print("FAIL" if bad else "PASS", "localhost");
print("unavailable_present", "unavailable" in h.lower())'
```

**Current:** PASS on localhost leak (fail-closed); FAIL on CTA availability (MR-C01).

---

### G3 — Payment ledger / reconciliation correctness

| Check                         | Automated                         | Manual                           | Pass criteria                                       |
| ----------------------------- | --------------------------------- | -------------------------------- | --------------------------------------------------- |
| Sandbox MoMo prepaid → ledger | Integration test + SQL aggregates | Lenco dashboard match (redacted) | `CHARGE_RECEIVED` + `ESCROW_HOLD` balanced (MR-B01) |
| Sandbox card prepaid → ledger | Same                              | Same                             | Same                                                |
| Webhook idempotency           | Replay same webhook               | —                                | Single ledger txn; payment status stable            |
| Reconciliation cron           | n8n execution success             | Recon report on forced mismatch  | Mismatch alerted; no silent drift                   |
| Money = integer ngwee         | Unit/contract tests               | Code review                      | No float money math                                 |

```bash
# Repo invariant (local CI)
cd services/api && uv run pytest -q -k 'ledger or payment or escrow' --maxfail=1
# After sandbox order (IDs redacted):
# SELECT count(*) FROM payments WHERE status='succeeded';
# SELECT count(*) FROM ledger_transactions;
# Expect both >0 in sandbox project only.
```

**Current:** FAIL (0 payments/ledger; prepaid hook PARTIAL).

---

### G4 — No false payment-success state

| Check              | Automated                                   | Manual | Pass criteria                                                                            |
| ------------------ | ------------------------------------------- | ------ | ---------------------------------------------------------------------------------------- |
| Pending payment UI | E2E: initiate then abandon                  | —      | UI shows pending/failed, **not** success                                                 |
| Webhook delay      | E2E: success UI only after confirmed status | —      | Success screen requires API success **and** ledger post (or explicit “confirming” state) |
| COD path           | E2E COD ≤K500                               | —      | COD never claims MoMo success                                                            |

**Current:** FAIL (unproven; CUST-08).

---

### G5 — Workflow reliability / retries

| Check                      | Automated                                       | Manual                           | Pass criteria                       |
| -------------------------- | ----------------------------------------------- | -------------------------------- | ----------------------------------- |
| Escrow auto-release active | n8n `search_workflows` shows active release-job | One sandbox release tick         | Active + success execution (MR-W01) |
| Tickets-issue active       | Same for tickets-issue                          | Paid ticket → exactly one ticket | No double-issue on retry (MR-W02)   |
| Internal ticks auth        | Unauthorized tick → 401/403                     | —                                | Tokens required                     |
| Notification dispatch      | Live workflow (already present)                 | Sandbox send                     | Outbox drains; retry safe           |

```text
Evidence pack:
- n8n workflow IDs + active=true screenshots/export
- Execution IDs for dry-run + sandbox money drill
- API logs for /internal/*/tick (redacted)
```

**Current:** FAIL (only dispatch + payment recon live).

---

### G6 — Error monitoring and actionable logs

| Check                                               | Automated                      | Manual            | Pass criteria                                      |
| --------------------------------------------------- | ------------------------------ | ----------------- | -------------------------------------------------- |
| Sentry projects exist for customer/vendor/admin/API | Sentry API/MCP list            | —                 | Vergeo5 projects present (MR-O01)                  |
| Test error ingested                                 | Trigger test exception per app | Sentry event link | Event visible with release tag                     |
| Uptime on health endpoints                          | Monitor API                    | —                 | Monitors green (MR-O02)                            |
| Payment/webhook errors actionable                   | Log query / Sentry issue       | —                 | Alert on webhook signature fail / ledger post fail |

**Current:** FAIL (no Vergeo5 Sentry projects).

---

### G7 — Backups and restore proof

| Check                   | Automated                                    | Manual                                | Pass criteria                         |
| ----------------------- | -------------------------------------------- | ------------------------------------- | ------------------------------------- |
| Scheduled backup exists | n8n backup workflow **or** host cron listing | OCI object listing (names/dates only) | Dated artifact within RPO (MR-W04)    |
| Restore drill           | —                                            | Restore to scratch DB                 | Documented success + RPO/RTO (MR-O04) |
| Pre-migration backup    | Checklist before MR-S01 apply                | —                                     | Backup timestamp before migrate       |

**Current:** FAIL / NOT_AUDITABLE.

---

### G8 — Critical test suite and CI gates

| Check                          | Automated                                                               | Manual               | Pass criteria                      |
| ------------------------------ | ----------------------------------------------------------------------- | -------------------- | ---------------------------------- |
| JS lint/typecheck/test         | `pnpm lint && pnpm typecheck && pnpm test`                              | —                    | Green on release commit            |
| API lint/type/tests            | `uv run ruff check . && uv run mypy app tests scripts && uv run pytest` | —                    | Green                              |
| Money/authz failure-path tests | pytest markers                                                          | —                    | Present + green for ledger/RBAC    |
| secret-scan blocking           | CI job without `continue-on-error`                                      | Branch protection UI | Required check; no bypass (MR-R05) |
| Contract/OpenAPI checks        | CI workflow                                                             | —                    | Required on `master`               |

```bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; export PATH="$HOME/.local/bin:$PATH"
pnpm lint && pnpm typecheck && pnpm test
cd services/api && uv run ruff check . && uv run mypy app tests scripts && uv run pytest
rg -n "continue-on-error" .github/workflows/*.yml
```

**Current:** FAIL (secret-scan/Lighthouse non-blocking; branch protection NOT_AUDITABLE).

---

### G9 — Deployment / rollback evidence

| Check                             | Automated                                      | Manual                                   | Pass criteria                                   |
| --------------------------------- | ---------------------------------------------- | ---------------------------------------- | ----------------------------------------------- |
| Frontend SHAs recorded            | Vercel `list_deployments`                      | —                                        | SHA per app in release ledger                   |
| API image digest recorded         | Host `API_IMAGE_TAG` / `docker inspect` / GHCR | —                                        | Digest ≠ unknown (MR-B10)                       |
| DB migrations match agreed target | `schema_migrations` query                      | —                                        | No silent drift (MR-S01)                        |
| Rollback drill                    | —                                              | Redeploy previous Vercel + prior API tag | Rollback procedure executed once; time recorded |
| Feature flags                     | SQL flags                                      | —                                        | `public_launch` intentional; Zamtel matches UI  |

**Current:** FAIL (API SHA NOT_AUDITABLE; DB drift CONFLICT).

---

## P1 gates (required before open public positioning)

| ID  | Gate                                    | Evidence                        | Current |
| --- | --------------------------------------- | ------------------------------- | ------- |
| G10 | Seller CTA live                         | CUST-01 HTML probe              | FAIL    |
| G11 | Demo catalogue remediated/labelled      | Catalog aggregate + SEO check   | FAIL    |
| G12 | KYC integrity                           | No tier>0 without `kyc_records` | FAIL    |
| G13 | Legal counsel sign-off (DPA/NPS escrow) | Written artifact (MR-L01)       | FAIL    |
| G14 | Zamtel collections decision + UI gate   | Flag + checkout methods         | FAIL    |
| G15 | Admin RBAC decision closed              | ADR / decisions update          | FAIL    |
| G16 | Staging UAT (core journeys)             | UAT notes 3–5 testers           | FAIL    |

---

## P2 gates (hardening; track but do not block invite-beta)

| ID  | Gate                                 | Notes                  |
| --- | ------------------------------------ | ---------------------- |
| G17 | Vernacular Bemba/Nyanja core flows   | After 0053; D27 timing |
| G18 | Lighthouse budgets                   | Perf/SEO/A11y          |
| G19 | Leaked-password protection on        | Auth advisor           |
| G20 | Lifecycle n8n (abandoned cart, etc.) | After money path       |
| G21 | Doc SoT banners on superseded plans  | MR-L02                 |

---

## Release evidence pack (template)

Attach to the release PR / ops ledger:

```text
release_id:
git_sha_frontends: {customer, vendor, admin}
api_image_digest:
db_migration_head:
n8n_workflows_active: [list]
sentry_projects: [list]
uptime_monitors: [list]
backup_artifact: {date, location}
restore_drill: {date, result}
sandbox_payments: {momo_payment_id_redacted, card_payment_id_redacted, ledger_txn_ids}
rls_probe: {path to SQL output}
ci_run_url:
rollback_drill: {date, result}
legal_signoff: {doc ref}
flags: {public_launch, zamtel_collections, ...}
gate_results: {G0..G9: PASS|FAIL}
```

---

## Go / No-Go

| Decision                           | Condition                                                                                                |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **NO-GO real money**               | Any of G0–G9 = FAIL or NOT_AUDITABLE                                                                     |
| **NO-GO public_launch=true**       | Any P0 gate FAIL **or** G10–G13 FAIL                                                                     |
| **GO invite-beta (no real money)** | Health G1 partial + localhost G2 localhost check PASS + explicit demo disclosure + `public_launch=false` |
| **GO real-money beta**             | All P0 gates PASS + G13 legal PASS + sandbox pack attached                                               |
| **GO open launch**                 | Real-money beta GO + G10–G16 PASS                                                                        |

**Today (2026-07-18): NO-GO** for real money and open launch.
