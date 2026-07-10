> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M13-P05 — Disputes console

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **Dispute service MERGED (M09-P09, `services/disputes/service.py`):** call **`resolve(service_client, *, dispute_id, admin_user_id, decision, admin_decision, customer_momo, customer_rail, partial_refund_ngwee)`** — `decision ∈ {resolved_refund, resolved_release, resolved_partial}`. It runs the guarded state machine, **moves money BEFORE committing the terminal status** (idempotent M08 calls; a thrown refund leaves the dispute re-drivable), and for partial **asserts the executed amount == the decided amount** (409 `partial_refund_amount_drift`). **Never poke the ledger manually — always go through `resolve()`.**
- **⚠ Admin app uses `[locale]/` routing** (`apps/admin/app/[locale]/page.tsx` exists). Your pages live under **`apps/admin/app/[locale]/disputes/`** — NOT `apps/admin/app/disputes/`.
- **Decisions → exact ledger (already wired in `resolve()`):** full refund → M08-P10 lane-1; partial → lane-2 (validated ≤ order total, exact-amount asserted) + release remainder; release → M08-P08. Your job = the **admin UI + router** that gathers evidence/context and calls `resolve()`. **Note mandatory.** Partial `partial_refund_ngwee` validated **≤ order total** before calling.
- **Evidence** = private `order-evidence` bucket → signed URLs (mirror the merged signed-download pattern). Both-side evidence + order/payment/ledger context panel.
- **Admin auth (M13-P01 merged):** admin-role + separate-origin allowlist.
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P05. **i18n `admin` (append-rule):** append `admin.disputes.*` (M13-P09 also appends `admin.dashboard.*` to `admin.json` this wave — disjoint sections).

## 2. Objective & scope

Admin disputes console: queue (by age/value), detail (both-side evidence via signed URLs, order+payment+ledger context, decisions **full refund / partial (ngwee) / release** with **mandatory note**), executing via the merged `resolve()` — partial validated ≤ order total, double-decision-guarded (state machine).
**Non-goals:** no dispute state machine / ledger logic (M09-P09 merged — call `resolve()`), no returns console, no order-ops console (M13-P06).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/admin/app/[locale]/disputes/page.tsx` (queue) · `apps/admin/app/[locale]/disputes/[id]/page.tsx` (detail + decision) · `apps/admin/app/[locale]/disputes/_components/*` (your files) · `services/api/app/routers/admin_disputes.py` (admin-scoped queue/detail/decide → `resolve()`) · `services/api/tests/test_admin_disputes.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/admin.json` (append `admin.disputes.*`)
  **Guardrail: nothing else. Do NOT touch `disputes/service.py`/`state.py` (M09-P09 — call `resolve()`), `refunds/*`/`escrow/*` (via `resolve()`), `admin/app/[locale]/page.tsx` (M13-P09), `main.py`, schema/db.ts.**

## 4. Implementation spec

- **`admin_disputes.py`** (admin-role + allowlist, uniform envelope): `GET /admin/disputes` (queue sorted by age/value), `GET /admin/disputes/{id}` (both-side evidence signed URLs + order/payment/ledger context), `POST /admin/disputes/{id}/decide` → validate **note non-empty** + (for partial) **`partial_refund_ngwee ≤ order total`** → call `resolve(...)`. Surface `resolve()` errors (e.g. `partial_refund_amount_drift`, invalid-transition 409) as the uniform envelope. Double-decision → the state machine's 409 (already resolved).
- **Pages:** queue table (age/value/SLA), detail with evidence viewer + context panel + decision form (radio: full/partial/release, ngwee input for partial, mandatory note). 360px+desktop; copy via `admin.disputes.*`.

## 5–9. Security etc.

Admin-role + separate-origin allowlist; note mandatory (block empty); partial ≤ order total; evidence via short-lived signed URLs; decisions only via `resolve()` (no manual ledger); double-decision guarded; no secrets.

## 10. Tests (RUN before reporting)

`test_admin_disputes.py`: **decision→`resolve()` mapping per type** (full/partial/release call `resolve` with the right decision + args — spy); **partial bounds** (`partial_refund_ngwee > order total` → rejected before `resolve`); **note mandatory** (empty → 400); **double-decision guard** (second decide on a resolved dispute → 409 surfaced); admin authz (non-admin → 403). `pnpm --filter admin build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Each decision produces exactly the right ledger transactions (via `resolve()`); note mandatory; parties notified (through `resolve()`); dispute SLA visible.
- [ ] Partial validated ≤ order total; double-decision guarded; `admin.disputes.*` appended (append-rule); admin build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P05 — Disputes console
**STATUS/FILES/DEVIATIONS** (confirm pages under `[locale]/disputes/`; how `resolve()` errors surface; partial ≤ order-total validation) **/TESTS** (paste decision→resolve-mapping + partial-bounds + note-mandatory + double-decision + admin-authz + full-pytest tail) **/EXCERPTS** the decide handler → `resolve()` call — nothing else **/QUESTIONS**
