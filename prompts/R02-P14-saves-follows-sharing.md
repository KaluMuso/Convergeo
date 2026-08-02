> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P14 — Saves, follows and sharing `[CODE]`

## 1. Context
**Wave W5.** Governing decision: **D37**.

Partly built already — check before writing:
- **Saves exist**: `user_wishlist` and `user_recently_viewed` (migration `0066`).
- **Clip share pages exist**: M17-P08 shipped a public SSR share page with OG tags.
- **Follows do not exist** anywhere.

So this pebble is: add **follows**, extend **sharing** to products/events/vendors using the pattern M17 already established, and surface saves consistently. It is not a new engagement system.

D37 keeps this deliberately one-directional: following a vendor is a **commerce subscription**, not a social graph. There are no followers lists, no public profiles, no feed of what other people did.

**Type:** `[CODE]`.

## 2. Objective & scope
A customer can follow a vendor, save anything, and share anything with a correct preview.
**Non-goals:** public profiles, follower counts *visible to other customers*, activity feeds, friend graphs, gifting.

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_vendor_follows.sql` — **verify next-free at branch time** (expected `0085`)
- `services/api/app/routers/follows.py` (new; auto-discovered)
- `services/api/app/services/social/{follows,share}.py` (new)
- `apps/customer/**` — follow button, saves surface, share sheet
- `apps/customer/app/[locale]/(share)/**` — reuse the M17 share-page pattern
- `packages/i18n/messages/en/{common,product,vendor}.json`
- Tests

## 4. Implementation spec
- `vendor_follows (user_id, vendor_id, created_at, primary key (user_id, vendor_id))` — **idempotent by unique key**, exactly as M17 did for likes: attempt the insert unconditionally and let the constraint absorb the double-tap. Never read-then-write, which races.
- FORCE RLS: a user reads and writes only their own follow rows. **A vendor may see an aggregate count of their own followers, never the identities** — that is the line between a commerce subscription and a social graph, and it is also the DPA-safe default.
- **Follows are a notification opt-in**, and the value only lands when something is sent. Wire "new listing from a vendor you follow" into the **existing `notification_outbox`** with digest-friendly batching (n8n already runs nudges/digest workflows). Respect existing consent/quiet-hours rules; never WAHA.
- **Sharing**: canonical URL + OG/Twitter tags for product, event, vendor storefront — mirroring the clip share page. Server-rendered so a WhatsApp link preview resolves without JS. Keep the payload tiny: a shared link is usually opened on a phone on mobile data, and the preview image is the whole first impression.
- Saves: one consistent affordance across PDP/PLP/clips, backed by the **existing** wishlist tables — do not add a parallel table.

## 5. Security / conventions
Every mutation: authz + rate limit + strict validation. Follower identities are never exposed. Share URLs must not leak private ids or a wholesale-only listing (see **D36** — a wholesale-only subject must 404 for an ineligible viewer, share link or not).

## 10. Tests (RUN before reporting)
- `test_follow_is_idempotent_under_double_tap`
- `test_user_cannot_read_another_users_follows` (RLS)
- `test_vendor_sees_count_not_identities`
- `test_new_listing_notification_enqueued_to_outbox_for_followers`
- `test_share_page_renders_og_tags_without_js`
- `test_share_link_to_wholesale_only_listing_404s_for_consumer` (D36 interaction)
- `test_saves_use_existing_wishlist_tables` (no new table)
- Migration replay; RLS matrix; route bundle sizes within budget; `pnpm lint typecheck test build`.

## 11. Acceptance criteria / DoD
- [ ] Follows idempotent, RLS-isolated, identities private.
- [ ] Follow drives an actual outbox notification.
- [ ] Share pages SSR with correct previews for product/event/vendor.
- [ ] D36 respected on every share path.
- [ ] No new saves table; no public profile or feed introduced.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P14 — Saves, follows, sharing
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** … · **EXCERPTS:** the idempotent insert + an OG head · **QUESTIONS:** …
