# Audit Ledger — Batch 0 + 0.5

**Model:** Independent fields per area — never a single misleading "complete" status.

- **Implementation:** `NOT_AUDITED` | `IMPLEMENTED` | `PARTIAL` | `BROKEN` | `MISSING` | `NOT_APPLICABLE`
- **Deployment:** `UNKNOWN` | `NOT_DEPLOYED` | `DEPLOYMENT_REQUIRED` | `DEPLOYED`
- **Runtime Verification:** `NOT_TESTED` | `VERIFIED` | `FAILED` | `BLOCKED_EXTERNAL`

**Batch 0.5 commit:** `fcf2b191` · **Batch 1A commit:** `e7555b8d` · **Date:** 2026-08-06

Canonical IDs below updated **only where Batch 0.5 obtained evidence**. All others remain `NOT_AUDITED` at canonical level.

---

## Canonical requirements — Batch 0.5 evidence

| Canonical ID     | Implementation | Deployment          | Runtime Verification | Batch 0.5 evidence summary                                                               |
| ---------------- | -------------- | ------------------- | -------------------- | ---------------------------------------------------------------------------------------- |
| **CAN-CAT-003**  | PARTIAL        | DEPLOYED            | NOT_TESTED           | B2B 404 on add (`fetch_listing`); cart read does not re-filter wholesale — **PARTIAL**   |
| **CAN-CAT-005**  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Code + reservation sweeper n8n ACTIVE; prod DB at 0071 (pre-reservation migrations band) |
| **CAN-DISC-001** | IMPLEMENTED    | DEPLOYED            | VERIFIED             | `/readyz?checks=search` ok on production API                                             |
| **CAN-DISC-004** | IMPLEMENTED    | DEPLOYMENT_REQUIRED | VERIFIED             | Embeddings cron n8n ACTIVE; search RPC ok live                                           |
| **CAN-FIN-001**  | IMPLEMENTED    | DEPLOYED            | VERIFIED             | Schema at prod 0071 includes ngwee bigint; code gates present                            |
| **CAN-FIN-002**  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | BLOCKED_EXTERNAL     | Lenco code present; `ledger_transactions`=0; OCI gates UNKNOWN                           |
| **CAN-FIN-004**  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Ledger schema in Git; `release-job` n8n not confirmed active                             |
| **CAN-FIN-005**  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Code + sweeper workflows; auto-release workflow import unknown                           |
| **CAN-OPS-001**  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | PARTIAL              | RLS in Git through 0095; prod at 0071; RLS CI trustworthy on master                      |
| **CAN-OPS-004**  | IMPLEMENTED    | PARTIAL             | PARTIAL              | 7/9 n8n workflows ACTIVE; 16/25 Git JSONs unconfirmed                                    |
| **CAN-OPS-005**  | IMPLEMENTED    | UNKNOWN             | BLOCKED_EXTERNAL     | n8n backup INACTIVE; Supabase PITR not verified                                          |
| **CAN-OPS-006**  | IMPLEMENTED    | DEPLOYED            | PARTIAL              | CI green; prod FE/API/DB triangle mismatch (BLK-202)                                     |
| **CAN-SOC-001**  | IMPLEMENTED    | DEPLOYED            | FAILED               | Contact Vendor on PDP; prod API `/enquiries` → 404 (Batch 1A)                            |
| **CAN-ORD-002**  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | `0086` cart RLS in Git; **not applied on prod** (at 0071)                                |
| **CAN-ORD-003**  | PARTIAL        | DEPLOYED            | NOT_TESTED           | Checkout re-derives prices; cart read path gap (BLK-101)                                 |
| **CAN-UX-001**   | IMPLEMENTED    | DEPLOYED            | VERIFIED             | Customer PWA on Vercel; `buildId=fcf2b191`                                               |

---

## Platform core (engineering ledger — Batch 0)

| ID       | Area                           | Implementation | Deployment          | Runtime Verification | Notes                                    |
| -------- | ------------------------------ | -------------- | ------------------- | -------------------- | ---------------------------------------- |
| CORE-001 | Monorepo (pnpm + turbo)        | IMPLEMENTED    | DEPLOYED            | VERIFIED             | lint/typecheck/test pass locally         |
| CORE-002 | FastAPI backend                | IMPLEMENTED    | DEPLOYED            | VERIFIED             | `/healthz` 200; SHA behind master        |
| CORE-003 | Supabase Postgres schema (Git) | IMPLEMENTED    | DEPLOYMENT_REQUIRED | VERIFIED             | Prod tip `0071`; staging `0079`          |
| CORE-004 | Three Next.js apps             | IMPLEMENTED    | DEPLOYED            | PARTIAL              | Customer SHA match; vendor/admin unknown |
| CORE-005 | RLS on money tables            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | VERIFIED             | RLS CI trustworthy (Batch 0.5)           |

## Authentication & authorization

| ID       | Area                             | Implementation | Deployment   | Runtime Verification | Notes                       |
| -------- | -------------------------------- | -------------- | ------------ | -------------------- | --------------------------- |
| AUTH-001 | Supabase Auth (OTP/email/Google) | IMPLEMENTED    | DEPLOYED     | NOT_TESTED           | config.toml + edge SMS hook |
| AUTH-002 | API JWT + user_roles             | IMPLEMENTED    | DEPLOYED     | NOT_TESTED           | Roles from DB not JWT       |
| AUTH-003 | Admin CF Access + IP allowlist   | IMPLEMENTED    | DEPLOYED     | BLOCKED_EXTERNAL     | CF Access redirect on probe |
| AUTH-004 | Custom access token hook (0051)  | PARTIAL        | NOT_DEPLOYED | NOT_TESTED           | SQL exists; hook disabled   |

