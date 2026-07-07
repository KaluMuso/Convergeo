> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 3 runs 5 pebbles in parallel — **touch ONLY your files below**. You solely own the `legal` i18n namespace this wave; do NOT touch other `messages/*.json`, `supabase/**`, `services/api/**`, or `packages/ui/src/*` component files other than the new `footer.tsx`.

# M15-P06 — Legal pages

## 1. Context

**Wave 3 (parallel ×5).** Grounded against as-built `master`:

- `packages/i18n/messages/en/legal.json` **already exists** but with **flat dotted keys** (`"legal.terms.title"`, `"legal.privacy.title"`, `"legal.updated"`). ⚠ **next-intl treats dots as nesting** — the same bug that forced `common.json` to be nested. **You MUST rewrite `legal.json` as a NESTED object** (`{ terms: {title, …}, privacy: {…}, returns: {…}, vendorAgreement: {…}, updated }`) and author all content keys there. `legal` is already in `NAMESPACES` with a loader in `request.ts` — no wiring needed.
- Customer app: `apps/customer/app/[locale]/layout.tsx` wraps children in `NextIntlClientProvider` (via `getMessages()`), imports `../globals.css`. There is **no `(marketing)` route group and no footer yet**. Pages are server components; use `useTranslations`/`getTranslations('legal')`.
- `packages/ui/src/footer.tsx` **does not exist** — you create it. Conventions: **no barrel** (deep import `@vergeo/ui/src/footer`), framework-agnostic `LinkComponent` prop defaulting to `<a>` (mirror `top-nav.tsx`/`bottom-nav.tsx`), test file with a `// @vitest-environment jsdom` first-line docblock + `import "@testing-library/jest-dom/vitest";` (no vitest.config.ts).
- ⚠ **M04-P06 (DPA export/delete flows) is NOT merged** — the privacy page links data-rights actions to `/{locale}/account/data` as a **documented target route** (not yet built); mark it clearly.
  Decisions to embed (`docs/plan/00-decisions.md`): **D4 commissions** (electronics 5% · home goods 8% · fashion/beauty 10% · services 12% · event tickets 5% · supplies/wholesale 3% · groceries/staples 5% · default 8% · free events 0%) — these mirror `commission_rates` seeds in `0008_config.sql` (bps: 500/800/1000/1200/500/300/500/800/0). **D17 returns two lanes**, **D13** Turnover-Tax posture + VAT-off-at-launch, **D8** prohibited categories, **D14** Lenco-held escrow + counsel review (F4) pending. Spec: `docs/plan/02-pebbles/M15-trust-security-compliance.md` §M15-P06.

## 2. Objective & scope

Four legal pages (Terms, Privacy/DPA, Returns, Vendor Agreement), a reusable Footer with legal links, the nested `legal` i18n content, wired into the customer layout.
**Non-goals:** no vendor/admin footer wiring (those app shells wire it later — customer only this wave), no checkout consent (M07-P05), no DPA flow implementation (M04-P06), no other namespaces.

## 3. Files (create/modify ONLY these)

- **Rewrite (nest + fill):** `packages/i18n/messages/en/legal.json`
- **Create:** `packages/ui/src/footer.tsx` + `packages/ui/src/footer.test.tsx`
- **Create:** `apps/customer/app/[locale]/(marketing)/legal/terms/page.tsx` · `.../privacy/page.tsx` · `.../returns/page.tsx` · `.../vendor-agreement/page.tsx` · `apps/customer/app/[locale]/(marketing)/legal/_components/legal-shell.tsx` (shared anchored-section chrome)
- **Modify:** `apps/customer/app/[locale]/layout.tsx` (render `<Footer>` after `{children}` — the only shared-file edit; no other W3 pebble touches this file)
  **Guardrail: nothing else.**

## 4. Implementation spec

- **`legal.json` (nested):** sections `terms`, `privacy`, `returns`, `vendorAgreement`, each with `title` + `sections` (heading + body strings), plus `updated` (ICU `Last updated {date}`) and a `counselNote` ("Pending legal review" per F4). Content drafted from decisions — plain, 360px-readable, anchor-linked. Privacy: Zambia DPA — consent basis, retention, and **export/delete rights** linking to `/{locale}/account/data`. Returns: **Lane 1** (faulty/wrong/not-as-described — report ≤48h with photo, full refund incl. delivery from escrow, return shipping on vendor, admin arbitrates) + **Lane 2** (change-of-mind, vendor opt-in per listing, 48h–7d window, unused/original condition, refund = item − outbound delivery − return transport − 10% restocking [config 5–15%], to mobile money or store credit). Vendor Agreement: commission table (the D4 rates), payout terms (D5 ≤48h / MoMo minutes), prohibited items (D8: salaula, used phones, fresh produce, alcohol, pharma, live animals, heavy building materials). Terms: escrow model (D14 Lenco-held + platform ledger), Turnover-Tax posture (D13, VAT off at launch).
- **Footer (`packages/ui/src/footer.tsx`):** token-styled (aubergine `--panel` footer per SELECTION), columns of links (legal, help, sell), payment-methods note ("MoMo · Airtel · Zamtel · Card"), app-name + copyright; **all copy via props** (`links`, `columns`, `note` — no literals in the component); `LinkComponent` prop. The customer layout passes localized labels + hrefs.
- **Pages:** server components; `generateMetadata` per page (title/description from `legal` namespace); `legal-shell.tsx` renders the anchored sections + "last updated" + counsel note; readable at 360px; semantic headings.
- **Layout edit:** import `Footer` from `@vergeo/ui/src/footer`, render below `{children}` inside the provider, pass legal links built from localized `legal`/`common` keys (reuse existing keys; if a label key is missing, add it to `legal.json` — do NOT touch `common.json`).

## 5. UI/UX & styling

Tokens only; aubergine footer; anchor-linked legal sections; "Pending counsel review (F4)" banner on each page.

## 6. Responsiveness

All pages + footer clean at 360px; footer columns stack.

## 7. Performance

Server-rendered static pages; no client JS beyond the provider; footer is a light server-safe component (no `"use client"` unless a link handler needs it).

## 8. SEO

Semantic HTML, per-page metadata + canonical; legal pages indexable (unlike the M02-P07 dev route).

## 9. Security

No secrets; commission figures stated as the D4 policy (note: authoritative rates live in `commission_rates`); no user input on these pages.

## 10. Tests (RUN before reporting)

- Footer (`// @vitest-environment jsdom`): renders provided links + labels, uses `LinkComponent`, no hardcoded user-facing strings.
- i18n completeness: a test asserting every key referenced by the four pages exists in `legal.json` and the file is valid nested JSON (no flat dotted keys remain).
- `pnpm --filter customer build` (all four routes compile), `pnpm --filter @vergeo/ui test`, `pnpm typecheck`, `pnpm lint`, `pnpm test`.
- Manual/asserted: footer legal links resolve to the four routes; privacy page links to `/{locale}/account/data`.

## 11. Acceptance criteria / DoD

- [ ] `legal.json` is nested (no flat dotted keys) and complete; pages render from it.
- [ ] Four legal pages live + linked from the customer footer; readable at 360px; "counsel review pending" noted.
- [ ] Vendor-agreement commission table states the D4 rates; returns page states both D17 lanes accurately.
- [ ] Footer is a reusable `@vergeo/ui` component (no barrel, LinkComponent, no literals); repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M15-P06 — Legal pages
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste build + footer + i18n-completeness output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
