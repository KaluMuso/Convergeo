> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P04 — Listing discoverability self-check and publish gate

## 1. Context

**Wave R2-B.** Source: `docs/plan/r02/01-strategy-convergence.md` §1.4, §3.4, §5. **Depends on R02-P01.**

**Demo exclusion is correct, deliberate, and completely silent.** Verified read-only on production
`dpadrlxukcjbewpqympu`, **2026-08-01**: 134 active listings, **all 134 demo-tagged**, therefore
**0 publicly discoverable**. The vendor-facing surface says nothing about this; nor does the customer
one, because `shouldShowSampleListingBadge`
(`apps/customer/app/[locale]/(shop)/_components/demo-listing.ts`) **hides the SAMPLE badge in
production by default**. A listing can be `status='active'`, look healthy in the vendor console, and be
invisible to every shopper — with no signal anywhere.

The exclusion rule is implemented **three times**, and the three must agree:

| Copy     | Location                                                                                                  |
| -------- | --------------------------------------------------------------------------------------------------------- |
| API      | `app/services/listings/demo.py` — `is_demo_public_id`, `fetch_demo_listing_ids`, `drop_demo_listing_hits` |
| Customer | `apps/customer/app/[locale]/(shop)/_components/demo-listing.ts` — `isDemoListingPublicId`                 |
| SQL      | `supabase/migrations/0068_search_query_facets_wholesale_and_kinds.sql:59-62`                              |

There is a second, unrelated reason a listing can be invisible: **wholesale**. Per D28, wholesale-only
listings are hidden from every consumer discovery surface unless the viewer is a verified business.
That is also correct and also unsignalled.

Publication happens on two paths, not one:

- creation — `routers/vendor_listings.py:510` via `_resolve_listing_status(mode, publish)` (`:304`),
  and the shared seam `create_listing_for_vendor` (`:391`) that M18-P05 also calls;
- status change — `routers/vendor_listings_manage.py`, `ListingUpdateRequest.status` (`:59`).

**Type:** `[CODE]` — API + vendor app. **No migration.**

## 2. Objective & scope

Give a vendor a truthful answer to "is my listing actually visible to shoppers, and if not, why?", and
stop the one publication that is guaranteed to disappoint — an active listing whose vendor has no
location, which cannot be found by distance and carries no geo into `search_documents`.

**In scope:** one shared discoverability predicate with reasons; a plain-language badge on the vendor
listing surface; a publish gate requiring a vendor location.

**Non-goals — do NOT do these:**

- **Do not change the demo rule, the wholesale rule, or any exclusion behaviour.** You are _reporting_
  the existing rules, not amending them. If you find the three copies disagree, **report it, do not
  unify it** — that is its own pebble with its own review.
- **Do not un-hide the SAMPLE badge in production** or touch `shouldShowSampleListingBadge`.
- **Do not touch `routers/vendor_profile.py`, the vendor home, or `scripts/seed_staging.py`** — R02-P01
  owns those.
- **Do not touch `scripts/ops/verify_live.sh`** — R02-P02 owns it. The DATA gate reports the same
  numbers from the operator side; both read the same rules, neither calls the other.
- Do not add an admin surface — R02-P05 owns the admin tile.
- Do not add a migration, a column, or a dependency. Discoverability is **derived**, never stored: a
  stored flag would go stale the moment an image or a vendor location changed.

## 3. Files (create/modify ONLY these)

- `services/api/app/services/listings/demo.py` — add the shared predicate alongside the existing
  helpers. Keep the current functions' signatures and behaviour untouched.
- `services/api/app/routers/vendor_listings.py` — creation-path gate only.
- `services/api/app/routers/vendor_listings_manage.py` — status-transition gate + expose the reasons on
  the listing summary/detail.
- `services/api/tests/test_listing_discoverability.py` **(new)**
- `apps/vendor/app/[locale]/listings/_components/**` — the badge component + its test.
- `apps/vendor/app/[locale]/listings/[id]/**` — surface the badge on listing detail.
- `packages/i18n/messages/en/vendor.json` — new keys under a single new `listings.discoverability.*`
  subtree. **English only.**

**Ownership note:** R02-P01 also edits `packages/i18n/messages/en/vendor.json`, under
`home.setupTasks.*`. P01 is in the **preceding wave** and this pebble depends on it, so the edits are
sequential, not concurrent. Rebase on P01 before starting and keep your keys strictly inside your own
subtree.

**Guardrail: modify ONLY the files above.** Do not touch any `packages/i18n/messages/{bem,nya,fr,zh}/**`
file (R02-P06/P07 own those), `supabase/migrations/**`, or the customer app.

## 4. Implementation spec

