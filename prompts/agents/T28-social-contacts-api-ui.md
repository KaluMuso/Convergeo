# Task T28: People and contacts — API, customer screens, phone-contact finding and invites (T8 part 2)

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/social-contacts-app` from `master`, **only after PR #873 (database) is merged**. Open one PR to `master`; don't merge.
**Board:** claim row T28 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Spec:** `prompts/agents/T8-social-contacts-spec.md` (read it first). Flag `social_contacts` stays **off**; every screen and endpoint returns 404 / hides when it is off.
**Owns (edit only these):**

- `services/api/app/routers/contacts.py` (new), `services/api/app/services/social/` (new), its registration line in `services/api/app/main.py`, `services/api/tests/test_contacts_api.py` (new)
- `apps/customer/app/[locale]/account/people/**` (new), the People tab entry in the account nav, `apps/customer/lib/social/**` (new)
- `packages/i18n/messages/*/social.json` (new namespace) and its registration

## The database is done (#873). Call these functions; never write the tables directly

All take `p_actor` = the signed-in user id when called by the API with the service role.

| Function                                                               | Use                                                                                                                                   |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `set_my_handle(p_handle, p_actor)`                                     | choose `@handle`                                                                                                                      |
| `lookup_handle_card(p_handle, p_actor)`                                | profile card for `@handle` or QR                                                                                                      |
| `send_contact_request(p_to_handle, p_note, p_actor)`                   | **Add** (note ≤ 80 chars). A crossing request auto-accepts                                                                            |
| `respond_contact_request(p_request_id, 'accept' or 'ignore', p_actor)` | Accept / Ignore                                                                                                                       |
| `my_contact_requests(p_actor)`                                         | in and out boxes (`outgoing` column). **An ignored request shows as pending to the sender — keep it that way; never tell the sender** |
| `remove_contact`, `block_user`, `unblock_user` (`p_other, p_actor`)    | contact menu                                                                                                                          |
| `send_chat_message(p_thread_id, p_kind, p_body, p_card, p_actor)`      | 1:1 chat text or share card                                                                                                           |
| `set_phone_discovery(p_user, p_phone_hash, p_enabled)`                 | "Let people find me by my phone number" (default off)                                                                                 |
| `discover_by_phone_hashes(p_hashes, p_actor)`                          | phone-contact matching, opted-in users only                                                                                           |

Errors come back as `social:<code>` (for example `social:duplicate`, `social:rate_limited`, `social:blocked`). Map each to a clear HTTP status and an i18n message.

## API (FastAPI)

Endpoints from the spec. Every mutating endpoint: auth required, Pydantic strict body, rate limit. Read the flag server-side.

**Phone hashing (important):**

- The browser sends `sha256_hex(E.164 number)` for each contact. Raw numbers never leave the phone.
- The server turns each into `hmac_sha256(SOCIAL_PHONE_PEPPER, client_hash)` before calling `discover_by_phone_hashes` or `set_phone_discovery`. The same transform is used when a user opts in with their own verified phone.
- `SOCIAL_PHONE_PEPPER` is a new env setting. No default in production: if it is missing, discovery returns 503 and the toggle is hidden. Add it to the settings class and `.env.example` only (King sets the value).
- At most 500 hashes per call; 5 calls per user per day.
- Normalise numbers to Zambian E.164 on the device before hashing: `0977…` and `977…` become `+260977…`. Put this in one shared function with tests.

## Customer screens (360 px first, i18n keys only)

Account → **People** tab with: Contacts, Requests (badge), **Add people**.

**Add people** offers:

1. Enter `@handle`.
2. Scan or show my QR code (the code encodes the share link `https://www.vergeo5.com/{locale}/u/{handle}`).
3. **Find friends from my contacts:**
   - **Android Chrome:** use the Contact Picker API (`navigator.contacts.select(['name','tel'], {multiple: true})`) when `'contacts' in navigator`. First show a plain explanation screen: "We only check which of your contacts are on Convergeo. Numbers are scrambled on your phone and never stored." Hash on the device with `crypto.subtle.digest('SHA-256', …)`. Show the matches with an **Add** button each.
   - **iPhone and desktop** (no Contact Picker): hide that button. Show **Share my Convergeo link** (Web Share API, falling back to copy) and **Invite on WhatsApp** (`https://wa.me/?text=` with the encoded invite text and link) instead.
   - For contacts the picker returned that are **not** on Convergeo: show an **Invite** button per contact that opens `https://wa.me/<their E.164 without +>?text=<invite>`. Never send anything automatically, and never store those numbers.
4. Settings toggle "Let people find me by my phone number", default **off**.

**Requests:** incoming with Accept / Ignore / Block. Outgoing shows "Pending" (including ignored ones).

**Contacts:** list → profile card → Message, Send a gift (reuse `gift_orders` with the recipient prefilled), Remove, Block, Report.

**Chat:** 1:1 text plus share cards (product, service, event). Polling every 15 s is enough for v1, no websockets. Keep the People route out of the main bundle (dynamic import). Run the bundle guard; growth for routes outside `/account/people` must be 0.

## Tests (required)

- API: authz (another user's request id → 404), flag off → 404, the `social:*` error mapping, rate limits, pepper missing → 503, at most 500 hashes, and that the endpoint never returns a non-opted-in user.
- Number normalisation and hashing: `0977123456`, `977123456`, `+260977123456` and `260977123456` all give the same hash; foreign numbers are kept as they are.
- UI: Contact Picker button only when supported; the iPhone fallback shows the Share and WhatsApp buttons; the ignored outgoing request shows "Pending"; Invite builds the right `wa.me` link.

## Done means

With the flag on in staging, two test users can find each other by handle, QR and phone, send and accept a request, chat, share a product card and block. With the flag off, nothing shows. Tests, typecheck, lint and bundle guard pass.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time (`pnpm --filter customer exec vitest related <files> --run`, `cd services/api && uv run pytest tests/test_contacts_api.py -q`), then typecheck and lint for the touched packages. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. bem, nya, fr and zh: copy the English text and mark it for review. Don't invent translations.
6. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev. Claude reviews (auth and privacy).
