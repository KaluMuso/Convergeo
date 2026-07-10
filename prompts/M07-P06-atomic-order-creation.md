> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — no migration (all columns exist). Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M07-P06 — Atomic order creation

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **All columns exist — NO migration:** `checkout_groups(idempotency_key text NOT NULL UNIQUE, subtotal_ngwee, delivery_fee_ngwee, total_ngwee, status)` (0012) → **idempotency is via this unique key**. `orders(checkout_group_id, vendor_id, customer_id, status default 'placed', fulfilment, delivery_zone, address_id, delivery_fee_ngwee, cod, commission_snapshot jsonb)` + `order_items` (+ `order_item_tickets`/`order_item_services` kind rows) (0005). **`commission_rates(category_key, rate_bps)`** (0008) → snapshot `rate_bps` per line at purchase into `orders.commission_snapshot` (immutable thereafter).
- **State machine merged (M09-P01):** `app/services/orders/state.py` — order rows are created at `'placed'`; **emit `order.placed` to `notification_outbox`** (M14-P01 dispatches). **Reservations merged (M07-P02):** `app/services/stock/claim.py` — **consume** the checkout's reservations on order creation. **Do NOT re-implement or edit `state.py`/`stock/*` — call them.**
- `app/services/orders/` exists (M09-P01 owns `state.py`/`audit.py`) — you add **`create.py`** (new file, no `__init__.py` needed — dir already packaged). Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Money = int ngwee (no float); reuse `app.services.cart` totals semantics — **totals must equal the server checkout session; never recompute divergently**.
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P06. **No payment execution (M08) — this creates the order + emits `order.placed`; payment/ledger posting is on webhook (W11).**

## 2. Objective & scope

A single-transaction order creation: from a validated checkout session → `checkout_group` (completed) + **per-vendor `orders` split** + `order_items` (+ kind detail rows) + **commission-rate snapshot (bps from `commission_rates` at purchase time)** + fees; **consumes reservations**; **idempotent via `checkout_groups.idempotency_key`** (retry returns the same group, no double order); emits `order.placed` to the outbox.
**Non-goals:** no payment initiation/ledger posting (M08/W11), no USSD-wait UX (M07-P07), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/orders/create.py` (the single-transaction creator) · `services/api/app/routers/orders_create.py` (`POST /orders` with client idempotency key) · `services/api/tests/test_order_creation.py`
  **Guardrail: nothing else. Do NOT touch `orders/state.py`/`audit.py` (M09-P01 — call), `stock/*` (M07-P02 — call), `orders/0005`, `main.py`, schema.**

## 4. Implementation spec

- **`create.py`:** in **ONE DB transaction** — mark `checkout_group` completed; **split into per-vendor `orders`** (each `status='placed'`, fulfilment/zone/fee from the session, `cod` flag from the chosen method); create `order_items` (+ ticket/service kind rows where applicable); **snapshot commission**: for each line resolve `commission_rates.rate_bps` by the product/listing category **at purchase time** into `orders.commission_snapshot` (immutable after — never re-read live later); **consume reservations** via `app.services.stock.claim`. **Partial failure rolls back everything.** **Idempotent:** a retry with the same `idempotency_key` returns the **identical** group (no double order). Emit `order.placed` per order to `notification_outbox` (dedupe_key from order id). Totals = Σ items + fees, **ngwee-exact**, equal to the server session total.
- **`orders_create.py`** (auth required): `POST /orders` taking the checkout session + client idempotency key → returns the created group. Reject if the session/reservations expired.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; single transaction (all-or-nothing); idempotent; commission snapshot immutable; totals ngwee-exact; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_order_creation.py`: **idempotency replay** (same key → identical group, no second order); **rollback injection** (a mid-transaction failure leaves NOTHING written); **multi-vendor split math** (totals = Σ items + fees, ngwee-exact, per-vendor); **snapshot correctness** (change `commission_rates` AFTER purchase → snapshot unchanged); reservations consumed; `order.placed` enqueued. **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Partial failure rolls back everything; duplicate submit returns the identical group (no double order).
- [ ] Totals = Σ items + fees ngwee-exact; commission snapshot immutable vs later config change; reservations consumed; `order.placed` emitted.
- [ ] Calls `state.py`/`stock` (not re-implemented); no schema; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M07-P06 — Atomic order creation
**STATUS/FILES/DEVIATIONS/TESTS** (paste idempotency-replay + rollback + split-math + snapshot-immutability + full-pytest tail) **/EXCERPTS** the single-transaction body + commission snapshot — nothing else **/QUESTIONS**
