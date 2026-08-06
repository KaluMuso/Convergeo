# Production Readiness Programme

**Latest audit:** Batch 1A.1 — 2026-08-06  
**Repository:** [KaluMuso/Convergeo](https://github.com/KaluMuso/Convergeo) (product brand: **Vergeo5**)  
**Current `master` SHA:** `475824c6559915f8cac5bd0ed1bf31c19acdedc1`  
**Batch 1A.1 branch:** `cursor/batch1a1-migration-executability-repair-eedc`

This directory is the **authoritative programme context** for production-readiness work.

## Authority hierarchy

1. **Repository code** — current implementation truth
2. **Database / deployment / runtime evidence** — current operational truth (when verified)
3. **Canonical Requirements Registry** — target business behaviour ([MASTER_REQUIREMENTS.md](./MASTER_REQUIREMENTS.md))
4. **Decision Register** — architecture decisions separating repo truth vs product target ([DECISIONS.md](./DECISIONS.md))
5. **Historical source documents** — traceability only ([REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md))

## Programme documents

| File                                                                                                 | Purpose                                                    |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [ARCHITECTURE_BASELINE.md](./ARCHITECTURE_BASELINE.md)                                               | Current-state architecture (Batch 0 ground truth)          |
| [MASTER_REQUIREMENTS.md](./MASTER_REQUIREMENTS.md)                                                   | **34 canonical requirements** (ingested Batch 0.5)         |
| [REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md)                                         | **223-row** source → canonical matrix (+ REG-001 gap note) |
| [DECISIONS.md](./DECISIONS.md)                                                                       | DEC-001…004 + REG-001; repo vs product distinction         |
| [AUDIT_LEDGER.md](./AUDIT_LEDGER.md)                                                                 | Implementation / deployment / runtime status               |
| [IMPLEMENTATION_QUEUE.md](./IMPLEMENTATION_QUEUE.md)                                                 | Ordered audit and implementation batches                   |
| [BLOCKERS.md](./BLOCKERS.md)                                                                         | Evidence-backed launch blockers                            |
| [2026-08-06/runtime-truth-evidence.md](./2026-08-06/runtime-truth-evidence.md)                       | Batch 0.5 live probe & migration evidence pack             |
| [2026-08-06/production-migration-catchup-plan.md](./2026-08-06/production-migration-catchup-plan.md) | Batch 1A migration waves & deploy sequencing               |

## Batch status

| Batch    | Status               | Summary                                                                         |
| -------- | -------------------- | ------------------------------------------------------------------------------- |
| **0**    | Complete             | Repository architecture baseline @ `761733dd`                                   |
| **0.5**  | Complete             | Runtime/migration truth; registry ingest; live probes                           |
| **1A**   | Complete             | Migration catch-up plan; compatibility matrix; waves A–G (logical groups)       |
| **1A.1** | Complete             | Executable-wave repair; BLK-201 fix; staging dry-run semantics; 0086 grant test |
| **1B**   | **Recommended next** | Full staging catch-up 0079→0095+TS (one `db push`) — operator approval required |

## Historical evidence packs

Dated snapshots under `docs/production-readiness/20YY-MM-DD/` remain **point-in-time** evidence. Re-verify before launch decisions. See `docs/plan/00-status.md` for the live gate summary.

## Aggregate posture

**NO_GO** — production DB 24+ migrations behind Git; zero money exercised; B2B cart read-path PARTIAL. Details: [BLOCKERS.md](./BLOCKERS.md).
