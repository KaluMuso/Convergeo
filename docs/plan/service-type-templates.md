# Service type templates (archetypes) — design

**Status:** spec for review (2026-11-27). Builds ON TOP of the open package list
(`docs/plan/service-packages.md`, PR #944). Phase B MVP is split into three PRs: data/API,
customer UI, vendor UI (stacked on #944).

## 1. Problem

Every service page is the same page: a big empty right half when there is no photo, one
"Basic" package card, "From K5". A lodge, a gym, a barber and a maid are very different
products, but the page treats all of them as a generic "job + quote". The listing page has
plain filters. We want each kind of service to look and read like what it is, while every
one still ends in the same action: **book, make an appointment, or request a quote**.

## 2. Principles

1. **Archetype, not vertical, drives the template.** A vertical is a browse category; an
   archetype is how the service is offered and booked. Many verticals share one archetype,
   so we ship 7 templates, not 15.
2. **Packages become "offers".** The #944 `service_packages` row is the offer. It keeps its
   universal fields (name, description, `price_ngwee`, `delivery_days`, `includes`,
   `sort_order`, status, cap 10) and gains one validated `attributes` JSON object whose
   shape depends on the service's archetype. No new offer table.
3. **Request-first (SP-1 stands).** Choosing an offer never takes payment. The booking panel
   builds a structured request (offer + dates/time/party size) and sends it through the
   existing `POST /rfq` with `package_id`. The vendor confirms or quotes. No calendars, no
   inventory locks, no payments in this phase.
4. **Honest data.** Capacity and availability shown to customers are vendor-declared hints,
   never promises. Copy says "request", not "reserved".
5. **Cheap bytes.** Templates are server components with one small client island (the
   request panel). No new dependency. Images through Cloudinary `f_auto/q_auto`.
   Customer route budget stays under 150 kB gz.
6. **Fallback is a feature.** Any archetype without a bespoke layout, and any service whose
   attributes fail validation, renders the polished generic layout. A bad JSON blob can
   never take a page down (same rule as SP-11).

## 3. Archetypes

| Archetype      | Verticals (existing, **new**)                          | Offer unit              | Booking primitive (request)              |
| -------------- | ------------------------------------------------------ | ----------------------- | ---------------------------------------- |
| `accommodation`| **lodging** (hotel, lodge, guesthouse), **property**   | room type / unit        | date range + room + guests (+ viewing for property) |
| `appointment`  | beauty, tailoring, auto                                | treatment / fitting / slot service | day + time slot + stylist preference |
| `membership`   | **fitness** (gym, studio, classes)                     | pass / membership       | start date + pass (recurring)            |
| `on_site`      | cleaning, home-services                                | hourly or per-visit job | date + time window + home size           |
| `rental`       | **rentals** (equipment, vehicles, party items)         | item                    | pickup date + period (hours/days) + qty  |
| `ticketed`     | **family-fun** (play parks, farms, attractions)        | ticket by audience      | visit date + timed entry + party mix     |
| `professional` | tech-services, printing-creative, food-catering, **staffing** (hiring) | package / role / rate | brief + deadline (classic RFQ)           |

Mapping is a pure function (`vertical -> archetype`) with a stored override
(`services.archetype`, nullable). Null means derived. `services.archetype` is **not**
`vendors.archetype` (the seller business type chosen at onboarding); the two are unrelated.

Unknown or null vertical resolves to `professional`, which is today's behaviour.

### 3.1 Per-archetype definition

Common to all: gallery (`portfolio_images`, cap 8, hero + thumbs), offer cards, request
panel, "about", provider card, reviews. Optional service-level attributes common to all:
`amenities` (<=12 short tags), `availability` (`available | limited | unavailable`),
`hours` (<=7 day rows), `policy` (cancellation `flexible | moderate | strict`, note <=200).

**accommodation** (rooms)
- Offer attributes: `room_type` (`standard | premium | presidential | family | dorm |
  other`), `sleeps` 1-20, `beds` 1-10 + `bed_type`, `size_sqm`, `amenities` (<=10 tags),
  `breakfast_included`, `min_nights` 1-30, `stay_kind` (`nightly | monthly`; monthly is the
  housing/"homing" listing, price = per month), `units_available` (hint).
- Price meaning: per night (or per month). `delivery_days` is unused (hidden).
- Capacity: `sleeps` per unit; `units_available` informs "only N left" copy (hint).
- Layout: wide hero + thumbnail strip, room cards (photo, beds, sleeps, amenity icons,
  price/night), check-in/out + policy strip, amenities grid, panel with check-in/out,
  guests, offer select. Vibe: **teal/blue** (calm, travel).
- Service attrs: `check_in`, `check_out` (HH:MM), `star_class` optional later.

**appointment** (salon/barber/tailor/garage)
- Offer attributes: `duration_min` 5-480 (step 5), `group` (menu section label <=30, e.g.
  "Hair", "Nails"), `staff` (<=6 names allowed to perform it, optional), `home_visit`,
  `price_is_from`.
- Capacity: one client per slot; the staff list is a preference, not a calendar.
- Layout: treatment **menu** grouped by `group`, each row with duration chip and price,
  stylist chips, panel with day + time-of-day preference (morning/afternoon/evening or
  free HH:MM) + stylist. Vibe: **pink/purple** (salon energy).
- Service attrs: `staff` roster (<=10 `{name, role}`), `walk_ins`.

**membership** (gym/studio)
- Offer attributes: `pass_kind` (`day | week | month | quarter | year | class_pack`),
  `valid_days` 1-730, `visits_included` (null = unlimited) 1-1000, `classes_included`,
  `guest_passes` 0-10, `peak_hours_only`.
- Capacity: gyms have high capacity; we show nothing per pass. Classes carry their own
  `capacity` in the schedule.
- Layout: pass cards (highlight best value = lowest cost per day), weekly class schedule
  (day tabs, <=21 entries), facilities, panel with start date + pass. Vibe: **orange/red**
  (energy).
- Service attrs: `class_schedule` (<=21 `{day 0-6, start, title, duration_min,
  capacity?}`).

**on_site** (maid, cleaning, handyman)
- Offer attributes: `pricing_unit` (`hour | visit | room`), `min_hours` 1-12, `home_size`
  (`studio | one_two_bed | three_bed | four_plus`), `crew_size` 1-10, `supplies_included`.
- Layout: "how big is your home" picker mapped to offers, what's included checklist, trust
  strip, panel with date + arrival window (morning/midday/afternoon) + home size +
  address area. Vibe: **green/cyan** (fresh).

**rental** (equipment, vehicles)
- Offer attributes: `unit` (`hour | day | week`), `deposit_ngwee` (integer ngwee, informational,
  collected by the vendor, **not** by Vergeo5), `quantity_available` 1-500 (hint),
  `specs` (<=8 `{label, value}`), `with_operator`, `delivery_available`, `min_period` 1-30.
- Layout: item cards with spec chips and "deposit K..." line, pickup/return note, panel with
  start date + period + quantity. Vibe: **amber** (utility).

**ticketed** (family fun)
- Offer attributes: `ticket_kind` (`adult | child | toddler | senior | family | group`),
  `age_min`, `age_max` (0-120), `party_size` (family/group bundle size 1-20),
  `entry` (`any_time | timed`), `slot_capacity` (hint).
- Layout: colourful ticket-stub cards by audience, opening hours, facilities/rules,
  panel with visit date + entry time + counts per ticket kind. Vibe: **yellow/orange/pink**
  (playful).
- Service attrs: `age_policy` note.

**professional** (default)
- Offer attributes (all optional): `rate_unit` (`hour | day | month | project`), `role`
  (<=40, for staffing), `experience_years` 0-50, `availability` (`now | week | booked`),
  `certifications` (<=5 short strings).
- Layout: today's package comparison with clean cards, portfolio gallery, brief-based
  request. Vibe: neutral **primary**.

## 4. Data model (Phase B1, one additive migration)

- `services.archetype text null` with CHECK on the 7 values (null = derived).
- `services.attributes jsonb not null default '{}'` with `octet_length(attributes::text) <= 8000`.
- `service_packages.attributes jsonb not null default '{}'` with the same size cap.
- Gallery: reuse `portfolio_images` (no change). Offer photo is `attributes.image`
  (Cloudinary public id) in every archetype.
- Verticals are free text in the DB; new verticals are added in the API Literal, the
  customer/vendor lists and i18n only.
- Reversible: `alter table ... drop column` for each column (documented in the migration).
- **Validation lives in Pydantic**: one strict model per archetype for offers
  (`OfferAttrs`) and for services (`ServiceAttrs`), `extra="forbid"`, ints for money, size
  and count caps. The API validates on write and returns a typed error code; on read the API
  runs a tolerant parse and returns `{}` for a row that no longer validates, so old/broken
  rows degrade to the generic layout. Offers keep the screen: attribute strings run
  through the prohibited-content screen with the package copy (SP-9).
- Migration order: **#943, #973 and #944 land first.** Their migrations are
  `20261127100000_vendor_sourcing_hub` (#973), `20261127120000_service_packages_open_list`
  (#944) and #943's own. This migration is `20261128090000_service_archetypes.sql`; if it is
  not strictly the latest after those land, **renumber** it above master's max and update
  every inventory (the 11 files PR #929 touched: ci.yml `EXPECTED_TYPEGEN_MIGRATION_COUNT`,
  `.gitleaks.toml`, coordinator inputs + runners + tests, typegen, reconcile and schema
  convergence tests). Not applied to any database in this phase.

## 5. Customer experience

**Detail page (`/s/[slug]`).** `resolveTemplate(archetype)` picks a layout component:
accommodation, appointment, membership, rental in B2; on_site, ticketed and professional
use the polished generic layout (generic = today's page, with the empty-hero bug fixed:
a tinted gradient hero with the archetype icon and vibe colour when there is no image, and a
photo mosaic when there are several). Shared building blocks live next to the page:
`ServiceHero` (gallery), `OfferCards` (per-archetype row renderers), `RequestPanel`
(client island), `PolicyStrip`, `AmenityGrid`.

**Request panel.** Desktop: sticky right column. Mobile: a bottom bar opening a sheet (glass
`bar-bottom` surface from `packages/ui`). It collects the archetype's booking fields
(dates, time, party size), validates them locally, and composes the `requested_details` text
(localised, one `label: value` line per field) which the existing request-quote modal opens
with. `package_id` rides along; the server stores the package snapshot (now including
`attributes`) so the vendor sees exactly what was asked. No payment, no hold.

**Listing page (`/services`).** Filter **boxes**: vertical (icon cards in a scroll-snap
row, archetype-coloured), area (chip list of areas present in results plus free text),
price band (under K100 / K100-500 / K500-2,000 / over K2,000, in ngwee), rating (4.5+, 4+,
3+), availability ("Available now" = vendor-declared). URL-synced (`category`, `area`,
`band`, `rating`, `avail`, `sort`, `page`), server-rendered via `searchParams`, active
filters shown as removable chips with "clear all". Cards show archetype-aware price copy
("from K350 / night", "K80 / session") and rating.

**Vibe tokens.** Colour comes from `packages/ui` hue tokens (`ICON_HUE_*`) mixed into
surfaces with `color-mix` so dark mode follows the theme; no ad-hoc hex. Glass is used for
sticky bars and sheets only. Imagery guidance (shown to vendors in the form): hero 4:3 or
16:9 bright daylight, 1 wide shot + 3 detail shots; room = bed + window; menu = result
photos; gym = floor + equipment; rental = item on neutral ground; family = people at
play (consent noted).

## 6. Vendor experience

The service form reads the archetype (derived from the chosen vertical, with an "advanced:
change service type" override) and swaps the offer editor fields: room types, treatment
menu, passes, rental items, ticket kinds, rate cards. The same editor, same cap of 10, with
archetype-specific field groups, inline validation mirroring the Pydantic limits, and
archetype-specific helper copy and photo guidance. Service-level attributes (amenities,
policy, hours, schedule, staff, availability) appear in a collapsible "details" section.

## 7. MVP vs later

| MVP (this phase)                                                   | Later                                         |
| ------------------------------------------------------------------ | --------------------------------------------- |
| 7 archetypes, mapping + override, 6 new verticals                  | per-archetype fields as columns if we need SQL filters |
| Attribute validation, public/vendor read-write                     | real availability calendars + inventory locks |
| 4 bespoke layouts (accommodation, appointment, membership, rental) | bespoke on_site, ticketed, professional      |
| Request panel -> RFQ text + package snapshot                       | structured `booking_request` object, vendor confirm flow |
| Filter boxes + rating/availability (vendor-declared)               | live availability, map/near-me                |
| No payments for bookings                                           | deposits via the existing `accept_quote` spine once live; rental deposits |
| Vendor-declared hours/schedules                                    | timed-entry ticket QR (events spine)          |

## 8. Decisions taken (reversible)

| #     | Decision                                                                                   |
| ----- | ------------------------------------------------------------------------------------------ |
| ST-1  | 7 archetypes; verticals map to them; per-service override stored, null = derived.         |
| ST-2  | Offer = package row + `attributes` jsonb; validated per archetype in Pydantic, not SQL.    |
| ST-3  | Property/housing ships as `accommodation` with `stay_kind=monthly` (viewing request).      |
| ST-4  | Staffing/hiring ships as `professional` with role + rate attributes.                       |
| ST-5  | Availability filter = vendor-declared flag; rating filter = vendor-level review average.   |
| ST-6  | Bookings are requests through RFQ; the package snapshot carries `attributes`.              |
| ST-7  | Broken attributes degrade to the generic layout, never an error page.                      |
| ST-8  | Deposits (rental, lodging) are informational copy; Vergeo5 never collects them in MVP.     |

## 9. Open questions for the founder

1. **Verticals:** are lodging, property, fitness, rentals, family-fun, staffing the right
   names and Bemba/Nyanja labels? Should property (houses for rent/sale) be its own vertical
   with sale listings, or only rent/viewings as designed?
2. **Availability:** is a vendor-set "available / limited / unavailable" enough for launch, or
   do you want a real date calendar for lodges first (it is the largest later item)?
3. **Deposits and prepayment:** should rooms and rentals ever take a deposit through the
   existing escrow spine, or stay pay-at-venue / cash for the pilot?
4. **Imagery:** can we require at least 3 photos for lodging/family-fun to publish? A stock
   or generated-illustration fallback for services with no photos (the current empty hero)?
5. **Reviews:** ratings are per vendor today. Do you want per-service (per room type)
   reviews so a lodge's rating is not mixed with its bar?
6. **Hiring/staffing:** is this agencies listing workers (rates per day) or job ads? Job ads
   belong to ZedApply, not here.
7. **Housing:** any legal/KYC requirements for listing property (landlord verification)?
8. **Class schedules:** is a weekly recurring schedule enough, or do gyms need dated sessions?
