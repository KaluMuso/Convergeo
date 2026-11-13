# Convergeo — Agent 2: Adversarial Logistics Failure Register

**Author:** Agent 2 (Adversarial Logistics Investigator) · **Date:** 13 Nov 2026 (Lusaka pilot go-live day)
**Scope:** brief §2 Agent 2 (27 listed scenarios) + 33 Zambia/Lusaka-specific scenarios + §7 automation boundaries + §9 security/RBAC.
**Method:** read-only. Every "status in code" claim cites the pilot tree at `/home/claude/wt-logistics-audit` (merge `a813f983`). Nothing was modified, run against a database, or deployed. Where behaviour depends on what is switched on in production (n8n workflows active, WhatsApp templates approved, SMS enabled), the row says **verify live** rather than guessing.

---

## 0. How to read this register

- **IDs:** `B01–B27` = the 27 scenarios the brief lists. `Z01–Z33` = additional Zambia/Lusaka scenarios. `C01–C16` = code defects found while checking status; these are cross-referenced from the scenarios they cause.
- **Score:** Likelihood (1–5) × Impact (1–5). Two scores: **P** = 30-day Lusaka pilot (COD-first, manual courier dispatch, a handful of vendors, 5–30 delivery orders/day), **S** = scale (hundreds of orders/day, prepaid on, intercity live).
- **Status in code:** **Handled** (prevention + detection exist), **Partial** (some guard exists, gaps listed), **Not handled** (nothing in code; ops-only today).
- **Money magnitudes** are rough and built on editable assumptions, not verified Zambian prices: AOV K150–500 (COD cap K500), customer delivery fee K30/K45/K65 (seed, `0008_config.sql`), courier cost per Lusaka trip K40–80 (ride-hail reference ranges in `docs/ops/lusaka-delivery-reference-prices.md`, secondary sources), commission 5–12%.
- **"Automatable?"** in the response field: **Auto** = deterministic rule/sweeper can resolve; **Auto+H** = system detects and acts provisionally, a human confirms; **H** = needs a human judgement every time.

---

## 1. Code defects that change the risk picture (read first)

These were found while checking scenario status. Several are live on day one of a COD pilot, so they rank above most operational scenarios.

| ID | Defect | Evidence | Pilot impact |
|---|---|---|---|
| **C01** | **COD orders auto-complete without the cash being booked, and after that the cash can never be booked.** The hourly auto-confirm job selects every `delivered` order older than `release_after_delivered_hours` (default 48 h) with no `cod = false` filter and moves it to `completed`. `confirm_cod_collection` only accepts `delivered` unless a collect transaction already exists, so after auto-confirm it raises `cod_invalid_status`. The COD receivable is also never opened at order time (`record_cod_receivable` is only called lazily inside confirm/refuse). Handover-code delivery and COD collection are two separate manual admin actions; nothing links them. | `services/api/app/routers/internal_order_jobs.py` `_list_auto_confirm_candidates` (no COD filter), `_process_auto_confirm`; `services/api/app/services/payments/cod.py` `_COLLECTABLE_STATUSES`, lines 375–384, `record_cod_receivable` callers (only lines 421, 509); `services/api/app/services/escrow/release.py:32` (48 h). Workflow `infra/n8n/order-jobs.json` (hourly) — **verify live whether active.** | Every COD order whose collection is not confirmed within 48 h disappears from the ledger: no receivable, no commission, no vendor payable. The books under-state cash held by riders. **Critical.** |
| **C02** | **COD ledger assumes the platform holds the cash, but nothing records who physically holds it.** `cod_collected` debits `platform_cash` and credits `vendor_payable` (net). There is no courier/rider cash-custody or remittance record. The **vendor** role can confirm COD collection, and COD is allowed on **pickup** orders, where the vendor takes the cash at the counter. In both cases the ledger says the platform holds the cash and owes the vendor its net share, so once payouts run the vendor is paid twice (gross cash in hand + net payout). | `services/api/app/services/payments/cod.py` module docstring ("platform-collect"), `expected_collection_posting_legs`; `services/api/app/routers/cod.py` `vendor_confirm_cod_collection` (`require_role("vendor")`); no COD/fulfilment restriction in `routers/checkout_payment.py` `_validate_payment_method`; `grep remit` finds no remittance model. | Up to K500 per pickup-COD or vendor-confirmed order becomes a double liability; rider float is invisible. **Critical before payouts are enabled.** |
| **C03** | **A failed delivery attempt after pickup cannot be re-dispatched, cannot be returned, and its stock is not restored.** `create_dispatch` only accepts orders in `confirmed`/`processing`; after `picked_up` the order is `shipped`, so a second attempt is refused. A `failed` dispatch leaves the order in `shipped` with no return-to-vendor leg. The cancel-restock trigger deliberately skips post-`shipped` cancellations. For **prepaid** orders the 7-day auto-release selects `shipped` orders with no check on dispatch status, so a lost or failed parcel releases the vendor's money unless the customer opens a dispute. | `services/api/app/services/dispatch/service.py` `DISPATCHABLE_ORDER_STATUSES`, `create_dispatch` lines 237–243, `board_snapshot` (ready list only `confirmed/processing`); `supabase/migrations/20261113071000_order_cancel_stock_release.sql` header; `routers/internal_order_jobs.py` `_list_auto_release_candidates`; `release.py:33` (7 days). | Every "customer not home" becomes an off-system workaround. Stock counts drift down. At scale (prepaid on) vendors are paid for undelivered goods. **High.** |
| **C04** | **Chain of custody can be bypassed.** (a) The vendor `ship` action moves a delivery order to `shipped` with no dispatch, which removes it from the dispatch board and blocks `create_dispatch`, so no handover code is ever minted. (b) Admin `intervene` can apply `MARK_DELIVERED` with no POD or handover code. | `services/api/app/routers/vendor_orders.py` `ship_vendor_order` (event `SHIP`); `services/api/app/services/orders/state.py` transition table (`PROCESSING --SHIP--> SHIPPED` vendor/admin; `SHIPPED --MARK_DELIVERED-->` vendor/admin/system); `routers/admin_orders.py` `/intervene`. | Vendors who use their own boda-boda or a cousin bypass the handover code; disputes then have no proof. **High.** |
| **C05** | **Delivery price ignores the vendor's location and the number of pickups.** The zone is the *customer's* straight-line distance from the CBD (A ≤5 km, B ≤12 km, C ≤25 km). A Matero vendor → Chilenje customer pays the same as a next-door vendor. A three-vendor checkout pays three fees. Free delivery applies per vendor group at ≥K200, with no courier-cost floor. | `services/api/app/routers/checkout.py` `ZONE_BANDS_KM`, `resolve_delivery_zone`, `compute_group_delivery_fee_ngwee`; `services/api/app/services/orders/fulfilment.py` (fee per vendor group); `services/cart/grouping.py:6` (K200). | Free-delivery orders can lose K40–80 each, which is more than the 5–12% commission on a K200–500 order. Cross-town pairs are under-priced. **High margin leak.** |
| **C06** | **Typed out-of-town landmarks are priced as Lusaka Band B.** With no GPS, any landmark not matched and not naming one of four towns (`ndola, kitwe, livingstone, chipata`) falls back to Band B (K45). "Kafue", "Chongwe", "Chisamba", "Kabwe", "Mazabuka", "Siavonga", "Solwezi" all become K45 Lusaka deliveries. | `routers/checkout.py` `OTHER_TOWN_TOKENS`, `resolve_address_zone` line 439; `supabase/migrations/20261113060000_delivery_fallback_zone_band_b.sql`. | A 45–60 km trip sold for K45. The rider refuses or ops subsidise K150–400. Likely within the first weeks. **High.** |
| **C07** | **The rider can be sent to the wrong branch.** The dispatch pickup point is the vendor's primary active location, but checkout stock can be consumed from another branch (`order_item_stock_consumption.location_id`). | `services/dispatch/service.py` `load_order_dispatch_context` (`ORDER BY vl.is_primary DESC … LIMIT 1`); `20261113071000_order_cancel_stock_release.sql` (`location_id`). | A wasted trip (K40–80) plus delay for multi-branch vendors. **Medium.** |
| **C08** | **Dispatch can be created before the parcel is packed.** `confirmed` is dispatchable. There is no "ready for collection" signal for delivery orders, and vendor `hours` (`vendor_locations.hours` jsonb) is unused by dispatch. | `DISPATCHABLE_ORDER_STATUSES = {"confirmed","processing"}`; `supabase/migrations/0002_identity_vendors.sql` (`hours`). | Riders wait or leave, and their waiting time is billed. **Medium.** |
| **C09** | **Handover-code closure depends on one human.** Only an **admin** can enter the code the rider relays (`/dispatch/requests/{id}/handover`). The rider phones or WhatsApps ops, and ops types it. The founder also has a full-time job. Five wrong codes lock the code for 15 minutes. | `routers/admin_dispatch.py` `verify_handover` (`require_role("admin")`); `services/dispatch/service.py` `HANDOVER_MAX_ATTEMPTS=5`, `HANDOVER_LOCKOUT_MINUTES=15`. | Deliveries stay "open" for hours, which feeds C01's 48-hour clock. The rider holds cash with no system record. **High.** |
| **C10** | **The customer gets the handover code at pickup, not at the door.** `_emit_shipped_best_effort` sends the code in the `order_shipped` WhatsApp as soon as ops marks `picked_up`. The code proves "customer knew a number", not "customer received the parcel". | `routers/admin_dispatch.py` `_emit_shipped_best_effort`. | It enables "read me the code" social engineering, family members passing it on, and rider–customer collusion (B25/Z14). **Medium.** |
| **C11** | **Silent lifecycle gaps in notifications.** `order_cancelled`, `dispute_opened/resolved`, `payout_sent/failed` and `order_processing` map to `None`. A customer whose order the vendor rejects is **not told**. The only logistics alert is "dispatch `requested` > 45 min". Nothing alerts on accepted-but-not-picked-up, picked-up-but-not-delivered (a rider holding goods and cash), placed-not-confirmed (`CONFIRM_SLA_HOURS = 2` is display-only), or delivered-COD-not-collected. | `services/notifications/events.py` `EVENT_REGISTRY`; `infra/n8n/dispatch-stale-alert.json`; `routers/vendor_order_queue.py:22`. | The customer waits at home for an order that was cancelled hours ago, and gets a refused-COD round trip anyway. **High.** |
| **C12** | **Riders are not first-class.** `courier_partners` is a company and contact record. There is no rider identity, phone, national ID/NRC, vehicle, KYC, per-rider cash balance or rating. Customer name, phone, landmark and GPS go to the courier company's WhatsApp (outbox payload). | `supabase/migrations/20261109100000_courier_dispatch_v1.sql`; `services/dispatch/message.py`. | There is no way to attribute theft, cash shortfall or misconduct to a person, and no way to block a bad rider. **High at scale.** |
| **C13** | **COD abuse controls are thin.** There is a per-checkout cap (≤ `cod_cap_ngwee`, K500) and a 20/min `POST /orders` rate limit. There is no limit on open COD orders per customer or phone, no refusal history and no new-account restriction. Stock is decremented when a COD order is placed. | `routers/checkout_payment.py` `_validate_payment_method`; `core/ratelimit_policies.py:317`. | Fake or prank COD orders cause wasted rider trips (K40–80 each) and block stock. **Medium–High.** |
| **C14** | **There are no reverse logistics.** The return lanes create refunds but no reverse dispatch (`grep dispatch services/returns/*` = 0). Return shipping is a constant K50. A COD refund needs a payout rail. | `services/returns/lane1.py` `DEFAULT_RETURN_SHIPPING_NGWEE`; `services/returns/lane2.py`. | Returns are run by hand. Cash refunds to COD customers are off-ledger. **Medium.** |
| **C15** | **Money-workflow failures may be silent.** The 2026-08-01 status entry records that none of the money workflow JSONs declare an `errorWorkflow` and the error-alert handler was inactive (VD-P06). **Verify live.** | `docs/plan/00-status.md` (RC-P02 entry); `infra/n8n/money-workflow-error-alert.json`. | If `order-jobs`/`notification-dispatch` stop, nobody notices. **Medium–High.** |
| **C16** | **"Always available" listings never decrement stock.** `stock_mode = 'always_available'` skips reservation. Vendors also sell the same unit in their physical shop. | `supabase/migrations/0003_catalog.sql:94`; `services/stock/claim.py` `_fetch_listing_stock_mode`. | Out-of-stock is discovered when the rider arrives. **Medium.** |

