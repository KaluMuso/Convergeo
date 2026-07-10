> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 9 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — reuse existing tables/triggers; the ONLY DDL allowed is a reversible `create or replace` of one existing audit function (below), which does **not** change `db.ts`. **Run the FULL `uv run pytest` before reporting.**

# M09-P01 — Order state machine

## 1. Context

**Wave 9 (parallel ×6).** Grounded against as-built `master` (**read `supabase/migrations/0005_orders.sql` before coding**):

- **`orders.status`** default `'placed'`, check in exactly: **`placed, confirmed, processing, ready, shipped, delivered, completed, cancelled`**. `orders(id, checkout_group_id, customer_id, vendor_id, status, fulfilment, delivery_fee_ngwee, …)`.
- **Two triggers already exist on `orders` — cooperate with them, do NOT re-implement or drop them:**
  1. `guard_orders_status_update()` — **status is server-controlled**: a non-`service_role`/non-`admin` caller that changes `status` gets `raise exception 'order status is server-controlled'`. So your transitions run via the **service-role** client (which the guard permits).
  2. `audit_orders_status_change()` — on every `status` change auto-inserts `order_events(order_id, actor, from_status, to_status)` with **`actor = auth.uid()`** and **no `note`**. Under a service-role call `auth.uid()` is **NULL**, so the auto-row is actor-less and note-less.
- **`order_events(id, order_id, actor, from_status, to_status, note, created_at)`** exists (append-only; parties-read RLS; trigger-written). Payment status for cancellation rules: read the order's payment state (`payments`/ledger land in M08 — **if unavailable, gate on a `payment_status`-style read with a documented fallback**, do not invent a table).
- `app/services/` is an implicit namespace package — create `app/services/orders/` with its **own `__init__.py`**; **do NOT create `app/services/__init__.py`**. This pebble adds **no router** (pure service layer; endpoints are M09-P02).
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P01. **The transition test table is GENERATED from the spec's transition table in that file** — read it.

## 2. Objective & scope

The order state machine: a transition table `placed→confirmed→processing→ready|shipped→delivered→completed` + cancellation branches, with **actor-permission per transition** (customer/vendor/admin/system), performed via a guarded service-role update, and an **audit row carrying actor + note** for every transition.
**Non-goals:** no HTTP endpoints (M09-P02), no order creation (M07-P06), no payment/refund execution (M08), no notifications.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/orders/__init__.py` · `orders/state.py` (transition table + `(state × event × actor) → next|reject`; the single authority) · `orders/audit.py` (writes an `order_events` row with **actor + note**) · `services/api/tests/test_order_state.py`
- **Allowed DDL (only if you take the audit-enrichment route below):** ONE new migration `supabase/migrations/0014_order_audit_actor_note.sql` that **`create or replace`s `audit_orders_status_change()`** to also capture `note` and a service-role actor from transaction-local settings (`current_setting('app.order_actor', true)` / `app.order_note`) that `state.py` sets via `set_config` before the update. **Function-only — no table/column change, so `db.ts` is unchanged.** Reversible (documented: restore the 0005 body). If you instead write the enriched row directly from `audit.py`, you MUST avoid a duplicate row (the auto-trigger already writes one) — **pick ONE path and state which in the report.**
  **Guardrail: nothing else. Do NOT touch `0005`, `guard_orders_status_update`, `main.py`, `db.ts`, `app/services/__init__.py`, other tables.**

## 4. Implementation spec

- **`state.py`:** a declarative transition table keyed by `(from_status, event)` → `to_status`, each with the **allowed actor roles**. Every legal transition in the spec table is present; every other `(state, event, actor)` is an explicit reject. **Cancellation encodes payment status:** paid → the transition demands a refund path (flagged/blocked pending M08), unpaid → straight cancel. The transition executes the `orders.status` update via the **service-role** client (guard permits it); concurrent conflicting transitions resolve by **row lock — one wins, the loser sees the already-moved state and is rejected**.
- **`audit.py`:** guarantees each committed transition yields an `order_events` row with **actor (the acting user/vendor/admin/system) + a note**. Reconcile with the existing auto-trigger per your chosen path (GUC-enriched trigger via `0014`, or single explicit write) — **no duplicate rows, no missing actor/note**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; status server-controlled (guard trigger enforced — tested that a non-service caller cannot flip status); audit append-only + complete; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_order_state.py`: **generated matrix** — every legal transition permitted with its actor, every illegal `(state, event, actor)` rejected; **audit completeness** (each transition writes exactly one `order_events` row with actor + note — no dup, no null actor); **cancellation payment rules** (paid → refund-path required, unpaid → straight cancel); **concurrent conflicting transitions** (row lock, one wins). If you add `0014`, note it replays clean in the migration order. **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Exhaustive `(state × event × actor)` matrix has an explicit expectation each; illegal transitions rejected.
- [ ] Every transition writes ONE audit row with actor + note (no dup from the auto-trigger); cancellation encodes payment status; concurrent transitions row-locked.
- [ ] Cooperates with the existing guard/audit triggers (not re-implemented/dropped); `db.ts` unchanged; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P01 — Order state machine
**STATUS/FILES/DEVIATIONS** (state clearly: audit path chosen — `0014` GUC-enriched trigger vs single explicit write — and how duplicates are avoided) **/TESTS** (paste matrix summary + audit-completeness + concurrent-transition + full-pytest tail) **/EXCERPTS** the transition table + the audit-write reconciliation — nothing else **/QUESTIONS**
