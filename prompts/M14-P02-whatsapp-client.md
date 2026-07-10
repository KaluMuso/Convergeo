> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free (`httpx` available). **Run the FULL `uv run pytest` before reporting.**

# M14-P02 — WhatsApp Cloud API client & templates

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **Outbox + adapter seam merged (M14-P01):** `app/services/notifications/{dispatcher.py, dedupe.py}` + **`adapters/base.py`** which defines `ChannelAdapter` (Protocol: `async def send(message: OutboxMessage) -> SendResult`), `OutboxMessage`, `SendResult`, `FailureKind`, `NoopAdapter`. **You implement a WhatsApp `ChannelAdapter`.** `notification_outbox(channel in ('whatsapp','sms','email'), template, payload jsonb, status, attempts, next_retry_at, dedupe_key)` (0007). **Official WhatsApp Cloud API ONLY (WAHA forbidden — D-lock).**
- **`adapters/` is a namespace dir with NO `__init__.py`** (only `base.py`) — **add your file, do NOT create `adapters/__init__.py`** (M14-P04 adds sibling adapters in parallel — avoid the add/add collision). **`templates/` is NEW and yours alone this wave** — create it with a `templates/__init__.py`. **Do NOT edit `dispatcher.py`** (adapter registration/wiring = M14-P05, W11) — ship the adapter + template registry standalone.
- **Money vars formatted server-side** (formatK-equivalent: `ngwee` → `K1,234.56`) — reuse `app.services.payments.money`/`app.schemas.base` for the ngwee→display; **no float**. Templates carry the trust narrative ("Your K__ is held safely by Vergeo5 until delivery"). i18n-slot aware (EN + Bemba/Nyanja slots).
- **Secrets from env only** — per-number token config via env-name constants; no literals.
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P02. **Webhook/opt-in/STOP = M14-P03 (not this wave).**

## 2. Objective & scope

A WhatsApp Cloud API `ChannelAdapter` (template sends, per-number token config) + a template registry (**order_confirmed, payment_received, order_shipped, order_ready_pickup, order_delivered, vendor_new_order, otp_login** with variable mapping, i18n-slot aware) + `docs/ops/whatsapp-templates.md` (exact bodies for Meta submission incl. Bemba/Nyanja slots).
**Non-goals:** no webhook/opt-in (M14-P03), no SMS/email/fallback (M14-P04), no dispatcher wiring (M14-P05), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/notifications/adapters/whatsapp.py` (Cloud API `ChannelAdapter`) · `notifications/templates/__init__.py` · `notifications/templates/whatsapp.py` (the 7-template registry) · `docs/ops/whatsapp-templates.md` · `services/api/tests/test_whatsapp_adapter.py`
  **Guardrail: nothing else. Do NOT create `adapters/__init__.py`, do NOT touch `dispatcher.py`/`dedupe.py`/`adapters/base.py` (import from base), `adapters/sms.py`/`email.py`/`fallback.py` (M14-P04), `main.py`, schema.**

## 4. Implementation spec

- **`whatsapp.py`:** implements `ChannelAdapter.send` for the WhatsApp Cloud API (template message payloads; per-number token from env). **Error taxonomy → retryable vs permanent** (`FailureKind`): rate-limit/5xx = retryable, invalid-template/blocked-number = permanent. Payload contract matches the Cloud API spec. **No media (v1).**
- **`templates/whatsapp.py`:** a registry mapping each of the 7 events to a template id + variable mapping from the outbox `payload`; **money vars rendered `K1,234.56` server-side from ngwee** (no float); i18n-slot aware (variable positions carry the localized body per EN/Bemba/Nyanja). Trust-narrative copy where applicable.
- **`docs/ops/whatsapp-templates.md`:** the exact template bodies (with variable placeholders + Bemba/Nyanja translations) ready for **Meta submission on F5-day**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; official Cloud API only (no WAHA); secrets env-only; money vars ngwee-exact (no float); error taxonomy retryable/permanent; no secrets committed.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_whatsapp_adapter.py`: **template variable mapping per template** (each of the 7 renders with fixture vars, money vars ngwee-correct `K1,234.56`); **error taxonomy** (rate-limit→retryable, invalid-template→permanent); **payload contract vs Cloud API spec** (respx/mock). **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Each of the 7 templates renders with fixture vars (money ngwee-correct); API errors mapped retryable/permanent; payload matches Cloud API.
- [ ] Official Cloud API only; secrets env-only; does NOT create `adapters/__init__.py` or touch `dispatcher.py`; `docs/ops/whatsapp-templates.md` ready for F5 submission; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M14-P02 — WhatsApp Cloud API client & templates
**STATUS/FILES/DEVIATIONS/TESTS** (paste template-mapping + error-taxonomy + full-pytest tail) **/EXCERPTS** one template's variable mapping (money ngwee→K) + the send error-taxonomy — nothing else **/QUESTIONS**
