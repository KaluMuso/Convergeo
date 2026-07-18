# Source Document

| Field          | Value                                                                                |
| -------------- | ------------------------------------------------------------------------------------ |
| DOCUMENT_SLUG  | `convergeo-product-strategy-april-2026`                                              |
| DOCUMENT_TITLE | Convergeo Product Strategy & Catalogue Architecture                                  |
| Prepared       | April 2026                                                                           |
| Source file    | `Convergeo_Product_Strategy_e030.pdf` (uploaded 2026-07-18)                          |
| Pages          | 23                                                                                   |
| Document class | Requirements / policy / specification (catalogue architecture)                       |
| Companion to   | Strategic Master Plan; builds on Product/VendorListing model + Services brief        |
| Audit mode     | READ-ONLY production reconciliation (2026-07-18)                                     |
| Assumption     | Auditing this Product Strategy PDF only (not the separately uploaded Strategy Brief) |

---

# Extracted text

## Page 1

Convergeo · Product Strategy · 1
CONVERGEO
Product Strategy & Catalogue Architecture
How the platform should think about, model, and onboard physical and digital products across
Zambia
Companion Brief to the Strategic Master Plan
Builds on: 75 strategic decisions, the canonical Product / VendorListing model, the Services brief
Prepared: April 2026

## Page 2

Convergeo · Product Strategy · 2

1. How This Connects to What You've Already Decided
   Your Strategic Master Plan locks in a clear product foundation: the canonical Product table is the golden
   record for an item, the VendorListing table holds price, stock, and condition per vendor (decisions Q12,
   Q41, plus the shared-image insight you flagged yourself). That model is correct and will scale. This brief
   does not revisit it.
   What this brief does is push one layer deeper. The canonical model works perfectly for a Coca-Cola
   500ml. It works less perfectly for a kilo of fresh tomatoes, a 50kg bag of cement, a salaula bale, an Itel
   A23 Pro that may or may not be the same SKU as the one a competing vendor is selling, or a custom-
   tailored chitenge dress. Most of the architectural choices you've already made stay; what changes is the
   rules around when an item gets a canonical entry, when it doesn't, and how vendors create listings
   without polluting the catalogue.
   Where this brief plugs in: Section 4 of your Master Plan (Technical Architecture) defines the
   Product/VendorListing schema. This brief proposes additions — product classes, pricing modes,
   condition models, attribute groups — that fit inside that schema as JSON attribute groups rather
   than new tables. Nothing here breaks the 60-day roadmap.
   The asymmetry between products and services
   In the services brief I argued that services collapse into six transaction archetypes. Products are simpler
   in transaction shape — most are buy-now — but harder in catalogue shape, because Zambian
   commerce mixes branded global SKUs, branded local SKUs, generic commodities priced by weight or
   volume, second-hand goods with no SKU at all, custom-made items, and bulk/wholesale orders that
   need quote flows. A flat product table treats all of these the same, which is why so many African e-
   commerce attempts feel chaotic.
   The fix is not more tables. It's recognising that the canonical-Product idea is a spectrum, not a binary,
   and designing the catalogue around five product classes that each behave differently.

## Page 3

Convergeo · Product Strategy · 3 2. The Five Product Classes
Every item that ever appears on Convergeo will fit into one of five classes. The class determines whether
a canonical record exists, how vendors attach to it, what fields are mandatory, what the comparison
view looks like, and how stock is counted.
Class What it is Canonical model Pricing mode Examples
A. Branded SKU Manufacturer-
defined products
with a fixed identity
(model, size, colour).
Strict canonical. One
Product row, many
VendorListings.
Per-unit, fixed. iPhone 15 Pro Max,
Samsung A55 5G,
HP ProBook, Coca-
Cola 500ml, Roma
tomato sauce
410g.
B. Branded
variant
Branded item with
vendor-relevant
variants (pack size,
flavour) but still a
defined SKU.
Canonical with
variants. Variant table
beneath product.
Per-unit per variant. Sun Maize Meal
25kg vs 10kg vs
5kg, Mosi Lager 6-
pack vs case,
Vaseline 100ml vs
250ml.
C. Commodity /
generic
Unbranded or
weakly branded
staples; quality
varies; substitutable.
Loose canonical. One
row per (commodity ×
grade × unit).
Per-kilo, per-litre, per-
bag, or per-bunch.
Tomatoes, onions,
dried kapenta,
charcoal, river
sand, cement
(mostly), maize
grain.
D. One-of-a-
kind / unique
Each unit is
genuinely different
— no two are the
same.
No canonical. Each
listing stands alone.
Per-listing, often
negotiable.
Used cars, used
phones, salaula
items, antiques,
custom artwork,
specific used
furniture.
E. Made-to-
order
Item is produced
after the order is
placed; spec is the
order.
No canonical. Listing is
a template; order
carries the spec.
Quote or template-
priced.
Tailored chitenge
outfits, custom
curtains, custom
cakes, bespoke
leather, custom
signage.

