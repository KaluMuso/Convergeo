# Implementation & Audit Queue

**Updated:** 2026-08-06 (Contact Vendor fail-closed compat fix)

---

## Completed

| Batch         | Title                                                | Outcome                                                                                   |
| ------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Batch 0**   | Repository truth & architecture baseline             | ARCHITECTURE_BASELINE.md; DEC-001…004                                                     |
| **Batch 0.5** | Runtime truth, migration truth & requirements ingest | Live probes; registry ingest                                                              |
| **Batch 1A**  | Production schema compatibility & catch-up plan      | [production-migration-catchup-plan.md](./2026-08-06/production-migration-catchup-plan.md) |
| **Compat**    | Contact Vendor fail-closed UI gate (BLK-202)         | PDP probes `GET /enquiries`; hides CTA when API unavailable; tests added                  |

---

## Recommended next action (do not execute until approved)

### Execute Wave B (0080–0081, 0089–0090) on **staging** + validate

**Rationale:** Staging already proves Wave A (0072–0079). Wave B is **low risk on production data** (0 vendor locations) but **unvalidated** on any environment. Applying Wave B on staging exercises branch-stock backfill, geo index, and reservation-location FKs before production Wave A/B. This is read-only planning's natural successor — not production apply yet.

**Scope:**

1. Apply migrations `0080`, `0081`, `0089`, `0090` on staging only.
2. Run `uv run pytest tests/rls -q` against staging-connected harness OR post-apply `supabase db reset` locally.
3. Smoke: checkout pickup paths, stock sweeper, `/search/nearby`.
4. Document results in `docs/production-readiness/2026-08-06/`.

**Out of scope:** Production apply; API deploy; feature flag activation; payments.

**Alternative (if staging apply blocked):** ~~C. Fix application compatibility — gate Contact Vendor UI until Wave C + API deploy (BLK-202).~~ **Done** — compat gate shipped; full CAN-SOC-001 still requires Wave C + API deploy.

---

## Deferred

| Item                             | Depends on                                     |
| -------------------------------- | ---------------------------------------------- |
| Production Wave A (0072–0079)    | Backup confirmation (EXT-004); operator window |
| Production Wave C+               | Wave A/B; API deploy coordination              |
| Batch 1B — Cart/B2B audit        | Catch-up plan accepted                         |
| Fix BLK-201 migration replay gap | Engineering session                            |

---

_One bounded action at a time._
