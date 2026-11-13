# Convergeo Logistics Blueprint

**Lead-agent synthesis of four independent investigations · 13 November 2026 · read-only assessment**

Nothing in any repository, database, configuration or workflow was changed to produce this document. Nothing here should be built until the founder approves the list at the end.

**Inputs (all read in full):**

| Report | File |
|---|---|
| Agents 1 + 4: strategy, decision engine, pricing, architecture, simulation, KPIs | `/home/claude/logistics/agent1-4-strategy-architecture.md` |
| Agent 2: 60 failure scenarios and code defects C01–C16 | `/home/claude/logistics/agent2-failure-register.md` |
| Agent 3: codebase audit | `/home/claude/logistics/agent3-systems-audit.md` |
| Agent 5: Zambian operators, prices, fuel, distances, regulation | `/home/claude/logistics/agent5-zambia-research.md` |
| Code checked to settle disagreements | `/home/claude/wt-logistics-audit` (commit `a813f983`) and branch `fix/pilot-money-dispatch` |

**How numbers are labelled.** Every number carries one of three labels:

- **[S]** sourced: read from the code, or from a cited public source.
- **[A]** assumption: a starting value someone chose. Editable. Replace with real data.
- **[D]** derived: arithmetic on [S] and [A] inputs. It moves when the inputs move.

**Effort scale used throughout.** S = up to 2 working days for one implementer. M = 3 to 7 days. L = 2 to 4 weeks, several work packages.

**Status wording.** "In progress (pilot build)" means the fix is already being made on branch `fix/pilot-money-dispatch` for today's pilot build. It is not re-proposed here.

---

## 0. Executive summary (three-minute read)

### The recommended model, in plain language

**Sell the customer a priced delivery promise. Decide how to fulfil it afterwards. Own no vehicles.**

1. **At checkout the customer buys a promise**, for example "today by 19:00, K45". They do not buy a driver or a route. Convergeo picks the cheapest safe way to keep the promise after the order exists.
2. **The customer sees the delivery cost before checkout**, on the product page and in the cart, for each shop that sells the item. A blender from a shop 15 km away shows a higher delivered price than the same blender from a shop 4 km away. The customer chooses. Convergeo never swaps products on its own.
3. **Convergeo rents every vehicle.** Today: partner couriers paid per job. Later, when there are enough orders: riders hired by the hour for fixed delivery rounds. For other towns: existing bus and postal parcel counters.
4. **One delivery per address.** A checkout from three shops to one home becomes one rider visit, one handover code and one cash payment, not three.
5. **The "intelligent engine" is small for now.** It is a set of clear rules, one price formula and an operations board. A route-optimisation solver is added only when measured order volume justifies it.

### What the investigation found that changes the plan

| Finding | Why it matters |
|---|---|
| At pilot volume the problem is **pricing and order density**, not routing. | Batching orders across customers saves about 1% at 5 orders a day and about 6% at 20 a day [D]. A solver cannot combine orders that do not exist at the same time. |
| The biggest cost lever is **the customer choosing a nearer shop before paying**. | In the brief's own three-shop example, the Matero leg is K90 of K158 courier cost, 57% [D]. No routing removes it. A nearer offer does. |
| **Hubs where one driver drops and another collects cost more**, not less. | The three-shop example costs K185 through a hub against K158 as three separate trips [D]. Collection points pay only when vendors bring parcels to them, or customers collect from them. |
| **"Free delivery above K200" cannot be afforded.** | Commission on a K200 order is K6 to K24 [D from S: 3–12% rates]. The delivery it gives away costs K28 to K90 [D]. |
| **Cash handling is the largest operational risk.** | Before today's fixes, the system could lose track of cash-on-delivery money entirely. It still does not record which rider holds how much. |
| **No Zambian parcel carrier publishes prices or offers an API.** "Platinum" and "TownStar" could not be found under those names. | The intercity lane must be designed for a person at a depot counter and a photographed waybill. |
| **One person closes every delivery.** | Every handover code and every cash confirmation needs the founder, who also has a day job. This caps volume before anything else does. |

### The five decisions the founder must make

| # | Decision | Recommendation | If not decided |
|---|---|---|---|
| 1 | **Who pays for delivery?** End "free above K200 per shop". Price delivery on the shop-to-customer distance. Charge one fee per address. | Yes to all three. Until the new pricing is built, raise the free-delivery threshold in configuration so it stops triggering. | The average delivery loses money. Estimated per-job cost is about K52 against fees of K30 to K65 [D]. |
| 2 | **Cash-on-delivery rules.** Only Convergeo operations confirm cash. Riders remit by mobile money the same day. A cap on cash a courier may hold (start K1,500 [A]). A small discount for paying in advance. | Yes. Raise the cap to K3,000 only when named, hourly-hired riders exist. | Cash shortfalls cannot be traced to a person. |
| 3 | **The delivery promise.** Two daily cut-offs (order by 11:00, delivered by 15:00; order by 15:00, delivered by 19:00) instead of an implied "now". "Deliver everything together" as the default. No platform delivery of chilled, frozen, hot food or medicines yet. | Yes. Add Express later, where it is feasible. | Customers assume "now"; riders arrive before parcels are ready; orders cannot be grouped. |
| 4 | **People and partners.** Appoint a second operator with a limited "logistics" login. Sign written agreements with at least two courier companies. Decide whether shops may deliver with their own rider. | Yes to the first two. Allow shop self-delivery only as an explicit choice with its own proof of delivery. | One absent person stops all deliveries. One courier sets the price. |
| 5 | **Other towns.** Open a prepaid-only, depot-to-depot lane after test parcels have been sent. Supply the exact names and phone numbers of "Platinum" and "TownStar". Confirm the courier-licence and data-protection position with a lawyer. | Yes, after Phase 1. Budget for about 10 test parcels per corridor. | Upcountry orders stay collection-only, which is the safe current behaviour. |

### Top eight next actions

| # | Action | Who | Effort |
|---|---|---|---|
| 1 | Finish and ship the six money and dispatch fixes on `fix/pilot-money-dispatch`. | Build | In progress (pilot build) |
| 2 | Raise `free_delivery_threshold_ngwee` so free delivery stops triggering, until new pricing exists. A configuration change, no code. | Founder | S (minutes, after decision 1) |
| 3 | Record the real courier cost on every delivery and send a weekly fee-versus-cost report. | Build | S |
| 4 | Get ten or more real quotes: per-job motorbike prices across Lusaka, an hourly rider rate, and parcel prices at two bus depots and the post office. | Founder | About one week of calls and visits |
| 5 | Allow a second delivery attempt and a "returned to shop" step after a failed delivery, with stock put back. | Build | M |
| 6 | Add a limited "logistics operator" login, one combined "handed over and cash received" action, and alerts for silent shops and silent riders. Tell customers when an order is cancelled or delivered. | Build | M |
| 7 | Record which courier holds which cash, with a daily cash-up and the cash cap. | Build | M |
| 8 | Add a "ready for collection" step for shops, group the operations board by checkout and address, and send the rider to the branch that actually holds the stock. | Build | M |

The next items after these are the new price formula (M to L) and showing delivered price before checkout (L). Both are in the approval list at the end.

---

## 0.1 Where the agents disagreed, and the ruling

The four reports agree on the main direction. They disagree on details that affect what gets built. Each ruling says who was right and why.

| # | Disagreement | Ruling | Reason |
|---|---|---|---|
| R1 | **Where the API runs.** The brief and `CLAUDE.md` say an OCI virtual machine. Agent 3 says Hetzner. | **Agent 3 is right.** | `.github/workflows/deploy-production.yml` deploys the API to Hetzner [S, checked]. OCI is staging only. The machine is small (2 vCPU, 4 GB per Agent 3), so heavy route calculation must not run inside the API. `CLAUDE.md` and `infra/README.md` need a documentation correction. |
| R2 | **Commission range.** Agent 2 uses 5–12%. Agents 1+4 use 3–12%, default 8%. | **Agents 1+4 are right.** | `supabase/migrations/0008_config.sql` seeds supplies 3%, electronics and groceries 5%, default and home 8%, fashion 10%, services 12% [S, checked]. Lower commission makes free delivery even less affordable. |
| R3 | **How to fix multi-shop fees.** Agent 3: keep per-shop fees, add a flat reduced fee for the second and third shop. Agent 2: apply the free threshold per checkout. Agents 1+4: one fee per address, priced on the real pickup route. | **Agents 1+4 on the target. Agent 3 on the mechanics.** Agent 2's option is dropped. | Any free threshold is unaffordable at these commission rates, so moving it from "per shop" to "per checkout" fixes the wrong thing. Agent 3's interim fee would change customer prices twice in a few weeks. Go straight to one quote function. Agent 3's warning stands: the fulfilment step and order creation must call the same function (`validate_fulfilment_step` and `authoritative_vendor_groups`), or orders are refused. |
| R4 | **Alert timers for silent riders.** Agent 2: accepted over 60 min, picked up over 4 hours. Agent 3: 30 min and 120 min. | **Agent 3 for "picked up" (120 min). 45 min for "accepted".** All editable in configuration. | The longest Lusaka delivery band is 25 km. A rider holding goods and cash for four hours unnoticed is too long. 45 minutes for "accepted" matches the existing "requested" alert, so one setting covers both. |
| R5 | **Cash a courier may hold.** Agent 2: K1,500. Agents 1+4: K3,000. | **K1,500 now, K3,000 later.** Both [A]. | Today there is no rider identity and no remittance record. K1,500 is three maximum-size cash orders [D from S: K500 cap]. K3,000 fits a six-parcel round and is reasonable once riders are named and hired by the hour. |
| R6 | **Shop does not respond.** Agent 2: automatic cancel after 6 hours. Agent 3: alert operations only. | **Agent 3 for the pilot. Agent 2 from Phase 1.** | Cancelling automatically while the customer receives no cancellation message (defect C11) makes things worse. Add the customer message first, then the automatic cancel at close of business. |
| R7 | **How a second attempt works.** Agent 2 offers reopening the same delivery job. Agent 3 creates a new job on the same order. | **Agent 3 is right.** | A new record per attempt keeps "failed" final, gives each attempt its own audit trail and its own cost, and reuses the rule "one active job per order". Cap at two attempts (Agent 2). |
| R8 | **Hubs.** The brief proposes relay hubs. Agent 3 models them as platform-owned sites. Agents 1+4 show relay hubs cost more and recommend partner-run collection points. | **Agents 1+4 on the economics. Agent 3 on the data shape.** | Relay hubs add a trip and a handling step: K185 against K158, and K431 against K394 in the ten-order case [D]. No platform-owned hub. When points arrive (Phase 3) they get their own small table, which may point at a shop's existing location. They are not squeezed into `vendor_locations`. |
| R9 | **Rider identity.** Agent 2: full registry with national ID, vetting and ratings. Agent 3: a riders table. Agents 1+4: a one-time link per delivery. | **Small riders list plus a one-time link.** No ID numbers stored by Convergeo. No rider app. | The need is to know which person holds which parcel and cash. A name, phone and courier company do that. The courier company holds identity documents under its agreement. Storing national IDs adds data-protection duties without stopping more theft. |
| R10 | **When the customer gets the handover code.** Agent 2: only when the rider taps "arrived". Today it is sent at pickup. | **Agent 2 is right, but it depends on the rider link.** | "Arrived" needs a way for the rider to signal. Build it with the rider link in Phase 1. |
| R11 | **Use of AI.** Agents 1+4 propose AI for reading landmarks, matching equivalent products and reading courier messages. | **None of these now.** | An area picker removes the need to interpret free-text landmarks. The catalogue already links each shop's listing to one canonical product, so "same product, nearer shop" needs no AI. The rider link replaces free-text courier replies. Revisit AI in Phase 4 for suggesting similar (not identical) products, offline, with a measured accuracy bar. |
| R12 | **New database tables.** Agent 3 lists parcels, vehicles, service-level and pricing-rule tables. Agents 1+4 add a logistics event stream. | **Build fewer.** See Deliverable 7. | Parcels, vehicles, a service-level table, a pricing-rule table and a new event stream are not needed at this scale. A column or a configuration entry does the job. |
| R13 | **Part-filled shop orders** (shop has 2 of 3 items). Agent 3: build per-item status in Phase 1. Agent 2: "all or nothing" for now. | **Agent 2 for now.** | It touches the ledger and refunds. Build it in Phase 2 only if shops reject more than about 5% of orders [A] for "part out of stock". A checkout where some shops deliver and others do not is already supported. |
| R14 | **Hourly-hired riders save 32–39%.** This is Agents 1+4's largest saving. | **Direction accepted. The figure is not.** | It rests on K60 an hour, which has no source. Agent 5 found no published rate. Do not hire by the hour until a real quote exists and a delivery round reliably has three or more parcels. Break-even rule in Deliverable 9. |
| R15 | **Fraud hardening.** Agent 2 proposes photo GPS checks, duplicate-image detection, offline-verifiable codes, a USSD code channel, masked calls and cash deposits. | **Deferred.** | Sound ideas for hundreds of orders a day. At pilot scale use cheap equivalents: numbered seal bags, recipient name on the note, a photo at pickup, and a refusal history. |
| R16 | **Perishables from day one.** Agents 1+4: yes for hot food and flowers if such shops join. Agent 2: nothing in the system supports it. | **Agent 2 is right.** | There is no handling flag, no Express promise and no agreed liability for spoilage. Until Phase 2, perishable shops use customer collection or their own delivery. |
| R17 | **PostGIS, OR-Tools, OSRM** (tools the brief asks to be evaluated). | **Not yet.** Both technical reports agree. | Straight-line distance times 1.4 and a table of about 50 named areas are enough until roughly 40 scheduled orders a day. |

