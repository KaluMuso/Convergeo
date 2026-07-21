> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the assigned namespace files.** **⚙ do NOT use `git stash`.** **No migration.** Run `pnpm --filter @vergeo/i18n test` + `node scripts/ci/i18n-lint.mjs` before reporting.

# CCP-03f — Bemba/Nyanja `vendor` + `ai` namespaces

## Findings (from `docs/production-readiness/2026-07-20/code-completion-programme.md` CCP-03 + reconciliation R-3)

- bem/nya are at **13/17**; missing `admin`, `ai`, `legal`, `vendor`.
- **Founder scope (default):** fill `vendor` (Zambian sellers) + `ai` now; keep `admin` EN-only (internal single-admin surface); **hold `legal`** for native-speaker sign-off (companion `CCP-03d`, gated on CCP-02 / D27). Runtime EN deep-merge (`packages/i18n/src/request.ts`) already renders English for any gap, so partial is honest.

## Required fix

Create `packages/i18n/messages/{bem,nya}/vendor.json` and `{bem,nya}/ai.json` at full key-parity with the EN namespace. Preserve every ICU placeholder exactly. Any money/payout string in `vendor.json` gets a review tag. Do **not** edit EN as source-of-truth (except a genuine key bug), do **not** add `admin`/`legal`, and do **not** claim native accuracy in the PR body.

## Files (ONLY)

- `packages/i18n/messages/bem/vendor.json`, `packages/i18n/messages/nya/vendor.json`
- `packages/i18n/messages/bem/ai.json`, `packages/i18n/messages/nya/ai.json`

## Tests (RUN)

`pnpm --filter @vergeo/i18n test`; `node scripts/ci/i18n-lint.mjs`; phase1-critical stays green; assert key-parity with EN for the two namespaces.

## Report

STATUS/FILES/DEVIATIONS/TESTS/EXCERPTS/QUESTIONS.

---

**Companion (HELD — do not open until CCP-02 native-review sign-off):** `CCP-03d-nya-bem-legal-placeholders` — ship `{bem,nya}/legal.json` only as clearly-marked `PENDING_NATIVE_REVIEW` placeholders; never index or claim native accuracy for legal/escrow/consent copy (D27). `admin` stays EN-only unless the founder reverses.
