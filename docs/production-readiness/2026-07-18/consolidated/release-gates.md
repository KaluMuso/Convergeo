# Release Gates — Vergeo5 / Convergeo

**Date:** 2026-07-18 (post-implementation refresh)  
**Master tip:** `d5c2134`  
**Purpose:** Exact automated and manual evidence required before staging enablement and production real-money / public release.  
**Rule:** A gate is **PASS** only with VERIFIED evidence at the named environment. PARTIAL / NOT_AUDITABLE / NOT_RUN = **FAIL**.  
**While any P0 production gate fails, the system is not production-ready** (no readiness %).

Related: `master-reconciliation-register.md` · `production-readiness-scorecard.md` · `implementation-wave-plan.md`

---

## Gate statuses

| Status | Meaning                                                                                          |
| ------ | ------------------------------------------------------------------------------------------------ |
| PASS   | VERIFIED evidence attached (link, SHA, query result, screenshot path, test log)                  |
| FAIL   | Missing, broken, contradicted, or not yet run                                                    |
| WAIVED | Founder-signed waiver with expiry + residual risk (rare; **never** for ledger/RLS/false-success) |

Each P0 gate tracks **Code** · **Staging** · **Production** separately. Unit tests and merged PRs satisfy **Code** only.

---

## Environment definitions

| Env            | Meaning                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------ |
| **Code**       | `master` tip builds/tests; does not prove live behaviour                                   |
| **Staging**    | Dedicated sandbox (Lenco sandbox + non-prod DB or isolated project) with controlled drills |
| **Production** | Live `*.vergeo5.com` + Supabase `dpadrlxukcjbewpqympu` + Hetzner API + n8n                 |

---

## P0 gates (must all PASS for real-money production)

### G0 — Authentication / authorization / RLS

