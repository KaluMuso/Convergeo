> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** No migration. Foreground blocking only; run the FULL `uv run pytest` before reporting.

# FIX-K — Event cancellation / schedule-change notifications are placeholders (M14 TODO)

## Finding

`services/api/app/services/events/cancellation.py:29,153` and `routers/organiser_events.py:581` carry `TODO(M14)`: when an organiser cancels an event or changes its schedule, the outbox row is enqueued with a **`"todo"` placeholder template token** instead of a real notification template. So affected ticket-holders are not properly notified on cancel/reschedule — a real lifecycle gap. (Live WhatsApp send additionally needs founder gate **F5**, but the template mapping + outbox enqueue is code and fully testable via the outbox, independent of F5.)

## Required fix

- Add real notification templates `event_cancelled` and `event_schedule_changed` to the notification template registry / dispatcher mapping, following the shape of the existing lifecycle templates (grep for how e.g. `order_*` / `ticket_*` events map to templates + i18n keys + channel routing). Include the localized message keys under the `notifications` namespace (per-namespace i18n file; **EN only in this pebble** — the vernacular fill is a separate i18n task).
- Replace the `"todo"` token at `cancellation.py` and `organiser_events.py:581` with the real template keys, passing the event/instance/refund context the templates need (event title, date, refund status).
- Keep the enqueue idempotent and outbox-mediated exactly like other lifecycle notifications (WhatsApp → SMS → email fallback via the shared dispatcher; no direct send).

## Files (ONLY)

- Modify `services/api/app/services/events/cancellation.py`
- Modify `services/api/app/routers/organiser_events.py` (the `:581` emit site only — no other route changes)
- Modify the notification template registry module (the one mapping event keys → templates; grep `event_cancelled`/dispatcher)
- Add `packages/i18n/messages/en/notifications.json` keys for the two new templates (append-only, EN)
- Add/extend `services/api/tests/test_event_cancellation.py` (or the existing events-notification test)
- **Do NOT touch** returns/*, kyc/*, other routers, migrations, `db.ts`, non-EN i18n files.

## Tests (RUN)

Cancelling an event enqueues an outbox row whose template key is `event_cancelled` (**not** `"todo"`) with the expected context; a schedule change enqueues `event_schedule_changed`. Dedupe/idempotency holds (one row per holder per event). **Full `uv run pytest`** + ruff + mypy.

## Report

STATUS / FILES / DEVIATIONS (where the template mapping lives; what context you passed) / TESTS (paste the outbox-carries-real-template assertions + full-pytest tail) / EXCERPTS (the mapping + the replaced emit sites) / QUESTIONS.
