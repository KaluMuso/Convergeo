# Source Document

| Field          | Value                                                                                                   |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| DOCUMENT_SLUG  | `convergeo-events-strategy`                                                                             |
| DOCUMENT_TITLE | Convergeo Events Strategy & Ticketing Architecture                                                      |
| Document date  | April 2026                                                                                              |
| Source file    | `Convergeo_Events_Strategy_3ab4.pdf` (uploaded 2026-07-18)                                              |
| Pages          | 23                                                                                                      |
| Classification | Requirements / policy / specification (ticketing architecture + Zambia event catalogue + phased launch) |
| Companion to   | Strategic Master Plan (Q49 all-events, Q50 dynamic QR, Q5 commission 5–10%, Day 49–53 build)            |
| Audit mode     | READ-ONLY production reconciliation (2026-07-18)                                                        |
| Live project   | Supabase `dpadrlxukcjbewpqympu`                                                                         |

---

## Extracted text (layout via pypdf)

Convergeo · Events Strategy · 1
CONVERGEO
Events Strategy & Ticketing Architecture
How the platform should think about, model, and discover events across Zambia
Companion Brief to the Strategic Master Plan
Builds on: 75 strategic decisions, dynamic-QR ticketing (Q50), all-events scope (Q49), the Services and
Products briefs
Prepared: April 2026

===== PAGE BREAK =====

Convergeo · Events Strategy · 2

1. How This Connects to What You've Already Decided
   Your Strategic Master Plan locks in three decisions that shape everything in this brief. Q49 commits
   Convergeo to all event types — entertainment, conferences, workshops, private — from day one as part
   of the super-app behaviour. Q50 commits to in-app tickets with dynamic QR codes refreshing every 60
   seconds. Q5 sets the commission model at 5–10% of ticket price. Day 49–53 of the roadmap allocates
   the build window.
   That's the right foundation. What it doesn't yet specify is the model: what an Event actually is in the
   schema, how tickets relate to it, how non-ticketed and free events fit, how multi-day and recurring
   events work, what happens at the door, what happens when an event is cancelled, and which event
   categories should launch when. Without those decisions, the Day 49–53 work risks shipping a thin clone
   of every other ticketing platform — the same trap that the products brief warned about for catalogue.
   Where this brief plugs in: Section 4 of your Master Plan defines the Product/VendorListing schema
   and treats event tickets as a product class with a flag. This brief proposes adding a sibling Event
   entity (with TicketType and Ticket children) rather than overloading Product. The reason: events
   have time, capacity, and entry-control mechanics that don't compress cleanly into a product row.
   Same database, same APIs, parallel structure.
   Why events are not products with dates
   It's tempting to model an event ticket as a product with a date attribute and capacity = stock. It almost
   works. It breaks the moment any of the following happens, all of which are common in Zambia:
   • The event has multiple ticket tiers (VIP, regular, student) with different prices, different perks,
   and different inventory pools — but a single shared event description, venue, and timing.
   • The event runs for multiple days, and the customer either picks specific days or buys a pass that
   grants access to all days.
   • The event is recurring — yoga every Tuesday at 6pm, monthly film screenings — and the
   platform should treat each instance as bookable while linking them under one event identity.
   • The event is free but capacity-limited — kitchen parties, store openings, gallery exhibitions,
   religious gatherings — where RSVP and headcount tracking matter even though no money
   changes hands.
   • The ticket is personalised — the buyer's name appears on the QR — for fraud prevention.
   Products do not behave this way.
   Forcing all of this through the Product table creates either nightmare attribute JSON or a flood of
   phantom products. A small parallel Event/TicketType/Ticket schema solves it cleanly and lets the
   existing Cart, Order, Payment, and Escrow flows be reused with minimal change.

===== PAGE BREAK =====

Convergeo · Events Strategy · 3

===== PAGE BREAK =====

Convergeo · Events Strategy · 4 2. The Five Event Types
Every event on Convergeo collapses into one of five types. The type determines what fields the
organiser must fill in, what the ticketing flow looks like, what entry control behaves like at the door, and
what the refund and dispute policies are. This is the events equivalent of the six service archetypes and
the five product classes.
Type What it is Examples and behaviour
Single-occurrence
ticketed
One date, one start/end time,
paid admission. Capacity-limited.
Concerts, comedy nights, sports fixtures, standalone
workshops. The default. Dynamic QR per ticket. Escrow
held until event date.
Multi-day ticketed Same event identity spanning 2+
days. Customer may buy a day
pass, multi-day pass, or full-
festival pass.
Music festivals, agricultural fairs, multi-day expos, pop-up
markets. Each ticket carries valid_dates[]; QR scans are
date-aware.
Recurring Same event template repeats on
a schedule. Each instance is
bookable.
Weekly yoga, monthly film series, regular comedy nights.
One event template, many instances. Bookings attach to
instance, not template.
Free RSVP /
capacity-tracked
No payment, but capacity is finite
and the organiser wants
headcount and a guest list.
Store openings, religious gatherings, gallery openings,
community meetings, kitchen parties. Free QR ticket;
same entry-control mechanics; no escrow path.
Private /
invitation-only
Not publicly listed. Discoverable
only via direct link or invitation
code.
Weddings, funerals (where ticketed seating is used),
corporate events, private parties. Listed but
unsearchable; access via signed URL or 6-digit code.

