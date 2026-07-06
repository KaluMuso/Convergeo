# WhatsApp Business Cloud API — Activation Guide (Vergeo5)

Goal: official Meta Cloud API for transactional messages (order confirmed / payment received / shipped / delivered / OTP), SMS as fallback. **No WAHA anywhere** — Meta provides a free test number the same day you start, so even development never needs an unofficial gateway.

Costs (July 2026, "Rest of Africa" band): utility templates ≈ **$0.006/msg** and **FREE inside an open 24h customer-service window**; authentication similar; marketing ≈ $0.0225/msg. At launch volumes this is trivially cheap. Pricing is per delivered template message (model changed July 2025); check the current rate card before big sends.

## Prerequisites (do first)
1. **A phone number NOT registered on any WhatsApp/WhatsApp Business app** — dedicated to the platform. A Zambian mobile (+260 MTN/Airtel/Zamtel) or fixed line works; it must be able to receive an SMS **or voice call** OTP once. After linking, the number cannot be used in the normal WhatsApp apps.
2. **vergeo5.com purchased** (founder action F1) + a business email on it (e.g. hello@vergeo5.com) — makes Business Verification dramatically smoother.
3. **PACRA certificate of incorporation** (+ proof of address: utility bill/bank statement matching the business name) scanned — needed for Business Verification (step 6).
4. A personal Facebook account (any) to bootstrap the Business Portfolio.

## Steps

### 1. Create the Meta Business Portfolio
- Go to **business.facebook.com** → Create a business portfolio.
- Business name: exactly the PACRA-registered name (mismatches stall verification). Add vergeo5.com and the business email; confirm the email link.

### 2. Create the developer app
- **developers.facebook.com** → My Apps → Create App → use case **"Other"** → type **Business** → attach it to the Business Portfolio from step 1.
- In the app dashboard, **Add Product → WhatsApp → Set up**. This auto-creates a **WhatsApp Business Account (WABA)** and gives you:
  - a **TEST phone number** (free, works immediately, can message up to 5 verified recipient numbers),
  - a temporary access token (23h) for first API calls.
- ✅ Development can start TODAY against the test number. Send yourself a hello-world:
  `POST https://graph.facebook.com/v23.0/{phone-number-id}/messages` with `{"messaging_product":"whatsapp","to":"+2609XXXXXXXX","type":"template","template":{"name":"hello_world","language":{"code":"en_US"}}}`.

### 3. Add the real number
- WhatsApp Manager (business.facebook.com/wa/manage) → Phone numbers → **Add phone number** → enter the dedicated +260 number → verify via SMS or voice OTP.
- Set the **display name**: "Vergeo5" (must plausibly relate to the business/website; Meta reviews it, usually minutes–48h).

### 4. Permanent access token (production credential)
- Business Settings → Users → **System users** → Add: name `vergeo5-api`, role **Admin**.
- Assign assets to the system user: the **app** (full control) and the **WABA** (full control).
- Generate token → select the app → scopes: `whatsapp_business_messaging` + `whatsapp_business_management` → expiry **never**. Store ONLY in the backend secret store (env var `WHATSAPP_ACCESS_TOKEN`) — never in the repo.

### 5. Webhooks (delivery/read/inbound events)
- App dashboard → WhatsApp → Configuration → Webhook: callback `https://api.vergeo5.com/webhooks/whatsapp`, verify token = random secret (env `WHATSAPP_WEBHOOK_VERIFY_TOKEN`); subscribe to `messages`. The backend must answer the GET challenge, then validate `X-Hub-Signature-256` on POSTs.

### 6. Business Verification (lifts limits; do in parallel, not blocking dev)
- Business Settings → **Security Centre** → Start Verification: legal name, address, phone, vergeo5.com; upload PACRA certificate + proof of address; verify a business phone/email/domain. Typically days.
- Messaging limits: unverified ≈ **250 business-initiated conversations/day** (plenty for beta) → **1,000/day** on verification → auto-scales (10K → 100K → unlimited) with volume + quality rating. Replies inside the 24h service window are unlimited and free.

### 7. Message templates (create early — approval can take hours–days)
Create in WhatsApp Manager → Message templates, category **Utility** (or Authentication for OTP). v1 set:
- `order_confirmed` — "Your Vergeo5 order {{1}} is confirmed. Total K{{2}}. Track: {{3}}"
- `payment_received` — escrow reassurance copy
- `order_shipped` / `order_ready_pickup` — with tracking/QR link
- `order_delivered` — + review nudge (keep it utility-toned; pure marketing copy → Marketing category and 4× the price)
- `otp_login` (Authentication category, one-tap copy-code button)
- `vendor_new_order` — "New order {{1}} on Vergeo5: {{2}} × {{3}}. Confirm in the vendor app."
- `rfq_new_quote`, `ticket_delivery` (QR link) when those verticals ship.
English first; add Bemba/Nyanja translations as separate template languages later (each language reviewed once).

### 8. Go-live checklist
- App Mode → Live (needs privacy policy URL — legal pages pebble supplies vergeo5.com/privacy).
- Opt-in: collect WhatsApp consent at checkout/signup (checkbox, stored with timestamp) — Meta policy + quality rating both demand it; every template footer offers "Reply STOP".
- Keep quality **green**: transactional sends only to opted-in users, SMS fallback on template failure (webhook `message_status=failed` → Africa's Talking).
- Optional later: **Official Business Account** (green tick) application once brand presence exists.

### Interim before the real number is live
Test number covers all development + internal beta (5 recipients). If public beta starts before display-name/verification clears: SMS-only for order-critical messages. **Never WAHA** — a banned number mid-beta is a trust catastrophe the platform can't afford.