Three things follow from this:

## Page 4

Convergeo · Product Strategy · 4
• The canonical-Product table you've designed is exactly right for Class A and Class B. That's where
the comparison view, the shared images, the price-and-distance sort, and the hyper-local
competition all happen — and those classes will dominate Phase 1 GMV.
• Class C breaks the pure-canonical model in a useful way. We need a canonical "commodity row"
for tomatoes-per-kilo, but the photos and even the description have to be vendor-supplied
because a heap of Soweto Market tomatoes genuinely doesn't look like a heap of Pick n Pay
tomatoes. Section 3 covers this.
• Class D and Class E should not pollute the canonical Product table at all. They live in the same
VendorListing table but with product_id = NULL and a class flag. Search still finds them via
Meilisearch + pgvector; comparison views just don't apply. This is how you absorb salaula, used
phones, and tailored work without making the catalogue feel like a flea market.
Schema implication (low cost, high payoff): Add a product_class enum (A–E) on both Product and
VendorListing. Add a nullable product_id FK on VendorListing (already implied by your model). For
Class D/E listings, product_id is NULL and the listing carries its own title, description, images, and
attributes. One enum field unlocks correct behaviour for all five classes without new tables.

## Page 5

Convergeo · Product Strategy · 5 3. Pricing Modes and Units of Sale
This is where most multi-vendor platforms in Africa quietly fail. They model price as a single ZMW
number per listing. That's fine for an iPhone. It is wrong for almost everything in a market. The pricing
model needs to support six modes from day one — even if the UI surfaces them progressively.
3.1 The six pricing modes
Mode Description When it applies
Per-unit fixed Single price for one unit. Standard
e-commerce.
Class A and B in almost all cases. Default mode.
Per-weight / per-
volume
Price expressed per kg / per litre /
per 100g; total computed at
checkout from weight chosen.
Butcheries, fresh produce by kilo, bulk dried goods, fuel,
paint.
Per-bunch / per-
pile / per-bundle
The Zambian market reality. "K20 a
heap" of tomatoes, "K10 a bunch"
of rape.
Soweto, Chisokone, City Market sellers. Class C.
Tiered / volume Different prices for different
quantities (1–10 = K50, 11–50 =
K45, 50+ = K40).
Wholesale-friendly listings, building materials, agro-
inputs. Q37.
Range / from "From K850" — actual price
depends on customisation
captured at checkout.
Class E made-to-order items. Tailoring, custom cakes,
signage.
Quote-only No public price; customer
requests, vendor responds.
Bulk corporate orders, large-quantity wholesale, B2B
(Q37).

3.2 Unit-of-sale matters more than you'd think
A vendor selling 50kg bags of mealie meal and a vendor selling 5kg bags should not appear on the same
canonical row. They appear on linked variant rows under the same parent product. The customer sees
both, can sort by price-per-kg (which the platform computes for them — vendors are not asked to do
unit math), and can filter to a preferred pack size. Without that price-per-kg normalisation, comparison
shopping breaks.
Therefore every product (Class A, B, C) carries two unit fields: a sale_unit (the unit the customer actually
buys: bag, bottle, kg, bunch) and an optional base_unit (the comparable unit: kg, litre, gram). Where
both exist, the platform always shows price-per-base-unit alongside the sticker price. This is a small
piece of UX that will quietly differentiate Convergeo from every WhatsApp seller in the country.

## Page 6

Convergeo · Product Strategy · 6
3.3 Currency display vs. settlement
Your decision Q23 is right — display in any currency, settle in ZMW. Two refinements specific to
products:
• For imported goods (electronics, cosmetics, vehicles) vendors should be able to peg the listing to
USD with a daily-refreshed FX margin. The customer sees ZMW; the vendor isn't bankrupted by
a kwacha slide between listing and sale.
• Lock the FX rate at order placement, not at fulfilment. Otherwise a 48-hour escrow becomes a
vendor's currency-exposure problem.

## Page 7

