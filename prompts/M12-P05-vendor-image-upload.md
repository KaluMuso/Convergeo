> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 7 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN — no migration** (`listing_images` exists). Stay dep-free.

# M12-P05 — Vendor image upload pipeline

## 1. Context

**Wave 7 (parallel ×8).** Grounded against as-built `master`:

- **`public.listing_images`** (`0003`) already exists (grep exact columns: `listing_id → vendor_listings, url/public_id, position, is_cover …`) with a **≤8-image guard trigger**. You add the attach/detach/reorder metadata API over it. `vendor_listings.status` gates.
- **Cloudinary signing is merged (M05-P10):** `POST /media/sign` with `resource_kind: 'listing'` → signed Cloudinary params for a **vendor-scoped folder** (`listings/{vendor_id}`). Reuse it — do NOT add a new signing endpoint (this is public product media, NOT the KYC private bucket).
- `@vergeo/ui` has media primitives (M02-P08: `CloudinaryImage`, `sanitizePublicId`). Vendor app `localePrefix:"always"` → components under **`apps/vendor/app/[locale]/listings/`** (spec's `app/listings/` is stale).
- **Interface edges (same wave):** M12-P03 creates the listing (you attach images after create — the manager takes a `listingId`); M12-P03 **owns `vendor.json`** — you **consume** `listings.images.*` keys it provides (do NOT edit `vendor.json`; list needed keys in QUESTIONS if missing).
- API routers auto-discover (never edit `main.py`).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P05.

## 2. Objective & scope

Direct-to-Cloudinary signed upload (vendor-scoped) with client-side downscale for data cost, reorder, cover-select, ≤8 enforced client + server; plus the `listing_images` attach/detach/reorder metadata API.
**Non-goals:** no listing create (M12-P03), no KYC docs (M12-P02b — different, private bucket), no CSV import (M12-P06).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/listings/_components/image-manager.tsx` (UploadDropzone wiring: signed upload, client-side downscale before upload, per-file progress + retry, reorder, cover select, ≤8) · `services/api/app/routers/listing_images.py` (attach/detach/reorder metadata) · `services/api/tests/test_listing_images.py`
  **Guardrail: nothing else. Do NOT edit `vendor.json` (M12-P03 owns it), `vendor_listings.py` (M12-P03), `media.py` (M05-P10), `main.py`, schema/db.ts, or `request.ts`.**

## 4. Implementation spec

- **`image-manager.tsx`:** request signed params from `POST /media/sign {resource_kind:'listing'}`; **client-side downscale** (canvas, e.g. max 1600px longest edge, quality) **before** upload for data cost; direct PUT/POST to Cloudinary; per-file progress + **retry on failure**; reorder (drag), cover select; **≤8 enforced client-side** (9th blocked). EXIF stripped via the Cloudinary transform. Copy via the `vendor` namespace `listings.images.*` keys (from M12-P03).
- **`listing_images.py`:** `POST/DELETE/PATCH` attach/detach/reorder metadata rows in `listing_images`, `Depends(require_role('vendor'))` + **ownership check: the listing must belong to the caller's vendor** (vendor A cannot attach into B's listing → 403). **≤8 enforced server-side too** (the DB guard trigger + an explicit check). Position + cover maintained.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; **2 MB photo uploads on simulated 3G without timeout** (downscaled). **Security:** vendor-scoped folder + ownership check (cross-vendor attach denied — tested); signed params only (no api_secret to client); ≤8 both layers; public product media (not private).

## 10. Tests (RUN before reporting)

`test_listing_images.py`: **cap both layers** (9th image blocked client + server); **authz** (vendor A cannot attach into B's listing → 403); **reorder persistence**; detach. Component: **failed-upload retry**, downscale-before-upload, ≤8 client block. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`; `uv run pytest`, `ruff`, `mypy`.

## 11. Acceptance criteria / DoD

- [ ] 9th image blocked client + server; vendor A cannot attach into B's listing (tested).
- [ ] Downscale-before-upload (3G-safe); reorder + cover persist; retry on failure.
- [ ] No `vendor.json` edit (consume M12-P03 keys); repo + API green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M12-P05 — Vendor image upload pipeline
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste cap-both-layers + cross-vendor-403 + reorder output
**EXCERPTS:** the ownership check in `listing_images.py` — nothing else
**QUESTIONS:** (or "none") — list any `listings.images.*` keys you need from M12-P03
