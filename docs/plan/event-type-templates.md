# Event type templates (archetypes) — design

**Status:** spec for the `feat/event-archetype-*` PR series (2026-11-27). Additive. A
published event with no archetype data renders exactly as before (the generic template).

## Goal

A church service, a family fair, a concert, a restaurant pop-up and a brand-sponsored
night should not share one page. Each **event archetype** gets its own page vibe,
layout blocks and organiser form fields, while ticketing (ticket types, holds, dynamic
QR, escrow, fees, refunds) stays the untouched backbone.

## Existing domain (what this builds on)

- `events` (0004 + 0036 `category_slug`/`landmark` + 0043 `visibility`/`age_restriction`
  - Wave A `event_type`, `platform_fee_payer`, `refund_policy_key`, `terms`, `city`),
    `event_instances`, `ticket_types` (`fixed | tier | free_rsvp`, `qty_cap`, `perks`,
    `attendee_named`, early-bird, quantity price tiers), tickets with dynamic QR, escrow
    settlement driven by `event_type` (`services/events/type_policy.py`).
- **`event_type` is a behavioural driver** (visibility default, settlement rule). It is
  **not** the archetype and is never read by the archetype code. Archetype is
  presentation and optional content only: it must never influence money, holds, QR or
  settlement (hard rule A-1 below).
- Categories: hierarchical `event_categories` (11 parents + children, 20261…
  `event_strategy_workflows`): `music{concerts,festivals,gospel}`, `sports{football}`,
  `religious{church}`, `family`, `nightlife{pop-up-dinners}`, `private-events`, etc.
- Customer `/e/[slug]` (hero, about, dates, calendar, venue, ticket picker, organiser),
  `/events` (date chips + category), vendor `EventForm`, ticket tiers page.

## Archetypes and category mapping

The archetype is **derived** from the category (and `event_type = private`) and may be
**overridden** by the organiser. Stored `events.archetype` is NULL while derived; the API
returns the effective value plus `archetype_source = derived | override`.

| Archetype           | Derived from category slug(s)                                                    | Vibe                        |
| ------------------- | -------------------------------------------------------------------------------- | --------------------------- |
| `concert`           | music, concerts, festivals, gospel, nightlife, comedy-theatre(-parent), stand-up | stage lights, high energy   |
| `religious`         | religious, church                                                                | calm, respectful, unhurried |
| `sports_family`     | sports, football, family                                                         | energetic, daytime, playful |
| `restaurant`        | pop-up-dinners                                                                   | warm, tactile, appetising   |
| `private_gathering` | private-events, or `event_type = private`                                        | intimate, personal          |
| `branded`           | **override only** (organiser picks it for a sponsor-led night)                   | brand-forward, bold         |
| `generic`           | everything else (workshops, exhibitions, markets, community, free-rsvp, unknown) | clean, polished fallback    |

`gospel` maps to `concert` (stage + lineup); an organiser can override to `religious`.
`branded` is override-only because "sponsored" is orthogonal to category; the **sponsor
band is available on every archetype** (see blocks), `branded` additionally makes the
sponsor the page's lead.

## Page layout blocks (customer `/e/[slug]`)

Blocks render only when their data exists; a missing block never leaves a hole.
`●` default-on, `○` shown when data present, `–` n/a.

| Block                             |        concert         |     religious     | sports_family  |     restaurant     |         branded         | private | generic |
| --------------------------------- | :--------------------: | :---------------: | :------------: | :----------------: | :---------------------: | :-----: | :-----: |
| Hero / poster (image-first)       | ● poster 4:5 on mobile |         ●         |       ●        |         ●          |            ●            |    ●    |    ●    |
| Facts strip (date, doors, venue)  |           ●            |         ●         |       ●        |         ●          |            ●            |    ●    |    ●    |
| Lineup / stages / slot times      |           ●            |         –         |       –        |         –          |            ○            |    –    |    –    |
| Agenda / order of service         |           –            |         ●         |  ○ activities  |         –          |            ○            |    ○    |    ○    |
| Speakers / hosts                  |           –            |         ○         |       –        |       ○ chef       |            –            |    –    |    –    |
| Activities + age groups           |           –            |         –         |       ●        |         –          |            –            |    –    |    –    |
| Menu sections                     |           –            |         –         |       –        |         ●          |            –            |    –    |    –    |
| Ticket tier cards                 |     ● GA/VIP/VVIP      | ● free / donation | ● age + family | ● set-menu / table |      ● multi-tier       | ○ RSVP  |    ●    |
| Sponsor band                      |           ○            |         ○         |       ○        |         ○          | ● lead ("Presented by") |    –    |    ○    |
| Gallery (images 2..8)             |           ●            |         ○         |       ●        |         ●          |            ●            |    ○    |    ○    |
| Venue and map link                |           ●            |         ●         |       ●        |         ●          |            ●            |    ●    |    ●    |
| Dress code / age policy chips     |           ○            |         ○         |       ○        |         ○          |            ○            |    ○    |    ○    |
| FAQs / policies (+ refund policy) |           ○            |         ○         |       ○        |         ○          |            ○            |    ○    |    ○    |
| Organiser card                    |           ●            |         ●         |       ●        |         ●          |            ●            |    ●    |    ●    |

