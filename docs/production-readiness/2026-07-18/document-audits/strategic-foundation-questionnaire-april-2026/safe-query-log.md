# Safe Query Log — Strategic Foundation Questionnaire audit

**Audit date:** 2026-07-18 · **Mode:** READ-ONLY · **Policy:** no writes/migrations/seeding/deploys/workflow-activation/payment actions. No PII, secrets, payment references, or raw row dumps recorded — **counts and outcomes only**.

This audit is of a *strategy document* with no named records, so no record-lookup queries were required. Probes below establish the **live-platform state** the document's claims are reconciled against. Two evidence tiers are distinguished:

- **(this session)** — probes I ran now, 2026-07-18.
- **(foundation, same-day)** — evidence from `../../foundation/*` captured ~12:48–16:02 UTC the same day (~3 h before this session). Cited where live re-probe was blocked.

---

## 1. Probes executed THIS SESSION

| # | Purpose | Target (tool / API / table) | Filter / args | Result (counts/outcome only) | Outcome |
| --- | --- | --- | --- | --- | --- |
| Q1 | Confirm live n8n automation coverage (Applause#7, RT#5/#9, Q66) | n8n MCP `search_workflows` | limit 100, no filter | **2** workflows, both active: "notification dispatch", "payment reconciliation crons" | OK — confirms only 2 live; escrow/ticket/backup workflows absent |
| Q2 | Confirm demo media in Cloudinary (Applause#5, Q16, demo-catalogue) | Cloudinary MCP `search-assets` | `expression: public_id:demo/*`, `max_results:0` | `total_count: **60**` (aggregate only; no asset list retrieved) | OK — demo media live; 60 assets under `demo/` |
| Q3 | Confirm 3-app topology + prod liveness (Applause#1, Q10/Q12) | Vercel MCP `list_deployments` | `projectId=…F7LswgTP` (customer), `teamId=…ACbQW705` | Customer app READY; latest prod target SHA `0b88723` (PR #277); prior prod `8cc1fa0` (PR #271); authors incl. "Claude" + "Cursor Agent" | OK — customer app live & advancing; multi-tool authorship visible |
| Q4 | Cross-reference locked decisions (interpret conflicts) | local file `docs/plan/00-decisions.md` | grep stack/payments/escrow/lang/COD/VAT | D2,D3,D4,D5,D11,D12,D13,D14,D15,D16,D18,D20,D21,D24,D25,D26,D27 matched | OK — rank-4 intent context only |
| Q5 | Attempted fresh public HTTP re-probe (F3, seller CTA) | `curl` → `www.vergeo5.com`, `api.vergeo5.com` | `/en/health`, `/healthz`, `/readyz`, `/catalog/listings?limit=1` | **BLOCKED** — proxy `403 CONNECT` (org egress policy) | Not auditable live; used foundation same-day evidence |
| Q6 | Attempted fresh Supabase read-only SQL | Supabase MCP (`mcp.supabase.com`) | list_tables / aggregates | **BLOCKED** — server unauthenticated + proxy `403 CONNECT` | Not auditable live; used foundation same-day evidence |

**Note on Cloudinary vs DB counts:** Cloudinary `demo/`=60 assets while `listing_images` with `cloudinary_public_id LIKE 'demo/%'`=134 (foundation). Not a conflict — multiple listing-image rows reference the same Cloudinary asset (image reuse across listings). Recorded for transparency; no raw IDs retrieved.

---

## 2. Evidence relied upon from the FOUNDATION snapshot (same-day, not re-run here)

These aggregates/facts are cited from `../../foundation/{production-evidence,database-schema-inventory,access-and-rls-inventory,critical-risk-register}.md` (SQL run under read-only operator access at ~12:48–13:00 UTC). Re-running was blocked (Q5/Q6 above); the snapshot is ~3 h old, same audit date.

| Evidence used | Value | Foundation source | Used for facts |
| --- | --- | --- | --- |
| Applied migrations | ≤0050 + odd `20260717100303` (0052); **0051/0053/0054/0055 not applied** | production-evidence §4 | F047, F079, b-table (schema drift) |
| Catalogue | 3 demo vendors, 134 listings, 150 products, 74 categories | production-evidence §5 | F054, F089, F110 |
| Demo images | 134 `listing_images` `cloudinary_public_id LIKE 'demo/%'`; catalog API `total=134` | production-evidence §5 | F069, F110 |
| Money ops | `payments`/`ledger_transactions`/`payouts`/`webhook_events`/`tickets` = 0 | production-evidence §5 | F044, F048, F071–F074, F092, F111 |
| Feature flags | `paid_tiers`, `abandoned_cart`, `wallet`, `zamtel_collections`, `public_launch` = all **false** | production-evidence §5 | F024, F040, F054, F060, F078, F100 |
| Config tables | `commission_rates`=9, `platform_config`=16, `delivery_zones`=3, `merch_slots`=1 | database-schema-inventory §2 | F061, F077, F081, F090 |
| Empty operational tables | `kyc_records`/`reviews`/`disputes`/`returns`/`invoices`/`business_buyers`/`vendor_locations`/`jobs`/`job_quotes` = 0; `services`=1 | database-schema-inventory §2 | F042, F083, F086, F087, F091, F093, F096 |
| Search projection | `search_documents`=288, `embedding_jobs`=288; pgvector + pg_trgm | database-schema-inventory §2 | F068 |
| n8n registry vs live | ~18 registered vs 2 active; escrow/tickets/backup absent | production-evidence §6 | F016, F044, F092, c-table |
| Seller CTA | `/sell` CTAs disabled; no localhost leak; env likely unset | production-evidence §8 | F031, c/d-tables |
| Observability | No Vergeo5 Sentry projects; analytics tables 0 rows | production-evidence §7 | F049, F099 |
| Auth | Supabase phone OTP/email/Google; `send-sms-otp` edge fn | access-and-rls-inventory §2 | F080 |
| RLS posture | RLS+FORCE on business tables; service-role-only tables (audit_log, outbox, user_roles, rate_counters, stock_reservations); 0051 role-hook not applied | access-and-rls-inventory §3 | RBAC/security context (E-list, L-list) |

---

## 3. Explicitly NOT performed (safety)

- No `INSERT`/`UPDATE`/`DELETE`/DDL/migration/seed.
- No sandbox or live payment initiated (Q19–Q22 remain code-only / unproven).
- No n8n workflow activated/executed (read-only listing only).
- No Cloudinary asset list, no raw `public_id` values, no vendor/customer PII, no payment references, no COD cap value, no commission bps, no env secret values retrieved.
- No RLS bypass or elevated-credential use to inflate coverage.
