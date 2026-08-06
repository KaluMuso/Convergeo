# Implementation & Audit Queue

**Updated:** 2026-08-06 (Batch 0.5 complete)

---

## Completed

| Batch         | Title                                                | Outcome                                                                                                           |
| ------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Batch 0**   | Repository truth & architecture baseline             | ARCHITECTURE_BASELINE.md; DEC-001…004 resolved from code                                                          |
| **Batch 0.5** | Runtime truth, migration truth & requirements ingest | Live probes; migration tips; registry ingest; [runtime-truth-evidence.md](./2026-08-06/runtime-truth-evidence.md) |

---

## Recommended next batch (do not execute until approved)

### Batch 1 — Cart, checkout derivation & B2B visibility integrity

**Rationale:** Batch 0.5 established the highest **actionable code-level security gap** without requiring production migration apply or money activation: **CAN-CAT-003** and **CAN-ORD-003** are **PARTIAL** — wholesale eligibility is enforced at cart add and checkout session creation, but **not** on `GET /cart` read. This violates the B2B invisibility invariant for stale cart rows and is directly traceable in code (BLK-101). Migration skew (BLK-001/002) blocks production verification of `0086` cart RLS (CAN-ORD-002) but does not block a read-only code audit and fix design.

**Scope (audit-first; implementation only if trivial doc fix is insufficient):**

1. Trace full cart → checkout → order path for wholesale/retail visibility and price re-derivation.
2. Map gaps to CAN-CAT-003, CAN-ORD-002, CAN-ORD-003 acceptance criteria.
3. Propose minimal fix (cart read filter vs checkout-only) with test cases.
4. Cross-check listing visibility changes post-add (retail → wholesale-only scenario).
5. Document interaction with D36 business-buyer gate.

**Canonical IDs:** CAN-CAT-003, CAN-ORD-002, CAN-ORD-003

**Deliverables:** Updated AUDIT_LEDGER rows; fix PR or implementation-queue entry; no production migration apply.

**Explicitly out of scope:** Lenco money drills, production migration apply, n8n activation, payout enablement.

**Why not migration batch first:** Migration apply is **ops execution** (BLK-001/002) requiring founder-approved maintenance window — not a bounded audit. Cart/B2B gap is a confirmed invariant violation in deployed code paths today.

---

## Deferred batches (outline)

| Batch   | Title                                                  | Depends on                      |
| ------- | ------------------------------------------------------ | ------------------------------- |
| Batch 2 | Staging migration apply + schema verification          | Founder ops window; BLK-001/002 |
| Batch 3 | Money representation & webhook safety (sandbox drill)  | Batch 2 + F9b creds             |
| Batch 4 | AuthZ & RLS penetration (live DB at current tip)       | Batch 2                         |
| Batch 5 | n8n fleet completion (release-job, order-jobs, backup) | Batch 2                         |
| Batch 6 | Backup/recovery proof                                  | EXT-004 dashboard access        |

---

_One batch at a time. No parallel feature implementation during audit programme._
