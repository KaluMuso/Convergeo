# R02-05 — B2B-lite readiness audit & phased route to full B2B

**Status:** discovery / advisory. **Date:** 2026-08-01. **Mode:** GATED — docs only.
**Audited against:** D2 (v1 verticals — Supplies thin), D24 (data model: supplies =
`vendor_listings.wholesale=true` + `price_tiers jsonb` + `moq`), D28 (B2B wholesale gating),
plus the §G v1 scope fence.
**Head at audit:** `7d8b3ae338a7ce198787a55bb45cd64a24ae7ffd` on
`claude/b2b-lite-readiness-audit-9yy8gt`; working tree clean at start.

This file **proposes**; it decides nothing. `docs/plan/00-status.md` and
`docs/plan/00-decisions.md` are untouched — new decisions appear here only as **candidate
ADRs** (§8) for the founder to accept, amend or reject.

## 0. How to read this

Every claim about the codebase carries a `path:line` citation. Each audited item is marked:

| Mark                     | Meaning                                                                                                           |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **Implemented**          | Present, wired, and covered by at least one test.                                                                 |
| **Partial**              | Present but incomplete, inconsistent between paths, or enforced at only one layer.                                |
| **Absent**               | Not built.                                                                                                        |
| **Deferred by decision** | Not built, and a locked decision says so (D28 / §G).                                                              |
| **Not auditable**        | Cannot be verified from the repo in this session (needs a live DB, a deployed origin, or a founder/legal answer). |

Source text, migration comments, prior audit prose and test names are treated as **evidence to
verify, not authority**. Where a code comment asserts a guarantee, the guarantee was re-derived
from the code before being recorded as Implemented.

---

## 1. Verdict

**The D28 thin slice is genuinely built at the API layer and is well tested there.** The shared
resolver exists, is the single eligibility source, and is applied at every consumer discovery
surface named in D28's 2026-07-15 follow-up. Seller-side, wholesale publishing is correctly
fenced behind auditable T2 KYC on the interactive create/update routes.

**Three structural weaknesses stop it short of "enforced".**

1. **The gate is API-deep, not RLS-deep.** `vendor_listings` and `search_documents` both grant
   public `SELECT` over the wholesale columns, so D28's "hidden from consumers" holds only for
   traffic that goes through FastAPI (§4, G1/G2).
2. **Wholesale price selection is a write-time decision that is never re-derived.** Cart lines
   persist `unit_price_ngwee` and `wholesale`; checkout and order creation consume them as given
   (§4, G3). Combined with permissive `cart_items` RLS this is a pricing-integrity hole that is
   broader than B2B but is reached _through_ the B2B tier logic.
3. **The verification lifecycle is one-way and drift-prone.** There is no suspend path despite
   `suspended` being a valid status, and a verified buyer can rewrite their own legal name and
   PACRA number while staying verified (§4, G4/G9).

None of these are Phase-2 features. They are launch-hardening on the slice D28 already
authorised, and they are the whole of the proposed **Wave B0**.

Everything beyond that — organisations, goods RFQ, quotes, contract pricing, warehouses,
B2B invoices, credit — is **Absent and correctly so** (D28 + §G). §5 sequences it without
pulling any financial risk forward.

### 1.1 Conformance at a glance

| Requirement (source)                                                                      | Status                                                                                                 |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Buyer-side `business_buyers` identity, PACRA + optional TPIN (D28)                        | **Implemented**                                                                                        |
| `pending→verified/rejected/suspended` lifecycle, status server-controlled (D28)           | **Partial** — no suspend path; post-verification detail drift (G4, G9)                                 |
| Single shared resolver `is_verified_business` / `business/access.py` (D28)                | **Implemented**                                                                                        |
| Enforced identically at discovery, cart pricing, checkout (D28)                           | **Partial** — discovery yes; cart yes at write; checkout/order do not re-derive (G3)                   |
| Wholesale hidden on _every_ consumer discovery surface (D28 follow-up)                    | **Partial** — API layer complete; DB layer open (G1, G2)                                               |
| Consumer always sees retail (D28)                                                         | **Partial** — true for price; a wholesale-only listing is still purchasable at retail with no MOQ (G8) |
| Supplies = `wholesale=true` + `price_tiers jsonb` + `moq` (D24)                           | **Implemented**                                                                                        |
| Supplies discoverable in a Supplies tab (D2)                                              | **Implemented** (gated)                                                                                |
| No credit terms, RFQ-broadcast for goods, business accounts, account managers v1 (D2, §G) | **Deferred by decision** — correctly absent                                                            |
| Vendor archetype persisted on the vendor row (D28 follow-up)                              | **Implemented**                                                                                        |

---

## 2. What is implemented

### 2.1 Buyer identity and the verification gate — **Implemented**

`supabase/migrations/0038_business_buyers.sql` creates `business_buyers` with
`user_id` unique FK to `profiles`, `legal_name`, `registration_no` (PACRA),
nullable `tpin`, and `status` constrained to `pending|verified|rejected|suspended`
(`0038:17-29`).

- **Status is server-controlled.** `guard_business_buyer_status_update()` raises unless the
  session is `postgres`/`supabase_admin`, `service_role`, or holds `admin`, blocking any change
  to `status`, `verified_at` or `user_id` (`0038:46-76`). Owners genuinely cannot self-verify.
- **RLS is present and FORCEd** (`0038:102-103`), with owner select/insert/update and admin-all
  policies; the insert policy pins `status = 'pending'` (`0038:114-121`). There is deliberately
  no owner DELETE policy, and no `anon` grant (`0038:149`).
- **`is_verified_business(uuid)`** is a `stable security definer` SQL function returning true only
  for `status = 'verified'` (`0038:81-94`).
- **RLS matrix coverage exists** — `services/api/tests/rls/test_matrix.py:224-246` asserts the
  per-persona shape (anon `deny_all`, customer insert `deny`, etc.).

The API resolver mirrors this in one place: `BusinessAccess`/`get_business_access`/
`require_wholesale_access` in `services/api/app/services/business/access.py:29-113`.
`eligible` is `status == "verified"` and nothing else (`access.py:73-77`); guests short-circuit
to `ANON_ACCESS` (`access.py:38,94-98`); a malformed or expired bearer token degrades to guest
rather than erroring (`access.py:80-87`).