**What is genuinely solid** (do not rebuild): the dispatch state machine with guard and audit triggers and one active dispatch per order (`20261109100000_courier_dispatch_v1.sql`); the service-role-only handover code with a constant-time compare and lockout (`dispatch/service.py`); server-authoritative fees and fulfilment (`orders/fulfilment.py`); the per-checkout COD cap re-validated server-side; exactly-once stock restore on pre-dispatch cancel (`20261113071000_…`); 15-minute checkout holds with the 2-minute sweeper (`tasks/sweepers.py`, `infra/n8n/reservation-sweeper.json`); the outbox with dedupe and WhatsApp→SMS→email fallback (`services/notifications/fallback.py`); idempotent ledger posts keyed `cod-receivable-/cod-collect-/cod-reversal-`.

---

## 2. Register — the 27 scenarios in the brief

Format per entry: **What** · **Why** · **Consequence (magnitude)** · **Prevent** · **Detect** · **Auto response** · **Human when** · **Code status** · **Score P/S**.

### B01 Multi-vendor checkout, vendors across town (Woodlands + Chilenje + Matero)
- **What:** Three independent dispatches, three riders, three COD collections and three handover codes for one customer. The customer pays three delivery fees, and parcels arrive hours apart.
- **Why:** Orders are split per vendor (one `checkout_group` → N `orders`). Dispatch is per order. There is no consolidation entity.
- **Consequence:** The customer pays K90–195 in fees on a K300 basket and abandons, or complains. If free delivery triggers per vendor, Convergeo pays K120–240 in courier cost. Three separate cash handovers triple the reconciliation work.
- **Prevent:** Show the per-vendor fee and expected arrival at checkout. Nudge with "2 of your 3 items are available from one vendor near you" (Model A, opt-in only). In the pilot, allow ops to put several orders for the same customer on one courier trip (one job reference for N dispatches). Apply the free-delivery threshold per **checkout**, not per vendor.
- **Detect:** Checkouts with more than one delivery group; fee/AOV ratio above 30%.
- **Auto:** Auto — group the board view by `checkout_group_id`; send one consolidated customer message.
- **Human:** Ops decides whether to multi-stop a rider (pilot).
- **Code:** **Partial.** Splitting and per-vendor fees work. No consolidation, and the board lists orders individually (`dispatch/service.py` `board_snapshot`). C05.
- **Score:** P 4×3=12 · S 5×4=20