1. **One predicate, many reasons.** Add a function that takes a listing (with its images, vendor and
   status already loaded — no N+1; follow `fetch_demo_listing_ids`'s batch idiom) and returns a
   structured verdict: discoverable yes/no, plus **every** applicable reason, not just the first.
   A listing can be draft **and** demo-tagged **and** vendor-location-less at once; a vendor who fixes
   one and is then told about the next has been failed three times.

   Reasons to distinguish, at minimum: `status_not_active`, `demo_media`, `wholesale_gated`,
   `vendor_no_location`, `vendor_not_active`.
   - `wholesale_gated` is **not a defect** — it is D28 working as designed. The copy must say so:
     visible to verified business buyers, not broken. Do not phrase it as an error.
   - Derive `demo_media` by calling the existing `is_demo_public_id` / `fetch_demo_listing_ids`. Do not
     re-implement the prefix test.

2. **Badge.** On the vendor listing list and detail, render the verdict in plain language. "Not
   discoverable" plus the reasons plus what to do about each. This is the one place a vendor learns
   the truth, so make it unmissable rather than a subtle grey chip — and make it _calm_: most causes
   are one action away from fixed.

3. **Publish gate.** Block a transition to `status='active'` when the vendor has no
   `vendor_locations` row with coordinates, on **both** publication paths (creation and status
   change). Return the uniform error envelope with a `message_key` the vendor app renders, pointing at
   `/[locale]/profile`.
   - **Do not gate on demo media.** A demo-tagged listing is a seeding artifact, not a vendor mistake,
     and blocking it would break the existing demo catalogue for no benefit.
   - Existing active listings are **not** retroactively unpublished. This gate applies at transition
     time only. Say so in the report.
   - `create_listing_for_vendor` (`vendor_listings.py:391`) is the shared seam M18-P05 calls for
     intake-born listings. Your gate must apply there too — an intake listing with no vendor location
     is exactly as invisible — and M18's tests must still pass. Run them.

4. **Reason coverage test.** Table-driven: for each reason, a listing that triggers exactly it, plus
   one listing triggering three at once and asserting all three come back. Plus the negative: a fully
   discoverable listing returns no reasons.

## 9. Security

- No authz change. Both routers keep their existing owner checks (`_load_vendor_for_owner`,
  `_assert_listing_owned_by_vendor`) and rate-limit policies. Add no route, so
  `core/ratelimit_policies.py` needs no row and the M15-P04 startup assert stays satisfied.
- **A vendor may only ever see the verdict for their own listing.** The reasons expose internal
  merchandising rules; leaking them cross-vendor tells a competitor why a rival is hidden. Test the 403.
- Do not leak the wholesale-eligibility state of any _buyer_ — `wholesale_gated` describes the
  listing, never who can see it.

## 10. Tests (RUN before reporting)

- `uv run pytest services/api/tests/test_listing_discoverability.py`
- `uv run pytest services/api/tests/test_vendor_listings.py services/api/tests/test_vendor_listings_manage.py`
  (or the existing equivalents) — publication behaviour unchanged except the new gate.
- `uv run pytest services/api/tests/e2e/test_intake_pilot.py` — the M18 chain still passes through
  `create_listing_for_vendor`.
- `uv run pytest services/api/tests/test_business_access.py` — wholesale gating untouched.
- `uv run ruff check .` · `uv run mypy app tests scripts`
- `pnpm test --filter vendor` · `pnpm lint` · `pnpm typecheck`
- Confirm `git diff --exit-code -- apps/customer/` and `-- supabase/migrations/` are clean.

## 11. Acceptance criteria / DoD

- [ ] One shared predicate returning **all** applicable reasons, not the first; proven by a
      three-reasons-at-once test.
- [ ] Demo detection delegates to the existing `demo.py` helpers — the prefix rule is not
      re-implemented anywhere in this diff.
- [ ] `wholesale_gated` is worded as designed-behaviour, not as an error.
- [ ] Publish gate blocks `→ active` without a vendor location on **both** paths, including
      `create_listing_for_vendor`; M18's intake tests still pass.
- [ ] Existing active listings are not retroactively unpublished.
- [ ] Cross-vendor read of another vendor's verdict returns 403, tested.
- [ ] Zero hardcoded user-facing strings; all keys under `listings.discoverability.*` in EN only.
- [ ] No migration, no stored discoverability column, no new dependency, no customer-app change.
- [ ] If the three copies of the demo rule are found to disagree, it is **reported, not fixed**.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** R02-P04 — Listing discoverability self-check and publish gate
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste the pytest/vitest summary lines, including the M18 intake suite
**EXCERPTS:** the predicate's reason enum and the three-reasons-at-once test
**DEMO RULE:** state whether the three copies (API / customer / SQL) agree; if not, describe the
disagreement precisely and **do not fix it here**
**RETROACTIVE:** confirm no existing active listing was unpublished by this change
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