Buyer-facing endpoints: `GET /business/status` and `POST /business/apply`
(`routers/business.py:67-97`), with a **rate limit** of 10/min per `client_ip:user_id` on apply
(`business.py:37-50`). Re-application is allowed only from `pending|rejected`
(`services/business/store.py:22,51-58`), and a resubmission resets to `pending` and clears
`reviewer_notes`/`verified_at` (`store.py:60-73`).

Admin: `POST /admin/business/{id}/verify|reject` behind `require_role("admin")` on an
`AdminAuditedRoute`, each recording a before/after audit entry and enqueueing a buyer
notification through the shared outbox (`routers/admin_business.py:21-26,122-183`).
UI exists on both sides: `apps/admin/app/[locale]/business/_components/BusinessQueue.tsx`,
`apps/customer/app/[locale]/account/business/page.tsx`.

### 2.2 Wholesale visibility rules — **Implemented at the API layer**

D28's follow-up demands hiding across _every_ consumer surface. Each is present and each takes
its decision from `BusinessAccess.eligible` — not from a listing flag, not from a client
parameter:

| Surface                               | Enforcement                                  | Evidence                                         |
| ------------------------------------- | -------------------------------------------- | ------------------------------------------------ |
| Supplies feed (`?wholesale=true`)     | Hard 403 via `require_wholesale_access`      | `routers/catalog.py:858-861`                     |
| Catalog PLP + facet counts            | Candidates filtered before faceting          | `catalog.py:783-789`, called at `catalog.py:878` |
| Product detail (PDP)                  | Listing rows filtered                        | `routers/products.py:405-409`, `products.py:693` |
| Price comparison                      | Listing rows filtered                        | `routers/comparison.py:151-154,228`              |
| Vendor storefront / directory profile | Listing rows filtered                        | `routers/directory.py:750-753,878`               |
| FTS search + suggest                  | Wholesale hits dropped post-RRF              | `services/search/__init__.py:408-409,496-497`    |
| Search facet counts (SQL)             | `exclude_wholesale` defaults true in the RPC | `supabase/migrations/0068_...sql:20,42-48,161`   |
| "Ask Vergeo" RAG retrieval            | Dropped **unconditionally**, not gated       | `services/ask/retrieve.py:65-68`                 |

The Ask-Vergeo behaviour is right and deliberate: the answer cache is query-keyed, so a
verified buyer's retrieval must not seed a cache entry a consumer could read
(`ask/retrieve.py:65-67`).

`drop_wholesale_listing_hits` (`services/search/__init__.py:194-218`) exists because
`search_documents` carries no wholesale column — confirmed: `wholesale` appears nowhere in
`supabase/migrations/0009_search.sql`. The compensating per-request `vendor_listings` probe is
correct but is a post-filter, which is what makes G2 possible.

Frontend mirrors the gate rather than owning it: `supplies/page.tsx:235-244` server-side checks
`/business/status` before rendering and marks the route non-indexable
(`supplies/page.tsx:169`); the Supplies nav entry is conditional
(`_components/use-business-eligibility.ts`, `bottom-nav-client.tsx:16`).

### 2.3 Price tiers and MOQ — **Implemented (with authoring gaps, §4)**

- **Storage** matches D24 exactly: `vendor_listings.wholesale boolean`, `price_tiers jsonb`
  with a DB-level shape check, `moq integer not null default 1 check (moq >= 1)`
  (`0003_catalog.sql:96-98`), indexed on `(status, wholesale)` (`0003:109`).
- **Shape validation in the DB**: `is_valid_price_tiers(jsonb)` requires an array of
  `{min_qty, price_ngwee}` positive ints (`0003:8-32`), hardened with a pinned `search_path`
  (`0047_harden_function_search_path.sql:20`).
- **Tier selection**: `select_unit_price_ngwee` picks the highest applicable `min_qty` tier and
  otherwise returns base retail (`services/cart/totals.py:10-29`). Money stays integer ngwee
  throughout — no float appears on this path.
- **MOQ**: `validate_moq` raises `cart.moq_violation` (HTTP 400, `retry: true`) only when the
  line is wholesale-eligible (`totals.py:32-40`).
- **Monotonicity**: authoring routes require strictly ascending `min_qty` and strictly
  descending `price_ngwee` (`vendor_listings.py:166-189`,
  `vendor_listings_manage.py:146-168`), mirrored in the CSV importer
  (`services/listings/csv_import.py:96-119`).
- **Commission**: the 3% supplies/wholesale rate from D4 is exercised
  (`tests/test_commissions_invoicing.py:190,213`).

### 2.4 Cart enforcement — **Implemented at write time**

`wholesale` is re-derived, never trusted from the stored line:

```
wholesale = bool(listing.get("wholesale", False)) and business_eligible
```

— `services/cart/merge.py:75` (guest→user merge) and `merge.py:139`
(`validate_item_qty_for_listing`). Eligibility is resolved per request via
`_business_eligible_for_user`, which returns `False` for any guest and reads the buyer's own row
(`routers/cart.py:179-184`). Add and update both re-run the derivation, including on the
quantity-accumulating branch (`cart.py:409-411,431-433,483-485`).

Covered by `tests/test_cart.py:232` (consumer forced to retail, MOQ not applied) and
`test_cart.py:249` (business buyer receives the tier), plus MOQ boundary tests at
`test_cart.py:90-101` and a merge-conflict path at `test_cart.py:181`.

### 2.5 Seller-side eligibility — **Implemented on interactive routes**

Publishing wholesale requires an **auditable** T2 approval, not a bare `vendors.kyc_tier`:
`services/kyc/eligibility.py` derives `can_wholesale` from an approved `kyc_records` trail and
exposes `orphaned_tier` (`eligibility.py:1-46`). Both the create route
(`vendor_listings.py:191-214` via `_enforce_wholesale_tier`) and the update route
(`vendor_listings_manage.py:349-361`) call `require_wholesale_eligible`. Create additionally
refuses `wholesale=true` without `price_tiers` (`vendor_listings.py:209-214`).
Tests: `test_listing_create.py:326` (T1 denied), `:489` (T2 allowed),
`test_kyc_integrity.py:268` (orphaned tier does not unlock wholesale).

### 2.6 Test coverage inventory — **Implemented**

14 tests in `tests/test_business_access.py` cover eligibility resolution, the 403,
apply/re-apply/verified-cannot-resubmit, admin notification enqueue, and the guest-403 /
verified-200 endpoint pair (`test_business_access.py:119-300`). Discovery-surface hiding has a
paired hides/shows test in each of `test_catalog.py:505-544`, `test_comparison.py:424-458`,
`test_directory.py:611-647`, `test_products.py:508+`, `test_search.py:709-743`, and
`test_ask.py:359`.

