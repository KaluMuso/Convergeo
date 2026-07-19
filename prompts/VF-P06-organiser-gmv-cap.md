> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P06 — Organiser Tier-1 GMV fraud cap `[CODE]`

## 1. Context
**Wave 5 (P0 for paid events specifically).** Source: `01-audit-findings.md` §5 / BG-3; MR-B04; events BL-004. **Live:** a Tier-1 organiser GMV cap (~K20k) — a fraud/liability control for unverified-tier event organisers — is **not evidenced** in code. Paid events must not let a Tier-1 organiser accumulate escrow beyond the cap.
**Type:** `[CODE]` (MONEY-adjacent → heightened review).

## 2. Objective & scope
Enforce the Tier-1 organiser GMV cap before accepting further paid-ticket escrow; reject/hold over-cap with an audit entry.
**Non-goals:** ticket issuance/release workflows (VD-P02); non-event commerce.

## 3. Files (edit/create ONLY these)
- `services/api/app/services/events/*` (the escrow-eligibility / organiser-gate path)
- `services/api/tests/test_event_*.py` (add the cap failure-path test)
**Guardrail: integer ngwee only; cap value in `platform_config`/`commission_rates`-style config, not hardcoded.**

## 4. Implementation spec
- On a paid-ticket order for a **Tier-1** organiser, compute cumulative organiser GMV; if the order would exceed the configured cap, **reject (422) or hold** and write an `audit_log` entry — never silently accept.
- Cap is config-driven (per KYC tier); Tier-2/verified organisers are unaffected. Fail-closed if the cap config is missing.

## 9. Security / correctness
- Integer ngwee; guarded transition + audit; no float. Failure-path test required (over-cap rejected).

## 10. Tests (RUN before reporting)
- Over-cap Tier-1 order → rejected/held + audited; under-cap → accepted.
- Tier-2 organiser unaffected. `uv run pytest services/api/tests/test_event_*.py -q` green.

## 11. Acceptance criteria / DoD (MR-B04)
- [ ] Tier-1 organiser cannot exceed the configured GMV cap; over-cap rejected + audited.
- [ ] Cap config-driven; fail-closed on missing config; failure-path test present.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P06 — Organiser Tier-1 GMV fraud cap
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the cap failure-path + accept tests · **EXCERPTS:** the cap-enforcement code (money) · **QUESTIONS:** the exact cap value if unspecified