Three things follow:
• All five types share the same Event schema. The differences are captured in flags (is_recurring,
is_private, is_free) and in child tables (TicketType, EventInstance for recurring). No type forks
the codebase.
• Free RSVP events matter more than they look. Half the events on Lusaka's calendar — gallery
openings, store launches, community gatherings — are free with RSVP. Excluding them means
Convergeo only ever shows the paying half of the city's social calendar, and loses the discovery
edge against Lusaka365 and Facebook events. They're cheap to support: same entry-control
flow, no payment integration.
• Private events are a feature, not an edge case. Wedding ticketing for plate-paying receptions,
funeral seating coordination, and corporate launches are real Zambian use cases. The mechanic
— listed-but-unindexed, access via code — is the same code path as a normal event with one
boolean flipped.

===== PAGE BREAK =====

Convergeo · Events Strategy · 5
Schema implication (low cost, high payoff): Add an Event entity with type enum (single / multi_day
/ recurring / free_rsvp / private), an EventInstance child (date, start_time, end_time, capacity), a
TicketType child (name, price, perks, inventory_per_instance), and a Ticket entity (the actual ticket
purchased, with personalised holder_name, dynamic_qr_secret, status). One small subtree, all five
types covered.

===== PAGE BREAK =====

Convergeo · Events Strategy · 6 3. Ticket Types, Pricing, and Capacity
The ticketing layer is where most platforms over-engineer. Convergeo should ship six ticket-pricing
modes from day one — even if only the simplest is exposed at launch — because retrofitting them later
forces painful migrations.
3.1 The six ticket pricing modes
Mode Description When it applies
Fixed-price tier One price, fixed inventory. "Regular
admission, K150, 200 available."
The default. Almost all small events at launch.
Multi-tier Multiple named tiers (VIP / Regular /
Student) with separate prices and
inventory pools.
Concerts, conferences, larger events. Each tier is a
TicketType row under one Event.
Early-bird / time-
staged
Same tier, price changes with time.
"K100 until April 30, K150 after."
Use price_schedule on the TicketType. Auto-
transitions on date.
Group / table Sold as a bundle of N seats. "Table of
8 for K3,200."
Weddings, corporate dinners, private rooms at
events. One sale, N tickets generated.
Free RSVP Zero price, capacity tracked. Type-4 events. Not a payment flow.
Pay-what-you-want Customer chooses an amount within
a min/max range.
Niche but useful for community events,
fundraisers, religious gatherings. Phase 3.

3.2 Capacity is a tree, not a number
A naive model has Event.capacity = 500. The real world is messier:
• Total venue capacity (the hard ceiling, set by the organiser based on the venue).
• Per-tier capacity that sums to the total — VIP 50 + Regular 350 + Student 100 = 500.
• Per-day capacity for multi-day events — same tier may have different capacity each day.
• Held seats for organiser comps, sponsor allocations, and door sales (bookable through admin
only).
Track capacity at the level where it's enforced: TicketType.inventory_total per instance, plus a venue-
level safety check at checkout. Don't let tier-sums exceed venue capacity. This is one validation rule,
easy to enforce at write time, that prevents a class of oversells that would destroy organiser trust on the
first big event.
3.3 Fees: who pays and how it's framed
Q5 sets commission at 5–10% of ticket price. Two practical refinements:

===== PAGE BREAK =====

Convergeo · Events Strategy · 7
• Display fees inclusive by default. The customer sees "K150" and at checkout sees "K150 ticket +
K9 platform fee = K159" with a clear breakdown. Hidden fees that surface only at checkout are
the single biggest cause of cart abandonment in ticketing — and Zambian buyers are particularly
sensitive after the WhatsApp "send me K150 and I'll bring the ticket" alternative.
• Let organisers choose absorb-fee or pass-through. Big organisers will prefer absorbing the fee to
keep round-number prices ("K150" not "K159"). Small organisers running thin margins will pass
through. The platform takes the same cut either way; only the tax-incidence framing changes for
the buyer.
• Set the floor commission at 5% (Q5 minimum) for the first 12 months. This matches the rate
established ticketing platforms charge in the region and removes "too expensive" as a reason for
organisers to stay on Facebook events.
3.4 Payment timing and escrow
Events are unique in your platform: there's a long gap between purchase and "delivery" (the event
itself), sometimes weeks. This creates organiser cash-flow problems if escrow logic from products is
applied naively.
• For events under 14 days away: hold full settlement until 24 hours after the event ends.
Standard escrow.
• For events 14+ days away: release 50% of settlement to the organiser at T-7 days, the remaining
50% at T+1 day after the event. This funds the organiser's last-week production costs (staging,
sound, security, catering deposits) without exposing the platform to a no-show event scam.
• For free RSVP events: no escrow path, but the platform still issues tickets and tracks attendance.
Useful data for the city-guide AI assistant later (Q52).

