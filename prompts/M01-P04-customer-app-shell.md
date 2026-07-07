> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P04 — Customer app shell

## 1. Context
**Wave 0, pebble 4 of 7 (sequential).** Depends on **M01-P01, M01-P03**. Creates the first Next.js app + the `packages/ui` preset stub and `packages/i18n` scaffolding it consumes. Vendor/admin shells clone this pattern in P05. Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P04. Read also: `docs/plan/00-decisions.md` D19/D27 (Next 15, i18n scaffolding).

## 2. Objective & scope
`apps/customer` App Router skeleton (TS strict, Tailwind 4 via the ui preset, next-intl EN, 360px-first placeholder, zero hardcoded strings) + minimal `packages/ui` (preset **stub**) + `packages/i18n` (messages + request config).
**Non-goals:** no real design tokens (M02-P01), no `formatK` (M02-P02), no auth (M04), no PWA (M16), no vendor/admin apps (P05), no components.

## 3. Files (create ONLY these)
- `apps/customer/`: `package.json`, `next.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`, `vercel.json`, `middleware.ts` (**locale stub only — no auth**), `app/[locale]/layout.tsx`, `app/[locale]/page.tsx` (placeholder), `app/globals.css`
- `packages/ui/`: `package.json`, `tailwind-preset.ts` (**stub** — real tokens land in M02-P01), `tsconfig.json`
- `packages/i18n/`: `package.json`, `tsconfig.json`, `messages/en/common.json`, `src/request.ts` (next-intl request config), `src/locales.ts` (`['en','bem','nya','fr']`, default `en`)
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec
- **Locale routing:** next-intl middleware over the locale list; `/` → `/en`; unknown locale → 404. `[locale]` layout wraps `NextIntlClientProvider`, sets `<html lang>`.
- **Placeholder page:** app name + one localized sentence — **every string from `messages/en/common.json`** (ICU). Mobile viewport meta; no horizontal scroll at 360px.
- **Tailwind:** `tailwind.config.ts` consumes `packages/ui/tailwind-preset.ts` (stub exports an empty-ish theme extension with a TODO pointing at M02-P01).
- **`vercel.json`:** root/app config for the Vercel project (build command, framework), no env values.
- **i18n messages:** per-namespace files from day one — this pebble owns only `common.json`.
- Deep imports only (`@vergeo/i18n/src/locales` style or package-exports map) — **no barrels**.

## 5. UI/UX & styling
Shell only. No ad-hoc colors — anything visual waits for M02 tokens; use plain semantic HTML.

## 6. Responsiveness
360px-first: placeholder renders cleanly at 360px (no horizontal scroll), still fine at desktop.

## 7. Performance
Placeholder page is a server component; zero client JS beyond the framework baseline. `pnpm build` output noted in the report (route JS size).

## 8. SEO
Base `metadata` (title template + description via i18n) in the locale layout; correct `lang` attribute. Full SEO is M05-P09.

## 9. Security
No secrets; only `NEXT_PUBLIC_*` vars may reach the client (none needed yet). Middleware does locale only — no auth logic.

## 10. Tests (RUN before reporting)
- Vitest smoke render of the placeholder page (localized string appears).
- **Missing-i18n-key failure case** (missing key surfaces as error/fallback per next-intl config — assert the configured behavior).
- Middleware: `/` redirects to `/en`; unknown locale 404s.
- Commands: `pnpm --filter customer build`, `pnpm --filter customer dev` (boot check), `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD
- [ ] `pnpm dev --filter customer` renders the localized placeholder; `pnpm build` green.
- [ ] All user-facing strings come from `common.json` (zero hardcoded).
- [ ] Locale routing works (`/`→`/en`, bad locale 404).
- [ ] ui preset stub + i18n package consumable via deep imports, no barrels.
- [ ] Clean at 360px.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P04 — Customer app shell
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual build/test/typecheck output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
