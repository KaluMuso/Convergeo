> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P01 — Bemba / Nyanja translations `[CODE]`

## 1. Context
**Wave 5.** Source: `01-audit-findings.md` BG-1; `docs/plan/i18n-audit.md`; D27; `release-gates.md` G18. **Live:** `packages/i18n/messages/bem/` and `nya/` contain **only `notifications.json`** (1 of 17 namespaces); the UI falls back to EN for everything else — so the vision-priority vernaculars are effectively untranslated, while `en`/`fr`/`zh` are full (17). The admin `TranslatorView` (`apps/admin/.../translations`) exists to author these.
**Type:** `[CODE]` — but translations must be **human-reviewed** (Bemba/Nyanja quality), not machine-dumped.

## 2. Objective & scope
Fill all 16 missing `bem` + `nya` namespaces with reviewed, ICU-valid strings so core customer flows render in vernacular.
**Non-goals:** the `zh` de-route (VF-P02); adding Tonga/Lozi (later per D27).

## 3. Files (create ONLY these)
- `packages/i18n/messages/bem/*.json` (16 namespaces mirroring `en/`)
- `packages/i18n/messages/nya/*.json` (16 namespaces)
**Guardrail: touch ONLY these locale message files; keys must mirror `en/` exactly (no added/removed keys).**

## 4. Implementation spec
- For each `en/{namespace}.json`, produce a `bem/` and `nya/` counterpart with the same key set, valid ICU messages, locale-aware plurals/gender where ICU requires, and correct ZMW/date placeholders.
- Prioritise core buyer flows (home, catalog, PDP, cart, checkout, account, common) for review quality; keep terminology consistent with the `notifications.json` already present.

## 9. Security / correctness
- No hardcoded strings introduced; no key drift vs `en` (the i18n-lint missing-key diff must be clean).

## 10. Tests (RUN before reporting)
- `pnpm --filter i18n test` / `node scripts/ci/i18n-lint.mjs` — no missing/extra keys for `bem`/`nya`; pseudo-locale + ICU parse clean.
- Spot-render core customer routes with `bem`/`nya` active → no `MISSING_MESSAGE`, no EN leakage on core flows.

## 11. Acceptance criteria / DoD (G18)
- [ ] 16 `bem` + 16 `nya` namespaces complete; key sets mirror `en`.
- [ ] i18n-lint green; ICU valid; core flows render vernacular.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P01 — Bemba / Nyanja translations
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** any namespace left EN-fallback + why · **TESTS:** paste i18n-lint output · **EXCERPTS:** none · **QUESTIONS:** review-source for the vernacular strings