===== PAGE BREAK =====

Convergeo · Events Strategy · 8 4. Event Discovery: Time-First, Not Distance-First
The services brief argued for vector + geo search with proximity re-ranking. Events invert that. Distance
still matters, but time is the dominant axis: a perfect event 5km away that happened yesterday is
useless; an event 30km away tomorrow night is interesting. The discovery layer needs different defaults.
4.1 Three primary lenses
The events tab should expose three top-level lenses, all bookmarkable and shareable:
• When — Tonight, This Weekend, Next Week, Next Month, On a Date. Time-first browsing. This
is what people actually want to know: "what's on this Saturday?"
• What — Music, Comedy, Workshops, Conferences, Sports, Family, Religious, Markets,
Exhibitions. The category tree, used as filters layered on top of When.
• Where — by city (Lusaka, Ndola, Kitwe, Livingstone, Kabwe), by neighbourhood for dense cities,
plus a "near me" radius option.
4.2 Search ranking signals
Hybrid retrieval (Meilisearch + pgvector, same as products and services) with an event-tuned re-ranking
score:
• Time decay — events further in the future score lower than events imminent, modelling actual
user intent. Events past their end-time drop off the index entirely.
• Sell-through pressure — events that are 70%+ sold get a small "selling fast" boost and a visible
badge. This drives FOMO conversion and is the kind of signal that becomes invaluable once the
platform has a few hundred events.
• Distance — same Haversine treatment as services, but weighted lower. People will travel further
for the right event than they will for a haircut.
• Category match and follow signals — if a user has bought music tickets before, music ranks
higher for them. Cheap personalisation, no ML required.
• Verification — verified organisers (Tier 2/3 KYC) outrank Tier 1 organisers. This is doubly
important for events because the cold-start fraud risk is high.
4.3 Browse-by-time defaults
The homepage events module should default to "Tonight + This Weekend" rather than "Trending" or
"All". This sounds minor; it isn't. It's the single decision that makes the events tab feel alive on first visit,
because there are always events tonight or this weekend somewhere in Lusaka. "All upcoming events"
feels like a directory; "Tonight" feels like a scene.
4.4 The calendar view (Phase 2)

===== PAGE BREAK =====

Convergeo · Events Strategy · 9
After Phase 1 has 50+ active events, a calendar view becomes valuable: a month grid where each day
shows event-density dots, expandable into the day's events. This is how power users (event-goers in
Lusaka, tour planners, lifestyle bloggers) use a city's event ecosystem. It also feeds directly into the city-
guide AI trip planner from Q52 — "show me everything happening in Livingstone the weekend I'm
there".
4.5 The city-guide integration
Q52 commits to city guides for Lusaka, Livingstone, Ndola with AI enhancement later. Events should plug
into city guides as a first-class section, not an afterthought. A Livingstone city guide page that shows
tour operators (services), craft markets (products), and tonight's events at the local lodge — all
bookable in one flow — is the actual super-app behaviour your master plan promised. None of the
existing event platforms in Zambia bundle commerce, services, and event tickets in one transaction
layer; this is where Convergeo's positioning crystallises.

===== PAGE BREAK =====

