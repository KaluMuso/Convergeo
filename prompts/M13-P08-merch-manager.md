> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 9 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — no migration (`merch_slots` is already complete). Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M13-P08 — Merchandising manager

## 1. Context

**Wave 9 (parallel ×6).** Grounded against as-built `master`:

- **`public.merch_slots` is complete (0008) — NO migration:** `id, slot_key text, variant_key text, payload jsonb, schedule_from timestamptz, schedule_to timestamptz, position int, active bool, created_at, updated_at`. You CRUD these. **Home reads them (M05-P01, merged W7)** — the home page ISR-renders active, in-window slots; you write the same rows it reads (schedule windows in **Africa/Lusaka**).
- **Admin app = separate hardened origin**, `localePrefix:"always"` → page at **`apps/admin/app/[locale]/merch/page.tsx`** (spec's `app/merch/` is stale). `require_role('admin')` + audit come from the merged **`admin_base`** (M13-P01/P07) — mount on it. Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- **Draft→publish + preview:** a **`?merch_preview=draft`** token-gated view on the customer home shows draft slots without publishing. (Home is M05-P01's file — you do NOT edit it; the preview is served by returning draft slots from your API when the token is present, and home already reads the slot API — **confirm the read contract; if home can't yet request drafts, ship the API's draft/preview support + a documented `TODO(home)` for the query wiring**. Do NOT edit `(shop)/page.tsx`.)
- i18n `admin` namespace registered; `admin.json` **shared with M13-P04 this wave** — you own a nested **`merch`** section (append-rule below).
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P08. Hero variants come from the design set (variant_key); banner images via the merged Cloudinary `/media/sign` (public) — reuse, don't rebuild.

## 2. Objective & scope

The admin merch slot board (hero variant picker, banner slot editor w/ Cloudinary image + link + schedule, featured-collection builder: listings/category/tag query + order + i18n title keys, rotation scheduling), **draft→publish**, **schedule windows (Lusaka TZ)**, and **preview** — composing the customer home without deploys.
**Non-goals:** no home rendering (M05-P01 — you write the slots it reads), no dashboards (M13-P09), no new schema, no editing `(shop)/page.tsx`.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/merch/page.tsx` (slot board) · `merch/_components/*` (hero-variant picker, banner editor, collection builder) · `services/api/app/routers/admin_merch.py` · `services/api/tests/test_admin_merch.py`
- **Modify:** `packages/i18n/messages/en/admin.json` (append nested `merch` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `admin_flags.py`/`moderation/*` (M13-P04), `(shop)/page.tsx` (M05-P01), `main.py`, `merch_slots` schema, `media.py`.**

## 4. Implementation spec

- **`admin_merch.py`** (mount on `admin_base` → `require_role('admin')` + audit): slot CRUD (`slot_key`, `variant_key`, `payload`, `position`, `schedule_from/to`, `active`); **draft vs published isolation** (draft edits don't affect live home until published); **schedule windows resolved in Africa/Lusaka** (expired/empty window → fall back to the default slot); **preview** returns draft slots when a valid `merch_preview` token is presented. Every mutation **audited**. Collection builder persists a listings/category/tag query + order + i18n title key into `payload`.
- **Merch page:** slot board (hero/banners/collections/events-row order via `position`), hero-variant picker (preview thumbnails from the design variant set), banner editor (Cloudinary image via `/media/sign` + link + schedule), featured-collection builder, draft/publish toggle. All copy via `admin` (`merch.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Admin-origin only (`require_role('admin')`); draft/publish isolation; schedule windows Lusaka-correct; preview token-gated; every mutation audited; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_admin_merch.py`: **slot CRUD + schedule windows** (in-window active, expired → fallback, across a Lusaka boundary); **publish/draft isolation** (draft not live until published); **fallback on empty/expired**; **preview token gate** (invalid token → no drafts); **authz** (non-admin → 403); mutations audited. `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Swap hero / reorder collections → the rows home reads change ≤1min without a deploy; expired schedule auto-falls-back (Lusaka TZ).
- [ ] Draft/publish isolated; preview token-gated (shows draft without publishing); non-admin 403; `admin.merch.*` nested (append-rule); full API suite + repo green.

## admin.json rule (shared with M13-P04 this wave)

Append ONLY your nested `merch` section; do NOT reorder/reformat siblings. The later-merging admin PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P08 — Merchandising manager
**STATUS/FILES/DEVIATIONS** (note the home preview-read contract + any `TODO(home)`) **/TESTS** (paste schedule-window + draft/publish-isolation + preview-gate + authz + full-pytest tail) **/EXCERPTS** the schedule-window resolution (Lusaka TZ) + draft/publish isolation — nothing else **/QUESTIONS**
