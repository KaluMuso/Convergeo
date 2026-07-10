> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0020` (ticket per-customer cap) this wave.** **Run the FULL `uv run pytest` before reporting.**

# M10-P02 — Ticket types & oversell-safe inventory

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **`ticket_types` EXISTS (0004_services_events.sql:127):** `event_id`, **`kind text check ('fixed','tier','free_rsvp')`**, `name`, **`price_ngwee bigint >= 0`**, `qty_cap int (>0 or null)`, plus the **free_rsvp price constraint** (`kind='free_rsvp' ⇒ price=0`, else `price>0`). Organiser RLS present (0004:664+). **Types are per-EVENT; capacity is per-INSTANCE.**
- **`event_instances` (0004:109):** `capacity int >= 0` (per-instance cap). **`tickets` (0004:149):** `instance_id`, `ticket_type_id`, `holder_user_id`, `status ('issued','checked_in','transferred','void')`, indexed `(instance_id, status)` — **inventory is derived by counting non-void issued tickets per instance/type.** Guard trigger makes ticket status/secrets server-controlled.
- **Missing: per-customer purchase cap** → **migration `0020_ticket_type_per_customer_cap.sql`**: additive `alter table public.ticket_types add column per_customer_cap int check (per_customer_cap is null or per_customer_cap > 0);` (nullable = unlimited). Additive-safe.
- **⚙ Atomic claim = the M07-P02 reservation pattern** (merged): claim under row lock / conditional insert so **no oversell at the capacity boundary under concurrency** (`SELECT … FOR UPDATE` on the instance + count check, or an atomic conditional insert). Enforce BOTH per-instance `capacity` AND per-type `qty_cap` AND `per_customer_cap`.
- **⚙ Depends on M10-P01 (parallel):** events/instances are created by the organiser CRUD (P01). You operate on **existing `event_id`/`instance_id`** via the merged schema — **no code import from P01.** Your ticket-config UI lives under `events/[id]/tickets/` which **P01 does not create** (disjoint).
- **This pebble = type config + inventory claim primitive.** Actual purchase/checkout wiring is **M10-P03 (W14)** — expose the claim function + type CRUD; do not build the buy flow.
- **i18n:** ticket-config UI strings → `vendor.json` (`vendor.tickets.*`, append-rule).
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P02. **Money = integer ngwee; free type = 0 (not null).**

## 2. Objective & scope

Ticket **type config** (fixed / multi-tier / free RSVP; per-type `qty_cap`; per-instance `capacity`; optional `per_customer_cap`) + an **oversell-safe atomic claim** primitive (no double-allocation at the boundary under concurrency). Vendor type-config UI.
**Non-goals:** no purchase/checkout/payment (M10-P03, W14), no wallet/QR (M10-P04), no event CRUD (M10-P01), no public event pages.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/tickets/inventory.py` (atomic claim per instance+type: capacity + qty_cap + per_customer_cap; returns claim or oversell error) · `services/api/app/routers/ticket_types.py` (organiser type CRUD, ownership-gated) · `apps/vendor/app/[locale]/events/[id]/tickets/page.tsx` (+ `_components/` — type config UI) · `supabase/migrations/0020_ticket_type_per_customer_cap.sql` · `services/api/tests/test_ticket_inventory.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/vendor.json` (append `vendor.tickets.*`)
  **Guardrail: nothing else. Do NOT touch `organiser_events.py` or `events/{page,new,[id]/edit}` (M10-P01), `tickets` table guard trigger, `main.py`, other schema/db.ts beyond `0020`.**

## 4. Implementation spec

- **`inventory.py`:** `claim_ticket(service_client, *, instance_id, ticket_type_id, holder_user_id, qty=1)` — under a lock/atomic conditional: verify `issued_count(instance) + qty ≤ capacity` AND `issued_count(type) + qty ≤ qty_cap` (if set) AND `holder_issued(type) + qty ≤ per_customer_cap` (if set); insert `tickets` rows `status='issued'` (secrets left server-controlled per the guard trigger); else uniform-envelope oversell/cap error. **Concurrency-safe: capacity-1 with two simultaneous claims → exactly one succeeds.**
- **`ticket_types.py`** (auth, organiser-owned, uniform envelope): CRUD types (validate `kind`/price constraint mirror — free_rsvp ⇒ 0; fixed/tier ⇒ >0; tier config validation); set `qty_cap`/`per_customer_cap`. Ownership via the event's organiser vendor.
- **`0020` migration:** additive nullable `per_customer_cap` column + check; reversible header.
- **UI:** type config (add/edit types, tier list, caps), 360px, ngwee entry via `formatK` display. Copy via `vendor.tickets.*`.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; **race test: capacity-1, two concurrent buyers → exactly one ticket**; tier prices ngwee (**no float**); free type = 0 (not null); per-customer cap enforced; organiser-owned (cross-vendor rejected); no secrets.

## 10. Tests (RUN before reporting)

`test_ticket_inventory.py`: **concurrency at capacity boundary** (simulate two simultaneous claims at capacity-1 → one success, one oversell error); **qty_cap boundary**; **per_customer_cap** (same holder over cap → rejected); **tier config validation** (free_rsvp price must be 0; fixed/tier >0); organiser authz (cross-vendor type CRUD rejected); `0020` replay note. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Race: capacity-1 with two concurrent buyers → exactly one ticket; tier prices ngwee; free type = 0 (not null); per_customer_cap enforced.
- [ ] `0020` adds `per_customer_cap` (additive, nullable); `vendor.tickets.*` appended (append-rule); vendor build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P02 — Ticket types & oversell-safe inventory
**STATUS/FILES/DEVIATIONS** (describe the atomic-claim mechanism used + how it mirrors M07-P02 + the `0020` column) **/TESTS** (paste concurrency-boundary + qty_cap + per_customer_cap + tier-config-validation + full-pytest tail) **/EXCERPTS** the atomic `claim_ticket` core — nothing else **/QUESTIONS**
