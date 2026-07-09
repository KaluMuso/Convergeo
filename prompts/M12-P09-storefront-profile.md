> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M12-P09 — Storefront profile editor

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- `public.vendors` (`0002`): `id, slug, display_name, description, logo_url, status ('draft'|'pending_kyc'|'active'|'suspended'), kyc_tier, preferred_badge, …` (**grep for hours/location/landmark/lat-lng columns before coding** — they live on the vendor row or an addresses row; write exactly those columns). Logo upload reuses the merged image/media path (Cloudinary public) — reference it, do not rebuild it.
- **Interface edge with M05-P08 (same wave):** M05-P08 (directory) **reads** the vendor data you **write**. Write the same columns it renders; you own the write side + `vendor_profile.py`; M05-P08 owns the read side + `directory.py`. Disjoint.
- Vendor app `localePrefix:"always"` → page at **`apps/vendor/app/[locale]/profile/page.tsx`**. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- **`vendor.json` shared with M12-P04 + M12-P06 this wave** — you own a nested **`profile`** section (append-rule below).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P09.

## 2. Objective & scope

Storefront profile editor: display name, description, logo, hours, location + landmark (GPS/landmark addressing), preferred badge; **profile-completeness meter**; **slug editable once** (then locked) with **301 redirect from the old slug** and uniqueness/charset validation.
**Non-goals:** no public profile render (M05-P08), no KYC/tier changes (M12-P02), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/profile/page.tsx` (+ `_components/*`) · `services/api/app/routers/vendor_profile.py` · `services/api/tests/test_vendor_profile.py`
- **Modify:** `packages/i18n/messages/en/vendor.json` (add nested `profile` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `directory.py` (M05-P08), `vendor_listings*.py` (M12-P03/P04), `main.py`, schema.**

## 4. Implementation spec

- **`vendor_profile.py`** (`require_role('vendor')` + ownership): `GET /vendor/profile` (own profile) + `PATCH /vendor/profile` (display name, description, logo_url, hours, location+landmark, preferred_badge). **Slug edit:** allowed **once** — validate unique + charset (`[a-z0-9-]`, lowercase), then persist the old slug for a **301 redirect** and lock further slug edits (a `slug_locked`/prior-slug marker on the existing row — grep for or reuse an existing column; if none exists you MUST NOT add a migration → track the old slug via an existing nullable column or reject a second edit by comparing against a stored value). Vendor-scoped (A cannot edit B → 403).
- **Completeness meter:** deterministic score over the filled fields (logo, description, hours, location, badge) — pure function, unit-tested.
- **Profile page:** the editor form + completeness meter + slug-edit-once affordance (with a clear "you can only change this once" warning). All copy via `vendor` (`profile.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; vendor-scoped (cross-vendor edit denied — tested); slug charset/uniqueness enforced; old-slug 301 preserved; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_vendor_profile.py`: **slug edit once then locked** (second edit → 409/blocked); **old-slug 301 mapping preserved**; **slug uniqueness + charset** rejection; **completeness meter** score (deterministic over field combos); **authz** (A cannot edit B). `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite.**

## 11. Acceptance criteria / DoD

- [ ] Slug editable once then locked; old slug → 301; uniqueness+charset enforced; completeness meter deterministic.
- [ ] Cross-vendor edit denied; writes the columns M05-P08 reads; `profile.*` nested (append-rule); full API suite + repo green.

## vendor.json rule (shared with M12-P04 + M12-P06 this wave)

Append ONLY your nested `profile` section; do NOT reorder/reformat siblings. The later-merging vendor PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M12-P09 — Storefront profile editor
**STATUS/FILES/DEVIATIONS** (note the vendor hours/location + old-slug/slug-lock columns grounded, and how slug-once is tracked without a migration) **/TESTS** (paste slug-once + 301 + completeness + authz + full-pytest tail) **/EXCERPTS** the slug-edit-once guard + completeness function — nothing else **/QUESTIONS**
