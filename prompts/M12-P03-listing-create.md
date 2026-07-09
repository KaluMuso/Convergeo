> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN — no migration** (tables exist). Stay dep-free.

# M12-P03 — Listing creation (attach / new-canonical / quick-list)

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- **`public.vendor_listings`** (`0003`, exact columns): `vendor_id, product_id (null-allowed), title_override, price_ngwee bigint CHECK > 0, condition ('new'|'refurbished'), stock_mode ('tracked'|'always_available'), stock_qty, wholesale bool, price_tiers jsonb CHECK is_valid_price_tiers, moq int ≥ 1, returnable, return_window_hours, status ('draft'|'active'|'paused'|'removed')`. **`public.products`** (canonical) + `search_documents` for live product search. `commission_rates(category_key, rate_bps)` (`0008`) for the commission % shown before publish (D4).
- **Caps are enforced by M12-P02 (merged W6):** import its **`require_listing_cap`** dependency (`app.services.kyc.caps`) and add `Depends(require_listing_cap)` to the create route — the 31st T1 listing → 403. Wholesale is **T2-gated** (check vendor `kyc_tier`).
- Vendor app: `localePrefix:"always"` → the page lives at **`apps/vendor/app/[locale]/listings/new/`** (the spec's `app/listings/` path is stale). `@vergeo/ui` forms; **money entered as ZMW decimal, converted client-side to integer ngwee, re-validated server-side** (float on money = review-blocking bug).
- API routers auto-discover (never edit `main.py`); service-role/user-token clients per module.
- **Interface edge with M12-P05 (same wave, image upload):** you create the listing; M12-P05 attaches images via `listing_images`. Keep listing-create independent of images (images attach after create).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P03.

## 2. Objective & scope

Three creation paths — **search-and-attach to a canonical product**, **submit-new-canonical → moderation**, **commodity quick-list (no canonical)** — with commission shown before publish, caps enforced, price converted exactly.
**Non-goals:** no image pipeline (M12-P05 — separate), no listing management/edit (M12-P04), no canonical moderation queue (M13-P03), no cart.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/listings/new/page.tsx` (+ `new/_components/*`: canonical live-search + attach, spec preview, new-canonical form, quick-list form, condition/price/wholesale fields) · `services/api/app/routers/vendor_listings.py` · `services/api/tests/test_listing_create.py`
- **Modify:** `packages/i18n/messages/en/vendor.json` (add a nested `listings` section — **you solely own `vendor.json` this wave**)
  **Guardrail: nothing else. Do NOT touch `listing_images.py`/`image-manager.tsx` (M12-P05), `kyc*`/onboarding files, `main.py`, schema/db.ts, or `request.ts`.**

## 4. Implementation spec

- **`vendor_listings.py`** `POST /vendor/listings` (create/validate), `Depends(require_role('vendor'))` + `Depends(require_listing_cap)`: three modes — **attach** (`product_id` set, live search against `products`/`search_documents`), **new-canonical** (creates a product in a **moderation (non-public) state** — not `active` — plus the listing), **quick-list** (`product_id` null, title_override required). Validate `price_ngwee` is a positive integer (reject floats/strings); `condition`, `stock_mode`/`stock_qty`; **wholesale + `price_tiers` + `moq` only for T2+ vendors** (T1 → 403 `wholesale_requires_t2`); tier validation (ascending qty, descending unit price via `is_valid_price_tiers`). Commission % for the category returned/shown **before publish** (from `commission_rates`).
- **Page** (`[locale]/listings/new`): attach flow shows spec preview + **commission % before publish**; ZMW decimal input → integer ngwee client-side (exact, no float drift) → server re-validates; **attach → live in <10 taps** from a search hit; new-canonical → "submitted for review" (not public).
- All copy via `vendor` (`listings.*`); tokens; 360px-first.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first. **Security:** vendor-scoped (a vendor creates only their own listings); caps server-enforced (client cannot bypass); price integer ngwee server-validated; new-canonical never public until moderated; no secrets.

## 10. Tests (RUN before reporting)

`test_listing_create.py`: **three creation paths**; **T1 wholesale denial** (403); **price conversion exactness** (e.g. `K1,234.56` → `123456` ngwee, no float error); **cap integration** (31st T1 listing → 403 via `require_listing_cap`); new-canonical enters moderation (not active). Component: attach live-search + commission-shown. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`; `uv run pytest`, `ruff`, `mypy`.

## 11. Acceptance criteria / DoD

- [ ] Attach → live in <10 taps; new-canonical → moderation (not public); quick-list works.
- [ ] Wholesale blocked for T1; commission shown matches config; price integer-exact.
- [ ] 31st T1 listing → 403 (cap dependency); `vendor.listings.*` nested; repo + API green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M12-P03 — Listing creation
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste three-paths + T1-wholesale-403 + price-exactness + cap-integration output
**EXCERPTS:** the create-route validation (price + wholesale-T2 + cap dependency) — nothing else
**QUESTIONS:** (or "none")
