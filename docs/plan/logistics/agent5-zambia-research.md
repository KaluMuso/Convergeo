# Agent 5: Zambia Logistics and Commercial Research (Model E input)

Prepared for: Convergeo logistics brief (`/home/claude/logistics/brief.md`, Agent 5 and Model E)
Research method: read-only web research (WebSearch and WebFetch). All sources accessed **13 Nov 2026** unless stated.
Status labels used throughout:

- **CONFIRMED**: stated in a source I fetched, with URL. Reliability of the source is noted.
- **PUBLICLY AVAILABLE SERVICE**: the operator offers it to any customer (no partnership needed), but details are only partly verified.
- **POTENTIAL PARTNERSHIP**: plausible commercial arrangement; nothing exists today and nothing public confirms the operator would agree.
- **NOT FOUND**: I searched and found no public evidence. This is not proof the thing does not exist.

## 0. Headline findings (read this first)

1. **There is almost no publicly verifiable pricing for intercity bus-parcel services in Zambia.** I found no published parcel tariff for Power Tools, Mazhandu, Shalom, CR Holdings/Euro-Africa, Kobs or any other coach operator. The one article that discussed luggage costs states that "no Zambian regulator publishes a comparable table of luggage charges" (I am Beezy blog, 16 Aug 2026; low reliability, see §9). Prices must be obtained by calling or visiting depots.
2. **No coach operator has a verified API or online parcel booking.** Nothing I found shows any intercity bus operator, Zampost, or DHL Zambia domestic service offering an API for domestic parcels. DHL has a developer portal, but its domestic availability in Zambia is not shown.
3. **"Platinum" and "TownStar / Tom Star" could not be verified.** Searches for "Platinum" coach and "Town Star / Townstar / Tom Star" in Zambia returned no operator by those names. The founder should supply the exact registered name or a phone number before they are treated as candidates.
4. **Likili and Juldan: NOT FOUND** as parcel or coach operators in any source I could read.
5. **Zampost (Zambia Postal Services) is the only national network with a documented, publicly described domestic parcel product** (EMS, 146 post offices per its own site), but its page gives no prices, no tracking detail for EMS, and no liability terms.
6. **Yango Delivery operates in Lusaka** (parcel and cargo via app; cargo tariff exists), but I found no evidence of a Zambia merchant API, and no published tariff.
7. **Verified fuel prices (Nov 2026)** are available from secondary media citing the ERB; the ERB's own PDF was not machine-readable to my tools (§7).

## 1. Operator register (summary)

| Operator | Type | Status | Parcel service evidenced? | Price published? | API / online booking? |
|---|---|---|---|---|---|
| Power Tools (Power Tools Logistics Ltd / "Power Tools Courier") | Coach + courier arm | PUBLICLY AVAILABLE SERVICE (coach); courier arm only partly evidenced | Blog says it runs a "cargo service" with no details; employer ad names "Power Tools Courier" | NOT FOUND | NOT FOUND (own website blocked, see §2.1) |
| Mazhandu Family Bus Services | Coach | PUBLICLY AVAILABLE SERVICE (passenger) | NOT FOUND | NOT FOUND | NOT FOUND |
| Shalom Bus Services | Coach | PUBLICLY AVAILABLE SERVICE (passenger) | NOT FOUND | NOT FOUND | NOT FOUND |
| CR Holdings / Euro-Africa Bus Services | Coach | PUBLICLY AVAILABLE SERVICE (passenger) | NOT FOUND (only passenger luggage allowances mentioned) | NOT FOUND | NOT FOUND |
| Kobs Coach Services | Coach | PUBLICLY AVAILABLE SERVICE (passenger) | NOT FOUND | NOT FOUND | NOT FOUND |
| Ticklays Coach Service | Coach (Lusaka to Mwinilunga) | PUBLICLY AVAILABLE SERVICE (passenger) | NOT FOUND | NOT FOUND | NOT FOUND |
| Juldan | Unknown | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND |
| Likili | Unknown | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND |
| "Platinum" | Unverified name | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND |
| "TownStar" / "Tom Star" | Unverified name | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND |
| Zampost EMS and Domestic Parcels | National postal operator | PUBLICLY AVAILABLE SERVICE | Yes (EMS, Domestic Parcels) | NOT FOUND (weight-based, "visit your nearest post office") | Track and Trace page listed; no API found |
| Zampost subsidiaries (Post Bus Company Ltd, Zampost Freight and Forwarding) | Bus / freight | NOT FOUND beyond names | NOT FOUND | NOT FOUND | NOT FOUND |
| DHL Express Zambia | International express | PUBLICLY AVAILABLE SERVICE (international) | Domestic Zambia NOT FOUND | NOT FOUND | DHL developer portal and MyDHL+ exist; Zambia domestic coverage not shown |
| FedEx Express Zambia | International express | PUBLICLY AVAILABLE SERVICE (international) | Domestic NOT FOUND | NOT FOUND | NOT FOUND for Zambia |
| Aramex Zambia | International | Page exists; content not verified | NOT FOUND | NOT FOUND | NOT FOUND |
| Mercury Express Logistics | Courier | Named in US government guide | International only per guide | NOT FOUND | NOT FOUND |
| Lechwe Express Logistics | Courier / freight forwarder (Lusaka) | PUBLICLY AVAILABLE SERVICE (directory listing) | "Courier and postal delivery to major destinations daily" (self-description) | NOT FOUND | Online tracking by airway bill number (self-description); no API stated |
| Yango Delivery (Lusaka) | App-based parcel / cargo | PUBLICLY AVAILABLE SERVICE | Yes (motorbike to van) | NOT FOUND | No Zambia API evidenced (see §2.7) |
| inDrive | Ride-hailing | Courier NOT FOUND in Zambia | Courier launched in Zimbabwe, not Zambia | n/a | n/a |
| Bolt | Ride-hailing | Courier / food NOT FOUND in Zambia | Lusaka pilot was ride-hailing only (Oct 2023) | n/a | n/a |
| Glovo | n/a | NOT FOUND in Zambia | n/a | n/a | n/a |
| Afridelivery | Local on-demand delivery (Lusaka, Kitwe) | PUBLICLY AVAILABLE SERVICE (dated article) | Yes (commission-based platform) | NOT FOUND | App exists; API NOT FOUND |
| ZamCargo | Unknown | NOT FOUND (see §2.9) | NOT FOUND | NOT FOUND | NOT FOUND |