The existing **TicketPicker, refund policy, calendar links, sticky CTA, countdown and
JSON-LD are reused unchanged**; templates wrap and surround them.

## Visual vibe (all tokenised, no ad-hoc colour)

Each archetype maps to **existing** `packages/ui` tokens only. No new hex, no new CSS
variable. A tint is `color-mix(in srgb, <token> 14%, var(--surface))`.

| Archetype     | Accent / tint token                           | Display type emphasis                            | Imagery guidance                                     |
| ------------- | --------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| concert       | `--accent` on `--panel` (dark hero)           | `font-display`, tight tracking, uppercase kicker | portrait poster + crowd/stage gallery, high contrast |
| religious     | `--cat-health` (sage)                         | `font-display`, relaxed leading, no uppercase    | soft, warm, people and place; avoid busy collages    |
| sports_family | `--cat-fitness` (blue) + `--cat-food` (coral) | large `text-hero`, friendly                      | action and family shots, bright daylight             |
| restaurant    | `--cat-food` (terracotta)                     | `font-display` + serif-feel menu headings        | food close-ups first, then room                      |
| branded       | `--primary` + sponsor logo on `--surface`     | bold display, brand-first                        | brand key visual hero, then product/crowd            |
| private       | `--cat-beauty` (sand)                         | gentle, centred title                            | one hero photo; gallery optional                     |
| generic       | `--primary-tint`                              | current display type                             | one wide hero                                        |

Dark mode, `glass` surfaces (`glassClass`) for overlay chips, 360px-first, hero image
via `CloudinaryImageStatic` (f_auto/q_auto, ≤8 images). Motion stays within the existing
`--dur*`/`--ease-*` tokens. Budget: templates are server components; the only client JS
remains the existing picker/sticky CTA (≤150 kB gz route budget unchanged).

## Ticket presentation patterns (existing ticket-type data only)

No schema change to `ticket_types`. A **tier card** is derived per type from `name`,
`price_ngwee`, `perks` (split into bullet lines, existing `splitTicketPerks`), `qty_cap`
vs `tickets_sold`, early-bird fields, `kind`.

- **Concert tiers (GA / VIP / VVIP):** cards ordered by price ascending; a deterministic
  classifier on the name (`vvip`, `vip`, `ga|general`) adds the badge; highest tier gets
  the accent border; "x left" when under 20% of cap remains.
- **Religious:** `free_rsvp` shows as "Free, no ticket needed to enter" and a donation
  note from `donation_note` (display text only; **no donation payment flow in MVP**).
- **Sports / family fair:** age-group tickets are separate types (e.g. "Child 3–12",
  "Adult"); the classifier recognises `child|kids|family|group`; **family bundles** are a
  ticket type named "Family (2+2)" with `perks`; quantity price breaks (`tiers`) already
  cover "buy 4+". The `age_groups` content block explains who each ticket is for.
- **Restaurant:** set-menu and table tickets are separate types ("Table for 4",
  "5-course set menu"); `seating_note` explains table assignment. **No seat map and no
  table inventory in MVP** (a table is a ticket type with a `qty_cap`).
- **Branded:** several price tiers as concert; promo codes use the **existing** event promo
  mechanism at purchase (no change); the page only shows an optional note (open question 3).

## Archetype-specific optional fields (validated JSON)

One additive column `events.archetype_details jsonb` (object, ≤16 KB), validated in the
API by one Pydantic model per archetype (`extra=forbid`, bounded lists, https-only URLs,
integer ngwee for any price). **Common to all archetypes:** `sponsors[]` (name, logo
Cloudinary id or https, link, tagline; ≤6), `dress_code` (≤80), `age_policy`
(`all_ages | guardian_under_12 | 16_plus | 18_plus`), `faqs[]` (≤8 × question ≤120,
answer ≤500). Per archetype:

