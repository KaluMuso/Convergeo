# Audit Ledger — Batch 0

**Model:** Independent fields per area — never a single misleading "complete" status.

- **Implementation:** `NOT_AUDITED` | `IMPLEMENTED` | `PARTIAL` | `BROKEN` | `MISSING` | `NOT_APPLICABLE`
- **Deployment:** `UNKNOWN` | `NOT_DEPLOYED` | `DEPLOYMENT_REQUIRED` | `DEPLOYED`
- **Runtime Verification:** `NOT_TESTED` | `VERIFIED` | `FAILED` | `BLOCKED_EXTERNAL`

**Audit commit:** `761733dd` · **Date:** 2026-08-06

---

## Platform core

| ID       | Area                           | Implementation | Deployment          | Runtime Verification | Notes                               |
| -------- | ------------------------------ | -------------- | ------------------- | -------------------- | ----------------------------------- |
| CORE-001 | Monorepo (pnpm + turbo)        | IMPLEMENTED    | DEPLOYED            | VERIFIED             | lint/typecheck/test pass locally    |
| CORE-002 | FastAPI backend                | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Image build in CI; live API unknown |
| CORE-003 | Supabase Postgres schema (Git) | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | 96 migrations; prod tip unknown     |
| CORE-004 | Three Next.js apps             | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | Dated Vercel READY; not re-probed   |
| CORE-005 | RLS on money tables            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | FAILED               | CI matrix may bypass RLS (RG-6)     |

## Authentication & authorization

| ID       | Area                             | Implementation | Deployment          | Runtime Verification | Notes                       |
| -------- | -------------------------------- | -------------- | ------------------- | -------------------- | --------------------------- |
| AUTH-001 | Supabase Auth (OTP/email/Google) | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | config.toml + edge SMS hook |
| AUTH-002 | API JWT + user_roles             | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | Roles from DB not JWT       |
| AUTH-003 | Admin CF Access + IP allowlist   | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | admin middleware            |
| AUTH-004 | Custom access token hook (0051)  | PARTIAL        | NOT_DEPLOYED        | NOT_TESTED           | SQL exists; hook disabled   |

## Commerce path

| ID      | Area                        | Implementation | Deployment          | Runtime Verification | Notes                         |
| ------- | --------------------------- | -------------- | ------------------- | -------------------- | ----------------------------- |
| COM-001 | Canonical product + listing | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                               |
| COM-002 | Cart (guest + auth)         | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                               |
| COM-003 | Checkout session            | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                               |
| COM-004 | Order placement             | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | 0 orders on DB per status doc |
| COM-005 | Stock reservations          | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Sweeper workflow exists       |
| COM-006 | B2B wholesale gating        | PARTIAL        | DEPLOYED            | NOT_TESTED           | Cart read-path gaps           |

## Financial

| ID      | Area                      | Implementation | Deployment          | Runtime Verification | Notes                   |
| ------- | ------------------------- | -------------- | ------------------- | -------------------- | ----------------------- |
| FIN-001 | ngwee integer money model | IMPLEMENTED    | DEPLOYED            | VERIFIED             | Schema + tests          |
| FIN-002 | Ledger double-entry       | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                         |
| FIN-003 | Lenco collections         | IMPLEMENTED    | DEPLOYMENT_REQUIRED | BLOCKED_EXTERNAL     | Kill switch default off |
| FIN-004 | Lenco webhooks            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                         |
| FIN-005 | Escrow release            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | n8n release-job         |
| FIN-006 | Payouts                   | IMPLEMENTED    | DEPLOYMENT_REQUIRED | BLOCKED_EXTERNAL     | PAYOUTS_ENABLED gate    |
| FIN-007 | Refunds                   | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                         |
| FIN-008 | COD ≤K500                 | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                         |
| FIN-009 | Reconciliation            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | n8n workflow            |

## Search & AI

| ID       | Area                      | Implementation | Deployment          | Runtime Verification | Notes                 |
| -------- | ------------------------- | -------------- | ------------------- | -------------------- | --------------------- |
| SRCH-001 | Postgres FTS + trgm + RRF | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                       |
| SRCH-002 | pgvector embeddings       | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | OpenRouter dependency |
| SRCH-003 | Ask Vergeo RAG            | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Quota tables exist    |
| SRCH-004 | Meilisearch               | NOT_APPLICABLE | NOT_DEPLOYED        | NOT_TESTED           | Not in codebase       |

## Automation

| ID       | Area                           | Implementation | Deployment          | Runtime Verification | Notes                   |
| -------- | ------------------------------ | -------------- | ------------------- | -------------------- | ----------------------- |
| AUTO-001 | n8n docker service             | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                         |
| AUTO-002 | Notification dispatch workflow | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                         |
| AUTO-003 | Payment sweeper                | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                         |
| AUTO-004 | DB backup workflow             | IMPLEMENTED    | NOT_DEPLOYED        | NOT_TESTED           | Inactive per status doc |
| AUTO-005 | Embeddings cron                | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                         |

## Verticals

| ID       | Area                                | Implementation | Deployment          | Runtime Verification | Notes                                  |
| -------- | ----------------------------------- | -------------- | ------------------- | -------------------- | -------------------------------------- |
| VERT-001 | Services / RFQ                      | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                                        |
| VERT-002 | Events / ticketing                  | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           |                                        |
| VERT-003 | B2B business buyers                 | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                                        |
| VERT-004 | Social commerce (enquiries/follows) | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           |                                        |
| VERT-005 | Video clips (M17)                   | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Migrations may be unapplied on prod    |
| VERT-006 | WAHA vendor intake (M18)            | IMPLEMENTED    | NOT_DEPLOYED        | NOT_TESTED           | Flag default false; no WAHA in compose |

## Infrastructure & ops

| ID      | Area                       | Implementation | Deployment          | Runtime Verification | Notes                                  |
| ------- | -------------------------- | -------------- | ------------------- | -------------------- | -------------------------------------- |
| OPS-001 | GitHub Actions CI          | IMPLEMENTED    | DEPLOYED            | VERIFIED             | Workflows present                      |
| OPS-002 | API container image GHCR   | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | api-image.yml                          |
| OPS-003 | Production deploy workflow | IMPLEMENTED    | DEPLOYMENT_REQUIRED | NOT_TESTED           | Manual trigger                         |
| OPS-004 | Staging plane              | IMPLEMENTED    | DEPLOYED            | NOT_TESTED           | staging branch workflow                |
| OPS-005 | Sentry                     | PARTIAL        | DEPLOYMENT_REQUIRED | NOT_TESTED           | Projects may be missing                |
| OPS-006 | Restore drill CI           | IMPLEMENTED    | DEPLOYED            | VERIFIED             | Green per status doc; not prod restore |

## Legal / launch gates

| ID      | Area                       | Implementation | Deployment     | Runtime Verification | Notes                    |
| ------- | -------------------------- | -------------- | -------------- | -------------------- | ------------------------ |
| LEG-001 | public_launch flag         | IMPLEMENTED    | DEPLOYED       | VERIFIED             | false per status doc     |
| LEG-002 | F4 counsel escrow sign-off | MISSING        | NOT_APPLICABLE | BLOCKED_EXTERNAL     | Pre real-money gate      |
| LEG-003 | Lenco sandbox money drill  | PARTIAL        | NOT_APPLICABLE | BLOCKED_EXTERNAL     | Scripts exist; F9b creds |

---

_Expand this ledger in future batches with canonical requirement IDs (CAN-_) once MASTER_REQUIREMENTS.md is fully ingested.*