## 2. Operator detail

### 2.1 Power Tools (Power Tools Logistics Limited / Power Tools Courier)

| Item | Finding | Status | Source |
|---|---|---|---|
| Routes | Lusaka to Copperbelt (Kapiri Mposhi, Kabwe, Kitwe, Ndola), Nakonde, Chinsali, Isoka; Mpulungu corridor (Mkushi, Serenje, Mpika, Kasama, Mbala, Mpulungu); Luwingu. The blog's route grouping contains errors (e.g. Chinsali and Isoka listed under Copperbelt), so treat as indicative. | CONFIRMED (low reliability: third-party blog, no date on page content) | https://travelertz.blogspot.com/2025/03/power-tools-coach-power-tools-bus.html |
| Routes (directory) | Lusaka to the Copperbelt, Nakonde, Mpulungu, Luwingu. | CONFIRMED (directory listing) | https://bizbwana.com/directory/transport/buses-and-coaches |
| Parcel / cargo | Blog says the company "runs a cargo service with timely delivery" across its routes; no rates, no how-to-send, no tracking. | CONFIRMED that a claim exists; service details NOT FOUND | https://travelertz.blogspot.com/2025/03/power-tools-coach-power-tools-bus.html |
| Corporate entity | Employer advertising a "Ticket Seller" as **Power Tools Logistics Limited / Power Tools Courier**, Lusaka; email domain `powertoolscourier.co.zm`. Ad posted 6 Mar 2024. This is evidence that a courier-branded entity exists; it does not describe parcel handling. | CONFIRMED (job board) | https://www.greatzambiajobs.com/jobs/job-detail/job-Ticket-Seller-job-at-Power-Tools-Courier-57554 |
| Depots | NOT FOUND | NOT FOUND | n/a |
| Contact | Only HR emails found; no operations or parcel phone number. | NOT FOUND | n/a |
| Prices, liability, API | NOT FOUND | NOT FOUND | n/a |
| Official website | `https://powertoolscourier.co.zm` could not be read: the fetch was blocked (permission request unanswered). **Not read; the founder or lead agent should open it manually.** | BLOCKED | n/a |

Assessment: strongest candidate for the northern corridor (Lusaka to Kabwe, Kapiri Mposhi, Copperbelt, Kasama, Nakonde) because it appears to have a courier-branded arm, but everything beyond that is unverified.

### 2.2 Mazhandu Family Bus Services

| Item | Finding | Status | Source |
|---|---|---|---|
| Routes | Copperbelt (Kitwe, Ndola), Livingstone, Kazungula (Botswana border), Katima Mulilo (Namibia border), one daily Mongu coach, cross-border Lusaka to Johannesburg. | CONFIRMED (third-party; page published 11 Dec 2017, last modified 4 Dec 2024) | https://safaribay.net/mazhandu-family-bus/ |
| Hub | Intercity Bus Terminus, Dedan Kimathi Road, Kamwala, Lusaka. Livingstone terminus: Mosi-oa-Tunya Road. | CONFIRMED | https://safaribay.net/mazhandu-family-bus/ ; https://www.zambiatourism.com/transport/bus/ |
| Phone numbers (as published by safaribay.net) | +260 977 806 060, +260 977 489 414, +260 977 619 698, +260 977 784 109. Third-party listing; verify before use. | CONFIRMED (low reliability) | https://safaribay.net/mazhandu-family-bus/ |
| Office hours | 08:00 to 17:00 every day (third-party). | CONFIRMED (low reliability) | https://safaribay.net/mazhandu-family-bus/ |
| Schedule | Lusaka to Livingstone buses "half hourly from 6am" to 11:30 (nine daily services) per the Zambia Tourism page; the page does not name the operator. | CONFIRMED for the corridor, not for Mazhandu | https://www.zambiatourism.com/transport/bus/ |
| Parcel service | NOT FOUND. The fetch of the safaribay page states no parcel service. | NOT FOUND | n/a |
| Official website `mazhandu.com` | Fetch blocked (permission request unanswered). **Not read.** | BLOCKED | n/a |

### 2.3 Shalom Bus Services, CR Holdings / Euro-Africa, Kobs, Ticklays

