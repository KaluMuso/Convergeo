# Lusaka delivery bands: ride-hail reference prices

Status: reference only, compiled 13 Nov 2026. Interim until a courier / ride-hail API exists.
Decision input: founder default fee band for unmatched Lusaka addresses is **Band B = K45**.

## 1. Current repository state (branch `fix/quality-sweep`)

| Zone key | Label | Fee | Source |
|---|---|---|---|
| `lusaka_a` | Band A (central) | K30 (3000 ngwee) | `supabase/migrations/0008_config.sql` (seed) |
| `lusaka_b` | Band B (mid-ring) | K45 (4500 ngwee) | same |
| `lusaka_c` | Band C (outer) | K65 (6500 ngwee) | same |

`services/api/app/routers/checkout.py`:
- GPS path: haversine distance from CBD centre (-15.4167, 28.2833). A <= 5 km, B <= 12 km, C <= 25 km, beyond = no delivery (pickup only).
- Landmark path (no GPS): case-insensitive substring match, first hit wins:
  - `band a` / `central` / `cbd` -> A
  - `band b` / `mid-ring` / `kabulonga` -> B
  - `band c` / `outer` -> C
  - `lusaka` / `woodlands` / `east park` -> A
  - Other towns (`ndola`, `kitwe`, `livingstone`, `chipata`) -> none.
  - Anything else -> unmatched; `platform_config.delivery_fallback_zone` (if set to an active zone key, e.g. `lusaka_b`) is used, otherwise refused.
- Free delivery threshold default K200 (20,000 ngwee).

Observed inconsistency: `kabulonga` maps to B by landmark but is about 4.8 km from CBD (Band A by GPS). Landmark matching is also order dependent: "Kabulonga, Lusaka" hits B first, "Woodlands, Lusaka" hits A.

## 2. Published ride-hail data (what exists)

Very little public data exists. No source found gives a Yango or inDrive base fare, per-km rate, per-minute rate or minimum fare for Lusaka. Yango's Lusaka page and its tariff pages for other cities do not state Lusaka tariffs (the Lusaka page says fares are shown in-app before confirming). inDrive is negotiated; no source reports typical Lusaka offers. No published Lusaka motorbike courier or Yango Delivery/Cargo tariff was found. Nothing below was invented; "not found" means not found.