---

## 3. What is absent, and correctly so

Per D28's scope fence and §G, all of the following are **Deferred by decision** and were
confirmed absent — no table, router, or flag exists for any of them:

buyer organisations & roles · account managers · contract pricing · credit / Net-30/60 ·
wallet & financing · multi-warehouse · lot/batch & stock allocation · RFQ-broadcast for goods ·
B2B-specific tax invoices.

Two things that _do_ exist are useful seams rather than partial builds, and §5 reuses them:

- **RFQ/quote spine for services**: `jobs` + `job_quotes` with
  `unique (job_id, provider_vendor_id)`, a `submitted|accepted|declined|expired` status enum,
  and `expires_at` (`0004_services_events.sql:33-82`).
- **Anti-spam broadcast precedent**: `services/rfq/broadcast.py` caps fan-out at
  `DEFAULT_BROADCAST_CAP = 8` (config-overridable via `rfq_broadcast_cap`) and raises an admin
  flag on no-match (`broadcast.py:10-15`). This is the pattern §5.3 extends to goods.

---

## 4. Findings

Ranked by money/leak severity. **G1–G4 and G8 are launch-hardening on the D28 slice, not new
scope.** Live-DB confirmation was not possible in this session (the Supabase MCP server is
unauthenticated), so DB-layer findings are derived from migration source and marked accordingly.

### G1 — `vendor_listings` RLS exposes wholesale rows and tier prices to the public — **Partial**

**Evidence.** `vendor_listings_public_active_select` permits `SELECT` on every active listing
whose vendor is active, with no role restriction and no wholesale predicate
(`0003_catalog.sql:273-284`), and `grant select on table public.vendor_listings to anon,
authenticated` (`0003:482`). The grant is column-wide, so `wholesale`, `moq` and `price_tiers`
are all readable. `NEXT_PUBLIC_SUPABASE_ANON_KEY` is a browser-inlined variable
(`.env.example`, `packages/auth/src/env.ts:10-13`), i.e. the PostgREST endpoint and its key are
public by design.

**Failure scenario.** Any guest issues
`GET /rest/v1/vendor_listings?wholesale=eq.true&select=id,title_override,price_ngwee,moq,price_tiers`
against the project URL with the public anon key and receives the entire wholesale catalogue
including every tier price — the exact data D28 requires to stay hidden. No login, no
`business_buyers` row, no API call.

**Severity.** High for D28 conformance; the competitive-intelligence exposure (a vendor's full
wholesale price ladder) is the real damage, not the listing titles.

**Not auditable live** — confirmed in migration source only.

### G2 — `search_documents` projections of wholesale listings are publicly readable — **Partial**

**Evidence.** `search_documents_public_select` permits reads wherever `is_public = true`
(`0009_search.sql:989-993`) and the projection carries **no** wholesale column (no `wholesale`
match anywhere in `0009_search.sql`) — which is precisely why the API needs the post-filter at
`services/search/__init__.py:194-218`.

**Failure scenario.** A guest queries `search_documents` directly and gets titles, prices and
vectors for wholesale listings that the `/search` endpoint would have dropped. The API-layer
`drop_wholesale_listing_hits` cannot help, because it is not in the path.

**Note.** `0068`'s facet RPC _does_ exclude wholesale in SQL (`0068:42-48`), so the two DB-side
paths are inconsistent with each other — one hardened, one not.

**Not auditable live.**

### G3 — Wholesale pricing is never re-derived after the cart write — **Partial**

**Evidence.** `routers/checkout.py` imports nothing from `services.business` (import block,
`checkout.py:1-21`) and builds line views straight from the stored row
(`checkout.py:307-330`, reading `item["unit_price_ngwee"]` and `item["wholesale"]`).
`routers/orders_create.py:224-240` likewise validates only that `qty`/`unit_price_ngwee` are
`int`, then feeds them into `create_orders_atomic` (`orders_create.py:267-276`). Meanwhile
`cart_items` RLS lets an owner `UPDATE` **any column** on lines in their own cart — the
`with check` tests cart ownership only (`0012_carts.sql:251-272`), there is no column guard
trigger, and `grant select, insert, update, delete on public.cart_items to authenticated, anon`
is unconditional (`0012:348`).

**Failure scenarios.**

1. _Revocation ignored._ A verified buyer fills a cart at tier prices; an admin then rejects or
   (once G4 is fixed) suspends them. Checkout and order creation still convert the cart at
   wholesale prices, because neither re-checks eligibility.
2. _Direct price tampering._ A logged-in buyer sets `unit_price_ngwee = 1` on their own
   `cart_items` row via PostgREST, then checks out. The order, the escrow amount, the
   commission and the invoice all inherit the forged price.

**Severity.** Highest in this document. Scenario 2 is a general money-path defect that B2B
merely surfaces; it should be treated as a launch gate on its own merits.

**Partial / Not auditable live** — code path confirmed in repo; the PostgREST reachability leg
is inferred from the RLS grants and the browser-inlined anon key, not exercised.

### G4 — `suspended` is unreachable — **Partial**

**Evidence.** `suspended` is a legal status in the DB check constraint (`0038:23-24`) and in
`VALID_STATUSES` (`access.py:21`), but `routers/admin_business.py` exposes only `/verify`
(`:122`) and `/reject` (`:152`). No route, service function or UI action sets `suspended`.

**Failure scenario.** A verified business buyer is later found to have lapsed PACRA registration
or to be abusing wholesale pricing. Ops has no in-product way to revoke: the only options are
`reject` (semantically wrong — it means "application refused", and it clears `verified_at`,
destroying the record that verification ever happened) or a manual SQL write outside the audit
trail.

### G5 — `PATCH` can turn a listing wholesale with no tiers — **Partial**

**Evidence.** Create enforces `price_tiers` presence for wholesale
(`vendor_listings.py:209-214`). The update path validates tier _ordering_ if tiers are supplied
(`vendor_listings_manage.py:346-347`) and checks vendor eligibility
(`:349-361`), but never asserts that a wholesale listing ends up with tiers.

