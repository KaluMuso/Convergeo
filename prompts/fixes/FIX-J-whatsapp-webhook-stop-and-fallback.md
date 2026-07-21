> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration.** Foreground blocking calls only; run the FULL `uv run pytest` (esp. webhook + fallback tests) before reporting. **Idempotency + failure-path tests are mandatory.**

# FIX-J — WhatsApp webhook: missing STOP/START auto-reply + un-wired lifecycle SMS fallback (🟠 MED×2)

## Findings (from the 2026-07-21 docs/ops audit)

Both defects live in `services/api/app/routers/webhooks_whatsapp.py`:

1. **No STOP/START acknowledgement.** `_handle_opt_keyword` (~L183-219) writes `notif_prefs` and logs, but sends **no** confirmation message. `notification-compliance.md` §41/§46 promise an auto-reply, and Meta expects a STOP acknowledgement. The i18n copy already exists — `notifications.compliance.stopConfirmation` / `startConfirmation` — but is unreferenced in the API.
2. **Lifecycle SMS fallback never fires.** The delivery-status handler (~L127-161) only rewrites the outbox row to `status=failed` on `message_status=failed`/`undelivered`. The fallback path exists — `services/api/app/services/notifications/fallback.py::evaluate_lifecycle_fallback` (~L348) + `resolve_fallback_channel` (~L186) + `WHATSAPP_UNDELIVERED_2MIN` — but has **zero callers**, so a template Graph accepted (HTTP 200) that later reports failed/undelivered never falls back to SMS. (SMS fallback today only fires on a _synchronous_ send failure in the dispatcher.)

## Required fix

1. **STOP/START ack:** in `_handle_opt_keyword`, after updating `notif_prefs`, enqueue exactly one confirmation notification (outbox row) using the existing `compliance.stopConfirmation` / `startConfirmation` keys, localized from the profile locale. It rides the normal dispatch drain. Must be idempotent per inbound message id (a duplicate inbound webhook must not enqueue twice).
2. **Wire lifecycle fallback:** in the delivery-status handler, when `message_status` is `failed`/`undelivered`, invoke `evaluate_lifecycle_fallback` → `enqueue_fallback_row` (SMS) for the affected outbox row. Idempotent — a webhook retry for the same (message id, status) must not enqueue a second fallback.

## Files (ONLY)

- Modify `services/api/app/routers/webhooks_whatsapp.py`
- Modify `services/api/app/services/notifications/fallback.py` **only if** a thin entry-point/helper is needed (prefer calling the existing functions)
- Extend `services/api/tests/test_webhooks*.py` / the whatsapp webhook test file
- **Do NOT touch** `dispatcher.py` or `internal_n8n.py` (FIX-I owns those), or `db.ts`.

## Tests (RUN — idempotency required)

- A `failed`/`undelivered` delivery-status webhook enqueues **exactly one** SMS fallback row; a duplicate webhook enqueues none; a `delivered` webhook enqueues none.
- A STOP inbound enqueues exactly one `stopConfirmation`; START enqueues exactly one `startConfirmation`; a duplicate inbound does not double-enqueue.
- **Full `uv run pytest`** + `ruff` + `mypy`.

## Report

STATUS / FILES / DEVIATIONS / TESTS (paste the idempotency assertions for both paths + full-pytest tail) / EXCERPT the status-handler fallback call + the ack enqueue / QUESTIONS.
