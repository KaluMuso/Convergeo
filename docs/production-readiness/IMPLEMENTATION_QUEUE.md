# Implementation & Audit Queue

**Updated:** 2026-08-06 (Batch 1A.2 staging schema catch-up complete)

---

## Completed

| Batch          | Title                                                | Outcome                                                                                   |
| -------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Batch 0**    | Repository truth & architecture baseline             | ARCHITECTURE_BASELINE.md; DEC-001…004                                                     |
| **Batch 0.5**  | Runtime truth, migration truth & requirements ingest | Live probes; registry ingest                                                              |
| **Batch 1A**   | Production schema compatibility & catch-up plan      | [production-migration-catchup-plan.md](./2026-08-06/production-migration-catchup-plan.md) |
| **Compat**     | Contact Vendor fail-closed UI gate (BLK-202)         | PDP probes `GET /enquiries`; hides CTA when API unavailable; tests added                  |
| **Batch 1A.2** | Staging schema catch-up 0079→0095+TS                 | [staging-schema-catchup-evidence.md](./2026-08-06/staging-schema-catchup-evidence.md)     |

---

## Recommended next action

### **A.** Deploy `master` API to staging + compatibility regression

**Rationale:** Staging DB is at Git schema tip. Deployed staging API (`161b58a3`) lacks `/enquiries`, `/rfq`, and other post-0079 routes. Schema-ahead/API-behind triangle must be closed on staging before production catch-up.

**Scope:**

1. Deploy API image tagged `ea80af3d` (or current `master`) to staging OCI only.
2. Smoke: `/enquiries` (401/403 expected for anon GET), `/rfq`, cart write via API, branch stock paths.
3. Confirm Contact Vendor CTA becomes visible when API probe passes.
4. Run `uv run pytest tests/rls -q` against staging-connected harness if credentials available.

**Out of scope:** Production DB/API deploy; payments; feature flag activation.

---

## Deferred

| Item                               | Depends on                                           |
| ---------------------------------- | ---------------------------------------------------- |
| Production catch-up (0071→0095+TS) | Staging API+DB validation complete; backup (EXT-004) |
| Batch 1B — Cart/B2B audit          | Staging at Git schema tip + API deployed             |

---

_One bounded action at a time._
