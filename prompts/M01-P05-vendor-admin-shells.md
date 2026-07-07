> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M01-P05 — Vendor & admin app shells

## 1. Context
**Wave 0, pebble 5 of 7 (sequential).** Depends on **M01-P04** (customer shell — the pattern to clone; `packages/ui` preset stub and `packages/i18n` already exist). Spec source: `docs/plan/02-pebbles/M01-foundations.md` §P05. Read also: `docs/plan/00-decisions.md` D20 (three apps; admin = separate hardened origin).

## 2. Objective & scope
`apps/vendor` and `apps/admin` skeletons cloning the P04 pattern. Admin is deliberately austere: **noindex, standalone output for Docker, separate origin/port config** — no SEO, no PWA, ever.
**Non-goals:** no auth guards (M04-P03), no features, no admin hardening middleware (M13-P01), no new i18n namespaces beyond what the shells minimally need from `common.json` (do not edit `common.json` — it is P04's file; if a key is missing, record under DEVIATIONS).

## 3. Files (create ONLY these)
- `apps/vendor/`: `package.json`, `next.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`, `middleware.ts` (locale stub), `app/[locale]/layout.tsx`, `app/[locale]/page.tsx`, `app/globals.css`
- `apps/admin/`: same skeleton set **plus** `app/robots.ts` (or `public/robots.txt`) — noindex
**Guardrail: modify ONLY these files; anything else → DEVIATIONS.**

## 4. Implementation spec
- Clone the P04 pattern exactly (locale middleware, `[locale]` layout + NextIntlClientProvider, placeholder page with i18n strings, ui preset via Tailwind config).
- **Admin specifics:** `output: 'standalone'` in `next.config.ts` (Docker deploy on OCI); `robots` → `Disallow: /` + `noindex` metadata/header; document the separate origin/port assumption (`admin.` host, distinct dev port) in `next.config.ts` comments; no analytics, no PWA.
- **Vendor specifics:** standalone output too (also OCI-served per D21); default SEO metadata minimal (it's auth-gated later).
- Dev ports distinct so `pnpm dev` runs all three apps concurrently.

## 5. UI/UX & styling
Shells only; semantic HTML placeholders; strings via existing `common.json` keys (or generic app-name key). No ad-hoc styling.

## 6. Responsiveness
Both placeholder pages clean at 360px (vendor app is a mobile daily-driver later).

## 7. Performance
Server components only; note route JS baseline in the report.

## 8. SEO
**Anti-SEO for admin** (noindex asserted by test). Vendor: minimal metadata.

## 9. Security
Admin marked noindex + standalone + separate-origin documented; no secrets; middleware = locale only (auth is M04).

## 10. Tests (RUN before reporting)
- Smoke render each app's placeholder (localized string appears).
- **Admin noindex asserted** (robots route/file content + metadata).
- All three apps run concurrently via `pnpm dev` (distinct ports — paste boot output).
- Commands: `pnpm --filter vendor --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD
- [ ] Both apps dev + build green.
- [ ] Admin: noindex + `output: 'standalone'` + separate origin/port documented.
- [ ] All three apps run concurrently via `pnpm dev`.
- [ ] Zero hardcoded strings; no edits to files owned by P01–P04.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M01-P05 — Vendor & admin app shells
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual build/test output (incl. concurrent dev boot)
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