Convergeo · Product Strategy · 7 4. Condition, Authenticity, and the Used-Goods Problem
Used and refurbished goods are too big a category to ignore in Zambia. Used Japan-import cars, second-
hand electronics from Dubai routes, refurbished laptops, and salaula clothing are all major real
categories. They're also the largest source of buyer disputes if not modelled carefully.
4.1 Condition tiers
Every Class A, B, and D listing must declare a condition from a controlled enum:
• New — sealed, with manufacturer warranty, original packaging.
• New (open box) — opened but unused, full warranty.
• Refurbished — professionally restored, working, may carry vendor warranty.
• Used — Excellent / Good / Fair — three tiers with clear platform-defined criteria, not vendor
self-description.
• For parts / not working — buyer accepts the item is non-functional.
The enum matters because search filtering, return-policy logic, and escrow hold periods can all branch
on it. Used items, for instance, get a slightly longer escrow window (72 hours rather than 48) because
verification on arrival takes longer.
4.2 Required evidence by condition
For anything not New, the platform should require photo evidence at listing time:
• Used phones / electronics: photo of the device powered on, plus serial number / IMEI photo
(the IMEI also lets the platform check against blacklisted-stolen-device databases later).
• Used vehicles: VIN photo, mileage photo, plus four exterior angles.
• Salaula: photo of the actual item being sold, not a stock photo. This is the single biggest fraud
vector and is worth enforcing strictly.
4.3 Authenticity for Class A branded SKUs
Counterfeits — particularly cosmetics, phone accessories, and pharmaceuticals — are a real risk. Three
layers of defence, in order of effort:
• Tier 2/3 vendors only on high-counterfeit-risk categories. Don't let Tier 1 (NRC-only) vendors list
cosmetics, supplements, or pharmaceuticals.
• Brand-protection program. Once a brand has 5+ vendors on the platform, allow the brand
owner (or their authorised distributor) to claim the canonical Product page and flag suspicious
listings.
• Customer-side authenticity reporting. A one-tap "this looks fake" button on every listing, routed
to admin queue. Cheap, effective.

## Page 8

Convergeo · Product Strategy · 8

## Page 9

Convergeo · Product Strategy · 9 5. Inventory: How Stock Should Actually Be Counted
Your existing schema has stock_quantity as an integer on VendorListing. Correct for Class A and most B.
Three additions handle the rest of the catalogue.
5.1 Stock modes
• Tracked numeric — the default. "I have 7 of these". Decrements on order, blocks at zero.
• Made-to-order — Class E. Stock is effectively infinite within capacity; the constraint is lead time,
not quantity. Vendor sets a per-week capacity and a default lead-time; orders past capacity
queue or get rejected.
• By-weight bulk — Class C bulk goods. Vendor declares total available weight (e.g. 200kg of dried
beans) and the system decrements as customers buy partial weights.
• Always-available service-like — for digital goods, infinite-supply downloads, certain rentals.
5.2 Reservation, not just decrement
During checkout, stock should be reserved for a short window (10–15 minutes is standard) rather than
decremented immediately. This is in your roadmap ("Stock reservation during checkout (timeout-based
release)" — day 23-24). Worth flagging the rule that goes with it: reserved stock counts as out-of-stock
for new buyers, but if the reservation expires unpaid, it must release atomically. Race conditions here
are how oversells happen.
5.3 Multi-vendor inventory honesty
Consider this risk: a vendor lists 50 units, sells 30 on Convergeo and 25 face-to-face at their physical
shop, and Convergeo only sees 20 of those 30 sold (they marked 10 as fulfilled outside the platform).
The platform now thinks they have 20 left when they have -5. Buyers order, vendor cancels, dispute
count climbs.
Two mitigations, both lightweight:
• Flag vendors whose cancel-rate exceeds 5% of orders. Auto-suspend at 10%. The first is a
warning shot; the second is a circuit-breaker.
• Phase 3 feature: optional POS-light integration. A vendor with a physical shop can mark off-
platform sales in their dashboard with one tap, keeping Convergeo's stock count honest. Pair
this with a tiny incentive — a 0.5% commission discount for vendors who do — and adoption
follows.

## Page 10

