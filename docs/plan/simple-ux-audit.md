# Simple-UX literacy audit — customer and vendor apps (2026-11-13)

**Goal (founder):** a shopper or seller who left school early should be able to buy, sell and
follow an order without help. Simple on the screen; the backend does the hard work.

**North star:** Convergeo is a street of shops. Each business's own name, logo and story leads
(like the painted signs on a Lusaka shopfront row); Convergeo is the calm street around them,
not the loudest sign.

**Target:** plain English at about a 10–12-year-old reading level. Short sentences (aim ≤ 15
words). One main action per screen. Familiar words. Icons next to text, never icons alone.
Tap targets ≥ 44px. Errors always say what to do next.

## How this audit was done

- Read every customer and vendor journey's page and component code under `apps/customer/app`
  and `apps/vendor/app`, and all English copy in `packages/i18n/messages/en/*.json`
  (~7,250 strings; admin and legal were out of scope).
- Ran both apps locally (`next dev`, no backend: API pointed at a closed port) and took
  360×800 Playwright screenshots: see
  `/tmp/claude-0/-home-claude/ad6c43ff-0022-5f17-8a8e-13729d2e4861/scratchpad/simple-ux/before/`.
  With no backend, data screens (product, cart contents, orders, vendor dashboard) show their
  loading, empty or sign-in states. Those states were audited as shown. The populated states
  were audited from code and copy.
- A jargon count over English copy (customer + vendor namespaces): `escrow` 66, `vendor`
  (customer-facing) 40+, `fulfil(l)ment` 26, `KYC` 28, `SKU` 17, `payout` 52, `moderation` 22,
  `RFQ` 3, `USSD` 6, `T1/T2` tiers on seller screens.

## Glossary (use these words everywhere)

| Instead of                           | Say                                                  |
| ------------------------------------ | ---------------------------------------------------- |
| Cash on delivery (COD)               | **Pay when it arrives** (pay cash)                   |
| Escrow / held in escrow              | **We keep your money safe** until you get your order |
| Vendor (to shoppers)                 | **Seller** (or the shop's own name)                  |
| Fulfilment / fulfillment             | **Delivery or pickup**                               |
| Listing                              | **Product** (seller app: "product" or "item")        |
| OTP / verification code              | **SMS code**                                         |
| RFQ / quote request                  | **Ask for a price** / price request                  |
| KYC / T1 verification                | **ID check**                                         |
| T2 / PACRA + TPIN                    | **Business papers check**                            |
| Payout                               | **Money sent to you** / your money                   |
| Payout method                        | **Where we send your money**                         |
| SKU                                  | **Item code**                                        |
| Dispute                              | **Problem report**                                   |
| Courier                              | **Rider**                                            |
| Dispatch / ship                      | **Send out**                                         |
| USSD prompt                          | **A message on your phone asking for your PIN**      |
| Lead time                            | **Days to make it**                                  |
| MOQ / minimum order quantity         | **Smallest order**                                   |
| GMV                                  | **Sales**                                            |
| Ledger, auditable record, moderation | (drop it — say "our team checks it")                 |

## Customer journeys

### 1. Home (`(shop)/page.tsx`, `catalog.home.*`)

- **Wrong promise:** the trust strip says "You pay → Held by Convergeo → Released on delivery"
  while the pilot is pay-when-it-arrives only. A shopper reads it as "pay first". Change the
  three steps to _Order on your phone → The seller sends it → Pay when it arrives_.
- **Jargon:** "escrow", "when the listing supports it", "eligible orders", "status you can
  review". Rewrite as short plain lines.
- **Icon-only header buttons (360px):** a monitor icon (theme), a person icon and a cart icon
  with no words. The monitor icon means nothing to most people. Account is already a labelled
  tab in the bottom bar; display settings are in the footer. **Fix:** on phones, show only the
  cart, with the word "Cart" under the icon.
- **Too many choices above the fold:** social icons + language + three icons + search + strip +
  carousel with five slides + two buttons. Recommend (not done here — design change): keep
  search and one hero.
- "Invite-only seller beta" box: "Public self-service signup is not open yet" → plain words.

### 2. Search (`(shop)/search`, `search.*`)

- "Showing keyword matches (semantic search unavailable)" — meaningless to a shopper. Say
  "Showing simple matches. Results may be less exact right now."
- Tab "Vendors" → "Shops".
- Empty results already offer suggestions; add one clear next step ("Try a shorter word").

### 3. Category (`(shop)/c/[...slug]`, `catalog.plp.*`)

- "No listings found" / "Listings unavailable" → "Nothing here yet" / "We couldn't load this
  page", with one action (try again, or search).

### 4. Product page (`(shop)/p/[slug]`, `catalog.pdp.*`)

- **Extra step the backend can default:** when a product is held at exactly one pickup branch,
  the shopper must still open a dropdown and pick that only branch before "Add to cart" turns
  on. **Fix:** pre-select the only branch (presentation only — the same `pickup_location_id`
  is sent; the add-to-cart gate is unchanged).
- Jargon: "Fulfilment", "Lead time", "Weekly capacity", "Product class", "Sold in increments
  of", "Listing details", "Sold by this vendor only". Rewrite.
- Report form: "helps moderation" → "helps our team check it".

### 5. Cart (`(shop)/cart`, `checkout.cart.*`)

- "Vendor subtotal qualifies for free Lusaka delivery — zone confirmed at checkout" (14 words,
  three ideas). → "Free delivery in Lusaka from this seller."
- "Applies inside Lusaka delivery zones only… Zone fees still apply below the threshold."
  → two short sentences.
- "Each seller is checked out with its own fulfilment choice." → "You choose delivery or pickup
  for each seller."
- Merge-recovery copy ("Your guest cart and account cart disagree") → plain words.
- "Proceed to checkout" → "Go to checkout".
- Empty cart already has one action ("Continue shopping") — keep; shorten body.

### 6. Checkout — pay when it arrives (`(shop)/checkout`, `checkout.checkout.*`)

- Steps "Contact · Delivery · Payment · Review": fine. Step 3 already hides methods the
  backend does not offer (pilot = cash only) — good. When only one method is offered, the
  shopper still sees a one-option chooser; acceptable but the title "How would you like to
  pay?" → "How you will pay".
- "Cash on delivery" label → **"Pay when it arrives"** (with the word cash in the help line).
- Contact step: "Verify & continue", "one-time code", "Payer mobile number", "USSD payment
  prompt". → "Check code and continue", "SMS code", "Phone number that will pay", "a message
  on your phone asking for your PIN".
- Review: "How your payment is protected / Held by Convergeo" (online only) → plain words.
- Card copy: "PCI compliant hosted checkout", "Lenco's secure hosted page" → "Safe card page
  run by Lenco, our payment partner. We never see your card number."
- Pending/approval: "We received a payment signal… check your order status for escrow
  updates" → "Your payment is being checked. Don't pay again. We'll update your order."
- Errors: most say what to do. Fix the few that don't ("Verification failed. Try again." →
  "That didn't work. Check the code and try again.").