Convergeo · Events Strategy · 10 5. Tickets, Dynamic QR, and Entry Control
Q50 commits to dynamic QR codes that refresh every 60 seconds. That's the right call — and it earns its
complexity at the door, where 90% of ticketing fraud actually happens. This section spells out the
mechanics so the Day 49–53 build doesn't ship a static-QR system that everyone refers to as "dynamic".
5.1 What dynamic QR actually means
Each issued Ticket carries a server-side secret (a long random string, never shown). The QR code
displayed in the customer's app is generated client-side every 60 seconds by HMAC-signing
(current_time_window || ticket_id) with that secret, encoded into a short URL or token. The scanner at
the door hits a verification endpoint with the scanned token; the server checks the HMAC against the
current and previous time-window using the same secret and returns valid / used / invalid / expired.
Three properties this gives you for free:
• A screenshot of the QR is useless after the next 60-second window. Scalpers cannot mass-share
screenshots in WhatsApp groups.
• A re-scan of the same ticket fails after the first valid scan. Tickets cannot be used twice — even
by the legitimate buyer who tries.
• The scanner works offline for short periods. Cache the day's secrets to the scanning device; sync
"used" status when the network returns. Critical for venues in the Copperbelt where
connectivity at the door is unreliable.
5.2 The PIN backup (Q33)
Q33 calls for QR primary + PIN backup. The PIN is a 6-digit code unique per ticket, displayed alongside
the QR. If the camera fails (cracked phone screen, lighting at the door, dust on lens), the door staff types
the PIN into the scanner app and the same verification logic runs. This is the kind of detail that quietly
differentiates the platform on the very first event when something goes wrong, which it always does.
5.3 Personalisation and transfer
Each ticket carries a holder_name, captured at purchase. By default, this is the buyer; for group
purchases, the buyer is asked to enter each holder's name.
• Tickets are transferable up to 6 hours before the event by the original buyer. Transfer revokes
the old ticket and issues a new one to the recipient via SMS / WhatsApp. The new holder has
their own QR + PIN.
• Transfer disabled within 6 hours of event start. Reduces same-day scalping; the legitimate "my
friend got sick, take my ticket" case is still served by the door staff scanning the original buyer's
ID against holder_name.

===== PAGE BREAK =====

Convergeo · Events Strategy · 11
• Resale is blocked at platform level. Q-style scalping markets are how trust evaporates. If a buyer
wants out, they can request refund per the policy below; they cannot list the ticket for sale.
5.4 Entry-control flow at the door
The vendor / organiser uses the same Convergeo app, switched into "event scanner" mode. Two-handed
flow:
• Door staff opens the event in scanner mode → camera activates → scans QR → screen shows
green check + holder name + tier ("Sarah Mwansa — VIP") in 1 second. Or red X with reason
("already used at 19:42", "expired", "wrong event").
• Organiser dashboard shows a live attendance counter: tickets sold, scanned, on-premises (sold
minus scanned), capacity. Useful for security limits and air-quality decisions in indoor venues.
• Manual override: organiser-role users (not just staff) can mark a ticket as scanned in the
dashboard if hardware fails entirely. Audit-logged.
5.5 Refunds, cancellations, and rescheduling
This is where event policies need to be explicit, not buried in T&Cs. A clear, customer-facing matrix
builds far more trust than tickets refreshing every 60 seconds:
Scenario Buyer entitled to Mechanic
Buyer cancels >7 days before Full refund minus 5%
admin fee
Self-service via order page; auto-refund from
escrow.
Buyer cancels 1–7 days before 50% refund or transfer Self-service; organiser sees the cancellation.
Buyer cancels <24 hours before No refund; transfer still
allowed
Reduces last-minute fraud; transfer preserves
goodwill.
Organiser cancels event 100% refund +
automatic notification
Platform-initiated. Escrow returned in full.
Organiser pays platform a small admin fee.
Organiser reschedules event Tickets auto-honour the
new date; opt-out
refund available
Notification + 7-day window to request refund.
Default keeps the ticket.
Force majeure (weather, etc.) Negotiated case-by-
case; platform mediates
Escrow held. Dispute flow (Q62).

===== PAGE BREAK =====

Convergeo · Events Strategy · 12 6. Organiser Onboarding and Tooling
Event organisers are a different vendor archetype from product sellers and service providers. They're
typically one-off or seasonal users — a person running an annual festival, a venue that hosts six events a
year, a workshop facilitator running quarterly sessions. Onboarding has to be lighter than vendor
onboarding for products, but trust requirements are arguably higher because event fraud is more visible
and more reputationally damaging.
6.1 Two organiser tiers, mapped to your tiered KYC
The Q35/Q36 tiered KYC model maps cleanly onto organisers:
• Tier 1 — Personal organiser. Identity verified via NRC photo. Can run free RSVP events (Type 4)
immediately and ticketed events up to a capped value (e.g. K20,000 GMV per event) until trust
is built. After 3 successful events, cap lifts.
• Tier 2 — Business organiser. PACRA verified. Full ticketed events, no caps. Can run multi-day and
recurring events. Earns the verified badge that customers see on every event card.
This compromise lets a one-person workshop facilitator launch instantly while reserving headline-act
ticketing capacity for vendors with skin in the game.
6.2 The event creation flow
Three-screen flow, designed to take under 5 minutes for a simple event:
• Screen 1 — Basics: title, category, type (single / multi-day / recurring / free / private), one-line
description, cover image, venue (with GPS pin), date(s) and time(s).
• Screen 2 — Tickets: add ticket types (name, price, capacity, perks). Free RSVP shows zero-price
as the default. Multi-tier reveals an "add another tier" button.
• Screen 3 — Promotion & policy: longer description with rich text, social links, refund policy
(defaults to platform standard), promotional banner, organiser bio. Organiser can publish or
save as draft.
Save-as-draft matters more for events than for products. Organisers iterate on event copy, get feedback
from co-organisers, and publish only when ready. The platform's bounce rate on event creation will be
terrible if every form requires immediate publication.
6.3 Co-organisers and team access
Real events have multiple people involved: the organiser, the venue manager, door staff, sometimes a
marketing partner. Each needs different access. A simple role model handles this without becoming an
HR system:
• Owner — full edit, financial, and refund access. The person who created the event.
• Manager — can edit event details, view sales, but not pull funds or issue refunds.

