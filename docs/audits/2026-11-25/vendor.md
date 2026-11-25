# Vendor app audit (apps/vendor, master)

Method: code read only. https://vendor.vergeo5.com was blocked by the agent proxy (403), so nothing logged-out was observed. Not covered in depth: events/tickets, services/packages, clips, extras, plan, intake, offers, and the onboarding internals (the onboarding error handling I did read looked sound). All paths below are under apps/vendor/app/[locale]/ unless noted.

## Top 15 issues, ranked by seller impact

1. **Pickup PIN fallback needs the full order UUID.**
   - File: scan/_components/pin-fallback.tsx. The i18n label is "Order ID / Paste or type order ID".
   - When the camera or QR fails, a Zambian seller must type a 36-character UUID. The "recent verifications" list shows only an 8-character prefix.
   - Fix: accept the 8-character short code the buyer sees, or search the seller's own ready-for-pickup orders by short code. Show a picker of orders awaiting pickup, then ask for the 6-digit PIN.

2. **The stock editor is unstyled and written in jargon.**
   - File: listings/[id]/edit/_components/stock-editor.tsx. Strings are in packages/i18n/messages/en/vendor.json under listings.manage.stock.
   - It uses bare `<input>`, `<button>` and `<select>` with no classes, so there is no 44px touch target and no focus style. The error message has no colour.
   - Copy is technical: "sale steps", "each step is {step}/1000 of that unit", "Branch provisioning requires the stock owner".
   - The success message prints a raw operation id: "Operation: {id}". Branch options fall back to the raw `location_id`.
   - Fix:
     - Use the shared ui Input, Button and Select, and FormField for the +/- change.
     - Show "You have 12 in stock. Add or remove: [ ]".
     - Drop the id from the success text and say "Stock updated: 5 to 8".
     - Hide the unit-step maths unless the unit is fractional.
     - Style the alerts with text-danger.

3. **Error text uses `text-error`, which is not a token.**
   - Files: returns/_components/returns-queue.tsx:~99 and reviews/_components/vendor-reviews-queue.tsx:126.
   - theme.css defines only `--color-danger`, so these failures render in plain body colour and are easy to miss.
   - Fix: change to `text-danger`. Add a lint or grep guard for unknown colour tokens.

4. **Returns: the seller must accept a refund or contest with no reason, no evidence and no confirmation.**
   - File: returns/_components/returns-queue.tsx.
   - Each card shows the item, the 8-character order prefix, the refund amount and "N evidence". It does not show the buyer's reason or the evidence photos, and the lane/status is not shown.
   - Accept (money out) and Contest fire immediately with no confirm step.
   - The Contest button has `loading={false}`, so there is no spinner.
   - After a successful action the row is removed, so the seller never sees the outcome.
   - The loading state is a bare `<p>`, and there is no VendorPage wrapper.
   - Fix:
     - Show the reason and evidence thumbnails, or link them from the order detail.
     - Add a confirm sheet for Accept and Contest ("You will refund K120 to the buyer").
     - Show a toast on success.
     - Use VendorPage and ListSkeleton.

5. **Jobs: the data the seller needs is fetched but not shown, and the status lies.**
   - File: jobs/page.tsx.
   - The type has `budget_band_min/max_ngwee` and `preferred_date`, and neither is rendered. A seller can't price a quote without the budget or know when the job is wanted.
   - Any `own_quote` shows the "Quoted" badge. Only `status === "submitted"` shows quote details.
   - If the quote is accepted, rejected, withdrawn or expired, the badge still says "Quoted" and the card offers "Send quote" again, which returns a 409 "already quoted".
   - The quote form state (amount, message) is shared across all jobs.
   - Fix:
     - Show the budget range and preferred date.
     - Map the status of `own_quote` to a badge (Accepted, Declined, Withdrawn, Expired) and hide the CTA unless a new quote is allowed.
     - Key the form state by job.

