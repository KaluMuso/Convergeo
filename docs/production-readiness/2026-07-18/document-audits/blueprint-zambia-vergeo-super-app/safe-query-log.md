# Safe Query Log — blueprint-zambia-vergeo-super-app

**Audit timestamp (UTC):** 2026-07-18 ~15:59–16:10  
**Mode:** READ-ONLY · No writes, migrations, seeds, deploys, workflow activation, or payment actions  
**Privacy:** Aggregates / metadata only — no PII, secrets, payment references, or row dumps

---

## HTTP / API probes

| ID  | Purpose                      | Target                                                  | Filters / notes           | Row-count / result                                                                                                 | Outcome |
| --- | ---------------------------- | ------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------- |
| H01 | Customer health              | `GET https://www.vergeo5.com/en/health`                 | —                         | `{"status":"ok","app":"customer"}`                                                                                 | OK      |
| H02 | API health                   | `GET https://api.vergeo5.com/healthz`                   | —                         | `{"status":"ok"}`                                                                                                  | OK      |
| H03 | API ready                    | `GET https://api.vergeo5.com/readyz`                    | —                         | `{"status":"ok"}`                                                                                                  | OK      |
| H04 | OpenAPI inventory            | `GET https://api.vergeo5.com/openapi.json`              | Path keyword tallies only | title Vergeo5 API v0.1.0; 228 paths; rfq=0 name matches; jobs/quotes/tickets/events/lenco present; yango=0; city=0 | OK      |
| H05 | Catalog size                 | `GET /catalog/listings?limit=1` then `limit=3`          | Public                    | `total=134`                                                                                                        | OK      |
| H06 | Services public list         | `GET /services?limit=5`                                 | Public                    | `total=1` (demo repair service)                                                                                    | OK      |
| H07 | Events public list           | `GET /events?limit=5`                                   | Public                    | `total=0`                                                                                                          | OK      |
| H08 | Search smoke                 | `GET /search?q={maize,chitenge,solar,iphone,laptop}`    | Public                    | totals 0/8/6/0/5; `degraded=true`                                                                                  | OK      |
| H09 | Customer UI keyword presence | `GET /en`, `/en/sell`, `/en/services`, `/en/events`, …  | HTML keyword scan only    | escrow/MoMo/Held by present; sell `unavailable` count=12; no localhost leak                                        | OK      |
| H10 | PWA manifest / SW            | `GET /manifest.webmanifest`, `/sw.js`, `/serwist/sw.js` | —                         | manifest 200; SW paths 404                                                                                         | OK      |
| H11 | Vendor gate                  | `GET vendor.vergeo5.com/en/health`                      | —                         | 307 → login                                                                                                        | OK      |
| H12 | Admin gate                   | `GET admin.vergeo5.com/en/health`                       | —                         | 302 Cloudflare Access                                                                                              | OK      |
| H13 | Admin vercel.app             | `GET convergeo-admin.vercel.app/en/health`              | —                         | 403 Access required                                                                                                | OK      |
| H14 | API docs framework           | `GET /docs`                                             | Framework string scan     | FastAPI/Swagger markers present; Django absent                                                                     | OK      |

---

## Supabase SQL (read-only aggregates)

Project: `dpadrlxukcjbewpqympu` · via Supabase MCP `execute_sql`

| ID  | Purpose                            | Target                                     | Filters                                  | Row-count / aggregate                                                                                                                                                        | Outcome       |
| --- | ---------------------------------- | ------------------------------------------ | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- |
| S01 | Core inventory                     | multi-`count(*)`                           | none (aggregates)                        | vendors 3; listings 134; products 150; orders 0; payments 0; ledger_txns 0; tickets 0; events 0; services 1; jobs 0; job_quotes 0; kyc_records 0; payouts 0; demo_images 134 | OK            |
| S02 | Commission matrix                  | `commission_rates`                         | `LIMIT 20`                               | 9 rows; `event_tickets=500` bps; `free_events=0`                                                                                                                             | OK            |
| S03 | Feature flags                      | `feature_flags`                            | all                                      | 5 flags, all `enabled=false` incl. `public_launch`, `paid_tiers`, `zamtel_collections`                                                                                       | OK            |
| S04 | Vendor identity (non-PII)          | `vendors`                                  | slug/status/archetype/kyc_tier           | 3 active; all `kyc_tier=2`; archetype null                                                                                                                                   | OK            |
| S05 | Escrow/delivery config             | `platform_config`                          | keys in release/COD/delivery/reservation | `release_after_delivered_hours=48`; shipped days 7; COD cap 50000 ngwee; free delivery 20000; reservation 15m                                                                | OK            |
| S06 | Config key inventory               | `platform_config`                          | keys only                                | 16 keys (no values dumped beyond S05 set)                                                                                                                                    | OK            |
| S07 | Attempted multi-statement (failed) | `commission_rates` wrong column `category` | —                                        | ERROR 42703 — corrected to S02                                                                                                                                               | Failed safely |

No `BEGIN` writes; no DDL; no PII columns selected (no phones/emails/addresses/payment refs).

---

## n8n MCP (read-only)

| ID  | Purpose                                 | Target                       | Filters | Result                                                                            | Outcome            |
| --- | --------------------------------------- | ---------------------------- | ------- | --------------------------------------------------------------------------------- | ------------------ |
| N01 | List workflows                          | `search_workflows` limit 100 | —       | **2** workflows, both active: notification dispatch; payment reconciliation crons | OK                 |
| N02 | Escrow release / tickets-issue presence | name scan of N01             | —       | **Absent**                                                                        | OK (gap confirmed) |

No `publish_workflow`, `execute_workflow`, or credential secret reads.

---

## Foundation cross-reference (not re-executed as writes)

Reused prior foundation evidence (`docs/production-readiness/2026-07-18/foundation/*`) for Vercel SHAs, migration drift, and RLS posture. Fresh probes above reconfirmed health, catalogue totals, n8n count, and money-table emptiness.

---

## Explicitly not queried

- Customer PII, KYC document contents, raw addresses
- Payment/ledger reference strings
- Vercel/Supabase/Lenco secret **values**
- Mutating Auth OTP sends to real numbers
- Admin UI behind Cloudflare Access (challenge only observed)