===== PAGE BREAK =====

Convergeo · Events Strategy · 13
• Door — scanner mode only. Cannot see financials, cannot edit anything.
Roles are added by phone number; the invited person gets an SMS with a one-tap link that grants them
access scoped to that event only. This is one feature that quietly punches above its weight in
differentiating from amateur ticketing.
6.4 Promotion tools the platform should provide
Don't expect organisers to be marketers. The platform should ship the basics:
• Auto-generated shareable link with rich Open Graph preview (title, image, date, price). One tap
from the event page; works in WhatsApp, Facebook, X, Instagram bio.
• Promo codes — flat or percentage discount, capped quantity, expiry date. Used for influencer
partnerships (Q28), sponsor giveaways, and "members get 20% off" mechanics.
• Affiliate links — a unique URL that tracks sales attributed to a specific influencer or partner, with
optional automatic revenue share. This is the same primitive that makes Q28's TikTok /
Instagram strategy actually measurable.
• Email/SMS to past attendees — once an organiser has run 2+ events, they can message past
buyers about the next one. Opt-out respected. Quiet retention engine.
6.5 Analytics organisers actually use
Don't recreate Google Analytics. Show four numbers prominently on the organiser dashboard:
• Tickets sold vs capacity, by tier.
• Sales velocity — sales per day, with a trend arrow.
• Where buyers came from — direct, search, shared link, promo code (this is the only piece
organisers will obsess over).
• Predicted final attendance — a simple "based on current pace, you'll sell ~340 of 500"
projection. Wrong sometimes, useful always, and a reason to keep checking the dashboard.

===== PAGE BREAK =====

Convergeo · Events Strategy · 14 7. Fraud and Trust Specific to Events
Event fraud has two distinct vectors that don't apply to products or services. Both need explicit
defences.
7.1 Buyer-side fraud (counterfeit and duplicate tickets)
This is what dynamic QR solves. But two layered defences make it bulletproof:
• First-scan-wins, with logging. The first valid scan marks the ticket used. Subsequent scans return
red with the original scan timestamp visible. No ambiguity at the door.
• ID match for high-value tickets (>K500). The QR scanner displays the holder name; door staff can
be instructed to spot-check ID. Optional, organiser-toggleable. Disabled by default to avoid
friction at small events.
7.2 Organiser-side fraud (no-show events)
Far more dangerous to platform reputation: an organiser collects ticket money for an event that never
happens. Three mechanics in combination handle this:
• Tier 1 caps. New organisers cannot sell more than K20,000 of tickets for a single event until
they've successfully run three. This caps platform exposure to first-time-fraud.
• Escrow timing (Section 3.4). Even Tier 2 organisers don't see most of the money until 24 hours
after the event ends. Pulling a no-show stunt means losing access to the funds.
• Pre-event verification calls. For events selling >K100,000 in tickets, a platform staffer calls the
organiser 48 hours before the event to confirm logistics. Five minutes of staff time, virtually
eliminates the high-value fraud case. Can be automated as the platform grows — for now it's
manual and worth it.
7.3 Disputes and chargebacks
When something goes wrong — event was disappointing, advertised performer didn't show, venue
oversold and turned people away — the dispute flow needs an event-shaped path:
• Disputes can be opened up to 7 days after the event end-time.
• Photo / video evidence is mandatory for "event was misrepresented" disputes.
• If the organiser doesn't respond within 72 hours, the dispute auto-resolves in the buyer's favour
and the platform refunds from the held escrow.
• Repeat-disputed organisers (3+ disputes upheld) lose ticketing privileges. Reinstatement
requires Tier 2 KYC and platform interview. Aligns with Q62 escalation tiers.

===== PAGE BREAK =====

Convergeo · Events Strategy · 15 8. Comprehensive Event Catalogue for Zambia
This is the events universe Convergeo's data model must absorb. Organised by category, each row maps
to one of the five event types from Section 2 and notes the dominant pricing mode plus Zambian
context. Phase 1 launch picks live in Section 9.

