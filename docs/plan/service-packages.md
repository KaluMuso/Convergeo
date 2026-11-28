# Service packages — design

> **Amended 2026-11-27 — open list (migration `20261127120000`).** Founder decision: SP-2 and the
> "≤3 by construction" rule are superseded. A service now has an **open, vendor-ordered list of up to
> 10 active packages**; `tier` is only an optional legacy label. See "Open list amendment" at the end.

**Status:** built on `feat/clips-pilot-service-packages` (2026-11-13). Additive; no flag
needed because a service with no packages renders exactly as before.

## Goal

Let a service provider offer up to three clearly-scoped tiers on a service listing
(Fiverr-style, adapted to Zambia's quote-first, COD-first services market), so a
customer can compare them on the service page and ask for a quote **for a specific
package** instead of describing the job from scratch.

## Existing domain (what this builds on)

- `services` (0004 + 0045 `includes` + booking columns): one listing per service,
  `from_price_ngwee` (nullable = "ask for a quote"), `bookable` + `booking_price_ngwee`.
- **RFQ** (`rfq_threads` 0095, `routers/rfq.py`): `POST /rfq {service_id, requested_details}`
  opens (or reuses) one open thread per customer × service; the vendor replies with a
  quote in integer ngwee.
- **Booking** (`routers/service_booking.py` → `services/rfq/booking.py`): fixed-price
  booking → synthesized job + quote → `accept_quote` deposit spine → checkout. Online
  deposits are **not live** in the pilot (COD-first).

## Smallest coherent extension

1. **`service_packages` table** (migration `20261124090100`): `service_id`, denormalised
   `vendor_id` (trigger-checked to equal the service's vendor), `tier`
   (`basic|standard|premium`, **UNIQUE per service ⇒ at most 3 by construction**),
   `name`, `description`, `price_ngwee` (bigint, `NULL` = request a quote; CHECK > 0),
   `delivery_days` (1–90), `revisions` (0–10, `NULL` = not applicable), `includes`
   (≤8 × ≤120 chars), `status` (`active|archived`). FORCE RLS: public read only for
   active packages of **active services of active vendors**; owner reads all of
   theirs; admin reads all. **No client write grants** — writes go through the API.
2. **Guarded status transitions** (`services/service_packages/state.py`):
   `active ↔ archived` only, via one function that writes an `audit_log` row; the router
   never issues a raw status update. "Remove" in the vendor app = archive.
3. **API**
   - `GET /services/{slug}` gains `packages: [...]` (active only, tier order).
   - `GET /vendor/services/{id}/packages` (owner) · `PUT /vendor/services/{id}/packages/{tier}`
     (create-or-update; re-activates an archived tier) ·
     `POST /vendor/services/{id}/packages/{tier}/archive`.
   - `POST /rfq` accepts optional `package_id` (only with `service_id`). The server
     verifies the package belongs to that service and is active, then stores
     `rfq_threads.package_id` + an immutable `package_snapshot` (tier, name, price,
     delivery, revisions, includes) so the vendor quotes against what the customer saw.
   - `GET /admin/services` items gain `packages` (tier, name, price, status).
4. **Customer app** (`/s/[slug]`): a package comparison section, server-rendered (no
   new client JS beyond the existing quote modal). 360px: one card per tier in a
   horizontal scroll-snap row; ≥640px: three columns. Each card's CTA opens the existing
   request-quote modal **prefilled** with a localized package summary and carries the
   `package_id`.
5. **Vendor app** (service edit page): a packages editor — one panel per tier, enable /
   edit / archive, price-or-quote toggle, inline validation and guidance.
6. **Admin**: packages listed under each service in the services oversight module.

## Product decisions taken (reversible)

| #     | Decision                                                                                                                                                                       | Why                                                                                                                                                                               |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SP-1  | **Packages route to RFQ only.** Choosing a package never creates an order, deposit or payment. The existing direct-booking (service-level `booking_price_ngwee`) is unchanged. | Brief: no new payment path; pilot is COD-first and online deposits are not live. A future "book this package" can pass `package_id` into `create_booking` once deposits are live. |
| SP-2  | Tiers are fixed keys (`basic/standard/premium`); the vendor may offer any subset (1–3) and rename each.                                                                        | Stable comparison layout and i18n; unique key enforces "≤3" in the database.                                                                                                      |
| SP-3  | Price is either fixed ngwee or "request a quote" per package.                                                                                                                  | Many Zambian services price on site (transport, materials).                                                                                                                       |
| SP-4  | Price order across tiers is **guidance, not a rule** (the vendor app warns if a higher tier is cheaper).                                                                       | Avoid blocking legitimate structures (e.g. Premium = quote).                                                                                                                      |
| SP-5  | `from_price_ngwee` is **not** auto-derived from packages.                                                                                                                      | Keeps browse/sort semantics and existing listings untouched; vendor guidance suggests aligning it.                                                                                |
| SP-6  | One open RFQ thread per customer × service is kept; picking another package on a reused thread updates the thread's package to the latest choice.                              | Matches the existing thread-reuse rule; the vendor always sees the current ask.                                                                                                   |
| SP-7  | Archive instead of delete; an archived tier is re-activated by saving it again.                                                                                                | Threads reference packages; history stays intact (FK `ON DELETE SET NULL` regardless).                                                                                            |
| SP-8  | Limits: name 2–40 chars, description ≤300, delivery 1–90 days, revisions 0–10 or n/a, ≤8 includes × ≤120 chars.                                                                | Fits a 360px card; bounds abuse.                                                                                                                                                  |
| SP-10 | A package request is allowed on a **fixed-price** service too (plain service RFQs still require a quote-based service).                                                        | The published package is itself the vendor's invitation to quote; without this, packages on priced services would be dead buttons.                                                |
| SP-11 | Package reads on the public service page and admin list **degrade to "no packages"** on error.                                                                                 | The optional section must never take the service page down (e.g. API deployed seconds before its migration).                                                                      |
| SP-9  | Package text is screened with the same prohibited-content screen as service listings.                                                                                          | One moderation rule for all service copy.                                                                                                                                         |

## Tests

- pytest: validation (ints only for money, bounds, tier keys), authz (non-owner 404,
  customer 403), guarded transitions + audit rows, public detail hides archived /
  inactive, RFQ prefill (snapshot stored, foreign/archived package refused, package
  without service refused), admin listing includes packages, migration pinned (RLS,
  no client write grants, unique tier).
- RLS live-DB tests + matrix row (run in CI against `supabase db reset`).
- vitest: package comparison rendering + prefill text, vendor editor validation.

## Open list amendment (2026-11-27)

Supersedes SP-2 (fixed tiers) and the SP-4 tier-order warning; everything else stands.

- **Schema** (`20261127120000_service_packages_open_list.sql`, additive, reversible): `tier` is
  nullable (`NULL` or `basic|standard|premium`), the `unique (service_id, tier)` key is dropped,
  `sort_order` is added (backfilled basic 0 / standard 1 / premium 2 so existing services render
  unchanged), and a trigger caps **active** packages at 10 per service (advisory-locked per service;
  archived packages do not count). Down: documented at the top of the migration.
- **API**: `POST /vendor/services/{id}/packages` (create, cap 10 → `409 package_limit_reached`),
  `PUT .../packages/{package_id}` (update; re-activating an archived one also respects the cap),
  `DELETE .../packages/{package_id}` (hard delete, audited as `service_package.deleted`; RFQ threads
  keep their immutable snapshot, the FK is `ON DELETE SET NULL`), `POST .../packages/reorder`
  (`{ids}` must be exactly the active ids, else `409 package_order_mismatch`),
  `POST .../packages/{package_id}/archive` (unchanged semantics, now by id). The old
  `PUT .../packages/{tier}` routes are removed. Clients cannot set `tier`.
- **Money**: unchanged. `price_ngwee` is integer ngwee (NULL = quote); the only reader of a package
  price is the RFQ snapshot (`package_snapshot.price_ngwee`), which now carries `tier: null` for
  open-list packages. No order/payment/booking code reads packages (SP-1).
- **Vendor app**: add / remove / move up-down, "N of 10" counter, limit message. **Customer page**:
  cards in the vendor's order (snap row on mobile, 2 columns from `sm`, 3 from `lg`), no tier
  heading. **Admin** oversight lists name/price/status without a tier.
- **Locales**: new/changed keys are translated for en, fr and zh; bem and nya fall back to English
  copy for the new vendor-editor strings (same as the rest of that editor).
