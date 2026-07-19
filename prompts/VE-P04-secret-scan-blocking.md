> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P04 — Make secret-scan blocking `[CODE]`

## 1. Context
**Wave 4.** Source: `01-audit-findings.md` X-3; MR-R05; critical-risk R7; `release-gates.md` G8. **Live:** `.github/workflows/ci.yml` `secret-scan` job has `continue-on-error: true` (non-blocking) though docs list it as required; Lighthouse advisory; `docs/ops/ci.md` says `deps-audit` informational while the workflow claims fail-on-high (CONFLICT). Branch-protection enforcement is founder-gated.
**Type:** `[CODE]` + a founder confirmation of branch protection.

## 2. Objective & scope
Make `secret-scan` blocking, reconcile the CI docs, and confirm branch protection requires it.
**Non-goals:** Lighthouse budgets (VE-P06); adding new scanners.

## 3. Files (edit ONLY these)
- `.github/workflows/ci.yml`
- `docs/ops/ci.md` (align blocking/informational claims)
**Guardrail: sole editor of `ci.yml` this wave (do not overlap VE-P06's `perf.yml`).**

## 4. Implementation spec
- Remove `continue-on-error: true` from `secret-scan`; keep the existing allowlist justifications (e.g. the `tmp`/`@lhci/cli` HIGH already documented) so the gate is truthful, not flaky.
- Reconcile `docs/ops/ci.md` so `secret-scan` and `deps-audit` blocking posture matches the YAML.
- Founder: confirm GitHub branch protection marks `secret-scan` (and the security-gates job) as required, no bypass.

## 10. Tests (RUN before reporting)
- A planted test secret makes `secret-scan` **fail** the run (remove it after).
- CI green on a clean commit; `docs/ops/ci.md` matches the YAML.

## 11. Acceptance criteria / DoD (G8)
- [ ] `secret-scan` blocking; planted secret blocks merge.
- [ ] `ci.md` reconciled with the workflow.
- [ ] Branch protection requires it (founder-confirmed screenshot/note).

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P04 — Make secret-scan blocking
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the planted-secret fail + clean-run pass · **EXCERPTS:** the `ci.yml` diff · **QUESTIONS:** branch-protection confirmation