| Item | Value | Source, date | Status |
|---|---|---|---|
| Yango per trip within Lusaka | K25-80 | zambiaprice (zambiaprice-com.pages.dev/daily-living/taxi-ride-hailing), "verified March 2026" | Aggregator site, secondary |
| Yango CBD -> Kabulonga | K30-45 | same, March 2026 | Aggregator, secondary |
| Yango CBD -> Chilenje | K25-40 | same, March 2026 | Aggregator, secondary |
| Yango CBD -> Airport (KKIA) | K80-120 | same, March 2026 | Aggregator, secondary |
| Yango CBD -> Kafue | K120-180 | same, March 2026 | Aggregator, secondary |
| Ride-hailing (Yango/Ulendo) Lusaka | K30-120 | zambiaprice transport-costs page, March 2026 | Aggregator, secondary |
| Street taxi within Lusaka | K50-150 | same, March 2026 | Aggregator |
| Minibus | K10-20 | same, March 2026 | Aggregator |
| Yango peak hour, Manda Hill -> Intercity bus terminal, ~5 km, ~10 min | about K60 | Zambia Monitor, 15 Aug 2025 (zambiamonitor.com/?p=69084) | News report, single data point |
| Yango ~11 km (Africana Hotel -> Natwange Backpackers) | K66 (~US$3) | nomadicbackpacker.com, 11 Sep 2023 | Old (pre-2025), blog; context only |
| Yango trip to the airport | K66 (~US$3), start unnamed | same, 11 Sep 2023 | Old, context only |
| Drivers sometimes charge above app fare | no amounts given | Zambia Monitor, 11 May 2025 (consumer associations' statement) | Qualitative |
| inDrive Lusaka fares | not found | searched 13 Nov 2026 | No data |
| Yango Delivery / Cargo / motorbike tariff Lusaka | not found | searched 13 Nov 2026 (only launch articles, Dec 2024) | No data |
| Local motorbike courier rates (e.g. Yafika, Musanga) | not found | searched 13 Nov 2026 | No data |

Derived (estimate, mine): the March 2026 and Aug 2025 points imply roughly K6-12 per km for short urban Yango car trips (K60 / 5 km = K12/km at peak; CBD->Kabulonga K30-45 over ~4.8 km straight line = K6-9/km). Pricing is nonlinear with a floor around K25-30, so short hops cost nearly the same as 3-4 km trips.

## 3. Areas, approximate distance from CBD and ride-hail range

Method for distances (estimate): straight-line haversine from the matcher's CBD point (-15.4167, 28.2833) to an approximate area centroid typed from general knowledge of Lusaka geography (not surveyed; each is plausibly off by 0.5-1 km). Road distance is typically 1.3-1.5x straight-line. The only ride-hail prices with sources are the four rows marked in section 2; other rows are blank because no data exists.

| Area | Approx straight-line km from CBD | Band by matcher distance rule | Observed ride-hail price (source) |
|---|---|---|---|
| Rhodes Park | 2.1 | A | none found |
| Northmead | 2.6 | A | none found |
| Woodlands | 2.8 | A | none found |
| Kabwata | 3.2 | A | none found |
| Manda Hill (landmark) | 3.3 | A | ~K60 peak to Intercity terminal, 5 km (Aug 2025) |
| Roma | 4.1 | A | none found |
| Kalingalinga | 4.1 | A | none found |
| East Park Mall (landmark) | 4.6 | A | none found |
| Emmasdale | 4.7 | A | none found |
| Kabulonga | 4.8 | A | K30-45 (zambiaprice, Mar 2026) |
| Chilenje | 5.1 | B (borderline) | K25-40 (zambiaprice, Mar 2026) |
| Makeni | 5.9 | B | none found |
| Matero | 7.0 | B | none found |
| Mtendere | 7.7 | B | none found |
| Ibex Hill | 8.1 | B | none found |
| Chelston | 8.6 | B | none found |
| Chainda | 9.2 | B | none found |
| Lilayi | 11.6 | B (borderline) | none found |
| Chalala | 12.5 | C (borderline) | none found |
| KKIA airport | about 13-15 (estimate) | C | K80-120 (zambiaprice, Mar 2026) |

Headline averages from the sourced data (derived, low confidence):
- Short central/inner trips (<= ~5 km): K25-45 car ride-hail, K60 at peak in one report. Midpoint about K35.
- Band A fee K30 is at the low end of that range; Band B K45 is at the upper end of inner trips and below the K80-120 airport range.
- No evidence either way on motorbike courier. Motorbike couriers are normally cheaper than a car ride for small parcels and are the relevant comparison for this platform, but no Lusaka tariff was found, so the K30/K45/K65 bands cannot be validated against it. Recommended: collect 10-20 real quotes (Yango app screenshots at several times of day; inDrive offers; two or three local riders) before changing fees.

## 4. Proposed mapping of areas to bands

Keep the K30/K45/K65 values. Proposal groups by distance, with a bias to B for ambiguous peripheral areas (matches the founder's K45 default).

| Band | Areas / landmarks |
|---|---|
| A (K30) | CBD, Cairo Road, Longacres, Rhodes Park, Northmead, Fairview, Woodlands, Woodlands Extension, Kabwata, Olympia Park, Roma, Kalingalinga, Kabulonga, Emmasdale, Manda Hill, East Park Mall, Levy Junction, Arcades, Government Complex, UTH |
| B (K45) | Chilenje, Makeni, Matero, Mtendere, Ibex Hill, Chelston, Chainda, Libala, Kamwala, Garden, Chawama (low confidence: not computed), Lilayi, Kalundu, Chelstone, Thornpark, Leopards Hill (outer edge) |
| C (K65) | Chalala, Chongwe road areas, Kafue Road beyond Lilayi, Airport/KKIA, Chilanga, Chisamba direction, Kabanana, Chaisa, Bauleni (low confidence), anything over about 12 km |

Note: Libala, Kamwala, Garden, Chawama, Chelstone, Thornpark, Kabanana, Chaisa, Bauleni, Chilanga, Olympia Park, Fairview and Longacres were not distance-computed here and their band is a judgement, flagged for review.

Landmark-matcher conflicts to fix in code (not changed here): Kabulonga should be A by distance, not B; Chilenje and Lilayi sit on band edges.

## 5. Additional area names the landmark matcher should recognise

Current keywords recognise only: cbd, central, kabulonga, woodlands, east park, lusaka, band a/b/c, mid-ring, outer. Suggested additions:

- Band A: cairo road, longacres, rhodes park, northmead, fairview, kabwata, olympia, roma, kalingalinga, emmasdale, manda hill, arcades, levy, thorn park, kamwala south, state house, university teaching hospital, uth, university of zambia, unza, great east road (inner).
- Band B: chilenje, makeni, matero, mtendere, ibex hill, chelston, chelstone, chainda, libala, kamwala, garden, kalundu, lilayi, chawama, ng'ombe, john laing, chaisa, bauleni, kabanana, misisi (the last four are borderline and may be C).
- Band C: chalala, chilanga, airport, kkia, chongwe, chisamba, kafue road, kanyama (borderline), leopards hill, foxdale.
- Spelling variants to normalise: "chelston/chelstone", "kamwala/kamwala south", "ibex/ibex hill", "ng'ombe/ngombe", "thorn park/thornpark", "leopards hill/leopard's hill".

## 6. Caveats

- Sources are secondary (aggregator page, one news item, one blog). Treat all ranges as indicative.
- Ride-hail surge, time of day and driver add-ons (reported by consumer groups, May 2025) move prices up.
- Revisit when a courier or ride-hail API provides live quotes.
