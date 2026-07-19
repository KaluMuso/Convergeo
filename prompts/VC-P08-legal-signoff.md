> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P08 — Legal counsel sign-off (DPA / NPS-Act escrow) `[OPS]`

## 1. Context
**Wave 0 engage → Wave 3 artifact.** Source: `01-audit-findings.md` X-4; MR-L01; **FD-08 (NB-5)**; `release-gates.md` G13. **Live:** legal posture is NOT_AUDITABLE — no written artifact. Engineering **cannot** mark legal PASS from code; real-money beta stays **NO-GO** until a written Zambian-counsel posture on the DPA + NPS-Act-2026 escrow model (Lenco-held funds; platform never pools) exists. Ties to founder gate F4.
**Type:** `[OPS]` — no code substitute; the founder engages counsel and records the artifact.

## 2. Objective & scope
Obtain and record written counsel posture, so `release-gates.md` `legal_signoff` can be filled before any live prepaid enablement.
**Non-goals:** enabling real money (stays sandbox-only until this + all P0 gates PASS).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/legal-signoff.md` (reference/summary + doc pointer — **not** the privileged advice verbatim)
**Guardrail: record a reference to the counsel artifact; do not paste privileged/PII content into the repo.**

## 4. Implementation spec
- Engage Zambian counsel; obtain written posture covering: Zambia DPA (data handling, export/delete, retention), NPS-Act-2026 escrow legality of aggregator-held funds, refund/dispute obligations, and any consumer-protection (CCPC) alignment for the two-lane returns.
- Record the artifact reference (date, author, scope, verdict) in the evidence doc and in the `release-gates.md` release-evidence `legal_signoff` field.

## 9. Security
- No privileged content or PII committed; store the artifact out-of-repo, reference only.

## 10. Tests / verification
- N/A (written artifact). Confirm the `release-gates.md` `legal_signoff` field references it.

## 11. Acceptance criteria / DoD (G13)
- [ ] Written counsel posture obtained (never a founder self-waiver as a PASS).
- [ ] Evidence doc references it; `release-gates.md` updated.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P08 — Legal counsel sign-off
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** N/A · **EXCERPTS:** none · **QUESTIONS:** …
