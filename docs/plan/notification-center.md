# In-app notification center (customer · vendor · admin)

Status: built on `feat/notification-center` (branch-only, not deployed). Owner ask: bell + unseen badge in
every app's navbar, a dropdown/sheet + full `/notifications` page, in-app toasts, PWA badge/push.

## Audit — what already exists (reused, not rebuilt)

| Piece | Where | How we reuse it |
| --- | --- | --- |
| Outbox (WhatsApp → SMS → email) | `notification_outbox` (0007), `enqueue_outbox_row`, `emit_event`, dispatcher | **AFTER INSERT trigger** on `notification_outbox` writes the in-app rows in the *same transaction* as the outbox row, whichever path inserted it (PostgREST, `run_sql_script`, or SQL functions such as `apply_payment_status` / COD checkout). No call-site changes, nothing to drift. |
| Silent registry events (KYC submitted, dispute opened, ticket issued) | `EVENT_REGISTRY` maps them to `None` (no WA template) — no outbox row | AFTER triggers on the guarded domain tables (`kyc_records`, `disputes`, `tickets`) — same transaction as the state transition. |
| Customer order-status gap | `vendor_orders._enqueue_status_notification` → template `order_status_changed` (no Meta template ⇒ customer currently gets nothing) | Trigger maps `to_status` → `order_confirmed / order_rejected / order_packed / order_shipped / order_ready_pickup / order_delivered` for the customer. Dedupe key `type:order_id` collapses the twin `emit_order_lifecycle` rows. |
| Toasts | `packages/ui/src/toast.tsx` (`emitToast`, provider mounted in all 3 layouts) | Newest-notification toast via `emitToast(..., {type: "info", action})`. |
| Auth/session | `@vergeo/auth` `getBrowserAccessToken`, `createApiClient` (`@vergeo/config`) | Bell client calls the API with the caller's bearer; customer imports it lazily. |
| PWA | customer: serwist `sw.ts` (no push yet); vendor: **no service worker** | Push = subscription + SW display path behind `feature_flags.web_push` (default OFF). Vendor gets a tiny push-only `public/push-sw.js`. |
| Admin roles | `user_roles(role='admin')` | Admin rows are **fanned out per admin user** at write time so seen/read is per person. |

## Data (migration `20261113090000_in_app_notifications.sql`, additive + reversible)

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
vendor shell header, admin shell header; `/notifications` page in each app. Badge: top-right, caps at `9+`,
`aria-label` "N unread notifications". Polling: unseen count every 60 s **only while visible**, immediately on
focus/visibility; panel list fetched only on open. Count increase ⇒ toast for the newest + `navigator.setAppBadge`.
Customer bundle: the bell is a ~2 KB island; panel + Supabase client load on first interaction / idle.
No websockets (Supabase Realtime is not used anywhere in the apps today).

## Web Push — founder steps to enable (flag stays OFF until done)

1. Generate a VAPID key pair (e.g. `npx web-push generate-vapid-keys`) on your machine — never commit it.
2. Set env names: API `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY`, `WEB_PUSH_VAPID_SUBJECT`
   (`mailto:` ops address); customer + vendor apps `NEXT_PUBLIC_WEB_PUSH_VAPID_PUBLIC_KEY`.
3. Add `pywebpush` to the API (`uv add pywebpush`) — the sender seam (`notifications/web_push.py`) is a no-op without it.
4. Flip `feature_flags.web_push` in admin config (audited). The "Turn on phone alerts" button then appears on the
   notifications page; permission is only requested from that tap, never on load, and a denied permission hides it.

## Not in scope / follow-ups

Push *sending* from the dispatcher (seam only), per-type mute preferences, retention purge (suggest 90 days via n8n),
bem/nya native review of the new strings (drafts appended to `PHASE1_NATIVE_REVIEW.md`).