Convergeo · Product Strategy · 10 6. How Vendors Actually Add Products
Different vendor types onboard products differently. One-size-fits-all listing forms are why platform
vendor-onboarding stalls in week three. Five flows cover the universe; each maps cleanly to your
existing tiered KYC and to the product classes.
6.1 Search-and-attach (the default for Class A and B)
Vendor types the product name. Convergeo's catalogue search finds the canonical Product. Vendor sees
"Add your offer" and provides only price, stock, condition. Whole flow under 30 seconds. This is what
your admin team curates the canonical catalogue for, and it is the single most powerful vendor-
acquisition mechanic on the platform.
6.2 Submit-new-canonical (the long tail of Class A and B)
Vendor cannot find their product. They submit a candidate canonical record: name, brand, category,
description, images, specs. It enters a moderation queue. Admin or AI-assisted moderation either
approves it as a new canonical Product, merges it with an existing one, or rejects with reason. Vendor's
listing goes live attached to whichever canonical record it ends up on.
Two practical rules around this queue:
• Auto-approve obvious duplicates of high-confidence brand+model matches. Don't make admin
review every Coke 500ml submission.
• Pay a small reward (free month of Bronze, K50 credit) to vendors whose submissions become
canonicals adopted by 3+ other vendors. They are doing the platform's catalogue work for free;
recognise it.
6.3 Commodity quick-list (Class C)
Market traders aren't going to fill out a 12-field form. The flow is: pick category (vegetables / fish /
charcoal / etc.), pick the commodity (tomatoes, kapenta, etc.) from a curated list, choose unit (per heap
/ per kg / per bunch), set price, snap one photo, publish. Three taps and a photo. The canonical
commodity row carries category, unit options, and a generic description; the vendor's listing carries
price, photo, and stock.
6.4 Unique-item listing (Class D)
Used phones, used cars, salaula. Full vendor-defined listing: title, description, multi-photo upload
(mandatory: real photos of this exact item), condition tier, evidence photos for high-risk items (IMEI,
VIN, mileage). Listing does not attach to any canonical Product. Search and discovery still work because
Meilisearch indexes the listing's own fields and pgvector embeds its description.
6.5 Made-to-order template (Class E)

## Page 11

Convergeo · Product Strategy · 11
Tailor or custom maker creates a template: "Custom chitenge two-piece — from K320, 5–7 day lead
time". Template carries example photos, fabric/material options, sizing form. When customer orders,
they fill the spec form (chest, waist, fabric choice, optional reference photo upload), platform converts
to a normal order with the spec attached.
6.6 Bulk operations
Aligns with your Q39 (manual + CSV bulk + API). Two specifics:
• CSV import schema should match the canonical Product fields, and the importer should
aggressively try to match incoming rows to existing canonicals before creating new ones. This
prevents the catalogue from doubling every time a Tier 2 vendor uploads.
• API access (Tier 3) should support webhook-based stock sync, not just one-shot uploads. A
vendor with their own POS shouldn't need to remember to push stock; the integration pushes
on every sale.

## Page 12

Convergeo · Product Strategy · 12 7. Product Discovery: Where the Services Logic Already
Mostly Applies
Your Strategic Master Plan correctly chose Meilisearch as the primary search engine and pgvector as the
semantic-AI-ready layer. The services brief argued for hybrid retrieval (BM25 + vector embeddings) with
reciprocal rank fusion, then geo and quality re-ranking. Almost all of that translates directly to products.
Three product-specific additions:
7.1 Two ranking signals you don't have for services
• In-stock boost. Out-of-stock listings should not appear on result page 1 except as a last resort.
This is mechanical, not editorial.
• Price competitiveness within canonical. For Class A and B, where multiple vendors sell the same
thing, the platform should slightly boost listings priced at or below the median for that
canonical. This rewards aggressive pricing without punishing anyone — and it teaches vendors
that being competitive is rewarded by visibility, which is the right behavioural lesson.
7.2 Browse vs. search vs. ask
Three discovery modes; the homepage should give equal weight to all three rather than collapsing them:
• Browse: category tree, curated collections (Q30), trending products, new arrivals. Good for
users who don't know what they want.
• Search: typed query, hybrid retrieval, faceted filters. Good for users with intent.
• Ask (Phase 3, after data accumulates): natural-language assistant. "I need a phone for my mum,
simple, under K2000" returns a curated handful with reasoning. This is genuinely valuable and is
where pgvector pays off — but only build it once you have the data to ground it. Q67 (AI
features prioritised: descriptions → fraud → pricing) and the Bootstrap-Reality tension in your
Master Plan get this right.
7.3 Hyperlocal proximity for Class C
Class C goods (fresh produce, charcoal, river sand) are extremely sensitive to distance — nobody buys
tomatoes from 40km away. For commodity listings, the geo re-ranking weight should be 2–3x what it is
for Class A. Implementation is just a per-class multiplier on the existing distance score; no new
infrastructure.

## Page 13

Convergeo · Product Strategy · 13 8. Comprehensive Product Catalogue for Zambia
This is the products universe Convergeo's data model must absorb. Organised by department, with each
sub-category mapped to a product class (Section 2), pricing mode (Section 3), and notes on Zambian
context — including which categories tend to be import-heavy, regulator-bound, or high-fraud. Phase 1
launch picks live in Section 9.

