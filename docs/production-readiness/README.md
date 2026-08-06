# Production Readiness Programme — Batch 0

**Audit date:** 2026-08-06  
**Repository:** [KaluMuso/Convergeo](https://github.com/KaluMuso/Convergeo) (product brand: **Vergeo5**)  
**Audited commit:** `761733dd982a9400a0e0c7427046ecbaf0aac11c` on `master`  
**Audit branch:** `cursor/batch0-architecture-baseline-9b44`  
**Working tree:** clean at audit start

This directory is the **authoritative programme context** for production-readiness work. Batch 0 established **current implementation truth** from repository code — not target behaviour from strategy documents.

## Authority hierarchy

1. **Repository code** — current implementation truth
2. **Database / deployment / runtime evidence** — current operational truth (when verified)
3. **Canonical Requirements Registry** — target business behaviour (external; not yet ingested into this repo)
4. **Decision Register** — proposed / unresolved architecture decisions
5. **Historical source documents** — traceability and strategy only

## Programme documents

| File                                                         | Purpose                                                           |
| ------------------------------------------------------------ | ----------------------------------------------------------------- |
| [ARCHITECTURE_BASELINE.md](./ARCHITECTURE_BASELINE.md)       | Current-state architecture (Batch 0 ground truth)                 |
| [MASTER_REQUIREMENTS.md](./MASTER_REQUIREMENTS.md)           | Canonical requirement definitions (pending full registry ingest)  |
| [REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md) | Source → canonical mapping scaffold                               |
| [DECISIONS.md](./DECISIONS.md)                               | Decision Register including DEC-001…DEC-004 resolution            |
| [AUDIT_LEDGER.md](./AUDIT_LEDGER.md)                         | Independent implementation / deployment / runtime status per area |
| [IMPLEMENTATION_QUEUE.md](./IMPLEMENTATION_QUEUE.md)         | Ordered audit and implementation batches                          |
| [BLOCKERS.md](./BLOCKERS.md)                                 | Evidence-backed launch and audit blockers                         |

## Historical evidence packs

Dated snapshots under `docs/production-readiness/20YY-MM-DD/` remain **point-in-time** evidence. Do not treat them as current state without re-verification. See `docs/plan/00-status.md` for the live gate summary (also dated; re-verify before launch decisions).

## Batch 0 scope

- **In scope:** repository identity, topology, backend, database (Git), auth, commerce/financial/search/automation architecture, infra evidence, observability, test baseline, DEC-001…004 resolution.
- **Out of scope:** feature implementation, refactors, payment activation, production deploys, demo seeding, Batch 1 execution.

## Next recommended batch

See [IMPLEMENTATION_QUEUE.md](./IMPLEMENTATION_QUEUE.md) — **Batch 1: Live environment verification & migration truth**.
