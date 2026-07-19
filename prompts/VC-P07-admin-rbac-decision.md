> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P07 — Admin RBAC per B-4 `[DOC or CODE]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` §4; MR-A02; **FD-02 (B-4)**; `release-gates.md` G15. **Live:** single `admin` CHECK behind Cloudflare Access; roadmap mentions superadmin/moderator (unbuilt). Agents are **forbidden from inventing roles** without B-4. **Default (B-4): single `admin` + Access** → this is a docs pebble.
**Type:** `[DOC or CODE]` per the B-4 answer.

## 2. Objective & scope
Make the admin authz model explicit and operable per the decision.
**Non-goals:** the admin user-management UI build (that is VF-P03, and only if B-4 chose additive roles).

## 3. Files (create/edit ONLY these)
- **Default (single-admin):** `docs/ops/admin-access.md` — runbook for grant/revoke of the `admin` role via a guarded path + Cloudflare Access; no new roles.
- **If B-4 = additive roles:** an additive migration (CHECK/RLS), grant/revoke API + admin UI, and `test_authz_matrix.py` rows — file list to be specified in that ADR (this pebble then becomes CODE and coordinates ownership with VF-P03).
**Guardrail: do NOT create superadmin/moderator without a recorded B-4 = additive-roles ADR.**

## 4. Implementation spec
- Default: document exactly how the founder grants/revokes `admin` (guarded, audited), how Access gates the origin, and why v1 supersedes the roadmap multi-tier model.
- Additive path: define roles, RLS, grant/revoke endpoints, and expand the authz matrix; no fabricated UI without backend.

## 10. Tests (RUN before reporting)
- Default: none (docs) — confirm the runbook is copy-pasteable, not prose.
- Additive: `uv run pytest services/api/tests/test_authz_matrix.py -q` green with new roles.

## 11. Acceptance criteria / DoD (G15)
- [ ] Matches the recorded B-4 decision.
- [ ] No fabricated role UI; authz model consistent with the DB CHECK.
- [ ] (Additive only) authz matrix green.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P07 — Admin RBAC per B-4
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** (additive) authz matrix / (default) none · **EXCERPTS:** none unless additive · **QUESTIONS:** the B-4 answer if unrecorded