## Commerce path

| ID      | Area                        | Implementation | Deployment          | Runtime Verification | Notes                      |
| ------- | --------------------------- | -------------- | ------------------- | -------------------- | -------------------------- |
| COM-001 | Canonical product + listing | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                            |
| COM-002 | Cart (guest + auth)         | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                            |
| COM-003 | Checkout session            | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | Re-derivation at checkout  |
| COM-004 | Order placement             | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | 0 orders on DB             |
| COM-005 | Stock reservations          | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Sweeper ACTIVE; schema gap |
| COM-006 | B2B wholesale gating        | PARTIAL        | DEPLOYED            | NOT_TESTED           | Cart read-path gap BLK-101 |

## Financial

| ID      | Area                      | Implementation | Deployment          | Runtime Verification | Notes                     |
| ------- | ------------------------- | -------------- | ------------------- | -------------------- | ------------------------- |
| FIN-001 | ngwee integer money model | IMPLEMENTED    | DEPLOYED            | VERIFIED             | Schema + tests            |
| FIN-002 | Ledger double-entry       | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | 0 ledger rows prod        |
| FIN-003 | Lenco collections         | IMPLEMENTED    | DEPLOYMENT_REQUIRED | BLOCKED_EXTERNAL     | Kill switch; OCI unknown  |
| FIN-004 | Lenco webhooks            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                           |
| FIN-005 | Escrow release            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | release-job unconfirmed   |
| FIN-006 | Payouts                   | IMPLEMENTED    | DEPLOYMENT_REQUIRED | BLOCKED_EXTERNAL     | PAYOUTS_ENABLED unknown   |
| FIN-007 | Refunds                   | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                           |
| FIN-008 | COD ≤K500                 | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                           |
| FIN-009 | Reconciliation            | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | n8n reconciliation ACTIVE |

## Search & AI

| ID       | Area                      | Implementation | Deployment   | Runtime Verification | Notes               |
| -------- | ------------------------- | -------------- | ------------ | -------------------- | ------------------- |
| SRCH-001 | Postgres FTS + trgm + RRF | IMPLEMENTED    | DEPLOYED     | VERIFIED             | Live search RPC ok  |
| SRCH-002 | pgvector embeddings       | IMPLEMENTED    | DEPLOYED     | VERIFIED             | Embedding check ok  |
| SRCH-003 | Ask Vergeo RAG            | IMPLEMENTED    | DEPLOYED     | NOT_TESTED           | Quota tables exist  |
| SRCH-004 | Meilisearch               | NOT_APPLICABLE | NOT_DEPLOYED | NOT_TESTED           | DEC-004 NOT_PRESENT |

## Automation

| ID       | Area                           | Implementation | Deployment | Runtime Verification | Notes             |
| -------- | ------------------------------ | -------------- | ---------- | -------------------- | ----------------- |
| AUTO-001 | n8n docker service             | IMPLEMENTED    | DEPLOYED   | VERIFIED             | MCP reachable     |
| AUTO-002 | Notification dispatch workflow | IMPLEMENTED    | DEPLOYED   | VERIFIED             | ACTIVE            |
| AUTO-003 | Payment sweeper                | IMPLEMENTED    | DEPLOYED   | VERIFIED             | ACTIVE            |
| AUTO-004 | DB backup workflow             | IMPLEMENTED    | DEPLOYED   | FAILED               | IMPORTED_INACTIVE |
| AUTO-005 | Embeddings cron                | IMPLEMENTED    | DEPLOYED   | VERIFIED             | ACTIVE            |

## Infrastructure & ops

| ID      | Area                       | Implementation | Deployment | Runtime Verification | Notes                         |
| ------- | -------------------------- | -------------- | ---------- | -------------------- | ----------------------------- |
| OPS-001 | GitHub Actions CI          | IMPLEMENTED    | DEPLOYED   | VERIFIED             | RLS matrix blocking on master |
| OPS-002 | API container image GHCR   | IMPLEMENTED    | DEPLOYED   | VERIFIED             | Prod image behind master      |
| OPS-003 | Production deploy workflow | IMPLEMENTED    | DEPLOYED   | NOT_TESTED           | Manual trigger                |
| OPS-004 | Staging plane              | IMPLEMENTED    | DEPLOYED   | NOT_TESTED           | Staging DB at 0079            |
| OPS-005 | Sentry                     | PARTIAL        | DEPLOYED   | NOT_TESTED           | Projects may be missing       |
| OPS-006 | Restore drill CI           | IMPLEMENTED    | DEPLOYED   | VERIFIED             | Green; prod restore unproven  |

## Legal / launch gates

| ID      | Area                       | Implementation | Deployment     | Runtime Verification | Notes                 |
| ------- | -------------------------- | -------------- | -------------- | -------------------- | --------------------- |
| LEG-001 | public_launch flag         | IMPLEMENTED    | DEPLOYED       | VERIFIED             | false prod + staging  |
| LEG-002 | F4 counsel escrow sign-off | MISSING        | NOT_APPLICABLE | BLOCKED_EXTERNAL     | Pre real-money gate   |
| LEG-003 | Lenco sandbox money drill  | PARTIAL        | NOT_APPLICABLE | BLOCKED_EXTERNAL     | Prerequisites PARTIAL |

---

_Expand canonical rows in future batches only with direct evidence. See [MASTER_REQUIREMENTS.md](./MASTER_REQUIREMENTS.md)._
