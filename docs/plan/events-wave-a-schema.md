# Events Phase-2 — Wave A (Schema Foundation) — Planning

**Status:** ✅ Decision gate answered 2026-07-15 → locked as **D29** (`00-decisions.md`), amending D2 + §G. Pebble specs below are final; build order in §6. **Mode:** GATED.
**Mountain:** M10 (Events & Ticketing). New pebbles extend the M10 series from **P10**.
**Baseline:** build-out complete; events D1–D3 defects fixed (`events-strategy-remediation.md`). Next free migration: **`0041`**.

## 0. ⚠ Scope-fence collision — this needs a decision, not just a build

Wave A is a **net-new Phase-2 expansion**. Several of its items were **explicitly fenced OUT of v1** by locked decisions:

- **D2** (locked): Events v1 = "fixed + multi-tier + free RSVP pricing only … **No early-bird schedules/group tables/PWYW v1.**"
- **§G scope fence** (locked): OUT of v1 = "early-bird/group/PWYW ticket pricing", "ticket resale marketplace (simple transfer-to-friend allowed)".

The scope fence deferred these **to Phase 2** — which is where we now are. So proceeding is legitimate, but per the operating protocol it must be recorded as a **new locked decision (D29)** that amends D2 + §G, chosen deliberately by the founder. That is the §4 gate. **I will not build a fenced-out feature until D29 locks it in.**

## 1. Current events/ticketing schema (grounded — what exists today)

- **`events`** — `id, organiser_vendor_id→vendors, title, slug (unique), description, venue, lat, lng, images[], status(draft|published|cancelled|completed), category_slug→event_categories, landmark, timestamps`. **No** event_type, visibility/access, recurrence, or policy fields.
- **`event_instances`** — `id, event_id, starts_at, ends_at?(>starts_at), capacity(≥0), timestamps`. No recurrence rule; multi-day already expressible via `ends_at`.
- **`ticket_types`** — `id, event_id, kind(fixed|tier|free_rsvp), name, price_ngwee, qty_cap?, per_customer_cap?`. **`kind='tier'` is an allowed enum value but nothing stores tiers/allocations** — it's an unused seam. Types attach to the **event**, not an instance.
- **`tickets`** — `id, instance_id, ticket_type_id, holder_user_id, order_item_id?, status(issued|checked_in|transferred|void), qr_secret?, pin_hash?, checked_in_at?`. **No `holder_name`/attendee data** — one buyer holds all qty. Server-only writes (guard trigger).
- **`order_item_tickets`** — `order_item_id(PK), ticket_type_id, instance_id`. **1 row per order_item**; quantity lives in `order_items.qty`. This is the only place instance targeting happens.
- **`ticket_transfers`** — transfer-to-friend exists (`0026`): `to_phone`, pending/claimed/cancelled/expired, one-pending guard.
- **`event_categories`** — `slug(PK), parent_slug?(self-ref), label_key, sort`; 6 seeded (`workshops, comedy-theatre, pop-up-dinners, cultural-arts, lifestyle-community, free-rsvp`).
- **Organisers = vendors** (no dedicated table). Identity on `vendors`: `display_name, description, logo_url, slug, preferred_badge, archetype`.
- **Purchase** (`internal_tickets.py` + `services/tickets/purchase.py`): request = `{instance_id, ticket_type_id, qty(1–20)}` only. Price read server-side from `ticket_type.price_ngwee`; **no override**. `free_rsvp`→`/rsvp` (0% commission, immediate issue); paid→`/checkout`. No access code, no per-attendee capture.
- **Escrow** (`escrow/event_release.py`): branch chosen from lead time (`starts_at − order.created_at`); ≤14d full at `settlement_end+24h`, >14d phased 50% at `starts_at−7d` + 50% at `settlement_end+1d`. **Reads only timing + `status='cancelled'` + disputes — no event_type/pricing-mode.**

## 2. Wave A items → concrete schema deltas