### B02 Many customers ordering from the same vendor
- **What:** A vendor gets 8 orders at once (promo or WhatsApp-status share) and prepares slowly. Several riders arrive and wait; some orders are oversold.
- **Why:** There is no vendor capacity or throttling, and no batching of pickups at the same vendor.
- **Consequence:** Rider waiting fees, late deliveries, cancellations. A single vendor can sink pilot NPS.
- **Prevent:** Per-vendor open-order cap (config). Batch pickups at the same location within a time window onto one courier job.
- **Detect:** More than N open `confirmed/processing` orders for a vendor; median confirm-to-pack time rising.
- **Auto:** Auto — hide the "fast delivery" promise and lengthen the ETA when the queue exceeds N; pause the listing when open orders exceed the cap.
- **Human:** Call the vendor when the cap is hit twice in a day.
- **Code:** **Not handled** (no capacity model; `CONFIRM_SLA_HOURS` display only, `routers/vendor_order_queue.py:22`).
- **Score:** P 2×3=6 · S 4×3=12

### B03 Different vendors in the same neighbourhood, many customers
- **What:** Three riders cover the same Kabwata streets at the same hour.
- **Why:** One dispatch per order, chosen by hand, with no route view.
- **Consequence:** Courier cost is 2–3 times what is needed. At the pilot's 5–30 orders a day this is small in kwacha but sets the habit.
- **Prevent:** Board view clustered by zone and time window. Ops assigns one courier job for several dispatches. Later, PDP/VRP batching (Agent 4).
- **Detect:** Dispatches with pickup points within 2 km created within 30 minutes and assigned to different jobs.
- **Auto:** Auto+H — suggest a "batch with" on the board.
- **Human:** Accept or reject the batch.
- **Code:** **Not handled** (no batch or job entity; `courier_reference` is free text).
- **Score:** P 2×2=4 · S 5×4=20

### B04 Riders travelling empty / returning without parcels
- **What:** A rider is paid for a trip where the parcel was not ready, the order was cancelled after the call-out, or there is no return load.
- **Why:** Dispatch is allowed before packing (C08). There is no cancellation notice to the courier on order cancel. There is no back-haul (returns) planning.
- **Consequence:** K40–80 per dead run. At 10% of trips that is about 1.5% of GMV.
- **Prevent:** Dispatch only after the vendor marks "packed" (`processing`) and a readiness time. Auto-notify the courier on cancel. Use back-haul for returns (C14).
- **Detect:** A dispatch `cancelled` after `accepted`; `failed` with reason "not ready".
- **Auto:** Auto — on order cancel, cancel the active dispatch and enqueue a courier message.
- **Human:** Agree the dead-run fee with the courier company.
- **Code:** **Partial.** Dispatch `cancelled` exists. Order cancel does not cascade to the dispatch or notify the courier.
- **Score:** P 3×2=6 · S 4×3=12

### B05 Riders arrive before orders are ready
- **Why:** C08 — `confirmed` is dispatchable, and there is no readiness timestamp or opening-hours check.
- **Consequence:** 20–60 minutes waiting, rider leaves, re-dispatch (blocked by C03 if already marked picked up).
- **Prevent:** A "ready for collection at HH:MM" vendor action. Dispatch auto-requested at ready time minus travel time. Respect `vendor_locations.hours`.
- **Detect:** Gap between `accepted_at` and `picked_up_at` above 30 minutes.
- **Auto:** Auto — WhatsApp nudge to the vendor when the rider is accepted and the order is still `confirmed`.
- **Human:** Repeat offenders.
- **Code:** **Not handled** (C08).
- **Score:** P 4×2=8 · S 4×3=12

### B06 Vendors delaying parcel preparation
- **What:** The order sits in `placed`/`confirmed` for hours. The COD customer changes their mind and refuses at the door.
- **Why:** No SLA enforcement, and vendor phones are offline (Z01).
- **Consequence:** Refusal rate rises sharply with delay. Each refusal costs a full trip (K40–80) plus a reversal.
- **Prevent:** Confirm SLA of 2 hours inside opening hours. Auto-cancel at T+X with stock restore (exists on cancel).
- **Detect:** `placed` age above `CONFIRM_SLA_HOURS`; `confirmed` older than 4 hours.
- **Auto:** Auto — nudge at T+1h; escalate at T+2h; auto-cancel and notify the customer at T+6h or close of business (needs the `order_cancelled` template, C11).
- **Human:** Vendor coaching or suspension after 3 breaches a week.
- **Code:** **Not handled** (display-only SLA; no sweeper).
- **Score:** P 4×3=12 · S 4×3=12

### B07 Customer unavailable at the address
- **What:** The rider arrives and the phone is off, the customer is at work, or the gate is locked.
- **Why:** No delivery window, no pre-arrival call script, and data or power issues (Z01/Z02).
- **Consequence:** A wasted trip. With COD there is no prepaid fee to absorb it, so Convergeo or the vendor pays K40–80.
- **Prevent:** Collect a delivery window at checkout. Send a "rider on the way" SMS or WhatsApp. Rider calls 10 minutes before arrival. Offer a safe-drop or alternate recipient on the order.
- **Detect:** Dispatch `failed` with a structured reason `customer_unavailable` (currently free text).
- **Auto:** Auto — after the first failure, message the customer to choose re-delivery or pickup within 24 hours; after a second failure, return to vendor and cancel.
- **Human:** Customer support calls on a high-value order.
- **Code:** **Partial.** `failed` and `failure_reason` exist but are free text. Re-delivery is blocked by C03.
- **Score:** P 4×3=12 · S 5×3=15

### B08 Incorrect or inaccessible address
- **Why:** Landmark-only addressing (Z03). GPS optional. Matcher limited, with Band B fallback for anything unmatched (C06).
- **Consequence:** Rider phones around for 30 minutes, or fails. Mispriced deliveries.
- **Prevent:** Require a GPS pin or WhatsApp location share for delivery. Store "directions" text. Phone verification for the recipient.
- **Detect:** Address with no lat/lng; fallback zone used; repeat failures to the same address.
- **Auto:** Auto — when the fallback zone is used, ask the customer to share their WhatsApp location before dispatch.
- **Human:** Ops confirms the location by phone for no-GPS addresses (pilot).
- **Code:** **Partial** (`addresses.lat/lng` optional; `routers/checkout.py` fallback).
- **Score:** P 4×3=12 · S 4×3=12

### B09 Failed deliveries and repeated attempts
- **Code status: Not handled — blocked by C03.** After `picked_up`, a second attempt cannot be dispatched in the system. Ops must either keep the original dispatch open while the rider re-tries off-system (not allowed: `failed` is terminal) or cancel.
- **Consequence:** Off-system custody of the goods, untracked rider cash, no audit trail. Stock not restored.
- **Prevent / Auto:** Add `failed → requested` (re-attempt) on the same dispatch, or allow `create_dispatch` from `shipped` when the latest dispatch is `failed`. Add a `returning_to_vendor → returned` leg with vendor acknowledgement. Restock on vendor-acknowledged return. Cap attempts at 2.
- **Detect:** `shipped` order with latest dispatch `failed` and no new dispatch within 24 hours.
- **Human:** Decide who pays the second attempt.
- **Score:** P 4×4=16 · S 5×4=20

