> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P03 — Enable the role hook (`0051`) `[OPS]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` §5; MR-S02; **FD-03 (B-2)**; `release-gates.md` G0. **Depends on VA-P02** (`0051` applied). **Live:** the custom-access-token hook function is absent and, even once migrated, is **dormant until enabled in the Supabase Auth dashboard** → JWT roles can lag `user_roles`, so isolation tests aren't authoritative. Middleware still leans on `app_metadata.roles`. **Requires B-2 = "apply 0051 + hook" (default).**
**Type:** `[OPS]` — Cursor writes the runbook + isolation-test invocation; the **founder** enables the Auth hook.

## 2. Objective & scope
Enable the Auth custom-access-token hook so JWT roles match `user_roles`, and prove role isolation.
**Non-goals:** FORCE RLS (VC-P02); admin RBAC model (VC-P07). If B-2 chose the manual-grant exception instead, this pebble becomes a written, time-boxed exception doc (no hook).

## 3. Files (create ONLY these)
- `docs/production-readiness/2026-07-19/vision-audit/evidence/role-hook.md`
**Guardrail: no code; dashboard + evidence only.**

## 4. Implementation spec
- Enable the `custom_access_token_hook` in Supabase Auth (dashboard/config) against the applied `0051` function.
- Mint fresh sessions for a customer, vendor, admin tester; confirm JWT `roles` claim == their `user_roles` rows.
- Run the isolation suites; confirm middleware no longer depends on stale `app_metadata`.

## 9. Security
- Admin still requires Cloudflare Access **and** the `admin` role (JWT alone never authorises admin — `getRoles` remains authoritative server-side). No secrets in evidence.

## 10. Tests / verification (RUN before reporting)
- `uv run pytest services/api/tests/rls services/api/tests/test_authz_matrix.py -q` green.
- JWT-role vs `user_roles` parity shown for all three personas (redacted).

## 11. Acceptance criteria / DoD (G0)
- [ ] Auth hook enabled; JWT roles == `user_roles`.
- [ ] Customer/vendor/admin isolation suites green.
- [ ] (Or, if B-2 exception:) signed time-boxed manual-grant doc attached.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P03 — Enable the role hook (`0051`)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste isolation/authz suite output + role-parity proof (redacted) · **EXCERPTS:** none · **QUESTIONS:** …
