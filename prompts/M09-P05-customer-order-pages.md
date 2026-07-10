> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M09-P05 — Customer order pages

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **Reads only:** `orders` + `order_events` (0005 — the timeline source; `transition_order` writes them), grouped by `checkout_group_id`; invoices/receipts from M08-P12 (same wave — **link/stub until the PDF lands in M15-P07**). Pickup QR/PIN display reads the M09-P03 pickup fields (same wave — **stub if unmerged**; show only for `ready` pickup orders, only to the owner). `account/` shell exists (M04-P05).
- **NEW i18n namespace `orders`** — create `packages/i18n/messages/en/orders.json` AND **register it in `packages/i18n/src/request.ts` `NAMESPACES`** (the `messages.test.ts` completeness test asserts files == NAMESPACES). **You are the SOLE `request.ts` editor this wave.** Nest keys (next-intl nests on dots).
- Customer app `localePrefix:"always"` → pages under **`apps/customer/app/[locale]/account/orders/`**. Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Timeline maps state-machine states → customer-friendly steps with **escrow trust copy** ("Held by Vergeo5 → Released").
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P05.

## 2. Objective & scope

Customer order list + detail (timeline from state-machine/audit events with escrow trust copy; **pickup QR/PIN shown only for ready-pickup orders, only to the owner**; receipt/invoice download link — stubbed until M15-P07; per-vendor sub-orders grouped under the checkout group) + the read API.
**Non-goals:** no confirm-received/report-problem (M09-P06), no invoice PDF (M15-P07 — link stub), no vendor pages (M12-P07), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/account/orders/page.tsx` (list) · `account/orders/[id]/page.tsx` (timeline detail + QR/PIN + invoice link) (+ `_components/*`) · `services/api/app/routers/customer_orders.py` · `packages/i18n/messages/en/orders.json` · `services/api/tests/test_customer_orders.py`
- **Modify:** `packages/i18n/src/request.ts` (add `"orders"` to `NAMESPACES` — sole editor this wave)
  **Guardrail: nothing else. Do NOT touch other namespaces/JSON, `orders/state.py`, `customer/*` unrelated routes, `main.py`, schema.**

## 4. Implementation spec

- **`customer_orders.py`** (auth required, **owner-scoped**): `GET /account/orders` (own orders, grouped by checkout group) + `GET /account/orders/{id}` (detail + `order_events` timeline). **Another customer's order → 404** (not 403 — don't leak existence). COD vs prepaid copy differs.
- **Pages:** list grouped by checkout group (per-vendor sub-orders); detail = a **timeline** mapping every state (incl. cancelled/refunded) to friendly steps + escrow trust copy; **QR/PIN block only for `ready` pickup orders owned by the viewer** (from M09-P03 fields — stub gracefully if unmerged); **invoice/receipt download link** (from M08-P12 data — stub link until M15-P07 PDF). All copy via the new `orders` namespace; 360px-first.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; owner-scoped (other customer → 404); QR/PIN visible only to owner on ready-pickup; escrow trust copy; account routes noindex; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_customer_orders.py`: **timeline mapping per state fixture** (placed…completed + cancelled/refunded → correct friendly steps); **authz** (other customer → 404); **COD vs prepaid** copy differences; QR/PIN only on ready-pickup + owner. i18n completeness `orders.*` (nested; NAMESPACES updated). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite.**

## 11. Acceptance criteria / DoD

- [ ] Timeline accurate for every state incl. cancelled/refunded; QR/PIN only for ready-pickup owner; sub-orders grouped by checkout group.
- [ ] Other customer → 404; `orders` namespace registered in `request.ts` + `orders.json` nested; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P05 — Customer order pages
**STATUS/FILES/DEVIATIONS** (note QR/PIN + invoice-link stub state) **/TESTS** (paste timeline-mapping + authz-404 + full-pytest tail) **/EXCERPTS** (none) **/QUESTIONS**
