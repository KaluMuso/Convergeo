# Events Phase-2 — Wave A: schema foundation (plan)

**Status:** planning · **Opened:** 2026-07-15 (#209, locks **D29**) · **Author track:** Claude implements
(Cursor credits exhausted), one PR per pebble, open-and-merge.

**Governing decision:** `docs/plan/00-decisions.md` **D29** (amends D2 + §G). This note is the grounded
schema map + pebble decomposition D29 points to. It supersedes nothing in D29 — where this note and
D29 differ, D29 wins.

> **⚠ One founder decision is still open before P10 migration code lands — the `event_type`
> taxonomy itself (see §4). Everything else in Wave A is fully specified by D29.**

---

## 1. Scope (from D29)

**IN (Wave A):**

- `events.event_type` — a **behavioral driver** (not a label), consumed by a single guarded **policy
  map** across discovery filtering, escrow timing, and UX.
- `events.visibility` = `public | unlisted | private` (+ access code for `private`).
- Pricing modes: **group/tiered** (activate the dormant `ticket_types.kind='tier'` seam) **+
  early-bird** time-gated windows. Prices resolved server-side within locked bounds.
- `tickets.holder_name` — optional per-attendee name, required only when a ticket type is flagged
  `named`. Buyer phone only; **no per-attendee phone**.
- Per-instance tier allocation (`ticket_type_instances` join) for real multi-night events.
- Event policy fields: `refund_policy_key`, `age_restriction`, `terms` (additive, no launch-behavior
  change).

**OUT (unchanged — do not build):** PWYW pricing, true recurrence/RRULE, ticket resale marketplace
(transfer-to-friend stays the only secondary path), booking calendars.

---

## 2. Current schema baseline (grounded on `master`)

Verified against `0004_services_events.sql` + `0035_event_instance_ends_at` + `0036_event_categories`

- `0039_event_search_category_path`.

| Table             | Columns today                                                                                                                                                                 | Wave-A gap                                                                            |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `events`          | `id, organiser_vendor_id, title, slug, description, venue, lat, lng, images, status(draft/published/cancelled/completed), created_at, updated_at` (+ `category_id` from 0036) | no `event_type`, no `visibility`/access code, no policy fields                        |
| `event_instances` | `id, event_id, starts_at, ends_at (0035), capacity, created_at, updated_at`                                                                                                   | no per-instance tier allocation                                                       |
| `ticket_types`    | `id, event_id, kind('fixed'\|'tier'\|'free_rsvp'), name, price_ngwee, qty_cap, created_at, updated_at`; CHECK: free_rsvp⇒price 0, else price>0                                | `kind='tier'` **dormant** (no tier rows table); no early-bird window; no `named` flag |
| `tickets`         | `id, instance_id, ticket_type_id, holder_user_id, order_item_id, status(issued/checked_in/transferred/void), qr_secret, pin_hash, checked_in_at, …`                           | no `holder_name`                                                                      |

**Existing escrow-timing behavior** (the money path `event_type` must plug into, not replace):
`event_release.py` releases event escrow on a **date-anchored** schedule — ≤14 days out ⇒ full at
event +24h; >14 days ⇒ 50% at event −7d + 50% at event +1d — under distinct idempotency keys
(`event-release-{order_id}-full|phase1|phase2`), never colliding with the order engine's
`release-{order_id}`. Wave A makes this schedule **also** a function of `event_type` via the policy
map (P14), keeping every leg idempotent/guarded/audited.

---

## 3. The per-type policy map (architectural crux of D29)

D29 requires event_type behavior to live in **one source of truth**, never scattered
`if event_type == …` branches. Design:

- **DB:** `events.event_type text not null default '<base>' check (event_type in (…))` — the enum is
  CHECK-constrained (additive; a later type is an additive CHECK widen, reversible).
- **App:** a single module `services/api/app/services/events/policy.py` exposing an immutable
  `EVENT_TYPE_POLICY: dict[EventType, EventTypePolicy]`. Each `EventTypePolicy` (frozen dataclass)
  declares the per-type behavior in three buckets:
  - **discovery** — browsable? default `visibility`? category/ranking hints.
  - **escrow** — which release schedule the policy selects (consumed by `event_release.py`; **P14**).
  - **ux** — organiser-form + attendee-page flags (named-tickets default, multi-instance affordance).
- **Consumers** import the map, never hard-code a type. A unit test asserts **every** enum value has a
  policy entry (no silent gap) and that `event_release.py` + the discovery filter both resolve their
  behavior through the map.

This keeps the money-touching coupling auditable: escrow timing per type is a data row reviewed once,
not logic spread across the codebase.

---

## 4. ⚠ Open founder decision — the `event_type` enum

D29 locked that event_type is a **full behavioral driver** (the founder's explicit choice over a
minimal classifier), but the **enum values themselves are not yet pinned**. Because the value set
feeds a CHECK constraint **and** the escrow policy map, it should be confirmed before P10's migration.

The remediation-doc hint (`single/multi-day/recurring/free/private`) conflates axes that D29 has since
split out: **visibility** (`public/unlisted/private`) is its own column, **free** is
`ticket_types.kind='free_rsvp'` (pricing), and **recurrence** is deferred. What remains for
`event_type` is the event's **format/nature** that meaningfully changes escrow risk, discovery, and UX.

**Proposed taxonomy (recommended default — pending founder confirm):**

| `event_type` | Meaning                                        | Escrow lean (P14)                       | Discovery / UX                            |
| ------------ | ---------------------------------------------- | --------------------------------------- | ----------------------------------------- |
| `single`     | One-session event (default)                    | date-anchored (current behavior)        | standard browse                           |
| `multi_day`  | Multi-instance run (festival, conference)      | phased (per-instance / 50-50)           | multi-instance picker; per-instance tiers |
| `experience` | Small capped experience (pop-up dinner, class) | conservative full-after-completion hold | `named` tickets default on                |
| `free`       | Free/RSVP-only (no paid tickets)               | **no escrow** (no money leg)            | RSVP CTA, no checkout                     |

This is a **starting proposal**, not a lock. The single question for the founder: **confirm this
4-value set (and defaults), or amend it.** Once confirmed it goes into D29's detail and P10 proceeds.
(P10 is otherwise fully specified; only the enum literal set is blocked.)

---

## 5. Pebble decomposition (M10-P10 … P14)

Sequencing (from `00-status.md`): **P10 first** (money-free foundation); then P11, P13, P14 depend on
P10; **P12 last**. P12 + P14 touch money ⇒ heightened-scrutiny review.

| Pebble      | Scope                                                                                                                                                                                                                                                                                                                                                                                                          | Migration                                                 | Money   | Depends                           |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------- | --------------------------------- |
| **M10-P10** | Classification + visibility + policy foundation: `events.event_type` (CHECK), `events.visibility` + access-code column, policy fields (`refund_policy_key`, `age_restriction`, `terms`); the `policy.py` map + coverage test; discovery filter honours `visibility` (unlisted hidden from browse, private requires code); organiser form + JSON-LD/indexability reflect visibility. **No money path touched.** | `0041`                                                    | no      | —                                 |
| **M10-P11** | Attendee data: `tickets.holder_name` (nullable) + `ticket_types.named` flag; capture `holder_name` at purchase, required iff the type is `named`; render on wallet/scanner.                                                                                                                                                                                                                                    | `0042`                                                    | no      | P10                               |
| **M10-P13** | Per-instance tier allocation: `ticket_type_instances` join (which tier sells at which instance, per-instance `qty_cap`); inventory + issuance read it; RLS-matrix row.                                                                                                                                                                                                                                         | `0043`                                                    | no*     | P10                               |
| **M10-P14** | `event_type` → escrow timing: wire the policy map's `escrow` bucket into `event_release.py` schedule selection; keep idempotency keys + guards + audit unchanged; free-type events post no escrow leg. **⚠ money — heightened review.**                                                                                                                                                                        | (code; no new table unless a policy config row is stored) | **yes** | P10                               |
| **M10-P12** | Pricing modes: activate `kind='tier'` (qty→price tier rows) + early-bird time-gated windows; server-side price resolution within locked bounds, no client price trusted; refund/escrow math uses resolved price. **⚠ money — heightened review.**                                                                                                                                                              | `0044`                                                    | **yes** | P10, (P13 for per-instance tiers) |

\* P13 is inventory-structural; it does not itself move money but underlies P12/P14 correctness, so
its issuance-count changes get a careful (non-money) review.

**Migration numbering:** next free slot is `0041` (master tops out at `0040_listing_below_median`).
Assign `0041→P10, 0042→P11, 0043→P13, 0044→P12`; P14 is code-only unless review prefers a stored
policy table. If master advances and claims a slot before a pebble merges, renumber to the next free
slot at merge (the recurring cross-PR hazard — see `product-strategy-gap-audit` history).

**Every new table (`ticket_type_instances`, any tier table) carries its `tests/rls/test_matrix.py`
row** (D29 + the standing "no untested tables" rule), and DB-backed tests wire into the CI `rls`
curated blocking step (the M10-FIX pattern).

---

## 6. Guardrails carried into every Wave-A pebble

1. **Money (P12/P14):** integer ngwee only; escrow legs stay idempotent + guarded + audited; prices
   resolved server-side within locked bounds; failure-path tests required.
2. **Migrations:** additive/reversible after M03; new tables get RLS + an RLS-matrix row; the enum is a
   CHECK (a later value = additive widen).
3. **i18n:** no hardcoded strings — new organiser/attendee copy via next-intl keys.
4. **State machines:** ticket/event status transitions stay guarded (no raw status UPDATE).
5. **Policy map is the only home for per-type behavior** — a coverage test forbids scattered branches
   and asserts every enum value has an entry.

---

## 7. Immediate next action

P10 is ready to implement **except** the §4 enum confirmation. Recommended: founder confirms (or
amends) the 4-value `event_type` set, then P10 ships as one PR (`0041` + `policy.py` + visibility
discovery filter + tests), open-and-merge, followed by P11/P13 → P14 → P12.