Department Sub-category Class Pricing mode Zambian context
Food: Groceries &
Staples
Mealie meal & maize
products
B
(variants)
Per-unit per pack
size
Sun, Olympic, Antelope
brands. 5/10/25/50kg
packs. Foundational SKU.
Food: Groceries &
Staples
Cooking oil B
(variants)
Per-unit per
bottle size
Sunfoil, Cargill, Pure &
Sasko. Heavily price-
sensitive.
Food: Groceries &
Staples
Sugar & salt B Per-unit Zambia Sugar dominant
locally.
Food: Groceries &
Staples
Rice, beans, kapenta,
dried fish
C / B Per-kg or per-
pack
Mix of branded packs and
weighed bulk. Kapenta is
iconic; multi-grade.
Food: Groceries &
Staples
Bread, biscuits, snacks A / B Per-unit Manda, Bakers Inn. Daily
fresh; logistics-sensitive.
Food: Groceries &
Staples
Soft drinks, juices, water A / B Per-unit / per-
case
Coca-Cola, Castle, Kachasu
products. Returnable
bottles complicate stock.
Food: Groceries &
Staples
Tea, coffee, beverages A / B Per-unit Tata Tea, local mosi-
coffee. Mostly imported.
Food: Groceries &
Staples
Condiments & sauces A / B Per-unit Royco, Knorr, locally
bottled hot sauces.
Food: Groceries &
Staples
Baby food & formula A / B Per-unit ZAMRA-adjacent
regulation; Tier 2/3 only.
Food: Fresh &
Perishable
Fresh vegetables C Per-bunch / per-
heap / per-kg
Soweto, City Market
vendors. Very short shelf
life. Same-day fulfilment
only.
Food: Fresh &
Perishable
Fresh fruit C Per-piece / per-kg Mango, banana, paw-paw,
citrus. Seasonal pricing.

## Page 14

Convergeo · Product Strategy · 14
Department Sub-category Class Pricing mode Zambian context
Food: Fresh &
Perishable
Fresh meat (beef, goat,
chicken)
C Per-kg Butchery cuts. Cold chain
required for delivery;
pickup-friendly.
Food: Fresh &
Perishable
Fresh fish C Per-kg / per-piece Bream, kapenta (fresh),
Lake Tanganyika supply.
Cold chain critical.
Food: Fresh &
Perishable
Eggs B Per-tray / per-
dozen
Tray pricing dominant.
Food: Fresh &
Perishable
Dairy (milk, yoghurt,
butter)
B Per-unit per pack Parmalat, Zammilk, Trade
Kings. Cold chain.
Food: Fresh &
Perishable
Frozen foods B Per-unit Imported frozen chicken,
chips, fish fingers.
Food: Prepared &
Specialty
Bakery custom (cakes,
etc.)
E Range / from Wedding cakes, kitchen-
party cakes. Made-to-
order.
Food: Prepared &
Specialty
Local artisan foods B / E Per-unit / quote Honey, peanut butter,
jams, indigenous teas —
emerging premium
category.
Food: Prepared &
Specialty
Restaurant takeaway
items
A Per-unit If platform supports food
delivery from Phase 2. See
services brief.
Beverages
(Alcoholic)
Beer (lager, dark, opaque) A / B Per-unit / per-
case
Mosi, Castle, Chibuku.
Liquor licensing applies;
delivery hours restricted.
Beverages
(Alcoholic)
Spirits & wine A / B Per-bottle Imported spirits dominant.
Tier 2/3 only; age
verification at delivery
mandatory.
Beverages
(Alcoholic)
Local brews (kachasu,
munkoyo)
C Per-litre / per-
bottle
Heavily informal; legal
complications; consider
Phase 3+.
Personal Care &
Beauty
Soap, shower gel, lotion A / B Per-unit Lifebuoy, Geisha, Vaseline.
High-volume daily.

## Page 15

