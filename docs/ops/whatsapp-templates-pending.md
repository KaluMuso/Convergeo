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
