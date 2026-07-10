> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M14-P07 — Template i18n & compliance pass

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **Notification adapters/templates MERGED (M14-P01…P05):** WhatsApp/SMS/email adapters, outbox dispatcher, `emit_event`/`EVENT_REGISTRY`, template rendering with slots (`to`, `pickup_details`, etc.). **You key all message bodies into `notifications.json`** and ensure adapters render from keys — **no hardcoded strings in adapters** (lint-enforced).
- **i18n structure:** `packages/i18n/messages/en/notifications.json` exists; namespaces registered in `packages/i18n/src/request.ts` (`notifications`). **Bemba/Nyanja** = `messages/bem/notifications.json` + `messages/nya/notifications.json` — **structure + EN-fallback markers** (not full translations). If `bem`/`nya` locales aren't registered, check `locales.ts` — **register only if the fallback plumbing already supports it; otherwise ship EN-keyed + documented fallback markers** (note in report).
- **Locale resolution per recipient pref** (the dispatcher already injects `locale` from `profiles.notif_prefs`/`locale` — M14-P05). **Transactional vs marketing** classification: **quiet hours 21:00–07:00 apply to MARKETING only**; transactional always sends. Consent audit points documented.
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P07. **You solely own `notifications.json` + bem/nya + the compliance doc this wave.**

## 2. Objective & scope

Template i18n + compliance pass: every notification body keyed in `notifications.json` (EN) with **bem/nya structure + EN-fallback markers**, locale resolution per recipient pref, **transactional/marketing classification** with **quiet-hours (21:00–07:00) enforced on marketing only**, consent/STOP/quiet-hours policy documented. No hardcoded strings in adapters.
**Non-goals:** no new channels/adapters (M14-P01…P05 merged), no new events, no live Meta send (F5-gated).

## 3. Files (create/modify ONLY these)

- **Create:** `packages/i18n/messages/bem/notifications.json` · `packages/i18n/messages/nya/notifications.json` · `services/api/tests/test_notification_i18n.py` · `docs/ops/notification-compliance.md` (STOP wording, consent points, quiet-hours policy)
- **Modify:** `packages/i18n/messages/en/notifications.json` (key ALL message bodies) · notification classification/quiet-hours in the **merged dispatcher** ONLY if a classification hook is missing (**minimal, sole editor of that seam this wave**; if the dispatcher already classifies, add keys only)
  **Guardrail: nothing else. Do NOT touch adapters' send logic (M14-P02…P05), `EVENT_REGISTRY`/`emit_event` (M14-P05), other locale namespaces, `main.py`, schema/db.ts. No migration.**

## 4. Implementation spec

- **`notifications.json` (EN):** every template body keyed (ICU, slots preserved); adapters render from keys (verify none hardcode). **bem/nya:** mirror the key structure with EN-fallback markers (e.g. `"__fallback": "en"` or EN text + marker) so resolution degrades cleanly.
- **Classification + quiet hours:** each template tagged `transactional | marketing`; a `should_send_now(template_class, now, tz)` gate → marketing suppressed 21:00–07:00 (deferred, not dropped), transactional always. Wire at the dispatcher's enqueue/send boundary (minimal edit if a hook is absent).
- **`notification-compliance.md`:** STOP/opt-out wording, consent capture points, quiet-hours policy, transactional vs marketing definitions.

## 5–9. Security etc.

No hardcoded user-facing strings in adapters (lint); locale per recipient pref; quiet-hours on marketing only; consent/STOP documented; no secrets.

## 10. Tests (RUN before reporting)

`test_notification_i18n.py`: **locale fallback matrix** (every template resolves EN; bem/nya fall back correctly via markers); **quiet-hours boundary** (marketing at 20:59 vs 21:00 vs 06:59 vs 07:00; transactional always sends); **classification correctness** (each template's class). Assert `messages.test` still passes (files == NAMESPACES). `pnpm typecheck`, `pnpm lint` (**no hardcoded strings**), `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Every template resolves in EN + falls back correctly for bem/nya placeholders; quiet-hours enforced on marketing class; no hardcoded strings in adapters (lint).
- [ ] bem/nya files + compliance doc created; classification correct; i18n message test green; full suite + lint green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M14-P07 — Template i18n & compliance pass
**STATUS/FILES/DEVIATIONS** (whether bem/nya locales were registered or EN-fallback-only; where classification/quiet-hours wired; any adapter still hardcoding) **/TESTS** (paste locale-fallback + quiet-hours-boundary + classification + full-pytest tail) **/EXCERPTS** the quiet-hours gate + a keyed template — nothing else **/QUESTIONS**
