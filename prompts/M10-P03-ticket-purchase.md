> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M10-P03 — Purchase & RSVP through checkout

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **Atomic ticket claim MERGED (M10-P02, `services/tickets/inventory.py`):** call `claim_ticket(service_client, *, instance_id, ticket_type_id, holder_user_id, qty)` — it enforces capacity + qty_cap + per_customer_cap under `pg_advisory_xact_lock` + `FOR UPDATE` (no oversell). Reuse it; do NOT reimplement claiming.
- **`tickets` (0004) + `order_items` `item_kind` (0005) exist** — issue tickets by inserting `tickets` rows (`status='issued'`, secrets server-controlled by the guard trigger) linked to `order_item_id`. **No migration.**
- **Checkout/cart MERGED (M07):** ticket line = `item_kind=ticket`. **Commission snapshot MERGED (M08-P12):** **5% paid tickets, 0% free events** — snapshot at purchase per the M08-P12 convention.
- **⚙ Issuance-on-payment seam (idempotent):** tickets are **issued only after verified payment** (webhook-replay-safe), **except free RSVP which skips payment and issues immediately**. The payment-success paths (`payments_card.py` `_mark_fulfilled`, `payment_status.py` SUCCESS transition) are **merged and NOT yours to edit**. Provide an **idempotent issuance service** `issue_tickets_for_paid_order(service_client, order_id)` (issues once per order's ticket items — a second call/webhook replay is a no-op) and wire it via the **least-invasive seam you own**: an internal fulfilment tick (`POST /internal/tickets/issue-tick`, internal-token, scans SUCCESS-paid orders with unissued ticket items) — mirror the sweeper/tick pattern (`internal_payment_sweeper.py`). **Do NOT edit the payment routers.** Idempotency key = order_item (one ticket set per paid item).
- **Payment failure → release claimed capacity** (void the claim / reservation TTL). Claim honors reservation TTL (M07-P02).
- **CTA:** replace the M05-P11 stub `ticket-picker.tsx` on the public event page `(shop)/e/[slug]`.
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P03. **i18n `events` (append-rule):** append `events.ticketPurchase.*` (M10-P04 also appends to `events.json` this wave — disjoint sections; rebase-append on conflict).

## 2. Objective & scope

Ticket purchase through checkout: claim capacity at checkout (M10-P02), issue tickets **after verified payment** (idempotent, replay-safe), **free RSVP skips payment** (issue immediately, 0% commission), **payment failure releases claimed capacity**. Replace the event-page ticket-picker stub.
**Non-goals:** no wallet/QR (M10-P04), no verify/check-in (M10-P06), no new payment logic (call merged M07/M08 — do not edit payment routers), no schema change.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/tickets/purchase.py` (checkout claim + `issue_tickets_for_paid_order` idempotent + free-RSVP path + failure-release) · `services/api/app/routers/internal_tickets.py` (internal-token issuance tick) · `apps/customer/app/[locale]/(shop)/e/[slug]/_components/ticket-picker.tsx` (replaces M05-P11 stub) · `services/api/tests/test_ticket_purchase.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/events.json` (append `events.ticketPurchase.*`)
  **Guardrail: nothing else. Do NOT touch `inventory.py`/`ticket_types.py` (M10-P02), `qr.py`/`ticket_wallet.py` (M10-P04), payment routers (`payments_card.py`/`payment_status.py`), checkout/cart (M07), `main.py`, schema/db.ts.**

## 4. Implementation spec

- **`purchase.py`:** `add_ticket_to_checkout(...)` → `claim_ticket(...)` (capacity-safe) + `item_kind=ticket` line with 5%/0% commission snapshot. `issue_tickets_for_paid_order(service_client, order_id)` → for each paid ticket item not yet issued, insert `tickets` rows (qty exact); **idempotent** (skip already-issued). Free RSVP: `rsvp(...)` → claim + issue immediately + order record, no payment, 0% commission. **Payment failure → `release_ticket_claim(...)`** voids the claim.
- **`internal_tickets.py`:** `POST /internal/tickets/issue-tick` (internal-token) scans SUCCESS-paid orders with unissued ticket items → `issue_tickets_for_paid_order`. Idempotent batch.
- **`ticket-picker.tsx`:** type/tier selector + qty (respects caps), price via `formatK`, free-RSVP CTA vs pay CTA; 360px; copy via `events.ticketPurchase.*`.

## 5–9. Security etc.

360px; **issued count == paid qty exactly** (idempotent webhook replay → no extra tickets); RSVP capped by capacity; payment failure releases capacity; commission 0% free / 5% paid; owner-scoped; no secrets.

## 10. Tests (RUN before reporting)

`test_ticket_purchase.py`: **failure-release** (payment fail → claimed capacity freed); **RSVP flow** (free → issued immediately, capped, 0% commission); **idempotent issuance on webhook replay** (issue twice → ticket count = paid qty once); **commission snapshot** 0% free / 5% paid. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Payment failure releases claimed capacity; RSVP capped by capacity; issued ticket count = paid qty exactly (idempotent replay); free = 0% commission.
- [ ] Issuance wired via an owned seam (no payment-router edits); `events.ticketPurchase.*` appended (append-rule); customer build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P03 — Purchase & RSVP through checkout
**STATUS/FILES/DEVIATIONS** (how issuance hooks payment success without editing payment routers; the idempotency key; free-RSVP path) **/TESTS** (paste failure-release + RSVP + idempotent-replay + commission + full-pytest tail) **/EXCERPTS** the idempotent `issue_tickets_for_paid_order` + the claim call — nothing else **/QUESTIONS**
