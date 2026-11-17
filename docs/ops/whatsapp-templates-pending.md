# WhatsApp templates pending Meta approval (E1 / E4)

Submit these in **WhatsApp Manager → Message templates** (founder action F5). Category **Utility**, language **English (en)**; add Bemba (`bem_ZM`) and Nyanja (`nya_ZM`) variants later under the same name. The text below is exact; variables are positional and must keep this order. Money values arrive pre-formatted as `K1,234.56` (integer ngwee, server-side). The server falls back to English when a locale variant is not approved.

Until a template is approved, sends for that event fail permanently on WhatsApp and fall over to SMS, then email (the existing fallback chain), so nothing is lost while approval is pending. Quiet hours do not apply (all are transactional) and opt-out (`STOP`) is honoured by the dispatcher.

Already approved and reused, so no new submission: `rfq_quoted` (event `quote_received`) and `service_quote_accepted` (event `quote_accepted`).

Registry source: `services/api/app/services/notifications/templates/whatsapp.py`.

## 1. `order_cancelled` (Utility, Customer-facing)

**Event:** `order_cancelled`  
**Variables:** {{1}} order reference · {{2}} refund detail

**Body (en):**

> Your Convergeo order {{1}} was cancelled. {{2}} Reply STOP to opt out.

**Sample values:** ord-abc123 · If you already paid, Convergeo will handle your refund and keep you updated.

## 2. `payment_failed` (Utility, Customer-facing)

**Event:** `payment_failed`  
**Variables:** {{1}} amount (K-formatted) · {{2}} retry link

**Body (en):**

> Your payment of {{1}} did not go through. If you were charged, contact support and we will sort it out. Try again: {{2}} Reply STOP to opt out.

**Sample values:** K1,234.56 · https://vergeo5.com/en/orders

## 3. `order_completed` (Utility, Customer-facing)

**Event:** `order_completed`  
**Variables:** {{1}} order reference · {{2}} order link

**Body (en):**

> Your Convergeo order {{1}} is complete. Thank you for shopping with us! See it here: {{2}} Reply STOP to opt out.

**Sample values:** ord-abc123 · https://vergeo5.com/en/orders/ord-abc123

## 4. `ticket_issued` (Utility, Customer-facing)

**Event:** `ticket_issued`  
**Variables:** {{1}} event title · {{2}} ticket link

**Body (en):**

> Your ticket for {{1}} is ready. Show the QR code at the door: {{2}} Reply STOP to opt out.

**Sample values:** Jazz Night · https://vergeo5.com/en/account/tickets

## 5. `dispute_opened` (Utility, Vendor-facing)

**Event:** `dispute_opened`  
**Variables:** {{1}} order reference

**Body (en):**

> A customer opened a dispute on order {{1}}. Open the vendor app to read it and respond.

**Sample values:** ord-abc123

## 6. `dispute_resolved` (Utility, Customer-facing)

**Event:** `dispute_resolved`  
**Variables:** {{1}} order reference · {{2}} resolution summary

**Body (en):**

> The dispute on your order {{1}} is resolved. {{2}} Reply STOP to opt out.

**Sample values:** ord-abc123 · Open the app to see the outcome.

## 7. `payout_sent` (Utility, Vendor-facing)

**Event:** `payout_sent`  
**Variables:** {{1}} amount (K-formatted) · {{2}} destination label

**Body (en):**

> Your payout of {{1}} is on its way to your {{2}}.

**Sample values:** K2,900.00 · MTN number ending 1234

## 8. `payout_failed` (Utility, Vendor-facing)

**Event:** `payout_failed`  
**Variables:** {{1}} amount (K-formatted) · {{2}} what to do next

**Body (en):**

> Your payout of {{1}} could not be sent. {{2}} We will retry once your details are correct.

**Sample values:** K2,900.00 · Please check your payout number in the vendor app.

# WhatsApp templates pending Meta approval

Templates the code already renders (`services/api/app/services/notifications/templates/whatsapp.py`)
but that are not yet approved in WhatsApp Manager. Until approval a send fails and the outbox
falls back (SMS → email); the in-app notification is written regardless. Submit each one, then
move it into `whatsapp-templates.md`. Other branches append to this file — keep one section per template.

## `points_earned` (Marketing — Convergeo Points, flag `loyalty_points`)

- Category: Marketing (quiet hours + consent apply; opt-out honoured).
- Languages: `en`, `bem_ZM`, `nya_ZM` (bem/nya pending native review).
- Body:

  > Thanks for shopping with Convergeo! You earned {{1}} points. You now have {{2}}. At {{3}} points you unlock a reward coupon. Points have no cash value.

- Variables: `{{1}}` points earned (integer), `{{2}}` balance (integer), `{{3}}` next coupon threshold (integer).
- Sample: `120`, `460`, `500`.
- Sent by: `private.points_insert` (order earn after the return window; verified review).

## `vendor_weekly_digest` (Marketing — weekly seller digest, flag `vendor_weekly_digest`)

- Category: Marketing (weekly, Monday 08:00 Lusaka; quiet hours + consent apply).
- Languages: `en`, `bem_ZM`, `nya_ZM` (bem/nya pending native review).
- Body:

  > Your week, {{1}}: {{2}} orders, {{3}} in sales. Top item: {{4}}. {{5}} new followers. {{6}} actions waiting for you. Next payout: {{7}}.

- Variables: `{{1}}` shop name, `{{2}}` orders (integer), `{{3}}` sales (`K1,234.56`), `{{4}}` top item or `-`,
  `{{5}}` new followers, `{{6}}` pending actions, `{{7}}` next payout (`K1,234.56`) or `-`.
- Sample: `Kabwe Phones`, `12`, `K3,480.00`, `Samsung A15 case`, `4`, `1`, `K2,900.00`.
- Sent by: `private.vendor_weekly_digest(p_now, true)` via `POST /internal/vendor-digest/weekly`.