| Operator | Routes and facilities | Parcel / price | Source |
|---|---|---|---|
| Shalom Bus Services | Lusaka to Livingstone and Johannesburg, Lusaka to Mongu, Lusaka to Nakonde; air-conditioned, "strict scheduling" (directory description) | Parcel NOT FOUND; price NOT FOUND | https://bizbwana.com/directory/transport/buses-and-coaches |
| CR Holdings | 20 towns served. Daily: 3 buses to Copperbelt, 1 to Solwezi, 2 to Livingstone. Stations: Lusaka (Kamwala intercity terminal), Ndola (Broadway Shopping Centre), Kitwe (Railway Station), Livingstone (Mosi-oa-Tunya Road). Agent phone numbers are published for Chingola, Choma, Kabwe, Kapiri Mposhi, Kazungula, Kitwe, Lusaka, Mansa, Mazabuka, Mufulira, Ndola, Sesheke, Solwezi. Page undated. | Only passenger luggage allowances are mentioned; parcel NOT FOUND | https://bizbwana.com/orgs/cr-holdings |
| Euro-Africa Bus Services | Seven days a week; hourly departures from Lusaka or Kitwe (directory description); membership scheme | Parcel NOT FOUND | https://bizbwana.com/directory/transport/buses-and-coaches |
| Kobs Coach Services | Lusaka to Lilongwe (Malawi); Lusaka to Ndola, also serving Chipata to Ndola passengers | Parcel NOT FOUND | https://bizbwana.com/directory/transport/buses-and-coaches |
| Ticklays Coach Service | Daily Lusaka to Mwinilunga, departures from 05:30 then 10:00 and every two hours | Parcel NOT FOUND | https://bizbwana.com/directory/transport/buses-and-coaches |

Note on CR Holdings: the published agent network (Mansa, Solwezi, Kabwe, Chingola, Mufulira, Choma, Mazabuka, Sesheke, Kazungula) is the widest town-level footprint I found in a single source, which is useful for planning a pick-up-at-agent model, but it is passenger ticketing and I have no evidence the agents accept parcels.

### 2.4 Zampost (Zambia Postal Services Corporation)

| Item | Finding | Status | Source |
|---|---|---|---|
| Network size | "146 Post Offices spread across the country" (Zampost). A US government guide says 144 post offices, and the EMS page says "more than 150 branches". Treat as roughly 145 to 150. | CONFIRMED (figures differ across sources) | https://zampost.com.zm/aboutUs.html ; https://trade.gov/country-commercial-guides/zambia-distribution-and-sales-channels ; https://zampost.com.zm/Ems.html |
| EMS | Sent from and collected at any post office counter, or collected from the customer's premises. Door-to-door priority mail that "endeavours to deliver". Charges based on weight; no figures on the page. | CONFIRMED | https://zampost.com.zm/Ems.html |
| Weight limits | International parcels max 30 kg. Domestic items "can exceed 30 kg" but no maximum is stated. | CONFIRMED | https://zampost.com.zm/Ems.html |
| Delivery time | US government guide: domestic EMS delivery "same-day or within 48 hours depending on distance" (guide last published 2026-03-23). Zampost's own page gives no times (a standards table exists only as an image). | CONFIRMED (secondary) | https://trade.gov/country-commercial-guides/zambia-distribution-and-sales-channels |
| Prices | NOT FOUND | NOT FOUND | https://zampost.com.zm/Ems.html (says visit nearest post office) |
| Liability / claims limits | NOT FOUND. Only statement: senders of prohibited items lose the right of claim; prohibited list at zampost.com.zm/prohibited.html (not fetched). | NOT FOUND | https://zampost.com.zm/Ems.html |
| Tracking | "Track & Trace: local and international mail tracking" is a menu item; whether it covers domestic EMS is not stated. | PARTLY CONFIRMED | https://zampost.com.zm/aboutUs.html |
| Customer care | 0955-007678; Mon to Fri 08:00 to 17:00, Sat 08:00 to 13:00, closed Sun and public holidays. Email customercare@zampost.com.zm. | CONFIRMED | https://zampost.com.zm/Ems.html ; https://zampost.com.zm/aboutUs.html |
| Agency model | "Third-party businesses served on an agency basis, using Zampost's countrywide network as a retail channel". This is the strongest documented hook for a partnership. | CONFIRMED | https://zampost.com.zm/aboutUs.html |
| Subsidiaries | Post Bus Company Limited, Zampost Freight and Forwarding, Zampost Travel and Tours. No routes or services found. | NOT FOUND beyond names | https://zampost.com.zm/aboutUs.html |
| API / bulk booking | e-Zampost (ezampost.co.zm) is linked but its content is unknown (fetch blocked). API NOT FOUND. | BLOCKED / NOT FOUND | n/a |

Assessment: PUBLICLY AVAILABLE SERVICE with a stated agency channel. It is the only provider with a post-office presence in most district towns. Reliability evidence: none found in this research (no on-time statistics, no complaint data).

### 2.5 DHL, FedEx, Aramex, Mercury Express

| Provider | Finding | Status | Source |
|---|---|---|---|
| DHL Express Zambia | Door-to-door express "on the next possible business day"; ServicePoint locator, MyDHL+ portal, API and Shopfront integrations, Developer Portal (developer.dhl.com). The Zambia page lists no addresses and does not confirm domestic Zambia express. | International: CONFIRMED. Domestic Zambia: NOT FOUND. API for domestic Zambia: NOT FOUND | https://www.dhl.com/zm-en/home/express.html |
| FedEx Express Zambia | Conditions of Contract for "FedEx Express Zambia Limited" and a Zambia customer-support site exist. Domestic parcels and API for Zambia not verified. | PUBLICLY AVAILABLE SERVICE (international) | https://www.fedex.com/en-zm/connect.html ; https://www.fedex.com/content/dam/fedex/meisa-middle-east/downloads/FedEx_Conditions_of_Contract_ZM.pdf (not read in full) |
| Aramex | A Zambia shipping page exists (aramex.com/zm/en/ship/send-shipments); not read. | NOT VERIFIED | https://www.aramex.com/zm/en/ship/send-shipments |
| Mercury Express Logistics | Named with DHL and FedEx as offering international delivery to and from Zambia; typical delivery 1 to 4 days regional and Europe, 4 to 7 days US and Canada. | CONFIRMED (international only) | https://trade.gov/country-commercial-guides/zambia-distribution-and-sales-channels |

