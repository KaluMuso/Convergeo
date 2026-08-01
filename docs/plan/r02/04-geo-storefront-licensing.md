# R02-04 — Geo, Storefront & Licensing: audit and phased additive contract

**Date:** 2026-08-01 · **Status:** discovery / proposal · **Mode:** GATED · **Authority:** none

This is a **planning document**. It changes no code, no schema, no flag, no configuration. Nothing
here is a decision: `docs/plan/00-decisions.md` remains the sole decision record, and every new
decision this work would need is written below as a **candidate ADR** for the founder to accept,
amend or reject (§7). Nothing here may be treated as approval to build.

**Method.** Every claim about the codebase is cited to a file path and symbol in the working tree at
`7d8b3ae` on branch `claude/geo-storefront-licensing-r02-fj8ara`. Strategy intent is cited to the
committed distillations (`docs/plan/research/`), never to the raw PDFs. Source text, prior audit
output and model output are treated as **untrusted input**: each was re-checked against the schema
and routers before being written down here, and where a distillation and the code disagree, the code
wins and the disagreement is recorded.

**Status vocabulary** (used in §2 and §3):

| Marker                   | Meaning                                                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------- |
| **Implemented**          | Present, wired end-to-end, exercised by tests                                            |
| **Partial**              | Present but incomplete, one-sided (read without write), or wired for only one code path  |
| **Absent**               | No table, column, route, or component exists                                             |
| **Deferred by decision** | Deliberately out of scope under a cited locked decision — **not** a defect               |
| **Not auditable**        | Cannot be established from the repository (live DB state, ops behaviour, founder intent) |

---

## 1. Scope, fences and what this document may not propose

### 1.1 Governing decisions this design must obey

| Decision  | Constraint this imposes here                                                                                                                                                                                                      |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **D28**   | Multi-warehouse and lot/batch inventory stay **OUT of v1**. Branch-aware _availability_ may therefore be modelled only as a fulfilment/display concern in v1; per-branch stock **quantities** are Phase 2 and need their own ADR. |
| **D34**   | Phase-1 catalogue is Class A branded/new (+ existing `refurbished`). No `product_class`, no expanded `condition`, no evidence model. Nothing here may add a product-class or condition dimension.                                 |
| **D35**   | An LLM may **suggest** structured fields but **never approves** KYC, publication, payment or moderation. This extends verbatim to licence review: every licence decision is a human admin action.                                 |
| **D9**    | KYC is 3 tiers + 1 earned badge. A regulator licence is **not** a fourth KYC tier — it is evidence attached to a vendor, with its own lifecycle.                                                                                  |
| **D16**   | Lusaka delivery via manual dispatch; nationwide pickup. No courier API integrations in v1. Service-area modelling must not imply automated dispatch.                                                                              |
| **D3**    | Paid vendor tiers ship feature-flagged and off. Any branch/collection cap that the strategy assigns to a paid tier must default to the free-tier value and read from config, never hard-coded.                                    |
| **D6**    | ≤ $50/mo infra. No paid geocoding, routing or tiles service may become a launch dependency.                                                                                                                                       |
| CLAUDE #6 | Migrations are additive-only after M03 and reversible or documented why not. Every proposal below is additive; none alters an existing column's type or drops one.                                                                |
| CLAUDE #7 | Customer routes ≤150KB gz JS; LCP ≤2.5s Fast-3G/360px. This is the binding constraint on map mode (§3.7).                                                                                                                         |

### 1.2 Explicitly not proposed

- No `product_class`, no `condition` enum change, no evidence model (**D34**).
- No per-branch stock ledger, no stock transfers, no lot/batch (**D28**) in v1.
- No automated licence approval, no LLM-scored licence validity, no auto-publication (**D35**).
- No courier/routing API integration, no paid tile subscription (**D16**, **D6**).
- No change to `docs/plan/00-status.md` or `docs/plan/00-decisions.md`.

---

## 2. Audit — current evidence

Tip of `supabase/migrations/` is `0079_clip_cost_guard.sql`; the next free number is **`0080`**.
`docs/plan/00-status.md` records that `0072`–`0079` are **not applied** to the live project, so all
statements below describe the **committed schema**, not live database state.

### 2.1 Capability summary

| #   | Capability                             | Status                                    | Anchor evidence                                         |
| --- | -------------------------------------- | ----------------------------------------- | ------------------------------------------------------- |
| 1   | Vendor location (single pin)           | **Implemented**                           | `supabase/migrations/0002_identity_vendors.sql:87`      |
| 2   | Vendor **branches** (multi-location)   | **Partial** — read-only; no write path    | `directory.py:213` vs `vendor_profile.py:432`           |
| 3   | Structured Zambian address             | **Absent**                                | `0005_orders.sql:8` — `landmark text` only              |
| 4   | Landmark + GPS capture                 | **Implemented** (privacy-unsafe, see 2.3) | `0002:92`, `0005:12`                                    |
| 5   | Branch-aware availability / stock      | **Absent** (partly **Deferred** — D28)    | `0003_catalog.sql:87` — stock is listing-scoped         |
| 6   | Opening hours storage + validation     | **Implemented**                           | `vendor_profile.py:163` `validate_vendor_hours`         |
| 7   | Hours **consumed** (open-now)          | **Absent**                                | no `open_now` symbol anywhere in the tree               |
| 8   | Vendor phone / social contact          | **Partial** — WhatsApp only               | `0046_vendor_whatsapp_msisdn.sql:19`                    |
| 9   | Service areas                          | **Partial** — free text, unused           | `0004_services_events.sql:15` `services.service_area`   |
| 10  | Delivery areas / zones                 | **Partial** — 3 flat bands + text guesses | `0008_config.sql:44`; `checkout.py:148`                 |
| 11  | Distance / nearby (search)             | **Partial** — re-rank inside a window     | `services/api/app/services/search/__init__.py:344`      |
| 12  | Distance / nearby (directory)          | **Partial** — first-branch only, in-app   | `directory.py:383`, `directory.py:519`                  |
| 13  | Map / list mode                        | **Absent**                                | no map library in the tree; CSP blocks tiles            |
| 14  | Route mode ("on the route")            | **Absent**                                | no routing/OSRM/polyline code                           |
| 15  | Geo in search ranking                  | **Implemented** (with two defects)        | `_geo_rerank`; `0009_search.sql:836` `search_rrf`       |
| 16  | Verification (KYC) lifecycle           | **Implemented**                           | `0056_kyc_integrity.sql`; `routers/admin_kyc.py`        |
| 17  | Regulator / sector **licence** records | **Absent**                                | no licence table, column, route or component            |
| 18  | Licence expiry monitoring              | **Absent**                                | follows from 17                                         |
| 19  | Store collections (vendor-curated)     | **Absent**                                | only platform `merch_slots` (`0008:120`)                |
| 20  | Impression analytics                   | **Absent** — explicitly so                | `routers/vendor_analytics.py:1-10`                      |
| 21  | Search analytics                       | **Implemented**                           | `0027_search_analytics.sql`; `0029_analytics_unify.sql` |
| 22  | Live DB state of any of the above      | **Not auditable**                         | Supabase MCP unauthenticated in this session            |

### 2.2 What exists, precisely

**`vendor_locations`** (`0002_identity_vendors.sql:87-101`) carries exactly
`id, vendor_id, lat, lng, landmark, hours jsonb, created_at, updated_at`. It has **no**
`name`, `phone`, `is_primary`, `status`, address components, service radius, or timezone. It has no
index on `vendor_id` (only the implicit PK), and no uniqueness constraint of any kind — nothing stops
a vendor accumulating duplicate rows.

**Hours** are validated server-side (`vendor_profile.py:163` `validate_vendor_hours`): day keys must
be in `DAY_KEYS`, each day is either `{"closed": true}` or `{"open": "HH:MM", "close": "HH:MM"}`,
`open == close` is rejected, and at least one day must be open. The shape is sound. What is missing
is everything downstream: no timezone column, no overnight semantics (`open > close` passes
validation with no defined meaning), no holiday/special-closure model, and — critically — **no
reader**. `hours` is returned by `directory.py:523`, `checkout.py:277` and the vendor profile
endpoint, and rendered by `apps/vendor/.../hours-editor.tsx`, but no code path ever compares it to a
clock.

