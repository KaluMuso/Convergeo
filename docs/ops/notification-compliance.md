# Notification compliance — Vergeo5

Operational policy for WhatsApp, SMS, and email notifications. Applies to all channels dispatched via `notification_outbox` (M14-P01) and rendered from `packages/i18n/messages/*/notifications.json`.

## Transactional vs marketing

| Class             | Definition                                                                                                                                              | Quiet hours                                                                                                                                                                                                              | Examples                                                                                                                                                                  |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Transactional** | Required for contract performance, authentication, or time-sensitive order/payment/vendor ops. User expects these regardless of marketing prefs timing. | **Never deferred** — send immediately when the dispatcher picks up the row.                                                                                                                                              | Order confirmed/shipped/delivered, payment received, OTP login, vendor new order, email receipts, KYC outcomes, payout-failure alert (founder), low-stock alert (vendor). |
| **Marketing**     | Engagement, nudges, or re-activation not required to fulfil an order.                                                                                   | **Deferred 21:00–07:00** local recipient time (`Africa/Lusaka` default; override via `profiles.notif_prefs.timezone` or payload `timezone`). Row stays `pending` with `next_retry_at` at next 07:00 local — not dropped. | Review request (+24h post-completion), abandoned-cart recovery (flag-gated), KYC stall nudge (48h).                                                                       |

Classification registry: `TEMPLATE_CLASSIFICATION` in `services/api/app/services/notifications/dispatcher.py`. Unknown templates default to **transactional** (fail-safe).

## Quiet hours policy

- **Window:** 21:00 inclusive → 07:00 exclusive in the recipient's timezone.
- **Scope:** Marketing class only. Transactional messages (including OTP and order updates) always send.
- **Implementation:** `should_send_now()` gate at the dispatcher send boundary; deferred rows use `schedule_retry()` without incrementing `attempts`.
- **Boundaries (Africa/Lusaka):**
  - 20:59 — marketing **sends**
  - 21:00 — marketing **deferred** to next 07:00
  - 06:59 — still deferred
  - 07:00 — marketing **sends**

## STOP / START opt-out

### Wording (WhatsApp templates)

Every customer-facing WhatsApp utility template footer:

- **EN:** `Reply STOP to opt out.`
- **Bemba:** `Lemeni STOP ukuleka.`
- **Nyanja:** `Lembani STOP kuleka.`

Keys: `notifications.compliance.stopReply` (per locale file).

### STOP handling (M14-P03)

1. Inbound WhatsApp message body matches `STOP` (case-insensitive, trimmed).
2. Webhook handler updates `profiles.notif_prefs` — disables **all channels** (`whatsapp`, `sms`, `email`) for marketing; transactional order/auth messages may still be required for contract performance (document consent at checkout).
3. Auto-reply uses `notifications.compliance.stopConfirmation` (EN; bem/nya fall back until translated).
4. Meta quality rating: honour STOP instantly — no further marketing sends after acknowledgement.

### START / re-opt-in

- Keyword: `START` (`notifications.compliance.startKeyword`).
- Re-enables marketing-capable channels per user action; confirmation via `notifications.compliance.startConfirmation`.

## Consent capture points

| Point                           | What is consented                                                                  | Storage / audit                                                  |
| ------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **Signup / checkout (M07-P05)** | Transactional order updates via preferred channel; link to Privacy Policy & Terms. | `profiles.dpa_consent_at`, checkout event log.                   |
| **WhatsApp first message**      | Meta template opt-in (utility category); STOP footer on every template.            | WhatsApp delivery webhooks → `notification_outbox` status.       |
| **Marketing nudges (n8n)**      | Only enqueued when user has not STOP'd; deferred outside quiet hours.              | `notif_prefs` channel flags; dedupe keys on outbox rows.         |
| **STOP inbound (M14-P03)**      | Withdrawal of marketing across all channels.                                       | `notif_prefs` update + support log for unknown senders.          |
| **Email receipts / KYC**        | Transactional — covered by account creation & vendor agreement.                    | Resend tags include `subject_key` / `body_key` for traceability. |

## Locale resolution

- Dispatcher injects `locale` from `profiles.locale` (default `en`) into outbox payload before adapter send (M14-P05).
- Message bodies keyed in `packages/i18n/messages/en/notifications.json`.
- **Bemba (`bem`)** and **Nyanja (`nya`)** locale files mirror structure; entries marked `"__fallback": "en"` resolve to English until translated. `bem` / `nya` are registered in `packages/i18n/src/locales.ts`.
- WhatsApp Meta language codes: `en`, `bem_ZM`, `nya_ZM` (see `META_LANGUAGE_CODES` in template registry).

## Adapter i18n keys (no hardcoded bodies)

| Channel  | Key prefix                            | Notes                                                                               |
| -------- | ------------------------------------- | ----------------------------------------------------------------------------------- |
| WhatsApp | `notifications.whatsapp.{template}.*` | Template variables mapped server-side; trust narrative slot for `payment_received`. |
| SMS      | `notifications.sms.{template}.body`   | Fallback chain supplies `body` from keys when WhatsApp fails.                       |
| Email    | `notifications.email.*`               | `subject_key` / `body_key` logged on send (Resend tags).                            |

ESLint `@vergeo/no-hardcoded-strings` applies to frontend; API adapters reference keys in template registries (email) or receive pre-rendered slots (WhatsApp).

## Related docs

- `docs/ops/whatsapp-templates.md` — Meta submission pack
- `docs/ops/whatsapp-cloud-api-setup.md` — F5 founder setup
- `docs/plan/02-pebbles/M14-notifications.md` §M14-P07