Assessment: international express carriers are not a practical intercity e-commerce channel unless a domestic product is confirmed with each carrier in writing.

### 2.6 Lechwe Express Logistics and other forwarders

| Item | Finding | Status | Source |
|---|---|---|---|
| Lechwe Express Logistics | Lusaka-based; "courier and postal delivery to major destinations daily"; collects and delivers; proof of delivery; online tracking by airway bill number; warehouse Plot 37061, Mwambeshi Road, Chinika Industrial Area, Lusaka; office at Freight Village, Kenneth Kaunda International Airport. No phone or email listed. Self-description on a directory; undated. | CONFIRMED as self-described claims; reliability unverified | https://bizbwana.com/orgs/lechwe-express-logistics |
| DSV Zambia | Offices in Lusaka and Ndola; international freight forwarder. Not an e-commerce parcel carrier. | PUBLICLY AVAILABLE SERVICE (freight) | https://www.dsv.com/en/countries/africa/zambia |
| Zambia Railways | Freight rail operator; seeking private partnerships to add capacity. Not a parcel service. | Freight only | https://www.freightnews.co.za/article/zambia-railways-seeks-private-partnerships-build-additional-capacity |

### 2.7 Yango Delivery (Lusaka)

| Item | Finding | Status | Source |
|---|---|---|---|
| Presence | Yango Cargo Express launched in Lusaka (with Abidjan and Accra), article dated 28 Mar 2024; vehicles "suited to transport items of large size and weight", ordered in the app's Delivery section; upfront pricing. | CONFIRMED | https://techlabari.com/?p=53673 |
| Cargo couriers | First offline event for Cargo tariff partner couriers on 18 Dec 2024 in Lusaka; RTSA led road-safety training; Country Manager Dennis Aremo; more than 500 couriers took part in 2024 events. | CONFIRMED | https://www.times.co.zm/?p=135693 |
| Vehicle range | "A motorbike for a quick city delivery or a larger vehicle for bulkier shipments"; 50% first-order discount for new users (undated). | CONFIRMED | https://interactive.nkwazimagazine.com/?p=13270 |
| Coverage | Lusaka only is named in dated sources. One undated article says Zambia-wide ("across the country"). Intercity: NOT FOUND. | Lusaka CONFIRMED; elsewhere NOT FOUND | sources above |
| Tariff | No minimum fare or per-km rate published in any Zambia source I read. | NOT FOUND | n/a |
| API | Yandex documents a Go Delivery API (sign a delivery agreement, get a corporate account and token); the page does not list supported countries and does not mention Zambia. A 2026 merchant-integration article describes the REST API only for Senegal (`X-Country: SN`). **No evidence of a Zambia API.** Must be asked of Yango Zambia directly. | NOT FOUND for Zambia | https://yandex.com/dev/logistics/api-go-delivery ; https://kolonell.com/en/blog/yango-delivery-senegal-merchant-integration-2026 |
| Other Yango services | Taxi and food delivery; card payments via Flutterwave announced 25 Feb 2026. | CONFIRMED | https://www.intelligentcio.com/africa/2026/02/25/yango-partners-with-flutterwave-to-strengthen-secure-digital-payments-for-food-delivery-and-taxi-service-in-zambia/ |

Assessment: PUBLICLY AVAILABLE SERVICE for same-city Lusaka parcels and bulky goods. POTENTIAL PARTNERSHIP for an API integration, but unverified. Not an intercity solution.

### 2.8 Other on-demand and local players

| Provider | Finding | Status | Source |
|---|---|---|---|
| Afridelivery | Founded 2016; commission-based; operates 07:00 to 22:00; over 50 drivers across Lusaka and Kitwe offices; partners Shoprite (online grocery) and Lafarge (B2B); planned to open to third-party sellers and expand to the Copperbelt. Article is old (COVID-era, circa 2020 to 2021); current status unverified. | CONFIRMED (dated) | https://fizambia.com/?p=9674 |
| inDrive | Launched ride-hailing in Lusaka Oct 2024; courier service referenced is in Zimbabwe, not Zambia. | Courier in Zambia NOT FOUND | https://techpoint.africa/2024/10/18/indrive-launches-in-lusaka/ |
| Bolt | Lusaka pilot announced 5 Oct 2023; ride-hailing only; food delivery listed for South Africa only. | Delivery in Zambia NOT FOUND | https://techtrends.co.zm/?p=92459 |
| Glovo | No Zambia presence found. | NOT FOUND | n/a |
| Motorbike courier firms | Courier industry is described as having poor rider conditions and informal structure (Nkwazi Magazine, 10 Dec 2024): low pay, inadequate protective gear, rising accidents. No named firms or rates. | CONFIRMED (conditions); firms and rates NOT FOUND | https://nkwazimagazine.com/a-dangerous-business-the-underserviced-courier-business |

### 2.9 ZamCargo and other names

