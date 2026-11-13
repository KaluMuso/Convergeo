# Agents 1 + 4 — Logistics Strategy, Decision Engine, Pricing, Architecture and Simulation

**Scope:** brief sections 1, 3 (Models A–F), 4, 5, 7, 10, 11, plus the founder's three added principles. Read-only assessment, 13 Nov 2026. Nothing in any repository, database, configuration or workflow was changed.

**Grounding:** pilot release candidate at `/home/claude/wt-logistics-audit` (read only), `docs/ops/lusaka-delivery-reference-prices.md`, and the sibling reports `agent3-systems-audit.md` (systems) and `agent5-zambia-research.md` (operators, fuel). Where those reports already cover a topic I point to them instead of repeating it.

**Labels used on every number:** **[S]** sourced (repo, cited URL or sibling report) · **[A]** editable assumption of mine · **[D]** derived by arithmetic or simulation from [S] and [A] inputs. No Zambian courier or parcel tariff is presented as fact; Agent 5 found none published.

---

## 0. Verdict in one page

**Recommended model: "sell a priced promise, bind the fulfilment method late".** A hybrid, asset-light network in which Convergeo owns the promise, the price, the data and the exceptions, and rents every vehicle. Concretely:

1. **Checkout sells a service level** (window + price), never a vehicle or a route. The fulfilment method is chosen after the order exists, as late as the promise allows. This is the founder's principle 1 and it is right; the code is already half-way there (`orders` versus `dispatch_requests`).
2. **Delivery cost is shown before checkout** (product page and cart), computed from the vendor's location to the customer's area. This is principle 2 and it is the largest single lever in the whole study: in the brief's own three-vendor example the Matero leg is 57% of the courier cost [D], and the only thing that removes it is the customer choosing a nearer offer before paying.
3. **Capacity is bought in three forms, switched by volume:** per-job partner couriers (now), time-chartered wave riders (from roughly 10 wave-eligible orders a day), and collection points / depot injection (when a corridor or a cluster justifies it). No owned fleet (principle 3).

**Where I disagree with the brief:**

