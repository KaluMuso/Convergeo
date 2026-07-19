> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P09 — Enable leaked-password protection `[OPS]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` X-7; MR-R03; `release-gates.md` G20. **Live:** Supabase security advisor WARNs that `auth_leaked_password_protection` is **disabled**. Cheap auth-hygiene close.
**Type:** `[OPS]` — dashboard toggle + evidence.

## 2. Objective & scope
Enable HaveIBeenPwned leaked-password protection in Supabase Auth and clear the advisor WARN.
**Non-goals:** other auth policy changes.

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/auth-hardening.md`
**Guardrail: dashboard + evidence only.**

## 4. Implementation spec
- Enable leaked-password protection in Supabase Auth settings; re-run `get_advisors(security)` and confirm the WARN is gone.

## 10. Tests / verification (RUN before reporting)
- Advisor no longer reports `auth_leaked_password_protection`.
- A known-breached password is rejected at signup/password-change (probe with a throwaway account).

## 11. Acceptance criteria / DoD (G20)
- [ ] Protection enabled; advisor WARN cleared.
- [ ] Breached-password rejection confirmed.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P09 — Enable leaked-password protection
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste advisor before/after + rejection probe · **EXCERPTS:** none · **QUESTIONS:** …
