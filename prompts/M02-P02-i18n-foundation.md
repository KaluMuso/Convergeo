> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# M02-P02 — i18n foundation & formatters (completion)

## 1. Context
**Wave 1 (parallel with M02-P01 and M01-P08 — files disjoint; touch nothing outside your list).** Wave 0 merged and **pre-built part of this pebble**: `packages/i18n` already has `src/format.ts` (`formatK`, `formatDate`, `formatNumber` — tested), `src/locales.ts` (`['en','bem','nya','fr']`), `src/request.ts` (next-intl request config + EN fallback), `messages/en/common.json`, and a lint-rule **stub** at `packages/i18n/eslint-no-hardcoded-strings.js`. The shared ESLint preset lives at `packages/config/eslint.config.mjs` with a commented slot for this rule. Spec source: `docs/plan/02-pebbles/M02-design-system.md` §P02. **Do not rewrite what exists and passes — complete it.**

## 2. Objective & scope
Finish the i18n foundation: split formatters into per-domain modules, create all 16 message-namespace skeleton files, harden the no-hardcoded-strings ESLint rule and **wire it into the shared preset**, and ensure per-namespace lazy loading.
**Non-goals:** no design tokens (M02-P01), no translations beyond EN skeletons, no app feature strings (feature pebbles own their namespace content), no new npm dependencies (**do not touch `pnpm-lock.yaml`** — M02-P01 owns it this wave).

## 3. Files (create/modify ONLY these)
- **Modify:** `packages/i18n/src/format.ts` → keep as thin re-export; **Create** `packages/i18n/src/format/money.ts` (move `formatK` here verbatim — it is tested and approved), `format/datetime.ts`, `format/number.ts`
- **Create:** `packages/i18n/messages/en/{auth,catalog,search,checkout,orders,vendor,admin,events,services,supplies,directory,legal,notifications,account,ai}.json` — 15 namespace skeletons (each with 2–3 seed keys proving ICU shape, e.g. a title + one interpolated string); `common.json` already exists — extend only if a key is genuinely shared
- **Modify:** `packages/i18n/src/request.ts` — per-namespace lazy loading (load a namespace file on demand, EN fallback per namespace)
- **Create:** `packages/config/eslint-rules/no-hardcoded-strings.js` (the hardened rule — move + improve the stub logic); **Delete** `packages/i18n/eslint-no-hardcoded-strings.js` (superseded)
- **Modify:** `packages/config/eslint.config.mjs` — register the rule in the existing commented slot (**warn** severity for now; M16-P03 flips to error)
- **Create/extend tests:** `packages/i18n/src/format/money.test.ts` (move existing cases + add >1M ngwee and int-only guard), `packages/config/eslint-rules/no-hardcoded-strings.test.js` (rule fixtures)
**Guardrail: nothing else — especially not `packages/ui/**`, `packages/config/src/tailwind-preset.ts`, `supabase/**`, `.github/**`, or `pnpm-lock.yaml`.**

## 4. Implementation spec
- **`format/money.ts`:** `formatK(ngwee: number)` — integer ngwee in, `K1,234.56` out, `en-ZM` grouping. Add a dev-mode assert rejecting non-integer input (`Number.isInteger`), throwing in dev/test, coercing-with-console-error in prod. This is the ONLY money display path platform-wide.
- **Namespace skeletons:** ICU messages; every file valid JSON with ≥2 keys; naming convention documented in a top-of-file `_comment` key or a short `packages/i18n/messages/README.md` (allowed addition) stating: **one namespace file = one owning pebble per wave**.
- **Lazy loading:** `request.ts` resolves messages per namespace on demand (dynamic import or explicit loader map), falling back to EN per namespace; missing key falls back to key name (existing behavior — keep).
- **ESLint rule (hardened):** flags literal text in JSX text nodes AND literal string props for user-facing attributes (`placeholder`, `title`, `alt`, `aria-label`); ignores: non-UI packages (`services/`), test files, technical strings (className etc. — attribute allowlist approach). Rule ID `@vergeo/no-hardcoded-strings`. Registered in the preset for `apps/**` and `packages/ui/**` file globs only, severity **warn**.

## 5–8. UI/UX · Responsiveness · Performance · SEO
N/A directly. Lazy per-namespace loading is the data-frugality mechanism — verify a route loads only its namespaces (demonstrate via the loader unit test, not an app change).

## 9. Security
No secrets; formatter never logs values; rule must not execute untrusted strings (pure AST checks).

## 10. Tests (RUN before reporting)
- Money: existing 5 cases still pass from the new location + `123456789012 → K1,234,567,890.12` + non-integer input rejected in dev.
- Locale fallback: bem/nya request for a missing namespace/key falls back to EN.
- Rule fixtures: planted JSX literal flagged; `formatK` output via variable NOT flagged; `className="x"` NOT flagged; placeholder literal flagged.
- Namespace JSON: a test iterating all 16 files asserting valid JSON + ≥2 keys.
- Repo green: `pnpm lint` (expect the new rule's warns only where planted), `pnpm typecheck`, `pnpm test`, `pnpm --filter customer build`.

## 11. Acceptance criteria / DoD
- [ ] `formatK(123456)` = `K1,234.56`; int-only guard active; all formatter tests green from `format/money.ts`.
- [ ] 16 namespace files exist, valid ICU JSON, ownership convention documented.
- [ ] Rule wired into `packages/config/eslint.config.mjs` slot (warn), catches planted literal (fixture-tested), no false positive on className.
- [ ] Per-namespace lazy loading proven by test; EN fallback intact.
- [ ] `pnpm-lock.yaml` untouched; no files outside the list.

## 12. IMPLEMENTATION REPORT
When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P02 — i18n foundation & formatters (completion)
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description of the change
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the actual test/lint output incl. rule fixtures and money cases
**EXCERPTS:** full code of `format/money.ts` (money-handling logic) — nothing else
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