**Geo in search works and is well-built.** `search.py:30-31` accepts `lat`/`lng`;
`services/search/__init__.py:344` `_geo_rerank` stamps `distance_km` and blends a bounded
`exp(-d/12km)` factor capped at +50% into `rrf_score`, never dropping coordinate-less hits. The
client (`near-me-toggle.tsx:20`) deliberately rounds the browser fix to 2 decimal places (~1.1km)
before it leaves the device. That is a genuinely good privacy default and should be preserved.

**Verification has a strong precedent to copy.** `0056_kyc_integrity.sql` gives `kyc_records` a real
lifecycle (`submitted → under_review → approved|rejected → suspended|revoked`) with immutable
decision evidence, and `routers/admin_kyc.py` supplies a review queue with SLA badges
(`on_track/due_soon/overdue`), short-TTL signed URLs against a private bucket
(`KYC_DOCS_BUCKET = "kyc-docs"`, `SIGNED_URL_TTL_SECONDS = 300`), templated reject reasons, admin
audit recording and outbox notifications. **The licence model in §3.9 should mirror this shape rather
than invent a new one.**

**Search analytics are real and privacy-conscious.** `search_query_log` (`0027`) stores a normalized
term, entity counts, a zero-result flag and Ask spend, with `user_id` trimmed after 30 days;
`analytics_events` (`0029`) is admin-read/service-write with no raw-PII column. This is a sound base
for §3.11 — the missing piece is only the impression event itself.

### 2.3 Defects found (each independently verified against the tree)

> These are current-code findings, not proposals. Several are cheap to fix and are sequenced first in
> §8 because later work would otherwise inherit them.

**G-D1 — Exact vendor GPS is world-readable.** `0002:294` creates
`vendor_locations_public_active_select` with no restriction beyond the parent vendor being `active`,
and `0002:425` grants `select` on the table to `anon`. `directory.py:457-466` and `products.py:395`
return raw `lat`/`lng`. For a home-based seller — the dominant archetype the platform is recruiting
(**D10**) — this publishes a residential address to anonymous users. This is a **Zambia DPA
exposure**, and it is asymmetric with the care taken on the buyer side, where the client
deliberately coarsens its own fix to ~1.1km (`near-me-toggle.tsx:20`).

**G-D2 — Moving a pin does not re-index search.** `0009_search.sql:700-760` installs sync triggers on
`vendors`, `vendor_listings`, `services`, `events` and `ticket_types`. There is **no trigger on
`vendor_locations`** (verified: the only trigger on that table is `vendor_locations_set_updated_at`,
`0002:98`). Because `search_documents.lat/lng` for `listing`, `service` **and** `vendor` rows is
sourced from a `left join lateral … order by created_at limit 1` over `vendor_locations`
(`0009:264`, `0009:362`, `0009:541`), a vendor that sets or moves its pin keeps stale — or null —
coordinates in the search projection until some unrelated write to `vendors`/`vendor_listings`/
`services` happens to fire. Every geo ranking result inherits this staleness.

**G-D3 — Multi-branch is read-only fiction.** `directory.py:213` `_parse_locations` is documented as
"All of a vendor's branches (a vendor may have many `vendor_locations` rows)" and
`VendorProfileDetail.locations` is a list. But the only write path,
`vendor_profile.py:432` `_upsert_location`, loads the single earliest-created row
(`_load_primary_location`, `vendor_profile.py:281`) and either inserts the first row or updates that
one. **A vendor cannot create a second branch through any supported surface.** The read side is
therefore dead capability, and any row beyond the first can only have arrived out-of-band.

**G-D4 — Where a second branch does exist, downstream code is wrong.**

- `directory.py:552` passes only `_first_location(row)` to `_matches_location`, so a vendor whose
  _second_ branch is inside the requested radius is filtered **out**.
- `checkout.py:271` `_fetch_vendor_locations` builds `dict[vendor_id → PickupLocationOut]` from an
  unordered `.in_()` query, so the pickup point a customer is shown is **whichever row the driver
  returned last** — non-deterministic across requests.
- `comparison.py:40` and all three `0009` projections take `order by created_at limit 1`, i.e. the
  oldest branch, silently.

**G-D5 — Directory does not scale and its facets do not match its filters.**
`directory.py:519` fetches **every** active vendor with no `range()`, then filters and paginates in
Python at `directory.py:583-586`. Around it sit `_aggregate_vendor_ratings` (3 queries),
`_vendor_category_paths`, `_vendor_listing_counts` and the demo-exclusion lookups — all over the
full vendor set on every request. Separately, `directory.py:588-599` computes facets from
`all_items` (the **unfiltered** list), so facet counts do not describe the current result set, and
the `locations` facet is keyed on free-text `landmark` (`directory.py:482`) giving unbounded
cardinality — one bucket per distinct string a vendor typed.

**G-D6 — Two different definitions of "verified".** `directory.py:160` `_is_verified` deliberately
uses only auditable approved tiers (`load_approved_tiers_for_client`) so that, per `0056`, an
orphaned bare `vendors.kyc_tier` is not surfaced. But `0009:585` computes the search
`boost_signals.verified` from raw `coalesce(v_row.kyc_tier, 0) >= 2`. A vendor with an orphaned tier
therefore **receives the +5% search boost while displaying as unverified** in the directory. `0056`
states such orphan rows exist and are deliberately not auto-upgraded.

**G-D7 — Delivery zone resolution falls back to substring-matching prose.** `checkout.py:165-175`
resolves a zone from `landmark` text via `"kabulonga" → lusaka_b`, `"woodlands"/"east park" →
lusaka_a`, `"ndola"/"kitwe"/… → pickup-only`. A customer in Kabulonga who writes "opposite the
Kabulonga Shoprite" gets band B; one who writes "Chelston" gets **no zone at all** and silently falls
through to pickup-only. Zone assignment — which sets a real money amount — currently depends on
which words the customer chose.

**G-D8 — No query-less nearby browse.** `search.py:23` declares `q: Query(min_length=1)`, so
`/search` cannot answer "what is open near me right now". `_geo_rerank` also only reorders the
candidate window `search_rrf` already returned, and that window is capped at 100 rows per lane across
three lanes (`0009:900,927,939`) — so proximity can reorder at most ~300 documents and can never
surface a nearby vendor that the lexical/vector lanes missed.

**G-D9 — Map mode is blocked by two independent constraints.** `apps/customer/next.config.ts:85` sets
`img-src 'self' data: blob: <cloudinary> <ga4>`, so no third-party tile host can load without a CSP
change; and CLAUDE #7 caps customer routes at 150KB gz JS, which a general-purpose map library
exceeds on its own. Both are deliberate and neither should be relaxed casually.

**G-D10 — `vendor_locations` RLS is correct but under-tested.** `services/api/tests/rls/test_matrix.py:2593`
records `update`/`delete` as `"permit"` for `CUSTOMER`, `OTHER_CUSTOMER` and `OTHER_VENDOR`. That is
**not** a hole: the harness treats `"permit"` as "the statement is not permission-denied"
(`test_matrix.py:2879`), and the owner-scoped `USING` clauses (`0002:338-370`) reduce a rival's
`UPDATE` to zero rows. But the matrix as written asserts only the absence of a privilege error, so
**no test asserts that a rival's write affects zero rows.** Any new branch table must ship a positive
cross-tenant isolation test rather than a matrix row alone.

### 2.4 Strategy intent vs. current code

From the committed distillations only:

