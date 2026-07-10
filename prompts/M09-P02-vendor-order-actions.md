> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M09-P02 — Vendor order actions

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **State machine merged (M09-P01):** `app/services/orders/state.py` — the transition table + `transition_order(...)` (actor-permission per transition; sets `app.order_actor`/`app.order_note` GUCs so the `0014` audit trigger records actor+note). **All vendor actions go THROUGH `state.py` — never raw status UPDATEs.** Vendor actions map to events: **confirm, reject (with reason), start_processing/pack, ship (with tracking note), ready_for_pickup**. A **reject on a PAID order enqueues the refund path** (M09-P01 encodes paid-state; you trigger it via the transition + an outbox event).
- Vendor app `localePrefix:"always"` → pages at **`apps/vendor/app/[locale]/orders/`** (spec's `app/orders/` is stale). Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Ownership: **vendor B cannot act on vendor A's order → 403** (derive vendor_id from the authenticated vendor, not the request). Actions emit `notification_outbox` events (M14-P01 dispatches).
- i18n `vendor` namespace registered; `vendor.json` — **you solely own it this wave** (append a nested `orders` section; do NOT reformat `onboarding`/`listings`/`profile` siblings).
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P02. **Pickup QR/PIN verify = M09-P03 (not this wave).**

## 2. Objective & scope

Vendor order actions (confirm / reject-with-reason / pack / ship-with-tracking-note / ready-for-pickup) gated by the state machine + vendor ownership, a mobile-first big-button action bar, and an order detail page. **Reject requires a customer-visible reason and triggers the refund path if the order is paid**; ship captures a free-text tracking note; every action emits an outbox event.
**Non-goals:** no order creation (M07-P06), no QR/PIN (M09-P03), no admin ops (M13-P06), no schema, no `state.py` changes.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/vendor_orders.py` (action endpoints) · `apps/vendor/app/[locale]/orders/[id]/page.tsx` (order detail + actions) · `apps/vendor/app/[locale]/orders/_components/action-bar.tsx` · `services/api/tests/test_vendor_orders.py`
- **Modify:** `packages/i18n/messages/en/vendor.json` (append nested `orders` section)
  **Guardrail: nothing else. Do NOT touch `orders/state.py`/`audit.py` (M09-P01 — call `transition_order`), `orders_create.py` (M07-P06), `main.py`, schema.**

## 4. Implementation spec

- **`vendor_orders.py`** (`require_role('vendor')` + ownership): endpoints for confirm / reject (requires `reason`, customer-visible) / pack / ship (requires `tracking_note`) / ready-for-pickup. Each calls `app.services.orders.state.transition_order(order_id, event, actor=vendor, note=…)` — **the state machine gates legality + actor-permission** (an action illegal from the current state → rejected). **Cross-vendor → 403** (order's vendor_id must equal the caller's). **Reject on a paid order → refund path** (transition encodes it; enqueue the refund outbox event). Every action emits a `notification_outbox` event (order-status-changed).
- **Order detail page** (`orders/[id]`): items, payment/fulfilment context, timeline (from `order_events`), and the **big-button mobile-first `action-bar.tsx`** showing only the actions legal from the current state. All copy via `vendor` (`orders.*`); 360px-first.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px big-button action bar; vendor-scoped (cross-vendor 403 — tested); transitions via state machine only (no raw UPDATE); reject reason customer-visible; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_vendor_orders.py`: **authz matrix** (vendor B cannot act on vendor A's order → 403); **state-gated action availability** (illegal-from-state action rejected); **reject on paid → refund event enqueued**; ship requires tracking note; actions emit outbox. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite.**

## 11. Acceptance criteria / DoD

- [ ] Vendor B cannot act on vendor A's order; only state-legal actions available; reject requires reason.
- [ ] Reject on paid order enqueues refund; ship captures tracking note; actions emit outbox; transitions via `state.py` only.
- [ ] `vendor.orders.*` nested (sole owner); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P02 — Vendor order actions
**STATUS/FILES/DEVIATIONS/TESTS** (paste authz-403 + state-gated availability + reject→refund + full-pytest tail) **/EXCERPTS** the ownership check + a `transition_order` call — nothing else **/QUESTIONS**