Convergeo · Product Strategy · 15
Department Sub-category Class Pricing mode Zambian context
Personal Care &
Beauty
Toothpaste, deodorant A Per-unit Colgate, Close-Up. Brand-
loyal.
Personal Care &
Beauty
Hair care (relaxers, oils,
weaves)
A / B / D Per-unit / per-
piece
Dark & Lovely, Motions.
Weaves often unique-
listing (Class D).
Personal Care &
Beauty
Makeup & cosmetics A / B Per-unit High counterfeit risk. Tier
2+ vendors only. Brand-
protection program
needed.
Personal Care &
Beauty
Fragrances A Per-unit Counterfeit-heavy; same
controls.
Personal Care &
Beauty
Feminine hygiene A / B Per-unit Always, Cottex. Sensitive
packaging considerations.
Personal Care &
Beauty
Baby care (diapers,
wipes)
A / B Per-unit Pampers, Huggies. Bulk
discount common.
Health & Wellness OTC medications A Per-unit ZAMRA-licensed vendors
only. Hard restriction on
Tier 1. Prescription items
not on platform.
Health & Wellness Vitamins & supplements A Per-unit ZAMRA notification
required. Counterfeit-
watch.
Health & Wellness Medical devices (BP
monitors, etc.)
A Per-unit ZAMRA / HPCZ overlap.
Tier 2+.
Health & Wellness First aid & bandages A / B Per-unit Lower regulation; more
permissive.
Fashion & Apparel New clothing (men,
women, kids)
A / B Per-unit per size Imported retail (Mr Price,
Pep, Edgars-style). Size
variants critical.
Fashion & Apparel Chitenge fabric & ready-
made
B / D Per-piece / per-
metre
ZamPrint and others.
Fabric per-metre, ready-
made per-piece. Iconic
Zambian category.

## Page 16

Convergeo · Product Strategy · 16
Department Sub-category Class Pricing mode Zambian context
Fashion & Apparel Tailored / made-to-order
outfits
E Range / from Custom chitenge, suits,
wedding outfits. See
Section 6.5.
Fashion & Apparel Salaula (second-hand
clothing)
D Per-piece Massive informal
category. Each item
unique. Phase 2
onboarding.
Fashion & Apparel Footwear A / B / D Per-pair per size New (Class A/B), used
(Class D).
Fashion & Apparel Bags & accessories A / B / D Per-unit Local leather goods are a
real artisanal category.
Fashion & Apparel Jewellery (costume + fine) A / B / D Per-unit Fine jewellery: high fraud,
Tier 2+ only,
authentication evidence.
Electronics & Tech Smartphones (new) A / B Per-unit per
variant
Itel, Tecno dominate
budget. Samsung, iPhone
premium. Variants by
storage/colour.
Electronics & Tech Smartphones (used /
refurb)
D Per-unit Huge category. IMEI
evidence mandatory.
Refurb tier.
Electronics & Tech Phone accessories (cases,
chargers)
A / B Per-unit Counterfeit-heavy; brand-
protection useful.
Electronics & Tech Laptops & desktops A / D Per-unit New retail + huge
used/import market from
Dubai routes.
Electronics & Tech TVs & home audio A / B Per-unit Hisense, Samsung, LG
dominant.
Electronics & Tech Small home appliances A / B Per-unit Kettles, irons, fans.
Branded SKUs.
Electronics & Tech Solar panels & inverters A / B Per-unit / per-kit Booming category given
load-shedding. ERB
regulation for installers
(services side).

## Page 17

Convergeo · Product Strategy · 17
Department Sub-category Class Pricing mode Zambian context
Electronics & Tech Generators & UPS A / B Per-unit Same driver as solar.
Honda, Lutian, brand-
name + generic.
Electronics & Tech Gaming & cameras A Per-unit Smaller market but high-
margin. Counterfeit-watch
on cameras.
Home & Living Furniture (new) A / B / E Per-unit / quote Home-grown carpenters
(Class E) + imported
branded (Class A/B).
Heavy-logistics.
Home & Living Furniture (used) D Per-unit Each piece unique.
Home & Living Mattresses & bedding A / B Per-unit per size Vitafoam-style local +
imports.
Home & Living Cookware & kitchenware A / B Per-unit Branded (Tefal, etc.) +
generic enamel ware
which is Class B/C.
Home & Living Cleaning supplies A / B Per-unit Boom, Sunlight, Surf. High-
volume.
Home & Living Curtains, mats, decor B / D / E Per-unit / quote Mix of off-the-shelf and
made-to-order.
Home & Living Garden & outdoor A / B Per-unit Tools, seeds for home
gardens, planters.
Building & Hardware Cement B Per-bag (50kg
standard)
Lafarge / Mpande / Sino.
Bulk discounts essential.
Heavy logistics.
Building & Hardware Iron sheets, roofing B / C Per-sheet / per-
metre
Pricing per sheet by gauge.
Bulk B2B core.
Building & Hardware Steel rebar, wire mesh C Per-kg / per-piece Construction-grade.
Quote-friendly for large
orders.
Building & Hardware Bricks, blocks, sand, stone C Per-thousand /
per-tonne
Hyper-local; transport cost
dominates.
Building & Hardware Paint B Per-litre per pack
size
Plascon, Crown. Colour
variants matter.

## Page 18

