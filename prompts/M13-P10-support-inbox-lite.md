> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 runs pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M13-P10 — Support inbox-lite

## 1. Context

**Wave 15 (parallel).** Grounded against as-built `master`:

- **⚠ Admin app uses `[locale]/` routing** — your page lives at **`apps/admin/app/[locale]/support/page.tsx`** (NOT bare `app/support/`).
- **Order ops MERGED (M13-P06):** reuse its lookup/context conventions. **Outbox MERGED (M14-P01…P05):** `enqueue_outbox_row` + `resolve_channel` (WhatsApp → SMS → email fallback). **Admin auth MERGED (M13-P01):** admin-role + separate-origin allowlist.
- **Scope fence — NOT a ticketing system:** lookup (order/customer by phone/id) + **canned outbound (i18n-keyed templates) via outbox** + interaction log per customer. Free-text send allowed **with audit**.
- **i18n `admin` (append-rule):** append `admin.support.*` (sole toucher of `admin.json` this wave — M13-P05/P09 were W14).
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P10.

## 2. Objective & scope

Admin support inbox-lite: lookup order/customer by **partial phone or id**, context card, **canned replies (i18n templates) sent via outbox** (channel fallback), free-text send with audit, per-customer interaction log.
**Non-goals:** no ticket/thread system, no order-ops actions (M13-P06), no dispute/return handling (M13-P05/M09), no new outbox channels.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/support/page.tsx` (+ `_components/*`) · `services/api/app/routers/admin_support.py` (lookup + canned/free-text send + log) · `services/api/tests/test_admin_support.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/admin.json` (append `admin.support.*` — canned templates + UI)
  **Guardrail: nothing else. Do NOT touch order-ops (M13-P06), the outbox dispatcher/adapters (M14 — call `enqueue_outbox_row`), `main.py`, schema/db.ts. No migration (use existing tables + `audit_log`).**

## 4. Implementation spec

- **`admin_support.py`** (admin-role + allowlist, uniform envelope, rate-limited): `GET /admin/support/lookup?q=` (partial phone or order/customer id → matching orders/customer + context card); `POST /admin/support/send` (canned template key OR free-text → `enqueue_outbox_row` with `resolve_channel` fallback; **free-text writes an `audit_log` row**); `GET /admin/support/log?customer_id=` (interaction history). Canned templates keyed in `admin.support.*`.
- **Page:** lookup box (partial phone), context card, canned-reply picker + free-text, interaction log; desktop + 360px. Copy via `admin.support.*`.

## 5–9. Security etc.

Admin-role + allowlist; partial-phone lookup; canned send → outbox with correct channel fallback; **free-text send audited**; interaction log complete; no secrets.

## 10. Tests (RUN before reporting)

`test_admin_support.py`: **lookup matching** (partial phone finds the customer/order); **outbox payloads** (canned send lands in outbox with correct channel + fallback); **audit of sends** (free-text → `audit_log` row); admin authz (non-admin → 403). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Lookup by partial phone works; canned send lands in outbox with correct channel fallback; interaction log complete (free-text audited).
- [ ] Pages under `[locale]/support/`; `admin.support.*` appended (append-rule); admin build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P10 — Support inbox-lite
**STATUS/FILES/DEVIATIONS** (lookup matching approach; canned vs free-text audit) **/TESTS** (paste lookup + outbox-payload + audit + admin-authz + full-pytest tail) **/EXCERPTS** the canned-send → outbox + free-text audit — nothing else **/QUESTIONS**