### B10 Customer cancels after dispatch
- **What:** The customer calls to cancel while the rider is en route, or refuses at the door ("found it cheaper", "changed my mind").
- **Why:** COD carries no commitment. The customer cannot cancel after `processing` in the app (`orders/state.py`: `PROCESSING --CANCEL-->` vendor/admin only), so they phone or simply refuse.
- **Consequence:** Full trip lost plus a return trip, K80–160. Stock not restored after `shipped`.
- **Prevent:** A COD commitment fee (for example, a K20 MoMo deposit for repeat refusers). Explicit "cancellations after dispatch are charged" consent. Refusal history (C13).
- **Detect:** `refuse_cod_collection` per customer and phone.
- **Auto:** Auto — after the first refusal, the next COD needs a deposit; after the second, COD is blocked for that phone or device.
- **Human:** Disputes about "rider was rude, so I refused".
- **Code:** **Partial.** `refuse_cod_collection` reverses the receivable and cancels the order (`payments/cod.py`). There is no refusal history, no return custody, and no restock.
- **Score:** P 4×3=12 · S 5×3=15

### B11 Vendor cancels after payment
- **What:** The vendor rejects a paid or COD order (out of stock, price error).
- **Consequence:** The customer is not notified (C11: `order_cancelled` → `None`). For prepaid there is a refund through the ledger (`vendor_orders.py` `refund_path`). For COD the rider may already be dispatched (B04).
- **Prevent:** Stock accuracy (Z09). Vendor rejection-rate KPI. Penalty after N rejections.
- **Detect:** Rejection rate per vendor; reject after `confirmed`.
- **Auto:** Auto — notify the customer with substitutes (Model A, opt-in); cancel the active dispatch and notify the courier.
- **Human:** Vendor review at more than 5% rejects.
- **Code:** **Partial.** Stock restore on reject works (`20261113071000_…`). Customer notification is missing (C11). The dispatch is not cascade-cancelled.
- **Score:** P 3×3=9 · S 4×3=12

### B12 Rider accepts and abandons
- **What:** The courier accepts on WhatsApp, then never collects, or collects and goes silent.
- **Why:** Manual WhatsApp coordination; no rider identity (C12); no SLA after `accepted`.
- **Consequence:** Delay. If after pickup, possible loss of goods and cash (B13/Z05).
- **Prevent:** Rider identity and a deposit or bond held by the courier company. SLA timers per state.
- **Detect:** `accepted` with no `picked_up` after 60 minutes; `picked_up` with no `delivered/failed` after 4 hours (Lusaka).
- **Auto:** Auto — alert ops at the thresholds. Auto-cancel and re-request an `accepted` job to a backup courier after 90 minutes.
- **Human:** Any `picked_up` dispatch going silent, because goods and cash are at risk.
- **Code:** **Partial.** Only the `requested > 45 min` alert exists (`dispatch/service.py` `list_stale_requested`; `infra/n8n/dispatch-stale-alert.json`).
- **Score:** P 3×4=12 · S 4×4=16

### B13 Theft, loss, damage, tampering
- **Why:** No sealed packaging, no pickup photo or parcel count, no rider identity, no vendor-side handover proof (the vendor never confirms "rider X took N parcels").
- **Consequence:** Full item value (K150–500, more for electronics). Liability unclear between vendor, courier and Convergeo.
- **Prevent:** Tamper-evident Convergeo bags with serial numbers (cheap). Pickup photo and parcel count at the vendor. Vendor confirms handover to the rider with a pickup code (the mirror of the customer handover code). A written courier liability clause (F6 courier MOUs).
- **Detect:** Customer opens a dispute within 48 hours; damage reported at the door; seal number mismatch.
- **Auto:** Auto+H — freeze vendor release and courier fee for that job; open a dispute automatically.
- **Human:** Liability decision.
- **Code:** **Partial.** POD photo at delivery exists (`pod_photo_public_id`). There is no pickup proof, no seal, and no rider identity.
- **Score:** P 2×4=8 · S 4×4=16

### B14 COD discrepancies and reconciliation
- **What:** The rider collects K480 but remits K450; the rider keeps the cash for days; collection is never confirmed; the vendor takes the cash directly.
- **Code status: Not handled → C01 + C02.** There is no rider cash custody, no remittance record, no daily cash-up, and auto-confirm drops unconfirmed COD from the ledger.
- **Consequence:** Directly lost cash, and a ledger that cannot be reconciled with MoMo or bank. One rider absconding with a day's float: K1,000–5,000.
- **Prevent:** A `cod_collections` record per dispatch (who holds it, amount, method cash or MoMo, time). Riders remit by MoMo to a Convergeo till the same day. Per-rider float cap (for example, K1,500). Exclude COD orders from auto-confirm until collection is booked. Disable vendor-role COD confirm, or restrict it to pickup orders with a vendor-remit ledger.
- **Detect:** Delivered COD with no collection after 2 hours; rider balance above the float cap; end-of-day sum of COD delivered ≠ remitted.
- **Auto:** Auto — block new dispatches to a courier or rider over the float cap; send a daily cash-up report.
- **Human:** Any shortfall; investigate a rider.
- **Score:** P 5×5=25 · S 5×5=25

### B15 Oversized, fragile, heavy, odd-shaped items
- **Why:** No weight, dimension or fragility attributes in dispatch. Courier assumed to be a motorbike.
- **Consequence:** A rider can't carry it (a fridge, a 20 kg bag of mealie meal), or breakage (glass, TVs). Flat zone fee badly under-prices it.
- **Prevent:** Listing-level `handling_class` (standard / bulky / fragile / heavy) driving vehicle type and fee multiplier. Bulky forced to pickup or vendor-delivered in the pilot.
- **Detect:** Category rules; courier rejection reason.
- **Auto:** Auto — at checkout, hide motorbike delivery for bulky items.
- **Human:** Quote by hand for bulky items.
- **Code:** **Not handled.**
- **Score:** P 3×3=9 · S 4×4=16

### B16 Products needing specialised transport (gas cylinders, chemicals, live animals, alcohol, medicines)
- **Why:** No hazmat or age-restricted flags. LPG cylinders are a common Lusaka purchase.
- **Consequence:** Legal and safety exposure; courier refusal.
- **Prevent:** Prohibited or special-handling category list. Pickup-only for hazmat in the pilot. Age verification at the door for alcohol.
- **Code:** **Partial** — there is a prohibited-content screen for listings (M18 notes); there is no logistics class.
- **Score:** P 2×4=8 · S 3×4=12

### B17 Perishables
- **Why:** No perishability attribute; batching logic (future) would treat them like electronics.
- **Consequence:** Spoilage paid by Convergeo, with refund and reputation cost.
- **Prevent:** `perishable_max_minutes` per listing. Perishables never batched or held. Delivery only inside vendor hours, with a same-hour dispatch SLA. No COD refusal for perishables without a deposit.
- **Detect:** Elapsed time from pickup to delivery above the maximum.
- **Auto:** Auto — perishable orders jump the queue on the board; escalate at 50% of the time limit.
- **Code:** **Not handled.**
- **Score:** P 2×3=6 · S 4×4=16

### B18 Mixed urgency in one checkout
- **What:** The customer wants the phone today and the curtains whenever, but the system treats them the same.
- **Code:** **Not handled** — there is a single delivery option per vendor group.
- **Prevent:** Per-group service level (express / standard / scheduled) once batching exists.
- **Score:** P 1×2=2 · S 3×3=9

### B19 Products not immediately available (made-to-order, backorder)
- **Why:** `made_to_order` mode exists in `stock/claim.py` (`_fetch_listing_stock_mode`), but delivery promises and ETAs ignore it. The 48-hour auto-confirm and 7-day auto-release clocks assume prompt shipping.
- **Consequence:** COD customer forgets or refuses 10 days later; a prepaid order auto-releases before delivery (C03).
- **Prevent:** Vendor-declared ready date; re-confirm with the customer at ready time before dispatch (COD). Auto-release clock starts from dispatch `delivered`, not order `shipped`.
- **Code:** **Partial.**
- **Score:** P 2×3=6 · S 3×4=12