Convergeo · Product Strategy · 18
Department Sub-category Class Pricing mode Zambian context
Building & Hardware Plumbing fittings A / B Per-unit Pipes by length (Class C-
ish).
Building & Hardware Electrical fittings & cable A / B / C Per-unit / per-
metre
Cable per metre is Class C.
Building & Hardware Tools (hand & power) A / B Per-unit Bosch, Stanley + cheap
imports.
Building & Hardware Doors, windows, frames B / E Per-unit / quote Standard sizes Class B;
custom Class E.
Automotive Parts &
Supplies
New auto parts A / B Per-unit OEM and aftermarket.
Critical to surface
compatibility data.
Automotive Parts &
Supplies
Used auto parts D Per-unit Each piece unique. Photos

- condition mandatory.
  Automotive Parts &
  Supplies
  Tyres & batteries A / B Per-unit per size Size variants critical (R14,
  R15, R16, etc.).
  Automotive Parts &
  Supplies
  Engine oil & fluids A / B Per-unit per pack Castrol, Total. Counterfeit
  risk.
  Automotive Parts &
  Supplies
  Used vehicles D Per-unit
  (negotiable)
  Japan-import dealers.
  Each car unique. VIN +
  mileage evidence
  mandatory.
  Automotive Parts &
  Supplies
  Vehicle accessories A / B / D Per-unit Stereos, mats, tints — mix.
  Agriculture & Inputs Hybrid maize seed A / B Per-pack Pannar, Seed Co,
  Zamseed. FISP-relevant.
  Seasonal demand spike.
  Agriculture & Inputs Vegetable & legume seed A / B Per-pack Smaller volume; more
  variety.
  Agriculture & Inputs Fertiliser (D-Compound,
  Urea)
  B Per-bag (50kg) Critical staple. Heavy
  logistics. Subsidy-aware
  pricing.
  Agriculture & Inputs Pesticides & herbicides A / B Per-unit ZEMA registration. Tier 2+
  only.

## Page 19

Convergeo · Product Strategy · 19
Department Sub-category Class Pricing mode Zambian context
Agriculture & Inputs Animal feed B Per-bag Layers mash, broiler
starter, pig pellets.
Volume category.
Agriculture & Inputs Day-old chicks & livestock B / D Per-bird / per-
head
Live animals. Vet
certification. Local pickup
only.
Agriculture & Inputs Veterinary medicines A / B Per-unit Vet Council regulation.
Agriculture & Inputs Farm tools (manual) A / B Per-unit Hoes, ploughs, machetes.
Agriculture & Inputs Irrigation kits & pumps A / B Per-unit / per-kit Solar irrigation booming.
Office & Stationery Stationery (pens, paper,
files)
A / B Per-unit / per-
pack
School-season demand
spike.
Office & Stationery Printers & cartridges A / B Per-unit Compatible-cartridge
fraud common; brand
controls.
Office & Stationery Office furniture A / B / E Per-unit / quote Bulk B2B opportunity.
Office & Stationery School supplies A / B Per-unit / per-
pack
Heavy seasonal.
Office & Stationery Books (textbooks, novels) A / D Per-unit Used textbooks Class D.
Toys, Hobby & Sport Children's toys A / B Per-unit Mostly imported.
Toys, Hobby & Sport Sports equipment A / B Per-unit Football, netball gear.
Branded + generic.
Toys, Hobby & Sport Bicycles & scooters A / B / D Per-unit New + used. Used:
condition photos
mandatory.
Toys, Hobby & Sport Musical instruments A / D Per-unit Heavy used market.
Toys, Hobby & Sport Art & craft supplies A / B Per-unit Smaller niche.
Crafts & Cultural Curios, carvings, baskets D Per-piece Tourist-driven. Each piece
unique. Class D listing.
Crafts & Cultural Pottery & ceramics D Per-piece Local artisans.
Crafts & Cultural Beadwork & jewellery D / B Per-piece Mix of one-off (D) and
small-batch (B).

## Page 20

Convergeo · Product Strategy · 20
Department Sub-category Class Pricing mode Zambian context
Crafts & Cultural Local art / paintings D Per-piece Each unique.
Pets Pet food A / B Per-unit per pack Royal Canin, IAMS
premium; local mass-
market.
Pets Pet accessories A / B / D Per-unit Collars, beds, toys.
Pets Live pets D Per-animal Vet certification. Local
pickup only. Phase 3+.
Digital Goods E-vouchers & gift cards A Per-unit
(denomination)
Mobile money top-up,
retail vouchers.
Digital Goods Software licenses A Per-unit Niche but feasible.
Digital Goods Event tickets A Per-unit (tier-
priced)
Already in your roadmap;
dynamic QR (Q50). Sits in
product taxonomy with
class=ticket flag.
Digital Goods Online courses & e-books A Per-unit Expand from Phase 3.

