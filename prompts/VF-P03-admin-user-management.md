> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P03 — Admin user/role management per B-4 `[CODE/DOC]`

## 1. Context
**Wave 5.** Source: `01-audit-findings.md` BG-2; MR-A01; **FD-02 (B-4)**. **Depends on VC-P07** (the B-4 decision + admin-access doc). **Live:** admin is vendor/business/KYC-centric; there is **no generic user/role management UI**, and `user_roles` is service-role-only. Whether this is a build or a doc depends entirely on B-4.
**Type:** `[CODE/DOC]` per B-4.

## 2. Objective & scope
- **Default (single-admin, B-4a):** ship the operable manual path — extend `docs/ops/admin-access.md` with the exact guarded grant/revoke procedure + audit expectations (no CRUD UI).
- **Additive roles (B-4b):** build the grant/revoke admin UI over the additive-role schema from VC-P07, with an audit trail on every change.
**Non-goals:** inventing roles absent a B-4b ADR; vendor staff RBAC (FD-10 = OUT).

## 3. Files (create/edit ONLY these)
- Default: `docs/ops/admin-access.md` (extend)
- Additive: `apps/admin/app/[locale]/users/**` (+ its `_components`) and the admin API route module — **exact list from the VC-P07 ADR**; coordinate ownership so it does not overlap VC-P07's files
**Guardrail: match the recorded B-4 decision; no fabricated role UI without backend + ADR.**

## 4. Implementation spec
- Default: precise, copy-pasteable grant/revoke steps via the guarded admin path; how audit is recorded; least-privilege guidance.
- Additive: list/grant/revoke UI reading `user_roles`; every mutation writes `audit_log` via `AdminAuditedRoute`; authz-matrix rows added.

## 10. Tests (RUN before reporting)
- Default: none (docs) — runbook is copy-pasteable.
- Additive: `uv run pytest services/api/tests/test_authz_matrix.py -q` green; UI role change writes an audit row (test).

## 11. Acceptance criteria / DoD (BG-2)
- [ ] Matches B-4; audit trail on every role change.
- [ ] No fabricated UI without backend.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P03 — Admin user/role management per B-4
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** (additive) authz + audit tests / (default) none · **EXCERPTS:** the authz change if additive · **QUESTIONS:** the B-4 answer
