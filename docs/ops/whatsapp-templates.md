# WhatsApp Message Templates — Meta Submission Pack (Vergeo5)

Ready for founder action **F5** (Meta Business / WhatsApp Manager). Create each template in **WhatsApp Manager → Message templates**. Category **Utility** unless noted. English (`en`) first; add **Bemba** (`bem_ZM`) and **Nyanja** (`nya_ZM`) as separate language variants on the same template name.

**Rules**

- Transactional copy only (utility tone) — keeps quality rating green and avoids marketing pricing.
- Money placeholders are pre-formatted server-side as `K1,234.56` (integer ngwee → display; no float in code).
- Footer on every template: `Reply STOP to opt out.`
- Variable positions must match the API registry in `services/api/app/services/notifications/templates/whatsapp.py`.

---

## 1. `order_confirmed` (Utility)

**Variables:** `{{1}}` order reference · `{{2}}` total (K-formatted) · `{{3}}` track URL

| Locale     | Body                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------ |
| **en**     | Your Vergeo5 order {{1}} is confirmed. Total {{2}}. Track: {{3}} Reply STOP to opt out.    |
| **bem_ZM** | Order yenu ya Vergeo5 {{1}} yasuminishwa. Total {{2}}. Tebula: {{3}} Lemeni STOP ukuleka.  |
| **nya_ZM** | Order yanu ya Vergeo5 {{1}} yatsimikizidwa. Total {{2}}. Onani: {{3}} Lembani STOP kuleka. |

**Sample values:** `ord-abc123` · `K1,234.56` · `https://vergeo5.com/en/orders/ord-abc123`

---

## 2. `payment_received` (Utility — escrow trust narrative)

**Variables:** `{{1}}` trust narrative line (includes K-formatted amount) · `{{2}}` order reference

| Locale     | Body                                      |
| ---------- | ----------------------------------------- |
| **en**     | {{1}} Order {{2}}. Reply STOP to opt out. |
| **bem_ZM** | {{1}} Order {{2}}. Lemeni STOP ukuleka.   |
| **nya_ZM** | {{1}} Order {{2}}. Lembani STOP kuleka.   |

**i18n slot `trust_narrative` (server fills {{1}} per locale):**

| Locale     | Slot text (amount token = server `formatK`)                 |
| ---------- | ----------------------------------------------------------- |
| **en**     | Your K__ is held safely by Vergeo5 until delivery.          |
| **bem_ZM** | K__ yenu yikwata bwino na Vergeo5 mpaka kufika kwa katundu. |
| **nya_ZM** | K__ yanu ikusungidwa ndi Vergeo5 mpaka kutumiza.            |

**Sample values:** `Your K1,234.56 is held safely by Vergeo5 until delivery.` · `ord-abc123`

---

## 3. `order_shipped` (Utility)

**Variables:** `{{1}}` order reference · `{{2}}` tracking info / link

| Locale     | Body                                                               |
| ---------- | ------------------------------------------------------------------ |
| **en**     | Your Vergeo5 order {{1}} has shipped. {{2}} Reply STOP to opt out. |
| **bem_ZM** | Order yenu {{1}} yatumizwa. {{2}} Lemeni STOP ukuleka.             |
| **nya_ZM** | Order yanu {{1}} yatumizidwa. {{2}} Lembani STOP kuleka.           |

**Sample values:** `ord-abc123` · `Track: https://vergeo5.com/en/orders/ord-abc123`

---

## 4. `order_ready_pickup` (Utility)

**Variables:** `{{1}}` order reference · `{{2}}` pickup details / QR link

| Locale     | Body                                                                       |
| ---------- | -------------------------------------------------------------------------- |
| **en**     | Your Vergeo5 order {{1}} is ready for pickup. {{2}} Reply STOP to opt out. |
| **bem_ZM** | Order yenu {{1}} yikwete kale. {{2}} Lemeni STOP ukuleka.                  |
| **nya_ZM** | Order yanu {{1}} akuyenera kutengedwa. {{2}} Lembani STOP kuleka.          |

**Sample values:** `ord-abc123` · `Collect at Kamwala Trading, stand 12. QR: https://vergeo5.com/en/pickup/ord-abc123`

---

## 5. `order_delivered` (Utility)

**Variables:** `{{1}}` order reference · `{{2}}` review link

| Locale     | Body                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------- |
| **en**     | Your Vergeo5 order {{1}} was delivered. Share your experience: {{2}} Reply STOP to opt out. |
| **bem_ZM** | Order yenu {{1}} yafika. Lemeni ifiwayo: {{2}} Lemeni STOP ukuleka.                         |
| **nya_ZM** | Order yanu {{1}} adafika. Lembani ndemanga: {{2}} Lembani STOP kuleka.                      |

**Sample values:** `ord-abc123` · `https://vergeo5.com/en/orders/ord-abc123/review`

---

## 6. `vendor_new_order` (Utility)

**Variables:** `{{1}}` order reference · `{{2}}` product title · `{{3}}` quantity

| Locale     | Body                                                                        |
| ---------- | --------------------------------------------------------------------------- |
| **en**     | New order {{1}} on Vergeo5: {{2}} × {{3}}. Confirm in the vendor app.       |
| **bem_ZM** | Order yambi {{1}} pa Vergeo5: {{2}} × {{3}}. Tukishisheni mu vendor app.    |
| **nya_ZM** | Order yatsopano {{1}} pa Vergeo5: {{2}} × {{3}}. Tsimikizani mu vendor app. |

**Sample values:** `ord-abc123` · `Samsung A15 128GB` · `2`

---

## 7. `otp_login` (Authentication)

**Variables:** `{{1}}` OTP code · **Copy-code button** (index 0) uses the same code.

| Locale     | Body                                                                                |
| ---------- | ----------------------------------------------------------------------------------- |
| **en**     | Your Vergeo5 login code is {{1}}. It expires in 10 minutes. Do not share this code. |
| **bem_ZM** | Code yenu ya kulowa mu Vergeo5 ni {{1}}. Ilekefwa mu miniti 10. Musosele code iyi.  |
| **nya_ZM** | Code yanu yolowera mu Vergeo5 ndi {{1}}. Imatha mu mphindi 10. Musagawane code iyi. |

**Button:** Authentication → **Copy code** (OTP auto-fill).

**Sample values:** `482913`

---

## API wiring (reference)

- Env: `WHATSAPP_TOKEN` (or `WHATSAPP_ACCESS_TOKEN`), `WHATSAPP_PHONE_NUMBER_ID`, optional `WHATSAPP_API_VERSION` (default `v23.0`).
- Endpoint: `POST https://graph.facebook.com/{version}/{phone-number-id}/messages`
- Payload built by `WhatsAppAdapter` + `build_cloud_api_template()` — see `services/api/tests/test_whatsapp_adapter.py`.

## Test-number E2E (post F5)

1. Add your personal +260 number as a test recipient in WhatsApp Manager.
2. Set env vars on staging API.
3. Enqueue an outbox row with `channel=whatsapp`, `template=order_confirmed`, and a fixture payload (see tests).
4. Trigger internal dispatch cron — expect `message_status=sent` webhook (M14-P03).
