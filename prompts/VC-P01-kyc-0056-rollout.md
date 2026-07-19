> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P01 — Apply `0056` to production + KYC orphan repair `[OPS]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` §3/§4/§5; MR-D02/MR-B11/MR-S11; `release-gates.md` G12; **NB-14 (FD-12)**. **Depends on VA-P02** (0056 staging-verified). **Live:** `kyc_records = 0`, but **3 vendors carry a `kyc_tier` with no auditable record (orphans)**; PR #293 freezes privileges without an approved record but **does not auto-heal**. `0056` is unapplied on prod.
**Type:** `[OPS]` — Cursor writes the runbook + evidence; the **founder** applies `0056` to prod (after VA-P02 PASS + VA-P00 backup) and performs guarded manual repair.

## 2. Objective & scope
Apply `0056` to production and resolve the 3 orphaned tiers by **manual, guarded** repair.
**Non-goals:** any auto-upgrade/backfill (forbidden by #293/FD-12); staging apply (VA-P02); role hook (VC-P03).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/kyc-0056-rollout.md`
**Guardrail: NEVER `UPDATE vendors SET kyc_tier`; NEVER auto-create `kyc_records`. Repair only via guarded admin paths.**

## 4. Implementation spec (runbook)
- Order per `impl/kyc-integrity-report.md`: API understands statuses (VA-P03 pinned) → apply `0056` to prod → clients.
- Run `/admin/kyc/orphaned-tiers` (`internal`/admin) → list the 3 orphans.
- Per orphan, either: create a proper KYC submission → guarded `start-review` → `approve` with evidence, **or** clear the tier via the guarded admin path. Ticket each; named ops owner (FD-12).
- Confirm privileged capabilities (wholesale/events/verified badge) stay **frozen** without an approved record.

## 9. Security
- Guarded transitions + `audit_log` only; no raw SQL on trust tables; PII redacted in evidence.

## 10. Tests / verification (RUN before reporting)
- `0056` in prod `schema_migrations`; `guard_kyc_record_integrity` present.
- Orphan report count → 0 after repair (or each remaining orphan ticketed).
- A bare-tier vendor cannot unlock a privileged capability (probe).

## 11. Acceptance criteria / DoD (G12)
- [ ] `0056` applied to prod after staging PASS + backup.
- [ ] 3 orphans manually resolved/ticketed; no auto-upgrade.
- [ ] Privileges require an approved `kyc_records` row.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P01 — Apply `0056` to production + KYC orphan repair
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste migration head + orphan-report before/after (redacted) · **EXCERPTS:** none · **QUESTIONS:** …