Category Sub-category Type Pricing mode Zambian context
Music & Live
Performance
Concerts (Zambian
artists)
Single ticketed Multi-tier Yo Maps, Slap Dee,
Chef 187 etc.
Lusaka/Copperbelt
heavy. Hard-ticket
fraud risk.
Music & Live
Performance
Concerts (international
touring)
Single ticketed Multi-tier + early-
bird
Periodic; high-value
(K500-K2000+). Pre-
event verification
mandatory.
Music & Live
Performance
Music festivals (multi-
day)
Multi-day
ticketed
Day pass + festival
pass
Stanbic Music
Festival, Lake of Stars
adjacent. Multi-tier
per day.
Music & Live
Performance
Album launches Single ticketed Fixed or tiered Often hybrid —
public ticketed +
private VIP.
Music & Live
Performance
DJ nights & club events Single ticketed Fixed + table
booking
Lusaka nightlife.
Group/table pricing
important.
Music & Live
Performance
Open mic & live music
nights
Recurring Fixed Weekly venue
events. Recurring
instances.
Music & Live
Performance
Gospel concerts Single ticketed Multi-tier Major category in
Zambia. Often
church-organised.
Comedy & Theatre Stand-up comedy nights Single ticketed Fixed Growing scene.
Lusaka Playhouse,
restaurant venues.
Comedy & Theatre Theatre productions Single or multi-
day ticketed
Multi-tier Lusaka Playhouse,
university
productions.

===== PAGE BREAK =====

Convergeo · Events Strategy · 16
Category Sub-category Type Pricing mode Zambian context
Comedy & Theatre Improv & sketch shows Recurring Fixed Weekly / monthly
venue series.
Sports Football matches
(domestic)
Single ticketed Multi-tier
(terrace/main/VIP)
Super League
fixtures. Stadium
ticketing — high
volume, low price-
point.
Sports Football matches
(international)
Single ticketed Multi-tier AFCON qualifiers,
friendlies. Premium
pricing tiers.
Sports Rugby & netball fixtures Single ticketed Fixed Smaller volume but
loyal audiences.
Sports Athletics & marathons Single ticketed Tiered (5K / 10K /
half / full)
Lusaka Marathon,
Victoria Falls
Marathon. Race
entry, not spectator.
Sports Boxing & MMA events Single ticketed Multi-tier + table Esther Phiri-era
legacy; periodic big
events.
Sports Golf tournaments Single ticketed

- free
  spectator
  Player entry +
  corporate sponsor
  Often charity-tied.
  Player slots ticketed;
  gallery free.
  Conferences &
  Professional
  Industry conferences Multi-day
  ticketed
  Multi-tier
  (delegate /
  student /
  corporate)
  Tech, finance,
  mining, agriculture.
  High price-point, low
  volume, B2B.
  Conferences &
  Professional
  Trade expos & exhibitions Multi-day
  ticketed
  Day pass + free
  with registration
  Zambia International
  Trade Fair,
  agricultural shows.
  Conferences &
  Professional
  Networking events Single ticketed Fixed Chamber of
  Commerce,
  professional bodies.
  Conferences &
  Professional
  Career fairs Single ticketed
  or free RSVP
  Free or low fixed Universities,
  recruitment-driven.
  Conferences &
  Professional
  Investor pitch nights Single ticketed Fixed Startup ecosystem;
  growing in Lusaka.

===== PAGE BREAK =====

Convergeo · Events Strategy · 17
Category Sub-category Type Pricing mode Zambian context
Workshops &
Education
Skills workshops Recurring or
single
Fixed or tiered Photography, coding,
business basics.
Recurring template.
Workshops &
Education
Wellness workshops Recurring Fixed Yoga, breathwork,
women's circles.
Capacity tight.
Workshops &
Education
Cooking & food classes Single or
recurring
Fixed Restaurant-led
cooking classes;
ingredient cost
included.
Workshops &
Education
Art classes & paint-and-
sip
Recurring Fixed Lusaka emerging
category.
Workshops &
Education
Language classes Recurring Fixed
(subscription-
style)
Bemba, Nyanja for
foreigners; English
for locals.
Workshops &
Education
Children's workshops Recurring Fixed Multi-sensory play,
art, holiday
programmes.
Workshops &
Education
Religious teachings &
retreats
Single or multi-
day ticketed
Free RSVP or low
fixed
Major category. Free
RSVP common.
Cultural & Arts Art exhibitions &
openings
Free RSVP or
ticketed
Free / low fixed Lechwe Trust, Henry
Tayali Art Centre,
gallery openings.
Cultural & Arts Film screenings Recurring or
single
Fixed (low) LUCAC monthly
series, indie cinema,
documentary nights.
Cultural & Arts Cultural festivals
(traditional)
Multi-day
ticketed
Multi-tier Kuomboka, N'cwala,
Likumbi Lya Mize.
Tourism-tied.
Cultural & Arts Poetry & spoken word Recurring Fixed Niche but loyal
scene.
Cultural & Arts Book launches Free RSVP or
single ticketed
Free / low fixed Authors, publishers.
Cultural & Arts Photography exhibitions Free RSVP Free Gallery + commercial
space hybrids.

