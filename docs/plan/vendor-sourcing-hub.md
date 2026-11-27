# Vendor sourcing hub ("Source") — spec

**Status:** proposed, 2026-11-27 · **Surface:** vendor app only · **Money movement:** none · **Flag:** none (read-only discovery + a data-only request queue)

Founder ask: give vendors an Alibaba-style place to find what to stock or buy, with three tabs (Zambian suppliers, Made in Zambia, Import) and findable business services (printing, packaging, logistics, design).

## 1. User stories

- As a **retailer**, I search wholesale listings from other Convergeo vendors and compare tier prices, MOQ, location and verified status, then message the supplier on WhatsApp.
- As a **buyer of local goods**, I filter to products declared Made in Zambia and to manufacturers, to source locally.
- As a **vendor who wants a product from abroad**, I submit an import request (link, photo URLs, specs, quantity, target price) and get back an estimated landed cost in ZMW, with product, freight, duty and clearing shown as separate lines.
- As a **vendor who needs a business service**, I find printers, designers, packaging and logistics providers and open an RFQ with one.
- As a **wholesaler / manufacturer / importer / service provider**, I declare my supplier type and mark which listings are Made in Zambia, so I appear in the right tab.
- As **admin**, I see every import request in a queue, reply with a quote, and close or reopen it. Every action is audited.

## 2. What already exists (searched in code)

| Need | Exists | Where |
| --- | --- | --- |
| Wholesale listing, tier prices, MOQ | yes | `vendor_listings.wholesale`, `price_tiers jsonb` (validated by `is_valid_price_tiers`), `moq` (0003); `_enforce_wholesale_tier` in `routers/vendor_listings.py` |
| Wholesale hidden from customers | yes, locked | D28/D36, `catalog.py`, `directory.py`, `test_customer_no_wholesale_pricing.py`: wholesale prices are **vendor-app only** |
| Business buyer verification | yes (customer side) | `business_buyers`, `services/business/access.py` (does not unlock wholesale on customer paths) |
| Operating archetype | partial | `vendors.business_archetype` (`manufacturer`, `importer_wholesaler`, `service_professional`, ...) is an onboarding/education driver, single-valued, not discovery-facing. `vendors.archetype` is the merchandise category |
| Vendor trust signals | yes | `vendors.kyc_tier`, `status`, `preferred_badge`, `commercial_tier` |
| Contact | yes | `vendors.whatsapp_msisdn` (public wa.me contact), `vendor_locations.landmark/lat/lng` |
| RFQ | partial | `rfq_threads` (0095) supports services and `product_class = E` listings only; wholesale listings 404 for non-business buyers. Service RFQ works for any signed-in user, including a vendor |
| Services | yes | `services` (vertical in `ServiceVertical`: `printing-creative`, `tech-services`, ...). **No `logistics` or `packaging` vertical** |
| Manufacturer / made-in flag | **no** | nothing on vendors or listings |
| Import path | **no** | nothing |

## 3. Data model gaps (one additive, reversible migration)

1. `vendors.supplier_types text[] not null default '{}'`, subset of `wholesaler | manufacturer | importer | service_provider`. Empty means "not listed in the hub" (safe default). Owner-declared, admin-overridable. Kept separate from `business_archetype` (single-valued, onboarding semantics).
2. `vendor_listings.made_in_zambia boolean not null default false`. Self-declared; admin can unset (moderation).
3. `import_requests`: vendor-owned request. `title`, `description`, `reference_url` (https only), `image_urls text[]` (https, max 5), `quantity > 0`, `unit`, `target_unit_price_ngwee` (optional, bigint), `destination_city`, `status` (`submitted | in_review | quoted | closed | cancelled`), timestamps.
4. `import_request_quotes`: admin reply, many per request (revisions). Lines in integer ngwee, all `>= 0`: `product_ngwee`, `freight_ngwee`, `duty_ngwee`, `clearing_ngwee`, `other_ngwee`; `total_ngwee` generated; `lead_time_days`, `valid_until`, `notes`, `partner_label` (which importer, free text), `is_estimate boolean not null default true` with a CHECK that it stays true in this MVP.