### B20 Intercity transport disruption (bus parcel services)
- **What:** The bus is late or cancelled, the parcel is offloaded, the depot is closed on Sunday, the parcel is lost, the claim is limited.
- **Code:** **Not handled.** Beyond 25 km is pickup only (`routers/checkout.py`), and `integration_kind='api'` is reserved. There is no intercity booking, waybill or depot-collect tracking. C06 lets nearby towns slip into Lusaka pricing.
- **Prevent:** Before launching intercity: waybill number and photo captured, a sender-declared value, the provider's claim limit shown, insurance or self-insurance reserve, receiver ID check at the depot, a "parcel arrived at depot" confirmation from the receiving agent.
- **Detect:** Expected-arrival SLA per route; no "arrived" confirmation by ETA + 12 hours.
- **Human:** Always for lost parcel claims.
- **Score:** P 1×3=3 (not live) · S 4×4=16

### B21 Public holidays, traffic, fuel shortages, weather
- **Why:** No calendar or capacity model. Fees are static.
- **Consequence:** Promises missed. At peak, courier prices rise above the fee charged.
- **Prevent:** Holiday calendar (Zambia gazetted holidays) blocking same-day promises. A `surge_multiplier` config that ops can switch. Rainy-season mode (Z07).
- **Detect:** Courier quotes above zone fee; late rate per day.
- **Auto:** Auto — on a holiday, ETA text changes to "next working day".
- **Code:** **Not handled** (static `delivery_zones.fee_ngwee`).
- **Score:** P 3×2=6 · S 4×3=12

### B22 Rural and off-network locations
- **Code:** **Partial.** GPS beyond 25 km gives pickup only, which is correct. The landmark path mis-prices (C06).
- **Prevent:** Explicit "outside delivery area — collect from the vendor or the nearest bus depot" message. Fix C06 with a town list plus "must share GPS".
- **Score:** P 3×3=9 · S 4×3=12

### B23 Courier or transport companies change prices or schedules
- **Why:** `courier_partner_zones.price_ngwee` is static. Agreements are on WhatsApp. Fuel swings (Z11).
- **Consequence:** A silent margin squeeze. Customer fee unchanged.
- **Prevent:** Record the actual `quoted_price_ngwee` per dispatch (field exists) and compare it with the fee charged. Alert when the margin per delivery is below zero. Price-review clause in courier MOUs.
- **Detect:** Weekly report of fee minus courier price by zone.
- **Code:** **Partial** (the field exists; no report or alert).
- **Score:** P 3×2=6 · S 4×3=12

### B24 Peaks (weekends, month-end payday ~25th–30th, festive season, back-to-school January)
- **Consequence:** Courier capacity shortfall, vendor stockouts, cash float overload (more COD at month-end).
- **Prevent:** Pre-book courier capacity for the payday window. Temporarily lower the COD cap or require prepaid at peak. Vendor stock confirmation drive before peaks.
- **Detect:** Orders per hour above courier capacity; `requested` queue age.
- **Auto:** Auto — at a queue threshold, switch checkout to "next-day delivery" text and push pickup.
- **Code:** **Not handled.**
- **Score:** P 3×3=9 (the pilot runs into month-end and December) · S 5×4=20

### B25 Fraudulent customers, vendors, couriers
- **Customers:** Fake COD orders (C13); "never received" claims after a code was shared (C10); stolen-phone accounts.
- **Vendors:** Fake "shipped" without a dispatch (C04); counterfeits (Z12); confirming COD collection to inflate payable (C02).
- **Couriers:** Fake POD photos (reused image); fake "customer refused" while reselling the goods; collusion (Z14).
- **Prevent:** Close C02/C04. POD photo must be taken in-app with EXIF and GPS checked against the drop-off (later). Rider identity (C12). Refusal history. Image hash dedupe on POD.
- **Detect:** The same POD hash used twice; delivery GPS more than 500 m from the drop-off; a customer with more than one "not received" dispute; a vendor whose orders are mostly vendor-shipped.
- **Human:** All fraud determinations.
- **Code:** **Partial** (handover code plus lockout, POD id; C02/C04/C10/C12/C13 open).
- **Score:** P 3×4=12 · S 5×5=25

### B26 Reverse logistics, returns, exchanges, warranty
- **Code:** **Partial.** The return lanes, refund maths and dispute escalation exist (`services/returns/lane1.py`, `lane2.py`). There is no reverse dispatch, no item-condition check at collection, no exchange flow, and COD refunds need a payout rail (C14).
- **Prevent:** Reverse dispatch reusing `dispatch_requests` with a direction flag. Vendor acknowledges receipt before the refund. Cash refunds for COD done by MoMo payout only, never cash from the rider.
- **Human:** Condition disputes.
- **Score:** P 2×3=6 · S 4×3=12

### B27 Delivery disputes and proof-of-delivery
- **What:** "I never got it", "the rider gave it to my neighbour", "it was empty".
- **Code:** **Partial.** Handover code or POD photo is required for `delivered` (`dispatch_requests_delivered_proof_check`). Weakened by C04 (bypass), C10 (code sent early), and the absence of pickup proof and seals.
- **Prevent:** Code at the door plus a seal number plus the recipient's name. Show the customer the POD photo on dispute. Hold vendor release while a dispute is open (exists: `_open_dispute_filter_sql`).
- **Auto:** Auto — a dispute within 48 hours freezes auto-confirm (exists) and attaches dispatch evidence to the case.
- **Score:** P 3×3=9 · S 4×4=16

---

## 3. Register — Zambia/Lusaka-specific scenarios (beyond the brief)

