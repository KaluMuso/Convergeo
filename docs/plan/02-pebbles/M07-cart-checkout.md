# M07 — Cart & Checkout — Pebbles

8 pebbles. All money integer ngwee end-to-end; totals computed server-side only (client displays). Checkout ≤4 steps at 360px. Owns i18n namespace `checkout` (+ `cart` keys inside it).

---

### M07-P01 — Cart domain & API `M`
**Deps:** M03-P02/P04, M04-P02 · **Files:** migration `supabase/migrations/00xx_carts.sql` (`carts` guest-token|user-owned, `cart_items`), `services/api/app/routers/cart.py`, `app/services/cart/` (merge, grouping, totals), `services/api/tests/test_cart.py`
Guest cart (signed httpOnly token) + authed cart; **merge on login** (qty-sum, price refreshed, conflicts surfaced); per-vendor grouping with per-group delivery eligibility; MOQ enforcement for wholesale lines; server-computed totals (ngwee).
**AC:** merge preserves both carts' items; MOQ-violating qty rejected with i18n error; RLS: only owner reads cart.
**Tests:** merge matrix (guest-only, both, dupes); MOQ boundaries; tier-price selection by qty; authz.

### M07-P02 — Stock revalidation & reservations `L`
**Deps:** P01 · **Files:** `services/api/app/services/stock/` (claim/release/sweep), `app/routers/internal_stock_sweeper.py` (cron endpoint), `services/api/tests/test_reservations.py`, `infra/n8n/reservation-sweeper.json`
Reservation claim at checkout entry: `UPDATE vendor_listings SET stock_qty = stock_qty - x WHERE id=… AND stock_qty >= x` style atomic claim + `stock_reservations` row (TTL from config, 10–15min); release on abandon/expiry (sweeper restocks); price/stock revalidation on every cart view + checkout step with change notices.
**AC:** **two concurrent buyers cannot oversell the last unit** (concurrency test); expiry restocks exactly once; always_available listings skip reservation.
**Tests:** race test (threaded double-claim), sweeper idempotency under re-run, TTL boundary, revalidation notice payloads.

### M07-P03 — Cart UI `M`
**Deps:** P01, M02 · **Files:** `apps/customer/app/[locale]/(shop)/cart/page.tsx`, `(shop)/_components/cart/` (line items, vendor groups, qty stepper, price-change/stock notices, mini-cart drawer), wire add-to-cart into PDP buy-box stub (`(shop)/_components/pdp/buy-box.tsx` — **modify; sequence after M05-P03's wave**), `packages/i18n/messages/en/checkout.json` (cart section)
Vendor-grouped cart with per-group subtotals + delivery hints, free-delivery-≥K200 progress nudge, stock/price change banners, empty state.
**AC:** all totals from server; 360px one-handed; guest cart persists across sessions.
**Tests:** render states (empty, changed prices, out-of-stock line); optimistic qty update rollback on API error.

### M07-P04 — Checkout steps 1–2 (contact & fulfilment) `L`
**Deps:** P02, M04-P04/P05 · **Files:** `apps/customer/app/[locale]/(shop)/checkout/page.tsx` (stepper shell), `checkout/_components/step-contact.tsx`, `step-fulfilment.tsx`, `services/api/app/routers/checkout.py` (session init + step validation endpoints)
Step 1: contact — logged-in skip; guest phone + inline OTP (M04 flow embedded). Step 2: per-vendor-group fulfilment — Lusaka delivery (zone lookup by GPS/landmark → fee from `delivery_zones`, free ≥K200/group) or pickup (vendor location w/ landmark + hours); reservation claimed on checkout entry with **visible countdown**.
**AC:** zone fee correct per seed zones; mixed delivery+pickup groups supported; countdown expiry returns to cart with notice.
**Tests:** zone resolution edge (outside zones → pickup-only), fee math ngwee-exact, guest-OTP-in-checkout flow.

### M07-P05 — Checkout steps 3–4 (payment method & review) `M`
**Deps:** P04, M03-P07 · **Files:** `checkout/_components/step-payment.tsx`, `step-review.tsx`, `services/api/app/routers/checkout_payment.py` (method validation)
Step 3: method select — MoMo (rail MTN/Airtel; Zamtel hidden pending F9a; payer number w/ +260 validation), card (widget explainer), **COD gated ≤K500 total** (config `cod_cap_ngwee`) with clear ineligibility message. Step 4: review — line items, fees, totals, escrow trust copy ("You pay → Held by Vergeo5 → Released on delivery"), T&C consent checkbox.
**AC:** COD option hidden/disabled above cap (server re-validates); rail selection persists; review totals match server calculation exactly.
**Tests:** COD boundary (=K500 allowed, +1 ngwee not), number validation, method server re-validation (tampered client).

### M07-P06 — Atomic order creation `L`
**Deps:** P05, M09-P01, M03-P04/P07 · **Files:** `services/api/app/services/orders/create.py`, `app/routers/orders_create.py`, `services/api/tests/test_order_creation.py`
Single transaction: checkout_group + per-vendor `orders` split + order_items (+kind detail rows) + commission-rate snapshot (bps from config at purchase time) + fees; consumes reservations; **idempotent via client idempotency key** (retry returns same group); emits `order.placed` events to outbox.
**AC:** partial failure rolls back everything; duplicate submit returns identical group (no double order); totals = Σ items + fees, ngwee-exact; commission snapshot immutable thereafter.
**Tests:** idempotency replay, rollback injection, multi-vendor split math, snapshot correctness vs config change after purchase.

### M07-P07 — Order-pending & USSD wait UX `M`
**Deps:** P06, M08-P04 · **Files:** `apps/customer/app/[locale]/(shop)/checkout/pending/[groupId]/page.tsx`, `checkout/_components/ussd-wait.tsx`, `payment-failed.tsx`, `services/api/app/routers/payment_status.py` (customer-scoped status poll)
Post-submit screen: "Check your phone — approve the K___ prompt" per rail with rail-specific helper copy; status poll (2s→backoff); states: waiting → success (→ order confirmation) / failed / expired (retry with same order, new payment attempt) / user-cancelled; COD path skips to confirmation with COD instructions.
**AC:** retry creates new payment attempt against same order (no duplicate order); poll authz-scoped; timeout guidance actionable.
**Tests:** state-transition renders; poll authz (other user 403); retry idempotency.

### M07-P08 — Abandoned-checkout events & funnel analytics `S`
**Deps:** P06, M14-P01 · **Files:** `services/api/app/services/analytics/funnel.py`, funnel event emission patches confined to `app/services/cart/events.py` + `app/services/orders/events.py` (new files), migration `00xx_funnel_events.sql`
Server-side funnel events (cart_add, checkout_start, step_complete, payment_start, order_placed, abandoned via sweeper) → analytics table + outbox `abandoned_checkout` event (**flag-gated off** per D2 scope — n8n workflow ships in M14-P06 disabled).
**AC:** abandonment detected on reservation expiry with cart snapshot; events schema stable for GA4 mirror (M16-P05); flag off = no notification.
**Tests:** funnel sequence integrity; abandonment trigger; flag gating.
