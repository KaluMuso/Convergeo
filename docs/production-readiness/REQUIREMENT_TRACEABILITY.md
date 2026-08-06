# Requirement Traceability — Scaffold

**Status:** Batch 0 — awaiting **Canonical Requirements Registry** ingest

---

## Traceability model

```
Source document (SR-*) → Canonical requirement (CAN-*) → Code / migration / test evidence → AUDIT_LEDGER status
```

**Rules:**

- Repository code proves **implementation exists**, not **deployed** or **verified**.
- Migrations in Git prove **schema intent**, not **applied on production**.
- Tests passing locally prove **developer harness**, not **production behaviour**.

---

## Source document index (historical — from programme context)

| Source bucket              | Repository location                                  | Notes                             |
| -------------------------- | ---------------------------------------------------- | --------------------------------- |
| Locked decisions D1–D37    | `docs/plan/00-decisions.md`                          | Product truth for planning        |
| Engineering conventions    | `CLAUDE.md`, `AGENTS.md`                             | Stack locked D18–D24              |
| Lenco API contracts        | `docs/ops/lenco/lenco-api-distilled.md`              | Payment integration               |
| Consolidated conflicts     | `docs/production-readiness/2026-07-18/consolidated/` | Doc vs live reconciliation        |
| Mountains / pebbles        | `docs/plan/01-mountains.md`, `docs/plan/02-pebbles/` | Implementation history            |
| External registry (225 SR) | **Not in repo**                                      | Operator-supplied; pending ingest |

---

## DEC-001…004 traceability (Batch 0 resolved)

| Decision         | Canonical theme            | Repository evidence             | Classification          |
| ---------------- | -------------------------- | ------------------------------- | ----------------------- |
| DEC-001 Backend  | CAN-STACK-001              | `pyproject.toml`, `app/main.py` | CONFIRMED_BY_REPOSITORY |
| DEC-002 AuthZ    | CAN-AUTH-001, CAN-AUTH-002 | migrations RLS + `auth.py`      | CONFIRMED_BY_REPOSITORY |
| DEC-003 Payments | CAN-PAY-001                | `payments/lenco/`, no DPO       | CONFIRMED_BY_REPOSITORY |
| DEC-004 Search   | CAN-SRCH-001               | `0009_search.sql`, `search_rrf` | CONFIRMED_BY_REPOSITORY |

---

## Example traceability row (template)

| SR-ID  | CAN-ID      | Requirement summary           | Code evidence                               | Test evidence                 | Ledger ID |
| ------ | ----------- | ----------------------------- | ------------------------------------------- | ----------------------------- | --------- |
| SR-??? | CAN-PAY-002 | Money stored as integer ngwee | `NgweeInt`, `0006_money.sql` bigint columns | `test_money_*`, `test_ledger` | FIN-001   |
| SR-??? | CAN-PAY-003 | Escrow release on fulfilment  | `escrow/release.py`                         | `test_escrow_*`               | FIN-005   |

---

## Superseded documentation conflicts (do not implement)

From `source-conflicts-and-decisions.md`:

| Conflict ID    | Stale doc claim | Repository truth           |
| -------------- | --------------- | -------------------------- |
| C-STACK-BE     | Django + DRF    | FastAPI                    |
| C-STACK-SEARCH | Meilisearch     | Postgres FTS/trgm/pgvector |
| C-PAY-PROVIDER | DPO / DPO+Lenco | Lenco only                 |
| C-STACK-ASYNC  | Celery + Redis  | n8n + outbox               |

---

_Populate SR-_ → CAN-* matrix when external registry is committed to the repository.*
