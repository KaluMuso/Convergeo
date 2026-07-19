> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VC-P05 — Collapse the duplicate `/refunds/execute` mount `[CODE]`

## 1. Context
**Wave 3.** Source: `01-audit-findings.md` §5 hygiene (backend agent finding). **`refunds.py` mounts the refund router twice** — at `/admin/refunds/execute` (under `AdminAuditedRoute`) **and** directly at `/refunds/execute`. The direct mount is still admin-protected (its handler `Depends(get_admin_audit_recorder)` → `require_role("admin")`) and records audit manually, but it **skips the `AdminAuditedRoute` audit-completeness enforcement** wrapper. Duplicate money-mutation surface worth collapsing.
**Type:** `[CODE]`.

## 2. Objective & scope
Keep a single admin-audited `/admin/refunds/execute` mount; remove the direct `/refunds/execute` mount; update callers/tests.
**Non-goals:** changing refund business logic (correct per `test_refund_execute.py`); other routers.

## 3. Files (edit ONLY these)
- `services/api/app/routers/refunds.py`
- any client caller of `/refunds/execute` (frontend/admin) that must move to `/admin/refunds/execute` — **list them in DEVIATIONS if outside `services/api`** and coordinate rather than silently editing another pebble's files
**Guardrail: modify ONLY `refunds.py` (+ its own tests); record cross-app caller changes under DEVIATIONS.**

## 4. Implementation spec
- Remove the `router = refunds_router` direct mount; keep `admin_router.include_router(refunds_router)` so the endpoint lives only at `/admin/refunds/execute` under `AdminAuditedRoute`.
- Confirm the authz-matrix/route-classification tests still pass (no dependency-public regression).

## 9. Security
- Single admin-audited mount; audit-completeness enforced by the route class; no authz weakened.

## 10. Tests (RUN before reporting)
- `uv run pytest services/api/tests/test_refund_execute.py test_authz_matrix.py -q` green.
- `uv run ruff check` / `mypy` clean.

## 11. Acceptance criteria / DoD
- [ ] Only `/admin/refunds/execute` exists (direct mount gone).
- [ ] Audit-completeness enforced via `AdminAuditedRoute`; authz tests green.
- [ ] Callers updated (or listed under DEVIATIONS for the owning app).

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VC-P05 — Collapse the duplicate `/refunds/execute` mount
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** cross-app callers · **TESTS:** paste refund + authz pytest · **EXCERPTS:** the mount change · **QUESTIONS:** …
