# In-app notification center (customer · vendor · admin)

Status: built on `feat/notification-center` (branch-only, not deployed). Owner ask: bell + unseen badge in
every app's navbar, a dropdown/sheet + full `/notifications` page, in-app toasts, PWA badge/push.

## Audit — what already exists (reused, not rebuilt)

| Piece                                                                 | Where                                                                                                                               | How we reuse it                                                                                                                                                                                                                                                                         |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Outbox (WhatsApp → SMS → email)                                       | `notification_outbox` (0007), `enqueue_outbox_row`, `emit_event`, dispatcher                                                        | **AFTER INSERT trigger** on `notification_outbox` writes the in-app rows in the _same transaction_ as the outbox row, whichever path inserted it (PostgREST, `run_sql_script`, or SQL functions such as `apply_payment_status` / COD checkout). No call-site changes, nothing to drift. |
| Silent registry events (KYC submitted, dispute opened, ticket issued) | `EVENT_REGISTRY` maps them to `None` (no WA template) — no outbox row                                                               | AFTER triggers on the guarded domain tables (`kyc_records`, `disputes`, `tickets`) — same transaction as the state transition.                                                                                                                                                          |
| Customer order-status gap                                             | `vendor_orders._enqueue_status_notification` → template `order_status_changed` (no Meta template ⇒ customer currently gets nothing) | Trigger maps `to_status` → `order_confirmed / order_rejected / order_packed / order_shipped / order_ready_pickup / order_delivered` for the customer. Dedupe key `type:order_id` collapses the twin `emit_order_lifecycle` rows.                                                        |
| Toasts                                                                | `packages/ui/src/toast.tsx` (`emitToast`, provider mounted in all 3 layouts)                                                        | Newest-notification toast via `emitToast(..., {type: "info", action})`.                                                                                                                                                                                                                 |
| Auth/session                                                          | `@vergeo/auth` `getBrowserAccessToken`, `createApiClient` (`@vergeo/config`)                                                        | Bell client calls the API with the caller's bearer; customer imports it lazily.                                                                                                                                                                                                         |
| PWA                                                                   | customer: serwist `sw.ts` (no push yet); vendor: **no service worker**                                                              | Push = subscription + SW display path behind `feature_flags.web_push` (default OFF). Vendor gets a tiny push-only `public/push-sw.js`. Customer SW serves the notification API NetworkOnly.                                                                                             |
| Admin roles                                                           | `user_roles(role='admin')`                                                                                                          | Admin rows are **fanned out per admin user** at write time so seen/read is per person.                                                                                                                                                                                                  |

## Data (migration `20261113130000_in_app_notifications.sql`, additive + reversible)

- `in_app_notifications(id, recipient_user_id, audience customer|vendor|admin, type, i18n_key, params jsonb, link_path,
dedupe_key, created_at, seen_at, read_at)`; `UNIQUE(recipient_user_id, audience, dedupe_key)`.
  - `i18n_key` = `notifications.inApp.<audience>.<type>` — never raw text. `params` is an allow-listed object (short order
    ref only; ≤1 KB). Pickup PINs/QR tokens, phone numbers, notes and amounts in the outbox payload are **not** copied.
  - `link_path` is app-relative and locale-less (`/account/orders/<id>`), checked by regex.
  - FORCE RLS: `authenticated` may `SELECT` own rows and `UPDATE (seen_at, read_at)` own rows only (column grant);
    a BEFORE UPDATE guard makes the timestamps monotonic (never cleared, read ⇒ seen). No client INSERT/DELETE.
- `web_push_subscriptions(user_id, audience, endpoint unique, p256dh, auth_secret, created_at)`; RLS own-row select/delete.
- `feature_flags.web_push = false`.
- Writers: `private.enqueue_in_app_notification(...)`, `private.enqueue_admin_in_app_notification(...)` (fan-out),
  `private.in_app_from_outbox()` trigger fn, domain trigger fns. All service-only; a writer failure is caught
  and raised as a WARNING so a notification bug can never roll back a payment/order transition.

Event coverage: order placed (vendor+customer), confirmed / rejected / packed / shipped / ready-for-pickup (customer),
delivered (customer+vendor), KYC submitted (vendor ack + admins), KYC approved/rejected (vendor), dispute opened
(admins + vendor), RFQ received (vendor), quote received (customer), new matching job (vendor), ticket issued (holder).

## API (`services/api/app/routers/notifications.py`)

`GET /me/notifications?audience=&cursor=&limit=` (keyset on `(created_at,id)`, opaque base64 cursor) ·
`GET /me/notifications/unseen-count?audience=` · `POST /me/notifications/seen` (`{ids?}`; empty = all) ·
`POST /me/notifications/{id}/read` · `POST /me/notifications/read-all` · `PUT|DELETE /me/push-subscriptions` (flag-gated).
Every query is filtered by the caller's own id; `audience=vendor|admin` additionally requires that role. Pydantic v2
strict, rate-limited (reads 600/h, writes 300/h per user).

## UI