### 7. Sign-in / sign-up / SMS code (`(auth)/*`, `auth.*`)

- "Phone sign-in uses a verification code. If you cannot receive one, use email instead."
  → "We'll send you an SMS code. No code? Use email instead."
- "Enter verification code", "Verify code" → "Enter the SMS code", "Continue".
- "Too many authentication requests" → "Too many tries. Wait {seconds} seconds, then try
  again."
- Welcome screen: "we'll personalize your home feed" → "We'll show you more of what you like."

### 8. Order tracking (`account/orders/*`, `orders.*`)

- Timeline mostly plain already (UX pass 4). Remaining jargon: "Pay the vendor on delivery",
  "Vendor confirmed your order", "Payment released to vendor", "Funds were released to the
  vendor after fulfilment", "Dispatch details", "Courier reference", "Receipt & invoice".
- Confirm-received: "Confirming releases payment from Convergeo escrow to the vendor" →
  "Only tap this when you have everything. We then pay the seller."
- Problem/return/dispute screens: "dispute", "investigate", "contest", "lane", "admin review"
  → "problem report", "look into it", "disagree", "our team is checking".
- Empty orders: "When you buy from Convergeo vendors, your orders and tracking will appear
  here." → "Things you buy will show here."

### 9. Account (`account/*`, `account.*`)

- "Manage listings, orders, and payouts in the vendor portal" → "Sell on Convergeo? Open your
  seller app."
- Delete-data confirm "verify with OTP" → "We'll send you an SMS code to check it's you."
- Addresses empty: "Add a landmark and GPS pin so vendors can find you faster." → "Add a place
  people know, like a church or school, so the rider can find you."

### 10. Services / price requests (`(shop)/services*`, `services.*`)

- Post-a-job is already plain and short. Fix "RFQ sent to # vendors" → "Price request sent to
  # sellers", "formal price" → "price", "{pct}% deposit… balance" → "Pay {pct}% now. Pay the
  rest when the work is done."
- Booking note uses the arrow escrow chain — reword plainly.

### 11. Events and tickets (`(shop)/events`, `account/tickets*`, `events.*`)

- "Pending transfer to {phone}" → "Waiting for {phone} to accept this ticket".
- Ticket QR screens are icon + code — good. Keep.

## Vendor journeys

### 12. Sign-up / invite (`(auth)/accept-invite`, `onboarding` intro)

- "You are finishing a seller invite application. Catalogue, payouts, and the vendor dashboard
  stay locked until Convergeo approves your KYC and grants seller access." (31 words, 4
  jargon terms) → "Finish these 3 steps. We check your ID, then you can start selling."
- Meta copy: "T1 KYC", "admin approval" → plain.

### 13. Verification (`onboarding`, `onboarding/status`)