6. **RFQ: the seller can't tell what is being asked, and some statuses show raw keys.**
   - File: rfq/page.tsx.
   - Each thread shows only `requested_details`. It does not show which listing or service, the buyer, the quote validity, or when it expires. `listing_id` and `service_id` are fetched but unused.
   - Only four status keys exist in vendor.json (pending, quoted, accepted, rejected). The API can return others such as expired, cancelled or closed, which would render a missing-key error or the raw key.
   - "Decline" has no confirm step.
   - The quote form is shared state, and the layout is a bare `<Spinner>` outside VendorPage.
   - Fix:
     - Resolve and show the item title and image.
     - Show "Valid until {date}".
     - Add a default/fallback status label.
     - Add a confirm for Decline.
     - Use the same loading pattern as the other pages.

7. **Raw order id shown on order detail.**
   - File: orders/_components/action-bar.tsx:475, `<p className="text-xs text-text-3">{order.id}</p>`.
   - The seller sees a full UUID under the status, while other screens (returns, disputes) show an 8-character code. This is inconsistent and unusable when the buyer quotes the order number over the phone.
   - Fix: show the same short code everywhere. Add one shared helper, `formatOrderCode`, for orders, returns, disputes and scan.

8. **Payouts history shows a Lenco reference instead of a date.**
   - File: payouts/_components/payouts-view.tsx:~224. `created_at` exists in the client type and is not rendered.
   - The row shows an amount, the raw `lenco_reference` (for example `pay-…`) and a status.
   - Fix: show the date and a plain-language status line ("Sent to your MTN 09xx…"), and keep the reference behind a tap to copy.
   - Related: the "PDF reports are coming soon" line is placeholder copy for a feature that isn't built.
   - Related, contradictory pilot message:
     - Payouts show a "not switched on during pilot" page.
     - Home still pushes "Add payout method" and the shop-status card shows payout as missing.
     - Settings hides the method link while the pilot flag is off.
   - Fix: gate the home task and the status card on `isVendorPayoutsEnabled()`, or make the copy say "optional during pilot".

9. **"Shop live" is the same thing as "ID verified".**
   - File: orders/_components/order-card.tsx:~815-870 (`const shopLive = kycApproved`).
   - It ignores whether the seller has any live listings, whether payouts are set, or whether a profile exists. A seller with zero listings is told their shop is live.
   - Home takings show a "Live / Quiet" delta pill, which means nothing to a seller.
   - Analytics failures are swallowed, so the stats show "—" with no explanation.
   - Fix:
     - Compute shopLive from KYC approved plus at least one active listing.
     - Replace the delta pills with real comparisons ("K0 today") or remove them.
     - Show a small "couldn't load" hint when analytics fail.

10. **No loading.tsx and only one error.tsx for 54 routes.**
    - Every page waits for client fetches. Pages that handle it ad hoc: jobs/rfq (bare spinner), returns (plain `<p>`), reviews, and settings (collab fetch fails silently).
    - A route-level failure (SSR or chunk load) shows the single global boundary with no seller-friendly context.
    - Fix: add app/[locale]/loading.tsx with ListSkeleton, plus an error.tsx for payouts, orders, listings and events so a failure keeps the nav and offers retry and a link home.
    - Also standardise on one helper for session-loading, error, retry and empty states (VendorErrorState and ListSkeleton exist, and some pages ignore them).

11. **Listings list has no search, filter or pagination, and two "Create listing" buttons.**
    - File: listings/_components/listings-manage-list.tsx:~108-125 and :~135.
    - `listListings()` loads everything. A seller with 200 items scrolls an unfiltered list.
    - The header action and the full-width bar below it are the same link.
    - Pause and Resume sit behind the edit page.
    - Fix: add a search box and status chips (All, Live, Draft, Paused, Out of stock) and a quick "Pause" toggle on the card. Remove the duplicate CTA.

