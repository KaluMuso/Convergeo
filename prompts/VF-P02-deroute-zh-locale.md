> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P02 — De-route `zh` from the public locale switcher `[CODE]`

## 1. Context
**Wave 5.** Source: `01-audit-findings.md` §2 cross-cutting; **NB-1**. **Live:** `LOCALES = [en, bem, nya, fr, zh]` and `zh` (Chinese) is **fully translated (17 namespaces)** and routable — but Chinese is **not a stated market language** (D27 order is EN → Bemba/Nyanja → French). It functions as a full-fidelity QA/pseudo locale. Until a market decision (NB-1), it should not sit in the public switcher.
**Type:** `[CODE]`.

## 2. Objective & scope
Keep `zh` building (QA fidelity) but remove it from the **public** locale switcher; public options = EN, FR, + `bem`/`nya` (once VF-P01 lands).
**Non-goals:** deleting `zh` messages; changing route resolution (keep `zh` resolvable for QA/deep links, just not offered in the switcher).

## 3. Files (edit ONLY these)
- `packages/i18n/src/locales.ts` (introduce/adjust a `PUBLIC_LOCALES` list distinct from routable `LOCALES`)
- the shared locale-switcher component (single file under `packages/ui` or the customer app shell that renders the switcher)
**Guardrail: do NOT edit message files (VF-P01 owns those) or the middleware matcher (keep `zh` routable).**

## 4. Implementation spec
- Add `PUBLIC_LOCALES` (en, fr, bem, nya) and drive the switcher from it; keep `LOCALES` (incl. `zh`) for routing/QA.
- Ensure no route 404s for `zh` (still resolvable); the switcher simply omits it.

## 10. Tests (RUN before reporting)
- Switcher renders only public locales; `zh` absent.
- `/zh/...` still resolves (no 404); i18n-lint green.
- `pnpm typecheck` clean.

## 11. Acceptance criteria / DoD (NB-1)
- [ ] `zh` omitted from the public switcher; EN/FR (+bem/nya) shown.
- [ ] `zh` still resolvable for QA; no 404s.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P02 — De-route `zh` from the public locale switcher
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste switcher render + `zh` route probe + typecheck · **EXCERPTS:** the `PUBLIC_LOCALES` change · **QUESTIONS:** the NB-1 market decision on Chinese