**Failure scenario.** A vendor creates a retail listing, then `PATCH`es `{"wholesale": true}`
with no `price_tiers`. The listing joins the gated supplies feed with `price_tiers: null`, so
`select_unit_price_ngwee` returns base retail for every quantity (`totals.py:18,29`) — a
"wholesale" listing with no wholesale price, shown to business buyers as a supply offer.

### G6 — CSV import bypasses the seller-side wholesale gate — **Partial**

**Evidence.** `_listing_payload` writes `wholesale` and `price_tiers` directly
(`services/listings/csv_import.py:446-464`) and the write executes at `csv_import.py:554-573`.
Neither `csv_import.py` nor `routers/listing_import.py` references `require_wholesale_eligible`
or `resolve_vendor_eligibility` — the grep returns nothing, whereas the interactive route calls
it at `vendor_listings.py:438`. The importer does enforce tier _shape_ (`csv_import.py:96-119`)
and listing caps (`csv_import.py:540-552`), so the omission is specific to the KYC capability
check.

**Failure scenario.** A T1 vendor who is denied wholesale on the create route
(`test_listing_create.py:326` proves the denial) uploads the same listings by CSV with
`wholesale=true` and succeeds — D9's "supplies tab eligible at T2" is bypassed, and the same
route also skips the create route's tier-required rule from G5.

### G7 — `moq` and `price_tiers` are never cross-validated — **Partial**

**Evidence.** `moq` is validated independently (`>= 1` at `0003:98`, `ge=1` at
`vendor_listings.py:46`) and tiers are validated independently
(`vendor_listings.py:166-189`). No code compares `moq` against `min(min_qty)`.

**Failure scenario.** `moq = 10`, lowest tier `min_qty = 50`. A business buyer orders 10 —
MOQ passes, no tier applies, and `select_unit_price_ngwee` falls through to base retail
(`totals.py:29`). The buyer is charged the consumer price on the wholesale feed. Silent, and
invisible to the vendor.

### G8 — A wholesale-only listing is purchasable by a consumer at retail — **Partial**

**Evidence.** `fetch_listing` filters on `status == 'active'` and nothing else
(`services/cart/store.py:48-77`); `wholesale` is selected but never used as a visibility
predicate. Because `wholesale = listing.wholesale AND business_eligible` (`merge.py:139`), a
consumer gets `wholesale = False`, which _also_ switches off the MOQ check
(`totals.py:34`).

**Failure scenario.** A consumer obtains a wholesale listing ID (trivially, via G1) and
`POST /cart/items` with `qty=1`. The line is accepted at base `price_ngwee` with no MOQ, and
the cart response echoes `title_override` and `vendor_id` (`cart.py:311-322`). D28's "a consumer
always sees retail" is honoured on price but not on _access_: the listing was supposed to be
invisible, and it just became an order.

**Design question for the founder (§7, FD-B01):** is `wholesale=true` intended to mean
"wholesale-only" or "also available retail"? The discovery layer treats it as the former; the
cart treats it as the latter. Both behaviours are defensible; the codebase should pick one.

### G9 — Verification drifts from the verified facts — **Partial**

**Evidence.** `business_buyers_owner_update` lets an owner update their row
(`0038:126-131`) and the guard trigger blocks only `status`, `verified_at` and `user_id`
(`0038:63-67`). `legal_name` and `registration_no` are therefore freely editable **after**
verification. The application-layer re-apply guard (`store.py:51-58`) does not close this: it
governs `POST /business/apply`, not a direct PostgREST `UPDATE`.

**Failure scenario.** A buyer is verified against PACRA number X, then edits the row to legal
name Y / PACRA number Z. `is_verified_business` still returns true; the admin queue shows the
new details as verified; nothing is audited. Any future B2B invoice built from this row
(§5.7) would carry unverified tax identifiers.

### G10 — No audit trail for buyer-side lifecycle events — **Partial**

**Evidence.** Admin decisions are audited via `AdminAuditedRoute` + `recorder.record`
(`admin_business.py:140-146,170-180`). Buyer-side events — application, resubmission, detail
edits — have no audit row; `store.py` writes without recording, and there is no
`business_buyer_events` table in any migration.

**Why it matters.** D28 makes this a KYC-adjacent identity. Vendor KYC has a state machine with
an audit trail (`services/kyc/state_machine.py`); the buyer-side equivalent has a trigger guard
but no history, so "when did this buyer become verified, and on what evidence" is not
answerable from the platform.

### G11 — Minor: no rate limit on the gated wholesale feed — **Partial**

`routers/business.py` rate-limits apply (`:37-50`), but `routers/catalog.py` contains no
`bump_rate_counter` call, so `/catalog/listings?wholesale=true` is unlimited for a verified
buyer. Low severity (the caller is verified and auditable), but it is the one endpoint that
returns a competitor's full price ladder, so a per-user cap is cheap insurance.

### G12 — Informational: `drop_wholesale_listing_hits` costs a query per search

`services/search/__init__.py:194-218` probes `vendor_listings` on every consumer search to
subtract wholesale hits. Correct, but it is a post-filter over an already-paginated hit list,
which means result pages can under-fill. Closing G2 by projecting `wholesale` into
`search_documents` would remove both the extra query and the short-page artefact.

---

## 5. Phased route to full B2B

Design rules applied throughout:

- **No Phase-2 financial risk before launch.** Nothing that creates a receivable, extends
  credit, or requires the platform to front cash appears before Wave B7, and B7 is gated on
  legal + accounting sign-off, not on engineering readiness.
- **Every wave is independently shippable and flag-gated off by default**, following the
  M17/M18 dark-ship precedent recorded in `docs/plan/00-status.md`.
- **Additive migrations only** (CLAUDE.md convention 6), each reversible or documented.
- **Reuse before invent**: the `jobs`/`job_quotes` spine, the capped-broadcast pattern, the
  gapless invoice counter, the ledger zero-sum trigger, and `AdminAuditedRoute` all already
  exist and are cited per wave.

### 5.0 Wave B0 — harden the slice D28 already authorised (**pre-launch**)

Not new scope: this is G1–G10 closed. Risk class: **safe, no founder/legal input needed** except
FD-B01 (the wholesale-only question), which B0-P02 needs before it can choose between a 403 and
a retail sale.

