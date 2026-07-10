> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M13-P09 — Dashboards

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **⚠ Admin app uses `[locale]/` routing:** the admin home is **`apps/admin/app/[locale]/page.tsx`** (exists) — you **replace/extend** it with the dashboard. NOT `apps/admin/app/page.tsx`.
- **Ledger is truth (M08-P05 merged):** **payout liabilities = escrow-held + released-unpaid** derived from ledger accounts (same seams M12-P08 used — sum escrow + vendor_payable). No parallel bookkeeping.
- **Reconciliation MERGED (M08-P07):** the reconciliation tile surfaces the **daily report state (green/red + drill-in)** from `reconciliation_reports` (0018). **AC: an injected ledger mismatch flags red on the dashboard.**
- **AI usage tile:** there is **no `ai_usage` table yet** (M06-P03, later wave) — render the **AI-usage/spend-vs-$15-cap tile as "no data"/flagged** (do NOT add a table; guard behind a flag). Other tiles use real data.
- **Aggregates:** GMV, orders-by-status, vendor/listing/product counts, funnel snapshot — from existing tables. **Cached 5min.** Loads <2s.
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P09. **i18n `admin` (append-rule):** append `admin.dashboard.*` (M13-P05 also appends `admin.disputes.*` — disjoint sections).

## 2. Objective & scope

Admin home dashboard: **GMV, orders-by-status, payout liabilities (ledger), reconciliation status (green/red + drill-in), vendor/listing/product counts, AI usage+spend (no-data until M06-P03), funnel snapshot** — aggregate endpoints cached 5min, loads <2s; **injected ledger mismatch → red**.
**Non-goals:** no AI-usage table (M06-P03), no dispute console (M13-P05), no new schema, no reconciliation engine (M08-P07 merged — read its report).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/_components/*` (dashboard tiles — your files) · `services/api/app/routers/admin_dashboards.py` (aggregate endpoints, admin-scoped, cached 5min) · `services/api/tests/test_admin_dashboards.py`
- **Modify:** `apps/admin/app/[locale]/page.tsx` (**replace placeholder with the dashboard — you own this edit; M13-P05 owns `[locale]/disputes/*`, not this file**) · `packages/i18n/messages/en/admin.json` (**APPEND-RULE** — append `admin.dashboard.*`)
  **Guardrail: nothing else. Do NOT touch `admin/app/[locale]/disputes/*` (M13-P05), reconciliation engine (M08-P07 — read `reconciliation_reports`), ledger internals (read via query seam), `main.py`, schema/db.ts. No migration.**

## 4. Implementation spec

- **`admin_dashboards.py`** (admin-role + allowlist, uniform envelope, **cached 5min**): `GET /admin/dashboard` → GMV, orders-by-status counts, **payout liabilities = escrow-held + released-unpaid (ledger-derived)**, **reconciliation tile from the latest `reconciliation_reports` row (green/red + drill-in id)**, vendor/listing/product counts, funnel snapshot, and an **AI-usage tile gated to "no data"** (flag). Aggregates must reconcile with source tables.
- **Pages/tiles:** dashboard grid on `[locale]/page.tsx`; reconciliation tile red on mismatch with drill-in link; number formatting via `formatK` for money; loads <2s (server-rendered aggregates, cached). Copy via `admin.dashboard.*`.

## 5–9. Security etc.

Admin-role + allowlist; **numbers reconcile with source tables**; **injected mismatch → red**; AI tile flagged/no-data (no fake numbers); 5min cache; <2s load; no secrets.

## 10. Tests (RUN before reporting)

`test_admin_dashboards.py`: **aggregate correctness vs fixtures** (GMV, orders-by-status, payout liabilities = ledger accounts, counts); **mismatch surfacing** (injected `reconciliation_reports` mismatch → tile red); **cache behavior** (5min); admin authz (non-admin → 403). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Injected ledger mismatch flags red; numbers reconcile with source tables; loads <2s; AI tile shows "no data" (flagged).
- [ ] Payout liabilities = escrow + released-unpaid (ledger); `admin.dashboard.*` appended (append-rule); sole editor of `[locale]/page.tsx`; admin build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P09 — Dashboards
**STATUS/FILES/DEVIATIONS** (ledger liability seams reused; reconciliation tile source; AI-tile flag) **/TESTS** (paste aggregate-vs-fixtures + mismatch-red + cache + admin-authz + full-pytest tail) **/EXCERPTS** the payout-liability aggregate + the reconciliation-red mapping — nothing else **/QUESTIONS**