- `concert`: `lineup[]` (name, role, stage, slot HH:MM, image, bio ≤200; ≤30), `stages[]`,
  `doors_open`, `merch_note`.
- `religious`: `agenda[]` (HH:MM, title, speaker, notes; ≤30), `speakers[]` (name, role,
  image, bio; ≤12), `denomination`, `donation_note`, `livestream_url`, `languages[]`.
- `sports_family`: `activities[]` (name, age group, time, area; ≤20), `age_groups[]`
  (label, min/max age; ≤8), `bring_list[]`, `family_bundle_note`.
- `restaurant`: `menu_sections[]` (title; items: name, description, `price_ngwee`
  int, dietary tags), `seating_note`, `reservation_note`, `host_name`.
- `branded`: `presented_by` (sponsor), `activations[]` (title, description; ≤8),
  `promo_note` (display text), `giveaway_note`.
- `private_gathering`: `host_names`, `occasion`, `rsvp_note`, `agenda[]` (≤20), `gift_note`.
- `generic`: `agenda[]` (≤20).

Reads **degrade**: if stored JSON fails validation (direct DB edit), the public API
returns `{}` rather than failing the page (same posture as SP-11).

## Discovery

`/events` gains URL-synced filter boxes: **type** (archetype), **date** (existing),
**area** (existing `city`/`neighbourhood`), **price** (`price_max` in ngwee, presets in
K), **free** (`free=1`). The API gains `archetype`, `price_max`, `free` query params.
Pure read filtering.

## Hard rules

- **A-1** Archetype/JSON never touches payments, holds, QR issuance, fees, escrow or refunds.
- **A-2** Migration is additive (two nullable/defaulted columns + checks), reversible.
- **A-3** Every user string is a next-intl key; organiser-entered text is rendered as
  plain text (no HTML), URLs sanitised to `https:`.
- **A-4** No ad-hoc colours; archetype themes only reference existing tokens.

## MVP vs later

**MVP (this series):** archetype column + derivation + override; validated JSON per
archetype; seven customer templates with image hero/gallery, tier cards, sponsor band;
`/events` filters; vendor form adapts per archetype; i18n en/fr/zh (+ bem/nya EN fallback).

**Later:** promo codes for branded events; donation tickets with pay-what-you-want;
table/seat inventory and seat map; lineup artist pages; merch linking to the merch
catalog; livestream embeds; per-archetype OG images; organiser-uploaded sponsor assets
via the asset library; per-type analytics; admin moderation of sponsor content;
sponsor self-serve portal.

## Migration and rollout

One migration `20261127150000_event_archetypes.sql` (`events.archetype`,
`events.archetype_details`, CHECKs, partial index). **Not applied to any database by this
series — King runs `supabase db push`.** The public read path retries without the new
columns if the API ships before the migration (no 500s on event pages).

**Renumbering:** #943 (`20261127090000`), #973 (`20261127100000`), #944
(`20261127120000`) land first. This migration is timestamped after them, so the file name
does not change; only the **inventory counts** need +3 on rebase (199 → 200 here; 203
after the three land): `ci.yml` `EXPECTED_TYPEGEN_MIGRATION_COUNT`, `typegen_artifact.py`
`MIGRATION_COUNT`, `run_coordinator_gates.py`, `coordinator-gate-inputs.json`,
`rehearse_explicit_transaction_profile.py`, `run_financial_real_stack.py` (`FORWARD`),
tests under `scripts/ci/` and `services/api/tests/`.

## Open questions for the founder

1. Is `gospel` a concert or a religious event by default? (Spec: concert, overridable.)
2. Should `branded` be a page type at all, or only a sponsor band on any archetype?
3. Promo codes: event ticketing already has promo-code discounts (`services/events/promo.py`, resolved at purchase). Branded events reuse them unchanged; this series only adds a display `promo_note`. Is that enough, or should the organiser UI surface promo management on the branded form?
4. Donation tickets: display-only note now, or build pay-what-you-want (a payment change)?
5. Restaurant "table bookings": is a ticket type with a cap per table size enough, or do
   you need real table/seat selection?
6. Sponsor content approval: may organisers self-publish sponsor logos/links, or must
   admin approve first?
7. Chinese (`zh`) and French copy are machine-assisted; who signs off? Bemba/Nyanja
   stay on English fallback until native review.
8. Should `/events` default to "all dates" when a type filter is chosen (today the default
   window is "tonight")?
