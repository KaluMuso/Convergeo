> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 17 (parallel batch 1). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-17 creator of `packages/i18n/messages/en/marketing.json`** (M11-P05/M16-P05 were told NOT to touch it). **⚙ MULTI-WORKTREE: do NOT use `git stash`** (shared `refs/stash` corrupts sibling worktrees — `git worktree add /tmp/base origin/master`, never stash). **Run `pnpm --filter customer build/typecheck/lint` before reporting.**

# M16-P04 — Content pages

## 1. Context

**Grounded against as-built `master`:**

- **`apps/customer/app/[locale]/(marketing)/` exists with `legal/` + `sell/`** (M15-P06 owns `legal/*` + the `legal` namespace — do NOT touch either). Add `about/`, `contact/`, `help/` under the SAME marketing group.
- **`packages/i18n/messages/en/marketing.json` does NOT exist yet — you create it** (zero hardcoded user-facing strings — next-intl keys only, lint-enforced). Register it in the i18n loader the same way existing namespaces are (follow the existing pattern; if the loader auto-globs, no edit needed — confirm and note).
- **Contact form → outbox email** (existing outbox pattern — the WhatsApp/SMS/email outbox; contact is email via Resend). WhatsApp-first contact (a `wa.me` deep link is the primary CTA; the form is the fallback).
  Spec: `docs/plan/02-pebbles/M16-perf-pwa-launch-qa.md` §M16-P04.

## 2. Objective & scope

About, Contact (WhatsApp-first + form→outbox), Help center (MDX FAQ, ~20 founder-editable articles seeded from decisions — escrow explainer flagship), branded i18n 404/500 pages, and the `marketing` i18n namespace. Client-side FAQ search. 360px-first, ≤150KB gz.
**Non-goals:** no analytics wiring (M16-P05), no legal pages (M15-P06), no new API business logic beyond the contact→outbox submit, no design-token changes.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(marketing)/about/page.tsx` · `contact/page.tsx` (+ a `_components/contact-form.tsx` if needed) · `help/page.tsx` + `help/[slug]/page.tsx` · the help MDX content collection (e.g. `apps/customer/content/help/*.mdx` or the repo's existing content convention — follow it) · `apps/customer/app/not-found.tsx` · `apps/customer/app/error.tsx` · `packages/i18n/messages/en/marketing.json`
- **Modify:** the contact submit may reuse an EXISTING outbox endpoint — prefer calling an existing route; only if none exists, add a minimal `contact` handler (note it in the report and keep it owner-agnostic/rate-limited). **Do NOT add other locale message files beyond `en/marketing.json` (EN-first; translations later).**
  **Guardrail: nothing else. Do NOT touch `legal/*`, `sell/*`, the customer root `layout.tsx` (M16-P05 owns it), db.ts, migrations, other apps.**

## 4. Implementation spec

- **About/Contact/Help pages:** server components where possible (SSR/SEO), 360px-first, all copy via `marketing.*` keys. Contact = WhatsApp `wa.me` primary CTA + a validated form (name/message) that POSTs to the outbox (email via Resend) — client validation + server rate-limit.
- **Help center:** MDX collection, founder-editable in-repo; `help/page.tsx` lists + client-side searches (build a small client index — no server search); `help/[slug]/page.tsx` renders one article. Seed ~20 articles from decisions (escrow explainer flagship, COD rules, returns lanes, tickets, vendor how-to) — short stubs are fine, but the escrow explainer is real content.
- **404/500:** branded, i18n (`marketing.notFound.*` / `marketing.error.*`), recovery links (home/search). `error.tsx` is a client component (Next requirement).

## 5–9. Security etc.

Contact form: server-side rate-limit + input validation (no injection into email); no PII beyond what's submitted; no secrets in client; i18n keys only (lint-enforced); bundle ≤150KB gz (MDX/search index client-light — lazy the search index if heavy).

## 10. Tests (RUN before reporting)

MDX article renders; FAQ client search returns the escrow article for "escrow"; 404/500 render with recovery links; contact form validation (empty/invalid rejected). `pnpm --filter customer build` (bundle within budget — note the per-route gz sizes; if a marketing route exceeds 150KB, add its ceiling to `lighthouserc.json` **only if you own no conflict** — otherwise flag for the converger), `pnpm --filter customer typecheck/lint/test`.

## 11. Acceptance criteria / DoD

- [ ] About/Contact/Help + branded 404/500 all i18n via new `marketing.json`; FAQ client-searchable; contact→outbox with validation + rate-limit; escrow explainer is real content.
- [ ] Customer build green + within bundle budget (report gz sizes); no hardcoded strings; no touch to legal/sell/layout.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M16-P04 — Content pages
**STATUS/FILES/DEVIATIONS** (the MDX content convention you followed; how contact submits to the outbox; how you registered `marketing.json`; per-route gz sizes) **/TESTS** (paste MDX render + FAQ search + 404/500 + form-validation + build bundle line) **/EXCERPTS** the contact submit handler + the FAQ search index + the marketing namespace registration — nothing else **/QUESTIONS**
