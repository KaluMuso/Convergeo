> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 5 runs 6 pebbles in parallel — **touch ONLY your files below**. Stay **dep-free** (M04-P07 owns Python deps; no new pnpm deps needed — use existing `@vergeo/ui`, `@vergeo/auth`, `@vergeo/i18n`).

# M04-P04 — Auth UI (login / signup / OTP)

## 1. Context

**Wave 5 (parallel ×6).** Grounded against as-built `master`:

- **`@vergeo/auth` exists** (M04-P03): browser/server Supabase SSR clients, `useSession`, role helpers. All three apps have composed auth+locale middleware. **The vendor/admin middleware redirects unauthenticated users to `/{locale}/login`** (`createLoginRedirect` → `/${locale}/login?next=…`; the login path is exempt from the gate). **Your login pages MUST resolve to `/{locale}/login`.**
- **All three apps use `localePrefix: "always"`** — every route lives under `app/[locale]/`. The spec's `apps/vendor/app/(auth)/…` / `apps/admin/app/(auth)/…` paths are **stale (missing `[locale]`)**: put auth pages under **`app/[locale]/(auth)/`** in all three apps so they match the middleware's `/{locale}/login`.
- **i18n `auth` namespace is already registered** in `NAMESPACES` with a loader; `packages/i18n/messages/en/auth.json` exists but is a **buggy flat-dotted skeleton** (`"auth.login.title": …`). next-intl **nests on dots** → you MUST rewrite it as a **nested object without the redundant `auth.` prefix** (pattern: `legal.json` / `vendor.json`), consumed via `useTranslations('auth')` + `t('login.title')` (client) or `loadNamespace(locale,'auth')` (server). Zero flat dotted keys.
- Form primitives exist in `@vergeo/ui` (M02-P03): inputs, `OTPField` (paste/auto-advance), buttons — deep-import `@vergeo/ui/src/<name>`.
  Spec: `docs/plan/02-pebbles/M04-auth-accounts.md` §M04-P04.

## 2. Objective & scope

Phone-first login/signup/OTP UI for all three apps, email+password and Google as alternates, all states i18n-keyed, compelling at 360px.
**Non-goals:** no account pages (M04-P05), no rate-limit backend (M04-P07 — but wire the throttled/`retry-after` **error states** so they're ready), no admin shell/layout (M13-P01 — you only add the `(auth)` group + its own minimal chrome), no DPA (M04-P06).

## 3. Files (create/modify ONLY these)

- **Create (customer):** `apps/customer/app/[locale]/(auth)/login/page.tsx` · `signup/page.tsx` · `otp/page.tsx` · `(auth)/layout.tsx` (minimal auth chrome, no app nav) · `(auth)/_components/{phone-form,otp-form,email-form,google-button,resend-countdown}.tsx`
- **Create (vendor):** `apps/vendor/app/[locale]/(auth)/login/page.tsx` (+ reuse shared components via import from a shared location — see below)
- **Create (admin):** `apps/admin/app/[locale]/(auth)/login/page.tsx`
- **Modify:** `packages/i18n/messages/en/auth.json` (nest + fill: login/signup/otp/errors)
  **Shared components:** to avoid duplicating the forms three times, place the reusable form components in **`@vergeo/ui/src/auth/`** (deep-import, no barrel) if cross-app reuse is needed — BUT `@vergeo/ui` is multi-owned; if adding there risks collision, instead keep them in the **customer** `(auth)/_components/` and have vendor/admin import their own thin pages calling `@vergeo/auth`. **Pick ONE approach, state it in DEVIATIONS.** Do NOT edit `@vergeo/ui` barrels or other pebbles' files.
  **Guardrail: nothing else — no middleware edits (M04-P03/M13-P01 own those), no layout edits outside your `(auth)/layout.tsx`, no `request.ts`.**

## 4. Implementation spec

- **Phone-first:** country code **+260 default**, national number entry; submit → Supabase phone OTP (via `@vergeo/auth` browser client `signInWithOtp`), route to `/{locale}/otp?phone=…`.
- **OTP page:** `@vergeo/ui` `OTPField`; **resend with cooldown countdown** (disabled during cooldown); error states — wrong code, expired, **throttled/`retry-after`** (reads a 429 body → localized "try again in {seconds}") — all `auth.*` keys.
- **Alternates:** email+password sign-in and **Google** (`@vergeo/auth` OAuth) as secondary options.
- **Post-auth:** respect the `?next=` param the middleware set; default to `/{locale}` (customer), vendor/admin dashboards.
- Server components for shells; client components only for the interactive forms.

## 5. UI/UX & styling

Tokens only (`@vergeo/ui`); phone-first, thumb-reachable CTAs; a11y labels complete (each input labelled, OTP announced). Editorial-but-minimal auth chrome (no marketing nav).

## 6–8. Responsiveness · Performance · SEO

360px-first; signup→browse achievable on phone number alone. Light client JS. Auth pages `noindex` (not SEO surfaces).

## 9. Security

Anon key only (client), never service-role; no secrets in code; OTP throttling enforced server-side (M04-P07) — UI just surfaces the state; Google via `@vergeo/auth` (no token handling in UI).

## 10. Tests (RUN before reporting)

Component tests (jsdom docblock per file, the established pattern): happy path (phone→OTP→success), wrong OTP, resend cooldown disables/re-enables, throttled→retry-after message. i18n completeness for `auth.*` (nested, no flat dotted keys). `pnpm --filter customer --filter vendor --filter admin build`; `pnpm typecheck`, `pnpm lint`, `pnpm test` green.

## 11. Acceptance criteria / DoD

- [ ] `/{locale}/login`, `/signup`, `/otp` render in all three apps; login path matches the middleware redirect.
- [ ] Phone-first + email + Google; resend cooldown; throttled/expired/wrong-code states all i18n-keyed.
- [ ] `auth.json` nested (0 flat dotted keys); a11y complete at 360px; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M04-P04 — Auth UI (login/signup/OTP)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** state the shared-components approach chosen (or "none")
**TESTS:** paste build + component-test + i18n-completeness output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
