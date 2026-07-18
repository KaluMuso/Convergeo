# Safe Query / Probe Log — Convergeo 60-Day Development Roadmap audit

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY. No writes, migrations, seeds, deploys, workflow activation, or payment actions were performed.
**Redaction:** No secrets, PII, addresses, phones, emails, payment references, or raw row dumps are recorded below — counts and outcomes only.

---

## 1. Local repository probes (rank 3, executed this session)

| # | Purpose | Target | Filter / command shape | Result (counts only) | Outcome |
| --- | --- | --- | --- | --- | --- |
| L1 | Confirm repo HEAD | git | `git rev-parse HEAD` | HEAD `0b88723` (PR #277) | OK — repo advanced past foundation's `8cc1fa0` (PR #271) |
| L2 | Backend framework | `services/api` | grep `django` vs `fastapi` (file counts) | django **0** files, fastapi **181** files; pyproject `vergeo5-api` | Confirms FastAPI (F003) |
| L3 | Payment provider | `services/api` | grep `dpo` vs `lenco` | DPO **0**, Lenco **70** | Confirms Lenco (F005) |
| L4 | Search engine | `services/api`, `supabase/migrations` | grep `meilisearch` vs FTS/vector | meili **0**; FTS/pgvector migration refs **5** | Confirms PG-native search (F006) |
| L5 | Async/cache tier | `services/api` | grep `celery`, `redis` | celery **0**, redis **0** | Confirms no Celery/Redis (F007/F008) |
| L6 | Email provider | `services/api` | grep `sendgrid|mailgun` vs `resend` | sendgrid/mailgun **0**, resend **6** | Confirms Resend (F009) |
| L7 | n8n workflow files | `infra/n8n/*.json` | list | **18** JSON files | Registry inventory (F042) |
| L8 | Admin role enum | `supabase/migrations` | grep role CHECK + `superadmin`/`moderator` | CHECK = `('customer','vendor','admin')`; superadmin **0** | Confirms no superadmin/moderator (F033) |
| L9 | Zamtel gating | `services/api` | grep `zamtel`, `LENCO_ENABLE_ZAMTEL`, `zamtel_collections` | **16** refs; flag + env present | Confirms Zamtel gated (F026) |
| L10 | Pickup/QR + tickets + checkout groups + reviews | `supabase/migrations` | grep table/migration names | `0017_order_pickup_tokens`, ticket migrations, `checkout_groups`, `0007_trust_ops` present | Confirms schema (F028/F031/F032) |
| L11 | Staging + context file | repo root / `.github/workflows` | ls | `deploy-staging.yml` present (stub); `AI_CONTEXT.md` **absent**, `CLAUDE.md` present | Confirms F011/F045 |
| L12 | Migration count | `supabase/migrations` | `ls *.sql | wc -l` | **55** (`0001`–`0055`) | Matches foundation repo tip |

---

## 2. Live n8n probes (rank 1, executed this session — read-only)

| # | Purpose | Target/API | Filter | Result (counts only) | Outcome |
| --- | --- | --- | --- | --- | --- |
| N1 | Enumerate live workflows | `Vergeo5_N8N` MCP `search_workflows` | limit 200, sort name:asc | **2** workflows, both `active:true` ("notification dispatch", "payment reconciliation crons") | VERIFIED — escrow-release/tickets/onboarding/backup workflows absent (F025/F042/F049) |

> No workflow was executed, published, activated, or modified. `search_workflows` is a read/list operation only.

---

## 3. Live HTTP probes (attempted, BLOCKED this session)

| # | Purpose | Target | Filter | Result | Outcome |
| --- | --- | --- | --- | --- | --- |
| H1 | Customer health | `www.vergeo5.com/en/health` | GET | **403 CONNECT** (agent egress policy) | NOT_AUDITABLE this session; foundation VERIFIED `200 {"status":"ok"}` |
| H2 | API health/ready | `api.vergeo5.com/healthz`,`/readyz` | GET | **403 CONNECT** | NOT_AUDITABLE this session; foundation VERIFIED `200` |
| H3 | OpenAPI + catalog total | `api.vergeo5.com/openapi.json`, `/catalog/listings?limit=1` | GET | **403 CONNECT** | NOT_AUDITABLE this session; foundation: title "Vergeo5 API" v0.1.0, catalog `total=134` |

> Per `/root/.ccr/README.md`, 403/CONNECT egress denials must be reported, not retried or routed around. Not retried.

---

## 4. Supabase live SQL (attempted, UNAVAILABLE this session)

| # | Purpose | Target | Intended filter | Result | Outcome |
| --- | --- | --- | --- | --- | --- |
| S1 | Re-verify aggregates (vendors/listings/orders/payments/ledger/tickets, feature_flags, role enum, RLS policy counts) | Supabase project `dpadrlxukcjbewpqympu` via MCP `execute_sql` (`BEGIN READ ONLY; SELECT count(*) …`) | scoped `count(*)` aggregates + `pg_policies`/`pg_class` metadata (no PII) | **Unavailable** — Supabase MCP requires OAuth (non-interactive session) and `mcp.supabase.com` egress-blocked | NOT_AUDITABLE this session; all DB counts cite the **foundation baseline** (`../foundation/database-schema-inventory.md`, `production-evidence.md`), prior-session live SQL, same audit date |

> The read-only aggregate/metadata query pack that *would* be run (from `../foundation/executive-baseline.md` §"Supabase SQL") is intentionally **not** reproduced against live here because the connection is unavailable — no elevated credential was used to force completion (contract §5).

---

## 5. PDF extraction (source handling)

| # | Purpose | Target | Method | Result | Outcome |
| --- | --- | --- | --- | --- | --- |
| P1 | Read source document | uploaded PDF (6.9 MB) | `pdfinfo` | **13 pages**, wkhtmltopdf→Ghostscript, image-based | Harness "71 pages" notice corrected to 13 |
| P2 | Text-layer extract | PDF | `pdftotext -layout` | ~307 chars (3 code strings only) | Confirms image-based; visual render required |
| P3 | Full content read | PDF pages 1–13 | poppler `pdftoppm` + Read tool (visual) | All phases/days/deliverables/gates transcribed | Source captured in `source-document.md` |

> No tooling was pointed at production; PDF processing is local. `apt-get install poppler-utils` (and an attempted `pip install pypdf`, which failed on a broken `cryptography`/`_cffi_backend`) were the only installs — local, no production impact.

---

## Compliance checklist

- [x] Read-only only; zero mutations to DB, workflows, deployments, payments.
- [x] No secrets, PII, payment references, addresses, phones, emails, or raw rows recorded.
- [x] Egress/auth denials reported, not bypassed; no elevated credentials used to force completeness.
- [x] "Not found" claims backed by scoped grep/list/aggregate; "Not auditable" used where access was insufficient.
- [x] No records created; gaps routed to `remediation-backlog.md`.
