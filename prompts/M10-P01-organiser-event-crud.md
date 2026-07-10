> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M10-P01 — Organiser event CRUD

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master` — **events schema already exists (0004_services_events.sql):**

- **`events` (0004:84):** `organiser_vendor_id`, `slug`, category/venue/lat/lng/landmark/description/images fields, **`status text check ('draft','published','cancelled','completed')`** (default `draft`). **RLS already gates organiser CRUD by vendor ownership** (`events_organiser_insert/update/delete/select` — organiser reads own in any status; public reads `published`). **No migration needed.**
- **`event_instances` (0004:109):** `capacity int check (>= 0)` + date/time. Organiser RLS present.
- **`ticket_types` (0004:127):** exists — but **types/inventory are M10-P02's** (parallel). You do event + instance CRUD only; **do NOT create `events/[id]/tickets/page.tsx`** (M10-P02 owns it) and **do NOT own `ticket_types.py`**.
- **Organiser = KYC'd vendor** (there is **no separate organiser flag** — `vendors.kyc_tier` / `status='active'`). Gate create/edit on an active-KYC vendor the caller owns. Reuse the KYC-tier check convention from M12-P02.
- **Publish flow** `draft→published→ended|cancelled`: map **"ended" → the existing `completed` status** (do not invent a new enum value — additive freeze). Validate: past-date instances rejected on publish; **instance `capacity ≥ sold count` enforced on edit** (query issued `tickets` for the instance — table exists, 0004:149).
- **Post-sale edit restriction:** venue/date changes **after tickets sold** flag a ticket-holder **notification event** — emit via the merged notification path (`app.services.notifications.events.emit_event` / outbox); if the exact event key isn't registered, enqueue an outbox row with a `TODO(M14)` mapping rather than blocking.
- **i18n:** organiser keys → `events.json` (append-rule); vendor-app nav/labels → `vendor.json` (`vendor.events.*`, append-rule). Vendor app uses the `vendor` namespace for its chrome; event-domain labels may reuse `events`.
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P01. Images ≤8 via the merged Cloudinary signing seam (M05-P10).

## 2. Objective & scope

Organiser (KYC'd vendor) event CRUD: list / create / edit with title, category (6), venue + lat/lng + landmark, images (≤8), description, instances (date/time, capacity), and a **publish flow** (`draft→published→ended(=completed)|cancelled`) with **edit restrictions after sales** (venue/date change → ticket-holder notification; capacity ≥ sold enforced).
**Non-goals:** no ticket types/pricing/inventory (M10-P02), no purchase/checkout (M10-P03, W14), no public event pages (M05-P11 merged), no schema change.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/events/page.tsx` (list) · `apps/vendor/app/[locale]/events/new/page.tsx` · `apps/vendor/app/[locale]/events/[id]/edit/page.tsx` · `apps/vendor/app/[locale]/events/_components/` (event form, instance editor, image picker — your files only) · `services/api/app/routers/organiser_events.py` (CRUD + publish, KYC-gated, ownership-scoped) · `services/api/tests/test_organiser_events.py`
- **Modify (APPEND-RULE — disjoint sections):** `packages/i18n/messages/en/events.json` (append organiser keys) · `packages/i18n/messages/en/vendor.json` (append `vendor.events.*`)
  **Guardrail: nothing else. Do NOT create `events/[id]/tickets/*` (M10-P02), `ticket_types.py`/`tickets/inventory.py` (M10-P02), `main.py`, schema/db.ts. Additive-only — no migration.**

## 4. Implementation spec

- **`organiser_events.py`** (auth, KYC-gated, ownership-scoped, uniform envelope, rate-limited): `GET /organiser/events` (own), `POST` (create draft), `PATCH /organiser/events/{id}` (edit — restricted after sales), `POST /organiser/events/{id}/publish` (draft→published; reject past-date instances), `POST .../cancel`, `POST .../end` (→ `completed`). Instance edit: `capacity ≥ sold` (count issued `tickets`). Venue/date change post-sale → emit ticket-holder notification event. **Non-KYC vendor → 403; vendor B cannot touch vendor A's event (RLS + explicit authz).**
- **Pages:** mobile-first organiser forms (360px), Cloudinary image upload (≤8 via merged seam), instance repeater; publish/cancel/end actions gated by current status. Copy via `events`/`vendor` keys.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; non-KYC blocked; cross-vendor blocked (authz + RLS test); publish rejects past dates; capacity-not-below-sold on edit; images ≤8; no secrets.

## 10. Tests (RUN before reporting)

`test_organiser_events.py`: **authz** (non-KYC → 403; vendor B on vendor A's event → 403/404); **edit-restriction matrix** (venue/date change pre-sale ok; post-sale → notification event + allowed only within rules; capacity below sold → rejected); **publish validation** (past-date instance → rejected; draft→published→completed/cancelled transitions). `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Non-KYC vendor cannot create; post-sale date change triggers a notification event; instance capacity ≥ sold count enforced on edit.
- [ ] Publish rejects past dates; `ended` maps to `completed` (no new enum); `events.json` organiser keys + `vendor.events.*` appended (append-rule); no migration; vendor build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P01 — Organiser event CRUD
**STATUS/FILES/DEVIATIONS** (note the KYC gate source + how `ended` maps to `completed` + the post-sale notification event key) **/TESTS** (paste authz + edit-restriction + capacity≥sold + publish-validation + full-pytest tail) **/EXCERPTS** the publish transition + post-sale edit guard — nothing else **/QUESTIONS**
