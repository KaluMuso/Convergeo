> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P05 — Rollback drill `[OPS]`

## 1. Context
**Wave 4.** Source: `01-audit-findings.md` §1; `release-gates.md` G9. **Depends on VA-P01/VA-P03** (known frontend SHAs + pinned API image). `infra/ROLLBACK.md` + `docs/ops/runbook-disaster-recovery.md` document the procedure; a **timed dry-run** is missing.
**Type:** `[OPS]` — Cursor writes the evidence doc; the **founder** runs the dry-run.

## 2. Objective & scope
Prove a timed rollback of both the frontend (Vercel prior deployment) and the API (previous image tag).
**Non-goals:** DB restore (VE-P03); any destructive prod change beyond the dry-run.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/rollback-drill.md`
**Guardrail: evidence only; roll forward again immediately after the dry-run.**

## 4. Implementation spec
- Vercel: promote a prior production deployment id, confirm the alias serves it, then roll forward. Record time.
- API: `infra/redeploy-api.sh rollback <prev-digest/tag>` on the host, confirm health, then roll forward. Record time.
- Note the escrow-reconciliation caveat (coordinate M08 recon around any DB restore — not exercised here).

## 10. Tests / verification (RUN before reporting)
- Frontend + API each demonstrably served a prior version, then returned to tip; health 200 throughout.
- Times recorded against the RTO target.

## 11. Acceptance criteria / DoD (G9)
- [ ] Timed frontend + API rollback dry-run recorded per `infra/ROLLBACK.md`.
- [ ] Rolled forward; health green.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P05 — Rollback drill
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste rollback/roll-forward timings + health · **EXCERPTS:** none · **QUESTIONS:** …