| #      | Work                                                                                                                                                                                                                                          | Closes          |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| B0-P01 | Push the wholesale predicate into RLS: split `vendor_listings_public_active_select` so wholesale rows require `is_verified_business(auth.uid())`; project `wholesale` into `search_documents` and add the same predicate to its public policy | G1, G2, G12     |
| B0-P02 | Re-derive price and eligibility at checkout **and** order creation; add a `cart_items` column guard trigger so `unit_price_ngwee`/`wholesale` are service-role-writable only; decide wholesale-only access at `fetch_listing`                 | G3, G8          |
| B0-P03 | Complete the buyer lifecycle: `POST /admin/business/{id}/suspend`, re-verification on `legal_name`/`registration_no` change, `business_buyer_events` audit table                                                                              | G4, G9, G10     |
| B0-P04 | Authoring consistency: require tiers when `PATCH` sets `wholesale=true`; run CSV import through `require_wholesale_eligible`; cross-validate `moq` against `min(min_qty)`; per-user rate limit on the supplies feed                           | G5, G6, G7, G11 |

### 5.1 Wave B1 — verified business organisations and roles (**post-beta, safe**)

**What.** Promote `business_buyers` from a per-user row to an organisation with members.
New `business_organisations` (the verified legal entity) + `business_members`
(`user_id`, `org_id`, `role`, `status`). Roles kept deliberately small for the first cut:
`owner` (manages members, accepts quotes), `buyer` (adds to cart, requests quotes),
`viewer` (reads pricing only).

**Why it is first.** Every later wave needs a stable answer to "which legal entity is this
request acting for". Building RFQ or contract pricing against a per-user identity guarantees a
migration later.

**Migration safety.** `business_buyers` becomes the seed: one organisation per existing verified
row, its user as `owner`. `is_verified_business(uid)` is rewritten to resolve through membership
so **every existing call site keeps working unchanged** — this is what makes B1 additive rather
than a rewrite.

**Requires:** FD-B01, FD-B07. **Risk:** none financial. **Deferred within B1:** invitations by
phone/WhatsApp, per-member spend limits (spend limits are a credit-adjacent control — B7).

### 5.2 Wave B2 — wholesale RFQ without broadcast spam (**post-beta, safe**)

**What.** `supply_requests` (buyer org, category, spec, target qty, needed-by, optional budget
band) with a `draft|open|quoted|awarded|cancelled|expired` lifecycle.

**Anti-spam is the design centre**, and the platform already has the precedent:

- **Capped, ranked fan-out, not broadcast.** Extend `services/rfq/broadcast.py`'s
  `DEFAULT_BROADCAST_CAP = 8` model (`broadcast.py:10-15`) to goods: match on category + T2
  eligibility + wholesale listing presence, rank, notify at most N.
- **Rate limits on both sides.** Per-org request creation caps (reuse
  `bump_rate_counter` as at `business.py:38-44`); per-vendor daily invitation caps so one
  vendor cannot be flooded.
- **No open marketplace of requests.** A supply request is visible only to invited vendors and
  the buyer — never a public feed. This is what separates it from the "RFQ-broadcast for goods"
  that §G excludes.
- **No-match escalation, not wider blast.** Reuse the `RFQ_NO_MATCH_FLAG_REASON` admin-flag
  pattern (`broadcast.py:14`) rather than expanding the recipient set.

**Requires:** B1. **Risk:** reputational (vendor spam) — mitigated above. Not financial.

### 5.3 Wave B3 — quote comparison and acceptance (**post-beta, safe**)

**What.** `supply_quotes` modelled directly on `job_quotes`
(`0004_services_events.sql:62-82`): one quote per vendor per request
(`unique (request_id, vendor_id)`), integer-ngwee line items, validity window (`expires_at`),
`submitted|accepted|declined|expired|withdrawn`.

**Comparison view.** A buyer-side table across quotes — landed unit price, MOQ, lead time,
vendor rating — which is the B2B expression of the D24 comparison moat.

**Acceptance is a guarded transition, not an UPDATE.** Accepting exactly one quote must
atomically: mark it `accepted`, mark siblings `declined`, move the request to `awarded`, and
materialise an order priced **from the quote snapshot** — no client-supplied price, mirroring
the events-pricing rule in D29 ("prices always resolved server-side within locked bounds").
An expired quote is not acceptable, and acceptance must be idempotent under retry.

**Payment stays exactly as it is today**: escrow prepay or COD ≤K500 (D12). No terms, no
invoice-then-pay. That is what keeps B3 free of financial risk.

**Requires:** B2. **Risk:** none financial.

### 5.4 Wave B4 — contract pricing (**post-beta; needs a founder decision, no legal**)

**What.** `supply_contracts` (vendor, buyer org, validity window, status) +
`supply_contract_prices` (listing or product, tier ladder, MOQ override). Resolution order at
pricing time becomes: **contract price → wholesale tier → retail**, computed in one place.

**Non-negotiable constraint.** `select_unit_price_ngwee` (`totals.py:10-29`) must remain the
single pricing function; contract resolution extends it rather than adding a parallel path. A
second pricing function is how B2B platforms get price drift between cart, checkout and invoice
— and G3 shows this codebase is already sensitive to exactly that.

**Open design tension (FD-B04).** Contract prices are confidential per buyer. The comparison
view (D24) is a public differentiator. The audit's recommendation: contract prices are **never**
projected into `search_documents` and never appear in comparison — they resolve at cart time
only, and the PDP shows "your contract price" solely to authenticated members of the
contracted org.

**Requires:** B1, B0-P01 (RLS must already be entity-aware). **Risk:** none financial.

### 5.5 Wave B5 — warehouses, lots/batches and stock allocation (**post-beta, safe; largest wave**)

**What.** `warehouses` (vendor, location, active) → `inventory_lots` (warehouse, listing,
qty, cost, batch ref, expiry) → allocation at order time, with a retail/wholesale pool split as
the strategy distillation describes (`docs/plan/research/strategy-bible-and-blueprint-distilled.md:30,68`).

**Sequencing note.** This is the wave most likely to be over-built. Recommended thin first cut:
multi-warehouse **stock location only** (which depot holds it, for pickup routing), deferring
FIFO/expiry, goods-received scanning and reorder alerts to B5b. Lot/batch tracking earns its
keep only for categories with expiry — and D8 currently excludes fresh produce and pharma, so
the launch catalogue has almost no genuine batch requirement.

**Interaction risk.** Stock reservation already exists (`stock_reservations`, referenced at
`checkout.py:355-363`). Allocation must extend that mechanism, not shadow it, or oversell
becomes possible under concurrency.

**Requires:** B0-P02 (order path must be authoritative first). **Risk:** operational, not
financial.