===== PAGE BREAK =====

Convergeo · Events Strategy · 18
Category Sub-category Type Pricing mode Zambian context
Food & Beverage Pop-up dinners & supper
clubs
Single ticketed Fixed (price
includes meal)
Chef-driven,
intimate. K300-K1500
per seat.
Food & Beverage Wine tastings Single ticketed Fixed Limited-seat.
Shardonnay-style
venues.
Food & Beverage Cocktail & spirits events Single ticketed Fixed Sponsor-driven
often.
Food & Beverage Food festivals & markets Single or multi-
day
Free RSVP + paid
stalls
Lusaka food trucks,
weekend markets.
Food & Beverage Coffee cuppings &
tastings
Single ticketed Fixed Specialty coffee
scene growing.
Food & Beverage Brunch & rooftop events Single ticketed Fixed Cargo88-style; price
includes meal.
Lifestyle &
Community
Fashion shows & runways Single ticketed Multi-tier Lusaka July, designer
launches.
Lifestyle &
Community
Thrift markets & flea
markets
Single Free RSVP + paid
stalls
Growing weekend
institution.
Lifestyle &
Community
Fitness & sports
community events
Recurring Free RSVP or fixed Park runs, cycling
clubs.
Lifestyle &
Community
Women-only events &
circles
Single or
recurring
Fixed Major category.
Game nights,
wellness, circles.
Lifestyle &
Community
Game nights & social
games
Recurring Fixed Trivia, board games,
themed nights.
Lifestyle &
Community
Children's & family
events
Single ticketed
or free
Fixed Holiday activities,
theme parks, play
centres.
Lifestyle &
Community
Pet & animal events Single ticketed Fixed Dog shows, adoption
days. Niche but loyal.
Religious & Spiritual Major religious
gatherings
Single ticketed
or free RSVP
Free / low fixed Crusades,
conferences. Often
free RSVP at scale.

===== PAGE BREAK =====

Convergeo · Events Strategy · 19
Category Sub-category Type Pricing mode Zambian context
Religious & Spiritual Worship nights &
concerts
Single ticketed Fixed Gospel concerts
overlap; standalone
worship events.
Religious & Spiritual Retreats & camps Multi-day
ticketed
Fixed (includes
lodging)
Church youth camps,
women's retreats.
Markets & Expos Agricultural shows Multi-day
ticketed
Day pass Lusaka Show,
regional shows.
Annual flagships.
Markets & Expos Trade fairs Multi-day
ticketed
Day pass +
corporate
ZITF (Bulawayo)
draws Zambian
attendees; domestic
equivalents.
Markets & Expos Real estate & property
expos
Single ticketed
or free
Free / low fixed Developer-led, sales-
funnel events.
Markets & Expos Wedding expos Single ticketed Low fixed Bridal industry
showcases. Vendor-
funded.
Tourism-Adjacent Adventure activity
bookings
Recurring
(daily)
Fixed per activity Bungee, rafting,
helicopter tours —
Livingstone-centric.
Overlaps with
services.
Tourism-Adjacent Safari sundowner events Recurring Fixed Lodge-organised.
Tourism-Adjacent Boat cruises &
sundowner cruises
Recurring Fixed Zambezi sunset
cruises. Capacity-
tight.
Tourism-Adjacent Wildlife & park-led
events
Single or
recurring
Fixed DNPW-organised.
Edutainment.
Private Weddings (with ticketed
seating)
Private Group/table or
fixed
Listed-but-
unindexed. Access by
code.
Private Corporate launches &
parties
Private Free RSVP or fixed Internal distribution.

===== PAGE BREAK =====

Convergeo · Events Strategy · 20
Category Sub-category Type Pricing mode Zambian context
Private Private parties (kitchen
parties, etc.)
Private Fixed or group Massive Zambian
category. Privacy-
sensitive.
Private Funerals (ticketed
seating)
Private Free RSVP Coordination tool,
not commerce.
Sensitive UX.

That's roughly 65 event sub-categories across 11 top-level categories. Combined with the ~110 service
sub-categories and ~100 product sub-categories, Convergeo's catalogue now spans 275+ supply types.
The architectural payoff: 5 product classes + 6 service archetypes + 5 event types = 16 behavioural
patterns, all sharing one schema, one search layer, one trust system, one payment rail. That is a
genuinely unified super-app, not three apps stitched together.

===== PAGE BREAK =====

