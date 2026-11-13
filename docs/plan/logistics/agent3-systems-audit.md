# Agent 3 — Existing Convergeo Systems Audit (logistics, delivery, fulfilment)

**Scope:** read-only audit of the pilot release candidate, detached checkout `/home/claude/wt-logistics-audit` at `a813f983` (origin/fix/quality-sweep, "merge: server-authoritative fulfilment, stock release on cancel, over-cap notice"), including migrations `20261113060000_delivery_fallback_zone_band_b.sql`, `20261113070000_checkout_fulfilment_choices.sql` and `20261113071000_order_cancel_stock_release.sql`. Nothing was modified. All paths below are relative to that checkout unless absolute.

**Classification key:** WORKS (fit for COD Lusaka pilot as is) · PARTIAL (exists, has a gap that matters) · MISSING · DUPLICATED · UNSUITABLE (exists but wrong shape for the logistics problem) · BUG (behaviour that loses money or strands orders).

---

## 0. Verified architecture (vs. the brief)

| Layer | Brief says | Repository says | Evidence |
|---|---|---|---|
| API host (production) | FastAPI on OCI VM | **Hetzner CX23** (2 vCPU / 4 GB, Nuremberg), standalone container `vergeo5-api` from `ghcr.io/kalumuso/convergeo-api:<sha>`, bound `127.0.0.1:8000`, **host systemd Caddy** in front. Not Docker Compose in production. | `.github/workflows/deploy-production.yml` ("pin-redeploy API on Hetzner", job `deploy-api` scp+ssh `infra/redeploy-api.sh`); `infra/redeploy-api.sh` header; `docs/plan/00-status.md` 2026-07-13 entry ("1 GB OCI micro was abandoned as the API host after the OOM incident") |
| API host (staging) | — | OCI (job `deploy-api-oci` in `.github/workflows/deploy-staging.yml`, secrets `STAGING_OCI_SSH_*`) | same |
| Compose file | — | `infra/docker-compose.yml` (api + caddy + n8n) describes the **old OCI layout**; `infra/README.md` is still titled "OCI provisioning runbook". Stale for production. | |
| n8n | n8n | Owner states n8n runs on **Hetzner** (`docs/ops/n8n-activation-runbook.md` line 3, issue #716). Live workflow IDs/active state **unverified**; every export in `infra/n8n/*.json` has `"active": false`. | |
| DB | Supabase Postgres | Supabase (eu-north-1), 156 migrations. Extensions: `pg_trgm`, `pgcrypto`, `vector`. **No PostGIS** (`0001_extensions.sql`); geo is `double precision` lat/lng + haversine in Python. | |
| DB access from API | — | Most order/dispatch/money paths build SQL strings and run them through `app.services.db.run_sql_script` (psycopg 3, bounded pool). Status changes are guarded functions + triggers, not PostgREST writes. | `services/api/app/services/db.py`, `services/orders/audit.py` |
| Frontends | Vercel | Vercel: `apps/customer`, `apps/vendor`, `apps/admin` (admin behind Cloudflare Access). | `docs/plan/00-status.md` |
| Payments | Lenco | Lenco (MoMo push + hosted card widget) + COD. | `services/payments/*` |
| RBAC | "existing RBAC" | `user_roles` (`customer/vendor/admin/superadmin/moderator` + `rbac_*` restricted roles) + `admin_roles.permissions` (8 permission strings, **no logistics/dispatch permission**). | `supabase/migrations/20261009100000_configurable_admin_roles.sql`, `services/api/app/core/auth.py::require_role` |

**Doc corrections to make (docs only):** `infra/README.md`, `infra/ENVIRONMENTS.md`, `CLAUDE.md` "Infra" line and `.github/workflows/api-image.yml` comment still say OCI hosts the production API. `docs/ops/lusaka-delivery-reference-prices.md` §1 and §5 describe an older landmark matcher (it says only a handful of keywords exist); the code now carries ~50 area names (see C2).

---

## A. Order management

### A1. Checkout → checkout_groups → per-vendor orders — **WORKS**
- **Path / functions:** `routers/checkout.py::create_checkout_session`, `::validate_contact_step`, `::validate_fulfilment_step` (`POST /checkout/steps/fulfilment`); `routers/orders_create.py` (`POST /orders`); `services/orders/create.py::create_orders_atomic`; `services/orders/fulfilment.py::authoritative_vendor_groups`.
- **Tables:** `checkout_groups(id, customer_id, idempotency_key unique, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status, fulfilment_choices jsonb)` → `orders(id, checkout_group_id, vendor_id, customer_id, status, fulfilment, delivery_zone, address_id, delivery_fee_ngwee, cod, commission_snapshot)` → `order_items(id, order_id, item_kind, qty, unit_price_ngwee, title_snapshot)` + `order_item_products(order_item_id, listing_id, product_id, listing_variant_id, variant_snapshot)` + new `order_item_stock_consumption`.
- **Behaviour:** one checkout session = one `checkout_groups` row; `create_orders_atomic` writes **one `orders` row per vendor** in a single transaction (`BEGIN … COMMIT` script), with idempotency key, address-ownership check, stock/variant locks in UUID order, reservation consumption, cart clearing (COD) and a `vendor_new_order` outbox row per COD order. Fulfilment and delivery fee per vendor group are recomputed server-side from `checkout_groups.fulfilment_choices` and the saved address; a client body that disagrees is refused (`orders.fulfilment_mismatch`, `orders.fulfilment_not_confirmed`).
- **Limitation:** the checkout group is a **payment/pricing container only**. Nothing downstream (dispatch, board, COD, notifications) groups the vendor orders of one checkout back together. A 3-vendor checkout becomes three unrelated delivery jobs.
- **Correction:** keep this model (it is the right "fulfilment order per vendor" split). Add a consolidation layer *above* it later (see §E, `delivery_consignments`), keyed on `checkout_group_id` + `address_id`. Do not rebuild order creation.

### A2. Order state machine — **WORKS** (one minor inconsistency)
- **Path:** `services/api/app/services/orders/state.py` — `TRANSITION_TABLE`, `resolve_transition`, `check_order_transition`, `transition_order`. DB side: `order_events` audit trigger fed by GUCs `app.order_actor` / `app.order_note`, `public.lock_payment_checkout_scope`, `public.order_has_collected_money`, `order_money_gates`.
- **States:** `placed → confirmed → processing → ready (pickup only) → delivered → completed`; `processing → shipped (delivery only) → delivered → completed`; `shipped → completed` via `auto_release` (SYSTEM); cancellations from placed/confirmed/processing (vendor/customer/admin by state), `ready`/`shipped → cancelled` admin only. Prepaid fulfilment events require a successful payment; paid cancellations require refund authority.
- **Behaviour:** row-locked, actor-authority checked in SQL, audited. Good.
- **Limitations:**
  1. **No "ready for courier collection" state for delivery orders.** `READY_FOR_PICKUP` is restricted to `fulfilment="pickup"`; a delivery order goes `processing → shipped`. "Processing" is emitted by the vendor's **pack** action with note "Order processing started" (`routers/vendor_orders.py::pack_vendor_order`), so ops cannot tell "started" from "parcel sealed and waiting".
  2. No time/SLA columns (accepted_at, ready_at, promised_by). Timing is only derivable from `order_events.created_at`.
  3. Minor: the SQL payment guard inside `transition_order` lists `'mark_ready'`, which is not an `OrderEvent` value (`ready_for_pickup` is). Not exploitable (you cannot reach `processing` without a paid `confirm`), but the list should match the enum.
- **Correction:** additively allow `processing → ready` for delivery orders (event `ready_for_collection`, vendor/admin), and make `ready` the only state from which a courier pickup is allowed. Keep the table-driven design.

### A3. Per-item status / partial fulfilment — **MISSING**
- `order_items` has no status column; vendor actions (`confirm`, `reject`, `pack`, `ship`) act on the whole vendor order. Returns are per `order_item` (`returns.order_item_id`) but are post-delivery money flows.
- **Consequence:** if a vendor has 2 of 3 items, the only option is reject (whole order cancelled, stock released by `release_cancelled_order_stock`) or ship short and handle via dispute.
- **Correction (Phase 1, not Phase 0):** add `order_items.fulfilment_status` (`pending|allocated|short|cancelled|packed`) and a vendor "partial accept" that cancels lines through a guarded function with ledger adjustment. For Phase 0, operate the rule "reject whole order + customer re-orders".

### A4. Stock release on cancel — **WORKS (pre-dispatch only)**
- `supabase/migrations/20261113071000_order_cancel_stock_release.sql`: `order_item_stock_consumption(order_item_id, order_id, listing_id, listing_qty, location_id, listing_variant_id, variant_qty, released_at)` + trigger `orders_release_cancelled_stock` → `public.release_cancelled_order_stock()`.
- **Limitation:** only fires when cancelling from `placed/confirmed/processing/ready`. A **failed delivery after pickup** (order `shipped`, goods returned to the vendor) restores nothing; orders placed before the migration restore nothing.
- **Correction:** when a returned-to-vendor event exists (see C6), allow restock from `shipped → cancelled` behind an explicit "goods returned to vendor" confirmation.

---

## B. Vendor management

### B1. Order notification (outbox) — **WORKS**
- COD: `vendor_new_order` outbox row written inside `create_orders_atomic` (dedupe key `order.placed:<order_id>:whatsapp`). Prepaid: emitted on payment success (`services/payments/*` → `apply_payment_status`, comment in `create.py`).
- Delivery: `notification_outbox(dedupe_key unique, channel, template, payload, status, attempts, next_retry_at)` drained by `POST /internal/dispatch/tick` (`routers/internal_dispatch.py`, n8n `infra/n8n/notification-dispatch.json`, every minute) → `services/notifications/dispatcher.py::run_dispatch_batch` (WhatsApp Cloud API → SMS → email).
- **Naming hazard:** `/internal/dispatch/*` is the *notification* dispatcher, unrelated to courier dispatch (`/admin/dispatch/*`). Keep in mind when writing runbooks and n8n names.
- **Limitation:** vendor must act in the vendor PWA; no WhatsApp quick-reply accept. `order_cancelled` is mapped **silent** in `services/notifications/events.py::EVENT_REGISTRY`, so a COD customer whose order is rejected gets no message.

### B2. Accept / reject — **WORKS**; acceptance SLA — **PARTIAL**
- `POST /vendor/orders/{id}/confirm|reject|pack|ship|ready-for-pickup` (`routers/vendor_orders.py`).
- `routers/vendor_order_queue.py`: `CONFIRM_SLA_HOURS = 2`, used only to **sort** the vendor queue (`compute_urgency`). No escalation, no auto-cancel, no ops alert when a vendor ignores a `placed` order.
- **Correction (Phase 0):** n8n tick that lists `placed` orders older than 2 h (and `confirmed/processing` older than X h) and enqueues an ops WhatsApp alert — same pattern as `dispatch-stale-alert`.

### B3. Preparation time — **MISSING**
- No `prep_minutes` / `ready_by` on vendors, listings or orders. Only `vendor_listings.lead_time_days` for made-to-order (`0085_product_classes.sql`). Riders will arrive before parcels are ready.

### B4. Stock verification — **WORKS**
- Checkout holds (`stock_reservations`, TTL `reservation_ttl_min`, default 15) → `services/stock/claim.py`; consumption and variant decrement in `create_orders_atomic`; sweeper `POST /internal/stock-sweeper/tick` (`infra/n8n/reservation-sweeper.json`); release on cancel (A4); low-stock alert (`infra/n8n/low-stock-alert.json`). Physical stock mismatch at the shop is only handled by vendor reject.

### B5. Ready-for-pickup / collection readiness — **PARTIAL**
- Customer self-pickup: **WORKS** — `ready` + QR/PIN (`services/pickup/issue.py`, `POST /vendor/pickup/verify` in `routers/pickup_verify.py`).
- Courier collection: **MISSING** (see A2.1).

### B6. Operating hours — **PARTIAL**
- `vendor_locations.hours jsonb` (0002), validated in `routers/vendor_profile.py`, evaluated by `services/vendors/hours.py::is_open_at` for search "open now" (`services/search/open_now.py`, `nearby.py`) and shown at checkout (`routers/checkout.py::_fetch_vendor_locations`). **Not used** by dispatch, SLA or pickup-time promises.

### B7. Pickup locations / branches — **PARTIAL (mismatch)**
- `vendor_locations` extended in `0080_vendor_location_details.sql` (`label, area, street, city, province, phone_e164, is_primary, status`), one primary per vendor (unique partial index). Branch stock in `listing_location_stock(listing_id, location_id, stock_qty)`; order lines record the branch they consumed (`order_item_stock_consumption.location_id`).
- **Limitation:** courier pickup point is computed in `services/dispatch/service.py::load_order_dispatch_context` as **the vendor's primary active location** (`ORDER BY vl.is_primary DESC … LIMIT 1`), ignoring the branch the stock was taken from. One vendor order can also span two branches. `orders` has no `pickup_location_id`.
- **Correction (Phase 0, small):** in `load_order_dispatch_context`, prefer the `location_id` recorded on `order_item_stock_consumption` for that order; flag the order on the board when lines come from more than one branch. Phase 1: add `orders.pickup_location_id`.

---

## C. Delivery management

### C1. Zones / bands and pricing inputs — **PARTIAL / UNSUITABLE for multi-vendor**
- **Tables:** `delivery_zones(zone_key, label, fee_ngwee, active)` seeded `lusaka_a` K30, `lusaka_b` K45, `lusaka_c` K65 (`0008_config.sql`); `platform_config` keys `free_delivery_threshold_ngwee` (default 20 000 = K200), `delivery_fallback_zone` (= `"lusaka_b"`, migration `20261113060000`), `cod_cap_ngwee`.
- **Functions:** `routers/checkout.py::resolve_delivery_zone` (GPS: haversine to CBD point −15.4167, 28.2833; ≤5 km A, ≤12 km B, ≤25 km C, else pickup-only), `::resolve_address_zone` (adds fallback), `::compute_group_delivery_fee_ngwee`, `::validate_fulfilment_step`.
- **Behaviour:** the zone is a property of the **customer address only**; the fee is charged **per vendor group** (`for vendor_id, group in groups_by_vendor.items(): … fee = compute_group_delivery_fee_ngwee(...)`), waived per group when that group's subtotal ≥ K200.
- **Limitations:**
  1. **Vendor location is ignored.** A Matero vendor delivering to Woodlands and a Woodlands vendor delivering to Woodlands are both Band A (K30). The brief's core problem (pickup legs) is not priced at all.
  2. **The brief's scenario costs the customer 3 × fee** (e.g. 3 × K45 = K135 for Band B) with no consolidation discount, and the free-delivery threshold is per vendor group, so a K450 basket split K150/K150/K150 pays 3 fees while a K200 single-vendor basket pays none.
  3. Free delivery means the fee is 0 while the platform still books (and pays) a courier — see D1.
- **Correction:** do not rebuild zones. Phase 0: keep per-group fee but add a configurable **multi-vendor cap** (e.g. "2nd and later vendor groups to the same address in the same checkout pay `platform_config.extra_vendor_fee_ngwee`") computed in `validate_fulfilment_step` *and* `authoritative_vendor_groups` (both must use the same function or POST /orders will refuse). Phase 1: price by pickup-leg + drop-leg once consolidation exists.

### C2. Landmark matcher + `delivery_fallback_zone` — **PARTIAL, one BUG**
- `_EXPLICIT_BAND_KEYWORDS`, `_AREA_KEYWORDS` (~50 Lusaka areas), `_match_landmark_zone` (whole-word, longest phrase wins), `OTHER_TOWN_TOKENS = ("ndola","kitwe","livingstone","chipata")`, `_load_fallback_delivery_zone`.
- The customer fulfilment form sends a **free-text landmark and no GPS** (docstring of `_load_fallback_delivery_zone`), so most addresses go through the matcher, and anything unmatched now becomes Band B.
- **BUG (pilot-relevant):** only four other towns are excluded. A landmark naming **Kabwe, Kafue (town), Chingola, Mufulira, Luanshya, Solwezi, Mansa, Kasama, Mazabuka, Choma, Monze, Siavonga, Chongwe-town outskirts beyond 25 km**, etc. is unmatched → falls back to `lusaka_b` → accepted as a K45 Lusaka delivery. Ops will receive undeliverable orders.
- Minor inconsistencies vs. `docs/ops/lusaka-delivery-reference-prices.md` §4: Kabanana, Chaisa, Bauleni are B in code, C in the doc; Leopards Hill is C in code, B in the doc.
- **Correction (Phase 0):** extend `OTHER_TOWN_TOKENS` to all provincial/district towns (move the list to `platform_config` so ops can add names without a deploy); log every fallback hit (`audit_log` or analytics event) so ops can review unmatched landmarks daily and grow `_AREA_KEYWORDS`. Capture GPS (browser geolocation, optional) on the address form so the GPS path is used when available.

### C3. Server-authoritative fulfilment (`checkout_groups.fulfilment_choices`) — **WORKS**
- Migration `20261113070000_checkout_fulfilment_choices.sql`; written in `validate_fulfilment_step`, read by `services/orders/fulfilment.py::parse_stored_choices` / `authoritative_vendor_groups`. Refuses tampered fees, moved fees between vendors, stale zones. Keep.

### C4. Courier dispatch v1 — **WORKS as a manual per-order tool; UNSUITABLE as the consolidation engine**
- **Migration:** `20261109100000_courier_dispatch_v1.sql`.
- **Tables:** `courier_partners(id, name, contact_whatsapp_e164, contact_email, integration_kind 'manual'|'api'(reserved), active, notes)`; `courier_partner_zones(courier_partner_id, zone_key → delivery_zones, price_ngwee)`; `dispatch_requests(id, order_id, courier_partner_id, status, courier_reference, cod_amount_ngwee, quoted_price_ngwee, pod_photo_public_id, delivered_via, failure_reason, notify_count, last_notified_at, requested_at…cancelled_at, created_by)` with partial unique indexes `dispatch_requests_one_active_per_order`, `dispatch_requests_one_delivered_per_order`; `dispatch_request_events` (append-only, trigger-written); `dispatch_handover_codes(dispatch_request_id, code 6 digits, failed_attempts, locked_until, verified_at)` service-role only. Guard trigger `guard_dispatch_requests_update`, audit trigger `audit_dispatch_requests_status`. Feature flag `courier_dispatch` default **OFF**.
- **Service:** `services/dispatch/state.py` (transition table mirrored in SQL), `services/dispatch/service.py` (`create_dispatch`, `transition_dispatch_admin`, `verify_handover_code`, `notify_courier`, `board_snapshot`, `list_stale_requested`, `party_dispatch_view`), `services/dispatch/message.py::build_courier_message`, `services/dispatch/couriers.py`.
- **Endpoints (admin, `require_role("admin")`, `AdminAuditedRoute`):** `GET /admin/dispatch/board`, `GET|POST|PATCH /admin/dispatch/couriers`, `POST /admin/dispatch/requests`, `GET /admin/dispatch/requests/{id}`, `GET …/{id}/message` (copy-paste text), `POST …/{id}/notify` (outbox WhatsApp/email), `POST …/{id}/transition`, `POST …/{id}/handover`. Party views: `GET /account/orders/{id}/delivery` (customer, includes handover code while active), `GET /vendor/orders/{id}/delivery` (`routers/order_delivery.py`).
- **UI:** `apps/admin/app/[locale]/orders/dispatch/page.tsx`, `_components/DispatchBoard.tsx`, `DispatchCard.tsx`, `CourierManager.tsx`, `dispatch-board-model.ts`; `apps/customer/…/account/orders/[id]/_components/courier-delivery.tsx`; `apps/vendor/…/orders/_components/courier-status.tsx`.
- **What works well:** guarded state machine, audit trail, chain of custody (handover code with 5-try / 15-min lockout, or POD photo required for ops-confirmed delivery — DB check `dispatch_requests_delivered_proof_check`), COD amount snapshot, courier directory with zone service areas, copyable message for manual WhatsApp, stale `requested` alert.
- **Limitations:**
  1. **One dispatch = one vendor order.** No batch/consolidation entity; the board (`board_snapshot`) lists orders flat, ordered by status and age, with no `checkout_group_id`, address, vendor area or customer. Three vendors in one checkout → three dispatches, three handover codes, three COD collections from the same customer.
  2. **Re-dispatch after pickup is impossible.** `DISPATCHABLE_ORDER_STATUSES = {"confirmed","processing"}`; a dispatch that fails after `picked_up` leaves the order `shipped`, which (a) drops it off the board's `ready_orders` query and (b) is refused by `create_dispatch`. No reassignment or second attempt path.
  3. **Dispatch and order transitions are two transactions.** `transition_dispatch_admin` commits the dispatch change (`apply_dispatch_transition`) and then calls `transition_order`; `verify_handover_code` commits `_claim_handover` then the order event. A failure between them leaves dispatch `picked_up/delivered` with the order still `processing/shipped`. Pre-flight (`_preflight_order`) narrows but does not close the window.
  4. **Handover code entry is admin-only** (`POST /admin/dispatch/requests/{id}/handover`): the rider must phone/WhatsApp ops with the code; ops is a single point of failure in the evening peak. There is no rider/driver identity, link or app.
  5. **Notifications:** only `picked_up` notifies the customer (`_emit_shipped_best_effort` → `order_shipped` with the code). `order_delivered` has a WhatsApp template (`services/notifications/templates/whatsapp.py`) but **no emitter anywhere**; failed/cancelled dispatches notify nobody.
  6. Stale alerting covers `requested` only (`list_stale_requested`, 45 min). Nothing alerts on `accepted` not picked up, or `picked_up` not delivered.
  7. `courier_dispatch_request` and `dispatch_stale_alert` WhatsApp templates are registered in code but not documented in `docs/ops/whatsapp-templates.md`; Meta approval status unverified. Fallback is the copy-text endpoint.
- **Correction:** keep the tables, triggers and endpoints. Phase 0 fixes listed in §G. Phase 1: add a `delivery_runs` (batch) parent that owns N `dispatch_requests` (see §E).

### C5. Legacy manual dispatch — **DUPLICATED**
- `POST /admin/orders/{id}/dispatch` (`routers/admin_orders.py::manual_dispatch`) drives `transition_order` with a free-text `[dispatch] courier=… | tracking: …` note; UI `apps/admin/…/orders/_components/DispatchPanel.tsx`.
- Vendor `POST /vendor/orders/{id}/ship` (`routers/vendor_orders.py::ship_vendor_order`) is offered for every delivery order regardless of the `courier_dispatch` flag (`_available_vendor_actions`).
- **Consequence:** an order can become `shipped` with no `dispatch_requests` row; it then leaves the dispatch board and can never get one (C4.2). Prepaid ones auto-release to the vendor after 7 days (D4).
- **Correction (Phase 0):** when `courier_dispatch` is ON, hide/refuse vendor `ship` for platform-dispatched delivery orders (or only allow it with an explicit `self_delivery` choice), and hide the legacy `DispatchPanel` (keep the endpoint for break-glass, audited).

### C6. Driver/courier model, tracking, cancellation, partners — **PARTIAL / MISSING**
- Courier = company directory row (`courier_partners`); **no driver, vehicle, capacity, availability, shift or location model**. No live tracking (only timestamps). `courier_reference` is free text.
- Cancellation: `requested|accepted → cancelled`; failure: `→ failed` with reason. Reassignment possible only before pickup (create new dispatch after cancel/fail).
- Partner integrations: `integration_kind='api'` reserved and refused (`create_dispatch` raises `courier_integration_unavailable`; `couriers.py::RESERVED_INTEGRATION_KINDS`). No TownStar/Platinum/Yango adapters exist. Intercity: `OTHER_TOWN_TOKENS` → pickup only; the D16 "intercity flat estimates" were never implemented.
- **Return-to-vendor / failed-delivery workflow: MISSING.**

### C7. n8n dispatch-related workflows — **PARTIAL (activation unverified)**
- `infra/n8n/dispatch-stale-alert.json` (15 min → `POST /internal/n8n/dispatch-stale/tick`, `routers/internal_n8n.py`), `notification-dispatch.json` (1 min), `order-jobs.json` (hourly auto-confirm / auto-release), `reservation-sweeper.json`, `low-stock-alert.json`, `reconciliation.json`, `payouts.json`, `release-job.json`. All exports `active:false`; live state on Hetzner not evidenced. No vendor-SLA, rider-SLA or COD-remittance workflows.

---

## D. Finance

### D1. Delivery fee charging and allocation — **BUG / UNSUITABLE**
- Charged per vendor group into `orders.delivery_fee_ngwee`; summed into `checkout_groups.delivery_fee_ngwee`; included in the Lenco charge (prepaid) or in the rider's COD amount (`compute_cod_amount_ngwee` = subtotal + fee).
- **The fee is paid out to the vendor.** Release gross = items + delivery fee: `services/escrow/release.py::_order_gross_ngwee` returns `subtotal + delivery_fee_ngwee`; `services/escrow/release_accounting.py::compute_release_amounts` sets `net = gross − commission`, and commission is computed only on item lines (`services/orders/create.py::_build_commission_snapshot`). The same holds for COD: `services/payments/cod.py::_load_cod_order` sets `collectable_ngwee = subtotal + delivery_fee`, and `confirm_cod_collection` posts `RELEASE_TO_VENDOR` for `collectable − commission`.
- Under D16 (`docs/plan/00-decisions.md`) **the platform books and pays the courier**. So Convergeo pays the rider and also passes the customer's delivery fee to the vendor. Every delivered order loses the full courier cost.
- **Correction (Phase 0, before first delivered order is released):** exclude `delivery_fee_ngwee` from vendor release gross in both paths and post it to a platform `delivery_revenue` account (new ledger template, additive), unless the order is vendor-self-delivered. Add `ledger_accounts` kinds `delivery_revenue` and `courier_payable` (additive seed, like `20261107130000_seed_ledger_accounts.sql`).

### D2. Ledger recording of logistics — **MISSING**
- `LedgerTemplate` (`services/ledger/templates.py`): `charge_received, escrow_hold, commission_capture, release_to_vendor, payout_executed, refund_lane1/2, cod_collected, clawback, refund_reversal, lenco_fee`. Platform accounts: `platform_cash, escrow, commission_revenue, fees`; per vendor: `vendor_payable, cod_receivable`. No delivery revenue, courier cost, courier payable or rider float.

### D3. Rider pay — **MISSING**
- Only `dispatch_requests.quoted_price_ngwee` (snapshot of `courier_partner_zones.price_ngwee`, nullable "quote per job"). No actual cost, no courier invoice/payable, no payout rail for couriers (`payouts.vendor_id` NOT NULL — vendor-only).

### D4. COD cash collection and remittance — **PARTIAL, two BUGs**
- **Model:** "platform-collect" (`services/payments/cod.py` module docstring): rider collects subtotal + fee and remits to the platform; `cod_collected` credits `platform_cash` and releases net to `vendor_payable`.
- Endpoints: `POST /vendor/orders/{id}/cod/confirm-collection|refuse-collection`, `POST /admin/orders/{id}/cod/confirm-collection|refuse-collection` (`routers/cod.py`).
- **BUG 1 — COD orders auto-complete before cash is booked.** `routers/internal_order_jobs.py::_list_auto_confirm_candidates` moves **every** `delivered` order (COD included) to `completed` after `release_after_delivered_hours` (default 48, `services/escrow/release.py`); customers can also `confirm-received` (`routers/order_confirmation.py`). `confirm_cod_collection` then refuses because `_COLLECTABLE_STATUSES = {"delivered"}` and no collect transaction exists → **cash can never be booked, vendor never paid via ledger**. Fix: exclude `cod AND no cod-collect-<id> transaction` from auto-confirm (and from customer confirm-received), or allow `completed` in `_COLLECTABLE_STATUSES` when no collect txn exists.
- **BUG 2 — vendor can confirm platform cash.** In platform-collect, the vendor endpoint `vendor_confirm_cod_collection` posts `platform_cash` (as if the platform received the cash) and makes the vendor's net payable for payout. If the rider handed cash to the vendor (very common informally), the platform pays the vendor a second time. Fix for Phase 0: admin-only confirmation (disable the vendor route or gate it behind a `cod_model='vendor_remit'` flag), and record who holds the cash.
- **Gap:** receivable is opened lazily (`record_cod_receivable` is only called inside confirm/refuse), so outstanding COD is invisible in the ledger until ops acts; receivable is per **vendor**, not per **courier**, so "how much cash is courier X holding" cannot be answered. No remittance batch, no daily cash-up, no variance record.
- Refusal (`refuse_cod_collection`) only from `shipped`; cancels the order; stock not restored (A4).

### D5. Vendor settlement — **WORKS** (except D1 inclusion of fee)
- Escrow release (`services/escrow/release.py::evaluate_and_release`, hourly `infra/n8n/release-job.json`), payouts (`services/payouts/*`, `infra/n8n/payouts.json`), with refund gates, dispute holds, velocity caps. COD orders are `not_eligible` for automatic release (correct).
- **BUG 3 — prepaid auto-release ignores delivery state.** `_list_auto_release_candidates` releases any order `shipped` for ≥ `release_after_shipped_days` (7) without a dispute. A dispatch that failed after pickup, or a vendor "ship" with no courier (C5), still pays the vendor after 7 days. Fix: exclude orders with a latest `dispatch_requests.status` in (`failed`,`cancelled`) or with no delivered dispatch when `courier_dispatch` is ON.

### D6. True fulfilment cost / delivery margin — **MISSING**
- Not computable today: revenue side exists (`orders.delivery_fee_ngwee`), cost side is absent (no actual courier cost per dispatch, no batch to apportion a shared trip, no failed-attempt cost). The reference doc itself estimates Band A (K30) at or below car ride-hail cost.
- **Correction:** Phase 0: add `actual_cost_ngwee` and `paid_to` on the dispatch record (additive column) and a weekly SQL/n8n report: fee charged vs cost per order, per zone, per courier. Phase 1: apportion batch cost to orders.

---

## E. Database / architecture

### E1. Logistics-relevant tables that exist (reuse, do not duplicate)
`checkout_groups` (customer checkout) · `orders` (= vendor fulfilment order) · `order_items`, `order_item_products`, `order_item_stock_consumption` · `order_events` (audit) · `order_money_gates` · `addresses(user_id, label, landmark NOT NULL, lat, lng, phone)` · `vendor_locations` (branches, hours, phone, primary) · `listing_location_stock` · `stock_reservations` · `delivery_zones` · `platform_config` · `courier_partners`, `courier_partner_zones`, `dispatch_requests`, `dispatch_request_events`, `dispatch_handover_codes` · `notification_outbox` · `ledger_accounts/transactions/postings` · `payouts` · `returns`, `refunds`, `disputes` · `audit_log` · `feature_flags`.

### E2. Indexes and performance
- Present: `orders_checkout_group_id_idx`, `orders_vendor_id_status_idx`, `orders_customer_id_created_at_idx`, `order_items_order_id_idx`, `order_events_order_id_created_at_idx`, `notification_outbox_status_next_retry_at_idx`, `vendor_locations_lat_lng_idx`, dispatch indexes listed in C4.
- Missing for dispatch reads: the board filters `orders WHERE fulfilment='delivery' AND status IN ('confirmed','processing')` — no index leads on `status`; fine at pilot volume, add a partial index `(status, created_at) WHERE fulfilment='delivery'` before scale.
- Board, stale and context queries use correlated subqueries per row (`sum(order_items)`, primary location, last failure) with `LIMIT 100`; acceptable for the pilot.
- Host: single Hetzner CX23 (2 vCPU / 4 GB, 2 uvicorn workers), synchronous psycopg pool. Adequate for pilot; a VRP solver (OR-Tools) must not run in the API request path on this box — run it as a separate job/container.
- No PostGIS: distance is Python haversine or SQL arithmetic. Adequate for Lusaka zone/cluster logic at pilot scale; PostGIS (available on Supabase) becomes useful once polygon zones and clustering are needed.

### E3. Events / outbox / automation
- Outbox pattern with dedupe and channel fallback: WORKS. Order lifecycle → `services/orders/events.py::emit_order_lifecycle` + `services/notifications/events.py::EVENT_REGISTRY` (`order_cancelled`, `order_processing`, `order_completed` silent; `order_delivered` mapped but never emitted).
- No domain event stream for logistics (no "ready", "rider assigned", "attempt failed" events) — dispatch writes only `dispatch_request_events` (audit) and one outbox message.

### E4. Gap map for §8 entities (reuse first)

| §8 entity | Status | Reuse / extend | New (only if needed) |
|---|---|---|---|
| Fulfilment orders | EXISTS | `orders` (one per vendor) | add `pickup_location_id`, `ready_at`, `promised_by` |
| Delivery consignments (customer-level, multi-vendor) | MISSING | key off `checkout_groups.id` + `address_id` | `delivery_consignments` (one drop per customer address/time window) |
| Parcels | MISSING | `order_items` for contents | `parcels` (order_id, size/weight class, label code) — only when one order splits or many orders share a bag |
| Pickup locations | EXISTS | `vendor_locations` | — |
| Collection hubs | MISSING | not `vendor_locations` (hubs are platform-owned, not vendor branches) | `hubs` table later; not Phase 0 |
| Drivers | MISSING | `courier_partners` = companies | `couriers_riders` (partner_id, name, phone, auth user optional, status) |
| Vehicles | MISSING | — | column `vehicle_class` on rider; table later |
| Routes / stops / batches | MISSING | `dispatch_requests` stays the per-order leg | `delivery_runs` (rider, date, status, cost) + `delivery_run_stops` (run_id, kind pickup/drop, dispatch_request_id, location, seq, eta, arrived_at) |
| Transport providers | PARTIAL | `courier_partners` (`integration_kind`) | add `kind` (last_mile / intercity_bus / freight) |
| Transport bookings | MISSING | `dispatch_requests.courier_reference` | `transport_bookings` for intercity (waybill, depot, fare) |
| Service levels | MISSING | — | `delivery_service_levels` (same-day, next-day, scheduled) referenced by orders |
| Pricing rules | PARTIAL | `delivery_zones`, `courier_partner_zones.price_ngwee`, `platform_config` | `delivery_pricing_rules` only when vendor-leg pricing is introduced |
| Proof of collection | MISSING | `dispatch_request_events` | vendor-confirmed handover code at pickup (mirror of `dispatch_handover_codes`) |
| Proof of delivery | EXISTS | handover code / POD photo | — |
| Delivery exceptions | PARTIAL | `failure_reason` text | `delivery_exceptions` (type enum, owner, resolution, cost) |
| Returns / reverse logistics | PARTIAL | `returns` (money only, `DEFAULT_RETURN_SHIPPING_NGWEE = 5_000` in `services/returns/lane1.py`) | reverse `dispatch_requests` with `direction='return'` (additive column) |
| Vendor fulfilment schedules | PARTIAL | `vendor_locations.hours` | `prep_minutes`, cut-off times on vendor/location |

---

## F. Security, RBAC, accountability (§9, as it applies to what exists)

| Role in brief | Exists today | Finding |
|---|---|---|
| Super Admin / Admin | `admin`, `superadmin` in `user_roles`; admin app on separate origin + Cloudflare Access | All dispatch actions require full `admin` (`require_role("admin")`). |
| Logistics Admin | **MISSING** | `admin_roles_permissions_valid` allows only `finance.read, events.manage, products.manage, services.read, vendors.manage, ads.manage, analytics.read, inventory.read`. A dispatcher must be a full admin (can also touch escrow, refunds, KYC). Add `logistics.manage` (and `cod.reconcile`) permissions and gate `/admin/dispatch/*` + COD admin routes with them. |
| Finance Admin | `finance.read` only | Read-only; COD confirm/refuse is full-admin. |
| Vendors | WORKS | Vendor endpoints check `vendors.owner_user_id`; `GET /vendor/orders/{id}/delivery` hides courier contacts and handover code. Vendor COD confirm is a money-authority problem (D4 BUG 2). |
| Drivers | **MISSING** | No identity; drivers receive customer phone and landmark by WhatsApp (`build_courier_message`), which is operationally necessary but untracked (no record of which rider saw which address). |
| Hub operators / Support | MISSING | — |
| Customers | WORKS | Delivery view only for the owner (`get_customer_order_delivery`); handover code shown only while dispatch active. |
| Audit | WORKS | `order_events`, `dispatch_request_events` (append-only trigger), `audit_log`, `AdminAuditedRoute` + `recorder.record(...)`; handover code never logged. |
| RLS | WORKS | courier tables admin-only RLS; dispatch tables admin-select, service-role writes; `dispatch_handover_codes` has no client grant. |

---

## G. Phase-0 operational fixes (first weeks of COD Lusaka delivery)

Ordered by money/stranding risk. All are small, additive changes on existing code; none needs a new subsystem.

1. **Stop paying the delivery fee to vendors.** `services/escrow/release.py::_order_gross_ngwee` and `services/payments/cod.py::_load_cod_order` / `confirm_cod_collection`: exclude `delivery_fee_ngwee` from vendor release; post it to a new platform `delivery_revenue` account (new template in `services/ledger/templates.py`, seed migration). Must land before the first delivered order is released.
2. **Unblock COD collection after auto-confirm.** `routers/internal_order_jobs.py::_list_auto_confirm_candidates` (and customer `confirm-received` in `routers/order_confirmation.py`): skip COD orders without a `cod-collect-<order_id>` ledger transaction; or accept `completed` in `services/payments/cod.py::_COLLECTABLE_STATUSES` when no collect txn exists.
3. **Make COD confirmation admin-only for platform-collect.** Disable `routers/cod.py::vendor_confirm_cod_collection` (feature-flag it) so only ops, after the rider's cash or MoMo remittance arrives, posts `platform_cash`. Add `collected_by` / `remitted_at` / `remittance_reference` to the dispatch record so ops can run a daily cash-up per courier.
4. **Block prepaid auto-release for undelivered dispatches.** `_list_auto_release_candidates`: exclude orders whose latest dispatch is `failed`/`cancelled`, or that have no delivered dispatch while `courier_dispatch` is ON.
5. **Close the "Kabwe = Band B" hole.** `routers/checkout.py::OTHER_TOWN_TOKENS`: add every non-Lusaka town (or move to `platform_config`); log each `delivery_fallback_zone` hit for daily review; add optional GPS capture on the customer address form.
6. **One dispatch path.** With `courier_dispatch` ON, refuse vendor `ship` for delivery orders (`routers/vendor_orders.py::_available_vendor_actions`) unless self-delivery is chosen, and hide `apps/admin/…/DispatchPanel.tsx` (legacy `POST /admin/orders/{id}/dispatch` kept as audited break-glass).
7. **Allow re-dispatch after a failed pickup-stage delivery.** `services/dispatch/service.py::DISPATCHABLE_ORDER_STATUSES` and `board_snapshot`: include `shipped` orders whose last dispatch is `failed`, so ops can send a second attempt or a return-to-vendor run; add a "returned to vendor" action that cancels from `shipped` and restocks (extend the trigger condition in `release_cancelled_order_stock` only for that explicit path).
8. **Vendor readiness signal.** Add `processing → ready` for delivery orders (`ready_for_collection`, `services/orders/state.py::TRANSITION_TABLE`) and require it before `picked_up`; until then, the runbook rule is "ops calls the vendor before booking a rider".
9. **Pickup point = the branch that holds the stock.** `load_order_dispatch_context`: use `order_item_stock_consumption.location_id` when present; flag multi-branch orders on the board.
10. **Group the board by checkout + address.** Add `checkout_group_id`, address landmark and vendor area to `board_snapshot` rows and sort/group by them in `DispatchBoard.tsx`, so ops can book one rider for a multi-vendor checkout by hand (manual consolidation) and send one combined courier message.
11. **Alerts and customer messages.** Extend `dispatch-stale-alert` to `accepted` > 30 min and `picked_up` > 120 min; add an n8n tick for vendor `placed` > 2 h (`CONFIRM_SLA_HOURS`); emit `order_delivered` on handover/POD delivery; map `order_cancelled` to a customer template so COD customers learn of a rejection; confirm Meta approval of `courier_dispatch_request`.
12. **Record real courier cost.** Additive `dispatch_requests.actual_cost_ngwee` (set on delivered/failed) + weekly fee-vs-cost report by zone and courier.
13. **RBAC:** add `logistics.manage` and `cod.reconcile` to `admin_roles_permissions_valid` and gate dispatch/COD admin routes, so a dispatcher does not need full admin.
14. **Docs:** correct OCI → Hetzner in `infra/README.md`, `infra/ENVIRONMENTS.md`, `CLAUDE.md`; refresh §1/§5 of `docs/ops/lusaka-delivery-reference-prices.md`; record live n8n workflow state on Hetzner.
15. **Operational guard until 1–4 land:** keep `courier_dispatch` OFF for prepaid, or settle courier cost/fee and COD cash manually in a spreadsheet keyed on `order_reference`, and do not let the release/order-jobs n8n workflows run unattended.

---

## H. What must NOT be rebuilt

- Per-vendor order split under `checkout_groups` and `create_orders_atomic` (idempotent, atomic, stock-safe).
- Server-authoritative fulfilment (`checkout_groups.fulfilment_choices`, `services/orders/fulfilment.py`).
- Order state machine (`services/orders/state.py`) and its SQL authority/money guards and `order_events` audit — extend the table, do not replace.
- Stock reservation/consumption/release (`services/stock/*`, `order_item_stock_consumption` trigger).
- Courier dispatch v1 tables, guard/audit triggers, handover-code chain of custody with lockout, POD-photo rule, courier directory and zone service areas, admin board UI — extend with a batch/run parent, rider identity and the fixes above.
- Notification outbox + dispatcher + channel fallback; n8n-tick-calls-internal-endpoint pattern with internal tokens.
- Ledger engine, escrow release, payouts with gates — add delivery/courier accounts and templates, do not fork.
- Pickup QR/PIN flow, `vendor_locations` branches + hours, `listing_location_stock`.
- Delivery zones/bands as the customer-facing price table (add vendor-leg and multi-vendor rules on top later).
