> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P18 — Real Bemba and Nyanja content `[CODE+HUMAN]`

## 1. Context
**Wave W6.** Closes VF-P01 / G18.

Measured 2026-08-01: `packages/i18n/messages/en/` holds **19** namespace files; `bem` and `nya` hold **16** each; `fr` holds 18. The runtime deep-merge in `packages/i18n/src/request.ts` falls back to English per key, so a missing vernacular key renders **English, never a raw key path** — the product is not broken, it is partly untranslated. `PUBLIC_LOCALES` is `["en","bem","nya","fr"]` (VF-P02 closed; `zh` is retained for QA only).

Machine translation is not sufficient here. Bemba and Nyanja commerce vocabulary — escrow, refund, tier pricing, dispute, pickup, COD — is where a literal translation stops meaning anything, and a customer who cannot understand "your money is held until you confirm delivery" will not complete the flow that the entire trust model depends on.

**Type:** `[CODE+HUMAN]` — an agent prepares and wires; a **human speaker reviews before merge**.

## 2. Objective & scope
`bem` and `nya` reach namespace parity with `en`, human-reviewed on the trust-critical paths.
**Non-goals:** new copy in English; adding a locale; translating admin-only surfaces (record if deliberately deferred).

## 3. Files (edit ONLY these)
- `packages/i18n/messages/bem/*.json`, `packages/i18n/messages/nya/*.json`
- `docs/plan/i18n-audit.md` — record coverage before/after and who reviewed
- Tests / the i18n lint

## 4. Implementation spec
- Identify the 3 missing namespaces per locale by diffing against `en` (known gaps historically: `admin`, `ai`, `legal`, `vendor` — verify, do not assume).
- Fill **every key**, preserving ICU plurals, placeholders and ordering. A dropped `{count}` is a runtime break, not a copy issue.
- **Priority for human review**, in this order: escrow/trust copy, checkout and payment, COD, dispute/refund, KYC, delivery/pickup, OTP. These are the strings where a wrong word costs money or trust.
- Keep the fallback intact — never ship a placeholder string like `TODO` that would render to a customer. If a key cannot be translated confidently, **leave it absent** so the English fallback shows: an honest English string beats a confident wrong one.
- Record the reviewer's name/role in `i18n-audit.md`.

## 5. Security / conventions
No hardcoded strings anywhere in the apps; i18n-lint is blocking in CI. Locale-aware ZMW/date/number formatting is unchanged by this pebble.

## 10. Tests (RUN before reporting)
- `node scripts/ci/i18n-lint.mjs` green.
- A test asserting `bem`/`nya` namespace count equals `en`'s.
- A placeholder-parity test: every key's ICU placeholders match `en`'s exactly.
- Render the checkout, escrow-status and dispute screens in both locales at 360px and confirm no overflow or truncation — vernacular strings are frequently longer than English and this is where layout breaks.
- `pnpm lint typecheck test build`.

## 11. Acceptance criteria / DoD
- [ ] `bem` and `nya` at namespace parity with `en`.
- [ ] Placeholder/plural parity proven by test.
- [ ] Trust-critical copy human-reviewed; reviewer recorded.
- [ ] No `TODO`/placeholder strings reachable by a customer.
- [ ] No 360px layout breakage in either locale.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P18 — Bemba/Nyanja content
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the parity tests + 360px screenshots · **EXCERPTS:** a trust-critical string in all three languages · **QUESTIONS:** name who reviewed
