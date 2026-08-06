# Implementation & Audit Queue

**Updated:** 2026-08-06 (Batch 1A.1 complete)

---

## Completed

| Batch          | Title                                                | Outcome                                                                                   |
| -------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Batch 0**    | Repository truth & architecture baseline             | ARCHITECTURE_BASELINE.md; DEC-001…004                                                     |
| **Batch 0.5**  | Runtime truth, migration truth & requirements ingest | Live probes; registry ingest                                                              |
| **Batch 1A**   | Production schema compatibility & catch-up plan      | [production-migration-catchup-plan.md](./2026-08-06/production-migration-catchup-plan.md) |
| **Batch 1A.1** | Migration executability & verification repair        | Executable-wave reclassification; BLK-201 fixed; 0086 grant test                          |

---

## Recommended next action (do not execute until approved)

### **B.** Full staging schema catch-up — `0079` → `0095` + timestamp RLS remediation (one contiguous `db push`)

**Rationale:** Batch 1A.1 proved Supabase CLI applies **all** pending migrations in a single contiguous, filename-sorted pass. Batch 1A's non-contiguous "Wave B" (`0080`, `0081`, `0089`, `0090` skipping `0082`–`0088`) is **not executable** via supported tooling. Staging rehearsal is simpler and safer as one controlled contiguous apply, then RLS matrix + smoke tests.

**Scope:**

1. Operator runs `supabase link` + `supabase db push --dry-run --linked` against staging (`iyasmrmbcrvlfxpzescb`) to confirm pending list.
2. Apply with `supabase db push --linked` (single operation — 17 migrations: `0080`…`0095`, then `20260802153539_rls_policy_contract_remediation`).
3. Run `uv run pytest tests/rls -q` against staging-connected harness or post-apply local `supabase db reset`.
4. Smoke: `/healthz`, `/readyz?checks=search`; confirm feature flags remain OFF.
5. Document results in `docs/production-readiness/2026-08-06/`.

**Out of scope:** Production apply; API deploy; feature flag activation; payments; `migration repair` history manipulation.

**Alternative (if staging apply blocked):** **C.** Gate Contact Vendor UI until API deploy (BLK-202) without DB change.

---

## Deferred

| Item                               | Depends on                                        |
| ---------------------------------- | ------------------------------------------------- |
| Production catch-up (0071→0095+TS) | Staging full catch-up validated; backup (EXT-004) |
| Batch 1B — Cart/B2B audit          | Staging at Git schema tip                         |
| API deploy to `master`             | Staging validation + coordinated window           |

---

_One bounded action at a time._