| #   | Wave A item                   | Concrete change                                                                                 | Net-new? | Fenced-out?     | Build size         |
| --- | ----------------------------- | ----------------------------------------------------------------------------------------------- | -------- | --------------- | ------------------ |
| a   | `event_type`                  | `events.event_type` enum + drives discovery/escrow/UX per type                                  | yes      | no (classifier) | S–M                |
| b   | privacy/access                | `events.visibility(public\|unlisted\|private)` + `access_code_hash`; discovery + purchase gates | yes      | no              | M                  |
| c   | recurrence                    | `events.recurrence_rule jsonb` + instance-generation helper                                     | yes      | no              | **L** (heaviest)   |
| d   | `holder_name` / attendee data | `tickets.holder_name`(+phone?); capture N attendees at purchase                                 | yes      | no              | S–M                |
| e   | pricing modes                 | early-bird (sale window), group/tier (qty→price), PWYW (min-bound) on `ticket_types`            | yes      | **YES — D2/§G** | **L** (money seam) |
| f   | per-instance tier allocation  | `ticket_type_instances(ticket_type_id, instance_id, allocation, sold)`                          | yes      | no              | M                  |
| g   | event policy fields           | `events.refund_policy_key, age_restriction, terms` additive columns                             | yes      | no              | S                  |

## 3. Provisional pebble decomposition (contingent on §4)

Numbered on the M10 series; migrations from `0041`. **Sequencing is constrained by shared hot files** — the API write path (`organiser_events.py`), the purchase path (`services/tickets/purchase.py`), the discovery reader (`events_public.py`), and `db.ts` are each touched by multiple items, so those items **cannot run in the same parallel wave** (exclusive-file-ownership rule). The realistic shape is a short mostly-sequential chain, not a wide fan-out.

Five pebbles (recurrence dropped per D-A4). The event_type→escrow coupling is **isolated into its own money pebble (P14)** so the foundation pebble stays money-free and the escrow change is small and independently reviewable.

- **M10-P10 — Event classification, visibility & policy (FOUNDATION, sequential; money-free).**
  Migration `0043` (originally planned `0041`; renumbered post-merge to resolve a duplicate-`0041` prefix collision with `0041_product_description` — `0041_product_description` was already applied to staging, so the unapplied events migration moved): `events.event_type` enum (`standard|recurring|free_rsvp|private`), `events.visibility` (`public|unlisted|private`) + `access_code_hash`, policy columns (`refund_policy_key, age_restriction, terms`). New pure module `services/events/type_policy.py` — the single per-type behavior map (default leg = **current escrow timing**, so landing this changes no money behavior). Organiser create/update write the fields; discovery (`events_public.py`) + `search_upsert_event` exclude `unlisted`/`private` from browse/sitemap/index; access-code gate on detail/purchase. Owns: `0041`, `organiser_events.py`, `events_public.py`, `type_policy.py`, `db.ts`(events slice). _Everything else builds on this._
- **M10-P11 — Per-attendee ticket data.**
  Migration `0042`: `tickets.holder_name`, + a `ticket_types.attendee_named` flag. Purchase request captures N attendee names for qty N (required only for named types); issuance writes them; wallet/scanner display them. Owns: `0042`, `internal_tickets.py`(request model), `purchase.py`(attendee capture), wallet/scanner display.
- **M10-P12 — Ticket pricing modes (group/tiered + early-bird). ⚠ MONEY SEAM.**
  Migration `0043`: early-bird `sale_starts_at/sale_ends_at` on `ticket_types`; group tiers via a `ticket_type_price_tiers(ticket_type_id, min_qty, price_ngwee)` table (activates the dormant `kind='tier'`). **Server-side** price resolution in `purchase.py` picks the active window/tier and rejects any client-supplied price. Organiser pricing UI. Owns: `0043`, `ticket_type_price_tiers`, `organiser_events.py`(pricing write), `purchase.py`(price resolution). **Shares `organiser_events.py` (P10) + `purchase.py` (P11) → sequence AFTER both.**
- **M10-P13 — Per-instance tier allocation.**
  Migration `0044`: `ticket_type_instances(ticket_type_id, instance_id, allocation, sold)` + per-(type,instance) capacity checks in inventory. Organiser instance-editor allocation UI. Owns: `0044`, ticket inventory/capacity logic, instance-editor allocation. Disjoint from P11/P12/P14.
