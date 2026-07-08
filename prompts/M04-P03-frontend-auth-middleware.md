> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 4 runs 6 pebbles in parallel — **touch ONLY your files below**. You are the SOLE owner of `pnpm-lock.yaml` this wave (you add `@supabase/ssr`); no other W4 pebble adds deps.

# M04-P03 — Frontend auth clients & middleware guards

## 1. Context

**Wave 4 (parallel ×6).** Grounded against as-built `master`:

- All three apps have a **locale-only middleware** using `next-intl/middleware`. Current `apps/customer/middleware.ts`:
  ```ts
  import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";
  import createMiddleware from "next-intl/middleware";
  export default createMiddleware({
    locales: [...LOCALES],
    defaultLocale: DEFAULT_LOCALE,
    localePrefix: "always",
  });
  export const config = { matcher: ["/", "/(en|bem|nya|fr)/:path*"] };
  ```
  You must **compose** auth with this — never drop locale routing. vendor/admin have the same stub.
- `packages/auth/` does NOT exist — you create it (new workspace package → you own the `pnpm-lock.yaml` change). Env names: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (customer app already declares public env in `packages/config`; confirm/reuse names — add `NEXT_PUBLIC_*` to `.env.example` if missing, names only).
- App origins: customer `:3000` (public, browsable logged-out), vendor `:3001` (vendor-gated), admin `:3002` (admin-gated).
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P03.

## 2. Objective & scope

A shared `@vergeo/auth` package (Supabase SSR browser/server clients, `useSession`, role helpers) + role-gated middleware composed with locale routing in all three apps.
**Non-goals:** no login/signup UI (M04-P04), no account pages (M04-P05), no API auth (M04-P02), no admin Cloudflare-Access hardening (M13-P01 — leave a flagged bypass).

## 3. Files (create/modify ONLY these)

- **Create:** `packages/auth/{package.json,tsconfig.json}` · `packages/auth/src/{index.ts,browser-client.ts,server-client.ts,middleware.ts,use-session.ts,roles.ts}` · `packages/auth/src/*.test.ts(x)`
- **Modify:** `apps/customer/middleware.ts`, `apps/vendor/middleware.ts`, `apps/admin/middleware.ts` (compose auth + locale), and each app's `package.json` + root `pnpm-lock.yaml` (add `@vergeo/auth` workspace dep + `@supabase/ssr`), `.env.example` (append any missing `NEXT_PUBLIC_SUPABASE_*` names)
  **Guardrail: nothing else — especially no app pages/layouts, no `packages/i18n`, no `supabase/**`.**

## 4. Implementation spec

- **`@vergeo/auth`** (uses `@supabase/ssr`): `createBrowserClient()`, `createServerClient(cookies)` (SSR cookie handling), `updateSession(request)` helper (refresh-rotation in middleware), `useSession()` hook (client), `roles.ts` (`hasRole`, `getRoles` reading `user_roles` via the server client, or from JWT app_metadata for the middleware fast-path — document which). Deep imports, **no barrel beyond `index.ts` re-export** (this package MAY have an index barrel since it's single-owned — unlike `@vergeo/ui`).
- **Middleware composition (all three apps):** run `@vergeo/auth` `updateSession` (refresh) THEN the next-intl locale middleware, merging responses. **customer**: optional auth — never blocks (browsable logged-out), just refreshes session. **vendor**: if no session OR no `vendor` role → redirect to `/{locale}/login` (or vendor login route). **admin**: require `admin` role → redirect otherwise; add a `NEXT_PUBLIC_ADMIN_BYPASS`-style **non-prod bypass flag** + a comment that Cloudflare-Access header enforcement lands in M13-P01. Preserve the locale `matcher`.
- **Session refresh rotation** handled in `updateSession` (Supabase SSR cookie refresh).

## 5–7. UI/UX · Responsiveness · Performance

Middleware is edge-light; no blocking DB calls in the hot path (role from session/JWT metadata for gating; authoritative DB re-check is the API's job per M04-P02).

## 8. SEO

Customer stays SSR-friendly + logged-out-browsable (no auth wall on public routes).

## 9. Security

vendor/admin bounce unauthenticated/under-privileged; session cookies httpOnly + refresh-rotated; admin bypass flag **off by default + non-prod only**; anon key only on client (never service-role).

## 10. Tests (RUN before reporting)

- `packages/auth`: role helpers (`hasRole`), `updateSession` cookie behavior (mock request/response), server/browser client construction.
- **Middleware matrix per app** (unit, mock session): customer logged-out → 200 (passes through, locale preserved); vendor no-session → redirect to login; vendor with vendor-role → pass; admin non-admin → redirect; admin with admin-role → pass; **locale routing still applied in every case** (e.g. `/` → `/en`).
- `pnpm --filter customer --filter vendor --filter admin build`; `pnpm typecheck`, `pnpm lint`, `pnpm test` green.

## 11. Acceptance criteria / DoD

- [ ] `@vergeo/auth` provides SSR clients + session + role helpers; single new dep `@supabase/ssr`.
- [ ] All three middlewares compose auth + locale (locale never dropped); customer browsable logged-out; vendor/admin gated.
- [ ] Session survives refresh; admin non-prod bypass flagged; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M04-P03 — Frontend auth clients & middleware guards
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste build + middleware-matrix output
**EXCERPTS:** full code of the three `middleware.ts` compositions + `roles.ts` (authz surfaces) — nothing else
**QUESTIONS:** (or "none")
