> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free.

# M13-P07 — Config editors

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master`:

- **Admin hardening is live (M13-P01):** `apps/admin/app/[locale]/layout.tsx` (nav shell), `apps/admin/middleware.ts` (admin gate + CF-Access), `services/api/app/routers/admin_base.py` (base router: `require_role('admin')` + **transparent audit middleware** — every admin mutation → `audit_log`). **Mount your config router on `admin_base`** so audit + authz are automatic. `packages/i18n/messages/en/admin.json` exists (M13-P01) — **add a nested `config` section** (no flat dotted keys). You are the only W6 pebble touching `admin.json`.
- **Config tables (`0008`):** `commission_rates(category_key, rate_bps)`, `delivery_zones(zone_key, label, fee_ngwee, active)`, `platform_config(key, value jsonb, description)` (incl. `cod_cap_ngwee`, `ai_*_quota`, release windows), `feature_flags`, `prohibited_categories`, category tree in `categories` (materialized `path`, `0003`). **These are edited, not created.**
- API: routers auto-discover (never edit `main.py`); service-role client confined. Admin app is `localePrefix:"always"` → routes under `apps/admin/app/[locale]/`.
- **Snapshot immunity:** orders/commissions snapshot rate at order time (M08-P12) — config edits must affect **only NEW** orders.
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P07.

## 2. Objective & scope

Admin config editors (commissions, delivery zones, platform config, feature flags, category tree) with typed validation, audit, and no-deploy effectiveness.
**Non-goals:** no merchandising manager (M13-P08), no new config schema, no dashboards (M13-P09), no admin shell (M13-P01).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/config/{commissions,delivery-zones,platform,flags,categories}/page.tsx` · `config/_components/*` · `services/api/app/routers/admin_config.py` · `services/api/tests/test_admin_config.py`
- **Modify:** `packages/i18n/messages/en/admin.json` (add nested `config` section)
  **Guardrail: nothing else. Do NOT edit `admin_base.py`/middleware/layout (M13-P01), `main.py`, schema/`db.ts`, or other namespaces.**

## 4. Implementation spec

- **`admin_config.py`** (mounted on `admin_base` → audit + `require_role('admin')` automatic): typed CRUD per config surface with **per-key validation**: commission `rate_bps` **0–2000**; ngwee values are non-negative ints; release-window hours within bounds; zone fee ngwee int. Invalid → **422/400 with field errors** (envelope). Every mutation is audited (via admin_base) + **effective without deploy** (reads are live).
- **Category tree editor:** drag-reorder + prohibit toggle; **guard against orphaning** — moving a parent prompts to move children (no orphan `parent_id`; keep `path` consistent).
- **Dangerous edits (COD cap, commissions):** confirmation UI showing **old→new diff** before commit.
- Pages: server components + minimal client for editors; all copy via `admin.config.*`.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Admin `noindex`; functional editors. **Security:** admin-only (admin_base gate); every mutation audited; validation server-side (client cannot submit out-of-bounds); service-role confined; no secrets.

## 10. Tests (RUN before reporting)

`test_admin_config.py`: **validation bounds per key** (rate_bps >2000 rejected, negative ngwee rejected, bad window rejected); **category tree integrity ops** (move-children, no orphan); **audit diff** written on mutation; **non-admin → 403** (via admin_base). **Snapshot-immunity note:** add a test or documented assertion that a commission change does NOT alter existing order snapshots (cross-ref M08-P12; if snapshot tables aren't in this wave, assert the config-read path is order-time-only and note the integration point). `uv run pytest`, `ruff`, `mypy`. i18n completeness `admin.config.*`. `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`.

## 11. Acceptance criteria / DoD

- [ ] Every config mutation validated (bounds per key) + audited + effective without deploy.
- [ ] Category tree edits guard against orphaning; dangerous edits show old→new diff.
- [ ] Commission change affects only NEW orders (tested/documented); non-admin 403; `admin.config.*` nested; repo green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M13-P07 — Config editors
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste validation-bounds + tree-integrity + audit-diff + non-admin-403 output
**EXCERPTS:** the per-key validation in `admin_config.py` — nothing else
**QUESTIONS:** (or "none")
