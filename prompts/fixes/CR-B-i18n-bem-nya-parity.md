> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the `bem/` and `nya/` message files below.** i18n messages are per-namespace files — touch only the namespaces this prompt assigns. **This prompt requires a Bemba/Nyanja speaker or reviewer — do NOT machine-translate and ship unreviewed.** Run `pnpm --filter @vergeo/i18n test` + the i18n lint (`node scripts/ci/i18n-lint.mjs`) before reporting.

# CR-B — Bring Bemba & Nyanja to customer-facing parity (D27)

## Finding

`packages/i18n/messages/`: `en`, `fr`, and `zh` each have **17 namespaces (complete)**; `bem` and `nya` have **13** — each missing **`ai`, `legal`, `vendor`, `admin`**. **D27 ranks Bemba/Nyanja AHEAD of French**, yet French (and a non-public `zh`) were completed first. Missing keys fall back to English by design (`packages/i18n/src/deep-merge.ts`), so nothing breaks — but Bemba/Nyanja users see English on **Ask Vergeo (`ai`)** and **legal** pages. This is the mandated launch-language work, unfinished.

## Required fix (customer-facing scope — default)

- Add `packages/i18n/messages/bem/ai.json` and `packages/i18n/messages/nya/ai.json` — full, human-reviewed Bemba/Nyanja translations mirroring the **exact key structure** of `en/ai.json` (all keys present; ICU placeholders/`{amount}`/`<tags>` preserved verbatim; do not translate placeholder names).
- Fill any customer-visible gaps in the already-present bem/nya namespaces if the i18n test surfaces missing keys vs `en` (e.g. `events`, `notifications`).
- **`legal` is intentionally EXCLUDED here** — legal copy in local languages is a liability decision. Leave `legal` to fall back to English until a founder+counsel decision (track as a follow-up). Do **not** add `bem/legal.json` or `nya/legal.json` in this pebble.
- **`vendor`/`admin` are operator-facing and out of scope** for this customer-parity pebble.

## Files (ONLY)

- Add `packages/i18n/messages/bem/ai.json`, `packages/i18n/messages/nya/ai.json`
- Optionally modify `packages/i18n/messages/bem/{events,notifications}.json`, `packages/i18n/messages/nya/{events,notifications}.json` **only** to add keys the i18n test reports as missing vs `en` (no restructuring)
- **Do NOT touch** `en/*`, `fr/*`, `zh/*`, `legal.json`, `vendor.json`, `admin.json`, `locales.ts`, or any app code.

## Tests (RUN)

- `pnpm --filter @vergeo/i18n test` — the pseudo-locale/parity test must confirm bem/nya `ai` keys match `en` structurally (no missing, no extra).
- `node scripts/ci/i18n-lint.mjs` — clean.
- Manual: render `/bem/ask` and `/nya/ask` — no bare un-bracketed English strings in translated areas.

## Report

STATUS / FILES / DEVIATIONS / TESTS (paste parity-test + i18n-lint output) / EXCERPTS (a few representative translated keys with the EN source beside them) / QUESTIONS (flag any `ai` string whose meaning was ambiguous to translate).