Shared, token-only components in `packages/ui/src/notification-center.tsx` (plain `.v-notif*` CSS classes in
`base.css`, like the toast). Each app wires a thin adapter (API + labels): customer shop header + account header,
vendor shell header, admin shell header; full page at `/account/notifications` (customer) and `/notifications`
(vendor, admin — admin route is exempt from nav-permission gating since it only shows the caller's rows). Badge: top-right, caps at `9+`,
`aria-label` "N unread notifications". Polling: unseen count every 60 s **only while visible**, immediately on
focus/visibility; panel list fetched only on open. Count increase ⇒ toast for the newest + `navigator.setAppBadge`.
Customer bundle: the bell is a ~2 KB island; panel + Supabase client load on first interaction / idle.
No websockets (Supabase Realtime is not used anywhere in the apps today).

## Web Push — sending (built on `feat/web-push-delivery`)

| Piece          | Where                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Queue          | `web_push_deliveries` (migration `20261113140000`, additive + reversible): one row per (notification, subscription), `UNIQUE(notification_id, subscription_id)` = idempotency key. Service-role only (FORCE RLS, no client grants).                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Enqueue        | AFTER INSERT trigger on `in_app_notifications` — same transaction as the in-app row, **only while `web_push` is ON**; inserts ids only; any error is a WARNING (never rolls back an order/payment/KYC transition). Nothing is sent inside a domain transaction.                                                                                                                                                                                                                                                                                                                                                                                             |
| Sender         | `services/api/app/services/notifications/web_push.py`, driven by `POST /internal/dispatch/web-push-tick` (same `X-Internal-Token` as the outbox tick; n8n `infra/n8n/notification-dispatch.json` calls both every minute).                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Crypto         | `pywebpush` 2.x (+ `py-vapid`) added via `uv add`: aes128gcm (RFC 8291) + VAPID ES256 (RFC 8292). Transport is `httpx`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Payload        | `{title, body, url, badge}` per `apps/customer/lib/push-payload.ts`: `notifications.title` + `notifications.inApp.<audience>.<type>` rendered in `profiles.locale` (→ English → `inApp.fallback`), only simple `{ref}` placeholders filled from sanitized params; `url` = `/<locale><link_path>`; `badge` = unseen count. No PINs, QR tokens, phones, amounts or user ids. Strings are snapshotted to `services/api/app/data/web_push_messages.json` (the API image has no `packages/`); a test fails on drift — regenerate with `uv run python scripts/sync_web_push_messages.py`. Admin `translation_overrides` are not applied to push text (follow-up). |
| Delivery rules | Compare-and-set claim on `attempts` (two ticks never double-send). 2xx → `sent`. 404/410 → that exact subscription row is deleted (queue rows cascade). 429/5xx/network → retry, backoff 60 s·2ⁿ (≥ `Retry-After`, cap 6 h), 5 attempts → `failed`. Other 4xx → `failed` (401/403 logs a VAPID warning). Skipped: already seen/read, older than 12 h, endpoint changed owner, per-user cap (20 sends/h via `bump_rate_counter` scope `web_push_send`).                                                                                                                                                                                                      |
| Quiet hours    | 22:00–06:00 Africa/Lusaka by default: due rows are deferred to 06:00 (attempt not spent). Env `WEB_PUSH_QUIET_HOURS` (`"22-6"`, `"off"`) and `WEB_PUSH_QUIET_TZ`. Push `Topic` collapses undelivered alerts per device, so a phone that was offline gets the newest one.                                                                                                                                                                                                                                                                                                                                                                                    |
| Fail closed    | Flag OFF → tick returns `reason: flag_off`. Any of the three VAPID env vars missing → no sends + warning (`vapid_missing`); unparsable private key → `vapid_invalid`. `GET /me/web-push` only reports enabled (and the public key) when all three are set.                                                                                                                                                                                                                                                                                                                                                                                                  |
| SSRF guard     | Endpoints must be `https` on a known push service (`fcm.googleapis.com`, `android.googleapis.com`, `*.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`), checked on subscribe and again before every send.                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Ownership      | `PUT /me/push-subscriptions` never deletes another user's row. Own endpoint → keys refreshed in place. Endpoint owned by someone else → transferred to the caller **only if the request carries that subscription's exact browser-generated `p256dh` + `auth`** (constant-time compare; the auth secret is known only to that browser and us), and the previous owner's still-queued alerts are dropped; otherwise `409 push_endpoint_conflict`. The sender re-checks `subscription.user_id == recipient` before every send. Unsubscribe deletes only the caller's row.                                                                                     |

## Web Push — founder steps to enable (flag stays OFF until done)

1. Generate a VAPID key pair on your own machine (never commit it, never paste it in chat/PRs):
   `npx web-push generate-vapid-keys` — prints a base64url public key and private key.
2. Hetzner API host (`infra/.env`, read by the `api` service; names listed in `infra/.env.example`): set `WEB_PUSH_VAPID_PUBLIC_KEY`,
   `WEB_PUSH_VAPID_PRIVATE_KEY`, `WEB_PUSH_VAPID_SUBJECT` (`mailto:` ops address), then restart the API.
   Optional: `WEB_PUSH_QUIET_HOURS` (default `22-6`).
3. Vercel → customer **and** vendor projects: set `NEXT_PUBLIC_WEB_PUSH_VAPID_PUBLIC_KEY` to the same public key; redeploy.
4. n8n: re-import `infra/n8n/notification-dispatch.json` (adds the "Send Web Push Batch" node) and activate it.
5. Flip `feature_flags.web_push` in admin config (audited). The "Turn on phone alerts" button then appears on the
   notifications page; permission is only requested from that tap, never on load, and a denied permission hides it.
6. Test on Android Chrome: open the customer app, Notifications → "Turn on phone alerts", close the app, trigger an
   order status change from a vendor account; the alert should arrive within ~1 minute (outside 22:00–06:00).
   iOS: Web Push only works for the PWA **added to the home screen** (iOS 16.4+), opened from that icon.
7. Rollback: flip `web_push` OFF (queueing stops immediately; ticks return `flag_off`).

## Not in scope / follow-ups

Per-type mute preferences, retention purge (suggest 90 days via n8n for `in_app_notifications` and finished `web_push_deliveries` rows), admin translation overrides for push text,
bem/nya native review of the new strings (drafts appended to `PHASE1_NATIVE_REVIEW.md`).