| Founder assumption | Finding | Evidence |
|---|---|---|
| The core problem is route inefficiency, to be solved by an intelligent engine. | At pilot volume the binding problems are **pricing and density**, not routing. A solver cannot batch orders that do not exist at the same time and place. | Volume simulation §6.8: under per-job courier pricing, city-wide batching saves about 1% at 5 orders/day and 6% at 20/day [D]. |
| Grouping orders geographically cuts cost substantially. | True for **one-to-many** flows (one origin, many drops) and for **same-address** multi-vendor checkouts. Weak for **many-to-many** (scattered vendors to scattered customers) while couriers are paid per job, because a per-job price already hides the courier's idle time and empty running. The saving appears when Convergeo buys rider **time** in blocks. | §6.8: chartered wave riders save 32% at 20/day and 39% at 80/day versus per-job; selective per-job batching saves 6% and 15% [D]. |
| Hubs where one driver collects and another delivers will reduce distance. | A cross-dock adds a leg and a handling event. In the three-vendor example it costs **more** than three separate trips (K185 vs K158 [D]). The hub that pays is a **vendor drop-off / customer collection point** and an **intercity injection point**. | §6.3, §6.4, §6.6. Jumia runs exactly this: sellers drop off or pay for pickup; most pickup stations are third-party owned ([Jumia seller guidelines](https://sellercenter.jumia.ug/delivery_guidelines), [TechCabal](https://techcabal.com/2025/11/18/jumias-asset-light-network-kenya/)). |
| Offer Express, Standard, Scheduled, Economy, Consolidated, Collection, Intercity. | Seven concepts is the engine's vocabulary, not the customer's. Show **at most three choices** at checkout on a 360 px screen. "Consolidated" is not a choice; it is how a multi-vendor cart is priced. "Intercity" is not a choice; it is what the destination implies. | §4.2. |
| AI should decide fulfilment. | Every dispatch decision here is a rule or a small optimisation. AI earns its place in three narrow spots: resolving free-text landmarks, matching equivalent products across vendors, and reading couriers' free-text replies. | §3.6. |
| Free delivery above K200 (current config). | Unaffordable. Commission on a K200 order is K10–K20 [S: `commission_rates` 5–10%]; the delivery it gives away costs K28–K90 [D]. And today the fee that *is* charged is paid out to the vendor (Agent 3, D1). | §4.4. |

**Sequencing rule:** each stage is unlocked by a measured trigger, not by a date (§2.3).

---

## 1. What the repository does today (only what the design depends on)

Verified by reading the code; details and file paths are in Agent 3's audit.

| Fact | Where | Consequence for this design |
|---|---|---|
| One checkout produces one `orders` row per vendor; one `dispatch_requests` row per order; nothing regroups them. | `services/orders/create.py`, `services/dispatch/service.py` | A three-vendor checkout is three unrelated courier jobs, three handover codes, three COD collections. |
| Delivery zone = customer's haversine distance from a CBD point (≤5 km A K30, ≤12 km B K45, ≤25 km C K65). **Vendor location is not an input.** | `routers/checkout.py::resolve_delivery_zone` | Matero→Kabulonga (15.4 road km [D]) and Woodlands→Kabulonga (4.3 road km [D]) both charge K30. |
| Fee is charged **per vendor group**; waived per group at subtotal ≥ K200. | `compute_group_delivery_fee_ngwee`, `platform_config.free_delivery_threshold_ngwee` | Customer over-pays on multi-vendor carts (3 × fee) while Convergeo under-recovers on long legs. |
| Courier cost per zone exists as an optional quote (`courier_partner_zones.price_ngwee` → `dispatch_requests.quoted_price_ngwee`); no actual cost. | migration `20261109100000_courier_dispatch_v1.sql` | Delivery margin cannot be computed. |
| Vendor locations carry mandatory `lat`/`lng` and an `hours` jsonb; customer addresses carry a mandatory landmark and optional `lat`/`lng`. | `0002_identity_vendors.sql`, `0005_orders.sql` | Vendor-to-area distance pricing needs no new data from vendors. |
| No parcel size, weight, handling class or preparation time on listings; `fulfilment_mode` (stocked / made_to_order) and `lead_time_days` exist. | `0085_product_classes.sql` | The promise engine can already split "ready now" from "made to order"; size and perishability need one small enum each. |
| Guarded state machines with CAS, audit triggers and an outbox with dedupe keys; n8n calls token-guarded `/internal/*` tick endpoints. | `services/dispatch/state.py`, `services/notifications/dedupe.py`, `routers/internal_dispatch.py` | The right automation pattern already exists; extend it, do not replace it. |
| Production API host is a Hetzner CX23 (2 vCPU / 4 GB) [S: Agent 3 §0]; no PostGIS. | — | Solvers and routing engines must be sized for that box. |

---

## 2. Strategy: the models, alone and combined

### 2.1 What the reference companies actually do, and what transfers

| Company | Mechanism | Evidence | Transfers to Zambia? |
|---|---|---|---|
| **Jumia** | Sellers hand over at a drop-off point, or pay for a pickup add-on; the seller prints Jumia's label; a handover receipt is the custody record. | [Seller delivery guidelines](https://sellercenter.jumia.ug/delivery_guidelines) [S] | **Yes, directly.** Pushing first mile onto the vendor is the cheapest consolidation there is. Vendors who already travel to town daily do it at near-zero marginal cost. |
| **Jumia** | 300+ pickup stations in Kenya, over 80% owned and run by third parties; 60% of deliveries go to secondary towns and villages. | [TechCabal, 18 Nov 2025](https://techcabal.com/2025/11/18/jumias-asset-light-network-kenya/) [S] | **Yes, later.** Partner-operated collection points are the upcountry model. Commission paid to agents is not published; negotiate locally. |
| **Takealot** | Paid delivery below a free threshold that has been **raised repeatedly** (R500 → R650 in Oct 2024; a Sept 2026 headline reports R750); R200 per-item surcharge for bulky goods. | [BusinessTech, 7 Oct 2024](https://businesstech.co.za/news/trending/794156/bad-news-for-takealot-delivery-fees-in-south-africa/) [S]; [EWN headline, 2 Sep 2026](https://www.ewn.co.za/2026/09/02/takealot-raises-minimum-spend-for-free-delivery-to-r750) [S, headline only] | **The lesson transfers:** even at Takealot's density, the free threshold sits at many multiples of the delivery fee (R650 vs R75, about 8.7× [D]). Convergeo's K200 vs K30 is 6.7× on a far thinner margin and with no density. |
| **Takealot** | 100+ pickup points, 30 inside Pick n Pay stores; 14,000 collections a month at those. | [Pick n Pay investor release](https://picknpayinvestor.co.za/media/takealot-expands-pickup-points-at-pick-n-pay-as-shoppers-flock-to-convenient-collection-option) [S] | **Yes:** host points inside existing retail (a vendor's own shop first, then a supermarket, fuel station or mobile-money booth). |
| **Amazon** | "Amazon Day": the customer picks a delivery day, orders are combined; about 20% fewer boxes in 2024; a small credit rewards the slower choice. | [About Amazon](https://www.aboutamazon.com/news/operations/what-is-amazon-day-delivery) [S] | **Yes, as a pattern:** pay the customer a little to wait, and consolidation follows. This is Model C. |
| **Uber Eats** | Batches of 2–3 orders, from one merchant or two; limited when delivery time would be significantly extended; more common at peaks. | [Uber, 27 Feb 2023](https://www.uber.com/au/en/blog/triple-batching-for-restaurants) [S] | **The limits transfer:** even the most data-rich on-demand network stacks only 2–3 and mostly same-merchant. That is the ceiling for Model F. |
| Amazon/Takealot fulfilment centres, Alibaba/Cainiao sortation, DHL hub networks, Lazada sort centres | Inventory or parcels pass through owned or contracted sort facilities. | General industry knowledge; **not researched or cited here**. | **No, not now.** These need volume that fills a trunk vehicle daily. Revisit above roughly 300 orders/day or for the Lusaka–Copperbelt corridor. |

### 2.2 Models A–F: independent verdicts

| Model | Verdict | Why | Cost to build | Viable from |
|---|---|---|---|---|
| **A. Nearby-vendor recommendation** | **Adopt, reframed as "landed-price comparison".** Never "substitution". | Removes distance instead of optimising it. The canonical catalogue with vendor listings and comparison already exists, so "same product, three offers, each with item price + delivery to *your area* + arrival time" is a ranking change, not a new system. Zero operating cost; works at one order a day. | Low | Day one |
| **B. Multi-order batching** | **Adopt in three narrow forms; do not build general batching yet.** (1) Same checkout, same address → one multi-pickup run. (2) Same vendor or vendors within about 1 km → stacked pickups. (3) Cluster batching inside scheduled waves. | Forms 1 and 2 are certain savings found by a SQL `GROUP BY`. Form 3 only pays with chartered riders and volume (§6.8). | Low (1, 2); medium (3) | 1–2: day one. 3: ~10+ wave orders/day |
| **C. Scheduled / time-window** | **Adopt now. It is the mechanism that creates density.** | A cut-off and a window cost nothing to promise and turn a trickle of orders into a batch. Standard same-day with two cut-offs is also simply more honest than an implied "now" with manual dispatch. | Low | Day one |
| **D. Collection / drop-off points** | **Adopt the cheap half; defer the cross-dock.** Now: collect-from-vendor (exists). Next: 3–5 partner points used for customer collection, vendor drop-off, failed-delivery holding and returns. Later: sortation. | A point that removes a leg saves money; a point that adds a leg costs money (§6.3). Points also solve the "customer not home" and COD-refusal problems that batching makes worse. | Medium (custody scanning, partner payout) | ~40+ orders/day or first clear cluster |
| **E. Third-party intercity** | **Adopt as a manual, prepaid-only, depot-to-depot lane.** | Agent 5: no operator API, no published parcel tariff, and "Platinum" / "TownStar" could not be verified. The design must assume a human at a depot counter and a waybill photo. | Low–medium (manual adapter, carrier rate table) | First paid upcountry order; formalise at ~5/week per corridor |
| **F. Perishables / time-critical** | **Separate lane with hard rules; keep it narrow at pilot.** Dedicated or same-vendor stack of 2, short radius, no holds, no hubs, no intercity. Chilled/frozen and medicines: not until packaging and legal position are settled. | Uber's own ceiling is 2–3 stacked ([source](https://www.uber.com/au/en/blog/triple-batching-for-restaurants)); Agent 5 flags undefined liability on bus parcels. Spoilage liability dwarfs any routing saving. | Low (rules) | Day one for hot food / flowers within radius, if such vendors are onboarded |

### 2.3 The hybrid, staged by measured triggers

| Stage | Trigger to enter [A, tune with data] | Capacity | Planning | Customer choices |
|---|---|---|---|---|
| **0 — Honest economics** | Now | Per-job partner couriers (dispatch v1) | Ops board + consignment grouping | Standard same-day window · Collect from vendor |
| **1 — Waves** | ≥10 wave-eligible delivered orders/day for 2 weeks, or ≥3 parcels per wave on most days | Add 1–2 chartered riders for fixed blocks; per-job for Express and overflow | Greedy insertion planner, two cut-offs | + Express where available · + Economy (next wave / next day) |
| **2 — Points and solver** | ≥40 wave-eligible/day, or ≥2 riders per wave, or one area with ≥8 drops/day | Sector riders; 3–5 partner points; daily depot run for intercity | OR-Tools PDPTW for waves; area distance matrix | + Collect from a point |
| **3 — Network** | ≥300/day or a corridor with ≥20 parcels/day | Cross-dock, courier APIs where verified, destination-town partners | Forecasting, rider link with GPS, re-planning | unchanged |

**Viability by volume** (courier cost per delivered order, illustrative, from §6.8):

| Model | Low (≤10/day) | Medium (20–80/day) | High (160+/day) |
|---|---|---|---|
| Per-job dedicated | Only practical option; about K52 [D] | Baseline K52–53 [D] | Baseline |
| A. Landed-price comparison | **Best lever** (cuts km at source) | Best lever | Best lever |
| B. Same-checkout / same-vendor consolidation | Works whenever it occurs | Works | Works |
| B. Cross-customer batching, per-job pricing | 1–3% saving: not worth building [D] | 6–15% [D] | 20–25% [D] |
| C. Waves with chartered riders | **Loses** money at 5/day (K61 vs K52); breaks even near 7–10/day [D] | **32–39% saving** [D] | 41–45% [D] |
| D. Customer collection at vendor | Free | Free | Free |
| D. Partner points (one-to-many last mile) | Not justified | K26–37 per order incl. K5 handling, if vendors drop off [D] | Strong |
| D. Cross-dock sortation | No | No | Evaluate |
| E. Depot-to-depot intercity | Manual, per order | Daily depot run | Corridor contracts |
| F. Dedicated perishable | Yes, short radius | + same-vendor stack of 2 | + zone-based riders |

---

## 3. Decision engine

Design rule: **deterministic first**. The engine is a set of pure functions over data that already exists plus four small new attributes. It runs at three moments: quote (cart / checkout), plan (cut-off or readiness), and exception.

### 3.1 Inputs and where they come from

| Input (brief §4 number) | Source today | Gap |
|---|---|---|
| Customer location (1) | `addresses.landmark` (+ optional lat/lng) | Area picker and optional pin (§4.5) |
| Vendor locations, inter-vendor distance, distance to customer (2–4) | `vendor_locations.lat/lng` [S] | None. Haversine × 1.4 circuity now [S: reference doc says 1.3–1.5]; area matrix later |
| Parcels, size, weight (5–6) | — | `size_class` S/M/L/XL/bulky per listing, defaulted by category. Exact weight is **not** needed for motorbike-versus-car decisions |
| Category / handling (7, 17) | category, `product_class`, `fulfilment_mode` [S] | `handling_class`: ambient / fragile / hot_food / chilled / frozen / flowers / restricted |
| Vendor prep time (8) | `lead_time_days` for made-to-order only | `prep_minutes` per location (default 30), plus a "ready" state for delivery orders (Agent 3, A2) |
| Urgency, chosen option (9, 16) | — | `service_level` on the checkout group / order |
| Driver availability, capacity, existing routes (10–12) | `courier_partners` (companies) | Stage 1: runs and chartered blocks. Before that, assume per-job capacity is available and alert on stale requests (exists) |
| Provider availability (13) | `courier_partner_zones` | Carrier services table for intercity (manual) |
| Cost, time, margin (14, 15, 18) | band fee only | Quote snapshot with estimated cost (§4, §5.2) |

### 3.2 Step 1 — classify each vendor order (at quote time)

```
lane(order):
  destination outside the Lusaka service area            -> INTERCITY
  any item handling_class in {chilled, frozen, restricted}-> NOT_OFFERED (pilot)   # vendor self-delivery or collect only
  any item handling_class in {hot_food, flowers}          -> PERISHABLE
  any item size_class == bulky                            -> BULKY                 # car/van courier, quoted
  otherwise                                               -> PARCEL
```

### 3.3 Step 2 — which service levels may be offered (feasibility, not preference)

All thresholds are [A] defaults held in `platform_config`.

| Lane | Offer | Promise | Conditions |
|---|---|---|---|
| PARCEL | **Standard** | Ordered and vendor-ready before 11:00 → by 15:00; before 15:00 → by 19:00; otherwise next day by 13:00 | Vendor open; item stocked |
| PARCEL | **Express** | Within 120 min of vendor ready | Vendor→customer ≤ 12 road km; vendor confirms ready ≤ 30 min; between 08:00 and 17:30; per-job courier reachable |
| PARCEL | **Economy** (Stage 1+) | Next wave or next day, whichever is later | Not perishable; customer accepts the window |
| PARCEL / BULKY | **Collect** | From vendor location (exists) or partner point (Stage 2) | Always offered; always the cheapest |
| PERISHABLE | **Express only** | Within 60 min of ready (hot food), 120 min (flowers) | Vendor→customer ≤ 6 road km (hot) / 12 km (flowers); else collect only. Prepaid, or COD only for customers with ≥1 completed order |
| BULKY | **Standard, quoted** | Same windows | Car/van class; R-per-item style surcharge as Takealot does ([source](https://businesstech.co.za/news/trending/794156/bad-news-for-takealot-delivery-fees-in-south-africa/)) |
| INTERCITY | **Depot collection** | Days, by corridor | Prepaid only; declared value ≤ cap; no perishable, no fragile without vendor packing declaration |
| Made-to-order | Any of the above, clock starts at ready | `lead_time_days` shown | — |

A mixed cart is classified per vendor order, then combined in step 3.

### 3.4 Step 3 — form consignments and pick the method (at plan time)

A **consignment** is everything going to one address in one promise window. It is the unit the customer experiences (one arrival, one handover code, one COD payment).

```
for each checkout:
  group vendor orders by (address, service_level, promise_window)        -> candidate consignments
  for each candidate with >1 vendor order:
     ready_spread = max(ready_at) - min(ready_at)
     if ready_spread <= SPLIT_SPREAD (90 min Standard, 20 min Express)   -> keep together: one multi-pickup run
     else:
        if customer chose "deliver together" (default for Standard/Economy and all COD) and
           latest ready_at still meets the promise                       -> keep together, hold the early parcels at the vendor
        else                                                             -> split: ready parcels now, late parcel in its own consignment
                                                                            (customer was shown and accepted the extra fee at checkout)

for each consignment, choose the method by lane and level:
  PERISHABLE                 -> DEDICATED per-job now.
                                Stack with another PERISHABLE consignment only if: same vendor or vendors <= 1 km apart,
                                both ready within 5 min, second drop ETA <= its promise, stack size <= 2.
  Express (PARCEL)           -> DEDICATED per-job; multi-pickup if the consignment has several vendors.
                                Hold <= 10 min for a same-vendor second order; never more.
  Standard / Economy         -> WAVE if a chartered block exists for that cut-off, else per-job (batched only if rule 3.5 passes).
  Collect                    -> no transport; issue a collection token (exists for vendor pickup).
  INTERCITY                  -> DEPOT RUN to the carrier chosen by 3.5.4, then carrier, then destination collection.
  any method fails (no courier accepts within SLA, rider cancels) -> escalate one level up in cost
                                (WAVE -> per-job -> ops call), never down in promise.
```

**Never-rules (hard constraints, not costs):** a perishable or Express parcel is never held for batching beyond the limits above; a parcel never changes rider without a custody scan; a rider never carries more COD cash than `COD_FLOAT_CAP`; an intercity parcel is never handed to a carrier unpaid.

### 3.5 Batching, holds, detours, batch size, hand-off

**3.5.1 When is waiting worth it?** Do not estimate this per order. Use **fixed cut-offs**; the hold is the time to the next cut-off and the customer agreed to it at checkout. Inside a wave the only question is membership:

```
add order o to run r  iff
   marginal_cost(r + o) <= BATCH_GAIN * dedicated_cost(o)      # BATCH_GAIN = 0.85 [A]
   and every stop in r + o still meets its promise
   and capacity, cash and duration limits hold
otherwise o travels as its own per-job dispatch
```

This "selective batching" rule can never cost more than dedicated delivery; it is the rule simulated in §6.8.

**3.5.2 Limits [A defaults]:**

| Limit | Motorbike | Car / small van | Reason |
|---|---|---|---|
| Parcels per run | 6 (S/M only; L counts as 2) | 12; bulky allowed | Box volume |
| Run duration | ≤ 180 min | ≤ 240 min | Promise window is 4 h cut-off to delivery |
| Added in-vehicle time per already-loaded Express parcel | ≤ min(20 min, 40% of its direct time) | same | Experience |
| Perishable stack | 2 | 2 | Quality |
| COD cash carried at once | ≤ K3,000 until remitted | same | Theft and reconciliation exposure; **in a COD-first market this, not volume, often caps batch size** |
| Pickup wait at vendor | 10 min, then skip and re-queue the order; vendor is flagged | same | Protects the other parcels on the run |

**3.5.3 Sequencing:** up to 6 stops, enumerate; up to about 12 stops, cheapest insertion with pickup-before-drop precedence (the 60-line routine used in §6); beyond that, OR-Tools (§3.7).

**3.5.4 Intercity hand-off:**

```
carrier = cheapest active carrier_service serving the destination town
          with reliability_score >= floor and next departure such that
          (depot cut-off - now) >= first-mile time + 30 min
first mile:  >= 3 intercity parcels today -> one consolidated depot run before the earliest cut-off
             else per-job to depot, or vendor drop-off at the depot (vendor paid a fixed credit)
custody:     Convergeo waybill number on the parcel; photo of the carrier's receipt uploaded by rider (proof of hand-off);
             customer receives carrier name, waybill, destination depot, expected arrival
arrival:     customer collects with ID + waybill; status closed by customer confirmation or depot photo;
             no confirmation by ETA + 24 h -> exception to ops
payment:     prepaid only; escrow release on confirmed collection
```

`reliability_score` starts at a neutral prior and is updated from Convergeo's own shipments. No public reliability data exists (Agent 5, §6).

### 3.6 Rules, optimisation, AI — who decides what

| Decision | Mechanism | Why |
|---|---|---|
| Lane, feasibility, promise window, never-rules | **Rules** | Legal, safety and trust constraints must be explainable and testable |
| Price and subsidy | **Formula** with versioned parameters | Auditable money (§4) |
| Consignment grouping, same-vendor stacking | **Rules** (group-by) | Exact and trivial |
| Wave membership and sequence, ≤ ~10 orders | **Greedy insertion** | Within a few percent of optimal at this size; milliseconds |
| Wave planning, > ~10 orders or ≥ 2 riders | **Optimisation** (OR-Tools PDPTW) | Assignment across riders is where heuristics start to lose real money |
| Carrier choice | **Rules** + score | Tiny option set |
| Prep-time and ETA estimates | **Statistics** (median / EWMA per vendor, per area pair), later gradient boosting | Needs a few thousand deliveries before a model beats a median |
| Demand forecast per area and hour | **Statistics**, Stage 3 | Sizes chartered blocks |
| Free-text landmark → delivery area | **AI (LLM, constrained to the known area list), human confirm on low confidence** | Today an unmatched landmark silently becomes Band B (and can be another town: Agent 3, C2). Metric: fallback-zone hit rate, wrong-zone rate |
| "Is this the same product?" for Model A | **AI offline**: pgvector similarity (index exists) + LLM spec check, written to the canonical catalogue; never at request time | Metric: precision of suggested equivalents on a hand-labelled sample ≥ 95% before showing customers |
| Courier / vendor free-text WhatsApp replies → suggested status | **AI suggests, ops confirms** | Metric: ops minutes per dispatch. No state change without a human click or a code |
| Daily exception digest | **AI summarisation** | Convenience only |
| Routing, assignment, pricing, state transitions, money | **Never AI** | Cheaper, faster and auditable without it |

### 3.7 Where optimisation algorithms pay off

- **Problem type.** Convergeo's wave is a Pickup-and-Delivery Problem with Time Windows and capacities (PDPTW). OR-Tools models it directly: `AddPickupAndDelivery`, same-vehicle and precedence constraints, time and capacity dimensions ([pickup/delivery](https://developers.google.com/optimization/routing/pickup_delivery), [time windows](https://developers.google.com/optimization/routing/vrptw)) [S]. VROOM is an alternative that pairs with OSRM ([repository](https://github.com/VROOM-Project/vroom); listed, not evaluated here).
- **Pay-off threshold [A].** Assume a solver beats greedy insertion by 5–10% of run kilometres. At K5.5/km and about 7 km per order that is K2–K4 per order: K20–K40 a day at 10 wave orders, K110–K220 a day at 55. Below about 40 wave orders a day the gain is smaller than the noise from vendors being late. Above it, and especially once two or more riders share a wave, adopt it.
- **Dynamic re-optimisation** (re-planning live as orders arrive) needs rider positions. Not before a rider link with location exists (Stage 3).
- **Geospatial clustering** (H3, DBSCAN): not needed while Lusaka is described by about 50 named areas. Use area names as the cluster key; revisit for heat-maps.

---

## 4. Pricing engine

### 4.1 Principles

1. **Price what causes cost:** the vendor-to-customer road distance, the number of pickups, the size class, the urgency and the payment method. The customer's distance from the CBD is none of these.
2. **One formula, versioned parameters.** Every quote stores inputs, parameter version, estimated cost, fee and subsidy, so margin is known per order from day one.
3. **Estimated cost first, then price.** Price = cost estimate × (1 + margin) + risk reserve − funded subsidy, rounded up to K5.
4. **Subsidy is a budget drawn from commission (or the vendor), never a free-floating threshold.**

### 4.2 What the customer sees versus what the engine computes

| Engine concept (brief) | Shown at checkout as | When |
|---|---|---|
| Standard | "Today by 15:00 / 19:00 — K__" | Always (default) |
| Express | "Within 2 hours — K__" | Only when feasible |
| Economy | "Tomorrow — K__ (save K__)" | Stage 1+ |
| Collection | "Collect from [vendor / point] — Free / K__" | Always |
| Consolidated | Not a choice. The cart shows **one** delivery line for all vendors, plus "Add from shops already in your cart: no extra delivery" | Multi-vendor carts |
| Scheduled | Stage 2: a date picker on Standard/Economy | Later |
| Intercity | Replaces the list when the destination is outside Lusaka: "Collect at [depot], [town] in 2–3 days — K__" | By destination |

Maximum three rows on screen.

### 4.3 Cost model and per-option formulas

**Courier cost estimate** (per-job partner; parameters [A], calibrated in §6.1 to the only sourced Lusaka fares):

```
road_km(a,b)      = 1.4 x haversine(a,b)                       # later: area-pair matrix
c_job(km, stops)  = max(K25, K5 + K5.5 x km + K8 x max(0, stops - 2))
c_wave(order)     = chartered_block_cost x standalone_cost(order) / sum(standalone_cost in run)   # allocation
```

| Option | Estimated cost C | Customer price P | Notes |
|---|---|---|---|
| **Standard** | Stage 0: `c_job(km, 2)`. Stage 1+: blend `(1−β)·c_job + β·c_wave`, β = measured share of Standard orders that travelled in a wave | `ceil5(max(K30, C × 1.10 + R))` | R = failed-delivery reserve (below) |
| **Express** | `c_job(km, 2) × peak_factor` | `ceil5(max(K45, C × 1.25 + R))` | Higher margin pays for the capacity kept idle for it |
| **Economy** | `c_wave` at current fill | `P_standard − ceil5(0.6 × (C_standard − C_economy))` | Customer gets 60% of the saving [A]; Convergeo keeps 40% |
| **Consolidated (multi-vendor, one address)** | `c_job(tour_km, pickups + 1)` on the best pickup sequence | `ceil5(C × 1.10 + R)`, shown as one line and **never more than the sum of the separate Standard fees** | Cart shows each vendor's marginal contribution so the customer can drop the expensive leg |
| **Collection at vendor** | 0 | 0 | — |
| **Collection at partner point** | point fee + share of the wave that feeds it | `ceil5(C × 1.10)`, floor K10 | Stage 2 |
| **Intercity** | first-mile share + carrier tariff (rate table, from depot quotes) + handling + optional destination last mile | `ceil5(first_mile + tariff × 1.05 + K handling)` | Tariff is pass-through; no margin on a number Convergeo cannot control yet |
| **Bulky / special handling** | car/van `c_job` with its own parameters | `P + surcharge(size_class, handling_class)` | — |

**Risk reserve:** `R = p_fail × (0.5 × C + reattempt_cost_not_recovered) + cod_cost`, with `p_fail` the measured first-attempt failure rate for that payment method (start 8% COD, 3% prepaid [A]) and `cod_cost` the cash handling and remittance cost per COD order (start K3 [A]). In practice this is K3–K8 per order and is the reason a small **prepaid discount** is justified.

**Per-option delivery contribution (stored per order):**

```
CM_delivery = P_customer + vendor_funded + platform_subsidy_transfer
              − C_courier_actual − C_point − C_carrier − C_cod − C_failed_attempts
CM_order    = commission − payment_fees + CM_delivery − platform_subsidy_transfer
Offer rule  : show an option only if expected CM_order >= CM_FLOOR      # default K0; promo campaigns may set a negative floor with a budget
```

### 4.4 Subsidy logic

**The current rule cannot hold.** Commission rates are 3–12%, 8% default [S: `0008_config.sql`]. Free delivery at K200 gives away K28–K90 of courier cost against K10–K20 of commission [D].

**Replace the threshold with a funded budget:**

```
subsidy_budget(order) = σ × commission(order)                     # σ = 0.5 [A]
delivery_discount     = min(P_customer, subsidy_budget + vendor_funded + campaign_funded)
```

Implied "free delivery" basket for a K40 delivery [D]: at 5% commission K1,600; at 8% K1,000; at 10% K800. Below that the customer sees a partial discount ("K8 off delivery"), which is still a conversion message.

Three subsidies that are worth paying, each with its own budget line and KPI:

| Subsidy | Rule | Why it pays |
|---|---|---|
| **Consolidation nudge** | Second and later vendors in a cart are charged only their marginal run cost; if a suggested nearer offer is accepted, share 50% of the saving as a discount | The saving is real and is created by the customer's choice |
| **Prepaid nudge** | K5 off delivery for mobile-money prepayment | Removes cash risk, refusal risk and the COD float cap on batching |
| **First order** | Free Standard delivery on the first order, capped at band D2, funded by marketing, hard monthly budget | Acquisition; measurable against repeat rate |

Vendor-funded free delivery (vendor opts in; deducted from payout) is the standard marketplace way to keep "free delivery" badges without the platform paying.

**Before any of this: the fee must reach Convergeo.** Agent 3 (D1) found the delivery fee is included in the vendor's release gross. Until that is fixed every delivered order loses the full courier cost regardless of pricing.

### 4.5 Minimum inputs for an accurate quote

| # | Input | Status |
|---|---|---|
| 1 | **Customer delivery area** (one of ~50 named areas; optional GPS pin) | Free-text landmark today. Add an area picker fed by the existing keyword list; ask once and remember it so product pages can quote |
| 2 | **Vendor location** lat/lng for each cart line | Exists |
| 3 | **Size class** per line (S/M/L/XL/bulky) | New enum, category default |
| 4 | **Handling class** per line | New enum, category default |
| 5 | **Service level** | New |
| 6 | **Payment method** (COD / prepaid) | Exists |
| 7 | **Cart subtotal and commission rate** (for the subsidy budget) | Exists |
| 8 | **Vendor readiness** (open now? prep minutes, lead days) | `hours` and `lead_time_days` exist; `prep_minutes` new |

Not needed to quote: exact weight and dimensions, exact road distance, rider availability, traffic.

A cheap, accurate source for input 1: ask the customer to **share a WhatsApp location pin**. The platform is already WhatsApp-native, a pin gives exact coordinates at no map-API cost, and the same pin is what the rider navigates to. (Verify the inbound location message type on the Cloud API account before relying on it.)

**Proposed distance bands (replace the CBD-radial test, keep the fee table) [A]:** D1 ≤ 4 road km K30 · D2 ≤ 8 km K45 · D3 ≤ 13 km K65 · D4 ≤ 20 km K95 · beyond: quoted or collect. Each fee is roughly the modelled per-job cost at the band midpoint plus 10–15% [D]. The first three reuse today's K30/K45/K65 so the change is to the *resolver* (vendor→customer instead of customer→CBD), not to the price list customers have seen.

---

## 5. Architecture that fits the existing stack

Stack as verified by Agent 3: FastAPI on a Hetzner CX23 (2 vCPU / 4 GB), Supabase Postgres (no PostGIS yet), n8n, three Next.js apps on Vercel, budget about $50/month.

### 5.1 Shape

```
Next.js (customer / vendor / admin)
        |  quote, choose level, track            | ready, handover            | board, plan, exceptions
        v                                         v                            v
FastAPI  services/logistics/        (all state, all money, all decisions)
   quote.py      pure function: cart + area + params -> options, cost estimate, fee, subsidy
   promise.py    cut-offs, windows, feasibility rules (3.2, 3.3)
   consign.py    consignment grouping (3.4)
   planner.py    wave membership + sequencing: v1 insertion, v2 OR-Tools
   carriers.py   manual adapters (intercity), reuse courier_partners
   costing.py    actual cost capture, allocation, savings attribution (section 7)
   existing: services/dispatch (state machine, handover codes), notifications outbox, ledger
        |
        v
Supabase Postgres   source of truth: orders, consignments, runs, stops, quotes, events, ledger
        ^
        |  HTTPS + shared token, idempotency key per tick
n8n     timers and human-facing plumbing only
```

### 5.2 Data: reuse first (aligned with Agent 3 §E4)

| Need | Reuse | Add (all additive) |
|---|---|---|
| Fulfilment order | `orders` | `service_level`, `promised_from/by`, `ready_at`, `consignment_id` |
| Customer-level delivery | `checkout_groups` + `address_id` | `delivery_consignments` (address, window, level, status, handover code owner) |
| Leg per order | `dispatch_requests` | `run_id`, `actual_cost_ngwee`, `allocated_cost_ngwee`, `baseline_cost_ngwee`, `direction` |
| Trip | — | `delivery_runs` (partner/rider, kind per_job / charter / depot, planned/actual cost, km, baseline and naive cost) and `delivery_run_stops` (seq, kind, location, eta, arrived/departed) |
| Price rules | `delivery_zones` (as fee bands), `platform_config` | `delivery_areas` (name, aliases, centroid, sector); `delivery_quotes` (inputs, rule version, estimated cost, fee, subsidy; referenced by the checkout group) |
| Listings | `vendor_listings` | `size_class`, `handling_class` |
| Vendor readiness | `vendor_locations.hours` | `prep_minutes`, optional `dropoff_capable` |
| Intercity | `courier_partners` (+ `kind`) | `carrier_services` (origin depot, destination town, cut-off, tariff by size, reliability), `transport_bookings` (waybill, receipt photo) |
| Events | `notification_outbox`, `dispatch_request_events` | `logistics_events` outbox (aggregate, type, seq, payload; unique on aggregate + type + seq) |
| Exceptions | `failure_reason` text | `delivery_exceptions` (type, owner, cost, resolution) |

### 5.3 Backend versus n8n

| Belongs in FastAPI + Postgres (transactional, audited) | Belongs in n8n (may fail or repeat without harm) |
|---|---|
| Quote, fee, subsidy, promise | Cron: call `POST /internal/logistics/tick/plan-wave` at each cut-off |
| Order, consignment, dispatch and run state transitions | Cron every 5 min: `…/tick/sla-watch` (stale requested / accepted-not-collected / collected-not-delivered) |
| Wave planning and rider assignment | Vendor "is it ready?" reminders; customer "arriving" messages (API enqueues to the outbox, n8n or the existing dispatcher sends) |
| Handover-code verification, custody records | Courier and carrier messages; depot-run briefing |
| COD receivable, courier payable, ledger postings | Daily COD cash-up report, daily KPI digest, weekly margin report |
| Exception creation and escalation level | Paging ops on an exception; opening a human task |

Rule: **n8n never decides and never holds the only copy of anything.** It wakes the API up and carries messages. If n8n is down for a day, no state is wrong; things are merely late, and the admin board has a "run now" button for each tick. Agent 3 notes n8n workflow activation is unverified; a missed-tick heartbeat alert (the existing uptime monitor pattern) should guard the two critical ticks.

### 5.4 Idempotency, retries, concurrency, recovery

| Risk | Control |
|---|---|
| Tick delivered twice / n8n retry | Each tick carries a deterministic key (`plan-wave:lusaka:2026-11-14T11:00`); stored unique; a repeat returns the stored result |
| Two planners at once | `pg_advisory_xact_lock` on the wave key; plan written in one transaction |
| Order planned into two runs | Partial unique index: one active run stop per dispatch request (same idea as the existing `dispatch_requests_one_active_per_order`) |
| Lost update on status | Existing compare-and-set transitions + guard triggers; extend to runs and consignments |
| Dispatch and order updated in separate transactions (Agent 3, C4.3) | One transaction per custody event, or a reconciler tick that repairs "dispatch delivered, order not" |
| Duplicate notifications | Existing outbox dedupe key, extended with the event sequence |
| Event consumer crash | Outbox rows claimed with `FOR UPDATE SKIP LOCKED`, visibility timeout, attempt counter, dead-letter after N tries into `delivery_exceptions` |
| Courier never answers | SLA watch escalates: re-notify → next courier → ops; each step is a recorded transition |
| Partial failure of a multi-vendor run | Stops are independent records; a skipped pickup re-queues that one order and the consignment is marked "partial" with the customer told |
| Planner gives a bad plan | Plans are `planned` until a human or rule releases them at Stage 1; store planner version and inputs for replay |

### 5.5 When to add PostGIS, OR-Tools, OSRM, H3 — and what each costs

| Tool | Add when | Why not sooner | Cost |
|---|---|---|---|
| **Haversine × 1.4 in Python/SQL** | Now (exists) | — | $0 |
| **Area-pair distance table** (~50 areas → ~1,225 pairs) | Stage 0–1 | Gives road distances for pricing with **no routing service running**: compute once offline, store in Postgres, correct from real trips | $0 |
| **PostGIS** | When areas become polygons, or "nearest point / vendors within X km" queries appear (Stage 1–2) | Centroid lookups do not need it | $0; listed Supabase extension ([docs](https://supabase.com/docs/guides/database/extensions/postgis)); one additive migration. pgRouting is also listed ([extensions](https://supabase.com/docs/guides/database/extensions)) but is not needed |
| **Greedy insertion planner** | Stage 1 | — | $0; ~100 lines |
| **OR-Tools** | ≥ ~40 wave orders/day or ≥ 2 riders per wave | Gain below operational noise (§3.7) | $0 licence; a `pip` dependency. Run it in a **separate worker container** on the same host with a 10–30 s limit, not in the API request path (Agent 3, E2). If the 4 GB host gets tight, a second small VM is the only new spend: a few euros a month [A — check current Hetzner price] |
| **OSRM** | When sequencing > ~10 stops, or when measured haversine error on fees exceeds ~20% | Needs the matrix more than live routing | $0 software. Memory scales with extract size: the project's figures for the full planet imply roughly 7× the `.pbf` to preprocess and 2× to serve [D from [OSRM wiki](https://github.com/Project-OSRM/osrm-backend/wiki/Disk-and-Memory-Requirements)]. A Zambia or Lusaka-only extract is small, so serving should fit beside the API; **preprocess off-box** and copy the files. The Zambia extract size could not be confirmed (Geofabrik page fetch was blocked) |
| **Traffic** | Not available in OSRM | Use time-of-day multipliers learned from own runs | $0 |
| **Commercial maps APIs** | Avoid in the request path | Paid per call; WhatsApp pins and the area table cover the need | Not costed here |
| **H3** | Analytics heat-maps only, Stage 3 | Not in Supabase's listed extensions ([extensions](https://supabase.com/docs/guides/database/extensions)); named areas are the natural grid for a landmark-addressed city | $0 as a Python library |

Net new monthly infrastructure cost through Stage 2: **$0**, with one optional small worker VM after that.

---

## 6. Financial and operational simulation

### 6.1 Editable assumptions

| Parameter | Value | Label | Basis |
|---|---|---|---|
| Current fee bands | K30 / K45 / K65; free ≥ K200 per vendor | **[S]** | repo |
| Commission | 3–12%, default 8% | **[S]** | `0008_config.sql` |
| Road circuity | 1.4 × straight line | **[S]** | reference doc: "typically 1.3–1.5×" |
| Area coordinates | approximate centroids, each within ~1 km of the reference doc's CBD distance | **[A]** | not surveyed |
| Per-job courier cost | `max(K25, K5 + K5.5/km)` | **[A]** | calibrated to secondary Yango **car** fares: CBD→Kabulonga K30–45, CBD→Chilenje K25–40, airport K80–120 (reference doc §2). Model gives K42, K44, K113. **No motorbike courier tariff exists publicly** (reference doc; Agent 5 §8) |
| Extra-stop fee in a multi-stop job | K8 per stop beyond two | **[A]** | none; sensitivity shown |
| Chartered rider | K60/hour including bike and fuel, 2-hour minimum block | **[A]** | none. An unverified blog cites rider salaries of K2,000–3,500/month (Agent 5 §8), which would make this conservative |
| Speed; pickup; drop | 22 km/h; 6 min; 5 min | **[A]** | — |
| Motorbike fuel use | 2.5 L/100 km | **[A]** | — |
| Petrol | K33.06/L (Nov 2026) | **[S]** | media citing ERB, via Agent 5 §7 |
| Partner point handling | K5/parcel | **[A]** | — |
| Intercity carrier tariff | **unknown — variable `X`** | — | Agent 5: no parcel tariff published anywhere |
| Proposed fee | `ceil5(cost × 1.10 + K3)` | **[A]** | §4.3 |

Fuel is shown for information; it is inside the courier's price, not added to it. Times are from vendor-ready. All results below are **[D]**: arithmetic on the table above, not observed costs. Replace the [A] rows with ten real courier quotes and every figure updates.

### 6.2 Scenario 1 — one vendor (Woodlands) → one customer (Kabulonga)

| Method | Road km | Trips / riders | Fuel L (K) | Courier cost | Time | Fee | Margin |
|---|---|---|---|---|---|---|---|
| Dedicated per-job, current fee | 4.3 | 1 / 1 | 0.11 (K4) | K28 | 23 min | K30 | **+K2** |
| Same, basket ≥ K200 (free today) | 4.3 | 1 / 1 | 0.11 | K28 | 23 min | K0 | **−K28** (commission at 8% of K200 = K16; order nets −K12) |
| Wave, chartered (at ~20 orders/day) | shared | shared | — | ≈ K19 | by window | K25 Economy | +K6 |
| Via a hub | longer | 2 | — | higher | slower | — | Not sensible |
| Collect from vendor | 0 | 0 | 0 | K0 | customer's time | K0 | K0 |

Reading: a single short order is fine on a dedicated rider. The loss is created by the free-delivery rule, not by logistics.

### 6.3 Scenario 2 — one customer (Kabulonga), three vendors (Woodlands, Chilenje, Matero)

| Method | Road km | Trips / riders | Fuel L (K) | Courier cost | Time to complete | Fee | Margin |
|---|---|---|---|---|---|---|---|
| **Today:** 3 dedicated jobs, 3 × Band A | 26.0 (4.3 + 6.3 + 15.4) | 3 / 3 | 0.65 (K21) | K158 (28 + 40 + 90) | 53 min, three arrivals | K90 | **−K68** |
| Today, each vendor group ≥ K200 | 26.0 | 3 / 3 | 0.65 | K158 | 53 min | K0 | **−K158** |
| One multi-pickup run (Matero → Woodlands → Chilenje → customer), per-job | 23.4 | 1 / 1 | 0.59 (K19) | K150 | 87 min, one arrival | K170 by formula | +K20 |
| Same run on a chartered rider already on shift | 23.4 | 1 / 1 | 0.59 | ≈ K87 (87 min × K60/h) | 87 min | K95–K125 | +K8 to +K38 |
| Hub: milk run to hub, then last mile | 25.3 | 2 / 2 | 0.63 (K21) | K185 (145 + 25 + 15 handling) | slower | — | Worse than doing nothing |
| Hub with **vendor drop-off** | 2.7 for Convergeo | 1 / 1 | 0.07 | K40 | next window | K45 | +K5 (vendors carry ~22 km themselves) |
| Hybrid: Woodlands + Chilenje in one run now; Matero separately | 23.1 | 2 / 2 | 0.58 | K146 (56 + 90) | 38 min + 53 min | — | — |
| **Model A:** Matero item bought from a vendor near the other two | 7.7 | 1 / 1 | 0.19 (K6) | **K56** | 38 min, one arrival | K65 | **+K9** |

Reading: consolidating into one run improves the experience (one arrival, one code, one cash payment) but saves only 5% of courier cost under per-job pricing, because the cross-town kilometres are still driven. The Matero leg alone is K90 of K158 (57%). The lever is the customer seeing "this item adds K95 delivery; the same item from a Woodlands shop adds K15" **before** checkout.

### 6.4 Scenario 3 — ten customers, five vendors, drops clustered in the east

Vendors: Woodlands, Chilenje, Matero, Northmead, Kabwata. Drops: Kabulonga ×2, Kalingalinga ×2, Roma ×2, Ibex Hill, Mtendere, Chelston, Rhodes Park.

| Method | Road km | Trips / riders | Fuel L (K) | Courier cost | Per order | Time | Fees (today) | Margin |
|---|---|---|---|---|---|---|---|---|
| 10 dedicated jobs | 81.2 | 10 / up to 10 | 2.03 (K67) | K497 | K50 | avg 33, max 49 min | K345 | **−K152** |
| 2 motorbike runs of 5, per-job | 52.4 | 2 / 2 | 1.31 (K43) | K394 | K39 | 126 and 103 min | K345 | −K49 |
| 1 car run of 10, per-job | 48.5 | 1 / 1 | — | K376 | K38 | 212 min | K345 | −K31 |
| 2 motorbike runs, **chartered** | 52.4 | 2 / 2 | 1.31 | ≈ K240 (2 × 2 h) | K24 | same | K345 | **+K105** |
| Hub: milk run in, one run out | 48.5 | 2 / 2 | 1.21 | K431 incl. K50 handling | K43 | ≈ 105 + 118 min | K345 | −K86 |
| Hub with vendor drop-off | 22.8 | 1 / 1 | 0.57 | K252 incl. handling | K25 | ≈ 118 min after cut-off | K345 | +K93 |

Reading: with a genuine cluster, batching cuts kilometres by 35% and per-job cost by 21%; buying the riders' time instead cuts cost by about half. The cross-dock version is again worse than plain batching unless vendors do the inbound leg.

### 6.5 Scenario 4 — perishables, four orders, 60-minute promise

Two food vendors (Kabulonga, Woodlands), two orders each.

| Method | Road km | Trips | Courier cost | Slowest delivery | Fees (today) | Margin |
|---|---|---|---|---|---|---|
| 4 dedicated | 14.5 | 4 | K107 | 23 min | K150 | +K43 |
| 2 same-vendor stacks of 2 | 10.4 | 2 | K84 | 30 min (second drops) | K150 | +K66 |
| Wave / hub / scheduled | — | — | — | breaks the promise | — | **Not permitted** |

Reading: same-vendor stacking saves 21% and keeps every delivery inside 30 minutes, but only because both orders were ready together. The rule in §3.4 (same vendor, ready within 5 minutes, stack of 2) captures this and nothing riskier.

### 6.6 Scenario 5 — intercity, Lusaka vendor (Matero) → Ndola or Livingstone

Distances: Ndola 321 km, Livingstone 472 km [S: Agent 5 §5]. Carrier parcel tariff `X`: **not published by any operator** [S: Agent 5]. Passenger fares (K140–230 Ndola, K200–350 Livingstone; secondary source) are context only and must not be used as parcel prices.

| Method | Lusaka first mile | Trunk | Destination | Convergeo cost | Time |
|---|---|---|---|---|---|
| Per-job rider to the depot | K62 (10.4 km) | `X_bus` | customer collects | K62 + `X_bus` | same or next day + collection |
| Daily consolidated depot run (4 intercity parcels) | K36 each (K144 run, 20.9 km) | `X_bus` | customer collects | K36 + `X_bus` | next departure after cut-off |
| Vendor drops at depot (paid a K15 credit [A]) | K15 | `X_bus` | customer collects | K15 + `X_bus` | vendor's schedule |
| + destination door delivery | as above | `X_bus` | local rider `Y` (unknown) | + `Y` | + hours |
| Door-to-door courier / postal EMS | — | `X_courier` | included | `X_courier` | Agent 5: 48 h domestic standard cited for EMS (secondary) |

Customer price: `ceil5(first_mile + 1.05 × X + K10 handling)`, prepaid only. Decision rule once quotes exist: use the bus depot lane while `first_mile + X_bus + K10 < X_courier`, and offer door delivery only in towns with a tested local partner. The first-mile share falls from K62 to K36 at four parcels a day and towards K15 with vendor drop-off; that is where Convergeo's own lever is.

### 6.7 Scenario 6 — mixed readiness (same checkout as Scenario 2; Matero item needs four hours)

| Method | Courier cost | Customer experience | Handovers / COD collections |
|---|---|---|---|
| Three dedicated jobs as each is ready | K158 | two parcels in ~30 min, third after ~5 h | 3 |
| Hold everything, one run | K150 (≈ K87 chartered) | everything at ~5.5 h | 1 |
| Split: two-vendor run now + dedicated later | K146 | ~40 min, then ~5 h | 2 |
| **Hybrid: two-vendor run now + late item on the evening wave** | ≈ K117 (56 + ≈ 61 wave allocation) | ~40 min, then evening window | 2 |
| Model A alternative for the late item | K56 | everything in ~40 min | 1 |

Reading: the engine's default (§3.4) is "together" when the latest item still meets the window, otherwise "split, with the late item on the next wave". The customer is shown both with prices at checkout; under COD, "together" is preferred because each extra handover is another cash event.

### 6.8 Volume model — when does each form of batching pay?

Monte-Carlo, 20–200 simulated days per row. Vendors and customers drawn at random around the CBD (mean vendor-to-customer distance about 6 km straight, 8.4 road km [A]); 70% of orders wave-eligible; two waves a day; six parcels per rider; cheapest-insertion routing; a batched run may not exceed 180 minutes.

| Orders/day | Wave-eligible | Dedicated K/order | Selective batching, per-job K/order (saving) | Share of orders batched | Chartered wave riders K/order (saving) |
|---|---|---|---|---|---|
| 5 | 3.6 | 52 | 51 (1%) | 7% | **61 (−17%)** |
| 10 | 6.9 | 52 | 51 (3%) | 15% | 42 (20%) |
| 20 | 14.0 | 53 | 50 (6%) | 30% | 36 (32%) |
| 40 | 28.1 | 53 | 47 (10%) | 43% | 33 (36%) |
| 80 | 57.0 | 53 | 45 (15%) | 59% | 32 (39%) |
| 160 | 114.2 | 52 | 42 (20%) | 72% | 31 (41%) |
| 320 | 223.9 | 53 | 40 (25%) | 78% | 29 (45%) |

Sensitivities: with no extra-stop fee, per-job batching saves 18% / 33% / 44% at 20 / 80 / 320 orders a day. If orders concentrate on 20 active vendors per wave, per-job batching saves 9% / 23% / 35% and chartered 33% / 42% / 48%. One-to-many delivery from a point where vendors have dropped parcels costs K42 / K37 / K31 per order per-job at 6 / 12 / 24 parcels, and K27 / K26 / K25 chartered, including K5 handling.

**What this says:**

1. **Below about ten orders a day, do not batch across customers and do not charter.** Chartering loses money (K61 versus K52) because the rider is paid to wait.
2. **The big step is commercial, not algorithmic:** moving from per-job to time-chartered riders once a wave reliably has three or more parcels. That step is worth about 30 points; a better routing algorithm on top is worth a few.
3. **Vendor concentration and one-to-many flows are what make batching work.** Both are things marketing and vendor operations can influence (featured local vendors; vendor drop-off).
4. The average per-job cost (≈ K52) is above every current fee band except C. With today's bands the pilot loses money on the average delivery **before** free delivery and before the fee-to-vendor issue.

---

## 7. KPIs and savings attribution

### 7.1 KPI set (brief §10), with starting targets [A]

| KPI | Definition | Pilot target | Stage 2 target |
|---|---|---|---|
| Delivery cost per order | Σ actual courier + point + carrier cost ÷ delivered orders | ≤ average fee | ≤ 0.85 × average fee |
| Cost per km; cost per parcel | actual cost ÷ planned road km; ÷ parcels | track | falling trend |
| Gross delivery margin | Σ `CM_delivery` ÷ Σ delivery fees | ≥ 0% | ≥ 10% |
| Subsidy rate | subsidy ÷ commission | ≤ 50% | ≤ 35% |
| Collection time | ready → collected (median, p90) | ≤ 45 / 90 min Standard | ≤ 30 / 60 |
| Delivery time | ready → delivered, by level | Express ≤ 120 min; perishable ≤ 60 | same, p90 |
| On-time % | delivered inside promised window | ≥ 90% | ≥ 95% |
| First-attempt failure % | failed or refused ÷ attempts, by payment method | ≤ 8% COD | ≤ 5% |
| Parcels per run; stops per run | — | n/a | ≥ 3; then ≥ 5 |
| Rider utilisation (chartered) | loaded minutes ÷ paid minutes | n/a | ≥ 60% |
| Distance per successful delivery | run km ÷ delivered parcels | track (≈ 8 km model) | ≤ 6 km |
| Empty return km | km after last drop of failed parcels returned | track | — |
| Vendor prep time; ready-on-time % | accepted → ready; ready by promised time | ≥ 85% on time | ≥ 92% |
| Rider wait at vendor | arrival → collected | median ≤ 10 min | ≤ 6 min |
| Orders consolidated | orders in multi-order consignments or runs ÷ delivery orders | track | ≥ 40% of wave-eligible |
| Savings from batching, routing, proximity, third party | §7.2 | report weekly | — |
| Third-party performance | per carrier: on-time departure, transit days, loss/damage, cost variance | score every carrier | — |
| Perishable compliance | delivered within promise ÷ perishable orders | ≥ 95% | ≥ 97% |
| COD integrity | cash remitted by T+1 ÷ cash collected; variance | 100%; K0 | same |
| Complaints, damage, returns | per 100 deliveries | ≤ 3 | ≤ 2 |
| Delivery satisfaction | one-tap WhatsApp rating after delivery | ≥ 4.3 / 5 | ≥ 4.5 |
| Quote accuracy | (actual − estimated cost) ÷ estimated | within ± 15% | within ± 10% |

Quote accuracy and subsidy rate are additions to the brief's list; they are what keep the pricing engine honest.

### 7.2 Separating the sources of savings

Store four cost figures at planning time, and one at completion. The differences are the attribution; no modelling after the fact.

| Stored figure | Meaning |
|---|---|
| `baseline_original` | per-job cost of each order from the vendor the customer **first** had in the cart, delivered alone |
| `baseline` | per-job cost of each order from the **final** vendor, delivered alone |
| `naive_cost` | cost of the actual grouping visited in arrival order (no sequencing) |
| `planned_cost` | cost of the plan actually issued |
| `actual_cost` | what was paid |

```
Vendor-proximity saving (Model A) = Σ baseline_original − Σ baseline        # only for carts where a nearer-offer suggestion was shown and accepted
Consolidation + batching saving   = Σ baseline − naive_cost                 # split by tag: same-checkout consignment vs cross-customer wave
Route-optimisation saving         = naive_cost − planned_cost
Capacity-model saving             = planned_cost at per-job rates − planned_cost at charter rates
Third-party / depot saving        = benchmark door-to-door quote − (first mile + carrier + handling)
Collection saving                 = Σ baseline of orders the customer chose to collect − point cost
Execution variance                = actual_cost − planned_cost              # late vendors, failed attempts, re-dispatch: a cost, reported separately
```

A shared run's cost is allocated to its orders in proportion to their standalone `baseline` (simple, stable, and never allocates more than the order would have cost alone when the batching rule in §3.5.1 is respected). The weekly report is a waterfall from "all orders dedicated" to "actual", one bar per line above.

---

## 8. Founder's three principles, assessed

| Principle | Assessment | Caveat |
|---|---|---|
| 1. Separate checkout from fulfilment | **Correct and already implied by the schema.** Formalise it: checkout stores a promise and a quote; fulfilment binds a method later. | The promise must be bounded by what can actually be delivered; every promise needs a fallback method one level up in cost. Under COD, splitting one checkout into several arrivals multiplies cash events, so "together" is the default. |
| 2. Cost-aware before checkout | **The highest-value item in this report.** Product page and cart must show item + delivery to the customer's area + arrival, per offer. | Needs the customer's area early (ask once, remember). Rank honestly: nearer is not better if the price difference exceeds the delivery saving; show both numbers. |
| 3. Hybrid network, not an owned fleet | **Correct.** | "Orchestration engine" at pilot scale is a rules module, a quote function and a board, perhaps 500 lines. Build the measuring instruments first; the optimiser is the last component to add, not the first. Keep at least two courier partners plus chartered riders so no single partner sets the price. |

---

### 8.1 Consistency with the sibling reports

| Sibling finding | Effect on this design |
|---|---|
| Agent 2 C05 / Agent 3 C1, D1: fee ignores vendor location, is charged per vendor, is waived at K200, and is paid out to the vendor | Same conclusion reached independently; it is priorities 1 and 2 below. Agent 2's working courier cost of K40–80 per Lusaka trip brackets this report's modelled average of about K52. |
| Agent 2 C01–C02, Z05, Z14, Z18–Z19: COD cash is not tracked per courier; float, change and collusion risks | Hence the K3,000 cash-carried cap as a hard batching constraint (§3.5.2), "together" as the COD default (§3.4), the prepaid nudge (§4.4) and prepaid-only intercity. Batching must not be switched on before per-courier cash custody exists. |
| Agent 2 C03 / Agent 3 C4.2: a failed attempt after pickup cannot be re-dispatched or returned | The engine's "escalate one level up" fallback (§3.4) and the failure reserve R (§4.3) both assume a re-attempt and a return leg exist. They are a precondition for waves, where one failed stop otherwise strands a parcel on a shared run. |
| Agent 2 C04: vendors can mark an order shipped with no dispatch | Vendor self-delivery should become an explicit, priced fulfilment choice (fee to the vendor, vendor's own proof), not a bypass; otherwise cost and on-time KPIs in §7 are blind to those orders. |
| Agent 2 C06 / Agent 3 C2: unmatched landmarks default to Band B, including other towns | The area picker and landmark resolution in §3.6 and §4.5 replace the fallback; out-of-area destinations route to the INTERCITY lane (§3.2) instead of being priced as Lusaka. |
| Agent 2 B05–B06, Z01, Z32: vendors late, offline or closed | Reason the plan clock starts at vendor-confirmed "ready", not at order time, and for the 10-minute wait-then-skip rule. |
| Agent 2 Z22 / Agent 3 C4.4: one operator is the single point for handover codes and dispatch | A tokenised rider link for code entry is the first automation worth more than any planner; without it, waves are capped by one person's attention. |
| Agent 3 E2: 2 vCPU / 4 GB host | Solver in a separate worker with a time limit; routing data precomputed (§5.5). |
| Agent 5: no APIs, no parcel tariffs, "Platinum" / "TownStar" unverified, petrol K33.06 | Manual carrier adapter and tariff variable `X` (§3.5.4, §6.6); fuel figure used in §6. |

---

## 9. Five highest-priority improvements

1. **Make delivery money real.** Stop paying the delivery fee out to vendors (Agent 3, D1), record actual courier cost on every dispatch, and store a quote snapshot with estimated cost. Without this nothing else can be measured.
2. **Price the leg that costs money.** Resolve the fee band from vendor-to-customer road distance instead of customer-to-CBD; charge one consolidated fee per address for multi-vendor carts; replace "free at K200" with a commission-funded delivery discount.
3. **Show landed price before checkout.** Area picker (and WhatsApp pin), delivery estimate on product page and cart, nearer-offer and "add from shops already in your cart" prompts. Never auto-substitute.
4. **Sell a window, group by address.** Two daily cut-offs for Standard, a "ready for collection" state for delivery orders, and a consignment record so one checkout to one address is one run, one handover code and one COD payment.
5. **Charter riders when the trigger is met, not before.** Track wave-eligible orders per day; at about ten, hire fixed blocks and turn on the insertion planner. Collect ten or more real courier quotes now so the cost model stops resting on car ride-hail fares.

---

## 10. Limits of this report

- No Zambian motorbike courier tariff, chartered-rider rate or intercity parcel tariff is published (reference doc; Agent 5). Every cost in §6 rests on a cost curve fitted to four secondary-source car ride-hail ranges. Directional conclusions (which method beats which, and at roughly what volume) are robust to the sensitivities shown; absolute kwacha figures are not.
- Area coordinates are approximate; the volume model assumes demand spread evenly around the CBD.
- The routing heuristic is cheapest insertion, so batched figures are slightly pessimistic.
- Not fetched or not verified: Geofabrik Zambia extract size (fetch blocked: `https://download.geofabrik.de/africa/zambia.html`); Jumia Q3 2025 results page (fetch failed); the EWN Takealot R750 item (headline only); VROOM (repository listed, not evaluated). Alibaba, DHL, Lazada and Bolt Food were not researched; statements about them are general knowledge and marked as such.
- "Platinum" and "TownStar" could not be verified as operators (Agent 5); Model E is designed for any depot-based carrier.
- Simulation scripts (not part of the repository): `/tmp/claude-0/-home-claude/ad6c43ff-0022-5f17-8a8e-13729d2e4861/scratchpad/sim.py` and `/tmp/claude-0/-home-claude/ad6c43ff-0022-5f17-8a8e-13729d2e4861/scratchpad/sim2.py`.

## 11. Sources

- Jumia seller delivery guidelines: https://sellercenter.jumia.ug/delivery_guidelines
- Jumia Kenya asset-light network (TechCabal, 18 Nov 2025): https://techcabal.com/2025/11/18/jumias-asset-light-network-kenya/
- Takealot delivery fees (BusinessTech, 7 Oct 2024): https://businesstech.co.za/news/trending/794156/bad-news-for-takealot-delivery-fees-in-south-africa/
- Takealot free-delivery threshold R750 (EWN, 2 Sep 2026, headline only): https://www.ewn.co.za/2026/09/02/takealot-raises-minimum-spend-for-free-delivery-to-r750
- Takealot pickup points at Pick n Pay: https://picknpayinvestor.co.za/media/takealot-expands-pickup-points-at-pick-n-pay-as-shoppers-flock-to-convenient-collection-option
- Amazon Day delivery: https://www.aboutamazon.com/news/operations/what-is-amazon-day-delivery
- Uber Eats batching (27 Feb 2023): https://www.uber.com/au/en/blog/triple-batching-for-restaurants
- OR-Tools pickups and deliveries: https://developers.google.com/optimization/routing/pickup_delivery
- OR-Tools time windows: https://developers.google.com/optimization/routing/vrptw
- OSRM disk and memory requirements: https://github.com/Project-OSRM/osrm-backend/wiki/Disk-and-Memory-Requirements
- Supabase extensions list and PostGIS: https://supabase.com/docs/guides/database/extensions · https://supabase.com/docs/guides/database/extensions/postgis
- VROOM (listed only): https://github.com/VROOM-Project/vroom
- Internal: `docs/ops/lusaka-delivery-reference-prices.md`; `/home/claude/logistics/agent3-systems-audit.md`; `/home/claude/logistics/agent5-zambia-research.md`