| Check                                         | Automated                           | Manual                  | Pass criteria                               |
| --------------------------------------------- | ----------------------------------- | ----------------------- | ------------------------------------------- |
| RLS on money/PII tables                       | SQL `relrowsecurity` inventory      | —                       | No unexpected `rls_enabled=false`           |
| FORCE RLS on ticket tiers + product_relations | SQL `relforcerowsecurity`           | Security note           | `true` **or** signed exception (MR-R01/R02) |
| Role isolation                                | API/RLS suite                       | Cross-tenant deny       | Isolation green                             |
| Role provisioning                             | `0051` applied **or** exception doc | Auth hook if using 0051 | JWT/`user_roles` consistent                 |
| Admin Access                                  | HTTP challenge without token        | Policy review           | Anonymous admin blocked                     |

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
COMMIT;
```

| Layer      | Current (2026-07-18)                                                          |
| ---------- | ----------------------------------------------------------------------------- |
| Code       | PARTIAL (migrations in repo; FORCE RLS still to decide)                       |
| Staging    | FAIL / NOT_RUN                                                                |
| Production | **FAIL** (migration drift; FORCE RLS false on ticket tiers; role hook absent) |

---

### G1 — Customer / vendor / admin route integrity

| Check                        | Automated                                                    | Manual            | Pass criteria                           |
| ---------------------------- | ------------------------------------------------------------ | ----------------- | --------------------------------------- |
| Customer/vendor/admin health | `GET /en/health`                                             | Spot-check shells | Healthy; admin Access-gated             |
| Critical customer routes     | HTTP codes incl. `/en/categories`, `/en/compare`, `/en/sell` | —                 | No unexpected 5xx; sell policy met (G2) |
| Deploy SHA parity            | Vercel production SHAs                                       | —                 | Match intended release tip              |
| API health                   | `/healthz` + `/readyz`                                       | —                 | 200 behind Caddy                        |

```bash
curl -sS -m 15 https://www.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://vendor.vergeo5.com/en/health
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://admin.vergeo5.com/en/health
curl -sS -m 15 https://api.vergeo5.com/healthz
curl -sS -m 15 https://api.vergeo5.com/readyz
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/categories
curl -sS -m 15 -o /dev/null -w "%{http_code}\n" https://www.vergeo5.com/en/compare
```

| Layer      | Current                                                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Code       | **PASS** (#289–#291 merged; health shells)                                                                                     |
| Staging    | FAIL / NOT_RUN (deploy tip not verified)                                                                                       |
| Production | **FAIL overall** — health shells OK at foundation SHA `8cc1fa0`; tip undeployed; sell CTA down; categories/compare 404 on live |

---

### G2 — No localhost production links + seller CTA policy

| Check                                                | Automated        | Manual        | Pass criteria                                 |
| ---------------------------------------------------- | ---------------- | ------------- | --------------------------------------------- |
| No `localhost:3001` in customer HTML                 | Grep sell + home | —             | Zero matches                                  |
| Seller CTA → vendor prod **or** explicit unavailable | Parse href       | Click-through | Prod vendor URL when env set; never localhost |

| Layer      | Current                                                      |
| ---------- | ------------------------------------------------------------ |
| Code       | PASS (fail-closed)                                           |
| Staging    | FAIL / NOT_RUN                                               |
| Production | **PARTIAL** — localhost PASS; CTA availability FAIL (MR-C01) |

---

### G3 — Payment ledger / release accounting / reconciliation

| Check                          | Automated           | Manual                 | Pass criteria                                                         |
| ------------------------------ | ------------------- | ---------------------- | --------------------------------------------------------------------- |
| Sandbox MoMo prepaid → ledger  | Integration + SQL   | Lenco match (redacted) | `CHARGE_RECEIVED` + escrow legs balanced (#274)                       |
| Sandbox card prepaid → ledger  | Same                | Same                   | Same                                                                  |
| Release capture-before-release | SQL + release tick  | —                      | `COMMISSION_CAPTURE` before `RELEASE_TO_VENDOR`; escrow nets 0 (#294) |
| Webhook idempotency            | Replay same webhook | —                      | Single ledger txn                                                     |
| Reconciliation cron            | n8n execution       | Forced mismatch        | Alerted; no silent drift                                              |
| Money = integer ngwee          | Unit/contract tests | Review                 | No float money math                                                   |

```bash
cd services/api && uv run pytest -q -k 'ledger or payment or escrow or settle_prepaid or release_accounting' --maxfail=1
# After sandbox order (IDs redacted):
# SELECT count(*) FROM payments WHERE status IN ('succeeded','success');
# SELECT count(*) FROM ledger_transactions;
# Expect both >0 in sandbox only.
```

| Layer      | Current                                                          |
| ---------- | ---------------------------------------------------------------- |
| Code       | **PASS** (#274 + #294 + pytest)                                  |
| Staging    | **FAIL** — sandbox drill NOT_RUN                                 |
| Production | **FAIL** — payments=0, ledger=0; prepaid must stay kill-switched |

> Unit/DB suite green ≠ gate PASS. PASS requires sandbox SQL aggregates + recon evidence.

---

### G4 — No false payment-success state

| Check              | Automated     | Manual | Pass criteria                                                          |
| ------------------ | ------------- | ------ | ---------------------------------------------------------------------- |
| Pending payment UI | E2E abandon   | —      | Pending/failed, **not** success                                        |
| Webhook delay      | E2E           | —      | Success only after API success **and** ledger (or explicit confirming) |
| COD path           | E2E COD ≤K500 | —      | COD never claims MoMo success                                          |

| Layer      | Current                              |
| ---------- | ------------------------------------ |
| Code       | **PARTIAL→PASS UI** (#289 hardening) |
| Staging    | **FAIL** — E2E NOT_RUN               |
| Production | **FAIL** — unproven                  |

---

### G5 — Workflow reliability / retries

| Check                      | Automated                             | Manual                   | Pass criteria             |
| -------------------------- | ------------------------------------- | ------------------------ | ------------------------- |
| Escrow auto-release active | n8n active `release-job`              | Sandbox release tick     | Active + success (MR-W01) |
| Tickets-issue active       | n8n `tickets-issue` (+ event-release) | Paid ticket → one ticket | No double-issue (MR-W02)  |
| Internal ticks auth        | Unauthorized → 401/403                | —                        | Tokens required           |
| Notification dispatch      | Live workflow                         | Sandbox send             | Outbox drains             |

| Layer      | Current                                                             |
| ---------- | ------------------------------------------------------------------- |
| Code       | PASS (JSON in `infra/n8n`)                                          |
| Staging    | FAIL / NOT_RUN                                                      |
| Production | **FAIL** — only notification dispatch + payment reconciliation live |

---

### G6 — Error monitoring and actionable logs

| Check                             | Automated       | Manual     | Pass criteria                  |
| --------------------------------- | --------------- | ---------- | ------------------------------ |
| Sentry projects for 3 apps + API  | Sentry list     | —          | Vergeo5 projects present       |
| Test error ingested               | Trigger per app | Event link | Visible with release tag       |
| Uptime on health                  | Monitor API     | —          | Monitors green                 |
| Payment/webhook errors actionable | Log/Sentry      | —          | Alert on signature/ledger fail |

| Layer      | Current                               |
| ---------- | ------------------------------------- |
| Code       | PARTIAL (SDK present, DSN-gated)      |
| Staging    | FAIL                                  |
| Production | **FAIL** — no Vergeo5 Sentry projects |

---

### G7 — Backups and restore proof

| Check                | Automated                    | Manual             | Pass criteria                |
| -------------------- | ---------------------------- | ------------------ | ---------------------------- |
| Scheduled backup     | n8n **or** host cron listing | OCI object dates   | Dated artifact within RPO    |
| Restore drill        | —                            | Restore to scratch | Success + RPO/RTO documented |
| Pre-migration backup | Checklist before MR-S01      | —                  | Timestamp before migrate     |

| Layer      | Current                    |
| ---------- | -------------------------- |
| Code       | PARTIAL (runbooks/scripts) |
| Staging    | FAIL / NOT_RUN             |
| Production | **FAIL / NOT_AUDITABLE**   |

---

### G8 — Critical test suite and CI gates

| Check                          | Automated                                  | Manual            | Pass criteria           |
| ------------------------------ | ------------------------------------------ | ----------------- | ----------------------- |
| JS lint/typecheck/test         | `pnpm lint && pnpm typecheck && pnpm test` | —                 | Green on release commit |
| API lint/type/tests            | `uv run ruff                               | mypy              | pytest`                 | —   | Green |
| Money/authz failure-path tests | pytest markers                             | —                 | Present + green         |
| secret-scan blocking           | CI without `continue-on-error`             | Branch protection | Required check          |
| Contract/OpenAPI               | CI                                         | —                 | Required on `master`    |

| Layer      | Current                                                                             |
| ---------- | ----------------------------------------------------------------------------------- |
| Code       | PARTIAL — suites green on merges; secret-scan non-blocking                          |
| Staging    | N/A                                                                                 |
| Production | **FAIL** as release gate (CI hardening incomplete; branch protection NOT_AUDITABLE) |

---

### G9 — Deployment / rollback evidence

| Check                     | Automated                 | Manual                 | Pass criteria                                  |
| ------------------------- | ------------------------- | ---------------------- | ---------------------------------------------- |
| Frontend SHAs recorded    | Vercel deployments        | —                      | SHA per app = intended tip                     |
| API image digest recorded | Host/`API_IMAGE_TAG`/GHCR | —                      | Digest ≠ unknown                               |
| DB migrations match tip   | `schema_migrations`       | —                      | Includes `0056` when KYC GO; no silent drift   |
| Rollback drill            | —                         | Prior Vercel + API tag | Executed once; time recorded                   |
| Feature flags             | SQL flags                 | —                      | `public_launch` intentional; Zamtel matches UI |

| Layer      | Current                                                             |
| ---------- | ------------------------------------------------------------------- |
| Code       | N/A                                                                 |
| Staging    | FAIL / NOT_RUN                                                      |
| Production | **FAIL** — tip undeployed; API SHA NOT_AUDITABLE; DB drift CONFLICT |

---

### G12 — KYC integrity (elevated P0)

| Check                           | Automated              | Manual              | Pass criteria                                       |
| ------------------------------- | ---------------------- | ------------------- | --------------------------------------------------- |
| Migration `0056` applied        | `schema_migrations`    | —                   | Applied staging then prod                           |
| Bare `kyc_tier` unlocks nothing | API capability probes  | Admin orphan report | `orphaned_tier=true` ⇒ no wholesale/events/verified |
| Controlled repair               | —                      | Reviewed plan only  | No ad-hoc privilege UPDATE                          |
| Lifecycle E2E                   | API tests + staging UI | —                   | submitted→under_review→approved                     |

| Layer      | Current                                   |
| ---------- | ----------------------------------------- |
| Code       | **PASS** (#291 UI + #293 API/`0056`)      |
| Staging    | **FAIL** — migrate/E2E NOT_RUN            |
| Production | **FAIL** — orphans live; `0056` unapplied |

---

## P1 gates (required before open public positioning)

| ID  | Gate                                    | Evidence                | Code             | Staging | Production |
| --- | --------------------------------------- | ----------------------- | ---------------- | ------- | ---------- |
| G10 | Seller CTA live                         | CUST-01 HTML probe      | PASS fail-closed | FAIL    | FAIL       |
| G11 | Demo catalogue remediated/labelled      | Catalog aggregate + SEO | N/A              | FAIL    | FAIL       |
| G13 | Legal counsel sign-off (DPA/NPS escrow) | Written artifact MR-L01 | N/A              | N/A     | FAIL       |
| G14 | Zamtel collections decision + UI gate   | Flag + checkout methods | PARTIAL          | FAIL    | FAIL       |
| G15 | Admin RBAC decision closed              | ADR / decisions update  | FAIL             | N/A     | FAIL       |
| G16 | Staging UAT (core journeys)             | UAT notes 3–5 testers   | N/A              | FAIL    | N/A        |

---

## P2 gates (hardening; track but do not block invite-beta)

| ID  | Gate                                 | Notes                             |
| --- | ------------------------------------ | --------------------------------- |
| G17 | Vernacular Bemba/Nyanja core flows   | After `0053`; D27 EN-first timing |
| G18 | Lighthouse budgets                   | Perf/SEO/A11y                     |
| G19 | Leaked-password protection on        | Auth advisor                      |
| G20 | Lifecycle n8n (abandoned cart, etc.) | After money path                  |
| G21 | Doc SoT banners on superseded plans  | MR-L02                            |

---

## Staging release gates (exact)

Staging may enable **sandbox prepaid** only when all of the following are PASS:

1. **SG-A** — G3 Code PASS (#274/#294 already) + sandbox project credentials present (F9b sandbox)
2. **SG-B** — G4 staging E2E PASS (false-success ban)
3. **SG-C** — G5 staging: `release-job` + `tickets-issue` active against staging API
4. **SG-D** — G12 staging: `0056` applied; orphan report reviewed; one full KYC lifecycle
5. **SG-E** — G0 staging: RLS probe + role isolation suite against staging DB
6. **SG-F** — G7 staging: backup taken immediately before migration apply
7. **SG-G** — Prepaid kill-switch remains **OFF** on production while staging drills run

**Staging GO ≠ Production GO.**

---

## Production release gates (exact)

### Invite-beta (no real money)

Allowed only if:

- G1 health shells PASS
- G2 localhost check PASS
- Explicit demo disclosure (G11 at least labelled) **or** invite-only with `public_launch=false`
- Prepaid/collections kill-switch **OFF**
- No claim of live GMV / ticket sales

### Real-money beta

All of:

| Must PASS           | Gate                                                        |
| ------------------- | ----------------------------------------------------------- |
| Auth/RLS            | G0 Production                                               |
| Deploy integrity    | G1 + G9 Production                                          |
| Seller CTA policy   | G2 (localhost PASS; CTA policy intentional)                 |
| Money integrity     | G3 + G4 Production (from staging pack promoted)             |
| Workflows           | G5 Production (`release-job` + tickets as needed for scope) |
| Monitoring          | G6 Production                                               |
| Backup/restore      | G7 Production                                               |
| CI hardening        | G8 (secret-scan blocking)                                   |
| KYC                 | G12 Production                                              |
| Legal               | G13                                                         |
| Zamtel              | G14                                                         |
| Admin RBAC decision | G15                                                         |

### Open launch (`public_launch=true`)

Real-money beta GO **plus** G10–G16 PASS.

---

## Release evidence pack (template)

```text
release_id:
git_sha_frontends: {customer, vendor, admin}
api_image_digest:
db_migration_head:          # expect 0056+ when KYC GO
n8n_workflows_active: [list]
sentry_projects: [list]
uptime_monitors: [list]
backup_artifact: {date, location}
restore_drill: {date, result}
sandbox_payments:
  momo_payment_id_redacted:
  card_payment_id_redacted:
  ledger_txn_ids:
  release_recon: {commission_ngwee, net_ngwee, escrow_after}