### Z01 Load-shedding kills vendor phones
- **What:** In long outage blocks, the vendor's phone dies, so the `vendor_new_order` WhatsApp is unseen for hours.
- **Consequence:** B06 delays; COD refusals.
- **Prevent:** SMS fallback for vendor-critical events (fallback exists; **verify Africa's Talking is enabled**). Vendor registers a second contact number. Ops phone call at T+30 min for unacknowledged orders.
- **Detect:** Outbox status not `read` for `vendor_new_order` after 30 minutes (if read receipts are captured); `placed` age.
- **Auto:** Auto — SMS at T+15, second contact at T+30, ops alert at T+60.
- **Code:** **Partial** (`services/notifications/fallback.py`; no per-event escalation ladder).
- **Score:** P 4×3=12 · S 4×3=12

### Z02 Network or data outage during the handover-code check
- **What:** The rider at the gate can't reach ops; the customer can't open the app to see the code; the MTN/Airtel network is down in the area.
- **Consequence:** The rider leaves with the goods, or hands over without proof, or waits 30 minutes. Delivery is "open" for hours (feeds C01/C09).
- **Prevent:** The code goes by SMS as well as WhatsApp. An offline-verifiable code (the rider gets a hash, or a short "last-2-digits" check, so they can confirm locally and sync later). A rider USSD or SMS path to submit the code (`*code#` style, later). A POD photo fallback that syncs later.
- **Detect:** `picked_up` older than 3 hours with no handover attempt.
- **Code:** **Partial** (POD photo fallback exists; requires an admin online).
- **Score:** P 3×3=9 · S 4×3=12

### Z03 Unnamed streets and landmark addressing ("behind the green church, ask for Mama Bwalya")
- **Code:** **Partial** — the landmark is required, GPS is optional, and the matcher knows few areas (`routers/checkout.py` `_AREA_ZONE_BY_KEYWORD`; reference doc notes the Kabulonga inconsistency).
- **Prevent:** WhatsApp location share as the primary capture method; store the rider-confirmed pin after the first successful delivery and reuse it.
- **Score:** P 5×2=10 · S 5×3=15

### Z04 Customer GPS pin set at work, delivery wanted at home (or pin dropped at the CBD by default)
- **Consequence:** Wrong zone and fee; a failed trip.
- **Prevent:** Confirm the pin against the landmark text; flag pins within 300 m of the CBD centre point used as the zone origin (−15.4167, 28.2833).
- **Code:** **Not handled.**
- **Score:** P 3×2=6 · S 3×3=9

### Z05 Rider cash-carrying risk and float
- **What:** Riders carry K2,000–5,000 by evening; robbery (especially at night), loss, "borrowing".
- **Consequence:** Direct loss; rider safety; with C02 the loss isn't even visible.
- **Prevent:** Push customers toward paying by MoMo at the door (the rider shows a merchant till number or a Lenco collection link; the customer pays on their phone and the handover then proceeds). Float cap per rider. Remit every 3–4 deliveries. No COD deliveries after 19:00.
- **Detect:** Rider balance (needs C02 fix).
- **Code:** **Not handled.**
- **Score:** P 4×4=16 · S 5×5=25

### Z06 ZRA receipt mismatch on COD
- **What:** The invoice is issued at order time for an amount the customer later disputes, part-refuses, or that changes. The vendor issues its own receipt (or none). The delivery fee's VAT and turnover-tax treatment differs from the goods.
- **Consequence:** ZRA sequential numbering gaps or voids; tax exposure; customer distrust.
- **Prevent:** Issue the invoice at **COD collection** (or credit-note on refusal). Treat the delivery fee as a separate line. Sequential numbers allocated atomically (exists: `20260924015610_invoice_counter_first_allocation_atomic.sql`); VSDC seam.
- **Detect:** Invoices on cancelled orders without a credit note.
- **Code:** **Partial** — **verify** where the invoice number is allocated for COD (`routers/invoices.py`).
- **Score:** P 2×3=6 · S 4×4=16

### Z07 Rainy season (Nov–Mar) road closures, floods in Kanyama, Misisi, George, Chawama
- **What:** Motorbikes can't pass, riders refuse, parcels get wet.
- **Prevent:** Seasonal "unreliable areas" list; waterproof bags; pickup-point alternative offered at checkout for flagged zones; weather-day switch.
- **Code:** **Not handled.**
- **Score:** P 4×3=12 (pilot starts in rainy season) · S 4×3=12

### Z08 Police checkpoints and road-traffic stops
- **What:** Riders without permits or helmets are detained; the parcel is held; there are bribe demands; a rider with no receipt is accused of carrying stolen goods.
- **Prevent:** A delivery note (order reference, item list, no prices) the rider can show; courier compliance (licensed operators only, F6); legal riders only.
- **Code:** **Not handled** (a courier message exists but is not a printable note).
- **Score:** P 3×2=6 · S 4×3=12

### Z09 Vendor oversells across channels (shop counter, Facebook, WhatsApp status)
- **Why:** Convergeo stock is one of several channels; `always_available` listings never decrement (C16).
- **Consequence:** Rejection after confirm (B11), or the rider arrives to "sold out".
- **Prevent:** Morning stock reconfirmation ping (one-tap WhatsApp); auto-pause listings not reconfirmed in 7 days; rejection-rate penalties.
- **Detect:** Reject reason "out of stock"; listings never edited in 30 days.
- **Code:** **Partial** (stock authority migration `20260930170100_vendor_stock_adjustment_authority.sql`; no reconfirmation loop; `infra/n8n/low-stock-alert.json` exists).
- **Score:** P 4×3=12 · S 5×3=15

### Z10 Shared household phones and recycled numbers
- **What:** The handover code and order details go to a phone shared with family or an employer; MTN recycles inactive numbers to new owners.
- **Consequence:** The code is used by the wrong person; privacy leaks (order contents); account takeover through OTP on a recycled number.
- **Prevent:** Recipient name check at the door; codes not shown in notification previews; dormant-account re-verification.
- **Code:** **Not handled.**
- **Score:** P 3×2=6 · S 4×3=12

### Z11 Fuel price swings (ERB monthly pump-price reviews) and fuel shortages
- **What:** Monthly price changes push courier costs above the static fee.
- **Prevent:** A fuel-indexed fee component reviewed monthly; courier MOU price-adjustment clause; margin alert (B23).
- **Code:** **Not handled** (static fees).
- **Score:** P 2×2=4 · S 4×3=12

### Z12 Counterfeits and grey imports (phones, chargers, cosmetics, spare parts)
- **What:** The customer refuses at the door ("it's fake"); disputes; brand-owner complaints; ZABS/ZCSA exposure.
- **Prevent:** Category-level verified-seller gating for electronics and cosmetics; the customer may inspect before paying COD (state the policy); seal and photo at pickup to resolve "swapped" claims.
- **Code:** **Partial** (KYC tiers, listing moderation; no counterfeit workflow).
- **Score:** P 3×3=9 · S 4×4=16

### Z13 Bus-company parcel loss and claim limits
- **What:** Bus parcel desks often pay limited compensation without a declared value; claims need the original waybill; they take weeks.
- **Prevent:** Declared value on every intercity parcel; a photo of the waybill stored; only declared-value carriers allowed for items above a threshold; self-insurance reserve (for example, 1–2% of intercity GMV).
- **Code:** **Not handled** (no intercity).
- **Score:** P 1×3=3 · S 4×4=16

### Z14 Rider–customer collusion
- **What:** The customer gives the code by phone; the rider marks the parcel delivered; the goods are resold; the customer later claims non-delivery (prepaid) or the rider "collects" nothing (COD reversed as refusal while the goods disappear).
- **Prevent:** Code revealed only at the door (rider taps "arrived", then the code is sent), C10 fix; GPS proximity check; refusal must be accompanied by a vendor-acknowledged return (C03).
- **Detect:** Refusals without a return; the same rider–customer pair repeating.
- **Code:** **Not handled.**
- **Score:** P 2×4=8 · S 4×4=16

### Z15 Rider–vendor collusion
- **What:** The vendor hands over a cheaper item or fewer units; the rider and vendor split the difference, or the vendor confirms COD collection (C02) for cash it took itself.
- **Prevent:** Pickup photo and parcel count; vendor COD confirm removed; spot-check calls to customers.
- **Code:** **Not handled.**
- **Score:** P 2×3=6 · S 3×4=12

### Z16 Rider identity fraud
- **What:** The courier company sends an unvetted subcontractor; the rider uses a borrowed NRC; a fake "Convergeo rider" phones the customer and takes the code or MoMo.
- **Prevent:** Rider registry (C12) with photo; the customer is told the rider's name and the last 3 digits of their phone; an anti-scam line: "Convergeo will never ask you to send money to a personal number".
- **Code:** **Not handled.**
- **Score:** P 2×4=8 · S 4×4=16

### Z17 SIM-swap on customer, vendor or founder phone
- **What:** Phone-OTP auth plus WhatsApp-delivered codes mean a swapped SIM gives full account and handover control. A swap of the **founder's** number captures ops alerts (`FOUNDER_WHATSAPP_E164`) and admin OTP.
- **Prevent:** Admin login not by phone OTP alone (hardware key or TOTP); vendor payout-number changes need a cooling-off period and re-KYC (check `vendor-role-lifecycle.md`); alert on new-device login.
- **Code:** **Partial** — admin is a separate origin with an allowlist (CLAUDE.md §Security); **verify** the admin MFA method.
- **Score:** P 2×5=10 · S 3×5=15

### Z18 Partial COD acceptance
- **What:** The customer accepts 2 of 3 items, or wants to pay part now and the rest by MoMo.
- **Code:** **Not handled** — `cod_amount_ngwee` is the full order snapshot; refusal is whole-order (`refuse_cod_collection`).
- **Consequence:** Riders improvise: they take part payment and record it as "refused" or "collected", which breaks the ledger.
- **Prevent:** Line-level accept or refuse with a recomputed collectable; or policy "all or nothing" stated clearly to riders and customers in the pilot.
- **Score:** P 3×3=9 · S 4×3=12

### Z19 No change
- **What:** The customer has a K100 note for K45, or K500 for K385; the rider has no change.
- **Consequence:** Delay, rounding (customer or rider loses), refusal.
- **Prevent:** Tell the rider the exact amount and ask the customer to have exact cash (message at pickup); MoMo at the door as the default.
- **Code:** **Not handled** (message shows amount only).
- **Score:** P 4×1=4 · S 4×2=8

### Z20 Data-cost aversion to tracking links
- **What:** Customers don't open web links (data bundles); a 150 KB tracking page is "expensive".
- **Prevent:** All critical info in the message text (rider name, ETA window, amount, code); tracking link optional; SMS for code.
- **Code:** **Partial** — the WhatsApp template carries text; the code is in the `order_shipped` message.
- **Score:** P 3×2=6 · S 3×2=6

### Z21 WhatsApp template not approved, or customer not opted in
- **What:** `order_shipped` (carrying the handover code), `courier_dispatch_request` and `dispatch_stale_alert` need Meta-approved templates. Before approval or without opt-in, nothing is sent.
- **Prevent:** Verify all logistics templates are approved before go-live; SMS fallback enabled; the admin board's "copy message" fallback (exists).
- **Detect:** Outbox rows failed or exhausted for logistics templates.
- **Code:** **Partial** (`docs/ops/whatsapp-templates.md`; **verify live**).
- **Score:** P 3×4=12 · S 2×3=6

### Z22 The single operator is unavailable (day job, meetings, travel, illness)
- **What:** Dispatch creation, courier notify, handover entry, COD confirm and refusal are all **admin-only** and manual.
- **Consequence:** Throughput is capped by one person's free minutes; C01 clock risk; the rider holds goods and cash longer.
- **Prevent:** A delegated "logistics ops" role with only dispatch and COD scopes (configurable admin roles exist: `20261009100000_configurable_admin_roles.sql`); a rider self-service code-submit path; an ops rota with the courier company's dispatcher.
- **Code:** **Partial** (role infrastructure exists; the dispatch endpoints check `require_role("admin")`).
- **Score:** P 5×4=20 · S 2×3=6

### Z23 Customer gives a different phone at checkout from the account phone
- **What:** The rider calls the checkout phone; the code goes to the account phone; neither is with the recipient.
- **Prevent:** One "recipient phone" field used for both, verified by OTP for COD.
- **Code:** **Partial** — dispatch uses `addresses.phone` for drop-off and `profiles.phone` for the customer (`dispatch/service.py`).
- **Score:** P 3×2=6 · S 3×3=9

### Z24 Vendor's GPS pin wrong or vendor moved stalls (markets: Soweto, Kamwala, Comesa)
- **Prevent:** Verify the vendor location at KYC (the rider confirms the pin on the first pickup); market stall numbering in the landmark.
- **Code:** **Partial** (`vendor_locations.lat/lng/landmark`; C07).
- **Score:** P 3×2=6 · S 4×2=8

### Z25 Courier marks "picked up" without actually collecting (to start the clock), or the vendor hands over to the wrong courier
- **Prevent:** A vendor-side pickup code (the vendor gets a code from the rider's job) before `picked_up` is accepted.
- **Code:** **Not handled** — `picked_up` is set by an admin on the courier's word.
- **Score:** P 2×3=6 · S 4×3=12

### Z26 Customer refuses because of price change, or the delivery fee was not understood
- **What:** Under the Band B fallback (C06) or multi-vendor fees (B01), the customer is surprised by the total at the door.
- **Prevent:** The order-confirmation message states the exact COD total including fees; repeat it at pickup.
- **Code:** **Partial.**
- **Score:** P 3×3=9 · S 3×3=9

### Z27 MoMo payment at the door fails or is reversed (customer shows a fake SMS "confirmation")
- **What:** If riders accept MoMo instead of cash, fake confirmation SMS screenshots are a known scam.
- **Prevent:** Payment verified by the platform (Lenco collection status) before handover, never by the rider reading the customer's SMS.
- **Code:** **Not handled** — no door-MoMo path exists; it must be designed with this check from the start.
- **Score:** P 2×3=6 · S 4×4=16

### Z28 Customer demands to open or inspect the parcel before paying COD
- **Prevent:** A clear inspection policy (outer inspection allowed; sealed electronics opened only after payment with a 48-hour fault return) printed on the delivery note.
- **Code:** **Not handled.**
- **Score:** P 4×2=8 · S 4×2=8

### Z29 Expired holds or concurrency: two customers buy the last unit; the 15-minute hold expires mid-payment
- **Code:** **Handled** — the 15-minute TTL claim, sweeper every 2 minutes, `checkout.reservation_expired` errors, row-locked claims (`stock/claim.py`, `tasks/sweepers.py`, `20261001120100_stock_claim_replay_authority.sql`). Residual risk only when the sweeper workflow is inactive (**verify live**).
- **Score:** P 1×2=2 · S 2×2=4

### Z30 Courier company is informal and goes bust or disappears with parcels and float
- **Prevent:** At least 2 couriers per zone; a courier bond or deposit; daily remittance (B14); MOUs (F6).
- **Code:** **Partial** (multiple `courier_partners` supported; `active` flag).
- **Score:** P 2×4=8 · S 3×4=12

### Z31 Customer PII in courier WhatsApp threads (Zambia Data Protection Act 2021)
- **What:** Customer name, phone, landmark and GPS go to the courier company's number and persist on riders' phones indefinitely. A data subject request cannot reach those copies.
- **Prevent:** A data-processing clause in the courier MOU; send only what is needed (first name, masked phone through a call-relay later); retention note.
- **Code:** **Partial** (`notification_outbox` payload; `docs/ops/data-retention.md` — **check that it covers courier messages**).
- **Score:** P 3×2=6 · S 4×3=12

### Z32 Vendor shuts or travels (funerals, village trips) with open orders
- **Prevent:** A vendor "away" toggle that pauses listings; auto-cancel unconfirmed orders (B06).
- **Code:** **Not handled** (verify whether a storefront pause exists).
- **Score:** P 3×2=6 · S 4×2=8

### Z33 Cross-border and in-transit risk later (SADC expansion)
- **Note only:** customs, ZRA import duties on resale, the COMESA simplified trade regime. Out of scope for the pilot; register so it is not forgotten.
- **Score:** P 0 · S 2×4=8

---

## 4. Priority ranking

### 4.1 Pilot, next 30 days (likelihood × impact, plus the cost of fixing)

| Rank | ID | Risk | Score P | Fix shape | Automatable? |
|---|---|---|---|---|---|
| 1 | B14 + C01 + C02 | COD cash not booked, or booked as platform cash; rider float invisible; auto-confirm erases it | 25 | Exclude `cod=true` from auto-confirm until collection is booked; open the receivable at order placement; disable vendor-role COD confirm (or vendor-remit ledger for pickup COD); `cod_collections` custody record + daily cash-up | **Auto** (rules) + H for shortfalls |
| 2 | Z22 + C09 | Single human closes every delivery and collection | 20 | Delegated logistics-ops role; one action "handover verified **and** COD collected (K amount, cash or MoMo)"; rider self-submit later | **Auto+H** |
| 3 | B09 + C03 | Failed attempt cannot be retried or returned; stock lost; (prepaid) auto-release | 16 | Allow re-attempt from `failed`; return-to-vendor leg with vendor acknowledgement; restock on return; auto-release keyed to dispatch `delivered` | **Auto** |
| 4 | Z05 | Rider robbery or absconding with float | 16 | Float cap, remit every few drops, no COD after 19:00, push MoMo at the door | **Auto** (cap and block) + H |
| 5 | C06 (+B22, Z26) | Out-of-town landmarks sold as K45 Lusaka delivery | 12–16 | Extend the other-town list (Kafue, Chongwe, Chisamba, Kabwe, Mazabuka, Siavonga…) **and** require a GPS or WhatsApp location for fallback-zone addresses | **Auto** |
| 6 | C11 + B06 + Z01 | Vendor silent or offline; customer not told of cancellation | 12 | `order_cancelled` template; SLA ladder (nudge, SMS, ops, auto-cancel); verify SMS fallback is enabled | **Auto** |
| 7 | B07 + B08 + Z03 | Customer unavailable or wrong address → wasted trips | 12 | Mandatory pin share; "rider on the way" message; structured failure reasons; re-delivery or pickup choice message | **Auto** |
| 8 | B12 | Accepted or picked-up dispatch goes silent | 12 | Two more stale timers (accepted >60 min, picked_up >4 h) on the existing alert workflow | **Auto** |
| 9 | C04 + C10 | Chain-of-custody bypass (vendor ship, admin intervene) and code sent too early | 12 | Block vendor `ship` for delivery orders when `courier_dispatch` is on; require POD on admin `MARK_DELIVERED`; send the code at "arrived" (or reveal it in-app only) | **Auto** |
| 10 | C05 + B01 | Delivery margin leak (free ≥K200 per vendor; vendor distance ignored) | 12 | Per-checkout free threshold with a courier-cost floor; record `quoted_price_ngwee` on every dispatch and a weekly margin report | **Auto** (report) + H (pricing decision) |

Close behind: Z21 (templates or opt-in, 12), B10/C13 (COD refusers and fake orders, 12), Z07 rainy season (12), Z09 oversell (12), B25 fraud (12), C15 silent workflow failure.

### 4.2 Scale (top risks once volume, prepaid and intercity arrive)
B14/Z05 cash (25) · B25 fraud (25) · B01/B03 consolidation economics (20) · B09 re-delivery (20) · B24 peaks (20) · B12/B13/B15/B17/B20/Z12–Z16/Z27 (16) — rider identity (C12) and custody proof (pickup code + seal) are the common fix behind most of them.

---

## 5. §7 Automation boundaries (what is safe to automate, and where)

**Rule:** state transitions and money stay in FastAPI and Postgres (guarded functions, row locks, idempotency keys, audit triggers, as dispatch and COD do today). n8n is **only** a scheduler and messenger that calls internal endpoints. It never decides financial or fulfilment state, and it must tolerate replays.

| Automation | Trigger | Owner | Action | Idempotency / failure handling | Escalation |
|---|---|---|---|---|---|
| Vendor confirm SLA ladder | sweep every 5 min | API sweeper, n8n cron | nudge T+60 → SMS → ops T+120 → auto-cancel (guarded `transition_order`, restock trigger) | outbox dedupe key `order:{id}:sla:{step}` | ops at T+120 |
| Dispatch staleness (3 timers) | sweep every 15 min | extend `list_stale_requested` | alert at requested >45 min, accepted >60 min, picked_up >4 h | one alert per dispatch per state (outbox dedupe) | ops; picked_up >8 h → incident |
| COD collection watchdog | sweep hourly | API | delivered COD with no `cod-collect-*` after 2 h → alert; **auto-confirm skips COD without collect** | read-only check; fix in the candidates SQL | finance at 24 h |
| Rider float cap | on collection record | API | block new COD dispatches to a rider or courier over the cap | transactional check at `create_dispatch` | ops to arrange remittance |
| Daily cash-up | 21:00 Lusaka | API report → n8n message | sum COD delivered vs remitted per courier | versioned report (pattern exists: `reconciliation_report_versions`) | finance on any variance ≠ 0 |
| Cascade cancel to courier | order → cancelled | API, same transaction | cancel active dispatch, enqueue courier message | dispatch CAS transition; outbox dedupe | none |
| Failed-attempt follow-up | dispatch → failed | API | customer choice message (re-deliver or pickup); after 24 h with no reply → return-to-vendor | once per dispatch | support when value is above K300 |
| Margin report | weekly | API → n8n | fee charged − `quoted_price_ngwee` by zone and courier | read-only | founder pricing review |
| Workflow health | each money/logistics workflow | n8n `errorWorkflow` | alert on failure (C15) | n/a | founder |

Recovery from partial failure: every sweeper must be safe to re-run (select by state, transition by CAS, post by idempotency key). That pattern already exists in `cod.py` and `dispatch/state.py`; the new sweepers should copy it, not invent a new one.

---

## 6. §9 Security, RBAC and accountability findings (logistics-relevant)

1. **Vendor can confirm COD collection** (`routers/cod.py`), which writes platform-cash ledger entries. Remove it, or route it to a vendor-remit ledger restricted to pickup orders (C02).
2. **Vendor can ship a delivery order without dispatch** (C04a). This is a custody bypass by a role that benefits from it.
3. **Admin `intervene` can deliver without proof** (C04b). Require a POD id or handover code, and audit with a reason code.
4. **Every dispatch action requires full `admin`**. There is no least-privilege logistics-ops or finance split for dispatch and COD, although configurable admin roles exist (`core/auth.py` permission map, `20261009100000_configurable_admin_roles.sql`). Add `logistics.dispatch` and `finance.cod` scopes.
5. **No rider principal.** Riders are not authenticated users, so "drivers see only assigned jobs" is achieved only by WhatsApp messages carrying full customer PII (Z31). When a rider app comes, give it a dispatch-scoped token showing a masked phone and the address only after `accepted`.
6. **Handover code delivery.** The service-role-only storage is good. The early reveal (C10) and the absence of a vendor-side pickup code (Z25) are the gaps.
7. **Audit trail.** Dispatch transitions and handover are audited (`dispatch_request_events`, admin audit recorder; the code is never logged — good). Missing: COD custody events, courier remittances, returns custody.
8. **Founder phone as the single alert sink** (`FOUNDER_WHATSAPP_E164`) is a SIM-swap and availability single point of failure (Z17/Z22).

---

## 7. Assumptions and things to verify live (not checked: read-only, no DB or n8n access in this pass)

- Whether `order-jobs.json` (auto-confirm and auto-release) is **active** in production. If it is, C01 bites at 48 h.
- Whether `courier_dispatch` is on and logistics WhatsApp templates are **approved**; whether SMS (Africa's Talking) is enabled.
- Whether Lenco payouts are enabled (C02 becomes real money when they are).
- `platform_config` live values: `cod_cap_ngwee`, `free_delivery_threshold_ngwee`, `release_after_delivered_hours`, `dispatch_stale_minutes`.
- Where COD invoice numbers are allocated (Z06).
- Volume, AOV and courier price assumptions in §0 are illustrative, not measured.

