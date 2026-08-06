# Implementation & Audit Queue

**Updated:** 2026-08-06 (Batch 0 complete)

---

## Completed

| Batch       | Title                                    | Outcome                                                                   |
| ----------- | ---------------------------------------- | ------------------------------------------------------------------------- |
| **Batch 0** | Repository truth & architecture baseline | ARCHITECTURE_BASELINE.md + programme docs; DEC-001…004 resolved from code |

---

## Recommended next batch (do not execute until approved)

### Batch 1 — Live environment verification & migration truth

**Rationale:** Git proves a large, mature codebase, but **deployment and runtime state are the largest unknowns**. Status doc (2026-08-01) already documents prod/staging migration skew, unknown API health, partial n8n import, and RLS CI false-green (RG-6). No feature work should proceed until this batch closes.

**Scope (read-only / evidence only):**

1. **Supabase migration tip** — compare `supabase_migrations.schema_migrations` on production and staging vs Git filenames (through `0095` and timestamp migration).
2. **API live probe** — `GET https://api.vergeo5.com/healthz`, `/readyz?checks=search`, `/fingerprint` (no secrets).
3. **Vercel production SHA** — customer/vendor/admin `/{locale}/health` `buildId` vs `git rev-parse master`.
4. **n8n inventory** — list active workflows on production host vs `infra/n8n/*.json` registry.
5. **Feature flags & money gates** — read `feature_flags` table and document `PAYMENTS_ENABLED` / `PAYOUTS_ENABLED` **names only** from runtime config (not values).
6. **RLS CI validity** — confirm whether RG-6 fix is merged; if not, record as BLOCKER.
7. **Ingest Canonical Requirements Registry** into MASTER_REQUIREMENTS.md + full traceability matrix.

**Deliverables:** Update AUDIT_LEDGER deployment/runtime columns; BLOCKERS.md; dated evidence file under `docs/production-readiness/2026-08-06/`.

**Explicitly out of scope:** Payment activation, payouts, schema changes, demo seeding.

---

## Deferred batches (outline only)

| Batch   | Title                                       | Depends on                        |
| ------- | ------------------------------------------- | --------------------------------- |
| Batch 2 | Canonical requirement audit (CAN-* vs code) | Batch 1 + registry ingest         |
| Batch 3 | Financial path end-to-end (sandbox drill)   | Batch 1 + F9b Lenco sandbox creds |
| Batch 4 | AuthZ & RLS penetration audit               | Batch 1 + RG-6 fix merged         |
| Batch 5 | n8n fleet activation & error-handler wiring | Batch 1 n8n inventory             |

---

_One batch at a time. No parallel feature implementation during audit programme._