### 5.6 Wave B6 — tax-ready B2B invoices (**needs accounting sign-off**)

**What.** Extend the invoice snapshot with buyer identity. Today
`InvoicePayload.to_snapshot()` carries `seller_tpin`, `vat_flag`, per-line `vat_rate_bps` and
totals — but **no buyer fields at all**
(`services/invoicing/builder.py:39-77`). A B2B tax invoice needs the purchaser's legal name,
TPIN and address.

**What already works and must not be disturbed.** Gapless numbering is genuinely atomic —
`next_invoice_no` and the `INSERT` share one transaction so a failed insert releases the number
(`services/invoicing/allocation.py:48-56,79-95`). Adding buyer fields is a snapshot-shape change
only; the allocation transaction must not be touched.

**VAT.** `VAT_ENABLED_AT_LAUNCH = False` and `VAT_RATE_BPS_AT_LAUNCH = 0`
(`builder.py:14-15`) per D13. B6 must keep VAT off and must not activate the VSDC seam
(`services/invoicing/vsdc.py`) — that is a separate decision at the K800k threshold.

**Gate:** an accountant confirms what a ZRA-valid B2B invoice must contain under Turnover Tax,
and whether buyer TPIN is mandatory or optional (FD-B02). Until answered, B6 ships the _fields_
and leaves presentation behind a flag.

**Requires:** B1 (buyer legal identity must be an organisation), B0-P03 (identity must not drift
— G9 is a correctness precondition for any tax document).

### 5.7 Wave B7 — credit / Net terms and account managers (**BLOCKED on legal + founder; earliest Year 2**)