RLS: both tables `enable` + `force` RLS. Vendors `select` only their own (`vendors.owner_user_id = auth.uid()`), admins `select` all; **no client insert/update/delete** (revoked); all writes go through the API with the service role and an authz check. Quotes are readable by the owning vendor only. Business-service verticals for logistics/packaging are **not** added here (customer-facing taxonomy change, see questions).

## 4. The three tabs (+ services), data sources

Endpoint `GET /vendor/sourcing/search?tab=&q=&category=&cursor=&limit=` requires `require_role("vendor")`; never exposed to customers or anonymous callers.

- **Zambian suppliers** (`tab=suppliers`): active `wholesale = true` listings of active vendors, excluding the caller's own vendor and demo media. Card: title, image, tier prices (`price_tiers`), MOQ, shop name, landmark, verified badge (`kyc_tier >= 2`), WhatsApp contact.
- **Made in Zambia** (`tab=made_in_zambia`): active listings with `made_in_zambia = true` (retail or wholesale; retail shown at its retail price, wholesale with tiers) plus shops whose `supplier_types` contains `manufacturer`.
- **Import** (`tab=import`): not a catalogue. Shows the caller's own import requests with status and latest quote, and a "Request an import" form. Quote card labels: "Estimate. Not an offer. No payment is taken."
- **Business services** (`tab=services`): active services in the business verticals (`printing-creative`, `tech-services`, plus `logistics` and `packaging` once added). Action: existing service RFQ (`POST /rfq` with `service_id`).

URL sync: `/source?tab=suppliers&q=...&category=...`. Category filter uses the existing `categories` tree.

## 5. Import MVP (curated request, no money)

Vendor submits request, status `submitted`. Admin queue in the admin app lists all requests; admin sets `in_review`, then posts a quote (lines in ngwee, estimate flag, validity, lead time), status becomes `quoted`. The vendor sees the latest quote with the line breakdown and a total, and can close the request or ask for a revision by submitting a new request referencing it (free text). Nothing creates an order, a payment, a ledger row or a notification to real customers. Vendor notification of a new quote goes through the normal outbox only if the founder approves (open question 4). Rate limits: 5 new requests per vendor per day, 60 admin writes per minute. Each admin write records through `AdminAuditRecorder` (before/after). Free text is screened with the existing prohibited-content screen; contact details in free text are not blocked (no chat here).

## 6. RBAC summary

| Actor | Search hub | Create / list import requests | Quote |
| --- | --- | --- | --- |
| anonymous / customer | no (403) | no | no |
| vendor | yes | own only (list by `vendor_id` of the caller) | read own |
| admin | n/a | read all | create, status change |

## 7. Open questions for the founder

1. Should an **unverified (T1) vendor** see other vendors' tier prices, or only `kyc_tier >= 2`? (Default in this PR: any active vendor.)
2. Who are the **partner importers**? MVP routes everything to the admin queue; do we want a partner login later, and who sets duty/clearing rates (static table vs. clearing agent quote)?
3. Add **`logistics` and `packaging` service verticals** to the shared taxonomy (touches customer service browse)?
4. Notify the vendor by WhatsApp/outbox when a quote lands? And a service-level target (e.g. first reply within 2 working days)?
5. Is "Made in Zambia" **self-declared** acceptable, or does it need admin verification / a ZABS or PACRA reference before the badge shows?
6. Should shops be able to opt out of appearing as suppliers while keeping wholesale listings? (Today: wholesale listings always appear; `supplier_types` only adds shop-level entries.)
7. Import categories to **exclude** (prohibited, ZABS/ZRA/ZEMA-regulated, used clothing, food): confirm list; reuse `screen_listing` as the first filter.
8. Does this need an **ADR amending D28/D36**? Wholesale stays vendor-app only, so we believe not.

## 8. Rollout

Migration is additive and not applied by this work. Registered in the migration inventories CI checks. UI is read-only discovery plus a data-only form, so no flag. Reversal: drop the two tables and three columns (documented in the migration header).