- Step name "T1 verification" → "Check your ID". "NRC" is familiar in Zambia — keep, but say
  "NRC (green ID card)" once where the photo is taken.
- "We match your mobile-money name" → "Your name must be the same as on your mobile money."
- Status: "T1 KYC approved", "Upgrade to T2 (PACRA + TPIN)" → "Your ID is checked. You can add
  products now." / "Add business papers (PACRA, TPIN)".
- Rejected: one clear button "Fix and send again" — already present; reword.

### 14. Add a product (`listings/new`, `listings.*`)

- Heaviest screen. Three tabs ("Catalog", "New product", "Quick list") + "Product class A–E"
  - "Branded SKU / Branded variant / Commodity / generic" + "Smallest sale increment" +
    "Minimum increments per order" + "Fulfilment" + "Lead time" + "Weekly capacity" + "Tracked
    quantity". A market trader cannot answer these.
- **Copy fix (done):** tabs → "Find it", "New product", "One-off item"; classes → "A. Brand
  product (same everywhere)", "B. Brand product with sizes or colours", "C. Everyday goods (no
  brand)", "D. One-of-a-kind item", "E. Made for each customer"; SKU → item code; lead time →
  days to make it; capacity → how many you can make each week.
- The 60-word "Product details" help paragraph → 3 short lines.
- **Recommended next (not done — changes form behaviour):** default Product class from the
  chosen tab and category so most sellers never see it; hide "Smallest sale increment" unless
  "Sold by" is not "Each"; ask "Do you have it now, or do you make it?" instead of the
  Fulfilment + Stock pair.

### 15. Orders inbox (`orders`, `vendor.queue.*`)

- Good: filter chips + one-tap actions + confirm sheet. Copy: "Filter and fulfil orders with
  one-tap actions" → plain; "Packing" chip OK.
- Empty: "No orders in this view." → "No orders here right now." with "Back to home".

### 16. Order detail (`orders/[id]`, `vendor.orders.*`)

- Status buttons: "Start packing", "Mark shipped", "Reject order" — OK, but "Mark shipped" →
  "Mark as sent". "Paid — held in escrow" → "Paid — we keep it safe until delivery".
  "SKU {sku}" → "Item code {sku}". "Tell the customer why you cannot fulfil this order" →
  "Tell the buyer why you can't do this order."
- "That action is not available for this order." → add what to do: "Refresh the page to see
  the latest order status."

### 17. Payouts notice (`payouts`, `vendor.payouts.*`)

- "Balances come straight from the ledger — no separate bookkeeping." and "These figures match
  your ledger accounts exactly." — no meaning to a seller. Remove the jargon.
- "Held in escrow / Released & available / Paid out" → "Waiting for delivery / Ready to send
  to you / Sent to you".
- "We re-verify via Lenco before saving" → "We check the name on the number before saving."
- Payout-paused notice → "We are not sending money yet. Your sales are still counted."

### 18. Vendor home (`page.tsx`, `vendor.home.*`) and menu (`vendor.shell.*`)

- "GMV", "Confirmed revenue", "auditable record" → "Sales", "Money from confirmed orders",
  (drop). KYC banner → "Finish your ID check".
- Menu groups "Operate / Sell & grow / Business" and items "Clips", "Intake",
  "Disputes" → "Daily work / Sell more / My business", "Videos", "Problems".

## Cross-cutting findings

1. **Numbers and money:** all money goes through `formatK()` (K1,234.56) — good. Seller price
   field help "Enter kwacha and ngwee, e.g. 1,234.56" is fine. Count copy uses ICU plurals —
   good.
2. **Errors without a next step:** ~20 generic "Action failed. Try again." style strings in
   vendor copy. Rewritten to say what to check (connection, refresh, contact support).
3. **Icons:** bottom nav is icon + label (good). Mobile header used bare icons (fixed for cart;
   duplicate account/theme icons removed on phones). Empty and error states use the shared
   `EmptyState`/`ErrorState` icons (good).
4. **Tap targets:** header actions are `min-h-11` (44px) — good. OTP digit boxes are 44px —
   good.
5. **Storefront identity (north star):** product cards and PDP say "Sold by {vendor}" — keep
   the shop's own name front and centre; never replace it with "a vendor". Shop pages
   (`/v/[slug]`) already lead with logo, cover and story.

## What Phase 2 changed (this branch)

- English copy rewritten to the glossary across `checkout`, `orders`, `auth`, `catalog`,
  `search`, `account`, `services`, `events`, `directory`, `common` and the seller app's
  onboarding, home, listings, orders, queue, payouts and menu copy. Keys unchanged; FR and ZH
  updated to match; Bemba/Nyanja drafts appended to `PHASE1_NATIVE_REVIEW.md` for native
  review (bem/nya JSON untouched).
- Product page pre-selects the only pickup branch.
- Phone header: cart shows the word "Cart"; duplicate theme and account icons hidden on
  phones (still in the bottom bar and footer; still in the header on tablet and desktop).
- No API, money, state-machine or business-rule changes.