That's roughly 100 product sub-categories across 13 departments. Combined with the ~110 service sub-
categories from the previous brief, Convergeo's data model needs to cleanly absorb 200+ supply types
from across both halves of the platform. The five product classes plus the six service archetypes give you
exactly that — eleven behavioural patterns, one underlying schema.

## Page 21

Convergeo · Product Strategy · 21 9. Phased Product Launch (Aligned to the 60-Day
Roadmap)
Your roadmap reaches public launch on Day 60 with a target of 75–100 active vendors and at least 5
products each. This section maps which product departments those first vendors should come from, and
which categories wait.
Phase 1 — Launch (Days 1–60, weeks 6–8 onboarding)
Eight product departments. Pick vendors who already have stable supply, photograph well, and can fulfil
reliably. The goal is depth in a few areas, not thinness across all.
• Food: Groceries & Staples — mealie meal, oil, rice, sugar, beverages. Highest repeat-purchase
frequency, builds habit.
• Personal Care & Beauty — soap, lotion, hair care. Tier 2+ for makeup; skip fragrances at launch.
• Fashion & Apparel — chitenge fabric and ready-made; new clothing from formal retailers. Skip
salaula at launch (Class D complexity).
• Electronics & Tech (selective) — new phones (Itel, Tecno), accessories, small appliances, solar
kits. Skip used phones at launch.
• Home & Living — kitchenware, cleaning supplies, branded furniture. Skip used furniture and
made-to-order.
• Office & Stationery — pens, paper, school supplies. Easy supply, good for school-season
campaign.
• Building & Hardware (light) — paint, hand tools, small fittings. Skip cement / sand / heavy
categories at launch (logistics not ready).
• Event tickets — already in your Day 49–53 plan.
Phase 2 — Commerce deepening (Months 3–6 post-launch)
Add classes that need more catalogue maturity, more vendor trust history, or heavier logistics:
• Class C produce (fresh vegetables, fruit, fish, meat) — needs same-day fulfilment. Pilot in Lusaka
first.
• Class D used phones, used laptops, used furniture, salaula — needs the condition + evidence +
dispute-handling system fully battle-tested.
• Heavy building materials — cement, iron sheets, sand, blocks. Needs vendor-managed delivery
(your Q45 hybrid logistics) and bulk-pricing UI.
• Agriculture inputs — seasonal but huge: time the rollout to the September–November planting
window.

## Page 22

Convergeo · Product Strategy · 22
• Used vehicles — VIN/mileage evidence flow, longer escrow, possibly even-longer dispute
window.
Phase 3 — Long tail and specialised (Months 6–12)
• Class E made-to-order — tailoring, custom cakes, custom signage. Template flow + spec form.
• Pharmaceuticals (OTC), supplements — only with ZAMRA-licensed vendors and authentication
program.
• Crafts & cultural curios — feeds the tourism/city-guides angle (Q52).
• Live animals, alcoholic beverages with delivery, regulated specialty goods — last because
regulation cost is highest.
• AI assistant for product discovery ("ask" mode) — once you have ≥10K transactions to ground
recommendations on.

## Page 23

Convergeo · Product Strategy · 23 10. Pulling It Together
Your existing decisions handle the e-commerce mechanics — escrow, payments, ranking, search,
comparison. This brief sharpens the catalogue itself: how products are classified, how they're priced,
how stock is counted, how vendors add them, and which to launch when.
The five things to take away:
• Products fall into five classes (A: branded SKU, B: branded variant, C: commodity, D: unique, E:
made-to-order). Your canonical Product / VendorListing schema works for all five if you add a
product_class enum and allow product_id to be NULL for D and E.
• Pricing has six modes, not one. Per-weight, per-bunch, tiered, range, and quote-only have to
coexist with per-unit fixed from day one — even if only per-unit is exposed in the UI at launch.
• Condition is a controlled enum with evidence requirements. This is what makes used goods (a
huge Zambian category) safe to transact and what makes the dispute system tractable.
• Five vendor onboarding flows map to the five classes. Search-and-attach is the default and is the
platform's largest vendor-acquisition lever — protect it by curating a strong canonical catalogue
early.
• Phase 1 picks eight product departments where supply is stable and logistics are simple. Class C,
D, and E categories — and the messier regulated ones — wait until the trust and operations
layers are battle-tested.
Combined with the services brief, Convergeo now has a coherent model for absorbing essentially any
kind of supply Zambia produces: 11 behavioural patterns (5 product classes + 6 service archetypes),
200+ sub-categories, one schema, one search layer, one trust system. That is the actual moat.

End of brief.
