> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 runs pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0025` (funnel events) this wave** (renumber to next free slot if claimed at merge). **Run the FULL `uv run pytest` before reporting.**

# M07-P08 — Abandoned-checkout events & funnel analytics

## 1. Context

**Wave 15 (parallel).** Grounded against as-built `master`:

- **Checkout/cart MERGED (M07-P06, reservations M07-P02):** reservations have a TTL; abandonment is detected on **reservation expiry** with a cart snapshot. **Notifications outbox MERGED (M14-P01):** `enqueue_outbox_row`.
- **⚙ Abandoned-cart workflow already ships flag-OFF (M14-P06, merged):** `infra/n8n/abandoned-cart.json` + `/internal/n8n/abandoned-carts` are gated off. You emit the `abandoned_checkout` outbox event (**flag-gated OFF per D2** — no notification while off); the M14-P06 workflow stays disabled. Do NOT enable it.
- **New event files (scope-fenced):** funnel emission patches are **confined to new files** `app/services/cart/events.py` + `app/services/orders/events.py` (do NOT scatter edits across cart/order routers). If those filenames already exist on master, extend them additively; otherwise create them.
- **Funnel table (migration `0025_funnel_events.sql`):** server-side funnel events (`cart_add`, `checkout_start`, `step_complete`, `payment_start`, `order_placed`, `abandoned`) → analytics table; schema **stable for a GA4 mirror (M16-P05)**. RLS admin/service-role.
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P08. **Backend/analytics only — no user-facing i18n.**

## 2. Objective & scope

Server-side funnel events (`cart_add → checkout_start → step_complete → payment_start → order_placed`, plus `abandoned` on reservation expiry with cart snapshot) written to a funnel table, and an `abandoned_checkout` outbox event **flag-gated OFF**. Schema stable for the later GA4 mirror.
**Non-goals:** no notification send (flag off; M14-P06 workflow stays disabled), no funnel UI/dashboard (M13-P09 aggregates separately), no GA4 mirror (M16-P05).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/analytics/funnel.py` (event recorder + abandonment sweeper) · `services/api/app/services/cart/events.py` (cart_add/checkout_start emitters) · `services/api/app/services/orders/events.py` (payment_start/order_placed emitters) · `services/api/app/routers/internal_funnel.py` (internal-token abandonment sweeper tick) · `supabase/migrations/0025_funnel_events.sql` · `infra/n8n/funnel-abandon.json` (cron → sweeper) · `services/api/tests/test_funnel.py`
  **Guardrail: nothing else. Do NOT edit cart/checkout/order routers or `orders/state.py` (emit via the new `events.py` files, called from existing hooks only if a hook already exists — otherwise the sweeper + explicit emit calls), `abandoned-cart.json` (M14-P06 — stays off), `main.py`, db.ts beyond `0025`.**

## 4. Implementation spec

- **`funnel.py`:** `record_event(*, stage, checkout_group_id, snapshot)` → insert funnel row (idempotent per (group, stage)); `sweep_abandoned(now)` → find reservations expired without `order_placed`, record `abandoned` with cart snapshot, enqueue `abandoned_checkout` outbox event **only if the flag is ON** (default OFF → no enqueue).
- **`cart/events.py` / `orders/events.py`:** thin emitters wrapping `record_event` for their stages.
- **`internal_funnel.py`:** `POST /internal/funnel/abandon-tick` (internal-token) → `sweep_abandoned`. `funnel-abandon.json` cron calls it.
- **`0025`:** `funnel_events` (stage, checkout_group_id, snapshot jsonb, created_at; unique (group, stage)); RLS admin/service-role; GA4-mirror-stable columns.

## 5–9. Security etc.

Flag OFF ⇒ no notification enqueued; funnel sequence integrity (idempotent per stage); abandonment on reservation expiry with snapshot; internal tick token-guarded; no secrets.

## 10. Tests (RUN before reporting)

`test_funnel.py`: **funnel sequence integrity** (stages recorded in order, idempotent per (group, stage)); **abandonment trigger** (expired reservation without order_placed → `abandoned` + snapshot); **flag gating** (flag off → no `abandoned_checkout` outbox row; flag on → enqueued). `0025` replay note. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Abandonment detected on reservation expiry with cart snapshot; events schema stable for GA4 mirror; flag off = no notification.
- [ ] `0025` additive+reversible; emission confined to the new `events.py` files; internal tick token-guarded; full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M07-P08 — Abandoned-checkout events & funnel analytics
**STATUS/FILES/DEVIATIONS** (how stages are emitted without scattering router edits; flag-gating source; abandonment sweeper) **/TESTS** (paste sequence-integrity + abandonment-trigger + flag-gating + full-pytest tail) **/EXCERPTS** the abandonment sweep + flag gate — nothing else **/QUESTIONS**
