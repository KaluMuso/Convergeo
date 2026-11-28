# Vendor sourcing hub ("Source") — spec

**Status:** founder decisions recorded 2026-11-27 (see section 7) · **Surface:** vendor app only · **Money movement:** none · **Flag:** none (read-only discovery + a data-only request queue)

Founder ask: give vendors an Alibaba-style place to find what to stock or buy, with three tabs (Zambian suppliers, Made in Zambia, Import) and findable business services (printing, design, packaging, logistics).

## 1. User stories

- As a **retailer**, I search wholesale listings from other Convergeo vendors and compare tier prices, MOQ, location and verified status, then message the supplier on WhatsApp.
- As a **buyer of local goods**, I filter to products declared Made in Zambia and to manufacturers, to source locally.
- As a **vendor who wants a product from abroad**, I submit an import request (link, photo URLs, specs, quantity, target price) and get back an estimated landed cost in ZMW, with product, freight, duty and clearing shown as separate lines.
- As a **vendor who needs a business service**, I find printers, designers, packaging and logistics providers and open an RFQ with one.
- As a **wholesaler / manufacturer / importer / service provider**, I declare my supplier type and claim Made in Zambia on listings I make, so I appear in the right tab once an admin approves.
- As **admin**, I see every import request in a queue, reply with a quote, and close it, and I review Made in Zambia claims (approve or reject, with the vendor's optional PACRA/ZABS reference). Every action is audited.

## 2. What already exists (searched in code)

| Need                                | Exists              | Where                                                                                                                                                                                                                     |
| ----------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Wholesale listing, tier prices, MOQ | yes                 | `vendor_listings.wholesale`, `price_tiers jsonb` (validated by `is_valid_price_tiers`), `moq` (0003); `_enforce_wholesale_tier` in `routers/vendor_listings.py`                                                           |
| Wholesale hidden from customers     | yes, locked         | D28/D36, `catalog.py`, `directory.py`, `test_customer_no_wholesale_pricing.py`: wholesale prices are **vendor-app only**                                                                                                  |
| Business buyer verification         | yes (customer side) | `business_buyers`, `services/business/access.py` (does not unlock wholesale on customer paths)                                                                                                                            |
| Operating archetype                 | partial             | `vendors.business_archetype` (`manufacturer`, `importer_wholesaler`, `service_professional`, ...) is an onboarding/education driver, single-valued, not discovery-facing. `vendors.archetype` is the merchandise category |
| Vendor trust signals                | yes                 | `vendors.kyc_tier`, `status`, `preferred_badge`, `commercial_tier`                                                                                                                                                        |
| Contact                             | yes                 | `vendors.whatsapp_msisdn` (public wa.me contact), `vendor_locations.landmark/lat/lng`                                                                                                                                     |
| RFQ                                 | partial             | `rfq_threads` (0095) supports services and `product_class = E` listings only; wholesale listings 404 for non-business buyers. Service RFQ works for any signed-in user, including a vendor                                |
| Services                            | yes                 | `services` (vertical in `ServiceVertical`: `printing-creative`, `tech-services`, ...). `services.category` is free text, so `logistics` and `packaging` need a code constant only, no seed                                |
| Manufacturer / made-in flag         | **no**              | nothing on vendors or listings                                                                                                                                                                                            |
| Import path                         | **no**              | nothing                                                                                                                                                                                                                   |

## 3. Data model gaps (one additive, reversible migration)

1. `vendors.supplier_types text[] not null default '{}'`, subset of `wholesaler | manufacturer | importer | service_provider`. Empty means "not listed in the hub" (safe default). Owner-declared, admin-overridable. Kept separate from `business_archetype` (single-valued, onboarding semantics).
2. Made in Zambia is a **claim reviewed by an admin**, on `vendor_listings`: `made_in_zambia_status` (`null | claimed | approved | rejected`), `made_in_zambia_reference` (optional PACRA/ZABS text, 3 to 80 chars), `made_in_zambia_claimed_at`, `made_in_zambia_reviewed_by`, `made_in_zambia_reviewed_at`, `made_in_zambia_review_note`. Vendors hold an RLS owner-update policy on their listings, so a guard trigger (`vendor_listings_made_in_zambia_guard`) blocks any non-service-role write that sets `approved`/`rejected` or touches the reviewer fields; an approval or rejection must carry reviewer and timestamp, and withdrawing a claim clears them.
3. `import_requests`: vendor-owned request. `title`, `description`, `reference_url` (https only), `image_urls text[]` (https, max 5), `quantity > 0`, `unit`, `target_unit_price_ngwee` (optional, bigint), `destination_city`, `status` (`submitted | in_review | quoted | closed | cancelled`), timestamps.
4. `import_request_quotes`: admin reply, many per request (revisions). Lines in integer ngwee, all `>= 0`: `product_ngwee`, `freight_ngwee`, `duty_ngwee`, `clearing_ngwee`, `other_ngwee`; `total_ngwee` generated; `lead_time_days`, `valid_until`, `notes`, `partner_label` (which importer, free text), `is_estimate boolean not null default true` with a CHECK that it stays true in this MVP.

RLS: both tables `enable` + `force` RLS. Vendors `select` only their own (`vendors.owner_user_id = auth.uid()`), admins `select` all; **no client insert/update/delete** (revoked); all writes go through the API with the service role and an authz check. Quotes are readable by the owning vendor only. `logistics` and `packaging` are added as service verticals in code (API literal, vendor and customer constants, i18n in all five locales); no database seed is needed because the category column is free text. The RFQ job categories (`logistics`, `packaging`) are extended the same way.

## 4. The three tabs (+ services), data sources

Endpoint `GET /vendor/sourcing/search?tab=&q=&category=&cursor=&limit=` requires `require_role("vendor")`; never exposed to customers or anonymous callers.

- **Zambian suppliers** (`tab=suppliers`): active `wholesale = true` listings of active vendors, excluding the caller's own vendor and demo media. Card: title, image, tier prices (`price_tiers`), MOQ, shop name, landmark, verified badge (`kyc_tier >= 2`), WhatsApp contact. **Bulk and tier prices are shown only to verified viewers (`kyc_tier >= 2`).** For an unverified vendor the API withholds `price_ngwee` and `price_tiers` (it returns `prices_locked: true` and `viewer_verified: false`), so nothing leaks through the network tab; the card stays visible with a "verify to see bulk prices" prompt linking to KYC onboarding.
- **Made in Zambia** (`tab=made_in_zambia`): active listings whose claim is **approved** (retail or wholesale). Claimed, rejected and unclaimed listings never appear, and the manufacturer-shop fallback is dropped, so the badge and the tab are approval-only.
- **Import** (`tab=import`): not a catalogue. Shows the caller's own import requests with status and latest quote, and a "Request an import" form. Quote card labels: "Estimate. Not an offer. No payment is taken."
- **Business services** (`tab=services`): active services in the business verticals (`printing-creative`, `tech-services`, `logistics`, `packaging`). Action: existing service RFQ (`POST /rfq` with `service_id`).

URL sync: `/source?tab=suppliers&q=...&category=...`. Category filter uses the existing `categories` tree.

## 5. Import MVP (curated request, no money)

Vendor submits request, status `submitted`. Admin queue in the admin app lists all requests; admin sets `in_review`, then posts a quote (lines in ngwee, estimate flag, validity, lead time), status becomes `quoted`. The vendor sees the latest quote with the line breakdown and a total, and can close the request or ask for a revision by submitting a new request referencing it (free text). Nothing creates an order, a payment or a ledger row. When an admin posts a quote the vendor owner is notified in-app (`in_app_notifications`, key `notifications.inApp.vendor.import_quote_ready`, link `/source`) and by email through the notification outbox (template `import_quote_ready`, Resend adapter, transactional). WhatsApp and SMS are deliberately not used. The notification is best effort and idempotent per quote (dedupe keys); a failure never fails or rolls back the audited quote. Rate limits: 5 new requests per vendor per day (the registered `write_standard` counter scope with a distinct key and a one-day window, because a new scope would violate `rate_counters_scope_check`), 60 admin writes per minute. Each admin write records through `AdminAuditRecorder` (before/after). Free text is screened with the existing prohibited-content screen; contact details in free text are not blocked (no chat here).

## 6. RBAC summary

| Actor                | Search hub | Create / list import requests                | Quote                                                                           |
| -------------------- | ---------- | -------------------------------------------- | ------------------------------------------------------------------------------- |
| anonymous / customer | no (403)   | no                                           | no                                                                              |
| vendor               | yes        | own only (list by `vendor_id` of the caller) | read own                                                                        |
| admin                | n/a        | read all                                     | create, status change; review Made in Zambia claims (`vendors.manage`, audited) |

## 7. Founder decisions (27 Nov 2026)

1. **Wholesale and tier prices are for verified vendors only** (`kyc_tier >= 2`). Unverified vendors see the card with a "verify to see bulk prices" prompt linking to KYC. Enforced server-side (section 4).
2. **Made in Zambia is claim and approve.** The vendor claims (optional PACRA/ZABS reference), an admin approves or rejects, and the reviewer and time are stored. The badge and the tab show approved only. The review queue reuses the import-requests pattern (`vendors.manage`, audited, rate limited). Folded into the existing sourcing migration; no second migration.
3. **`logistics` and `packaging` are service verticals**, included in the business-services tab, with i18n in all five locales.
4. **Quote notifications:** in-app and email through the outbox (Resend), new template keys. No WhatsApp, no SMS.

Still open, not blocking: who the partner importers are and who sets duty and clearing rates (MVP routes everything through the admin queue); import categories to exclude beyond the existing `screen_listing` screen; whether shops may opt out of appearing as suppliers while keeping wholesale listings; a first-reply service target. No ADR amending D28/D36 is needed because wholesale stays vendor-app only.

## 8. Rollout

Migration is additive and not applied by this work. Registered in the migration inventories CI checks. UI is read-only discovery plus a data-only form, so no flag. Reversal: drop the two tables, the Made in Zambia columns, trigger and function, and `vendors.supplier_types` (documented in the migration header).

**Migration numbering:** the file is `20261127100000_vendor_sourcing_hub.sql`. Merging it moves the migration inventory count from 199 to 200. #943 and #944 also add a migration and renumber 199 to 200, so whichever of the three merges second must bump to 201, and the third to 202, and refresh the inventory digests (`scripts/ci/coordinator-gate-inputs.json`, `.gitleaks.toml`) when it does.
