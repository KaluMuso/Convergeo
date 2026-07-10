> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free (`httpx` available). **Run the FULL `uv run pytest` before reporting.**

# M14-P04 — SMS & email adapters + fallback chain

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **Outbox + adapter seam merged (M14-P01):** `adapters/base.py` = `ChannelAdapter` (Protocol `async def send(OutboxMessage) -> SendResult`), `OutboxMessage`, `SendResult`, `FailureKind`. **You implement SMS + email `ChannelAdapter`s + the fallback chain.** `notification_outbox(channel, status, attempts, next_retry_at, dedupe_key)` (0007).
- **`adapters/` is a namespace dir with NO `__init__.py`** — **add your files, do NOT create `adapters/__init__.py`** (M14-P02 adds `adapters/whatsapp.py` in parallel — avoid the add/add collision). **Do NOT touch `dispatcher.py`** (wiring = M14-P05, W11) or `templates/` (M14-P02). **The fallback references channels by the `ChannelAdapter` Protocol + channel NAME, never by importing `whatsapp.py`** (keeps you decoupled from M14-P02).
- **Adapters:** SMS = **Africa's Talking** (GSM-7 length-aware truncation with a link); email = **Resend** (receipts, KYC outcomes — HTML templates, i18n-keyed). **Fallback chain:** WhatsApp fail / no-opt-in / **undelivered-2min → SMS → email tertiary**; **per-user pref overrides** (an SMS-only user never gets a WhatsApp attempt). **Fallback decisions logged** (why SMS fired) — via structured logging / outbox `attempts`; **no new schema** (if a delivery-audit table seems needed, flag it, don't add it). OTP path (M04) uses SMS-primary — the chain applies to **lifecycle** messages.
- **Secrets from env only** (AT + Resend keys via env-name constants; no literals).
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P04.

## 2. Objective & scope

SMS (`Africa's Talking`, GSM-7 truncation + link) + email (`Resend`, i18n HTML) `ChannelAdapter`s, and the **fallback chain** (WhatsApp→SMS→email with a 2-min undelivered trigger + per-user pref overrides), with fallback decisions logged.
**Non-goals:** no WhatsApp adapter/templates (M14-P02), no dispatcher wiring (M14-P05), no schema, no OTP change (M04).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/notifications/adapters/sms.py` (Africa's Talking) · `adapters/email.py` (Resend) · `notifications/fallback.py` (the chain) · `services/api/tests/test_fallback.py`
  **Guardrail: nothing else. Do NOT create `adapters/__init__.py`, do NOT touch `dispatcher.py`/`dedupe.py`/`adapters/base.py` (import from base), `adapters/whatsapp.py`/`templates/*` (M14-P02), `main.py`, schema.**

## 4. Implementation spec

- **`sms.py`:** Africa's Talking `ChannelAdapter`; **GSM-7 length-aware truncation** (fit within a segment, append a link when truncated); error taxonomy → retryable/permanent. **`email.py`:** Resend `ChannelAdapter`; i18n-keyed HTML templates (receipts, KYC outcomes); retryable/permanent mapping.
- **`fallback.py`:** given a lifecycle message + a user's channel prefs + delivery status, resolve the next channel: **WhatsApp fail / no-opt-in / undelivered-after-2min → SMS → email (tertiary)**; **per-user pref overrides** short-circuit (SMS-only user → never a WhatsApp attempt). **Log the decision** (why the fallback fired) via structured logging / outbox attempts. Resolves adapters **by channel name via the `ChannelAdapter` Protocol** — no direct import of `whatsapp.py`.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; secrets env-only; fallback decisions logged; prefs respected; GSM-7 truncation safe; no secrets committed.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_fallback.py`: **chain decision matrix** (opt-in × pref × delivery-status → correct next channel); **2-min SLA simulation** (forced WhatsApp undelivered → SMS fires within 2min via mock + dispatcher tick); **SMS GSM-7 truncation** (over-length → truncated + link); **prefs respected** (SMS-only user never gets a WhatsApp attempt); email receipt renders. **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Forced WhatsApp failure → SMS within 2min (mock + tick); email receipts render; prefs respected (SMS-only → no WA attempt).
- [ ] Fallback decisions logged; SMS GSM-7 truncation correct; resolves adapters by channel (no `whatsapp.py` import); no new schema.
- [ ] Does NOT create `adapters/__init__.py` or touch `dispatcher.py`; secrets env-only; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M14-P04 — SMS & email adapters + fallback chain
**STATUS/FILES/DEVIATIONS** (note how fallback decisions are logged w/o new schema) **/TESTS** (paste chain-matrix + 2min-SLA + GSM-7-truncation + prefs + full-pytest tail) **/EXCERPTS** the fallback decision + GSM-7 truncation — nothing else **/QUESTIONS**
