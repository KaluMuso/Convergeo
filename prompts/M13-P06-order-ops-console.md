> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 10 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M13-P06 — Order ops console & manual dispatch

## 1. Context

**Wave 10 (parallel ×8).** Grounded against as-built `master`:

- **State machine merged (M09-P01):** `app/services/orders/state.py` — **admin interventions are state-machine transitions (audited), never raw updates**; import `transition_order` (actor=admin, note=reason). `order_events` (0005) is the timeline source. **Manual dispatch drives the customer timeline (M09-P10, later)** — write the dispatch as status transitions + `order_events`/notes so the future timeline reads them.
- **⚙ Same-wave edge — ledger (M08-P05):** escrow manual hold/release **posts via M08-P05's ledger templates with a `manual` flag + dual-note** (reason + confirmation phrase). M08-P05 lands this wave — **code against its `post_transaction(template=…)` interface; if unmerged at your build time, stub the ledger call behind a thin local interface + `TODO(M08-P05)` and unit-test the dual-note enforcement independently.** Phase-4 verifies the integration.
- **Admin app = separate hardened origin**, `localePrefix:"always"` → pages at **`apps/admin/app/[locale]/orders/`** (spec's `app/orders/` is stale). `require_role('admin')` + audit via the merged **`admin_base`** (M13-P01/P07). Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- i18n `admin` namespace registered; `admin.json` — **you solely own it this wave** (append a nested `orders` section; do NOT reformat `flags`/`merch`/`moderation`/`config` siblings).
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P06.

## 2. Objective & scope

Admin order ops: search ANY order (id/phone/vendor/status) → full context (items, payment, ledger, timeline) + a **manual dispatch panel** (courier booked: Yango/inDrive/other + tracking note + status updates), status intervention via the state machine (with reason), and **escrow manual hold/release with a dual-note** (reason + confirmation phrase) posting via M08 templates with a `manual` flag.
**Non-goals:** no vendor actions (M09-P02), no disputes (M13-P05), no automated dispatch, no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/orders/page.tsx` (search) · `orders/[id]/page.tsx` (context + manual dispatch + escrow ops) (+ `_components/*`) · `services/api/app/routers/admin_orders.py` · `services/api/tests/test_admin_orders.py`
- **Modify:** `packages/i18n/messages/en/admin.json` (append nested `orders` section)
  **Guardrail: nothing else. Do NOT touch `admin_flags.py`/`admin_merch.py`/`admin_products.py` (other M13), `orders/state.py`/`ledger/*` (M09-P01/M08-P05 — call), `main.py`, schema.**

## 4. Implementation spec

- **`admin_orders.py`** (mount on `admin_base` → `require_role('admin')` + audit): **search** ANY order by id/phone/vendor/status; **order context** (items, payment, ledger postings, `order_events` timeline); **manual dispatch** (courier + tracking note → a status transition via `transition_order`, visible to the customer ≤1min); **status intervention** via the state machine (illegal transitions rejected, reason required); **escrow manual hold/release** → M08-P05 `post_transaction` with a `manual` flag + **both notes required (dual-note enforced — reject if either missing)** and the postings **balance** (Σ=0).
- **Console pages:** search + result list; order detail with the dispatch panel, intervention control (state-machine-gated), and the escrow op with a confirmation-phrase field. All copy via `admin` (`orders.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Admin-origin only (`require_role('admin')`); interventions = state-machine transitions (audited, never raw); manual escrow requires dual-note + balances; injection-safe search; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_admin_orders.py`: **search correctness** (by id/phone/vendor/status); **dispatch → timeline** (dispatch entry appears in `order_events`); **illegal intervention transition rejected**; **dual-note enforcement** (manual escrow op missing a note → rejected); **manual-op ledger balance** (Σ=0, `manual` flag) — stub M08-P05 if unmerged; **authz** (non-admin → 403). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Dispatch entry visible to customer ≤1min; illegal intervention transitions rejected; search correct across id/phone/vendor/status.
- [ ] Manual escrow op requires dual-note (enforced) and balances (Σ=0, `manual` flag); interventions audited via state machine.
- [ ] `admin.orders.*` nested (sole owner); non-admin 403; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P06 — Order ops console & manual dispatch
**STATUS/FILES/DEVIATIONS** (note whether M08-P05 was merged or stubbed) **/TESTS** (paste search + dispatch→timeline + dual-note + ledger-balance + authz + full-pytest tail) **/EXCERPTS** the dual-note enforcement + the state-machine intervention — nothing else **/QUESTIONS**