---

## Deliverable 1: Executive logistics strategy

### 1.1 The model

Convergeo runs an **asset-light hybrid**. It owns four things: the promise to the customer, the price, the data, and the handling of exceptions. It rents everything that moves.

| Layer | What Convergeo does | What it does not do |
|---|---|---|
| Before checkout | Shows item price plus delivery to the customer's area plus arrival time, for each shop offering the product. | Substitute products without the customer choosing. |
| At checkout | Sells a service level: a delivery window and a price. Up to three choices on screen. | Promise a vehicle, a rider or a route. |
| After checkout | Groups everything going to one address in one window into one consignment (one visit). Picks the method by rule. | Send three riders to one home. |
| Transport | Books partner couriers per job. Later hires riders by the hour for fixed rounds. Uses bus and postal counters for other towns. | Own vehicles or employ drivers. |
| Control | Records custody at each handover, the cash each courier holds, the real cost of each delivery. | Let a workflow tool or a WhatsApp thread be the only record. |

### 1.2 Why this model and not the one in the brief

The brief frames the problem as wasted driving, to be solved by an engine that plans routes. The evidence points elsewhere.

1. **There is not yet enough volume to batch.** The pilot expects 5 to 30 delivery orders a day [A, Agent 2]. Simulated across-customer batching at that volume saves 1% to 6% [D].
2. **Per-job courier prices already hide the courier's idle time.** Convergeo pays per delivery, so a cleverer route saves the courier money, not Convergeo. The saving reaches Convergeo only when it buys rider time by the hour.
3. **The money being lost today is lost by pricing rules, not by routes.** Free delivery above K200, fees that ignore where the shop is, three fees on one checkout, and (until today's fix) the fee being paid on to the shop.
4. **Reliability is limited by people and cash, not by algorithms.** One operator, no rider identity, no record of cash held.

### 1.3 The order of work

Each stage is unlocked by a measured trigger, not by a date. All triggers are [A] and should be tuned with real data.

| Stage | Enter when | Transport | Planning | Customer choices |
|---|---|---|---|---|
| **0. Honest economics** | Now | Partner couriers, per job | Operations board grouped by address | Standard window · Collect from shop |
| **1. Rounds** | 10 or more scheduled orders a day for two weeks, **and** three or more parcels in most rounds, **and** a real hourly rider quote | Add one or two riders hired for fixed blocks | Simple "add the next nearest stop" planner | + Express where feasible · + Economy (next round or next day) |
| **2. Points and solver** | 40 or more scheduled orders a day, or two or more riders per round, or one area with eight or more drops a day | Riders by sector · 3 to 5 partner collection points · daily depot run | Route solver (OR-Tools) in a separate worker | + Collect from a point |
| **3. Network** | 300 or more a day, or one corridor with 20 or more parcels a day | Sorting site, courier APIs where verified, partners in destination towns | Forecasting, live rider positions | Unchanged |

### 1.4 The founder's three principles, assessed

| Principle | Verdict | Caveat |
|---|---|---|
| Separate checkout from fulfilment | **Correct.** The database already half does this (`orders` versus `dispatch_requests`). | Every promise needs a fallback method that costs more, never one that delivers later. With cash on delivery, splitting a checkout into several visits multiplies cash events, so "together" is the default. |
| Show cost before checkout | **The highest-value item in the whole study.** | Needs the customer's area early. Ask once and remember it. Show both numbers honestly: a nearer shop is not better if its item price is higher by more than the delivery saving. |
| Hybrid network, no owned fleet | **Correct.** | Keep at least two courier partners so no single partner sets the price. |

### 1.5 Where the founder's assumptions were challenged

| Assumption in the brief | Finding |
|---|---|
| Grouping orders geographically cuts cost substantially. | True for one origin to many drops, and for one checkout to one address. Weak for scattered shops to scattered customers while couriers are paid per job. |
| Relay hubs reduce distance. | They add a trip and a handling step. They pay only when shops drop off or customers collect. |
| Offer seven delivery options. | Seven is the engine's vocabulary. Show at most three on a 360-pixel screen. "Consolidated" is how a multi-shop cart is priced, not a choice. "Intercity" is what the destination implies, not a choice. |
| AI should decide fulfilment. | Every dispatch decision is a rule or a small calculation. No AI is recommended before Phase 4 (ruling R11). |
| Platinum and TownStar can carry parcels. | Neither name could be verified as an operator [S: Agent 5]. The design works with any depot-based carrier. |

---

## Deliverable 2: Comparative assessment of Models A–F and the hybrid

Cost figures are per delivered order, illustrative, from Deliverable 9.

| Model | Verdict | Advantages | Disadvantages | Build effort | Operating cost | Scales? | Viable from |
|---|---|---|---|---|---|---|---|
| **A. Nearby-shop recommendation** | **Adopt, renamed "delivered-price comparison".** Never called substitution. | Removes distance instead of managing it. Works at one order a day. No operating cost. Uses the existing canonical catalogue. | Needs the customer's area before checkout. Only helps when two shops stock the same product. | L (touches product page, cart, search ranking) | None | Yes | Day one |
| **B. Multi-order batching** | **Adopt two simple forms now. Defer general batching.** (1) Same checkout, same address: one run. (2) Same shop or shops within about 1 km: stacked pickups. | Forms 1 and 2 are certain savings found by simple grouping. One visit, one code, one cash payment. | Across-customer batching saves 1–6% below 20 orders a day [D]. Cash held per rider caps batch size. One failed stop delays the rest. | S to M for forms 1 and 2. L for general batching. | None extra | Yes, with volume | Forms 1–2: day one. General: about 10+ scheduled orders a day |
| **C. Scheduled windows** | **Adopt now.** This is what creates density. | A cut-off costs nothing to promise. Turns a trickle into a batch. More honest than an implied "now". | Slower than instant for the customer. Needs shops to be ready on time. | M | None | Yes | Day one |
| **D. Collection and drop-off points** | **Adopt the cheap half. Reject the relay hub.** Now: collect from shop (exists). Phase 3: 3 to 5 partner points for customer collection, shop drop-off, failed-delivery holding and returns. | A point that removes a trip saves money. Solves "customer not home" and refused cash. | A point that adds a trip costs money. Needs custody scanning, partner pay and a liability agreement. | M to L | About K5 per parcel handling [A] | Yes | About 40+ orders a day, or the first clear cluster |
| **E. Third-party intercity** | **Adopt as a manual, prepaid-only, depot-to-depot lane.** | Uses networks that already run daily. No fleet. | No published prices, no API, no stated liability for any operator [S: Agent 5]. Status depends on photos and phone calls. | M | Carrier price unknown: variable `X` | Yes, by corridor | First paid upcountry order. Formalise at about 5 a week per corridor |
| **F. Perishables** | **Separate lane with hard rules. Not offered through platform delivery until Phase 2.** | Protects product quality and liability. | Needs a handling flag, an Express promise and agreed spoilage liability. None exist. | S for the rules, after Phase 1 attributes exist | Dedicated trips only | Narrowly | Phase 2 |
| **Hybrid (recommended)** | A + B(1,2) + C now. Hourly riders and Economy at Stage 1. D points and E formalised at Stage 2. | Each part is switched on when its trigger is met, so nothing is built before it pays. | Needs discipline to measure triggers honestly. | Phased | $0 new infrastructure through Stage 2 | Yes | Now |

**Viability by volume** (courier cost per delivered order [D]; per-job baseline about K52):

| Approach | Low: up to 10 a day | Medium: 20 to 80 a day | High: 160+ a day |
|---|---|---|---|
| Per-job dedicated courier | The only practical option. About K52. | Baseline, K52–53. | Baseline. |
| A. Delivered-price comparison | **Best lever.** | Best lever. | Best lever. |
| B. Same-checkout or same-shop grouping | Works whenever it occurs. | Works. | Works. |
| B. Across-customer batching, per-job pricing | 1–3% saving. Not worth building. | 6–15%. | 20–25%. |
| C. Rounds with hourly riders | **Loses money** at 5 a day (K61 against K52). Breaks even near 7–10 a day. | 32–39% saving, if the hourly rate assumption holds (ruling R14). | 41–45%. |
| D. Collect from shop | Free. | Free. | Free. |
| D. Partner points, shops drop off | Not justified. | K26–37 an order including handling. | Strong. |
| D. Relay hub with sorting | No. | No. | Evaluate. |
| E. Depot-to-depot intercity | Manual, per order. | Daily depot run. | Corridor contracts. |
| F. Dedicated perishable | Not offered. | Short radius, stack of two from one shop. | Riders by zone. |

---

## Deliverable 3: Failure-scenario register (consolidated and prioritised)

Agent 2 documented 60 scenarios (B01–B27 from the brief, Z01–Z33 specific to Zambia) and 16 code defects (C01–C16). The full text for each, with cause, consequence, prevention, detection and response, is in `/home/claude/logistics/agent2-failure-register.md`. This table groups them by the fix that resolves them, in priority order. Every ID appears at least once.

**Automation column:** *Auto* = a rule or scheduled check resolves it. *Auto+H* = the system detects and acts provisionally, a person confirms. *H* = a person must judge each case.

**Build status column:** *Exists* · *In progress (pilot build)* · *Proposed, Phase n*.

### Tier 1: fix during the pilot (money, stranded orders, single points of failure)

| Rank | Risk | IDs covered | What goes wrong | Fix | Automation | Build status |
|---|---|---|---|---|---|---|
| 1 | Cash on delivery is lost from the books | C01, B14 | A delivered cash order auto-completes after 48 hours and its cash can never be recorded. | Skip cash orders in auto-complete until the cash is booked. | Auto | **In progress (pilot build)** |
| 2 | Delivery fee paid on to the shop | C05 (part), Agent 3 D1 | Convergeo pays the rider and also hands the customer's fee to the shop. | Keep the fee as platform revenue. | Auto | **In progress (pilot build)** |
| 3 | Shop confirms cash it took itself | C02 (part), Z15 | The ledger believes Convergeo holds the cash and pays the shop a second time. | Only operations confirm cash. | Auto | **In progress (pilot build)** |
| 4 | Nobody knows which courier holds how much cash | C02 (rest), Z05, Z19, Z18 | Robbery, "borrowing", short remittance, no change, part-payment improvised at the door. | Record cash per courier; same-day mobile-money remittance; daily cash-up; cash cap K1,500 [A]; exact-amount message; "all or nothing" rule stated. | Auto, with H for any shortfall | Proposed, Phase 0 |
| 5 | One person closes every delivery | Z22, C09, Z02 | Deliveries stay open for hours; riders hold goods and cash; network failure at the gate blocks the code. | Limited logistics login; one combined "handed over + cash received" action; photo proof as fallback (exists); rider link in Phase 1. | Auto+H | Proposed, Phase 0 and 1 |
| 6 | A failed delivery cannot be retried or returned | C03, B09, B07, B10 | "Customer not home" becomes an off-system workaround. Stock is never put back. | New attempt on the same order (max two); "returned to shop" step with shop acknowledgement; restock on return; structured failure reasons; message asking the customer to choose re-delivery or collection. | Auto | Proposed, Phase 0 |
| 7 | Prepaid money released for undelivered goods | C03 (part), B19 | After seven days the shop is paid even if the delivery failed. | Exclude failed or missing deliveries from auto-release. | Auto | **In progress (pilot build)** |
| 8 | Other towns sold as a K45 Lusaka delivery | C06, B22, B08, Z03, Z04 | "Kabwe" or "Kafue" typed as a landmark is accepted as Band B. Wrong pins give wrong fees. | Full town list. Then an area picker and optional location pin; log every fallback; flag pins on the city-centre default point. | Auto | Town list: **in progress (pilot build)**. Picker: proposed, Phase 1 |
| 9 | Chain of custody can be bypassed | C04, C10, Z25, B27, B13, Z14 | A shop marks "shipped" with no courier job. Admin marks delivered without proof. The code reaches the customer before the rider does. No proof at pickup. | Block shop "ship" for platform deliveries. Require proof on admin override. Code released at "arrived". Shop-side pickup confirmation and seal number. | Auto | Shop-ship block: **in progress (pilot build)**. Rest: proposed, Phase 0 and 1 |
| 10 | Shop is silent; customer is not told | B06, B11, C11, Z01, Z32, B05, C08, B04 | Orders sit unconfirmed. Rejected orders produce no customer message. Riders arrive before the parcel is packed. Cancelled orders leave the courier uninformed. | Reminder at 1 hour, operations alert at 2 hours. Customer messages for "cancelled" and "delivered". "Ready for collection" step required before pickup. Cancelling an order cancels its courier job. Shop "away" switch. | Auto | Proposed, Phase 0 |
| 11 | Rider accepts, then goes silent | B12 | Goods and cash at risk with no alert. | Alerts at accepted over 45 min and picked up over 120 min [A]. | Auto, H for picked-up cases | Proposed, Phase 0 |
| 12 | Messages or scheduled jobs silently not running | Z21, C15, Z29 | WhatsApp templates not approved; workflows inactive; failures unnoticed. | Verify live template approval and workflow state. Error alert on every workflow. Heartbeat alert when a scheduled check is missed. | Auto | Proposed, Phase 0 (mostly verification) |
| 13 | Delivery priced below cost | C05 (rest), B01, Z26, B23, Z11 | Free delivery and shop-blind fees lose K28–K90 an order. Fuel changes monthly. | Record actual cost; weekly margin report; new price formula; exact total repeated in the confirmation message. | Auto report, H for pricing decisions | Cost recording: proposed, Phase 0. Formula: Phase 1 |

### Tier 2: fix in Phase 1 and 2 (grows with volume)

| Risk | IDs covered | Fix | Automation | Build status |
|---|---|---|---|---|
| Fake or refused cash orders | C13, B25, Z28, Z10, Z23 | Limit open cash orders per phone. Refusal history: after one refusal, prepay next time; after two, no cash option. One verified recipient phone. Stated inspection policy. | Auto | Proposed, Phase 1 |
| Rider sent to the wrong branch or stall | C07, Z24 | Use the branch recorded when stock was taken. Rider confirms the pin on first pickup. | Auto | Proposed, Phase 0 (branch) and 1 |
| Shop sells the same unit elsewhere | Z09, C16 | Morning one-tap stock reconfirmation; pause listings not confirmed in 7 days; rejection-rate measure. | Auto | Proposed, Phase 1 |
| No riders identified as people | C12, Z16, Z30, Z08 | Small riders list; customer told the rider's name; delivery note the rider can show at a checkpoint; two couriers per zone; written agreements. | Auto+H | Proposed, Phase 1 |
| Many orders at one shop; several riders in one street | B02, B03 | Stack pickups at one shop. Board suggests "batch with". Cap open orders per shop. | Auto+H | Proposed, Phase 1 and 2 |
| Bulky, fragile, restricted, perishable, mixed urgency | B15, B16, B17, B18 | Size class and handling class on each listing, defaulted by category. Motorbike delivery hidden for bulky items. Restricted goods collection-only. | Auto | Proposed, Phase 1 (attributes), Phase 2 (lanes) |
| Returns have no transport | B26, C14 | Return job reusing the delivery job record with a direction flag. Shop acknowledges receipt before refund. Cash refunds only by mobile-money payout. | Auto+H | Proposed, Phase 2 |
| Peaks, holidays, rain, fuel shortage | B24, B21, Z07 | Holiday calendar switches the promise to "next working day". Operations switch for a rainy-day mode and flagged areas. Pre-book couriers for month-end. | Auto, switched by H | Proposed, Phase 1 |
| Privacy and account security | Z31, Z17, Z06, Z20 | Data clause in courier agreements; minimum data in courier messages; retention rule for courier data. Stronger admin login than phone code alone. Invoice at cash collection. All key facts in message text, not behind a link. | Auto+H | Proposed, Phase 1. Z17 and Z06 need live verification first |

### Tier 3: before intercity and scale

| Risk | IDs covered | Fix | Automation | Build status |
|---|---|---|---|---|
| Bus parcel delayed, lost or under-compensated | B20, Z13 | Waybill photo; declared value; value cap; prepaid only; arrival confirmation; a reserve of 1–2% of intercity sales [A]. | Auto+H, H for every claim | Proposed, Phase 3 |
| Mobile-money payment at the door faked | Z27 | Payment confirmed by the platform through Lenco before handover. Never by the rider reading the customer's SMS. | Auto | Proposed, Phase 1 (design it in from the start) |
| Counterfeits refused at the door | Z12 | Verified-seller gating for electronics and cosmetics; seal and pickup photo. | H | Proposed, Phase 2 |
| Cross-border trade | Z33 | Noted only. Out of scope until Phase 5. | n/a | Phase 5 |

**What is already solid and must not be rebuilt** (Agent 2 and Agent 3 agree): the delivery-job state machine with its audit trail; the handover code with lock-out after five wrong tries; fees computed on the server; the cash cap per checkout; stock restored on cancellation before dispatch; 15-minute checkout holds; the notification queue with WhatsApp, SMS and email fallback; the ledger with duplicate-proof postings.

**To verify live before relying on any of this** (none of the agents had production access): whether the scheduled workflows are active; whether WhatsApp templates are approved and SMS is switched on; whether payouts are enabled; the live values of the configuration settings; where cash-order invoice numbers are issued.

---

## Deliverable 4: Existing-systems audit (condensed)

Source: Agent 3, checked against commit `a813f983`. Paths are relative to the repository root. `services/…` means `services/api/app/services/…` and `routers/…` means `services/api/app/routers/…`.

### 4.1 The real architecture

| Layer | Brief says | Repository shows |
|---|---|---|
| API host | FastAPI on OCI | **Hetzner CX23** (2 vCPU, 4 GB), one container behind Caddy. OCI is staging. (`.github/workflows/deploy-production.yml`, `infra/redeploy-api.sh`) |
| Database | Supabase Postgres | Supabase, 156 migrations. Extensions: `pg_trgm`, `pgcrypto`, `vector`. **No PostGIS.** Distances use latitude and longitude with a straight-line formula. |
| Automation | n8n | n8n on Hetzner. Every exported workflow in `infra/n8n/*.json` is marked inactive. **Live state unverified.** |
| Front ends | Next.js on Vercel | Three apps: `apps/customer`, `apps/vendor`, `apps/admin`. |
| Payments | Lenco | Lenco mobile money and card widget, plus cash on delivery. |
| Roles | Existing RBAC | `user_roles` plus `admin_roles.permissions` with eight permission names. **None for logistics.** (`supabase/migrations/20261009100000_configurable_admin_roles.sql`) |

### 4.2 What works (keep, extend, do not rebuild)

| Area | What exists | Where |
|---|---|---|
| Checkout to orders | One checkout produces one order per shop, in one transaction, safe against duplicates and stock races. | `services/orders/create.py::create_orders_atomic`, `routers/checkout.py`, `routers/orders_create.py` |
| Server-decided fulfilment and fees | The server recomputes fulfilment and fee; a tampered request is refused. | `services/orders/fulfilment.py::authoritative_vendor_groups`, `checkout_groups.fulfilment_choices` |
| Order state machine | Table-driven, row-locked, audited. | `services/orders/state.py`, table `order_events` |
| Stock | Holds, consumption, release on cancel before dispatch. | `services/stock/claim.py`, migration `20261113071000_order_cancel_stock_release.sql` |
| Courier dispatch v1 | Courier directory, per-order delivery job, guarded states, handover code with lock-out, photo proof, admin board. | Migration `20261109100000_courier_dispatch_v1.sql`; `services/dispatch/state.py`, `service.py`, `message.py`; `routers/admin_dispatch.py`; `apps/admin/app/[locale]/orders/dispatch/` |
| Notifications | Queue with duplicate protection, WhatsApp then SMS then email. | `services/notifications/dispatcher.py`, `fallback.py`, table `notification_outbox` |
| Ledger, escrow, payouts | Double-entry ledger, release gates, dispute holds. | `services/ledger/templates.py`, `services/escrow/release.py`, `services/payouts/` |
| Customer collection | Ready state with QR or PIN. | `services/pickup/issue.py`, `routers/pickup_verify.py` |
| Shop branches and hours | Branches with coordinates and opening hours; stock per branch. | Tables `vendor_locations`, `listing_location_stock` |

### 4.3 What needs fixing

| # | Finding | Where | Class | Status |
|---|---|---|---|---|
| 1 | Delivery fee included in the amount released to the shop. | `services/escrow/release.py::_order_gross_ngwee`, `services/payments/cod.py::_load_cod_order` | Bug, money | **In progress (pilot build)** |
| 2 | Cash orders auto-complete before cash is recorded, after which it cannot be recorded. | `routers/internal_order_jobs.py::_list_auto_confirm_candidates`, `services/payments/cod.py::_COLLECTABLE_STATUSES` | Bug, money | **In progress (pilot build)** |
| 3 | Shop role can confirm platform cash. | `routers/cod.py::vendor_confirm_cod_collection` | Bug, money | **In progress (pilot build)** |
| 4 | Prepaid auto-release ignores a failed delivery. | `routers/internal_order_jobs.py::_list_auto_release_candidates` | Bug, money | **In progress (pilot build)** |
| 5 | Only four other towns are recognised; the rest fall back to Band B. | `routers/checkout.py::OTHER_TOWN_TOKENS`, `resolve_address_zone` | Bug, pricing | **In progress (pilot build)** |
| 6 | Shop "ship" bypasses the courier job. | `routers/vendor_orders.py::ship_vendor_order`, `_available_vendor_actions` | Custody bypass | **In progress (pilot build)** |
| 7 | No second attempt or return after a failed delivery. | `services/dispatch/service.py::DISPATCHABLE_ORDER_STATUSES`, `create_dispatch`, `board_snapshot` | Stranded orders | Proposed, Phase 0 |
| 8 | Fee ignores shop location; charged per shop; waived per shop at K200. | `routers/checkout.py::resolve_delivery_zone`, `compute_group_delivery_fee_ngwee` | Unsuitable pricing | Proposed, Phase 1 |
| 9 | No "ready for courier collection" state for delivery orders. | `services/orders/state.py::TRANSITION_TABLE` | Missing | Proposed, Phase 0 |
| 10 | Pickup point is the shop's main branch, not the branch that holds the stock. | `services/dispatch/service.py::load_order_dispatch_context` | Wrong address | Proposed, Phase 0 |
| 11 | Delivery job and order are updated in two separate transactions. | `services/dispatch/service.py::transition_dispatch_admin`, `verify_handover_code` | Integrity gap | Proposed, Phase 1 |
| 12 | All dispatch and cash actions need a full admin. | `routers/admin_dispatch.py` (`require_role("admin")`) | Access too broad | Proposed, Phase 0 |
| 13 | Only "requested" jobs raise a stale alert. No shop-silence alert. | `services/dispatch/service.py::list_stale_requested`, `infra/n8n/dispatch-stale-alert.json`, `routers/vendor_order_queue.py` (`CONFIRM_SLA_HOURS`) | Partial | Proposed, Phase 0 |
| 14 | "Cancelled" produces no customer message; "delivered" has a template but nothing sends it. | `services/notifications/events.py::EVENT_REGISTRY` | Partial | Proposed, Phase 0 |
| 15 | A legacy manual dispatch screen duplicates dispatch v1. | `routers/admin_orders.py::manual_dispatch`, `apps/admin/…/DispatchPanel.tsx` | Duplicated | Proposed, Phase 0 (hide; keep as audited emergency route) |
| 16 | Documents still describe OCI as production; the reference price document describes an older landmark matcher. | `infra/README.md`, `infra/ENVIRONMENTS.md`, `CLAUDE.md`, `docs/ops/lusaka-delivery-reference-prices.md` | Docs | Proposed, Phase 0 |

### 4.4 What is missing

| Missing | Consequence | Planned in |
|---|---|---|
| Real courier cost per delivery | Delivery margin cannot be calculated. | Phase 0 |
| Cash custody per courier, remittance record | Cash held by riders is invisible. | Phase 0 |
| Any grouping above the per-shop order | Three shops, one home: three jobs, three codes, three cash payments. | Phase 0 (board view), Phase 1 (consignment record) |
| Size, handling class, preparation time | Cannot tell bike from car, perishable from durable, ready from not ready. | Phase 1 |
| Service levels and promised times | No windows; nothing to be on time against. | Phase 1 |
| Rider as a person | No attribution, no rider link. | Phase 1 |
| Runs, stops, hourly riders | No batching beyond manual. | Phase 2 |
| Intercity booking | Other towns are collection-only. | Phase 3 |
| Return transport | Returns handled by hand. | Phase 2 |
| Per-item status inside a shop order | Shop must reject the whole order if one item is short. | Phase 2, only if measured need (ruling R13) |

---

## Deliverable 5: Proposed architecture

### 5.1 Text diagram

```
 CUSTOMER app            VENDOR app                ADMIN app                  RIDER (no app)
 (Vercel)                (Vercel)                  (Vercel, restricted)       one-time web link
   | area, quote,          | confirm, "ready",       | board, cash-up,          | arrived, code,
   | choose window,        | hand over to rider      | exceptions, plans        | failed + reason
   | track, confirm        |                         |                          |
   v                       v                         v                          v
 +-----------------------------------------------------------------------------------------+
 |  FastAPI (Hetzner)   --- every decision, every state change, every kwacha ---          |
 |                                                                                         |
 |  services/logistics/  (new, small)            existing, extended                        |
 |    quote.py     price + cost estimate         services/orders     (state machine)       |
 |    promise.py   cut-offs, windows, rules      services/dispatch   (jobs, handover code) |
 |    consign.py   group by address + window     services/payments   (COD, Lenco)          |
 |    custody.py   cash held, remittances        services/ledger     (double entry)        |
 |    planner.py   rounds (Phase 2)              services/notifications (outbox)           |
 |    carriers.py  manual intercity (Phase 3)                                              |
 +-----------------------------------------------------------------------------------------+
        |  one transaction per custody or money event                  ^
        v                                                              |  HTTPS + token +
 +-------------------------------+                                     |  repeat-safe key
 |  Supabase Postgres            |                          +----------------------------+
 |  the only source of truth     |                          |  n8n (Hetzner)             |
 |  orders, consignments, jobs,  |                          |  clocks and messengers     |
 |  quotes, cash custody, ledger |                          |  "wake the API at 11:00"   |
 +-------------------------------+                          |  "carry this alert"        |
                                                            +----------------------------+
        Outside parties, all manual for now:
        COURIER COMPANIES (WhatsApp message + rider link)  ·  BUS / POST DEPOTS (waybill photo)
        COLLECTION POINTS (Phase 3: scan in, scan out)     ·  LENCO (mobile money, payouts)
```

### 5.2 How the parties interact (normal Lusaka delivery, target state after Phase 1)

1. **Customer** sets their area once. Product pages and the cart show delivered price and arrival window per shop.
2. **Customer** checks out, choosing a window. The server stores the quote (inputs, estimated cost, fee) and creates one order per shop, as today.
3. **API** groups the shop orders for one address and window into one **consignment** with one handover code.
4. **Shop** confirms, packs and taps "ready for collection". No courier is booked before this.
5. **Operations** (or the cut-off timer) books a courier job for the consignment. The courier company gets a WhatsApp message with a one-time rider link.
6. **Rider** collects. The shop confirms the handover. Custody moves to the rider.
7. **Rider** taps "arrived". Only then is the code released to the customer. The rider enters the code, or uploads a photo. For cash orders the amount collected is recorded against that courier.
8. **API** marks the order delivered, tells the customer, and records the actual courier cost.
9. **Courier** remits cash by mobile money the same day. Operations match it in the daily cash-up. Only then does the shop's share become payable.
10. **Failure at any step** creates a new attempt, a return to the shop, or an operations alert. Nothing is left in an open state without a timer watching it.

### 5.3 Component boundaries: API and database versus n8n

**Rule: n8n never decides and never holds the only copy of anything.** If n8n is down for a day, nothing is wrong, only late. The admin board carries a "run now" button for each timed job.

| Must live in FastAPI + Postgres (transactional, audited) | May live in n8n (safe to fail or repeat) |
|---|---|
| Quote, fee, discount, promised window | Timer that calls the API at each cut-off |
| Order, consignment, delivery-job and run state changes | Timer every 5–15 minutes that asks the API "what is stale?" |
| Handover-code checks and custody records | Sending reminders the API has queued |
| Cash receivable, cash held per courier, remittance matching, ledger postings | Daily cash-up message and weekly margin report (the API produces the numbers) |
| Round planning and rider assignment | Paging operations about an exception |
| Creating an exception and setting its escalation level | Heartbeat alert when a timer did not fire |

### 5.4 Reliability controls

| Risk | Control | Exists? |
|---|---|---|
| A timer fires twice | Each timed call carries a fixed key (for example `plan:lusaka:2026-11-14T11:00`). A repeat returns the stored result. | Pattern exists for notifications; extend |
| Two state changes race | Compare-and-set transitions with guard triggers. | Exists for orders and delivery jobs |
| One order in two active jobs | Partial unique index: one active job per order. | Exists |
| Job updated but order not (two transactions) | One transaction per custody event, plus a repair check for "job delivered, order not". | Proposed, Phase 1 |
| Duplicate messages | Outbox duplicate key. | Exists |
| A timed job silently stops | Error workflow on every n8n workflow; missed-heartbeat alert. | Proposed, Phase 0 |
| Courier never answers | Stale check escalates: re-notify, next courier, operations. Each step is a recorded change. | Partly exists |
| A bad plan | Plans stay "proposed" until a person releases them, through Phase 2. Inputs and planner version are stored. | Proposed, Phase 2 |

### 5.5 Technology choices and cost

| Tool | Decision | Add when | Monthly cost |
|---|---|---|---|
| Straight-line distance × 1.4 | Use now. | Now | $0 |
| Table of about 50 named areas with distances between each pair | Build. Gives road distances without running a routing service. | Phase 1 | $0 |
| "Add the nearest feasible stop" planner (about 100 lines) | Build. | Stage 1 trigger | $0 |
| OR-Tools route solver | Defer. Run in a separate worker with a 10–30 second limit, never inside an API request. | 40+ scheduled orders a day, or two riders per round | $0, or a few euros for a second small machine [A] |
| PostGIS | Defer. | When areas become drawn shapes or "nearest point" queries appear | $0 (Supabase extension) |
| OSRM road routing | Defer. Prepare the map data on another machine and copy it over. | When straight-line error on fees exceeds about 20%, or runs exceed about 10 stops | $0 |
| Paid map APIs | Avoid in the request path. | Not planned | Not costed |
| AI | None before Phase 4 (ruling R11). | Phase 4 | Within the existing $15 a month cap |

**Net new infrastructure cost through Stage 2: $0** [D]. This fits the $50 a month ceiling.

---

## Deliverable 6: Logistics decision engine

The engine is a set of plain rules. It runs at three moments: when quoting (cart and checkout), when planning (cut-off, or shop says ready), and when something fails. All thresholds are [A] and live in configuration.

### 6.1 Inputs

| Input | Source today | Gap |
|---|---|---|
| Customer location | Landmark text; optional coordinates | Area picker and optional pin (Phase 1) |
| Shop locations and distances | `vendor_locations` coordinates [S] | None |
| Parcel size | None | Size class S / M / L / XL / bulky per listing, defaulted by category. Exact weight is not needed. |
| Handling needs | Category, `fulfilment_mode` | Handling class: ambient / fragile / hot food / chilled / frozen / flowers / restricted |
| Shop readiness | Opening hours; `lead_time_days` for made-to-order | Preparation minutes per branch (default 30); "ready" tap |
| Urgency | None | Service level on the order |
| Courier availability | Courier directory | Assume per-job is available; alert when not. Riders and blocks from Stage 1. |
| Cost and margin | Fee band only | Stored quote with estimated cost; actual cost per job |

### 6.2 Decision tree

```
STEP 1  WHICH LANE?  (per shop order, at quote time)
  Destination outside the Lusaka service area?            -> INTERCITY
  Any item chilled, frozen or restricted?                 -> NOT OFFERED (collect, or shop's own delivery)
  Any item hot food or flowers?                           -> PERISHABLE   (not offered before Phase 2)
  Any item bulky?                                         -> BULKY        (car or van, quoted)
  Otherwise                                               -> PARCEL

STEP 2  WHAT MAY BE OFFERED?  (feasibility, never preference)
  PARCEL     Standard   ready by 11:00 -> by 15:00 | ready by 15:00 -> by 19:00 | else next day by 13:00
             Express    within 120 min of ready; only if shop-to-customer <= 12 road km,
                        shop ready within 30 min, time between 08:00 and 17:30        (Stage 1)
             Economy    next round or next day                                         (Stage 1)
             Collect    always offered, always cheapest
  PERISHABLE Express only: 60 min (hot food) within 6 km; 120 min (flowers) within 12 km.
             Otherwise collect only. Prepaid, or cash only for customers with a completed order.
  BULKY      Standard windows, car or van, surcharge by size. Or collect.
  INTERCITY  Depot collection, days by corridor. PREPAID ONLY. Declared value under a cap.
             No perishables. No fragile goods without the shop's packing declaration.
  Made to order: any of the above; the clock starts when the shop says ready.
  Show at most three choices. Show an option only if the order's expected contribution
  (commission + delivery fee - delivery cost - payment fees) is at or above the floor (default K0).

STEP 3  GROUP INTO CONSIGNMENTS  (at plan time)
  Consignment = everything going to one address in one promised window.
  Several shops in one consignment:
     all ready within 90 min of each other (20 min for Express)?   -> one multi-pickup run
     else, latest item still meets the promise and the customer
          chose "deliver together" (default; always for cash)?      -> hold early parcels at the shops, one run
     else                                                           -> split; the late parcel travels in its own
                                                                       consignment (customer saw and accepted the
                                                                       extra fee at checkout)

STEP 4  CHOOSE THE METHOD
  PERISHABLE          -> dedicated courier. Stack of 2 only if same shop (or within 1 km),
                         ready within 5 min of each other, and the second drop still meets its promise.
  Express             -> dedicated courier; multi-pickup if several shops.
                         Hold at most 10 min for a second order from the same shop.
  Standard / Economy  -> the round, if an hourly rider is booked for that cut-off (Stage 1).
                         Otherwise per-job courier.
  Collect             -> no transport; issue a collection code (exists).
  INTERCITY           -> to the depot (see 6.4), then carrier, then customer collects.

STEP 5  WHEN SOMETHING FAILS
  No courier accepts in time, or the rider cancels  -> escalate one step UP in cost
                                                       (round -> per-job -> operations phones).
                                                       Never one step DOWN in promise.
  Shop not ready 10 min after the rider arrives     -> skip, re-queue that order, flag the shop.
  Customer unavailable                              -> rider records the reason; customer is asked to choose
                                                       re-delivery or collection; after the second failure,
                                                       return to shop and cancel.
```

### 6.3 Rules that are never broken

1. A perishable or Express parcel is never held to fill a batch beyond the limits above.
2. A parcel never changes hands without a recorded custody event.
3. A courier never carries more cash than the cap. New cash jobs to that courier are blocked until remittance.
4. An intercity parcel is never handed to a carrier unpaid.
5. No product is ever substituted without the customer choosing it.
6. No state change and no money movement is ever decided by AI or by n8n.

### 6.4 Batching rules (Stage 1 onward)

**When is waiting worth it?** Do not estimate per order. Use fixed cut-offs. The wait is the time to the next cut-off, and the customer agreed to it at checkout.

**Does this order join this run?** Only if all three hold:

- adding it costs no more than 85% [A] of delivering it alone;
- every stop still meets its promise;
- capacity, cash and duration limits hold.

Otherwise it travels alone. By construction this rule can never cost more than dedicated delivery.

| Limit [A] | Motorbike | Car or small van |
|---|---|---|
| Parcels per run | 6 (S and M only; L counts as 2) | 12; bulky allowed |
| Run duration | 180 min | 240 min |
| Extra travel time added to an Express parcel already on board | the lesser of 20 min or 40% of its direct time | same |
| Perishable stack | 2 | 2 |
| Cash carried | K1,500 now; K3,000 with named hourly riders (ruling R5) | same |
| Wait at a shop | 10 min, then skip | same |

In a market where most orders are cash, **the cash cap limits batch size before box volume does**: at the K500 cash cap per checkout [S], K1,500 is three full-value cash orders [D]. This is the strongest practical reason to encourage prepayment.

**Sequencing.** Up to 6 stops: try every order. Up to about 12 stops: add each stop where it costs least, pickups before their drops. Beyond that: the route solver.

**Intercity hand-off.**

```
Carrier    = cheapest active carrier serving the town, with reliability above a floor,
             whose next departure leaves time for the first mile plus 30 min.
First mile = 3 or more intercity parcels today -> one combined depot run before the earliest cut-off;
             otherwise a per-job courier, or the shop drops at the depot for a fixed credit.
Custody    = Convergeo reference on the parcel; photo of the carrier's receipt uploaded;
             customer receives carrier name, waybill number, depot and expected arrival.
Arrival    = customer collects with ID and waybill; closed by customer confirmation or depot photo;
             nothing by expected arrival + 24 h -> exception to operations.
Payment    = prepaid only; released on confirmed collection.
```

Carrier reliability starts neutral and is updated from Convergeo's own shipments. No public reliability data exists [S: Agent 5].

### 6.5 Who decides what

| Decision | Mechanism |
|---|---|
| Lane, feasibility, promise, never-rules | Rules |
| Price and discount | One formula with versioned settings |
| Consignment grouping, same-shop stacking | Rules (simple grouping) |
| Round membership and order, up to about 10 orders | Simple insertion planner |
| Rounds above about 10 orders or with 2+ riders | Route solver (OR-Tools) |
| Carrier choice | Rules plus a score |
| Preparation-time and arrival estimates | Averages per shop and per area pair. A learned model only after a few thousand deliveries. |
| Routing, assignment, pricing, state, money | **Never AI** |

### 6.6 Pricing rules used by the engine

**Principles.** Price what causes cost: shop-to-customer road distance, number of pickups, size, urgency and payment method. The customer's distance from the city centre causes none of these. Estimate cost first, then set the price. Discounts come from a funded budget, not a free-floating threshold.

**Cost estimate** (settings [A]; fitted to four second-hand car ride-hail fare ranges, because no motorbike courier tariff is published [S: Agent 5]):

```
road_km        = 1.4 x straight-line km
per-job cost   = the greater of K25, or K5 + K5.5 x road_km + K8 x (stops beyond two)
risk reserve R = first-attempt failure rate x half the trip cost, plus cash handling
                 (start: 8% failure for cash, 3% prepaid, K3 cash handling) -> about K3 to K8 an order
```

| Option | Customer price | Note |
|---|---|---|
| Standard | cost × 1.10 + R, rounded up to K5, minimum K30 | |
| Express | cost × 1.25 + R, rounded up to K5, minimum K45 | Higher margin pays for capacity kept free |
| Economy | Standard minus 60% of the saving | Customer gets 60%, Convergeo 40% |
| Several shops, one address | one fee on the best pickup route; **never more than the separate Standard fees added up** | The cart shows what each shop adds, so the customer can drop the expensive one |
| Collect from shop | K0 | |
| Collect from partner point | cost × 1.10, minimum K10 | Phase 3 |
| Intercity | first mile + carrier price × 1.05 + K10 handling | Carrier price passed through; no margin on a number Convergeo does not control |
| Bulky | car or van cost + size surcharge | |

**Proposed distance bands** [A], replacing the "distance from city centre" test while keeping the fee values customers have already seen: up to 4 road km K30 · up to 8 km K45 · up to 13 km K65 · up to 20 km K95 · beyond: quoted, or collect.

**Discount budget, replacing "free above K200".**

```
discount budget = 50% of the commission on that order   [A]
delivery discount = the lesser of the delivery fee, or (budget + any shop-funded amount + any campaign amount)
```

For a K40 delivery, the basket at which delivery becomes fully free is K1,600 at 5% commission, K1,000 at 8%, K800 at 10% [D]. Below that the customer sees a partial discount, for example "K8 off delivery". With the K500 cash cap [S], a cash order can never earn fully free delivery under this rule. That is correct: it cannot afford it.

Three discounts worth paying, each with its own budget and measure:

| Discount | Rule | Why |
|---|---|---|
| Fewer-shops nudge | Second and later shops in a cart pay only what they add to the route. If the customer accepts a nearer offer, share 50% of the saving. | The saving is real and the customer created it. |
| Prepaid nudge | K5 off delivery for paying by mobile money in advance. | Removes cash risk, refusal risk and the cash cap on batching. |
| First order | Free Standard delivery, capped at the K45 band, from a fixed monthly marketing budget. | Acquisition, measured against repeat orders. |

Shops may also fund free delivery themselves, deducted from their payout. This keeps "free delivery" badges without Convergeo paying.

**Minimum information to quote accurately:** customer area · shop coordinates (exists) · size class · handling class · service level · payment method (exists) · cart subtotal and commission rate (exist) · shop readiness. **Not needed:** exact weight, exact road distance, rider availability, traffic.

---

## Deliverable 7: Database and API improvement plan

**Ground rules** (from the project's own conventions): every change is additive; money is whole ngwee in the database and API; every state change goes through a guarded function with an audit record; every new table has row-level security; every changing endpoint has an authorisation check, input validation and a rate limit; no user-facing text is hard-coded.

### 7.1 Reuse first

| Concept in the brief | Decision | How |
|---|---|---|
| Fulfilment order | **Reuse** `orders` (one per shop) | Add `service_level`, `promised_by`, `ready_at`, `pickup_location_id`, `consignment_id` |
| Delivery consignment | **New, Phase 1** | `delivery_consignments`: one address, one window, one code |
| Parcel | **Not built** | Size class on the listing is enough. Revisit only if one order must split across bags. |
| Pickup location | **Reuse** `vendor_locations` | Add `prep_minutes` |
| Collection hub | **New, Phase 3**, as `collection_points` | May point at a shop branch or a third-party site. No platform-owned hub. |
| Driver | **New, Phase 1**, minimal | `courier_riders`: name, phone, courier company, active. No ID numbers. |
| Vehicle | **Not built** | A `vehicle_class` value on the rider or the job (bike / car / van) |
| Route, stops, batch | **New, Phase 2** | `delivery_runs` and `delivery_run_stops`. `dispatch_requests` stays the per-order leg. |
| Transport provider | **Reuse** `courier_partners` | Add `kind`: last mile / intercity bus / postal / freight |
| Transport booking | **New, Phase 3** | `transport_bookings`: waybill, depot, receipt photo, declared value |
| Service level | **Not a table** | A fixed list in code plus settings in `platform_config` |
| Pricing rules | **Not a table** | Versioned settings in `platform_config`; every quote stores the version it used |
| Proof of collection | **Extend** | Shop confirms the handover to the rider; recorded in `dispatch_request_events` |
| Proof of delivery | **Exists** | Handover code or photo. Code moves to consignment level in Phase 1. |
| Delivery exception | **Column now, table later** | `failure_code` on the job in Phase 0. `delivery_exceptions` (type, owner, cost, resolution) in Phase 2 when there is a queue to manage. |
| Returns | **Extend** | `dispatch_requests.direction = 'return'` |
| Shop schedule | **Reuse** `vendor_locations.hours` | Used by the promise rules from Phase 1 |
| Event stream | **Not built** | `order_events`, `dispatch_request_events` and `notification_outbox` already record and carry events |

### 7.2 Database changes by phase

| Phase | Change | Purpose |
|---|---|---|
| 0 | `dispatch_requests` + `actual_cost_ngwee`, `attempt_no`, `direction`, `failure_code`, `pickup_location_id` | Real cost; second attempt; return; structured reasons; correct branch |
| 0 | `dispatch_requests` + `cod_collected_ngwee`, `cod_collected_method`, `cod_collected_at`, `remittance_id` | Who holds which cash |
| 0 | New `courier_remittances` (courier, amount, method, reference, received at, recorded by) | Daily cash-up per courier |
| 0 | `orders` + `ready_at`; order transition `processing → ready` allowed for delivery orders | Shop readiness |
| 0 | `admin_roles` permission list + `logistics.manage`, `cod.reconcile` | Limited operator login |
| 0 | Ledger account `delivery_revenue` | **In progress (pilot build)** |
| 0 | `platform_config` + alert timers, cash cap, town list | Editable without a deploy |
| 1 | New `delivery_areas` (name, other spellings, centre point, sector) and area-pair distances | Area picker; road distance without a routing service |
| 1 | New `delivery_quotes` (inputs, settings version, service level, estimated cost, fee, discount, who funds it) | Margin per order; auditable price |
| 1 | New `delivery_consignments`; `orders` + `consignment_id`, `service_level`, `promised_by` | One visit, one code, one cash payment |
| 1 | `vendor_listings` + `size_class`, `handling_class`; `vendor_locations` + `prep_minutes` | Lanes and promises |
| 1 | New `courier_riders`; `dispatch_requests` + `rider_id`; rider link tokens (stored hashed, expiring) | Rider as a person; self-service code entry |
| 1 | Ledger accounts `courier_payable`, `courier_cash_held` | Cash custody and courier cost inside the ledger |
| 2 | New `delivery_runs`, `delivery_run_stops`; `dispatch_requests` + `run_id`, `allocated_cost_ngwee`, `baseline_cost_ngwee` | Rounds; cost sharing; savings measurement |
| 2 | New `delivery_exceptions` | Exception queue with owners |
| 2 | `order_items` + `fulfilment_status` (only if ruling R13's trigger is met) | Part-filled shop orders |
| 3 | New `collection_points`, `carrier_services`, `transport_bookings`, `custody_events`; `courier_partners` + `kind` | Points and intercity |
| 4–5 | Area shapes (PostGIS), per-town service areas, currency and country columns where needed | Scale |

**Indexes.** Add a partial index on `orders (status, created_at) where fulfilment = 'delivery'` before volume grows [S: Agent 3]. Each new table gets indexes on its foreign keys and on `(status, created_at)`.

### 7.3 State machines

Existing machines are extended, not replaced. New ones follow the same pattern: a transition table in code, mirrored by a database guard, with an audit row per change.

```
ORDER (existing; additions marked +)
  placed -> confirmed -> processing -> +ready (delivery orders too) -> shipped -> delivered -> completed
  shipped -> +cancelled, only through "returned to shop, acknowledged", which also restocks

DELIVERY JOB (existing; additions marked +)
  requested -> accepted -> picked_up -> +arrived -> delivered
                                    \-> failed (+failure_code)
  requested | accepted -> cancelled
  after failed: +new job on the same order (attempt 2, the maximum)  or  +return job (direction = return)
  return job: requested -> accepted -> delivered (meaning: shop acknowledged receipt)

CONSIGNMENT (new, Phase 1)
  open -> ready -> dispatched -> delivered
                             \-> partly_delivered -> delivered | closed
                             \-> failed -> closed

CASH CUSTODY (new, Phase 0 as a record; Phase 1 in the ledger)
  expected -> held_by_courier -> remitted -> matched (ledger posted; shop share becomes payable)
           \-> refused (order cancelled, goods return)        \-> shortfall (a person decides)

RUN (new, Phase 2)
  proposed -> released -> in_progress -> completed | aborted

TRANSPORT BOOKING (new, Phase 3)
  booked -> handed_to_carrier -> arrived_at_depot -> collected
                             \-> overdue -> found | lost (claim; a person decides)
```

### 7.4 Events

Events are rows in the existing audit and outbox tables. Each has a duplicate-proof key so a repeat does nothing.

| Event | Raised when | Who is told |
|---|---|---|
| `order.ready_for_collection` | Shop taps ready | Operations board; planner |
| `consignment.formed` / `.split` | Grouping decided | Customer (one message per consignment) |
| `dispatch.requested` / `.accepted` / `.picked_up` | Job progresses | Courier; shop; customer at pickup |
| `dispatch.arrived` | Rider taps arrived | Customer receives the handover code |
| `dispatch.delivered` | Code or photo accepted | Customer; shop |
| `dispatch.failed` | Rider records a reason | Customer (choose re-delivery or collection); operations |
| `dispatch.returned` | Shop acknowledges a return | Customer; stock restored |
| `cod.held_by_courier` / `.remitted` / `.shortfall` | Cash events | Finance; operations on shortfall |
| `sla.vendor_unconfirmed` / `sla.dispatch_stale` / `sla.cod_unbooked` | A timer finds a stale item | Shop, then operations |
| `order.cancelled` | Any cancellation | **Customer** (missing today) and courier if a job is active |
| `booking.handed_to_carrier` / `.arrived` / `.overdue` | Intercity (Phase 3) | Customer; operations on overdue |

### 7.5 API additions (outline contracts)

All amounts are whole ngwee. All admin routes sit behind the new permissions.

| Phase | Endpoint | Purpose |
|---|---|---|
| 0 | `POST /vendor/orders/{id}/ready-for-collection` | Shop signals the parcel is sealed and waiting |
| 0 | `POST /admin/dispatch/requests/{id}/complete` with `{handover_code or pod_photo_id, cod_collected_ngwee, cod_method}` | One action: delivered **and** cash recorded against the courier |
| 0 | `POST /admin/dispatch/requests` extended: accepts an order whose last attempt failed; accepts `direction: "return"` | Second attempt; return to shop |
| 0 | `POST /admin/dispatch/requests/{id}/returned` | Shop acknowledged; cancel and restock |
| 0 | `PATCH /admin/dispatch/requests/{id}/cost` with `{actual_cost_ngwee}` | Real courier cost |
| 0 | `GET /admin/cod/custody` · `POST /admin/cod/remittances` | Cash held per courier; record and match a remittance |
| 0 | `GET /admin/logistics/margin-report` | Fee against cost by zone and courier |
| 0 | `GET /admin/dispatch/board` extended with checkout, landmark and shop area | Group by address for manual consolidation |
| 0 | `POST /internal/logistics/tick/sla-watch` | One repeat-safe check for all stale timers |
| 1 | `GET /delivery/areas` · `PUT /account/delivery-area` | Area picker, remembered |
| 1 | `POST /delivery/quote` with `{area or pin, lines, payment_method}` returning up to three options, each with window, fee, discount and what each shop adds | One quote function for cart, checkout and order creation |
| 1 | `GET /products/{id}/offers?area_id=` | Delivered price and arrival per shop |
| 1 | `POST /vendor/orders/{id}/handover-to-rider` | Proof of collection |
| 1 | `GET /r/{token}` and `POST /rider/{token}/arrived`, `/handover`, `/failed` | Rider link: no login, one job, expires |
| 2 | `POST /internal/logistics/tick/plan-round` · `GET/POST /admin/logistics/runs…` | Rounds |
| 3 | `…/admin/logistics/carriers`, `…/bookings` · `POST /point/{token}/scan` | Intercity and points |

### 7.6 Security and access (brief §9)

| Role | Exists today? | May see | May do | Must not |
|---|---|---|---|---|
| Super Admin | Yes | Everything | Everything; grant roles; override with a reason, audited | Mark delivered without proof (override requires a photo or code) |
| Logistics Admin | **No. Add in Phase 0** (`logistics.manage`) | Board, jobs, couriers, riders, exceptions; customer contact for active jobs | Create, assign, cancel jobs; enter codes; record cash handed to courier; record cost | Touch escrow, refunds, payouts, identity checks, pricing settings |
| Finance Admin | Read-only today. **Add `cod.reconcile` in Phase 0** | Ledger, cash custody, remittances, margin report | Match remittances; confirm cash; resolve shortfalls | Change job status; edit prices |
| Customer Support | No. Phase 1, as a restricted admin role | Order and delivery status; customer contact | Message customers; open an exception | Any money or state change |
| Vendor Admin / Vendor | Yes (owner check on every route) | Own orders and their delivery status. No courier contact. No handover code. | Confirm, pack, ready, hand to rider | Confirm platform cash (**in progress (pilot build)**); mark shipped without a job (**in progress (pilot build)**) |
| Driver / Rider | **No. Phase 1**, with no account | Through a one-time link: one job. Pickup address at once; drop address, first name and phone only after accepting. Cash amount. | Arrived; enter code; upload photo; record failure | See other jobs, order contents beyond a parcel count, or anything after the job closes. The link expires. |
| Collection Point Operator | No. Phase 3 | Parcels addressed to that point: reference, size, collection code check | Scan in; scan out against the customer's code | See customer addresses, phone numbers or order contents |
| Customer | Yes | Own orders; code only when the rider has arrived | Choose options; confirm receipt; raise a dispute | — |

**Audit.** Every job change, code attempt, cash event, remittance, cost entry, override and rider-link use writes an audit row with who, when and why. The handover code itself is never logged (already true).

**Alert routing.** Operations alerts go to a small list of numbers, not to the founder's phone alone (Agent 2, Z17 and Z22).

### 7.7 Data protection and retention

| Topic | Position | Label |
|---|---|---|
| What couriers receive | Only what delivery needs: first name, phone, landmark or pin, cash amount, parcel count. | Recommendation |
| Courier agreements | A written data-processing clause in each courier and carrier agreement: use only for the delivery, delete after 30 days [A], report loss of data. | Recommendation; get legal wording |
| Rider links | Show the drop address and phone only after acceptance; stop showing them 24 hours [A] after the job closes. | Recommendation |
| Retention of delivery data | Job records, custody and cash records: keep with the order for tax and audit. Rider-link access logs: 12 months [A]. Proof-of-delivery photos: 90 days after the dispute window closes [A], then delete. Notification payloads containing phone numbers: prune on the existing outbox schedule. `docs/ops/data-retention.md` already clears addresses on account deletion [S]; it lists outbox pruning as an open follow-up and does not mention courier data. | [S] for the gap; periods are [A] |
| Identity documents | Convergeo does not store rider ID numbers. Courier companies hold them. | Ruling R9 |
| Registration and data location | A law-firm summary says data controllers must register with the Data Protection Commissioner, and that personal data must be stored in Zambia unless an exception applies (for example consent plus approved contracts) [S: Agent 5, secondary source; the Act itself was not read]. The database is hosted in the EU (`eu-north-1`) [S: Agent 3]. **This needs a lawyer's opinion. It affects the whole platform, not only logistics.** | Open legal question |
| Courier licence | If Convergeo only arranges carriage through licensed couriers it may not need its own courier licence; if it carries for hire it may. The two published fee figures conflict [S: Agent 5]. Confirm with ZICTA or counsel before hiring riders by the hour. | Open legal question |

---

## Deliverable 8: Automation blueprint

Every automation follows one pattern that already exists in the code: a timer in n8n calls a token-protected API endpoint; the API selects items by state, changes them through guarded functions, and queues messages with a duplicate-proof key. Running any of them twice changes nothing.

| # | Automation | Trigger | Action | Conditions | Error handling | Escalation | Phase / status |
|---|---|---|---|---|---|---|---|
| 1 | Checkout hold sweeper | Every 2 min | Release expired stock holds | Hold older than 15 min | Repeat-safe | None | Exists (verify active) |
| 2 | Notification sender | Every minute | Send queued messages: WhatsApp, then SMS, then email | Unsent, due for retry | Retry with back-off; duplicate key | Failed logistics templates listed on the board | Exists (verify templates approved, SMS on) |
| 3 | Auto-complete delivered orders | Hourly | Move delivered orders to completed | 48 h since delivery; no dispute; **not a cash order with unbooked cash** | Repeat-safe | None | Exists; cash exclusion **in progress (pilot build)** |
| 4 | Auto-release prepaid | Hourly | Release escrow to the shop | 7 days shipped; no dispute; **latest job not failed or missing** | Repeat-safe | None | Exists; exclusion **in progress (pilot build)** |
| 5 | Shop-silence ladder | Every 5–15 min | Remind the shop at 1 h; alert operations at 2 h | Order unconfirmed, inside opening hours | One message per order per step | Operations phone the shop. From Phase 1: auto-cancel at close of business, with customer message and restock | Proposed, Phase 0 (alerts), Phase 1 (auto-cancel) |
| 6 | Stale delivery jobs | Every 15 min | Alert on requested > 45 min, accepted > 45 min, picked up > 120 min [A] | Per job, per state | One alert per job per state | Picked up > 8 h: incident; a person calls the courier company | Requested: exists. Others: proposed, Phase 0 |
| 7 | Cancel cascades to courier | Order cancelled | Cancel the active job; message the courier; message the customer | Job not yet picked up | Same transaction as the cancel | If already picked up: becomes a return job | Proposed, Phase 0 |
| 8 | Cash-unbooked watchdog | Hourly | Alert when a delivered cash order has no cash record | 2 h after delivery | Read-only check | Finance at 24 h | Proposed, Phase 0 |
| 9 | Cash cap | When cash is recorded against a courier | Block new cash jobs to that courier | Cash held above the cap (K1,500 [A]) | Checked inside job creation | Operations arrange remittance | Proposed, Phase 0 |
| 10 | Daily cash-up | 21:00 Lusaka | Report per courier: cash delivered, remitted, outstanding | Daily | Stored, versioned report | Finance on any difference other than zero | Proposed, Phase 0 |
| 11 | Failed-delivery follow-up | Job failed | Ask the customer: re-deliver or collect | Attempt 1 | Once per job | No reply in 24 h, or attempt 2 fails: return to shop. Support phones for orders above K300 [A] | Proposed, Phase 0 |
| 12 | Weekly margin report | Weekly | Fee charged against actual cost, by zone and courier | Jobs with a cost entered | Read-only; lists jobs missing a cost | Founder pricing review; alert if average margin is below zero | Proposed, Phase 0 |
| 13 | Workflow health | Any workflow error or missed run | Alert | Error workflow set on every workflow; heartbeat on the critical timers | n/a | Operations list | Proposed, Phase 0 |
| 14 | Fallback-zone review | Daily | List addresses that used the fallback band | Phase 0 only; the picker replaces it | Read-only | Operations add area names | Proposed, Phase 0 |
| 15 | Cut-off planner | 11:00 and 15:00 | Form consignments; book per-job couriers, or propose a round | Orders ready, or expected ready, for that window | Fixed key per cut-off; advisory lock; plan stays "proposed" until released | No courier accepts: next courier, then per-job, then operations | Proposed, Phase 1 (grouping), Phase 2 (rounds) |
| 16 | Readiness nudge | Shop-to-customer travel time before the cut-off | Ask the shop "is it ready?" | Order confirmed, not yet ready | One message per order | Late twice in a week: flag the shop | Proposed, Phase 1 |
| 17 | Code at the door | Rider taps "arrived" | Send the handover code to the customer by WhatsApp and SMS | Active job | Photo fallback if the network fails | Operations enter the code by phone as a last resort | Proposed, Phase 1 |
| 18 | Refusal history | Cash refused | After one refusal, require prepayment next time; after two, remove the cash option for that phone | Per phone | Rule checked at checkout | Support reviews complaints such as "rider was rude" | Proposed, Phase 1 |
| 19 | Morning stock check | 07:30 daily | One-tap "still in stock?" to shops with active listings | Listings not confirmed in 7 days are paused | One message per shop per day | Shop coaching at over 5% rejections | Proposed, Phase 1 |
| 20 | Holiday and rain mode | Calendar date, or an operations switch | Change the promise text to "next working day"; offer collection in flagged areas | Gazetted holidays; operator switch | Setting only | None | Proposed, Phase 1 |
| 21 | Intercity overdue | Expected arrival + 24 h | Open an exception | Booking not confirmed arrived | Once per booking | A person phones the depot; claim process | Proposed, Phase 3 |
| 22 | Carrier scoring | Each closed booking | Update on-time, loss and cost-difference scores | n/a | Recalculated from records | Carrier below the floor is paused for review | Proposed, Phase 3 |

**Where a person is always required:** any cash shortfall; any lost or damaged parcel and who pays; any fraud finding; any lost-parcel claim with a carrier; releasing a planned round (until Phase 4); changing prices.

---

## Deliverable 9: Financial simulation

**Read this first.** No Zambian motorbike courier tariff, hourly rider rate or bus parcel tariff is published [S: Agent 5]. Every kwacha cost below comes from a cost curve fitted to four second-hand car ride-hail fare ranges. **Which method beats which, and at roughly what volume, is reliable. The exact kwacha figures are not.** Ten real quotes (next action 4) replace the [A] rows and every figure updates.

The scenario arithmetic was produced by Agents 1+4. The lead agent re-checked Scenarios 1 and 2 and the discount arithmetic by hand. The volume simulation was not re-run.

### 9.1 Editable assumptions

| Setting | Value | Label | Basis |
|---|---|---|---|
| Fee bands today | K30 / K45 / K65 by customer distance from the city centre (5 / 12 / 25 km) | [S] | `supabase/migrations/0008_config.sql`, `routers/checkout.py` |
| Free delivery today | Shop subtotal of K200 or more | [S] | `platform_config.free_delivery_threshold_ngwee` = 20000 |
| Cash-on-delivery cap | K500 per checkout | [S] | `platform_config.cod_cap_ngwee` = 50000 |
| Commission | 3% to 12% by category; default 8% | [S] | `0008_config.sql` |
| Petrol | K33.06 a litre (November 2026) | [S] | Media quoting the regulator, via Agent 5. The regulator's own PDF could not be read. |
| Lusaka to Ndola / Livingstone | 321 km / 472 km | [S] | Logistics Cluster road table, via Agent 5 |
| Road distance | 1.4 × straight line | [S] | `docs/ops/lusaka-delivery-reference-prices.md` gives 1.3–1.5 |
| Per-job courier cost | the greater of K25, or K5 + K5.5 per road km | **[A]** | Fitted to car ride-hail ranges in the reference document. No motorbike tariff exists. |
| Extra stop in one job | K8 per stop beyond two | **[A]** | None |
| Hourly rider | K60 an hour including bike and fuel; 2-hour minimum | **[A]** | None. See ruling R14. |
| Speed; pickup time; drop time | 22 km/h; 6 min; 5 min | **[A]** | None |
| Motorbike fuel use | 2.5 litres per 100 km | **[A]** | None |
| Collection-point handling | K5 a parcel | **[A]** | None |
| Shop depot drop-off credit | K15 | **[A]** | None |
| Intercity carrier price | **Unknown: `X`** | — | Not published by any operator |
| Proposed fee | cost × 1.10 + K3, rounded up to K5 | **[A]** | Deliverable 6.6 |
| Area positions | Approximate centre points | **[A]** | Not surveyed |
| Pilot volume; basket size | 5–30 delivery orders a day; K150–K500 | **[A]** | Agent 2 |

Fuel is shown for information. It is inside the courier's price, not added to it. "Courier cost" is what Convergeo pays; with per-job couriers it already includes the driver. Times run from "shop says ready". All results are [D].

### 9.2 Scenario 1: one shop (Woodlands), one customer (Kabulonga)

| Method | Road km | Trips / riders | Fuel | Courier cost | Time | Customer charge | Delivery margin |
|---|---|---|---|---|---|---|---|
| Dedicated per-job, today's fee | 4.3 | 1 / 1 | 0.11 L (K4) | K28 | 23 min | K30 | **+K2** |
| Same, basket of K200 or more (free today) | 4.3 | 1 / 1 | 0.11 L | K28 | 23 min | K0 | **−K28**. Commission at 8% of K200 is K16, so the order nets −K12. |
| Round with hourly rider (at about 20 orders a day) | shared | shared | — | about K19 | by window | K25 Economy | +K6 |
| Through a hub | longer | 2 | — | higher | slower | — | Not sensible |
| Collect from shop | 0 | 0 | 0 | K0 | customer's time | K0 | K0 |
| Third party | — | — | — | — | — | — | Not applicable |

**Reading.** A single short delivery is fine on a dedicated courier. The loss is created by the free-delivery rule, not by logistics.

### 9.3 Scenario 2: one customer (Kabulonga), three shops (Woodlands, Chilenje, Matero)

| Method | Road km | Trips / riders | Fuel | Courier cost | Time | Customer charge | Delivery margin |
|---|---|---|---|---|---|---|---|
| **Today:** three dedicated jobs | 26.0 (4.3 + 6.3 + 15.4) | 3 / 3 | 0.65 L (K21) | K158 (28 + 40 + 90) | 53 min; three arrivals | K90 | **−K68** |
| Today, each shop group at K200 or more | 26.0 | 3 / 3 | 0.65 L | K158 | 53 min | K0 | **−K158** |
| Batched: one multi-pickup run, per-job | 23.4 | 1 / 1 | 0.59 L (K19) | K150 | 87 min; one arrival | K170 by formula | +K20 |
| Scheduled: same run by an hourly rider already on shift | 23.4 | 1 / 1 | 0.59 L | about K87 | 87 min | K95–K125 | +K8 to +K38 |
| Hub: collect to hub, then deliver | 25.3 | 2 / 2 | 0.63 L (K21) | K185 (145 + 25 + 15 handling) | slower | — | **Worse than today** |
| Hub with shops dropping off | 2.7 for Convergeo | 1 / 1 | 0.07 L | K40 | next window | K45 | +K5. Shops carry about 22 km themselves. |
| Hybrid: Woodlands + Chilenje now; Matero separately | 23.1 | 2 / 2 | 0.58 L | K146 (56 + 90) | 38 min, then 53 min | — | — |
| **Model A:** the Matero item bought from a shop near the other two | 7.7 | 1 / 1 | 0.19 L (K6) | **K56** | 38 min; one arrival | K65 | **+K9** |

**Reading.** One run improves the experience (one arrival, one code, one cash payment) but saves only 5% of courier cost under per-job pricing, because the cross-town kilometres are still driven. The Matero leg is K90 of K158. The lever is the customer seeing, before checkout, that this item adds about K95 of delivery while the same item from a nearer shop adds about K15.

### 9.4 Scenario 3: ten customers, five shops, drops clustered in the east

| Method | Road km | Trips / riders | Fuel | Courier cost | Per order | Time | Customer charges (today) | Delivery margin |
|---|---|---|---|---|---|---|---|---|
| Ten dedicated jobs | 81.2 | 10 / up to 10 | 2.03 L (K67) | K497 | K50 | avg 33, max 49 min | K345 | **−K152** |
| Batched: two motorbike runs of five, per-job | 52.4 | 2 / 2 | 1.31 L (K43) | K394 | K39 | 126 and 103 min | K345 | −K49 |
| Batched: one car run of ten, per-job | 48.5 | 1 / 1 | — | K376 | K38 | 212 min | K345 | −K31 |
| Scheduled: two motorbike runs, **hourly riders** | 52.4 | 2 / 2 | 1.31 L | about K240 | K24 | same | K345 | **+K105** |
| Hub: collect in, one run out | 48.5 | 2 / 2 | 1.21 L | K431 incl. K50 handling | K43 | about 105 + 118 min | K345 | −K86 |
| Hub with shops dropping off | 22.8 | 1 / 1 | 0.57 L | K252 incl. handling | K25 | about 118 min after cut-off | K345 | +K93 |

**Reading.** With a real cluster, batching cuts distance by 35% and per-job cost by 21%. Buying rider time instead roughly halves the cost, if the hourly rate assumption holds. The relay hub is again worse than plain batching unless shops do the inbound leg.

### 9.5 Scenario 4: perishables, four orders, 60-minute promise

| Method | Road km | Trips | Courier cost | Slowest delivery | Customer charges | Delivery margin |
|---|---|---|---|---|---|---|
| Four dedicated | 14.5 | 4 | K107 | 23 min | K150 | +K43 |
| Two same-shop stacks of two | 10.4 | 2 | K84 | 30 min | K150 | +K66 |
| Round, hub, scheduled or third party | — | — | — | breaks the promise | — | **Not permitted** |

**Reading.** Stacking two orders from one shop saves 21% and stays inside 30 minutes, but only because both were ready together. That is the only batching allowed for perishables.

### 9.6 Scenario 5: intercity, Lusaka shop (Matero) to Ndola or Livingstone

Carrier price `X` is unknown. Passenger fares (K140–230 to Ndola, K200–350 to Livingstone, second-hand source) are context only and **must not be used as parcel prices**.

| Method | Lusaka first mile | Trunk | Destination | Convergeo cost | Time |
|---|---|---|---|---|---|
| Per-job rider to the depot | K62 (10.4 km) | `X` bus | customer collects | K62 + `X` | same or next day, plus collection |
| Daily combined depot run (4 parcels) | K36 each (K144 run) | `X` bus | customer collects | K36 + `X` | next departure after cut-off |
| Shop drops at the depot | K15 credit | `X` bus | customer collects | K15 + `X` | shop's schedule |
| Add door delivery at destination | as above | `X` bus | local rider `Y` (unknown) | + `Y` | + hours |
| Door-to-door courier or postal express | — | `X` courier | included | `X` courier | 48 hours cited for postal express (second-hand) |
| Dedicated vehicle from Lusaka | — | 321–472 km each way | — | Not sensible for one parcel | — |

**Customer price:** first mile + `X` × 1.05 + K10 handling, rounded up to K5, prepaid only. **Decision rule once quotes exist:** use the bus depot lane while first mile + `X` bus + K10 is less than `X` courier. Offer door delivery only in towns with a tested local partner. Convergeo's own lever is the first mile: K62 falls to K36 at four parcels a day and towards K15 when shops drop off.

### 9.7 Scenario 6: mixed readiness (Scenario 2's checkout; the Matero item needs four hours)

| Method | Courier cost | Customer experience | Handovers and cash payments |
|---|---|---|---|
| Three dedicated jobs, each when ready | K158 | two parcels in about 30 min, the third after about 5 h | 3 |
| Hold everything, one run | K150 (about K87 hourly) | everything at about 5.5 h | 1 |
| Split: two-shop run now, dedicated later | K146 | about 40 min, then about 5 h | 2 |
| **Hybrid: two-shop run now, late item on the evening round** | about K117 | about 40 min, then the evening window | 2 |
| Model A alternative for the late item | K56 | everything in about 40 min | 1 |

**Reading.** The default is "together" when the latest item still meets the window. Otherwise split, with the late item on the next round. For cash orders "together" is preferred because each extra handover is another cash event.

### 9.8 Volume: when does each form of batching pay?

Simulated days with shops and customers placed at random around the city centre (average shop-to-customer 8.4 road km [A]); 70% of orders can wait for a round [A]; two rounds a day; six parcels per rider; run limit 180 minutes.

| Orders a day | Can wait | Dedicated, K per order | Selective batching per-job, K per order (saving) | Share batched | Hourly riders, K per order (saving) |
|---|---|---|---|---|---|
| 5 | 3.6 | 52 | 51 (1%) | 7% | **61 (−17%)** |
| 10 | 6.9 | 52 | 51 (3%) | 15% | 42 (20%) |
| 20 | 14.0 | 53 | 50 (6%) | 30% | 36 (32%) |
| 40 | 28.1 | 53 | 47 (10%) | 43% | 33 (36%) |
| 80 | 57.0 | 53 | 45 (15%) | 59% | 32 (39%) |
| 160 | 114.2 | 52 | 42 (20%) | 72% | 31 (41%) |
| 320 | 223.9 | 53 | 40 (25%) | 78% | 29 (45%) |

**Break-even check for hourly riders** [D]: a block pays when (hourly rate × hours) ÷ parcels in the block is below the per-job cost. At K60 an hour and a 2-hour block, that is K120 ÷ K52, so **three or more parcels per block**. At K40 an hour it is two. This is why the Stage 1 trigger is "three parcels in most rounds and a real quote", not a date.

### 9.9 What the simulation says

1. **Low volume (up to 10 a day):** per-job couriers only. Do not batch across customers. Do not hire by the hour. Fix pricing, show delivered price, group by address.
2. **Medium volume (20 to 80 a day):** hourly riders on two fixed rounds become the main saving. A simple planner is enough until about 40 a day.
3. **High volume (160+ a day):** route solver, riders by sector, partner collection points, daily depot run.
4. **At every volume:** the customer choosing a nearer shop, and collection, beat any routing.
5. **Today's fees do not cover today's costs.** Average modelled per-job cost is about K52, above every band except the K65 one. Illustration [D] with a K300 basket [A] at 8% commission [S]: commission K24; with a K45 fee the delivery loses about K7 and the order contributes about +K17; with free delivery the order contributes about −K28.

---

## Deliverable 10: Phased implementation roadmap

Phases 0 and 1 are worth doing at pilot volume. Phases 2 to 5 each start when their trigger is met.

### Phase 0: audit and immediate operational fixes

| Item | Detail |
|---|---|
| **Scope** | (a) **In progress (pilot build):** delivery fee kept as platform revenue; cash orders not auto-completed before cash is booked; shops cannot confirm platform cash; prepaid auto-release blocked for failed deliveries; other towns no longer accepted at Band B; shop "ship" cannot bypass the courier job. (b) **Proposed:** real cost per delivery and weekly margin report; second attempt, return to shop and restock; logistics and cash permissions; combined "handed over + cash" action; cash custody per courier, remittances, daily cash-up, cash cap; "ready for collection" step; pickup from the branch that holds the stock; board grouped by checkout and address; alerts for silent shops and riders; "cancelled" and "delivered" customer messages; cancel cascades to the courier; workflow error alerts; hide the legacy dispatch panel; documentation corrections. (c) **Founder, no code:** raise the free-delivery threshold; collect real quotes; sign two courier agreements; verify live workflows, templates and SMS. |
| **Dependencies** | Founder decisions 1, 2 and 4. Live verification of n8n, WhatsApp templates and SMS. |
| **Affected apps and services** | API (`services/dispatch`, `services/orders/state.py`, `services/payments/cod.py`, `services/notifications/events.py`, `routers/admin_dispatch.py`, `routers/vendor_orders.py`); admin app (dispatch board, cash-up screen); vendor app (ready button); n8n (stale alert, new timers, error workflow). |
| **Database changes** | Columns on `dispatch_requests` and `orders`; new `courier_remittances`; two permission names; configuration keys. All additive. |
| **API changes** | The Phase 0 rows in 7.5. |
| **Complexity** | Medium overall. About eight work packages, each S or M. |
| **Risks** | Touching money paths during a live pilot. Changing the order state machine (adding "ready" for delivery) could affect in-flight orders. |
| **Acceptance criteria** | Every delivered order has an actual cost. Every kwacha of cash is recorded against a courier, then matched to a remittance, with a daily difference of zero. A failed delivery can be re-sent or returned without leaving the system, and stock comes back. A non-founder operator can run a full delivery day. No order sits in any state without a timer watching it. The weekly margin report is produced. |
| **Testing** | Failure-path tests for every money and state change (cash booked twice, remittance larger than cash held, third attempt refused, return without acknowledgement). Role tests: logistics operator cannot touch escrow; shop cannot confirm cash. Repeat-safety tests on each timer. One end-to-end drill on staging: order, ready, collect, fail, re-attempt, deliver, cash, remit, cash-up. |

### Phase 1: foundational logistics improvements

| Item | Detail |
|---|---|
| **Scope** | Area picker and remembered customer area. One quote function (shop-to-customer distance, one fee per address, discount budget) used by cart, checkout and order creation. Delivered price and arrival on product pages and cart, with "same product, nearer shop" and "add from shops already in your cart" prompts. Service levels and two cut-offs. Consignments with one code per address. Size and handling class on listings; preparation minutes per branch. Riders list and one-time rider link; code released on "arrived"; shop confirms handover. Cash custody inside the ledger. Mobile-money payment at the door, confirmed through Lenco. Refusal history. Auto-cancel for silent shops. Holiday and rain switch. Morning stock check. Single-transaction custody events. |
| **Dependencies** | Phase 0 complete. Real courier quotes to set the formula. Founder decisions 1 and 3. Legal opinion on data location and courier licence. |
| **Affected apps and services** | Customer app (product page, cart, checkout, tracking; must stay inside the 150 KB script budget); vendor app (listing attributes, handover); admin app (areas, pricing settings, riders); API (new `services/logistics/` with quote, promise, consign, custody); n8n (cut-off timer, nudges). |
| **Database changes** | `delivery_areas`, `delivery_quotes`, `delivery_consignments`, `courier_riders`, rider link tokens; columns on `orders`, `vendor_listings`, `vendor_locations`, `dispatch_requests`; ledger accounts. |
| **API changes** | The Phase 1 rows in 7.5. Checkout's fulfilment step takes a quote reference. |
| **Complexity** | High. This is the largest phase: roughly ten to twelve work packages across all three apps. |
| **Risks** | Customers see different delivery prices: communicate it. The quote must be identical at cart, checkout and order creation, or orders are refused. Listing attributes default by category and some will be wrong. The rider link exposes customer contact details if it leaks, so it must expire and be single-job. |
| **Acceptance criteria** | A three-shop checkout to one address produces one consignment, one code, one cash payment and one delivery line in the cart. Fee error against actual cost within ±15%. Every order has a stored quote with estimated cost. Rider self-closes at least 80% [A] of deliveries without operations typing a code. On-time rate against the promised window is measured and at least 90% [A]. Free delivery is funded only from the discount budget. |
| **Testing** | Property tests on the quote function (never above the sum of separate fees; never below the minimum; identical result at all three call sites). Migration tests (additive, reversible). Rider-link security tests (expiry, wrong job, reuse). Lighthouse and bundle budgets on customer routes. Shadow mode: compute new quotes beside old fees for two weeks before switching. End-to-end multi-shop journeys. |

### Phase 2: intelligent batching and route optimisation

| Item | Detail |
|---|---|
| **Scope** | Runs and stops. Hourly-rider blocks. Simple insertion planner for rounds, then OR-Tools in a separate worker when volume warrants. Economy and Express options. Cost sharing across a run and savings measurement. Exception queue. Return transport. Perishable lane (hot food, flowers) if such shops are onboarded. Per-item status only if ruling R13's trigger is met. |
| **Dependencies** | Stage 1 trigger met: 10+ scheduled orders a day for two weeks, three parcels in most rounds, a real hourly quote. Rider link in use. Cash custody live. Courier-licence position confirmed. |
| **Affected apps and services** | API (planner, costing); a new worker container on the same host; admin app (run board, release plan); customer app (new options); n8n (cut-off planner). |
| **Database changes** | `delivery_runs`, `delivery_run_stops`, `delivery_exceptions`; cost columns on `dispatch_requests`; optional `order_items.fulfilment_status`. |
| **API changes** | Plan-round timer endpoint; run management; exception endpoints. |
| **Complexity** | High. |
| **Risks** | Hiring by the hour before volume supports it loses money (K61 against K52 at five orders a day [D]). One failed stop delays a shared run. The 4 GB host may need a second small machine for the solver. |
| **Acceptance criteria** | Courier cost per scheduled order at least 20% [A] below the per-job baseline for four consecutive weeks. Rider time in use at least 60% [A] of paid time. No Express or perishable promise broken because of batching. Plans can be replayed from stored inputs. |
| **Testing** | Planner tests on recorded real days (replay). Constraint tests: cash cap, capacity, duration, pickup before drop. Solver time-limit and fallback-to-simple-planner tests. Load test with the solver running beside the API. |

### Phase 3: collection points and third-party transport

| Item | Detail |
|---|---|
| **Scope** | Three to five partner collection points (customer collection, shop drop-off, failed-delivery holding, returns) with scan-in and scan-out. Manual intercity lane: carrier list, rate table from real quotes, bookings with waybill photo, depot run, arrival confirmation, carrier scoring. Destination-town collection first; door delivery only where a local partner has been tested. |
| **Dependencies** | Depot quotes and test parcels (about 10 per corridor). Written agreements covering liability and data. Prepaid checkout working at volume. Founder decision 5. Trigger: about 40+ orders a day for points; about 5 upcountry orders a week per corridor for the lane. |
| **Affected apps and services** | Customer app (collect-from-point option, intercity option, tracking text); admin app (carriers, bookings, points); a scan page for point operators; API (`carriers.py`); n8n (overdue timer). |
| **Database changes** | `collection_points`, `carrier_services`, `transport_bookings`, `custody_events`; `courier_partners.kind`. |
| **API changes** | Carrier, booking and point-scan endpoints. Quote function gains the intercity and point branches. |
| **Complexity** | Medium for software. High for operations (partners, agreements, liability). |
| **Risks** | Undefined carrier liability [S: Agent 5]. No tracking beyond photos and phone calls. Point partners losing parcels. Rainy-season delays on non-trunk roads. |
| **Acceptance criteria** | Every intercity parcel has a waybill photo, a declared value and an arrival confirmation. Loss and damage below 1% [A] across the first 100 parcels. Each carrier has a measured on-time score. Point parcels are scanned in and out with no unexplained differences. |
| **Testing** | Booking state tests including overdue and lost. Scan permission tests (operator sees only that point's parcels). A live corridor trial with low-value test parcels before customer orders. |

### Phase 4: predictive logistics and automated optimisation

| Item | Detail |
|---|---|
| **Scope** | Preparation-time and arrival predictions per shop and area pair. Demand forecast per area and hour to size rider blocks. Road distances from OSRM. Area shapes with PostGIS. Automatic release of plans within guardrails. Re-planning with rider positions, if a rider app exists by then. Offline AI suggestions of similar products for the delivered-price comparison, shown only above 95% measured accuracy [A]. |
| **Dependencies** | A few thousand completed deliveries with clean timestamps and costs. Phase 2 in steady use. |
| **Affected apps and services** | API (estimates), worker (solver, OSRM), admin app (analytics dashboard), optionally a rider app. |
| **Database changes** | PostGIS extension and area shapes; estimate tables; rider position log if adopted. |
| **API changes** | Estimate inputs to the quote function; analytics endpoints. |
| **Complexity** | High. |
| **Risks** | Building models before the data supports them. Privacy of rider location. Memory on the host. |
| **Acceptance criteria** | Arrival prediction error beats the simple average on held-back data. Fee error within ±10%. Each automated decision can be explained from stored inputs. |
| **Testing** | Back-testing on history. A/B comparison against the rule-based planner. Privacy review of location data. |

### Phase 5: nationwide scaling and regional expansion

| Item | Detail |
|---|---|
| **Scope** | Service areas and partners per town (Copperbelt first, by corridor volume). Corridor contracts. A Lusaka sorting site only if a corridor fills a vehicle daily. Courier APIs where verified. Cross-border groundwork: customs, duties, currency. |
| **Dependencies** | A corridor with 20+ parcels a day, or 300+ orders a day overall. Legal and tax advice per country. A payment provider beyond Lenco where needed (the payment code already has a seam for this). |
| **Affected apps and services** | All apps (town selection, per-town pricing); API (multi-area settings). |
| **Database changes** | Town or region on areas, zones, partners and settings; currency and country where needed. |
| **API changes** | Region-aware quotes and promises. |
| **Complexity** | High; mostly commercial and operational. |
| **Risks** | Spreading thin before Lusaka is profitable per order. Regulatory differences. |
| **Acceptance criteria** | Each new town reaches positive delivery margin within a set period, or is switched back to collection-only. |
| **Testing** | Per-town pilot with a volume cap before opening. |

---

## Appendix A: Measures and starting targets

All targets are [A] and should be reset once four weeks of real data exist.

| Measure | Definition | Pilot target | Stage 2 target |
|---|---|---|---|
| Delivery cost per order | Actual courier, point and carrier cost ÷ delivered orders | at or below the average fee | 15% below the average fee |
| Delivery margin | (Fees − delivery costs) ÷ fees | 0% or better | 10% or better |
| Discount rate | Delivery discounts ÷ commission | 50% or less | 35% or less |
| Quote accuracy | (Actual − estimated cost) ÷ estimated | within ±15% | within ±10% |
| Collection time | Ready to collected | median 45 min | median 30 min |
| On-time rate | Delivered inside the promised window | 90% | 95% |
| First-attempt failure | Failed or refused ÷ attempts, by payment method | 8% for cash | 5% |
| Cash integrity | Cash remitted by next day ÷ cash collected; difference | 100%; K0 | same |
| Shop ready on time | Ready by the promised time | 85% | 92% |
| Rider wait at shop | Arrival to collected | median 10 min | median 6 min |
| Orders consolidated | Orders sharing a consignment or run ÷ delivery orders | track | 40% of those that can wait |
| Parcels per run; rider time in use | — | not applicable | 3 or more; 60% or more |
| Carrier performance | On-time departure, transit days, loss, cost difference, per carrier | score every carrier | — |
| Complaints and damage | Per 100 deliveries | 3 or fewer | 2 or fewer |
| Delivery satisfaction | One-tap WhatsApp rating | 4.3 of 5 | 4.5 of 5 |

**Telling the sources of saving apart.** Store a small set of cost figures per order when it is planned, and one when it is completed. The differences are the attribution, with no modelling afterwards.

| Saving | How it is measured | Available from |
|---|---|---|
| Nearer shop (Model A) | Per-job cost from the shop first in the cart, minus per-job cost from the shop finally chosen, for carts where a suggestion was shown and accepted | Phase 2 |
| Consolidation and batching | Sum of each order's per-job cost alone, minus the cost of the grouping actually used | Phase 1 (same address), Phase 2 (rounds) |
| Route optimisation | Cost of the grouping in arrival order, minus the cost of the planned order | Phase 2 |
| Hourly riders | Planned cost at per-job rates, minus planned cost at hourly rates | Phase 2 |
| Third-party transport | Door-to-door courier quote, minus (first mile + carrier + handling) | Phase 3 |
| Execution loss | Actual cost minus planned cost: late shops, failed attempts, re-sends. Reported as a cost, separately. | Phase 0 (actual), Phase 2 (planned) |

## Appendix B: Limits of this blueprint

- **Not verified live.** No agent had production access. Whether workflows are active, templates approved, SMS enabled and payouts switched on is unknown.
- **No real courier prices.** Every cost rests on a curve fitted to second-hand car ride-hail fares. The hourly rider rate has no basis at all.
- **No parcel tariffs, liability terms or APIs** were found for any Zambian carrier. "Platinum", "TownStar", "Likili", "Juldan" and "ZamCargo" were not found under those names. Three operator websites could not be opened.
- **Legal points are second-hand.** The data-protection summary comes from a law-firm page, not the Act. Courier licence fees conflict between sources. Neither is legal advice.
- **The volume simulation** assumes demand spread evenly around the city centre and was not re-run by the lead agent.
- **International comparisons** (Jumia, Takealot, Amazon, Uber Eats) are cited in the Agents 1+4 report with links. Statements about Alibaba, DHL and Bolt Food there are general knowledge and were not researched.
- **Pilot-build fixes** were confirmed as present on the branch for two of the six items by reading its commit list (delivery fee as platform revenue; cash orders not auto-completed). The other four are taken as in progress on the lead's instruction.

---

## Approval requested: highest-priority implementation items

Nothing below will be built without the founder's approval. Items are in recommended order. Effort: S = up to 2 days, M = 3 to 7 days, L = 2 to 4 weeks. The six pilot-build fixes are already in progress and are not listed.

| # | What | Why | Effort | Risk |
|---|---|---|---|---|
| 1 | **Switch off free delivery for now** by raising the threshold in configuration. | Each free delivery loses K28–K90 against K6–K24 of commission. No code needed. | S | Low. Some customers may notice; say so plainly at checkout. |
| 2 | **Record real courier cost on every delivery, with a weekly fee-versus-cost report.** | Without it nothing else can be measured or priced. | S | Low. |
| 3 | **Cash custody: cash recorded per courier, remittance record, daily cash-up, cash cap of K1,500.** | The largest operational risk. Cash held by riders is invisible today. | M | Medium. Touches money paths; needs failure-path tests. |
| 4 | **Second attempt and return to shop after a failed delivery, with restock.** | Every "customer not home" is currently an off-system workaround. | M | Medium. Changes job and order transitions. |
| 5 | **Logistics and cash permissions, and one combined "handed over + cash" action.** | Removes the founder as the single point of failure; lets a second operator run deliveries without full admin power. | M | Low to medium. |
| 6 | **Alerts and messages:** silent shop (1 h, 2 h), silent rider (45 min, 120 min), "cancelled" and "delivered" customer messages, cancel cascades to courier, workflow error alerts. | Customers currently wait for orders that were cancelled; riders can go silent unnoticed. | M | Low. Needs WhatsApp template approval. |
| 7 | **"Ready for collection" step, pickup from the correct branch, board grouped by checkout and address.** | Stops riders arriving early or at the wrong branch; lets operations send one rider for a multi-shop checkout by hand. | M | Medium. Adds an order state for delivery orders. |
| 8 | **New price formula:** shop-to-customer distance, one fee per address, commission-funded discount, area picker, stored quote. Run in shadow mode for two weeks first. | Today's fees ignore the leg that costs money and charge three fees on one checkout. | L | Medium to high. Customer-visible price change; must be identical at cart, checkout and order creation. |
| 9 | **Delivered price before checkout:** delivery cost and arrival per shop on product page and cart; nearer-shop prompt; customer always chooses. | The largest cost lever found. Removes distance instead of managing it. | L | Medium. Touches the customer app's performance budget and search ranking. |
| 10 | **Delivery windows and consignments:** two daily cut-offs; one visit, one code, one cash payment per address. | Creates the density that later batching needs; fewer cash events. | L | Medium. Handover code moves from job to consignment. |
| 11 | **Riders list and one-time rider link;** code released on "arrived"; shop confirms handover. | Closes deliveries without an operator typing codes; gives proof at pickup; attributes parcels and cash to a person. | M to L | Medium. The link exposes contact details if leaked; must expire. |
| 12 | **Size and handling class on listings; preparation minutes per branch.** | Needed to tell bike from car and to make honest promises. | M | Low. Defaults by category will sometimes be wrong. |
| 13 | **Mobile-money payment at the door, confirmed through Lenco; K5 prepaid discount; refusal history.** | Cuts the cash riders carry and the cost of refusals. | M | Medium. Payment confirmation must come from the platform, never from the customer's SMS. |
| 14 | **Founder actions, no code:** ten or more real courier quotes and an hourly rate; two courier agreements with liability and data clauses; depot and post-office parcel quotes; exact names for "Platinum" and "TownStar"; legal opinion on data location and courier licence; live check of workflows, templates and SMS. | Every cost figure and the whole intercity lane depend on these. | About 1–2 weeks of founder time | Low. |
| 15 | **Later, each when its trigger is met:** hourly riders and round planner (Phase 2); collection points and manual intercity lane (Phase 3). | Not worth building before the volume exists. | L each | Building early loses money. |

**Suggested first approval:** items 1 to 7 and item 14. They stop losses, make cash traceable and remove the single point of failure. Items 8 to 13 follow as Phase 1 once real quotes are in hand.