| Strategy intent (cited)                                                                                                                                                                                                                    | Reality                                                                                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| "Vendor→Location→Listing hierarchy: multi-branch businesses with per-branch hours/staff/GPS/stock" (`strategy-bible-and-blueprint-distilled.md:60`)                                                                                        | Vendor→Listing only; branches read-only (G-D3)                                                                                        |
| "geo/open-now/Bayesian-quality/verification re-rank, map+list UI, 'New in town' / 'Around me' / 'On the route'" (`…distilled.md:45`)                                                                                                       | geo ✅, Bayesian ✅ (`0034`), verification ✅ (skewed, G-D6), open-now ✗, map ✗, route ✗                                              |
| "sector licences required for Tier-2 verification per category — ZAMRA, HPCZ, ERB, RTSA, NCC, ZIA, EIZ/SIZ, ZIEA, LAZ, ZICA, PIA, BoZ, ZICTA, ZEMA, WARMA, ZABS, Liquor Licensing Board, local councils, TEVETA/HEA…" (`…distilled.md:91`) | No licence model at all (2.1 #17)                                                                                                     |
| "trust tiers 0–3 … 2 regulator licence" (`…distilled.md:44`)                                                                                                                                                                               | **Conflicts with D9.** D9 rejects unverified Tier-0 and defines 3 tiers + a badge. Licences must attach _beside_ KYC, not renumber it |
| "rich profile w/ social links/photos/**branches**" is a **Silver K249/mo** perk (`master-plan-distilled-B.md:28`)                                                                                                                          | Paid tiers are flagged off (**D3**) ⇒ branch caps must be config-driven, defaulting to the free value                                 |
| "pickup point model (location/hours/contact)" (`master-plan-distilled-C.md:44`)                                                                                                                                                            | Location ✅, hours stored-not-used, contact ✗ per branch                                                                              |
| "delivery zones + fee calc by zone/vendor location, geocoding" (`master-plan-distilled-C.md:44`)                                                                                                                                           | Flat bands + prose matching (G-D7); no geocoding                                                                                      |
| "curated collections" on the homepage (`master-plan-distilled-A.md:48`)                                                                                                                                                                    | Platform `merch_slots` only; no vendor-curated collections                                                                            |

---

## 3. Phased additive contract

Each capability below states: **minimum data model → API → UI → RLS/privacy → migration risk →
offline/3G → admin workflow → tests → phase**. Every migration is additive; none alters or drops an
existing column. Migration numbers are indicative and must be re-sequenced at implementation time.

Phase key: **L** = launch (needed for the controlled live-beta of the no-money discovery surface per
**D30**) · **B** = beta (after L, before public) · **P2** = Phase 2 (needs its own ADR).

### 3.1 Structured Zambian addresses + privacy-safe landmarks/GPS — **L**

**Data model** (`0080_geo_address_structure.sql`, additive):

```
public.zm_regions           -- static reference, seeded
  code text primary key                   -- 'LSK', 'CBT', …  (10 provinces)
  kind text check (kind in ('province','district'))
  parent_code text references zm_regions(code)
  name text not null
  centroid_lat double precision, centroid_lng double precision

alter table public.addresses add column
  province_code  text references public.zm_regions(code),
  district_code  text references public.zm_regions(code),
  area_name      text,          -- free text, the compound/suburb ("Chelston", "Kabulonga")
  delivery_note  text;          -- gate colour, "ask for X" — never used for zone maths
```

`landmark` stays exactly as-is and stays **required**: it is the primary human addressing mode in
Zambia and must not be demoted. The structured fields are strictly **additive hints** — an address
with only a landmark remains valid forever.

**Privacy model — the core of this pebble.** Add to `vendor_locations`:

```
  location_precision text not null default 'area'
    check (location_precision in ('exact','area','hidden'))
```

and expose coordinates through **one** shared resolver rather than at each call site:

```
public.geo_public_point(lat, lng, precision) → (lat, lng)   -- IMMUTABLE
  'exact'  → unchanged                     (registered shopfront, vendor opted in)
  'area'   → rounded to 2dp (~1.1 km)      DEFAULT — matches near-me-toggle.tsx:20
  'hidden' → NULL, NULL                    (landmark text only; still routable by a human)
```

The public read path must select through this function; only the vendor owner, admin and
service-role read raw coordinates. Precision is a **vendor choice with an explanation**, defaulting
to the safe value — never silently exact.

**API.** `GET /directory`, `GET /directory/{slug}`, `GET /products/{slug}` and `GET /search` return
coarsened coordinates plus a new `location_precision` discriminator so the client can render
"approximate area" honestly instead of drawing a false-precision pin. `PATCH /vendor/profile`
accepts `location_precision`. `POST/PATCH /account/addresses` accept the new optional fields.

**UI.** Address form (`apps/customer/.../account/_components/address-form.tsx`) gains
province/district selects (from `zm_regions`, cached) and an `area_name` input, all optional, with
landmark unchanged and still first. Vendor profile gains a three-option precision control with plain
copy about what each publishes. All strings are next-intl keys under `account.*` / `vendor.profile.*`
(CLAUDE #2).

**RLS/privacy.** `zm_regions` is public read, service-role write. `vendor_locations` policies are
**unchanged** — the coarsening happens in the read projection, so this does not touch the existing
policy set. This is the fix for **G-D1**.

**Migration risk.** Low. All columns nullable except `location_precision`, which has a safe default.
Reversible by dropping the added columns and the function. The one behavioural change is that public
coordinates become coarser — deliberate, and it must be called out in the release note because
`comparison.py`'s pickup-availability check reads those coordinates (see 3.6).

**Offline/3G.** `zm_regions` is a small static payload — ship it as a build-time constant in
`packages/config`, not a runtime fetch, and cache-first in the service worker. Coarsening **reduces**
bytes. No new blocking request.

**Admin.** None. Region reference data changes by migration, not by an admin CRUD screen.

**Tests.** `geo_public_point` truth table across all three modes incl. NULL input; a public-route
test asserting anon never receives an `exact` coordinate for an `area`/`hidden` vendor; owner still
sees exact; address create/patch with and without structured fields; RLS matrix row for `zm_regions`.

### 3.2 Vendor / storefront branches — **L** (single branch hardening) + **B** (multi-branch)

Split deliberately, because **G-D3/G-D4** mean multi-branch is a _correctness_ problem before it is a
feature.

**L — make the existing single branch honest.** No schema change. Fix the three first-branch bugs:
give `vendor_locations` a deterministic ordering key, make `checkout.py:271` select deterministically,
and stop `directory.py:552` claiming to support branches it cannot filter. Add the missing
`vendor_locations(vendor_id)` index.

**B — real branches** (`0081_vendor_branches.sql`, additive):

```
alter table public.vendor_locations add column
  name          text,                     -- "Kabulonga branch"; null ⇒ display vendor name
  phone_msisdn  text check (phone_msisdn is null or phone_msisdn ~ '^260[79][0-9]{8}$'),
  is_primary    boolean not null default false,
  status        text not null default 'active'
                check (status in ('active','temporarily_closed','archived')),
  timezone      text not null default 'Africa/Lusaka',
  position      integer not null default 0;

create unique index vendor_locations_one_primary_uidx
  on public.vendor_locations (vendor_id) where is_primary;
create index vendor_locations_vendor_id_idx on public.vendor_locations (vendor_id);
```

The `phone_msisdn` CHECK is copied verbatim from `0046_vendor_whatsapp_msisdn.sql:27` — same
canonical form, same normalisation helper (`vendor_profile.py:normalize_whatsapp_msisdn`), so there
is one MSISDN contract in the codebase, not two.

Backfill sets `is_primary = true` on each vendor's earliest-created row, which makes the partial
unique index satisfiable and preserves today's "oldest row wins" behaviour exactly. **Every**
`order by created_at limit 1` becomes `where is_primary` — `comparison.py:40`, `0009:264`,
`0009:362`, `0009:541`, `vendor_profile.py:281`.

**Branch cap.** `master-plan-distilled-B.md:28` assigns multi-branch to the Silver tier. Since **D3**
keeps paid tiers off, the cap lives in `platform_config` (e.g. `vendor_max_branches`, default `3` for
everyone) and is read, never hard-coded — so switching it to tier-derived later is a config change,
not a rewrite.

**API.** New `/vendor/branches` CRUD (list/create/patch/delete, owner-scoped, cap-enforced,
primary-reassignment guarded). `PATCH /vendor/profile` keeps writing the primary branch for backward
compatibility. Public responses gain `name`, `phone_msisdn`, `status`, `is_primary`.

**UI.** Vendor: a branch list under `profile/` reusing `hours-editor.tsx` per branch. Customer: the
storefront renders branches as cards; the PDP and checkout name the branch offering pickup.

**RLS.** Existing owner/admin policies already scope by `vendor_id` and carry over unchanged. Add a
**positive** cross-tenant test (per **G-D10**): a rival vendor's `UPDATE` against another vendor's
branch affects **zero rows**.

**Migration risk.** Medium — the partial unique index fails if backfill misses a vendor. Backfill
first, index second, in one transaction; verify `count(*) where is_primary` equals
`count(distinct vendor_id)` before creating the index. Reversible by dropping index + columns.

**Offline/3G.** Cap branches server-side; return at most the cap. Branch cards are text — negligible
bytes. Do **not** lazy-load branches behind a second request on the storefront: one payload, one
render.

**Admin.** Read-only branch list on the vendor detail screen. No admin branch CRUD (**D33** —
admin surfaces are not fabricated where a manual path suffices).

**Tests.** Cap enforcement; exactly-one-primary invariant under concurrent writes; primary reassign;
archive hides from public but preserves order history; cross-tenant isolation; checkout picks the
primary deterministically.

### 3.3 Branch-aware availability and stock — **L** (availability) / **P2** (quantities)

This is the **D28 fence**, so the split matters and must be stated plainly.

**L — availability without quantities.** A listing gains an opt-in set of branches at which it can be
collected. No per-branch quantity, no reservations per branch, no transfers — the listing-level
`stock_qty` and `stock_reservations` (`0005:121`) spine is untouched.

```
public.vendor_listing_locations             -- 0082, additive
  listing_id  uuid references vendor_listings(id) on delete cascade
  location_id uuid references vendor_locations(id) on delete cascade
  primary key (listing_id, location_id)
```

Semantics, written into the column comment so it cannot drift: **"presence means this listing may be
collected here; it carries no quantity and is not an inventory record (D28)."** Absent rows mean "all
active branches", so existing listings need no backfill.

**P2 — per-branch quantities.** `stock_qty` per branch, branch-scoped reservations, low-stock alerts
per branch, transfers. This **is** multi-warehouse inventory and is **Deferred by decision (D28)**.
It must not be built without a dated ADR (candidate **ADR-R02-04-E**, §7).

**API.** `GET /directory/{slug}`, PDP and comparison expose `available_at: [{location_id, name}]`.
Checkout's pickup step lists only branches linked to every item in that vendor's group.

**UI.** PDP: "Collect at: Kabulonga · Chilenje". Checkout: a branch radio instead of the current
implicit single pickup point.

**RLS.** New table mirrors `vendor_listings`: public read when both parents are active; owner write;
admin all. Needs its own RLS-matrix row **and** a cross-tenant test.

**Migration risk.** Low — new join table, empty at first, absence means "all branches".

**Offline/3G.** Adds one small array per listing. Fold it into the existing PDP payload; do not add a
request.

**Admin.** None at L.

**Tests.** Empty set ⇒ all active branches; archived branch drops out of pickup options; checkout
rejects a branch not linked to every item in the group; **an explicit test asserting no quantity
column exists on this table**, so the D28 fence is enforced by CI rather than by memory.

### 3.4 Hours, contact and social — **L**

**Data model** (`0083_vendor_hours_contact.sql`):

```
alter table public.vendor_locations add column
  hours_exceptions jsonb not null default '[]'::jsonb;   -- [{date, closed} | {date, open, close}]

alter table public.vendors add column
  contact_phone_msisdn text check (… same regex as 0046 …),
  social_links jsonb not null default '{}'::jsonb;        -- allow-listed keys only
```

`social_links` keys are allow-listed server-side (`facebook | instagram | tiktok | x | website`) with
per-key URL validation, host allow-list and `https` enforcement. **A vendor-supplied URL is untrusted
input**: render as `rel="noopener noreferrer nofollow"`, never auto-fetch it, never render an
og-preview from it, and never let it into the search projection body.

Hours semantics get pinned down where they are currently undefined:

- `timezone` per branch (3.2), defaulting `Africa/Lusaka`.
- `open > close` means **overnight** (closes after midnight) — decide it explicitly and document it in
  the column comment, because today it validates and means nothing.
- `hours_exceptions` overrides the weekly pattern for a given date; the array is capped
  (e.g. 60 entries) and past entries are swept.

**API.** `PATCH /vendor/profile` and `/vendor/branches` accept `hours_exceptions`, `contact_phone_msisdn`,
`social_links`. Public payloads gain them.

**UI.** Vendor: exceptions editor beside `hours-editor.tsx`; social link fields with inline validation.
Customer: contact row on the storefront next to the existing WhatsApp deep link.

**RLS/privacy.** No policy change. `contact_phone_msisdn` is a **business** contact, published
deliberately — the consent copy must say so, and it must stay distinct from `payout_msisdn`
(the money rail) exactly as `0046` keeps `whatsapp_msisdn` distinct.

**Migration risk.** Low, all additive with safe defaults.

**Offline/3G.** Social links are icon + href; use inline SVG from `packages/ui`, no third-party
badge scripts (which would also breach the CSP).

**Admin.** Social links and contact phone are moderatable content — surface them in the existing
moderation queue rather than building a new screen.

**Tests.** Overnight-hours truth table; exception overrides weekly pattern; DST-free `Africa/Lusaka`
assumption asserted; social-link scheme/host rejection incl. `javascript:` and unicode-confusable
hosts; MSISDN normalisation shared with `0046`.

### 3.5 Open-now — **L**

The single highest-value item here: the data already exists and is inert (**2.1 #7**).

**Data model.** None. Open-now is computed, never stored — a stored flag would need a cron and would
be wrong between ticks.

```
public.location_is_open(hours jsonb, exceptions jsonb, tz text, at timestamptz) → boolean
  -- IMMUTABLE-in-practice; called with an explicit `at`, never now(), so it is testable
```

**API.** `open_now=true` filter on `/directory` and on the nearby endpoint (3.6). Every branch in a
response carries `open_now: bool` and `opens_at`/`closes_at` hints so the UI can render "Closes in 40
min" without a second round-trip.

Compute `open_now` **server-side**, then let the client re-derive it from `opens_at`/`closes_at` for
cached payloads — otherwise a service-worker-cached storefront shows a shop as open at midnight.

**Ranking.** `boost_signals.open_now` is deliberately **not** added at L. Adding it means recomputing
the projection every time a shop opens or closes, i.e. a scheduled reindex — cost the budget (**D6**)
does not need to carry for a discovery beta. Open-now is a **filter and a badge** at L; the ranking
boost the strategy describes (`…distilled.md:45`) is **B**, behind candidate **ADR-R02-04-C** (§7).

**UI.** "Open now" chip on directory and nearby; per-branch "Open · closes 18:00" / "Closed · opens
Mon 08:00" line.

**Privacy.** None — hours are already public.

**Migration risk.** Very low; one function.

**Offline/3G.** The `opens_at`/`closes_at` approach is what makes a cached page honest offline. This
is a hard requirement, not a nicety.

**Admin.** None.

**Tests.** Boundary minutes (open, close, exactly-on); overnight spans; all-closed day; exception day;
empty `hours` ⇒ `open_now = null` (unknown), never `false` — a vendor who has not set hours must not
be rendered as closed.

### 3.6 Nearby, map/list, distance, route — **L** (nearby/list) · **B** (map) · **P2** (route)

**L — a real nearby endpoint.** `GET /nearby?lat&lng&radius_km&kind&open_now&page` returning vendors
and branches sorted by true distance, with `distance_km` on every item. This is the fix for **G-D8**:
it needs no query string, so "what is open near me" becomes answerable.

Distance must be computed **in SQL**, not in Python over a full table read (**G-D5**). Without
PostGIS (`0001_extensions.sql` installs only `pgcrypto`, `pg_trgm`, `vector`, and adding PostGIS to
Supabase free tier is a decision, not an assumption), use a bounding-box prefilter on indexed
`lat`/`lng` plus exact haversine on the survivors:

```
create index vendor_locations_lat_lng_idx on public.vendor_locations (lat, lng);
-- WHERE lat between $1 and $2 and lng between $3 and $4   → then exact haversine, then order
```

Correct and cheap at Zambian data volumes. Whether to adopt PostGIS/`earthdistance` instead is
candidate **ADR-R02-04-B** (§7) — deliberately not assumed here.

**Directory fix.** Rewrite `list_directory_vendors` to push filtering, distance and pagination into
SQL, match against **any** branch (fixing **G-D4**), and compute facets over the **filtered** set
(fixing **G-D5**). The `locations` facet switches from free-text `landmark` to `district_code` from
3.1, giving bounded cardinality.

**B — map/list toggle.** Blocked by **G-D9** on two independent axes. The only launch-safe options
are (a) list-only with a static, server-rendered map image, or (b) a self-hosted lightweight vector
map. Either needs a CSP `img-src`/`connect-src` amendment and a route-level bundle-budget exemption.
That combination is a decision, not an implementation detail: candidate **ADR-R02-04-D** (§7). **Do
not add a map library before that ADR is accepted.**

**P2 — route mode.** "On the route" (`…distilled.md:45`) needs a routing engine (OSRM self-hosted or a
paid Directions API) plus corridor search. Both fail **D6** or **D16** today. **Deferred.**

**Also fix at L:** `comparison.py:99` `is_lusaka_delivery_available` hard-codes a 35km radius from
hard-coded CBD coordinates. Move both to `platform_config` so ops can adjust without a deploy, and
note that 3.1's coarsening shifts a pin by up to ~1.1km — immaterial against a 35km radius, but it
must be stated in the release note rather than discovered.

**UI.** Nearby is a customer route with a distance chip per card. It reuses `near-me-toggle.tsx`
verbatim — the same 2dp coarsening, the same permission-denied copy.

**RLS/privacy.** The nearby endpoint returns **coarsened** coordinates (3.1) and must **never**
accept an unbounded radius: cap `radius_km` server-side (the existing `Query(gt=0, le=500)` at
`directory.py:846` is the precedent) so it cannot be walked as a vendor-address enumeration oracle.
Rate-limit it like the other public read endpoints.

**Migration risk.** Low (indexes + config rows). The directory rewrite is behaviour-visible: keep the
current response shape, add fields only, and diff old-vs-new orderings on seed data before merging.

**Offline/3G.** Nearby is inherently online (it needs a fix). Cache the **last** nearby result
stale-while-revalidate with a visible "as of" timestamp; never show a stale distance as live.

**Admin.** None.

**Tests.** Bounding-box vs. brute-force haversine agreement on seeded fixtures; antimeridian and
pole inputs rejected by the existing `ge/le` bounds; radius cap enforced; second-branch match (the
**G-D4** regression); facets reflect filters (the **G-D5** regression); coarsened coordinates in every
public response.

### 3.7 Delivery areas and service areas — **L** (honesty) · **B** (polygons)

**L.** Replace prose-matching (**G-D7**) with something checkable, without adding geometry:

```
alter table public.delivery_zones add column
  district_code text references public.zm_regions(code),
  centroid_lat double precision, centroid_lng double precision,
  max_radius_km numeric(6,2);
```

Resolution order becomes: **GPS → band by radius** (today's behaviour, kept) → **district_code →
band** (new, deterministic) → **pickup-only** (explicit). The landmark substring heuristic is
**deleted**, not extended. Where a zone cannot be resolved, the UI must say "we could not work out
your delivery area — pick up, or set your district", never silently price at zero.

**Service areas.** `services.service_area` (`0004:15`) is free text and unused. At L, keep the column
and add `service_area_district_codes text[]` beside it, so services become filterable by district
without a data migration of existing prose.

**B.** Vendor-declared delivery radius per branch (`delivers_within_km`), surfaced as "Delivers to
your area" on the PDP. Still no courier integration (**D16**).

**P2.** True zone polygons and geofencing — needs PostGIS (ADR-R02-04-B) and is only worth it once
delivery leaves Lusaka.

**API.** `GET /public-config` exposes zones with district codes so the client can render a picker.
Checkout returns `resolved_zone_key` plus a new `zone_source: 'gps' | 'district' | 'none'` so the
customer can be told **why** they were priced that way.

**RLS.** `delivery_zones` is already admin-managed via `admin_config.py:369`; unchanged.

**Migration risk.** Medium — this touches **money** (`compute_group_delivery_fee_ngwee`,
`checkout.py:181`). Ship behind a config flag, replay historical checkouts through old and new
resolvers, and diff the fee before enabling. Fees stay integer ngwee (CLAUDE #1) throughout.

**Offline/3G.** Zone list is small and cacheable; the district picker is a static select.

**Admin.** Extend the existing delivery-zone screen (`admin_config.py`) with the new fields. No new
surface.

**Tests.** Every current landmark-heuristic case re-expressed as a district case; unresolvable
address ⇒ explicit pickup-only with `zone_source: 'none'`; free-delivery threshold interaction
unchanged; **a fee-parity test** old-vs-new across seeded addresses.

### 3.8 Search ranking — **L** (fix) · **B** (tune)

**L — fix the two defects, add nothing.**

1. **G-D2:** add a `vendor_locations` AFTER INSERT/UPDATE/DELETE trigger that re-syncs the vendor
   document and every affected listing/service document. Guard it: a vendor with many listings must
   not turn one pin edit into an unbounded synchronous fan-out — enqueue via the existing
   `embedding_jobs` (`0022`) pattern rather than doing it inline.
2. **G-D6:** change `0009:585` to source `verified` from the same auditable approved-tier rule
   `directory.py:160` uses, so one definition of "verified" governs both display and ranking.

**B — tuning, each behind evidence.** Open-now boost (ADR-R02-04-C); the strategy's "2–3× distance
weight for commodities" (`…distilled.md:71`) — note `docs/plan/product-strategy-gap-audit.md` F6b
already dispositioned this as a post-v1 refinement, so it should be reopened there, not here;
raising the per-lane 100-row cap if nearby recall proves insufficient.

**Migration risk.** The `verified` change **alters live ranking**. Additive to schema, but capture
before/after top-20 for a seeded query set and attach the diff to the PR.

**Tests.** Pin move ⇒ listing/service/vendor documents all re-synced (the **G-D2** regression);
orphaned bare `kyc_tier` gets **no** verified boost (the **G-D6** regression); byte-identical ranking
when no location is supplied — the existing invariant at `services/search/__init__.py:445`.

### 3.9 Regulator / licence records, expiry monitoring, admin review — **B**

Built on the `kyc_records` shape (2.2), not a new pattern. **Beta**, not launch: **D8**'s launch
categories exclude every licence-gated vertical (no pharma, no alcohol, no live animals), so nothing
at launch requires a licence — which is exactly why this can be built carefully rather than fast.

**Data model** (`0084_vendor_licences.sql`):

```
public.regulators                              -- static reference, seeded from …distilled.md:91
  code text primary key                        -- 'ZAMRA','HPCZ','ERB','RTSA','NCC','ZICTA','ZEMA','WARMA','ZABS','TEVETA',…
  name text not null
  category_paths text[] not null default '{}'  -- which catalogue paths this regulator gates
  verify_url text                              -- public register, for the human reviewer

public.vendor_licences
  id uuid primary key
  vendor_id uuid not null references vendors(id) on delete cascade
  regulator_code text not null references regulators(code)
  licence_number text not null
  holder_name text                             -- as printed; may differ from display_name
  issued_on date
  expires_on date
  doc_storage_paths text[] not null default '{}'   -- PRIVATE bucket, same as kyc-docs
  status text not null default 'submitted'
    check (status in ('submitted','under_review','approved','rejected','expired','revoked'))
  reviewer_id uuid, reviewed_at timestamptz, review_reason text   -- immutable evidence
  created_at, updated_at
  unique (vendor_id, regulator_code, licence_number)
```

**Non-negotiables, from D35 and D9:**

- **No LLM approves anything.** An LLM may pre-fill `licence_number`/`expires_on` from an uploaded
  image **only** into separate `suggested_*` fields that no state transition ever reads. Status moves
  exclusively through a guarded transition function invoked by a human admin (CLAUDE #4).
- A licence is **not** a KYC tier (**D9**). It never writes `vendors.kyc_tier`. It is a separate
  badge with its own lifecycle. The strategy's "trust tier 2 = regulator licence"
  (`…distilled.md:44`) conflicts with D9 and is **not** adopted — recorded as a conflict, not
  silently reconciled.
- Documents live in a **private** Supabase bucket with short-TTL signed URLs, exactly as
  `admin_kyc.py:28-29`. Never Cloudinary — **D26** puts sensitive documents in private storage.
- A licence document contains third-party PII. Retention is bounded and the DPA basis documented
  alongside the KYC retention rules.

**Expiry monitoring.** A daily job (n8n, per **D6**'s automation preference) flags `expires_on` at
T-30/T-7/T-0, notifies the vendor via the existing outbox, and transitions to `expired` at T-0.
**`expired` must gate the category, not the vendor** — a lapsed licence hides licence-gated listings
and clears the badge; it does not suspend an otherwise-good vendor. That asymmetry is deliberate and
should be stated in the ADR.

**API.** Vendor: `/vendor/licences` CRUD (submit, replace, list) — the vendor may never set `status`.
Admin: `/admin/licences` queue with SLA badges, signed doc URLs, approve/reject with templated
reasons — a direct port of `admin_kyc.py`. Public: `GET /directory/{slug}` exposes at most
`{regulator_code, status: 'approved', expires_on}` — **never** the licence number, holder name or
document.

**UI.** Vendor: a licences section in onboarding, shown only when the vendor's categories intersect a
regulator's `category_paths`. Admin: a review queue beside the KYC queue. Customer: a "Licensed:
ZAMRA" badge with a plain-language explanation.

**RLS.** `regulators` public read / service-role write. `vendor_licences`: owner select+insert;
**no** owner update of `status` (trigger-guarded, mirroring `guard_vendor_status_update`,
`0002:124`); admin all; **no anon policy at all** — the public badge is served through a
service-role-computed projection, so the raw table is never anon-readable. This is stricter than
`kyc_records`, which grants `select` to `anon` (`0002:426`) while relying on the absence of an anon
policy; the new table should not repeat that belt-without-braces pattern.

**Migration risk.** Low — new tables. The judgement risk is high (regulator list accuracy), which is
why `regulators` is seed data reviewed by the founder, not a hard-coded enum.

**Offline/3G.** Document upload is the heaviest flow: client-side downscale before upload, resumable,
explicit data-cost warning. Reuse the KYC upload component rather than writing a second one.

**Admin workflow.** Queue → open → view signed docs → verify against `verify_url` (a human visiting
the public register) → approve/reject with reason → audited via `AdminAuditRecorder`. Reject reason
templates: `illegible_document`, `expired_licence`, `name_mismatch`, `wrong_regulator`,
`not_verifiable_on_register`, `other`.

**Tests.** Vendor cannot self-approve (trigger); LLM-suggested fields never reach a transition;
expiry job idempotent across reruns; expired licence hides gated listings but not the vendor;
licence number never appears in any public response (assert on the serialised payload, not the
model); RLS matrix rows + positive cross-tenant isolation tests for both tables.

### 3.10 Store collections — **B**

Vendor-curated collections ("Back to school", "Chitenge picks"). Distinct from platform
`merch_slots` (`0008:120`), whose `featured_collections` slot key (`admin_merch.py:33`) is
**admin-controlled homepage merchandising**, not a vendor capability.

**Data model** (`0085_store_collections.sql`):

```
public.store_collections
  id uuid primary key
  vendor_id uuid not null references vendors(id) on delete cascade
  slug text not null, title text not null, description text
  cover_public_id text                                    -- Cloudinary, D26
  status text not null default 'draft' check (status in ('draft','active','archived'))
  position integer not null default 0
  unique (vendor_id, slug)

public.store_collection_items
  collection_id uuid references store_collections(id) on delete cascade
  listing_id    uuid references vendor_listings(id) on delete cascade
  position integer not null default 0
  primary key (collection_id, listing_id)
```

**Cross-vendor integrity:** a trigger must reject an item whose `vendor_listings.vendor_id` differs
from the collection's `vendor_id`. A DB-level check, not an API check — the API is not the only
writer.

**Wholesale interaction (D28).** Collections are a discovery surface, so they are inside D28's
"every consumer discovery surface" fence: wholesale-only listings must be filtered from collection
contents for guests and non-verified consumers via the **existing** shared resolver
(`app/services/business/access.py` `get_business_access`) — never a second, parallel filter.

**API.** `/vendor/collections` CRUD (cap from `platform_config`); public
`GET /directory/{slug}/collections` and `/collections/{collection_slug}`.

**UI.** Vendor: collection builder reusing the listing picker. Customer: collection strip on the
storefront; a collection page with ISR + canonical URL (SEO is a launch-quality concern, so get the
canonical right the first time).

**RLS.** Public read when collection is `active` **and** parent vendor is `active`; owner write;
admin all. Matrix rows + cross-tenant tests for both tables.

**Migration risk.** Low; new tables, empty.

**Offline/3G.** Collections are cacheable, SEO-friendly, image-heavy — enforce the ≤8-image
convention and `f_auto,q_auto` (**D26**), and lazy-load below the fold.

**Admin.** Collections carry vendor-authored copy and imagery ⇒ they are moderatable. Route them into
the existing moderation queue; do not build a parallel review tool.

**Tests.** Cross-vendor listing rejected at the DB; archived collection 404s publicly but survives for
the owner; wholesale filtering matches the vendor storefront exactly (assert both call the same
resolver); slug uniqueness per vendor; cap enforced.

### 3.11 Trustworthy impression and search analytics — **L** (impressions) · **B** (vendor-facing)

`vendor_analytics.py:1-10` is refreshingly explicit that today's "views" metric is **cart activity,
not impressions**, and that `conversion` is therefore a cart-to-order rate. That honesty is the
baseline to preserve: the risk in this capability is not missing data, it is **publishing a number a
vendor will not trust**.

**Data model** (`0086_impression_events.sql`):

```
public.impression_events
  id uuid primary key
  surface text not null check (surface in ('search','directory','nearby','plp','collection','storefront'))
  entity_kind text not null check (entity_kind in ('listing','vendor','service','event'))
  entity_id uuid not null
  session_id uuid                       -- rotating, not a stable identity
  position integer                      -- rank at which it was shown
  query_hash text                       -- hash of normalized term; never the raw term
  created_at timestamptz not null default timezone('utc', now())
```

No `user_id`. No raw query text. Reuse `0027`'s 30-day trimming precedent, and the `0029` posture:
service-role write, admin read, **no** anon or vendor read of raw rows.

**Trustworthiness rules — these are the substance of this item:**

1. **An impression is a view, not a render.** Count only when the card is ≥50% visible for ≥1s
   (IntersectionObserver), mirroring the discipline already applied to clips, where
   `clips_engagement.py:55` documents "a view is three seconds of actual watching, not an
   impression".
2. **Deduplicate per session per entity per surface** within a window; a scroll-up-scroll-down must
   not inflate a count.
3. **Batch and beacon** — one `sendBeacon` per batch, never one request per card. On 3G this is the
   difference between a working feed and a stalled one.
4. **Exclude the vendor's own sessions** and known bots.
5. **Never expose a raw count to a vendor without its denominator.** Ship "shown 120 times · 14
   clicks · 2 orders" or ship nothing.
6. **Consent.** Impressions are behavioural analytics under the Zambia DPA. Route through the same
   consent gate as the GA4 mirror; if consent is absent, the server-side count still runs
   (anonymised, no session id) — matching the `0027`/`0029` stance of "anonymized regardless of
   consent".

**API.** Extend `POST /analytics/collect` (`analytics_collect.py`) — **do not** add a second
collection endpoint with a second rate limiter and a second validation path.

**UI.** An impression hook in `packages/ui` used by every card component, so no surface can silently
opt out or double-count.

**Migration risk.** Low schema risk; real **volume** risk — this is the highest-cardinality table
proposed. Mandate a retention sweep and a rollup from day one, and add the storage estimate to the
budget check (**D6**), not after.

**Offline/3G.** Drop batches when offline; **never** replay a stale batch on reconnect (it would
record an impression that never happened). Cap in-memory batch size.

**Admin.** Extend `admin_search_insights.py` with impression-derived CTR by surface.

**Tests.** Dedup within a session; 50%/1s threshold; batch cap; no `user_id` or raw term in any
persisted row (assert on the row, not the request); offline batches dropped not replayed;
vendor-facing numbers always carry denominators.

---

## 4. RLS and privacy summary

| Table                      | anon                    | customer         | vendor owner                            | admin  | Note                                                       |
| -------------------------- | ----------------------- | ---------------- | --------------------------------------- | ------ | ---------------------------------------------------------- |
| `zm_regions`               | select                  | select           | select                                  | all    | static reference                                           |
| `vendor_locations` (+cols) | select **coarsened**    | select coarsened | own: all                                | all    | fixes G-D1 via projection, policies unchanged              |
| `vendor_listing_locations` | select (parents active) | select           | own: all                                | all    | no quantity column — D28                                   |
| `regulators`               | select                  | select           | select                                  | all    | static reference                                           |
| `vendor_licences`          | **none**                | **none**         | own: select+insert; **no** status write | all    | strictest table proposed; public badge via projection only |
| `store_collections`        | select (active+active)  | select           | own: all                                | all    |                                                            |
| `store_collection_items`   | select (parents active) | select           | own: all                                | all    |                                                            |
| `impression_events`        | **none**                | **none**         | **none**                                | select | service-role write only                                    |

Every new table ships: `enable row level security` **and** `force row level security` (the **D32**
posture, and `0064_force_rls_launch_tables.sql` is the precedent), an RLS-matrix row in
`services/api/tests/rls/test_matrix.py`, **and** — per **G-D10** — at least one positive cross-tenant
test asserting a rival's write affects zero rows.

**Privacy positions taken:**

- Vendor GPS defaults to ~1.1km precision; exact is opt-in with informed copy (fixes G-D1).
- Buyer GPS stays coarsened client-side before transmission (`near-me-toggle.tsx:20`) — unchanged.
- Licence documents: private bucket, short-TTL signed URLs, bounded retention, admin-only.
- Impressions: no `user_id`, no raw query text, rotating session id, 30-day trim.
- Nearby endpoint radius is capped and rate-limited so it cannot be walked as an address oracle.

---

## 5. Offline and 3G posture

The service worker (`apps/customer/sw.ts`) already routes API GETs NetworkFirst and catalog
navigations StaleWhileRevalidate. Consequences that must shape the build:

1. **Cached pages must not lie about time.** Anything time-dependent (open-now) ships with
   `opens_at`/`closes_at` so the client re-derives state from the device clock. A boolean alone
   guarantees a wrong badge on a cached page (§3.5).
2. **Cached pages must not lie about distance.** Nearby results carry an "as of" timestamp.
3. **No new blocking third-party request** on a customer route. Region data is a build-time constant;
   social icons are inline SVG; map tiles are blocked by CSP until ADR-R02-04-D.
4. **Uploads are the expensive flow.** Licence documents must be downscaled client-side and
   resumable, with an explicit data-cost warning — Zambian mobile data is metered and this is the
   flow most likely to be abandoned.
5. **Impressions must be batched via `sendBeacon`** and dropped, never replayed, when offline.
6. **Every payload addition is byte-audited** against the ≤150KB gz budget in the pebble's PR, not
   after the fact.

---

## 6. Migration risk register

| Risk                                                      | Severity | Mitigation                                                                                            |
| --------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------- |
| `is_primary` partial unique index fails on backfill       | High     | Backfill then index in one transaction; assert `count(is_primary) == count(distinct vendor_id)` first |
| Delivery-zone rewrite changes a **money** amount          | High     | Config-flagged; replay historical checkouts; fee-parity diff attached to the PR (CLAUDE #1)           |
| `verified` ranking change reorders live results           | Medium   | Capture before/after top-20 on a seeded query set; attach diff                                        |
| `vendor_locations` re-sync trigger fan-out on big vendors | Medium   | Enqueue via the `embedding_jobs` (`0022`) pattern; never re-sync inline                               |
| Coordinate coarsening shifts pickup-eligibility edges     | Low      | ~1.1km against a 35km radius; add a boundary test; state it in the release note                       |
| `impression_events` volume                                | Medium   | Retention sweep + rollup from day one; storage estimate into the D6 budget check                      |
| Branch-aware availability drifts into D28 inventory       | Medium   | CI test asserting no quantity column on `vendor_listing_locations`                                    |
| Regulator seed list inaccurate                            | Medium   | Founder-reviewed seed data, not a hard-coded enum; `verify_url` per regulator                         |

All proposed migrations are additive and reversible by dropping the added objects. None alters an
existing column type or drops a column (CLAUDE #6).

---

## 7. Candidate ADRs — founder decision required

None of these is decided. Each needs a dated entry in `docs/plan/00-decisions.md` before the
dependent pebble is built.

| ID               | Question                                                                                                                            | Recommendation                                                                                                                                               | Blocks      |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------- |
| **ADR-R02-04-A** | Is there a **Mountain 19 — Geo, Storefront & Licensing**? M01–M18 are consumed and CLAUDE #10 requires PR titles `M{nn}-P{nn}`.     | **Yes** — open M19 and number these pebbles under it. Without it the pebbles cannot be titled per convention.                                                | all pebbles |
| **ADR-R02-04-B** | Adopt **PostGIS** (or `earthdistance`/`cube`) on Supabase, or stay with bounding-box + haversine?                                   | **Stay bounding-box + haversine for L/B.** Correct at Zambian volumes, no extension risk, no cost. Revisit only if nearby p95 degrades.                      | 3.6, 3.7 P2 |
| **ADR-R02-04-C** | Should **open-now** become a ranking boost (`boost_signals.open_now`) as well as a filter?                                          | **Filter + badge at L; boost at B only if measured.** A boost forces scheduled reindexing — a D6 cost with no evidence behind it yet.                        | 3.5, 3.8    |
| **ADR-R02-04-D** | Ship a **map view**? It requires a CSP `img-src`/`connect-src` amendment **and** a route-level bundle-budget exemption (CLAUDE #7). | **Defer past launch.** If wanted at B, prefer a static server-rendered map image over an interactive library.                                                | 3.6 map     |
| **ADR-R02-04-E** | Does **per-branch stock quantity** get pulled into scope? This is squarely the **D28** multi-warehouse fence.                       | **No.** Keep D28. Ship branch-aware _availability_ only (3.3 L). Revisit when a real multi-branch vendor asks.                                               | 3.3 P2      |
| **ADR-R02-04-F** | Is a regulator licence a **KYC tier** (strategy `…distilled.md:44`) or a **separate badge** (this design)?                          | **Separate badge.** D9 locks 3 tiers + 1 earned badge; renumbering the trust ladder would ripple through caps, quotas and payouts.                           | 3.9         |
| **ADR-R02-04-G** | Which **regulators** are in the seed list, and does an expired licence hide the **category** or **suspend the vendor**?             | **Hide the gated category only.** Suspension is disproportionate for a lapsed renewal. Seed list needs founder review — `…distilled.md:91` lists ~25 bodies. | 3.9         |
| **ADR-R02-04-H** | Are **branches** and **collections** free-tier features, or Silver perks (`master-plan-distilled-B.md:28`)?                         | **Free at launch, caps in `platform_config`.** D3 keeps paid tiers off; a config-driven cap makes tiering later a config change.                             | 3.2, 3.10   |

---

## 8. Proposed implementation order

Smallest safe order. Each pebble is one branch, one PR, with **exclusive file ownership** — no two
pebbles in the same wave touch the same file (the Phase-2 wave rule in `.claude/commands/vergeo5.md`).
Pebble IDs are provisional pending **ADR-R02-04-A**.

### Wave 0 — correctness, no new capability (unblocks everything)

| Pebble  | Title                             | Owns (exclusive)                                                                      | Depends | Phase |
| ------- | --------------------------------- | ------------------------------------------------------------------------------------- | ------- | ----- |
| **G01** | Search re-sync on location change | `supabase/migrations/0080_*.sql`, `services/api/tests/test_search_location_sync.py`   | —       | L     |
| **G02** | One definition of "verified"      | `supabase/migrations/0081_*.sql`, `services/api/tests/test_search_verified_parity.py` | —       | L     |
| **G03** | Deterministic primary branch      | `services/api/app/routers/comparison.py`, `services/api/app/routers/checkout.py`      | —       | L     |

G01 fixes **G-D2**, G02 fixes **G-D6**, G03 fixes the `checkout.py` half of **G-D4**. All three are
small, independent, and every later pebble inherits the bugs if they are skipped. G01/G02 own
disjoint migration files; G03 owns no migration.

### Wave 1 — privacy and address structure (needs Wave 0 merged)

| Pebble  | Title                             | Owns (exclusive)                                                                                                                                            | Depends | Phase |
| ------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ----- |
| **G04** | `zm_regions` + structured address | `supabase/migrations/0082_*.sql`, `packages/config/src/regions.ts`, `apps/customer/.../account/_components/address-form.tsx`                                | G01–G03 | L     |
| **G05** | Coordinate precision (**G-D1**)   | `supabase/migrations/0083_*.sql`, `services/api/app/services/geo/precision.py`, `services/api/app/routers/directory.py`, `products.py`, `vendor_profile.py` | G04     | L     |

G05 is the **highest-priority privacy fix** and must land before any surface that amplifies vendor
coordinates (G07, G08).

### Wave 2 — storefront depth (parallel after Wave 1)

| Pebble  | Title                                               | Owns (exclusive)                                                                                                                       | Depends  | Phase |
| ------- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| **G06** | Branches (schema + vendor UI)                       | `supabase/migrations/0084_*.sql`, `services/api/app/routers/vendor_branches.py`, `apps/vendor/.../profile/_components/branch-list.tsx` | G05      | B     |
| **G07** | Hours exceptions + open-now                         | `supabase/migrations/0085_*.sql`, `services/api/app/services/geo/hours.py`, `apps/vendor/.../profile/_components/hours-exceptions.tsx` | G05      | L     |
| **G08** | Nearby endpoint + directory rewrite (**G-D4/G-D5**) | `services/api/app/routers/nearby.py`, `services/api/app/routers/directory.py`, `apps/customer/.../nearby/`                             | G05, G07 | L     |

G07 and G08 both need G05 (coarsened coordinates) but own disjoint files. G08 takes sole ownership of
`directory.py` after G05 releases it — **G05 and G08 must not run concurrently**.

### Wave 3 — money-adjacent and contact

| Pebble  | Title                                 | Owns (exclusive)                                                                                                               | Depends | Phase |
| ------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------- | ----- |
| **G09** | Delivery zones by district (**G-D7**) | `supabase/migrations/0086_*.sql`, `services/api/app/routers/checkout.py`, `services/api/app/routers/admin_config.py`           | G04     | L     |
| **G10** | Contact phone + social links          | `supabase/migrations/0087_*.sql`, `services/api/app/routers/vendor_profile.py`, `apps/customer/.../storefront/contact-row.tsx` | G06     | L     |

**G09 touches money** (CLAUDE #1, #4) and needs the fee-parity diff in §6. It must not share a wave
with anything else touching `checkout.py` — hence G03 lands in Wave 0 and releases the file.

### Wave 4 — availability, collections, analytics

| Pebble  | Title                              | Owns (exclusive)                                                                                                                                    | Depends | Phase |
| ------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ----- |
| **G11** | Branch-aware availability (no qty) | `supabase/migrations/0088_*.sql`, `services/api/app/services/listings/availability.py`                                                              | G06     | L     |
| **G12** | Store collections                  | `supabase/migrations/0089_*.sql`, `services/api/app/routers/store_collections.py`, `apps/vendor/.../collections/`, `apps/customer/.../collections/` | G06     | B     |
| **G13** | Impression events                  | `supabase/migrations/0090_*.sql`, `services/api/app/routers/analytics_collect.py`, `packages/ui/src/hooks/use-impression.ts`                        | G08     | L     |

### Wave 5 — licensing (needs ADR-R02-04-F and -G accepted)

| Pebble  | Title                       | Owns (exclusive)                                                                        | Depends       | Phase |
| ------- | --------------------------- | --------------------------------------------------------------------------------------- | ------------- | ----- |
| **G14** | Regulators + licence schema | `supabase/migrations/0091_*.sql`, `services/api/app/services/licences/state_machine.py` | G06, ADR-F/-G | B     |
| **G15** | Vendor licence submission   | `services/api/app/routers/vendor_licences.py`, `apps/vendor/.../licences/`              | G14           | B     |
| **G16** | Admin licence review queue  | `services/api/app/routers/admin_licences.py`, `apps/admin/.../licences/`                | G14           | B     |
| **G17** | Expiry monitoring           | `infra/n8n/licence-expiry.json`, `services/api/app/routers/internal_licence_expiry.py`  | G14           | B     |

G15/G16/G17 are parallel after G14 and own disjoint apps. **G16 is the only pebble that may transition
a licence status, and only on an authenticated human admin action** (**D35**).

### Not scheduled — needs an accepted ADR first

Map view (ADR-D) · route mode (P2) · per-branch stock quantity (ADR-E, **D28**) · open-now ranking
boost (ADR-C) · commodity distance weighting (reopen `product-strategy-gap-audit.md` F6b) · zone
polygons (ADR-B).

---

## 9. Unresolved founder decisions

**Blocking a build start (§7):** ADR-R02-04-A (mountain number) blocks every pebble's PR title.
ADR-R02-04-F and -G block Wave 5 entirely.

**Blocking a specific pebble:** ADR-R02-04-B (G08 approach) · ADR-R02-04-D (map) · ADR-R02-04-E
(D28 fence) · ADR-R02-04-H (branch/collection caps).

**Pre-existing, unchanged by this document** — carried forward from `00-decisions.md` because they
touch surfaces here:

- **F8** — confirm or invert the D12 COD cap. `0008_config.sql:82` still carries the
  `-- F8: founder to confirm` marker. G09 changes delivery-fee resolution and would be safer merged
  after F8 is settled.
- **F1** (domain), **F2** (PACRA/TPIN) — a company TPIN is a T2 KYC input and would be the natural
  first real test of the licence flow.
- **F6** (courier MOUs) — bounds how far service-area modelling should go before it over-promises.
- **F9a** (Zamtel) — unrelated to geo, listed only because `0008` ties it to the same config table.

**Not auditable from the repository** — needs founder or ops input, not code:

1. Do any real vendors have more than one branch today? The answer decides whether G06 is beta or
   launch. (Live DB unreachable this session; `00-status.md` records the tables as empty.)
2. Which regulators actually matter for the recruited vendor mix? `…distilled.md:91` lists ~25 and
   **D8**'s launch categories gate none of them.
3. Is exact vendor GPS ever operationally required (e.g. for manual dispatch under **D16**)? If so,
   G05 must keep an admin-only exact-coordinate read path — the design assumes it should.

---

## 10. Adversarial notes on this document

Recorded so a later reader does not have to re-derive them:

- **The biggest risk here is scope creep dressed as coherence.** Branches → per-branch stock →
  transfers is a smooth slope straight through the D28 fence. §3.3's "no quantity column" CI test is
  the guardrail; it is deliberately a **test**, not a comment.
- **Open-now is the cheapest real win** and is listed first among features because the data already
  exists (§2.2) and nothing reads it. It should not be sequenced behind branches.
- **G-D1 (public exact GPS) is the most serious current finding.** It is a live privacy exposure in
  merged code, not a missing feature, and G05 should not be traded away for feature work.
- **Licensing looks urgent and is not.** No launch category (**D8**) requires a licence. Building it
  at beta, carefully, on the proven `admin_kyc.py` shape, beats building it fast at launch.
- **The strategy documents are not authority.** Where `…distilled.md:44` (licence = trust tier 2) or
  `master-plan-distilled-B.md:28` (branches = Silver perk) conflict with **D9**/**D3**, the locked
  decision wins and the conflict is recorded (§2.4, ADR-F, ADR-H) rather than quietly reconciled.
- **Everything in §2 was re-verified against the tree.** Where a claim could not be verified — live
  DB state, ops behaviour, founder intent — it is marked **Not auditable** rather than assumed.