rls_probe: {path to SQL output}
kyc: {0056_applied, orphan_count, repair_plan_ref}
ci_run_url:
rollback_drill: {date, result}
legal_signoff: {doc ref}
flags: {public_launch, zamtel_collections, prepaid_enabled}
gate_results:
  code: {G0..G9,G12}
  staging: {G0..G9,G12}
  production: {G0..G9,G12}
prs_reconciled: [#274, #289, #290, #291, #293, #294]
```

---

## Go / No-Go

| Decision                           | Condition                                                                                     |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| **NO-GO real money**               | Any of G0–G9 or G12 Production = FAIL / NOT_AUDITABLE                                         |
| **NO-GO public_launch=true**       | Any P0 production gate FAIL **or** G10–G13 FAIL                                               |
| **GO invite-beta (no real money)** | Health G1 partial + G2 localhost PASS + demo disclosure + `public_launch=false` + prepaid OFF |
| **GO staging money drills**        | Staging gates SG-A…SG-G PASS                                                                  |
| **GO real-money beta**             | All P0 production gates PASS + G13 + sandbox pack attached                                    |
| **GO open launch**                 | Real-money beta GO + G10–G16 PASS                                                             |

### Today (2026-07-18)

| Decision                    | Status                         |
| --------------------------- | ------------------------------ |
| Invite-beta (no real money) | Conditional OK with disclosure |
| Staging money drills        | **NO-GO** until SG-* prepared  |
| Real-money beta             | **NO-GO**                      |
| Open launch                 | **NO-GO**                      |

**Do not declare the system production-ready** while payment release accounting, migration rollout, RLS, workflows, monitoring, backup/restore, or rollback evidence is incomplete — even though #274 / #293 / #294 are code-complete on master.
