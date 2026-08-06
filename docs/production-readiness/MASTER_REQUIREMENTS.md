# Master Requirements — Programme Scaffold

**Status:** Batch 0 — **registry not found in repository**

The operator referenced a **CONVERGEO PRE-CURSOR CANONICAL REQUIREMENTS REGISTRY** (225 source requirements → 34 canonical requirements, traceability matrix, decision register, launch scopes). That document was **not present** in the Git tree at audit commit `761733dd`.

This file is a **scaffold**. Ingest the external registry verbatim in a follow-up session without changing canonical definitions.

---

## Interim authority (until registry ingest)

| Source                                   | Role                                           |
| ---------------------------------------- | ---------------------------------------------- |
| `docs/plan/00-decisions.md`              | Locked product decisions D1–D37                |
| `CLAUDE.md`                              | Non-negotiable engineering conventions         |
| `docs/production-readiness/DECISIONS.md` | DEC-001…004 repository resolution              |
| External Canonical Requirements Registry | **Target** business behaviour (pending ingest) |

---

## Canonical requirement index (placeholder)

Map each `CAN-*` ID from the external registry here. Below: **engineering anchors** derived from locked decisions — not a substitute for the 34 canonical requirements.

| Canonical ID (pending) | Title (from D-record)                | Implementation anchor                        |
| ---------------------- | ------------------------------------ | -------------------------------------------- |
| CAN-STACK-001          | FastAPI + Supabase backend           | `services/api/`                              |
| CAN-STACK-002          | Three-app Next.js frontend           | `apps/customer                               | vendor | admin` |
| CAN-PAY-001            | Lenco-only payments                  | `app/services/payments/lenco/`               |
| CAN-PAY-002            | Integer ngwee money                  | `0006_money.sql`, `NgweeInt`                 |
| CAN-PAY-003            | Escrow + ledger-of-record            | `ledger/`, `escrow/`                         |
| CAN-PAY-004            | Payment kill switches                | `payments/gate.py`                           |
| CAN-AUTH-001           | RLS on every table                   | `supabase/migrations/*`                      |
| CAN-AUTH-002           | Role-scoped API                      | `app/core/auth.py`                           |
| CAN-SRCH-001           | Postgres hybrid search               | `0009_search.sql`, `search_rrf`              |
| CAN-SRCH-002           | Ask Vergeo RAG                       | `app/services/ask/`                          |
| CAN-CAT-001            | Canonical products + vendor listings | `0003_catalog.sql`                           |
| CAN-COM-001            | Cart → checkout → order spine        | `cart.py`, `checkout.py`, `orders_create.py` |
| CAN-VEND-001           | KYC tiers + vendor lifecycle         | `kyc/`, `0056_kyc_integrity.sql`             |
| CAN-EVT-001            | Events + ticketing                   | `0004`, events routers                       |
| CAN-B2B-001            | Verified business wholesale gate     | `0038_business_buyers.sql`, D28/D36          |
| CAN-SOC-001            | Bounded social commerce              | `0082`–`0083`, D37                           |
| CAN-OPS-001            | WhatsApp → SMS → email outbox        | `notifications/`, n8n dispatch               |
| CAN-OPS-002            | n8n automation plane                 | `infra/n8n/`                                 |
| CAN-LAUNCH-001         | public_launch feature flag           | `0030_beta_invites.sql`                      |

---

## Ingest checklist (next documentation batch)

- [ ] Add all 34 `CAN-*` definitions from external registry (verbatim scope, no prose drift)
- [ ] Map 225 source requirement IDs in REQUIREMENT_TRACEABILITY.md
- [ ] Link each CAN-* to AUDIT_LEDGER rows with implementation/deployment/runtime fields
- [ ] Record launch scope tags (retail / events / B2B / social) per canonical requirement

---

_Do not mark requirements IMPLEMENTED based on this scaffold alone — verify against code and live environment per AUDIT_LEDGER.md._
