> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 9 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — no migration. Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M13-P04 — Listing & review flag queues

## 1. Context

**Wave 9 (parallel ×6).** Grounded against as-built `master`:

- **`public.flags` exists (0007):** `id, entity_type text, entity_id uuid, reason text, reporter_user_id, status text default 'open' check (open|actioned|dismissed), created_at, updated_at`. Reuse it — **no new schema**. **Repeat-offender counter = computed** (count `actioned` flags per vendor), not a new column. **Suspension = `vendors.status` change** (`active`→`suspended`): listings hidden, but **in-flight/delivered orders unaffected** (payouts continue) — do NOT cascade-cancel.
- **Admin app = separate hardened origin**, `localePrefix:"always"` → page at **`apps/admin/app/[locale]/moderation/flags/page.tsx`** (spec's `app/moderation/…` is stale). `moderation/` already exists (M13-P03 `moderation/products/`, merged W8) — `flags/` is a new sibling subpath. `require_role('admin')` + audit come from the merged **`admin_base`** (M13-P01/P07) — mount on it. Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
- **State-machine rule:** flag status transitions + vendor suspension mutate via guarded writes + **audit log** — never a raw status UPDATE (M15/M13 audit). Actions also **enqueue `notification_outbox`** (M14-P01 dispatches) — warn-vendor / suspension notify.
- i18n `admin` namespace registered; `admin.json` **shared with M13-P08 this wave** — you own a nested **`flags`** section (append-rule below).
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P04. Prohibited-category attempts also land here (M15-P08 blocks + flags server-side — code the queue to display `entity_type='prohibited'`-style rows too; do not build the blocker).

## 2. Objective & scope

A unified admin flag queue (listing flags + review flags + prohibited-attempt flags) with actions **dismiss / unpublish / remove / warn-vendor / escalate-suspend**, a per-vendor **repeat-offender counter**, exact **suspension semantics** (listings hidden, in-flight orders unaffected, payouts continue), all **audited + notified**.
**Non-goals:** no disputes console (M13-P05), no prohibited-category blocker (M15-P08 — you only surface its flags), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/moderation/flags/page.tsx` (+ `_components/*`) · `services/api/app/routers/admin_flags.py` · `services/api/tests/test_admin_flags.py`
- **Modify:** `packages/i18n/messages/en/admin.json` (append nested `flags` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `admin_merch.py` / `merch/*` (M13-P08), `admin_products.py`/`moderation/products/*` (M13-P03), `admin_base`, `main.py`, schema.**

## 4. Implementation spec

- **`admin_flags.py`** (mount on `admin_base` → `require_role('admin')` + audit): `GET /admin/flags` (unified queue: listing/review/prohibited; filter by status/entity_type; oldest-first) + action endpoints **dismiss / unpublish (listing hidden ≤1min) / remove / warn-vendor / escalate-suspend**. Each action: guarded status write + **audit row** + **`notification_outbox` enqueue** where the actor is notified. **Repeat-offender counter** returned per vendor (count of `actioned` flags). **Suspension:** set `vendors.status='suspended'` (guarded) — listings stop surfacing publicly, **but existing orders/payouts are untouched** (no cascade).
- **Flags page:** unified queue with the action set, repeat-offender badge, confirm on destructive actions. All copy via `admin` (`flags.*`).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Admin-origin only (`require_role('admin')`); every action audited + (where relevant) notified; suspension does not touch in-flight orders (tested); injection-safe; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_admin_flags.py`: **action-semantics matrix** (dismiss/unpublish/remove/warn/suspend → correct status + audit + outbox enqueue); **suspension side-effects** (listings hidden, in-flight orders + payouts unaffected); **repeat-offender counter**; **authz** (non-admin → 403). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite (import guard).**

## 11. Acceptance criteria / DoD

- [ ] Unpublish reflects publicly ≤1min; suspension exact (in-flight orders/payouts unaffected); repeat counter correct.
- [ ] Every action audited + notified (outbox); non-admin 403; `admin.flags.*` nested (append-rule); full API suite + repo green.

## admin.json rule (shared with M13-P08 this wave)

Append ONLY your nested `flags` section; do NOT reorder/reformat siblings. The later-merging admin PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P04 — Flag queues
**STATUS/FILES/DEVIATIONS/TESTS** (paste action-matrix + suspension-side-effects + authz + full-pytest tail) **/EXCERPTS** the suspension guarded-write + audit/outbox enqueue — nothing else **/QUESTIONS**
