# Release Gates — Vergeo5 / Convergeo

**Date:** 2026-07-18 (refresh after PRs #274, #289–#294)  
**Purpose:** Exact automated and manual evidence required before real-money / public release.  
**Rule:** A gate is **PASS** only with VERIFIED evidence at the required maturity layer. PARTIAL / NOT_AUDITABLE / CODE_COMPLETE-only = **FAIL** for launch.  
**While any P0 gate fails, the system is not production-ready** (no readiness %).

Related: `master-reconciliation-register.md` · `production-readiness-scorecard.md` · `panel-backlogs.md`

---

## Maturity required per gate class

| Gate class                           | Minimum maturity to PASS                                               |
| ------------------------------------ | ---------------------------------------------------------------------- |
| Code/unit invariants (CI)            | CODE_COMPLETE on release commit + green CI                             |
| Money, escrow, KYC privileges, RLS   | **STAGING_VERIFIED** (then PRODUCTION_VERIFIED before open real-money) |
| Public positioning / `public_launch` | **PRODUCTION_VERIFIED** probes on live URLs + flags                    |
| Legal                                | Written artifact (not code)                                            |

**Explicit:** PR **#274** collection accounting and PR **#294** release accounting are **CODE_COMPLETE** and **staging-unverified** → G3/G4 remain **FAIL**.  
**Explicit:** PR **#293** KYC integrity is **CODE_COMPLETE** while migration **`0056`** remains staging/production rollout-dependent → G12 remains **FAIL**.

---

## Gate statuses

| Status | Meaning                                                                                |
| ------ | -------------------------------------------------------------------------------------- |
| PASS   | VERIFIED evidence attached at required maturity                                        |
| FAIL   | Missing, broken, contradicted, or only CODE_COMPLETE                                   |
| WAIVED | Founder-signed waiver with expiry + residual risk (never for ledger/RLS/false-success) |

---

## Staging gates (must PASS before production money enablement)

| ID  | Gate                                    | Automated evidence             | Manual evidence                    | Pass criteria                                                                | Current                                                                                           |
| --- | --------------------------------------- | ------------------------------ | ---------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| S0  | Staging schema target                   | `schema_migrations` on staging | Migration plan review              | Agreed set includes needed `0051`/`0053`–`0056` as decided                   | FAIL                                                                                              |
| S1  | Sandbox MoMo prepaid → ledger           | SQL aggregates + pytest        | Lenco sandbox dashboard (redacted) | `CHARGE_RECEIVED` (+ hold posture) balanced; idempotent replay               | FAIL / BLOCKED_EXTERNAL (2026-07-20 Prompt 8: no F9b + API 502; `…/lenco-sandbox-money-drill.md`) |
| S2  | Sandbox card prepaid → ledger           | Same                           | Same                               | Same                                                                         | FAIL / BLOCKED_EXTERNAL (same preflight)                                                          |
| S3  | Release accounting drill                | Release tick + SQL             | Recon summary fields               | `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR`; escrow→0; double-tick safe  | FAIL / BLOCKED_EXTERNAL (same; release ticks inactive)                                            |
| S4  | n8n release + tickets active on staging | Workflow active=true           | Execution IDs                      | Authenticated ticks succeed; no double release/issue                         | FAIL                                                                                              |
| S5  | KYC lifecycle drill                     | API tests + SQL                | Admin Access session               | submit→under_review→approve; orphan report; privileges freeze without record | FAIL (`0056` unapplied live)                                                                      |
| S6  | False-success E2E                       | Playwright/E2E                 | —                                  | Pending/failed ≠ paid; COD isolated                                          | FAIL / BLOCKED_EXTERNAL (Prompt 8 D NOT RUN)                                                      |
| S7  | Staging UAT notes                       | —                              | 3–5 tester journeys                | Written pack attached                                                        | FAIL                                                                                              |

---

## P0 production gates (must all PASS for real-money)

### G0 — Authentication / authorization / RLS

| Check                                                    | Automated                             | Manual                  | Pass criteria                  |
| -------------------------------------------------------- | ------------------------------------- | ----------------------- | ------------------------------ |
| RLS enabled on money/PII tables                          | SQL `relrowsecurity` inventory        | —                       | No unexpected disabled RLS     |
| FORCE RLS on ticket tiers (+ product_relations decision) | `relforcerowsecurity`                 | FD-07 note              | `true` **or** signed exception |
| Role isolation                                           | customer/vendor/admin suites          | Cross-tenant deny       | Tests green                    |
| Role provisioning                                        | `0051` applied **or** FD-03 exception | Auth hook if using 0051 | JWT/`user_roles` consistent    |
| Admin Access                                             | HTTP challenge without token          | Policy review           | Anonymous blocked              |
| KYC migration                                            | `0056` in `schema_migrations`         | Orphan report           | Trigger/view present           |

```sql
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
SELECT version, name FROM supabase_migrations.schema_migrations
WHERE version LIKE '%0051%' OR version LIKE '%0056%' OR name ILIKE '%kyc_integrity%'
ORDER BY version;
COMMIT;
```

**Current:** FAIL (migration drift; FORCE RLS false on ticket tiers; role hook absent; `0056` not applied).

---

### G1 — Customer / vendor / admin route integrity

| Check                        | Automated                                          | Manual     | Pass criteria                                                    |
| ---------------------------- | -------------------------------------------------- | ---------- | ---------------------------------------------------------------- |
| Customer/vendor/admin health | HTTP probes                                        | Spot-check | Health OK; admin Access-gated                                    |
| Critical customer routes     | `/en`, `/en/sell`, `/en/categories`, `/en/compare` | —          | Expected codes; honesty empty OK                                 |
| Deploy SHA parity            | Vercel production SHAs                             | —          | Intended release SHAs recorded (include #289–#291 when deployed) |
| API health                   | `/healthz` `/readyz`                               | —          | 200 behind Caddy                                                 |

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/categories
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/compare
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://vendor.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
curl -sS -m 15 https://api.vergeo5.com/healthz
curl -sS -m 15 https://api.vergeo5.com/readyz
```

**Current:** Conditional PASS on health shells; FAIL overall until panel deploy PRODUCTION_VERIFIED + sell CTA policy (G2/G10).

---

### G2 — No localhost production links

| Check                                                 | Automated            | Manual        | Pass criteria                 |
| ----------------------------------------------------- | -------------------- | ------------- | ----------------------------- |
| No `localhost:3001` in customer HTML                  | Grep sell/home       | —             | Zero matches                  |
| Seller CTA → vendor prod                              | Parse href           | Click-through | `https://vendor.vergeo5.com…` |
| No prod `localhost:8000` API fallbacks on money paths | Bundle/source review | —             | Fail-closed                   |

**Current:** PASS on vendor localhost leak (fail-closed); FAIL on CTA availability; PARTIAL on residual API localhost fallbacks (integration review).

---

### G3 — Payment ledger / reconciliation correctness

| Check                        | Automated   | Manual          | Pass criteria                            |
| ---------------------------- | ----------- | --------------- | ---------------------------------------- |
| Sandbox MoMo → ledger        | S1          | Lenco match     | Collection posts (#274) STAGING_VERIFIED |
| Sandbox card → ledger        | S2          | Same            | Same                                     |
| Release capture → vendor net | S3          | Recon fields    | #294 invariants STAGING_VERIFIED         |
| Webhook idempotency          | Replay      | —               | Single ledger txn                        |
| Recon cron                   | n8n success | Forced mismatch | Alerted; no silent drift                 |
| Integer ngwee only           | Unit tests  | Review          | No float money math                      |

**Current:** FAIL — CODE_COMPLETE only (#274/#294); live `payments=0`, `ledger_transactions=0`. Prompt 8 sandbox drill **BLOCKED_EXTERNAL** (`docs/production-readiness/2026-07-20/lenco-sandbox-money-drill.md`) — no F9b creds; API 502; tip mismatch.

---

### G4 — No false payment-success state

| Check         | Automated   | Manual | Pass criteria                                                                                |
| ------------- | ----------- | ------ | -------------------------------------------------------------------------------------------- |
| Pending UI    | E2E abandon | —      | Not success                                                                                  |
| Webhook delay | E2E         | —      | Success only after confirmed policy (order_confirmed / confirming≠paid; ledger per contract) |
| COD path      | E2E ≤K500   | —      | Never claims MoMo success                                                                    |

**Current:** FAIL — UI CODE_COMPLETE (#289); staging E2E open; Prompt 8 false-success matrix **NOT RUN** (BLOCKED_EXTERNAL).

---

### G5 — Workflow reliability / retries

| Check                                  | Automated              | Manual                   | Pass criteria   |
| -------------------------------------- | ---------------------- | ------------------------ | --------------- |
| Escrow auto-release active             | n8n active release-job | Sandbox release tick     | MR-W01          |
| Tickets-issue (+ event-release) active | n8n                    | Paid ticket exactly-once | MR-W02          |
| Internal ticks auth                    | Unauthorized → 401/403 | —                        | Tokens required |
| Notification dispatch                  | Live workflow          | Sandbox send             | Outbox drains   |

**Current:** FAIL (Prompt 8 did not activate money workflows; release/tickets still inactive; see also n8n fleet evidence).

---

### G6 — Error monitoring and actionable logs

| Check                             | Automated       | Manual     | Pass criteria                  |
| --------------------------------- | --------------- | ---------- | ------------------------------ |
| Sentry projects exist             | Sentry list     | —          | Vergeo5 projects present       |
| Test error ingested               | Trigger per app | Event link | Release tags match             |
| Uptime on health                  | Monitor API     | —          | Monitors green                 |
| Payment/webhook errors actionable | Sentry/log      | —          | Alert on signature/ledger fail |

**Current:** FAIL (no Vergeo5 Sentry projects; uptime NOT_AUDITABLE).

---

### G7 — Backups and restore proof

| Check                | Automated                 | Manual               | Pass criteria             |
| -------------------- | ------------------------- | -------------------- | ------------------------- |
| Scheduled backup     | n8n or host cron listing  | OCI names/dates only | Dated artifact within RPO |
| Restore drill        | —                         | Scratch restore      | Documented success        |
| Pre-migration backup | Checklist before DB-01/02 | —                    | Timestamp before migrate  |

**Current:** FAIL / NOT_AUDITABLE.

---

### G8 — Critical test suite and CI gates

| Check                              | Automated                                  | Manual               | Pass criteria           |
| ---------------------------------- | ------------------------------------------ | -------------------- | ----------------------- |
| JS lint/typecheck/test             | `pnpm lint && pnpm typecheck && pnpm test` | —                    | Green on release commit |
| API lint/type/tests                | `uv run ruff` / `mypy` / `pytest`          | —                    | Green                   |
| Money/KYC/authz failure-path tests | pytest incl. prepaid/release/kyc suites    | —                    | Present + green         |
| secret-scan blocking               | CI without `continue-on-error`             | Branch protection UI | Required; no bypass     |
| Contract/OpenAPI checks            | CI                                         | —                    | Required on `master`    |

**Current:** FAIL (secret-scan/Lighthouse non-blocking; branch protection NOT_AUDITABLE). Note: panel integration recorded green lint/type/test/build on combined master for apps — does not clear G8 security gates.

---

### G9 — Deployment / rollback evidence

| Check                      | Automated           | Manual                 | Pass criteria                                  |
| -------------------------- | ------------------- | ---------------------- | ---------------------------------------------- |
| Frontend SHAs recorded     | Vercel deployments  | —                      | SHA per app                                    |
| API image digest recorded  | Host/GHCR           | —                      | Digest ≠ unknown                               |
| DB migrations match target | `schema_migrations` | —                      | Incl. agreed `0056`                            |
| Rollback drill             | —                   | Prior Vercel + API tag | Time recorded                                  |
| Feature flags              | SQL flags           | —                      | `public_launch` intentional; Zamtel matches UI |

**Current:** FAIL (API SHA NOT_AUDITABLE; DB drift; panel SHAs not PRODUCTION_VERIFIED vs foundation `8cc1fa0`).

---

## P1 gates (required before open public positioning)

| ID  | Gate                                  | Evidence                                                          | Current                        |
| --- | ------------------------------------- | ----------------------------------------------------------------- | ------------------------------ |
| G10 | Seller CTA live                       | CUST-01 HTML probe                                                | FAIL                           |
| G11 | Demo catalogue remediated/labelled    | Catalog + SEO; FD-04                                              | FAIL                           |
| G12 | KYC integrity live                    | No privileged bare tier; `0056` applied; orphan ops               | FAIL (CODE_COMPLETE #293 only) |
| G13 | Legal counsel sign-off                | Written artifact FD-08                                            | FAIL                           |
| G14 | Zamtel collections decision + UI gate | FD-01 + checkout methods                                          | FAIL                           |
| G15 | Admin RBAC decision closed            | FD-02 ADR/decisions                                               | FAIL                           |
| G16 | Staging UAT (core journeys)           | S7 pack                                                           | FAIL                           |
| G17 | Panel honesty PRODUCTION_VERIFIED     | Deploy #289–#291; probe categories/compare/SW/admin empty honesty | FAIL                           |

---

## P2 gates (hardening; track but do not block invite-beta)

| ID  | Gate                                | Notes                  |
| --- | ----------------------------------- | ---------------------- |
| G18 | Vernacular Bemba/Nyanja core flows  | After 0053; D27 timing |
| G19 | Lighthouse budgets                  | Perf/SEO/A11y          |
| G20 | Leaked-password protection on       | Auth advisor           |
| G21 | Lifecycle n8n                       | After money path       |
| G22 | Doc SoT banners on superseded plans | MR-L02                 |

---

## Release evidence pack (template)

```text
release_id:
git_sha_frontends: {customer, vendor, admin}
api_image_digest:
db_migration_head:
migrations_applied_includes_0056: yes|no
n8n_workflows_active: [list]
sentry_projects: [list]
uptime_monitors: [list]
backup_artifact: {date, location}
restore_drill: {date, result}
sandbox_payments:
  momo: {payment_id_redacted, ledger_txn_ids}
  card: {payment_id_redacted, ledger_txn_ids}
  release: {capture_id_redacted, release_id_redacted, escrow_net}
rls_probe: {path}
kyc:
  migration_0056: applied|not
  orphan_report_count:
ci_run_url:
rollback_drill: {date, result}
legal_signoff: {doc ref}
flags: {public_launch, zamtel_collections, ...}
code_complete_prs: {274, 288, 289, 290, 291, 293, 294}
maturity:
  collection_accounting: CODE_COMPLETE|STAGING_VERIFIED|PRODUCTION_VERIFIED
  release_accounting: CODE_COMPLETE|STAGING_VERIFIED|PRODUCTION_VERIFIED
  kyc_integrity: CODE_COMPLETE|STAGING_VERIFIED|PRODUCTION_VERIFIED
gate_results: {S0..S7, G0..G9: PASS|FAIL}
```

---

## Go / No-Go

| Decision                           | Condition                                                                            |
| ---------------------------------- | ------------------------------------------------------------------------------------ |
| **NO-GO real money**               | Any of G0–G9 = FAIL/NOT_AUDITABLE **or** S1–S6 = FAIL                                |
| **NO-GO public_launch=true**       | Any P0 gate FAIL **or** G10–G13 FAIL                                                 |
| **GO invite-beta (no real money)** | Health shells OK + G2 localhost check PASS + demo disclosure + `public_launch=false` |
| **GO real-money beta**             | All P0 gates PASS + G13 legal PASS + staging pack STAGING_VERIFIED attached          |
| **GO open launch**                 | Real-money beta GO + G10–G17 PASS                                                    |

### Today (2026-07-18)

| Claim                             | Result                                           |
| --------------------------------- | ------------------------------------------------ |
| Real money                        | **NO-GO**                                        |
| Open launch                       | **NO-GO**                                        |
| Invite/demo browse                | Conditional OK with disclosure                   |
| Treat #274/#294 as launch-cleared | **NO** — CODE_COMPLETE, staging-unverified       |
| Treat #293 as launch-cleared      | **NO** — CODE_COMPLETE, `0056` rollout-dependent |

---

_Do not declare production readiness while payment reconciliation, migration rollout, RLS, workflows, monitoring, backup/restore, rollback, or live configuration evidence remains incomplete._
