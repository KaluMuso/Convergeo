> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 4 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ Do NOT add any dependency / touch `pnpm-lock.yaml`** (M04-P03 solely owns it this wave) — stay dep-free.

# M12-P11 — Public vendor pitch page

## 1. Context

**Wave 4 (parallel ×6).** Grounded against as-built `master`:

- Customer app has a **`(marketing)` route group already** (M15-P06 created `apps/customer/app/[locale]/(marketing)/legal/…` + a `Footer` in the root layout). You add `(marketing)/sell/` alongside — no collision, no layout edit needed (footer already renders).
- i18n: `packages/i18n/messages/en/vendor.json` exists (M02-P02 skeleton). `vendor` is in `NAMESPACES` with a loader. **You own `vendor.json` this wave** (no other W4 pebble touches it). Load a namespace in a server component via `loadNamespace('en'|locale, 'vendor')` + `createTranslator` (the pattern M15-P06's layout used) OR `getTranslations` — match how the legal pages consume `legal`. Keys are **nested** (next-intl nests on dots — do not use flat dotted keys).
- ⚠ **No live config-read client exists on the customer app yet** (Supabase SSR clients land in M04-P03, parallel; commission_rates is public-read in `0008_config.sql` but you cannot add `@supabase/*` deps). So render the commission table from the **D4 constants** (which equal the `commission_rates` seed) as a typed constant in `_components/`, with a prominent comment + a `TODO(config)` to bind to live `commission_rates` once a public config read exists (M13-P07 / a catalog config endpoint). Do NOT stale-copy into three places — one constant module.
- Decisions to state (`00-decisions.md`): **D3** "Free to list. Pay only when you sell." (free tier: 30 listings). **D4** commissions (electronics 5% · home 8% · fashion/beauty 10% · services 12% · tickets 5% · supplies 3% · groceries 5% · default 8% · free events 0%). **D5** payout promise ("Paid out in minutes on mobile money — always within 48 hours"). **D9** KYC tiers (T1 NRC+selfie same-day → sell). **D2** all five verticals.
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P11.

## 2. Objective & scope

The founder's public recruitment page on the customer origin: hero, value props, commission table, how-it-works, KYC explainer, payout promise, FAQ, CTA → vendor app signup. SEO'd, fast, compelling at 360px.
**Non-goals:** no live config binding yet (D4 constants + TODO), no vendor onboarding flow (M12-P01 — CTA deep-links only), no footer/layout changes (M15-P06 done), no new deps.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(marketing)/sell/page.tsx` · `apps/customer/app/[locale]/(marketing)/sell/_components/{hero,commission-table,how-it-works,kyc-explainer,payout-promise,faq,cta}.tsx` · `apps/customer/app/[locale]/(marketing)/sell/_components/commission-rates.ts` (the single D4-constant module)
- **Modify (nest + fill):** `packages/i18n/messages/en/vendor.json` (add a `pitch` section — all page copy; keep existing skeleton keys)
  **Guardrail: nothing else — do NOT touch `.env.example` (M04-P03 owns it), `pnpm-lock.yaml`, or the root layout.**

## 4. Implementation spec

- Server component page composing the sections from `@vergeo/ui` primitives (Button, cards, badges) + local section components; all copy via the `vendor` namespace (`pitch.*`), zero hardcoded user-facing strings.
- **`commission-rates.ts`:** exports the D4 rate list `[{categoryKey, label, ratePct}]` matching `0008` seeds; the commission table renders from it; `TODO(config)` comment as above.
- Hero: "Free to list. Pay only when you sell." + dual CTA (Start selling → vendor signup URL). Read a configurable base `process.env.NEXT_PUBLIC_VENDOR_APP_URL ?? "http://localhost:3001"` (fallback in code; **do NOT edit `.env.example`** — M04-P03 owns it this wave; add a `TODO(env)` comment naming `NEXT_PUBLIC_VENDOR_APP_URL` for a later env pass). Do NOT hardcode a prod host.
- KYC explainer: T1 same-day (NRC + selfie + MoMo-name), tiers ladder. Payout promise: D5 wording. FAQ: a handful (fees, payout timing, what can I sell, KYC). CTA repeats the signup deep-link.
- `generateMetadata`: SEO title/description/OG from `vendor.pitch`; canonical; **indexable** (this is an acquisition page).

## 5. UI/UX & styling

Tokens only (`@vergeo/ui`); editorial hero per SELECTION; commission table legible at 360px (stacks/scrolls, no horizontal page scroll).

## 6. Responsiveness

360px-first; commission table uses an `overflow-x:auto` container if it must scroll; CTAs thumb-reachable.

## 7. Performance

Static/SSR; **LCP ≤2.5s target**; no heavy client JS (server components); images via `@vergeo/ui` `CloudinaryImage` or none.

## 8. SEO

Semantic HTML, per-page metadata, canonical, schema.org where sensible; indexable.

## 9. Security

No secrets; vendor-app URL from an env name (not hardcoded); no user input.

## 10. Tests (RUN before reporting)

- Config-driven table: a test asserting the rendered commission table rows equal `commission-rates.ts` (which equals the D4/0008 seed values) — catches drift.
- SEO metadata present; CTA hrefs resolve to the vendor-app signup deep-link; i18n completeness for `vendor.pitch` keys (nested, no flat dotted keys).
- `pnpm --filter customer build` (route compiles for all 4 locales), `pnpm typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] `/sell` renders hero, commission table (D4 constants + config TODO), how-it-works, KYC, payout promise, FAQ, CTA.
- [ ] Commission table = the constant module (test-asserted); metadata + indexable; CTA deep-links to vendor signup.
- [ ] Compelling + no horizontal scroll at 360px; `vendor.json` nested; no new deps; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M12-P11 — Public vendor pitch page
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste build + config-table + i18n-completeness output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
