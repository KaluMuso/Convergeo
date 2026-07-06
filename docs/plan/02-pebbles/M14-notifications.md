# M14 — Notifications & Automation — Pebbles

7 pebbles. Outbox pattern (table from M03-P06): at-least-once dispatch + dedupe keys = effectively-once per event. Channel chain: WhatsApp → SMS fallback → email tertiary, honoring per-user prefs (M04-P05). Setup guide: `docs/ops/whatsapp-cloud-api-setup.md`. ⚠ Live sends gated on founder action F5 (Meta setup) — all pebbles fully testable against mocks/test numbers.

---

### M14-P01 — Outbox dispatcher & channel adapter interface `L`
**Deps:** M03-P06 · **Files:** `services/api/app/services/notifications/dispatcher.py` (poll pending → resolve channel per prefs+template → adapter send → mark sent/failed + retry backoff, dead-letter after N), `notifications/adapters/base.py` (adapter protocol), `notifications/dedupe.py` (**dedupe_key = event type + entity id + channel** — unique constraint honored), `app/routers/internal_dispatch.py` (cron tick), `infra/n8n/notification-dispatch.json`, `services/api/tests/test_dispatcher.py`
At-least-once with idempotent send guard; per-channel rate pacing; failure taxonomy (retryable vs permanent).
**AC:** M14 success criterion: exactly-once per event per channel under re-run/crash-mid-batch (dedupe tested); dead-letters visible to admin; dispatcher lag <2min at cron cadence.
**Tests:** crash-mid-batch replay, dedupe collision, backoff schedule, permanent-failure routing.

### M14-P02 — WhatsApp Cloud API client & templates `L`
**Deps:** P01 · **Files:** `services/api/app/services/notifications/adapters/whatsapp.py` (Cloud API client: template sends, media-less v1, per-number token config), `notifications/templates/whatsapp.py` (registry: **order_confirmed, payment_received, order_shipped, order_ready_pickup, order_delivered, vendor_new_order, otp_login** — variable mapping, i18n-slot aware), `docs/ops/whatsapp-templates.md` (exact template bodies for Meta submission incl. Bemba/Nyanja slots), `services/api/tests/test_whatsapp_adapter.py`
Templates carry the trust narrative ("Your K__ is held safely by Vergeo5 until delivery"); money vars formatted via formatK-equivalent server-side; doc ready for F5-day submission.
**AC:** each template renders with fixture vars (ngwee-correct); API errors mapped to retryable/permanent; test-number E2E documented.
**Tests:** template variable mapping per template, error taxonomy, payload contract vs Cloud API spec.

### M14-P03 — WhatsApp webhook & opt-in/STOP `M`
**Deps:** P02 · **Files:** `services/api/app/routers/webhooks_whatsapp.py` (verify token handshake + signature; delivery/read status → outbox record updates; **inbound STOP/START handling → prefs update across ALL channels for STOP**), `services/api/tests/test_wa_webhook.py`
Quality-safety: STOP honored instantly (Meta quality rating protection); status callbacks close the delivery loop (drives SMS fallback decision in P04); unknown inbound → support log (M13-P10 visibility).
**AC:** M14 success criterion: STOP honored across channels; forged webhook rejected; status updates idempotent.
**Tests:** STOP/START flows, signature verify, duplicate status events, unknown-sender handling.

### M14-P04 — SMS & email adapters + fallback chain `M`
**Deps:** P01 · **Files:** `services/api/app/services/notifications/adapters/sms.py` (Africa's Talking; GSM-7 length-aware truncation w/ link), `adapters/email.py` (Resend: receipts, KYC outcomes — HTML templates i18n-keyed), `notifications/fallback.py` (**chain: WhatsApp fail/no-opt-in/undelivered-2min → SMS → email tertiary**; per-user pref overrides), `services/api/tests/test_fallback.py`
Fallback decisions logged (why SMS fired); OTP path (M04) uses fastest-available (SMS primary for OTP per M04-P01 — chain applies to lifecycle messages).
**AC:** M14 success criterion: forced WhatsApp failure → SMS within 2min (tested via mock + dispatcher tick); email receipts render; prefs respected (SMS-only user never gets WA attempt).
**Tests:** chain decision matrix (opt-in × pref × delivery status), 2min SLA simulation, SMS truncation.

### M14-P05 — Lifecycle event wiring `M`
**Deps:** P01, M08-P04, M09-P01 · **Files:** `services/api/app/services/notifications/events.py` (**single mapping: domain event → template + audience + channel policy** for: order placed/confirmed/shipped/ready/delivered/completed, payment received/failed, payout sent/failed, KYC approved/rejected, dispute opened/resolved, ticket issued/transferred, quote received/accepted), enqueue calls added in domain event emitters (`app/services/*/events.py` files — **new files only, no shared-file edits**), `services/api/tests/test_event_wiring.py`
One registry = auditable coverage; vendor vs customer audiences separated; each event → outbox rows with dedupe keys.
**AC:** M14 success criterion: full order lifecycle fires correct messages exactly once each (fixture run through state machine); no event without mapping (coverage test vs state-machine transition list).
**Tests:** lifecycle fixture sweep, audience routing, coverage completeness.

### M14-P06 — n8n operational workflows `M`
**Deps:** P01, M13-P09 data · **Files:** `infra/n8n/` (`kyc-nudge.json` — 48h stalled applications; `payout-failure-alert.json` → founder WhatsApp; `low-stock-alert.json` → vendor; `review-request.json` — post-completion +24h; `abandoned-cart.json` — **flag-gated OFF**), `services/api/app/routers/internal_n8n.py` (data endpoints these workflows call, internal-token), `docs/ops/n8n-workflows.md` updates (**same file as M13-P11 — different wave**)
Workflows call API endpoints (logic stays in API; n8n = scheduling/glue only — solo-ops maintainability).
**AC:** each workflow importable + runs against staging; abandoned-cart inert while flag off; failure alert fires on injected payout failure.
**Tests:** endpoint tests per workflow data source, flag gating, alert payloads.

### M14-P07 — Template i18n & compliance pass `S`
**Deps:** P02–P05 · **Files:** `packages/i18n/messages/en/notifications.json` (all message bodies keyed), Bemba/Nyanja slot files `messages/bem/notifications.json` + `messages/nya/notifications.json` (structure + EN-fallback markers), `services/api/tests/test_notification_i18n.py`, `docs/ops/notification-compliance.md` (STOP wording, consent points, quiet hours policy 21:00–07:00 for non-transactional)
Locale resolution per recipient pref; transactional vs marketing classification (quiet hours apply to marketing only); consent audit trail points documented.
**AC:** every template resolves in EN + falls back correctly for bem/nya placeholders; quiet-hours enforcement on marketing class; no hardcoded strings in adapters (lint).
**Tests:** locale fallback matrix, quiet-hours boundary, classification correctness.
