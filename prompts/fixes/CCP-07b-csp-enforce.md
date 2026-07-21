> **Prepend `prompts/_header.md`.** **TWO PRs, phased — do NOT enforce-first.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** Security-minded review before the enforce PR merges.

# CCP-07b — CSP: report-only → enforce (phased)

## Findings (from `docs/production-readiness/2026-07-20/code-completion-programme.md` CCP-07 + reconciliation R-4)

- **CCP-07a landed:** per-request nonce in all three middlewares, script policy shipped as `Content-Security-Policy-Report-Only` (`packages/auth/src/middleware.ts` `applyReportOnlyCspNonce`; each app `middleware.ts` + `next.config.ts`). Nonce-free hardening (`base-uri`, `object-src 'none'`, `frame-ancestors`, `form-action`) is already **enforced**.
- Enforce-first without an RO evidence window risks blank/broken **checkout (Lenco card widget)**, **vendor QR**, and **admin**.

## Required fix

**PR1 — `cursor/ccp-07b-csp-report-evidence` (evidence):** wire a CSP report sink (`report-uri`/`report-to`) and collect violations across browse→cart→checkout→**Lenco card widget**, vendor listing+QR, admin dashboards. Record the clean (or allowlisted) RO window in `docs/ops/security-headers.md`. **No enforce yet.**

**PR2 — `cursor/ccp-07b-csp-enforce` (enforce, only after a clean RO window):** promote the script policy from `Content-Security-Policy-Report-Only` to enforced `Content-Security-Policy`. Keep the per-request nonce; **never** add `'unsafe-inline'`/`'unsafe-eval'` to `script-src`; preserve the Lenco checkout allowlist and admin `frame-ancestors 'none'`/`frame-src 'none'`. Update `docs/ops/security-headers.md` + `scripts/ci/check-headers.mjs`.

## Files (ONLY)

- `packages/auth/src/middleware.ts`, `apps/{customer,vendor,admin}/middleware.ts` + `next.config.ts`
- `docs/ops/security-headers.md`, `scripts/ci/check-headers.mjs`

## Tests (RUN)

`scripts/ci/check-headers.mjs`; manual critical paths (card widget, vendor QR, admin dashboards) with zero console CSP breakage after enforce; Observatory target per the runbook.

## Report

STATUS/FILES/DEVIATIONS/TESTS (RO violation summary before PR2)/EXCERPTS/QUESTIONS.
