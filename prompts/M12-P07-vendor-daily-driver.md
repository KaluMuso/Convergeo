> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M12-P07 — Orders queue daily-driver

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **Vendor order actions merged (M09-P02, W10):** `vendor_orders.py` (confirm/reject/pack/ship/ready via `transition_order`) + `apps/vendor/app/[locale]/orders/[id]/page.tsx` + `orders/_components/action-bar.tsx`. **Reuse the M09-P02 action endpoints** — your card actions call them; full M09-P02 semantics (state-gated + ownership + outbox). Do NOT re-implement actions.
- Vendor app `localePrefix:"always"`. **Vendor home `apps/vendor/app/[locale]/page.tsx` EXISTS** (M01-P04 shell) — you **turn it into the daily-driver home** (today's takings + needs-action + big buttons). You create the **queue list** `orders/page.tsx` + `orders/_components/order-card.tsx`. **M09-P02 owns `orders/[id]/` + `orders/_components/action-bar.tsx` — do NOT touch those; your `order-card.tsx` is a distinct file in the shared `_components/` dir.**
- **Takings = today's CONFIRMED revenue, TZ Africa/Lusaka** (compute the day window in Lusaka; sum confirmed orders' totals; `formatK`). Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`) — or reuse an existing vendor-orders read endpoint. i18n `vendor` namespace registered; **`vendor.json` — you solely own it this wave** (append a nested `home`/`queue` section; do NOT reformat `orders`/`onboarding`/`listings`/`profile` siblings).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P07. **Payouts view = M12-P08 (not this wave).**

## 2. Objective & scope

The screen a vendor lives in: home = **today's takings (formatK, Lusaka TZ) + needs-action list (sorted by urgency) + big buttons**; an orders queue with status filters; `order-card.tsx` with thumb-sized one-tap actions (Confirm/Pack/Ship/Ready) wired to M09-P02, confirm sheets, pull-to-refresh, offline-tolerant read cache. **Usable one-handed at 360px.**
**Non-goals:** no order detail (M09-P02 owns `[id]/`), no action logic (M09-P02 — call), no payouts (M12-P08), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/orders/page.tsx` (queue + filters) · `apps/vendor/app/[locale]/orders/_components/order-card.tsx` (thumb actions)
- **Modify:** `apps/vendor/app/[locale]/page.tsx` (M01-P04 shell → daily-driver home: takings + needs-action + big buttons) · `packages/i18n/messages/en/vendor.json` (append nested `home`/`queue` section)
  **Guardrail: nothing else. Do NOT touch `orders/[id]/page.tsx` or `_components/action-bar.tsx` (M09-P02), `vendor_orders.py` (call it), `main.py`, schema, other namespaces.**

## 4. Implementation spec

- **Home (`[locale]/page.tsx`):** **today's takings** = sum of today's **confirmed** orders' totals in **Africa/Lusaka** TZ (integer ngwee, `formatK`); **needs-action list** sorted by urgency (new orders needing confirm first, by SLA); **big buttons** to the queue/actions. Offline-tolerant read cache; empty state.
- **Queue (`orders/page.tsx`):** list with status filters; each row = `order-card.tsx`. **`order-card.tsx`:** thumb-sized one-tap actions (Confirm/Pack/Ship/Ready) → M09-P02 endpoints with a confirm sheet; pull-to-refresh. Actions from the card = **full M09-P02 semantics** (state-gated, ownership, outbox). All copy via `vendor` (`home.*`/`queue.*`); **360px one-handed**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px one-handed (thumb-reach actions); takings TZ-correct (Lusaka); vendor-scoped via M09-P02; offline-tolerant read; no secrets.

## 10. Tests (RUN before reporting)

Component/API: **takings aggregation** (TZ boundaries — an order at 23:30 Lusaka counts today, not tomorrow UTC; only confirmed counted); **needs-action ordering** (new/confirm-SLA first); **action wiring** (card action → M09-P02 semantics); empty states. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`** (confirm green if you add/reuse an aggregation endpoint).

## 11. Acceptance criteria / DoD

- [ ] Usable one-handed at 360px; takings = today's confirmed revenue exactly (Lusaka TZ); card action = full M09-P02 semantics.
- [ ] Needs-action urgency-sorted; queue filters work; `vendor.home.*`/`queue.*` nested (sole owner); repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M12-P07 — Orders queue daily-driver
**STATUS/FILES/DEVIATIONS** (note how takings are aggregated + TZ handling) **/TESTS** (paste takings-TZ + needs-action-order + build) **/EXCERPTS** the Lusaka-TZ takings aggregation — nothing else **/QUESTIONS**
