> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **⚙ do NOT use `git stash`.** No migration. **⚠ Do NOT flip to enforce without a clean report-only evidence window (see gate below).** Foreground blocking only.

# FIX-M — Promote CSP from Report-Only to enforce (CCP-07b PR2)

## Finding

CSP runs in **report-only** across all three apps: per-request nonce middleware + `Content-Security-Policy-Report-Only` header (CCP-07a, `e0e4e79`), and #479 (`a872b555`) wired the **report sink** so violations are now collected (CCP-07b PR1). The enforce flip has not happened. Until it does, the CSP provides monitoring but no actual XSS protection.

## Gate (MUST hold before this PR merges — not a code condition, an evidence one)

- A **clean report-only evidence window** on production: the report sink shows **no legitimate violations** across the real customer journeys — critically **checkout with the Lenco hosted widget** (the highest-risk surface; the widget injects script/frame that the policy must already allow), plus auth/OTP, media/Cloudinary, and analytics. Record the window + a zero-legit-violations summary under `docs/production-readiness/<date>/csp-enforce-evidence.md`. **If checkout would break under enforce, that is exactly what report-only exists to catch — fix the policy first.**

## Required change (once the gate holds)

- Switch the header from `Content-Security-Policy-Report-Only` to `Content-Security-Policy` (enforce) in the customer app first, keeping the per-request nonce and the `report-uri`/`report-to` sink live so regressions still surface. Vendor + admin follow after their own windows (admin is `frame-ancestors 'none'`, strictest).
- Keep the Lenco widget scope limited to the checkout route only (do not widen `script-src`/`frame-src` globally to make it pass).
- Roll back path documented: revert to report-only by flipping the header name.

## Files (ONLY)

- Modify `apps/customer/next.config.ts` (header name; nonce + sink unchanged) — vendor/admin in follow-up PRs
- Modify `docs/ops/security-headers.md` (record the RO→enforce promotion + rollback)
- **Do NOT touch** the nonce middleware logic, the report sink, migrations, `db.ts`.

## Tests / verification (RUN)

- `security-gates` (headers manifest) green with the enforced header.
- Served-HTML check: `Content-Security-Policy` present (not `-Report-Only`), nonce present, `report-to` still set.
- Manual/E2E: checkout with the Lenco widget renders and completes under enforce (the acceptance test); auth/OTP, media, analytics unaffected.

## Report

STATUS / FILES / DEVIATIONS / EVIDENCE (link the clean RO window; confirm checkout-under-enforce passed) / TESTS (paste the header check + security-gates) / QUESTIONS.
