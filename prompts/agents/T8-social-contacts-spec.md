# T8: Social contacts ("add people", WeChat-style). Spec v1

**Status:** spec. Claude owns the database and RLS design; Cursor builds the UI and API after Claude's migration PR lands.
**Flag:** `social_contacts` (default **off**). **Model for Cursor:** Composer 2.5.

## Goal

Let customers (and vendors acting as people) add each other as contacts, chat 1:1, and share product, service and event cards. Contacts drive word-of-mouth, gifting and repeat purchase.

## User stories

1. **My code:** each user has a personal QR code and a Vergeo ID (`@handle`, unique, editable once per 30 days). Scanning the QR code or entering `@handle` opens their profile card with an **Add** button.
2. **Request:** **Add** sends a contact request with an optional note (up to 80 characters). The recipient can **Accept**, **Ignore** (silent), **Block** or **Report**. Pending requests expire after 30 days.
3. **Contacts list:** A–Z list with search; tap to open the chat; long-press to remove or block.
4. **Find friends from phone contacts:** opt-in only. Numbers are hashed (SHA-256 of E.164 with a server pepper) on the device side or the server side, never stored raw, and matched only against users who enabled "Let people find me by phone" (default off).
5. **Chat 1:1:** text, plus share cards for product, service and event, linking to the listing. No media uploads in v1. Read receipts are optional and default off.
6. **Gift:** from a contact's profile, **Send a gift**, which reuses the existing `gift_orders` flow with the recipient prefilled.
7. **Safety:** only accepted contacts can message. Blocking is two-way and immediate (it hides profiles and stops requests and messages). Reports go to the admin Moderation queue.

## Data model (Claude writes the migration)

- `user_handles(user_id pk, handle citext unique, changed_at)`
- `contact_requests(id, from_user, to_user, note, status enum[pending, accepted, ignored, expired], created_at, decided_at)` with a unique pending pair
- `contacts(user_a, user_b, created_at)`, stored as an ordered pair (`user_a < user_b`), with a check constraint
- `contact_blocks(blocker, blocked, created_at)`
- `chat_threads(id, user_a, user_b, created_at, last_message_at)` (unique pair)
- `chat_messages(id, thread_id, sender, kind enum[text, share_card], body text ≤ 2000, card jsonb, created_at)`
- `phone_discovery(user_id, phone_hash, enabled bool)`
- **RLS:** a row is visible only to its two parties. Inserting a message requires an existing contact and no block in either direction, enforced in a `SECURITY DEFINER` function plus RLS, never in the UI alone.
- **Rate limits** (existing `rate_counters`): 30 requests a day per user, 20 messages a minute per thread.

## API (FastAPI)

- `GET/PUT /me/handle`, `GET /me/qr` (signed payload `vgo:add:<handle>`)
- `GET /people/{handle}`: public card (name, avatar, handle), or 404 when blocked
- `POST /contacts/requests`, `GET /contacts/requests?box=in|out`, `POST /contacts/requests/{id}/accept|ignore`
- `GET /contacts`, `DELETE /contacts/{user_id}`, `POST /contacts/{user_id}/block`, `POST /contacts/{user_id}/report`
- `POST /contacts/discover-phones` (hashes in, matches out; opt-in users only)
- `GET /chats`, `GET /chats/{id}/messages?before=`, `POST /chats/{id}/messages`
- Every mutating endpoint has an authz check, Pydantic strict validation and a rate limit. New notification events: `contact_request_received` and `chat_message_received`, through the outbox and in-app first; WhatsApp only after Meta approval.

## UI (customer app, i18n keys only, 360 px first)

- Account → **People** tab: contacts, requests (badge) and **Add people** (scan QR / enter `@handle` / phone, opt-in).
- Profile card sheet; chat screen with share-card picker (from Saved and Recently viewed).
- Settings: "Let people find me by phone" (off) and "Who can send me requests: everyone / no one".
- Budget: People and Chat routes ≤ 150 KB gz JS. Load the QR scanner lazily.

## Tests (required)

- RLS: a non-party cannot read threads or messages; messaging after a block fails; a request is refused when the recipient sets "no one".
- Rate-limit failure paths; a duplicate pending request; handle uniqueness (case-insensitive).
- Phone discovery never returns users who didn't opt in.
- The UI renders nothing with the flag off.

## Out of scope for v1

Group chats, media and voice messages, a moments or feed of friends' activity, payments between users.
