> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P03 — Restore drill `[OPS]`

## 1. Context
**Wave 4.** Source: `01-audit-findings.md` X-2; MR-O04; `release-gates.md` G7. **Depends on VD-P04** (a real dated dump exists). **Live:** restore is NOT_AUDITABLE — a backup with no proven restore is not a backup. `docs/ops/runbook-disaster-recovery.md` + `scripts/*restore*` exist for the procedure.
**Type:** `[OPS]` — Cursor writes the evidence doc; the **founder** restores into a scratch target.

## 2. Objective & scope
Restore VD-P04's dump into a scratch DB, verify integrity, and document RPO/RTO.
**Non-goals:** production restore; authoring the backup workflow (VD-P04).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/restore-drill.md`
**Guardrail: restore to a SCRATCH target only, never prod.**

## 4. Implementation spec
- `pg_restore` the latest dump into a scratch DB; verify row counts / key invariants (ledger balances, invoice sequence continuity) match the source snapshot.
- Time the restore; record RPO (dump cadence) + RTO (restore duration) against the DR runbook target.

## 10. Tests / verification (RUN before reporting)
- Restore completes; `load/invariant-check.py` (or key SELECTs) passes on the restored data.
- RPO/RTO recorded within the DR target (or waiver noted).

## 11. Acceptance criteria / DoD (G7)
- [ ] Scratch restore succeeds; integrity verified.
- [ ] RPO/RTO documented against the runbook.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P03 — Restore drill
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste restore + invariant output + timings · **EXCERPTS:** none · **QUESTIONS:** …