Convergeo · Events Strategy · 21 9. Phased Events Launch (Aligned to the 60-Day
Roadmap)
Day 49–53 of your roadmap allocates the build window for events and ticketing. With launch on Day 60,
that gives you about 4 working weeks between events going live in code and the public launch. Phase 1
should target a small number of high-quality events rather than blanketing the calendar.
Phase 1 — Launch (Days 49–60 build, weeks post-launch)
Six categories where supply is achievable in a few weeks of organiser outreach and where ticketing is
genuinely valuable to organisers (i.e. they're currently using WhatsApp + bank transfers and hating it):
• Workshops & education — wellness, skills, cooking, art classes. Small capacity, organiser-
friendly, recurring — the perfect starter category. Recruit 5–10 facilitators.
• Comedy & theatre — defined venues, established organisers, manageable scale. Recruit 2–3
venue partnerships.
• Pop-up dinners and food events — chef-driven, intimate, currently chaotic on WhatsApp.
Recruit 3–5 supper-club operators.
• Cultural & arts — gallery openings, film screenings, book launches. Mostly free RSVP at first,
which sidesteps payment risk while building event-volume credibility.
• Lifestyle & community — game nights, women-only events, fitness community runs. Cheap to
organise, frequent, build platform habit.
• Free RSVP events broadly — make it free for organisers in Phase 1 (no platform commission on
free events ever, by design). This populates the calendar fast and gives the discovery layer
something to show.
Phase 2 — Commerce deepening (Months 3–6 post-launch)
• Music concerts (Zambian artists) — the big-ticket category. Wait until trust is established and
Tier 2 organiser onboarding is smooth.
• Conferences & expos — high-value, B2B, longer sales cycles. Needs the multi-tier and group-
pricing UI fully shipped and tested.
• Sports fixtures — partnerships with FAZ, clubs. Stadium-scale ticketing tests the QR scanner
under volume.
• Fashion shows, wedding expos — vendor-funded events that bring product/services vendors
onto the platform via a different door.
• Multi-day events — agricultural shows, music festivals. Tests the multi-day ticket schema in
production.

===== PAGE BREAK =====

Convergeo · Events Strategy · 22
Phase 3 — Long tail and high-stakes (Months 6–12)
• International touring concerts — high-value, high-risk. Pre-event verification calls become
standard. Possibly the first category where Convergeo charges premium commission (8–10% of
Q5's range).
• Religious gatherings at scale — large free-RSVP capacity events. Tests the system under 5,000+
attendee scans.
• Private events (weddings, funerals, corporate) — the privacy and code-access flow requires
careful UX design. Worth doing well, not first.
• Cultural festivals (Kuomboka, N'cwala) — government and traditional authority partnerships.
Long lead time, high reward.
• Tourism-adjacent recurring activities — connects to the city-guide AI assistant; this is where
commerce + services + events fully converge.

===== PAGE BREAK =====

Convergeo · Events Strategy · 23 10. Pulling It Together
Your existing decisions — dynamic-QR, all-events scope, 5–10% commission, the Day 49–53 build
window — are correct foundations. This brief sharpens the model: how events are typed, how tickets
are priced and capacity-managed, how discovery works on a time-first axis instead of distance-first, how
dynamic QR actually behaves at the door, how organisers onboard, and what to launch when.
The five things to take away:
• Events fall into five types (single ticketed, multi-day ticketed, recurring, free RSVP, private). One
Event entity with type enum, plus EventInstance and TicketType children, covers all five without
forking the codebase.
• Six ticket pricing modes need to coexist from day one, even if only fixed-price tier is exposed at
launch. Multi-tier, time-staged, group/table, free RSVP, and pay-what-you-want each handle a
real Zambian use case.
• Discovery is time-first, not distance-first. The events tab defaults to "Tonight + This Weekend".
Distance and category filter on top. Sell-through pressure ("selling fast") is a uniquely event-
shaped ranking signal worth surfacing.
• Dynamic QR is the door mechanic, not the brochure feature. HMAC-signed time-windows, 60-
second refresh, PIN backup, offline scanner cache, first-scan-wins logic. Without these
mechanics, "dynamic QR" is marketing language.
• Phase 1 picks six categories — workshops, comedy/theatre, pop-up food, cultural & arts,
lifestyle community events, and free RSVP broadly — where supply is reachable, capacity is
small, and organisers are currently using WhatsApp + bank transfers. Concerts, conferences, and
high-value events wait for Phase 2. Religious-scale and international-touring events wait for
Phase 3.
Combined with the products and services briefs, Convergeo's supply model is now fully specified: 16
behavioural patterns, 275+ sub-categories, one schema, one search, one trust layer, one payment rail.
The "hub of logos" that Q72 commits to is no longer aspirational language — it's a documented
architecture.

End of brief.