- **ZamCargo**: no operator by this exact name was found. The nearest hits were "Zambia Cargo and Logistics Limited" (a job-board company page, no service detail; https://www.ajira.co.tz/company/568/zambia-cargo-and-logistics-limited) and "Zambia Railways" freight. Status: NOT FOUND. Ask the founder whether a specific business was meant.
- **Truck / freight options**: intercity truck hire 2,000 to 5,000 ZMK, and a 20 ft container Lusaka to Dar es Salaam US$2,500 to 4,000, from ZambiaPrice "Transport Costs in Zambia 2026" ("Prices verified March 2026"; moderate to low reliability; unsourced survey data). https://zambiaprice-com.pages.dev/vehicles/transport-costs/ . No named truck operator with a published tariff was found. The US government guide says nearly all imports move by truck and lists distribution hubs: Lusaka, Kitwe, Ndola, Livingstone, Kasama, Solwezi, Chipata. https://trade.gov/country-commercial-guides/zambia-distribution-and-sales-channels

## 3. Coverage matrix (what the sources let us say about each destination)

"Evidenced" means a source names the town as served by that operator's passenger or parcel network. Parcel acceptance at the depot is not evidenced for any bus operator.

| Destination | Coach operators evidenced as serving it | Zampost | Notes |
|---|---|---|---|
| Ndola | Mazhandu, Power Tools (via Copperbelt), CR Holdings (Broadway Shopping Centre), Kobs | Zampost head office is in Ndola (Plot 17, 18 Arusha St) | Zampost head office address from https://zampost.com.zm/aboutUs.html |
| Kitwe | Mazhandu, Power Tools, CR Holdings (Railway Station), Euro-Africa | Post office presence assumed, not itemised | |
| Other Copperbelt (Chingola, Mufulira) | CR Holdings agents (phone numbers published) | not itemised | |
| Livingstone | Mazhandu, Shalom, CR Holdings (Mosi-oa-Tunya Road); corridor "half hourly from 6am" | not itemised | |
| Solwezi | CR Holdings (1 bus daily) | not itemised | |
| Kabwe, Kapiri Mposhi | Power Tools (en route), CR Holdings agents | not itemised | |
| Chipata | Kobs (serves Chipata passengers to Ndola); Lusaka to Eastern Province routes exist on the Bizbwana product page (not read) | not itemised | |
| Mansa | CR Holdings agent (Mansa) | not itemised | Operator coverage thin in the sources |
| Kasama, Nakonde, Mpika, Mpulungu | Power Tools, Shalom (Nakonde) | not itemised | |
| Mongu | Mazhandu (1 daily), Shalom | not itemised | |
| Mwinilunga | Ticklays | not itemised | |

Zampost does not itemise its 146 branches on the pages I read, so town-level Zampost presence is NOT FOUND in a verifiable list.

## 4. Published fares and price evidence (passenger fares only; no parcel tariffs found)

These are shown only as an indirect indicator of corridor cost and are **not** parcel prices.

| Route | Distance (source) | Bus fare range (ZMK as published) | Travel time | Source and reliability |
|---|---|---|---|---|
| Lusaka to Kitwe | 330 km | 150 to 250 | 4 to 5 h | ZambiaPrice, "Prices verified March 2026"; moderate to low reliability; internal inconsistencies |
| Lusaka to Ndola | 320 km | 140 to 230 | 4 to 5 h | same |
| Lusaka to Livingstone | 470 km | 200 to 350 | 6 to 7 h | same |
| Lusaka to Chipata | 570 km | 250 to 400 | 7 to 8 h | same |
| Lusaka to Solwezi | 600 km | 280 to 450 | 8 to 10 h | same |

Source: https://zambiaprice-com.pages.dev/vehicles/transport-costs/ . The site says "Prices are for reference only"; verify at the terminus.

**Parcel prices: NOT FOUND for any operator.** Do not use any figure as a parcel tariff in the model. Replace with quotes gathered through the protocol in §10.

## 5. Road distances

| Pair | Road km | Source | Status |
|---|---|---|---|
| Lusaka to Ndola | 321 | Logistics Cluster Zambia road network (undated) | CONFIRMED |
| Lusaka to Livingstone | 472 | same | CONFIRMED |
| Lusaka to Chipata | 580 | same | CONFIRMED |
| Lusaka to Solwezi | 583 | same | CONFIRMED |
| Lusaka to Mbala | 581 | same | CONFIRMED |
| Lusaka to Kitwe | 330 (ZambiaPrice, secondary) | https://zambiaprice-com.pages.dev/vehicles/transport-costs/ | Secondary only |
| Lusaka to Kabwe, Kasama, Mansa, Mongu, Nakonde | not in the sources I read | n/a | NOT FOUND (compute with a routing engine) |

Source for the first five rows: https://dlca.logcluster.org/node/2079 . The same document says the network is about 67,671 km with only about 15% paved; Lusaka is the hub through which virtually all trunk highways pass; trading corridors are paved and good; secondary roads are mostly gravel and damaged by rainy-season floods; tertiary roads can become impassable in the rains; the eastern (Malawi border) area is mostly passable only by 4x4. Implication for Convergeo: hub-and-spoke through Lusaka is structurally natural, and town-to-town non-Lusaka shipping will be slow or non-existent. Plan for rainy-season (roughly Nov to Mar) delay flags on non-trunk legs; this is an inference from the road-condition notes, not a sourced transit-time statistic.

## 6. Reliability evidence

| Operator | Evidence found | Verdict |
|---|---|---|
| All coach operators | No parcel loss, delay or damage statistics found. Only passenger-safety news (e.g. Mazhandu crash and licence stories appear in Lusaka Times results; not read in detail). | NOT FOUND for parcels |
| Zampost | No on-time or loss statistics found | NOT FOUND |
| Yango cargo | Training and loyalty programme for couriers (Dec 2024); no delivery performance data | NOT FOUND |
| Motorbike couriers (sector) | Rising accident rates and poor conditions reported; Bikers Association reportedly claimed over 1,000 biker deaths "this year" (Nkwazi Magazine, 10 Dec 2024; the claim is reported secondhand) | CONFIRMED (conditions); relevant to rider-safety and insurance requirements |

Reliability must be measured, not assumed. Use the pilot design in §10.

## 7. Fuel prices (ERB, November 2026)

The ERB published the November 2026 press statement on 31 Oct 2026 (page: https://www.erb.org.zm/november-2026-petroleum-pump-prices-press-statement-and-price-build-ups/ ; PDF: https://www.erb.org.zm/wp-content/uploads/PressStatements/CurrentFuelPumpPricesNovember2026.pdf). My tools could not extract text from the PDF ("empty or contains no machine-readable text"), and direct download through the sandbox proxy returned 403. Figures below therefore come from media reports quoting the ERB.

| Product | Nov 2026 (K/litre) | Previous (K/litre) | Sources |
|---|---|---|---|
| Petrol | **33.06** | 31.46 | Diggers (31 Oct 2026), Energy News Africa (1 Nov 2026), Zambian Observer headline "PETROL from 31.46 to 33.06" |
| Diesel | **34.45** | 33.27 | Diggers, Energy News Africa, Zambia Monitor, Zambian Observer |
| Kerosene | **32.08** | 29.76 (derived by Energy News Africa from a K2.32 rise) or 29.96 (Zambia Monitor) | Energy News Africa, Zambia Monitor |

Discrepancy note: Zambia Monitor prints petrol as K33.60; three other outlets give K33.06, and "up K1.60 from K31.46" arithmetically equals K33.06, so K33.60 is very likely a typo. Previous kerosene is reported as 29.76 or 29.96; the new figure (32.08) agrees. Effective from midnight 31 Oct 2026 (Zambia Monitor, Energy News Africa).

Sources:
- https://diggers.news/business/2026/10/31/erb-hikes-fuel-prices-4/
- https://energynewsafrica.com/zambia-fuel-prices-rise-for-november-as-kwacha-weakens/
- https://www.zambiamonitor.com/zambia-hikes-november-petrol-diesel-prices/
- https://zambianobserver.com/fuel-prices-increased-petrol-from-31-46-to-33-06diesel-from-33-27-to-34-45/ (headline only; article not fetched)

Model use: fuel moved about +5% (petrol) and +3.5% (diesel) month on month (my arithmetic from the figures above). Delivery pricing should reference a live fuel index rather than a fixed constant.

## 8. Motorbike courier rates in Lusaka

**NOT FOUND.** No source I could read publishes per-delivery rates for Lusaka motorbike couriers, Yango cargo, or Afridelivery.

The only numbers adjacent to the question are unsourced:
- Rider salaries "K2,000 to K3,500 per month each" and licensing estimates in an M&J Consultants blog (8 May 2025). That blog states fees for ZICTA, RTSA and rider licences with no sources; treat as unverified. https://mjconsultants-co-zm.pages.dev/insights/how-to-start-a-motorcycle-delivery-business-in-zambia-a-comprehensive-guide/

Recommended: collect rates by placing real test bookings through Yango (app) and two or three local motorbike couriers across a grid of Lusaka routes, and record date, time, distance, fare and weather (§10).

## 9. Regulatory points

| Topic | What the sources say | Status | Source |
|---|---|---|---|
| Data Protection Act No. 3 of 2021 (DPA) | Controllers and processors must register with the Data Protection Commissioner; the certificate lasts one year. Consent is required for processing, and the data subject must be told of the right to withdraw it. Personal data must be processed and stored on a server or data centre in Zambia, with limited exceptions; sensitive personal data must be stored in Zambia regardless. Transfers abroad are allowed with the data subject's consent plus approved standard contracts or ministerial permission, among other exceptions. Controllers must notify the Commissioner of a security breach within 24 hours; processors must notify the controller as soon as practicable. Penalty for breach of processing rules: up to the higher of 100 million penalty units (about ZMW 30 million per the source) or 2% of prior-year turnover. | CONFIRMED (secondary law-firm summary; the primary Act is at https://zambialii.org/akn/zm/act/2021/3/eng@2021-03-24 and was not read) | https://www.dlapiperdataprotection.com/?c=ZM&t=law |
| DPA: sharing customer data with transport partners | The summary does not address third-party disclosure directly and does not describe controller-to-processor contract content. Practical reading (my inference, not a legal opinion): treat each carrier as a processor or independent controller, share only name, phone, delivery address and parcel details needed for delivery, record the lawful basis and consent in the checkout flow, put a written data-processing clause in each partner agreement, and obtain legal advice on registration and on carriers that store data abroad (e.g. cloud-based app carriers). | NOT FOUND in source; inference flagged | n/a |
| ODPC registration deadline | An ITLaw article on a registration deadline of 30 April 2025 exists in results; not read. | NOT VERIFIED | https://itlawco.com/zambias-odpc-registration-deadline-30-april-2025/ |
| ZICTA courier licensing | Couriers are licensed by ZICTA. A Zambia Monitor article reports the Minister signing a Statutory Instrument cutting annual courier licence fees (local K10,000 to K5,000; international K15,000 to K10,000); the article is undated, so the current fee is unknown. A different unsourced blog says "Domestic Courier License: K10,000 (5-year validity) + 1% of gross revenue annually" (8 May 2025). The two conflict. | CONFLICTING; verify with ZICTA | https://www.zambiamonitor.com/?p=12234 ; https://mjconsultants-co-zm.pages.dev/insights/how-to-start-a-motorcycle-delivery-business-in-zambia-a-comprehensive-guide/ |
| Pending law change | Zambia is proposing to replace the Postal Services Act No. 22 of 2009 with the **Postal and Courier Services Bill, 2026**; consultations by the Ministry of Technology and Science with ZICTA; couriers are in scope; aims include modernised licensing, consumer protection, universal-service fund and better addressing. Article dated 23 Jul 2026. The bill is a proposal. | CONFIRMED | https://itweb.africa/article/zambia-updates-postal-laws-for-digital-economy/LPwQ5MlboeOvNgkj |
| Implication for Convergeo | If Convergeo itself carries parcels for hire it may need a courier licence; if it only arranges carriage through licensed carriers it may not. This is a legal question to confirm with ZICTA or counsel. | NOT FOUND (inference) | n/a |
| ZRA: VAT | Standard rate 16%; registration at ZMW 800,000 annual taxable turnover or ZMW 200,000 in any rolling three months (third-party guide, page updated 20 Oct 2026). Cross-border electronic services regulations since 1 April 2024. Verify with ZRA. | CONFIRMED (secondary) | https://trykintsugi.com/sales-tax-guides/africa/zambia |
| ZRA: invoicing | Convergeo's own CLAUDE.md states "ZRA-ready sequential invoices (VAT flag off at launch; VSDC seam)". The VSDC/smart-invoice requirement for delivery fees was not researched here. | NOT RESEARCHED | n/a |
| RTSA: commercial riders and vehicles | The Road Traffic Act No. 11 of 2002 is on the RTSA site (https://www.rtsa.org.zm/wp-content/uploads/2019/09/The-Road-Traffic-Act-No-11-of-2002.pdf) and was not read. The M&J blog lists road service licence and identity certificate fees per motorcycle and says insurance is "legally required" at third-party level, but gives no sources. RTSA does run safety training for Yango cargo couriers (Dec 2024). Motorcycle commercial licensing specifics: NOT VERIFIED from a primary source. | NOT VERIFIED | https://www.times.co.zm/?p=135693 |
| Rider safety | Reported lack of helmets and protective gear, rising accidents. Supports a requirement for helmets, third-party insurance and a rider check in any Convergeo rider onboarding. | CONFIRMED (conditions) | https://nkwazimagazine.com/a-dangerous-business-the-underserviced-courier-business |

Liability / claims limits: **NOT FOUND for every domestic operator** (no coach operator, Zampost EMS page, Yango, or Lechwe). Only the FedEx Zambia Conditions of Contract exist as a published international-carriage liability document (not read in full). Convergeo must negotiate liability in writing and carry its own cargo insurance, or decline to ship high-value goods by bus-parcel.

## 10. Suitability for e-commerce fulfilment, and how Convergeo can use existing networks

### 10.1 Assessment by mode

| Mode | Fit | Why (evidence) | Main gaps |
|---|---|---|---|
| Depot-to-depot via coach operators (Mazhandu, Power Tools, CR Holdings, Shalom, Kobs) | POTENTIAL PARTNERSHIP. Best fit for the cheapest intercity trunk leg on corridors with frequent departures (Lusaka to Livingstone "half hourly from 6am"; Copperbelt; Solwezi daily) | Frequent scheduled departures, established terminals (Kamwala Lusaka, Mosi-oa-Tunya Livingstone, Broadway Ndola, Kitwe Railway Station) | No published tariff, liability, tracking, API or confirmation parcels are carried for third parties. Operators may carry parcels informally |
| Depot-to-door and door-to-door via Zampost EMS | PUBLICLY AVAILABLE SERVICE. Best fit for destinations without bus-parcel depots; agency model documented | 146 post offices, door-to-door EMS, 48-hour domestic standard (secondary) | No price, liability, SLA data; tracking scope unclear; no API found |
| Local last-mile in destination town (motorbike couriers, taxi-based) | POTENTIAL PARTNERSHIP in larger towns only | Yango in Lusaka; Afridelivery in Lusaka and Kitwe (dated) | Town-level courier firms outside Lusaka and Kitwe: NOT FOUND |
| International express (DHL, FedEx) | Not suited to domestic e-commerce | International product evidence only | Domestic: NOT FOUND |
| Freight trucks / rail | Suited only to bulk supplies (B2B tier pricing) | US guide: trucks carry nearly all imports | No parcel use; no tariff |

### 10.2 Practical conclusions for Model E

1. **Do not design around an API.** None was found for any intercity partner. The fulfilment-orchestration layer should treat each provider as a "manual" adapter: Convergeo generates a waybill/label with its own reference, hands it to the vendor, and the status is updated by WhatsApp/SMS photo-proof or a depot agent confirming handover and receipt. API adapters (Yango, DHL) can be added later behind the same interface once access is verified.
2. **Depots are the integration point.** Published terminals exist for Lusaka (Intercity terminus, Kamwala), Livingstone (Mosi-oa-Tunya Road), Ndola (Broadway Shopping Centre), Kitwe (Railway Station). These are plausible Convergeo "collection points" for Model D, but each must be agreed with the operator.
3. **Hub-and-spoke through Lusaka** matches the road network (Logistics Cluster document).
4. **Provider selection engine inputs** that can actually be sourced today: destination town, operator departure frequency, depot location, declared value, weight, fragility. Cost, transit time, and reliability inputs will have to come from the pilot data, not from public sources.
5. **Prohibited or unsuitable via bus-parcel**: perishable and chilled goods (Model F), high-value electronics unless insured, because liability and handling are undefined.

### 10.3 Verification protocol before any commitment (recommended)

For each target operator (Power Tools first; then CR Holdings/Euro-Africa, Mazhandu, Shalom, Kobs; Zampost EMS; Lechwe):
1. Call or visit the Lusaka depot and ask: do you carry third-party parcels; weight and size limits; tariff per kg and per parcel by destination; minimum charge; declared-value fees; maximum liability per parcel; claim process and time limit; collection and delivery (door) options; cut-off and departure times; whether the receiving depot notifies the recipient by SMS; proof of delivery; operating hours; whether business accounts and invoicing exist.
2. Send 10 identical test parcels per corridor (Lusaka to Livingstone, Ndola/Kitwe, Solwezi, Chipata, Kasama/Mansa) with realistic contents of low value; record door-to-door time, damage, loss, communication quality, cost. Do the same for Zampost EMS.
3. Record every quote with date, name of person, and phone number so it can be cited later.
4. Ask Yango Zambia sales whether a merchant API or account exists in Zambia.
5. Confirm with ZICTA (or a lawyer) the licensing position for Convergeo and the DPA registration and partner-clause position.

## 11. Items not completed or blocked

| Item | Reason |
|---|---|
| `https://powertoolscourier.co.zm`, `https://www.mazhandu.com`, `https://ezampost.co.zm` | Fetch permission requests were not answered; not read. Suggest the lead agent or founder open them. |
| ERB November 2026 press-statement PDF | Returned no machine-readable text; direct download blocked (HTTP 403 through the proxy). Fuel figures are from media quoting the ERB (§7). |
| Primary text of the DPA, Road Traffic Act 2002, Postal Services Act, FedEx Conditions of Contract | Identified but not read. |
| Platinum, TownStar/Tom Star, Likili, Juldan, ZamCargo | No evidence found. Need exact names or contact details from the founder. |
| Provincial towns: Mansa, Kasama, Chipata, Mongu, Solwezi local couriers | No local courier firms found. |
| Bus-parcel prices, liability limits, API | NOT FOUND for every operator. |

## 12. Source list (all accessed 13 Nov 2026)

1. Zampost EMS: https://zampost.com.zm/Ems.html
2. Zampost About: https://zampost.com.zm/aboutUs.html
3. US Commercial Service, Zambia Country Commercial Guide (distribution and sales channels; last published 2026-03-23): https://trade.gov/country-commercial-guides/zambia-distribution-and-sales-channels
4. Power Tools blog: https://travelertz.blogspot.com/2025/03/power-tools-coach-power-tools-bus.html
5. Power Tools Courier job ad (6 Mar 2024): https://www.greatzambiajobs.com/jobs/job-detail/job-Ticket-Seller-job-at-Power-Tools-Courier-57554
6. Mazhandu (third-party): https://safaribay.net/mazhandu-family-bus/
7. Zambia Tourism, Luxury Bus Services: https://www.zambiatourism.com/transport/bus/
8. Bizbwana bus directory: https://bizbwana.com/directory/transport/buses-and-coaches
9. Bizbwana CR Holdings: https://bizbwana.com/orgs/cr-holdings
10. Bizbwana Lechwe Express Logistics: https://bizbwana.com/orgs/lechwe-express-logistics
11. DHL Zambia Express: https://www.dhl.com/zm-en/home/express.html
12. Yango Cargo Express launch (28 Mar 2024): https://techlabari.com/?p=53673
13. Yango couriers event (published 20 Dec 2024): https://www.times.co.zm/?p=135693
14. Nkwazi Magazine, Yango Cargo: https://interactive.nkwazimagazine.com/?p=13270
15. Nkwazi Magazine, courier conditions (10 Dec 2024): https://nkwazimagazine.com/a-dangerous-business-the-underserviced-courier-business
16. Yandex Go Delivery API: https://yandex.com/dev/logistics/api-go-delivery
17. Kolonell, Yango Delivery Senegal integration (2026): https://kolonell.com/en/blog/yango-delivery-senegal-merchant-integration-2026
18. Yango + Flutterwave (25 Feb 2026): https://www.intelligentcio.com/africa/2026/02/25/yango-partners-with-flutterwave-to-strengthen-secure-digital-payments-for-food-delivery-and-taxi-service-in-zambia/
19. Afridelivery profile: https://fizambia.com/?p=9674
20. inDrive Lusaka launch (18 Oct 2024): https://techpoint.africa/2024/10/18/indrive-launches-in-lusaka/
21. Bolt Lusaka pilot (5 Oct 2023): https://techtrends.co.zm/?p=92459
22. ZambiaPrice transport costs ("verified March 2026"): https://zambiaprice-com.pages.dev/vehicles/transport-costs/
23. I am Beezy luggage costs article (16 Aug 2026): https://blog.iambeezy.app/en/long-distance-travel-luggage-costs-zambia-en-2026/
24. Logistics Cluster, Zambia road network: https://dlca.logcluster.org/node/2079
25. ERB November 2026 page: https://www.erb.org.zm/november-2026-petroleum-pump-prices-press-statement-and-price-build-ups/
26. Diggers (31 Oct 2026): https://diggers.news/business/2026/10/31/erb-hikes-fuel-prices-4/
27. Energy News Africa (1 Nov 2026): https://energynewsafrica.com/zambia-fuel-prices-rise-for-november-as-kwacha-weakens/
28. Zambia Monitor fuel (31 Oct 2026): https://www.zambiamonitor.com/zambia-hikes-november-petrol-diesel-prices/
29. DLA Piper, Zambia data protection: https://www.dlapiperdataprotection.com/?c=ZM&t=law
30. ITWeb, Postal and Courier Services Bill 2026 (23 Jul 2026): https://itweb.africa/article/zambia-updates-postal-laws-for-digital-economy/LPwQ5MlboeOvNgkj
31. Zambia Monitor, ZICTA courier fees (undated): https://www.zambiamonitor.com/?p=12234
32. Kintsugi, Zambia VAT guide (updated 20 Oct 2026): https://trykintsugi.com/sales-tax-guides/africa/zambia
33. M&J Consultants motorcycle delivery guide (8 May 2025; unsourced figures): https://mjconsultants-co-zm.pages.dev/insights/how-to-start-a-motorcycle-delivery-business-in-zambia-a-comprehensive-guide/
34. M&J Consultants courier aggregator article (27 Jun 2025; names no couriers): https://mjconsultants-co-zm.pages.dev/insights/inside-zambias-booming-courier-aggregator-market-a-2025-guide-for-tech-startups/