**This is the Phase-2 financial risk fence and it does not move.** D2, §G and the strategy
phasing (`strategy-bible-and-blueprint-distilled.md:104` — "Ph3: Net-30/60 credit, account
managers, contract pricing") all place it late, and nothing in this audit argues for pulling it
forward.

**Why it is categorically different from B1–B6.** Everything above rearranges who sees what and
how a price is computed. Net terms means the platform (or the vendor) ships goods against a
promise to pay. That creates a receivable, a default risk, a collections process, and —
depending on structure — a regulated lending activity. D14 already establishes that the platform
**never pools funds in its own bank account** and that counsel review under the NPS Act 2026 is
a pre-real-money gate (F4). Net terms is a materially larger question than the escrow flow F4
covers.

**Hard preconditions, all of which must be true before any B7 pebble is written:**

1. **Zambian counsel** confirms whether platform-fronted Net-30/60 constitutes lending or a
   payment service requiring BoZ authorisation (FD-B03) — an extension of F4, not covered by it.
2. **Founder decides who carries default risk** — platform, vendor, or a third-party financier
   (FD-B05). This determines the entire ledger design and is unanswerable by engineering.
3. **Accounting treatment** of receivables, bad debt and revenue recognition is agreed
   (FD-B02's larger sibling).
4. **Volume gate** reached — the strategy sets 300–500 orders/month for B2B mode
   (`strategy-bible-and-blueprint-distilled.md:103,112`); credit should sit later still.

**Account managers** are the low-risk half of this wave and could be split out: assigning a
human to an org, with a WhatsApp contact path, needs no credit model. Recommend splitting
**B7a (account managers, safe post-beta)** from **B7b (credit/Net terms, blocked)** so the safe
half is not held hostage.

**Also out, unchanged:** wallet / Vergeo Pay / financing, working-capital advances, ERP-grade
API, cross-border (§G).

---

## 6. Cross-cutting requirements for every wave

These are acceptance criteria, not suggestions. They restate CLAUDE.md conventions 1, 3, 4, 5
and 9 in B2B terms.

### 6.1 RLS

- **Every new table carries an RLS-matrix row** in `services/api/tests/rls/test_matrix.py`
  covering all seven personas — the `business_buyers` entry at `test_matrix.py:224-246` is the
  template.
- `enable` **and** `force row level security` on every new table, per D32's precedent
  (`0064_force_rls_launch_tables.sql`).
- **Organisation isolation is the new axis.** Existing personas test customer-vs-customer and
  vendor-vs-vendor; B1 onward needs `OTHER_ORG` — org A must not read org B's quotes, contract
  prices, or member list. A contract price leaking across orgs is a commercial incident.
- **No `anon` grant** on any B2B table (follow `0038:149`).
- Wholesale/contract visibility predicates belong **in the policy**, not only in the router
  (this is G1/G2's whole lesson).

### 6.2 Pricing integrity

- **One pricing function.** All resolution — contract → tier → retail — flows through
  `select_unit_price_ngwee` (`totals.py:10-29`). No parallel implementation, ever.
- **Never trust a stored or client-supplied price.** Re-derive at cart, checkout **and** order
  creation (the fix for G3). The rule already exists elsewhere in the codebase — D29 states it
  for ticket pricing — and must be uniform.
- **Integer ngwee end to end**; `Decimal` only at the Lenco boundary. A float on a tier price is
  a review-blocking bug (CLAUDE.md convention 1).
- **Snapshot at commitment.** An accepted quote and an issued invoice freeze their prices; a
  later contract change must not retroactively alter them.
- **Eligibility is re-checked at every money step**, so revocation takes effect immediately
  rather than at next cart write.

### 6.3 Approvals and state machines

- Org verification, supply-request lifecycle, quote acceptance and contract activation each get
  a **guarded transition function with an audit row** — never a raw status `UPDATE`
  (CLAUDE.md convention 4). `services/kyc/state_machine.py` is the in-repo model.
- **Illegal transitions must be tested explicitly**, not just legal ones: accepting an expired
  quote, accepting two quotes on one request, activating a contract for a suspended org,
  verifying an org twice.
- **Idempotency** on every acceptance/award path — a retried accept must not create a second
  order (CLAUDE.md convention 5).

### 6.4 Audit

- Every admin decision rides `AdminAuditedRoute` + `AdminAuditRecorder`
  (`admin_business.py:21-26,140-146`).
- Buyer-side and vendor-side lifecycle events get their own append-only event rows (G10) —
  who, what, when, and the prior state.
- **Verification evidence is immutable.** Once verified, changing a legal identifier forces
  re-verification and writes an audit row (G9).
- Contract price changes are versioned, not overwritten — a dispute six months later must be
  answerable.

### 6.5 Rate limits

- Org creation, member invitation, supply-request creation, and quote submission all rate-limited
  per user **and** per org via `bump_rate_counter` (`business.py:38-44`).
- Per-vendor **inbound** caps on RFQ invitations — the anti-spam guarantee in §5.2 is a rate
  limit, not a policy statement.
- Per-user cap on the wholesale feed and any future price-export endpoint (G11).

### 6.6 Failure-path tests (required per pebble, per CLAUDE.md convention 9)

Money, authz and state-machine logic each need failure-path coverage. Minimum set:

**Authz / isolation**

- Guest, consumer, `pending`, `rejected`, `suspended` buyer → 403 on every wholesale surface.
- Org A member cannot read org B's quotes, contracts, members, or invoices (direct-ID attempt,
  not just list filtering).
- A `viewer` cannot accept a quote; a `buyer` cannot manage members.
- Vendor A cannot read vendor B's quote on the same request.

**Pricing**

- Tampered `cart_items.unit_price_ngwee` is rejected or overwritten at checkout (G3).
- Eligibility revoked between cart and checkout → line re-prices to retail (G3).
- `moq` above the lowest tier does not silently fall through to retail (G7).
- Wholesale listing with null tiers cannot reach the supplies feed (G5).
- Contract price expiry mid-checkout falls back to tier price deterministically.

**State machine**

- Two concurrent accepts on one request → exactly one order.
- Accepting an expired quote → rejected.
- Retried accept with the same idempotency key → no duplicate order.

**Discovery**

- Direct PostgREST read of `vendor_listings` / `search_documents` as `anon` returns zero
  wholesale rows (the G1/G2 regression test — this belongs in `supabase/tests/`, exercised
  against real RLS, not in the Python fakes).

**Rate limits**

- Request-creation and invitation caps return 429 with `retry_after`.

---

## 7. Unresolved founder decisions

Blocking-ness is stated per item; nothing here blocks Wave B0 except FD-B01.

| ID         | Question                                                                                                                                                                                             | Needed by     | Blocking?                                       |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------- |
| **FD-B01** | Does `wholesale=true` mean **wholesale-only** (consumers get 403) or **also-retail** (consumers buy at `price_ngwee`)? Discovery assumes the former, cart assumes the latter (G8).                   | B0-P02        | **Yes** — B0-P02 cannot be specified without it |
| **FD-B02** | What must a ZRA-valid B2B invoice contain under Turnover Tax? Is buyer TPIN mandatory? **Needs an accountant.**                                                                                      | B6            | Yes, for B6                                     |
| **FD-B03** | Does platform-fronted Net-30/60 constitute lending or a payment service under Zambian law (BoZ / NPS Act 2026)? **Needs counsel** — an extension of F4, not covered by it.                           | B7b           | Yes, for B7b                                    |
| **FD-B04** | Are contract prices confidential per buyer (audit recommends: yes, never in search or comparison)?                                                                                                   | B4            | Yes, for B4                                     |
| **FD-B05** | Who carries default risk on Net terms — platform, vendor, or third-party financier? Determines the entire ledger design.                                                                             | B7b           | Yes, for B7b                                    |
| **FD-B06** | Confirm the B2B-mode volume gate. Strategy says 300–500 orders/month (`strategy-bible-and-blueprint-distilled.md:103,112`); D3 uses ~300 orders/mo for paid vendor tiers. Same trigger or different? | B1 sequencing | No                                              |
| **FD-B07** | How is PACRA verified — manual document review (today's implicit process) or a registry lookup? Affects whether re-verification (G9) is cheap or expensive.                                          | B0-P03, B1    | No — B0-P03 can ship manual-review              |
| **FD-B08** | Re-verification cadence for verified business buyers (annual, on PACRA lapse, never)? PACRA annual returns lapse is a live founder issue (F2).                                                       | B0-P03        | No                                              |
| **FD-B09** | Should account managers (B7a) split from credit (B7b) so the safe half ships post-beta? Audit recommends yes.                                                                                        | B7 sequencing | No                                              |

**Not auditable in this session:** live RLS behaviour (Supabase MCP unauthenticated), so G1/G2/G3
carry a repo-derived confidence level; anything requiring legal or accounting input (FD-B02,
FD-B03, FD-B05).

---

## 8. Candidate ADRs

Proposed, **not decided**. `00-decisions.md` is unmodified.

**ADR-R02-B1 (candidate) — Wholesale visibility is enforced in RLS, not only in the API.**
D28's "hidden from consumers" becomes a database-level guarantee: `vendor_listings` and
`search_documents` policies test `is_verified_business(auth.uid())` for wholesale rows. The API
filters remain as defence in depth. Rationale: G1/G2 show the current guarantee does not survive
direct PostgREST access with the public anon key.

**ADR-R02-B2 (candidate) — Price is re-derived at every money step.**
Cart, checkout and order creation each re-resolve unit price and wholesale eligibility from the
listing and the live `business_buyers` state; stored line prices are treated as a cache, never as
truth. `cart_items.unit_price_ngwee`/`wholesale` become service-role-writable only. Rationale: G3.

**ADR-R02-B3 (candidate) — The verified business identity is an organisation, seeded from
`business_buyers`.** `is_verified_business(uid)` is rewritten to resolve through membership so
every existing call site is unchanged. Rationale: B1 is a precondition for B2–B6, and doing it
later means migrating quotes, contracts and invoices.

**ADR-R02-B4 (candidate) — Goods RFQ is invitation-based and capped; there is no public request
feed.** Extends the existing `rfq_broadcast_cap` pattern to supplies. Rationale: §G excludes
"RFQ-broadcast for goods"; an invitation-based, capped, rate-limited request is a different
mechanism and is the only form that respects the spam constraint.

**ADR-R02-B5 (candidate) — Credit/Net terms (B7b) is fenced behind counsel + accounting +
founder risk-allocation answers, and account managers (B7a) split out as separately shippable.**
Rationale: §5.7; the safe half should not wait on the regulated half.

---

## 9. Proposed pebble sequence

One pebble = one branch = one PR titled `M{nn}-P{nn}: {title}` (CLAUDE.md convention 10).
Mountain number to be assigned by the founder when these are promoted into `02-pebbles/`;
`B0-*` are written as fixes against existing mountains, `B1+` as a new B2B mountain.

**Exclusive file ownership is per wave**: pebbles within a wave own disjoint file sets and may
run in parallel. Migration numbers must be **reserved up front** at dispatch (next free is
`0080`, current tip is `0079_clip_cost_guard.sql`) so parallel pebbles do not collide on
filenames.

### Wave B0 — pre-launch hardening (parallel; no cross-dependencies)

| Pebble                                     | Owns (exclusive)                                                                                                                                                                                                      | Depends on |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **B0-P01** RLS-level wholesale hiding      | `supabase/migrations/0080_wholesale_rls.sql`, `supabase/tests/0080_wholesale_rls.test.sql`, `services/api/tests/rls/test_matrix.py` (wholesale rows)                                                                  | —          |
| **B0-P02** Money-path price re-derivation  | `services/api/app/routers/checkout.py`, `routers/orders_create.py`, `services/cart/store.py`, `supabase/migrations/0081_cart_line_price_guard.sql`, `services/api/tests/test_checkout.py`, `test_order_money_gate.py` | FD-B01     |
| **B0-P03** Buyer lifecycle completion      | `services/api/app/routers/admin_business.py`, `services/business/store.py`, `supabase/migrations/0082_business_buyer_events.sql`, `apps/admin/app/[locale]/business/**`, `services/api/tests/test_business_access.py` | —          |
| **B0-P04** Wholesale authoring consistency | `services/api/app/routers/vendor_listings_manage.py`, `services/listings/csv_import.py`, `routers/listing_import.py`, `routers/catalog.py` (rate limit), `tests/test_listing_manage.py`, `test_csv_import.py`         | —          |

_Contention note:_ B0-P01 and B0-P02 both touch RLS-adjacent surface but own different migration
files and different test files — safe in one wave. B0-P02 and B0-P04 both touch pricing but on
disjoint sides (consumption vs. authoring).

### Wave B1 — organisations (single pebble; blocks everything after)

| Pebble                                                         | Owns                                                                                                                                                                                                                                                              | Depends on                                  |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **B1-P01** Business organisations + members + resolver rewrite | `supabase/migrations/0083_business_organisations.sql`, `services/api/app/services/business/**`, `routers/business.py`, `routers/admin_business.py`, `apps/customer/app/[locale]/account/business/**`, `tests/test_business_access.py`, `tests/rls/test_matrix.py` | B0-P03 (audit table + lifecycle land first) |

### Wave B2–B3 — RFQ and quotes (sequential; B3 needs B2's tables)

| Pebble                                                 | Owns                                                                                           | Depends on     |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | -------------- |
| **B2-P01** `supply_requests` schema + RLS + lifecycle  | `supabase/migrations/0084_supply_requests.sql`, `services/api/app/services/supply/requests.py` | B1-P01         |
| **B2-P02** Capped invitation matching + notifications  | `services/api/app/services/supply/matching.py`, `routers/supply_requests.py`                   | B2-P01         |
| **B2-P03** Buyer request UI                            | `apps/customer/app/[locale]/(shop)/supplies/requests/**`                                       | B2-P02         |
| **B3-P01** `supply_quotes` schema + guarded acceptance | `supabase/migrations/0085_supply_quotes.sql`, `services/api/app/services/supply/quotes.py`     | B2-P01         |
| **B3-P02** Quote comparison + acceptance→order         | `routers/supply_quotes.py`, `apps/customer/.../supplies/requests/[id]/**`                      | B3-P01, B0-P02 |
| **B3-P03** Vendor quote inbox                          | `apps/vendor/app/[locale]/supply-requests/**`                                                  | B3-P01         |

### Wave B4–B6 — pricing, inventory, invoices

| Pebble                                                                       | Owns                                                                                                                        | Depends on             |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| **B4-P01** Contract schema + resolution in `select_unit_price_ngwee`         | `supabase/migrations/0086_supply_contracts.sql`, `services/api/app/services/cart/totals.py`, `services/supply/contracts.py` | B1-P01, B0-P02, FD-B04 |
| **B4-P02** Contract admin + vendor UI                                        | `apps/vendor/app/[locale]/contracts/**`, `apps/admin/app/[locale]/contracts/**`                                             | B4-P01                 |
| **B5-P01** Warehouses (location only)                                        | `supabase/migrations/0087_warehouses.sql`, `services/api/app/services/inventory/**`                                         | B0-P02                 |
| **B5-P02** Allocation into the existing reservation path                     | `services/api/app/services/stock/claim.py`, `services/inventory/allocation.py`                                              | B5-P01                 |
| **B5b-P01** Lots/batches + FIFO + expiry _(defer until a category needs it)_ | `supabase/migrations/0088_inventory_lots.sql`                                                                               | B5-P02                 |
| **B6-P01** Buyer identity in the invoice snapshot                            | `services/api/app/services/invoicing/builder.py`, `invoicing/pdf.py`, `tests/test_invoicing.py`                             | B1-P01, B0-P03, FD-B02 |

### Wave B7 — split

| Pebble                                                            | Owns                                                                                            | Depends on                                       |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| **B7a-P01** Account managers (assignment + WhatsApp contact path) | `supabase/migrations/0089_account_managers.sql`, `apps/admin/app/[locale]/business/managers/**` | B1-P01                                           |
| **B7b-\*** Credit / Net terms                                     | _not specified_                                                                                 | **Blocked**: FD-B03, FD-B05, FD-B02, volume gate |

**B7b is deliberately left unspecified.** Writing pebbles for it now would invite implementation
before the legal and risk-allocation answers exist, which is exactly the Phase-2 financial risk
this audit is asked to keep out of launch.

### Dependency summary

```
B0-P01 ─┐
B0-P02 ─┼─ (pre-launch, parallel)
B0-P03 ─┼──────────► B1-P01 ──┬──► B2-P01 ──► B2-P02 ──► B2-P03
B0-P04 ─┘                     │        └──► B3-P01 ──┬──► B3-P02
                              │                      └──► B3-P03
                              ├──► B4-P01 ──► B4-P02
                              ├──► B6-P01
                              └──► B7a-P01
        B0-P02 ──────────────────► B5-P01 ──► B5-P02 ──► B5b-P01

        B7b  ◄── BLOCKED: FD-B03 (counsel) + FD-B05 (risk) + FD-B02 (accounting) + volume gate
```

---

## 10. What this audit did not touch

No application code, migration, workflow, configuration, flag, secret or infrastructure setting
was modified. Nothing was deployed, seeded, or connected. `docs/plan/00-status.md` and
`docs/plan/00-decisions.md` are unchanged. No GitHub state was altered and no PR was opened.
