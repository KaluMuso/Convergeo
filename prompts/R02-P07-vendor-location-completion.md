> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P07 — Vendor location completion: structured address, phones, branches `[CODE]`

## 1. Context
**Wave W3 (real data).**

**Read this before designing anything: `vendor_locations` already exists** (migration `0002_identity_vendors.sql`) with `vendor_id`, `lat`, `lng`, `landmark`, `hours jsonb`, timestamps — and it is already joined by **seven routers**: `catalog.py`, `directory.py`, `products.py`, `vendor_profile.py`, `comparison.py`, `checkout.py`, `events_public.py`. Geo distance already works (`haversine_m` in `directory.py`, distance SQL in `catalog.py`).

So this pebble **extends** that table; it does not introduce a location model. Rebuilding one would orphan seven working call sites.

What is genuinely missing: structured street/area fields, **phones**, a per-branch label, and the notion that a vendor has *several* locations that a customer chooses between.

Zambia guardrail: **landmark + GPS is the primary addressing mode**, not street number. `landmark` stays **required**; structured fields are additive and optional.

**Type:** `[CODE]`.

## 2. Objective & scope
Make a vendor location a complete, contactable, nameable branch.
**Non-goals:** per-branch stock (that is **R02-P08**); routing/maps UI (**R02-P11**); open-now evaluation (**R02-P10**).

## 3. Files (edit ONLY these)
- `supabase/migrations/NNNN_vendor_location_details.sql` — **verify next-free at branch time** (expected `0081`)
- `services/api/app/routers/vendor_locations.py` (new — router auto-discovery; **do not edit `main.py`**)
- `services/api/app/services/vendors/locations.py` (new)
- `packages/types/src/db.ts` — regenerate, do not hand-write
- `apps/vendor/app/[locale]/settings/locations/**` (new)
- `packages/i18n/messages/en/vendor.json` — **this namespace only**
- Tests under `services/api/tests/`

## 4. Implementation spec
Additive columns on `vendor_locations`:
- `label text` — "Main branch", "Kabwata stall"; unique per vendor
- `area text`, `street text`, `city text`, `province text` — all nullable
- `phone_e164 text` — validated `+260…`; **this is a branch contact, not `vendors.whatsapp_msisdn`**, which is the storefront WhatsApp number from `0046` and must not be overloaded (the same reasoning D35 applied to intake identity)
- `is_primary boolean not null default false` — **partial unique index**: at most one primary per vendor
- `status text` — `active|closed`, so a closed branch stops appearing without deleting history

RLS mirrors `vendors`: public read for active locations of active vendors; vendor writes own; admin all. FORCE RLS. Column-level grants — a client must not be able to write `status` or `is_primary` directly if the repo's convention for that field family is a guarded transition.

Extend the seven existing read paths to return `label` and `phone_e164` **without changing their shapes destructively** — additive fields only, so no consumer of those endpoints breaks.

## 5. Security / conventions
RLS + FORCE RLS; additive migration; reversible or documented why not. Phone is PII — never log it in full (mirror the intake lane's masking rule). Zero hardcoded strings; ICU keys in `vendor.json`.

## 10. Tests (RUN before reporting)
- Migration replay green (`scripts/ci/migration-replay.sh`).
- RLS matrix row for the new columns; `test_no_untested_tables.py` green.
- `test_only_one_primary_location_per_vendor` — the partial unique index refuses the second.
- `test_closed_branch_disappears_from_public_reads` across all seven routers.
- `test_phone_is_validated_e164` and `test_phone_is_not_logged_in_full`.
- Existing tests for the seven routers still green — **regression is the main risk here**.

## 11. Acceptance criteria / DoD
- [ ] `vendor_locations` extended, not replaced; all seven call sites still green.
- [ ] At most one primary branch per vendor, enforced by index.
- [ ] Branch phone is separate from the storefront WhatsApp number.
- [ ] `landmark` still required; structured fields optional.
- [ ] Vendor UI can add/edit/close a branch; strings are i18n keys.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P07 — Vendor location completion
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** … · **EXCERPTS:** migration + the primary-branch index · **QUESTIONS:** …
