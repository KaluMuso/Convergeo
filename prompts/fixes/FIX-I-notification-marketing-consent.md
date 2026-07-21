> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration** (reuses `profiles.notif_prefs`). Foreground blocking calls only; run the FULL `uv run pytest` (esp. the notification + dispatch tests) before reporting. **Failure-path tests are mandatory** (consent/opt-out logic).

# FIX-I — STOP does not actually suppress marketing at enqueue or dispatch (🔴 HIGH — Meta quality + Zambia DPA)

## Finding (from the 2026-07-21 docs/ops audit)

`docs/ops/notification-compliance.md` promises: STOP suppresses **marketing**, **transactional** still sends. Neither layer enforces it:

- **Enqueue never reads consent.** `services/api/app/routers/internal_n8n.py::_load_profiles` (~L114) selects only `id, phone, locale, display_name`; `_enqueue_items` (~L439) enqueues unconditionally. Marketing nudges (`review_request`, `kyc_nudge`, `abandoned_cart_recovery`) are created even for users who replied STOP.
- **Dispatch never gates on consent.** `services/api/app/services/notifications/dispatcher.py::resolve_channel` (~L175-190) returns the requested channel even when **all** channels are disabled (final `return requested_channel` at ~L190). STOP writes `notif_prefs={whatsapp:false,sms:false,email:false}`, so a marketing row still sends. Transactional survival today is an *accidental* side effect of the same fall-through.

## Required fix (class-aware — no schema change)

Reuse the existing `TEMPLATE_CLASSIFICATION` map (`dispatcher.py` ~L51-78) as the marketing-vs-transactional oracle.

1. **Dispatch gate (`dispatcher.py`):** in `_process_row`, after `resolve_channel`, if the template is **marketing** AND the resolved channel is disabled in `notif_prefs`, **suppress** the row (mark it a terminal `suppressed`/`skipped` state — not `failed`, not retried) and do not send. If the template is **transactional**, keep current behavior (still sends). Keep quiet-hours handling unchanged.
2. **Enqueue filter (`internal_n8n.py`):** have `_load_profiles` also select `notif_prefs`; in the marketing nudge paths, skip recipients whose relevant channel(s) are all disabled. Do NOT filter transactional enqueue.
3. Add a small shared helper (e.g. `is_channel_enabled(notif_prefs, channel)` if not already present) and a `is_marketing(template)` lookup so both layers use one source of truth.

_Note: the STOP/START inbound auto-reply acknowledgement is handled separately in **FIX-J** (it owns `webhooks_whatsapp.py`), so this pebble does NOT touch that file._

## Files (ONLY)

- Modify `services/api/app/services/notifications/dispatcher.py`
- Modify `services/api/app/routers/internal_n8n.py`
- Extend `services/api/tests/test_notifications*.py` / the dispatch test file (add a new test module if cleaner)
- **Do NOT touch** `webhooks_whatsapp.py` (FIX-J owns it), `fallback.py`, or `db.ts`.

## Tests (RUN — failure-path required)

- A user with `notif_prefs` all-false: a **marketing** outbox row is **suppressed** (terminal, not retried); a **transactional** row (e.g. `order_confirmed`, `otp_login`) still sends.
- Enqueue skips opted-out recipients for a marketing nudge but not for a transactional event.
- A user with only WhatsApp disabled: marketing falls back to an enabled channel (SMS/email) per existing fallback order; fully-opted-out → suppressed.
- **Full `uv run pytest`** + `ruff` + `mypy`.

## Report

STATUS / FILES / DEVIATIONS (the suppressed terminal state name; the class oracle) / TESTS (paste the marketing-suppressed vs transactional-sent assertions + full-pytest tail) / EXCERPT the `_process_row` gate + the enqueue filter / QUESTIONS.
