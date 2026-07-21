> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration.** Run `pnpm --filter customer typecheck lint test` (+ affected vendor/admin) before reporting.

# FIX-I — Fail-closed API base residual (account/* + sitemap) (🟡 honesty / SEO)

## Findings (from `docs/production-readiness/2026-07-21/code-reconciliation-since-audits.md` R-2)

- The `(shop)` conversion path is already fail-closed via `apps/customer/lib/api-base-url.ts` (`resolveApiBaseUrl` → `null` in production when `NEXT_PUBLIC_API_BASE_URL` is unset).
- **~27 sites still inline** `process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"`, all under `apps/customer/app/[locale]/account/**` (orders, jobs, tickets, dispute, return, privacy, business), `(marketing)/beta/_components/beta-gate.tsx`, and **`apps/customer/lib/seo/sitemap-events.ts`** — the sitemap is a public SEO artifact that would emit `localhost:8000` if env is ever unset.

## Required fix

1. Replace each inline fallback with `resolveApiBaseUrl` / `absoluteApiUrl` from `apps/customer/lib/api-base-url.ts`.
2. Each call site handles the `null` return honestly — skip the fetch and render the existing unavailable/empty-honest state — **never** localhost. Do not use `getApiBaseUrl()`'s `""` fallback where it would produce a relative fetch during SSG.
3. `sitemap-events.ts`: when base is `null`, return `[]` (omit the events chunk) — never localhost.
4. Confirm `apps/vendor` and `apps/admin` route every domain api client through their own `lib/api-base-url.ts` (VEND-11 / ADM-11); fix any residual inline localhost there.

## Files (ONLY)

- `apps/customer/app/[locale]/account/**` client modules carrying the inline fallback
- `apps/customer/app/[locale]/(marketing)/beta/_components/beta-gate.tsx`
- `apps/customer/lib/seo/sitemap-events.ts`
- `apps/vendor/**`, `apps/admin/**` residual api clients (only if they inline localhost)
- Extend `apps/customer/lib/api-base-url.test.ts` (+ a sitemap null-base test)
- **Do NOT** change the helper's prod-`null` semantics.

## Tests (RUN)

Helper null-path covered; sitemap returns `[]` when base unset; an account client renders the unavailable state (not localhost) in a production build. `rg 'localhost:8000' apps` returns only the dev-guarded helper defaults. `pnpm --filter customer typecheck lint test`.

## Report

STATUS/FILES/DEVIATIONS/TESTS (paste the `rg 'localhost:8000' apps` result)/EXCERPTS/QUESTIONS.