- **M10-P14 — event_type-driven escrow timing. ⚠ MONEY SEAM (isolated).**
  `event_release.py` reads `type_policy.py` (from P10) to select per-type release anchors/holds (e.g. `private`/`standard` current timing; `recurring` per-instance; `free_rsvp` n/a). Small, single-file money change; legs stay idempotent/audited/guarded. Owns: `event_release.py` only. **Sequence after P10** (needs `type_policy.py`); disjoint from P11/P12/P13.

**Wave shape (also my build order, Cursor limit reached):** `P10 (foundation)` → then **{P11, P13, P14} parallel** (disjoint files) → `P12` last (shares `organiser_events.py`+`purchase.py` with P10/P11). `db.ts` is converger-reconciled — each pebble supplies its own type slice.

## 4. DECISION GATE — ✅ LOCKED (D29, 2026-07-15)

- **D-A1 — `event_type` = FULL BEHAVIORAL DRIVER** (founder's explicit choice). Enum `standard | recurring | free_rsvp | private`. Type drives **discovery filtering + escrow timing + UX**, not just a label. ⚠ **Money-path coupling** → implemented as one **guarded per-type policy map** (single source of truth read by `event_release.py` + discovery), never scattered conditionals; escrow legs stay idempotent/audited. See §5.1.
- **D-A2 — Pricing modes = group/tiered + early-bird; PWYW deferred** (my rec, founder confirmed). Activates the dormant `kind='tier'` seam + time-gated sale windows. Server-side price resolution within locked bounds only.
- **D-A3 — Attendee data = optional per-ticket `holder_name`, buyer-phone only** (my rec, founder confirmed). Required only when a ticket type is organiser-flagged "named".
- **D-A4 — Recurrence = DEFERRED** (my rec, founder confirmed). Manual multi-instance stays the mechanism; no RRULE build.
- **Lower-leverage (defaulted):** visibility = `public | unlisted | private`(access-code); per-instance allocation = **yes** (`ticket_type_instances`); policy fields = `refund_policy_key + age_restriction + terms`.

## 5. Downstream impact (flag now, detail per-pebble once locked)

- **Escrow** (`event_release.py`) reads no event/pricing fields today — pricing modes don't change release timing, but **PWYW would change refund math** (variable paid amount) → another reason to defer PWYW.
- **Discovery/search** (`events_public.py`, `search_upsert_event`) must exclude `private`/`unlisted` from browse + sitemap + search index — a P10 concern.
- **`order_item_tickets` is 1-row-per-order_item** — per-attendee names (P11) live on `tickets` rows, not this table; per-instance allocation (P13) is a new join table, not a change here.
- **Migrations 0041–0044** are additive + reversible (M03-merged rule); each new table (`ticket_type_price_tiers`, `ticket_type_instances`) needs its RLS-matrix row (the new-table rule) or CI's `test_no_untested_tables` fails.

### 5.1 event_type per-type policy map (the money-path discipline)

Because D-A1 makes `event_type` a **behavioral driver over escrow**, all per-type behavior lives in one module `services/events/type_policy.py` — a pure `event_type → {discovery_visibility_rule, escrow_anchor_rule, ux_flags}` map with an explicit **default = today's timing-based escrow** for any type not overriding it. `event_release.py` (P14) and `events_public.py` (P10) both read this map; nothing branches on `event_type` inline. This keeps the money seam auditable (one place to review), keeps escrow legs idempotent/guarded exactly as the order engine requires, and means P10 can land the column with zero money-behavior change (default policy) before P14 activates per-type timing.

## 6. Status — decisions locked, build ready

D29 is locked; specs above are final. Build order (I implement — Cursor limit reached): **P10 foundation** → **{P11, P13, P14}** → **P12**, one PR per pebble, open-and-merge flow. ⚠ P12 (pricing) and P14 (escrow) are money seams carrying heightened-scrutiny review + failure-path tests.

**Progress:** ✅ **P10** (#211, migration `0043` — renumbered from `0041`), ✅ **P11** (#212, migration `0042`), ✅ **P13** (migration `0048_ticket_type_instances`, allocation cap woven into the oversell-safe claim + organiser allocation API/UI; no denormalised `sold` counter — the claim counts live tickets, drift-free). **Remaining: P14** (escrow timing ⚠money) and **P12** (pricing modes ⚠money, last — shares `organiser_events.py`/`purchase.py`).