12. **Home loads six requests on mount and the dashboard component lives in a 1,045-line file.**
    - Files: orders/_components/order-card.tsx (VendorHomeView plus the orders queue plus the card), page.tsx.
    - Payout balances, the full listings list (only to count products in review), analytics, KYC and the dashboard are fetched separately.
    - The whole listings payload is downloaded just to count `pending_moderation`.
    - Order-card code and home code ship together on every orders route.
    - Fix:
      - Return `products_in_review` and `payout_msisdn_set` from /dashboard.
      - Split VendorHomeView into home/vendor-home.tsx, with the queue and the card in separate files.
      - Lazy-load the offer/QR bits.

13. **Reviews and disputes show raw or half-raw identifiers and sparse context.**
    - Files: disputes/_components/disputes-list.tsx:92 and dispute-detail.tsx:162 (`order_id.slice(0, 8)`, same pattern as the returns screen, no title or date), reviews/_components/vendor-reviews-queue.tsx (error token, see #3).
    - Fix: show the item title, the buyer's first name and the date, and use the shared order code helper. For reviews, show the product being reviewed and the star rating up top.

14. **Business switcher and settings are thin.**
    - Files: _components/business-switcher.tsx:75-77, settings/_components/settings-view.tsx.
    - Settings is only links (notifications, profile). There is no WhatsApp number or notification preference, and "WhatsApp" links to the profile page, not to a control.
    - Account shows only the email or phone. Sign-out has no confirmation, and a failed collab status fetch is silently ignored.
    - Fix: add direct toggles for WhatsApp order alerts and a quiet-hours note, and show the shop name and plan.

15. **Typography is too small for low-literacy, outdoor phone use.**
    - 137 uses of `text-xs` across vendor components. Examples: order id, status hints, stock help, hint lines under photos and forms.
    - Stock editor (#2) and returns have no touch-friendly spacing.
    - Fix: use `text-sm` minimum for anything the seller must read to act; reserve `text-xs` for timestamps. Prefer icon + one-line helper text over paragraphs.

## Batches (exclusive file ownership)

### Batch A: Orders, scan, returns, home (money and fulfilment)
Issues #1, #3 (returns), #4, #7, #9, #12
1. scan/_components/pin-fallback.tsx
2. scan/_components/recent-verifications.tsx
3. scan/_components/scan-view.tsx
4. scan/_lib/pickup-client.ts
5. returns/_components/returns-queue.tsx
6. returns/page.tsx
7. orders/_components/action-bar.tsx
8. orders/_components/order-card.tsx (split out the home view)
9. _components/vendor-shop-status-card.tsx (shop live logic)
10. _lib/home-tasks.ts
11. _lib/order-code.ts (new shared helper)
12. page.tsx (home)
13. services/api: dashboard endpoint additions (if allowed)
Also edit the matching keys in packages/i18n/messages/en/vendor.json (see rule below).

### Batch B: Seller requests, payouts, trust
Issues #3 (reviews), #5, #6, #8, #13
1. jobs/page.tsx
2. rfq/page.tsx
3. payouts/_components/payouts-view.tsx
4. payouts/_components/payouts-pilot-notice.tsx
5. payouts/_components/payout-method-form.tsx
6. disputes/_components/disputes-list.tsx
7. disputes/_components/dispute-detail.tsx
8. reviews/_components/vendor-reviews-queue.tsx
9. lib/payouts-availability.ts
10. settings/_components/settings-view.tsx
11. _components/business-switcher.tsx

### Batch C: Listings, stock and global states
Issues #2, #10, #11, #14 (settings split from B only if needed), #15
1. listings/[id]/edit/_components/stock-editor.tsx
2. listings/_components/listings-manage-list.tsx
3. listings/_components/listing-product-status.tsx
4. loading.tsx (new, app/[locale])
5. error.tsx (per-route additions)
6. _components/async-state.tsx
7. _components/vendor-skeletons.tsx

i18n rule: packages/i18n/messages/en/vendor.json (and the bem/nya/fr copies) is shared by all three batches. Give one agent ownership of that file, or have each batch send its new keys as a patch to be merged by the coordinator.

## Positives
- Onboarding error handling is thorough (auth failures never fall back to a fake draft, drafts survive on-device).
- Orders have an offline cache.
- Reject-order flow requires a reason.
- Money formatting consistently goes through formatK.
