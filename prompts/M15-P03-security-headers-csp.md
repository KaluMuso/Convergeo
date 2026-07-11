> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel batch 1). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-17 editor of `infra/Caddyfile` + all three `apps/*/next.config.ts`.** **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — use `git worktree add` to compare against master). **Run `pnpm build/typecheck/lint` for all three apps before reporting.**

# M15-P03 — Security headers & CSP

## 1. Context

**Grounded against as-built `master`:**

- **`infra/Caddyfile` exists** with a `(common_security)` snippet — extend it (per-origin headers for API + vendor + admin). Customer app is on Vercel (headers via `next.config.ts`), vendor/admin behind Caddy.
- **`apps/{customer,vendor,admin}/next.config.ts` all exist** — add CSP (nonce), HSTS, `frame-ancestors`, `referrer-policy`, `permissions-policy`. **Admin strictest.**
- **CSP allowances:** self, Cloudinary (`res.cloudinary.com`), Supabase (`*.supabase.co`), **Lenco widget ONLY on the customer checkout route** (scoped CSP — `checkout/card/[paymentId]`), GA4 (`*.googletagmanager.com`/`google-analytics.com` — M16-P05 wires GA4, but allow it in CSP). Report-only rollout → then enforce.
  Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P03.

## 2. Objective & scope

Per-origin security headers + CSP (nonce-based, report-only→enforce, admin strictest, Lenco widget scoped to checkout), a header-check CI script, and an ops doc. Mozilla-Observatory-A posture.
**Non-goals:** no app logic change, no GA4 wiring (M16-P05 — just allow it in CSP), no new route.

## 3. Files (create/modify ONLY these)

- **Modify:** `infra/Caddyfile` (per-origin header blocks for api/vendor/admin) · `apps/customer/next.config.ts` · `apps/vendor/next.config.ts` · `apps/admin/next.config.ts` (headers()/CSP; customer checkout-scoped Lenco allowance)
- **Create:** `docs/ops/security-headers.md` (the policy per origin + report-only→enforce runbook) · `scripts/ci/check-headers.mjs` (asserts required headers present per origin config)
  **Guardrail: nothing else. Do NOT touch app routes/components, `ci.yml` (M15-P05 owns it this wave — the header-check wiring into CI is a converger step; ship the script + document how to run it), customer root `layout.tsx` (M16-P05 owns it), db.ts, migrations.**

## 4. Implementation spec

- **`next.config.ts` (each app):** `async headers()` (or middleware nonce) returning HSTS (`max-age=63072000; includeSubDomains; preload`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (deny camera/mic/geo except where a route needs it — vendor scanner needs camera; scope it), `Content-Security-Policy` with a nonce; `frame-ancestors 'none'` (admin) / self (others). **Customer checkout card route** gets a route-scoped CSP `frame-src`/`script-src` allowing the Lenco widget origin; the rest of the customer app does NOT.
- **Caddyfile:** reuse/extend `(common_security)`; api origin = strict (no framing), admin = strictest allowlist.
- **`check-headers.mjs`:** parse each `next.config.ts`'s header set (or a shared header manifest you define) and assert required headers exist; exit non-zero if a required header is missing. Document running it (converger wires it into ci.yml).

## 5–9. Security etc.

CSP nonce (no `unsafe-inline` for scripts); Lenco widget scoped to checkout only; admin strictest + `frame-ancestors 'none'`; HSTS preload; report-only rollout documented; no secrets in headers.

## 10. Tests (RUN before reporting)

`node scripts/ci/check-headers.mjs` passes; `pnpm --filter customer build`, `pnpm --filter vendor build`, `pnpm --filter admin build` (CSP doesn't break the build); `pnpm typecheck/lint` for all three. Manually verify the Lenco allowance is present ONLY on the checkout card route config.

## 11. Acceptance criteria / DoD

- [ ] Required headers present per origin (check script passes); Lenco widget CSP scoped to checkout; admin strictest; report-only→enforce documented.
- [ ] All three app builds green; no CSP change leaks the Lenco allowance to non-checkout routes.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M15-P03 — Security headers & CSP
**STATUS/FILES/DEVIATIONS** (the per-origin header set; the nonce approach; how Lenco is scoped to checkout; report-only vs enforce) **/TESTS** (paste check-headers + the three builds) **/EXCERPTS** the customer CSP (incl. checkout Lenco scoping) + admin CSP — nothing else **/QUESTIONS**
