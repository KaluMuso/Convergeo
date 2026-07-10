> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M09-P10 — Scheduled jobs & manual-dispatch surfaces

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **Order state machine merged (M09-P01, `orders/state.py`):** transition via `transition_order(...)` — **never raw UPDATEs.** Auto-confirm = the same transition M09-P06 uses (`confirm_received` → Completed); auto-release = **M08-P08 `evaluate_and_release(service_client, order_id)`** (merged `escrow/release.py`).
- **Release engine already skips holds:** `release.py` returns `("held","dispute_open")` when `_has_open_dispute` is true (statuses `open`/`vendor_responded`/`under_review` after M09-P09). Your jobs **must also skip disputed/held orders** — but since `evaluate_and_release` is idempotent + hold-aware, calling it on a held order is a no-op; still, filter obviously-held orders out of the batch for efficiency.
- **Idempotency is the theme:** re-running a job must **never double-fire** a transition or release. Auto-confirm is idempotent via `transition_order` (already-Completed → no-op); auto-release via the ledger idempotency guard (`release-{order_id}` key). Batch-safe: `LIMIT` + cursor.
- **Windows:** 48h auto-confirm after `Delivered`; 7d auto-release after `Shipped` (only if not already released/confirmed). Reuse `release.py`'s window constants where possible; do not hardcode divergent values.
- **Internal auth:** these endpoints are **called by n8n**, not customers — guard with the internal-token pattern (mirror any existing internal endpoint; if none, a shared-secret header validated server-side, secret from env). **Not** customer-authed.
- **Dispatch timeline:** `apps/customer/.../orders/[id]/page.tsx` (M09-P05, merged) — **you own the SOLE W13 edit to this page** (mount `<DispatchTimeline>`). Admin-pasted courier/tracking comes from **M13-P06 order-ops (merged W10/W11)** stored on the order (tracking note / order_events); render it read-only for the customer.
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P10. **⚙ M13-P06 data:** read the existing tracking/dispatch fields the ops console writes; if a field is absent, render the states you have (do NOT add a migration).

## 2. Objective & scope

Idempotent scheduled jobs — **48h auto-confirm after Delivered**, **7d auto-release after Shipped** — via the state machine + M08-P08 release engine, **skipping disputed/held orders**, batch-safe (LIMIT + cursor); plus a **customer dispatch timeline** rendering courier + tracking note + status updates ≤1 min after admin entry. n8n workflow JSON that calls the job endpoints.
**Non-goals:** no new transitions/release logic (call M09-P01 + M08-P08), no admin ops console (M13-P06), no schema change, no confirm/report UI (M09-P06).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/internal_order_jobs.py` (internal-token: `POST /internal/order-jobs/auto-confirm`, `POST /internal/order-jobs/auto-release` — batch, idempotent) · `infra/n8n/order-jobs.json` (schedule → calls the two endpoints) · `apps/customer/app/[locale]/account/orders/[id]/_components/dispatch-timeline.tsx` · `services/api/tests/test_order_jobs.py`
- **Modify:** `apps/customer/app/[locale]/account/orders/[id]/page.tsx` (**mount `<DispatchTimeline>` — sole W13 editor of this page; do not touch M09-P06's `confirm-received.tsx`/`report-problem.tsx`**) · `packages/i18n/messages/en/orders.json` (append `orders.dispatch.*`, append-rule)
  **Guardrail: nothing else. Do NOT touch `orders/state.py`, `escrow/*` (call `evaluate_and_release`), `order_confirmation.py` (M09-P09), `main.py`, other `infra/n8n/*.json` (M14-P06), schema/db.ts.**

## 4. Implementation spec

- **`internal_order_jobs.py`:** batch-select candidate orders (`Delivered` >48h and not Completed; `Shipped` >7d and not released/confirmed), **excluding held/disputed**, `LIMIT` + cursor. For each: auto-confirm → `transition_order(confirm_received, actor=system)`; auto-release → `evaluate_and_release(service_client, order_id)`. **Re-run over the same batch = no double-fire** (assert). Uniform envelope; internal-token guard (env secret); return counts processed/skipped.
- **`order-jobs.json`:** n8n schedule trigger → HTTP calls to both endpoints with the internal token (token as an n8n credential/expression, **never inline in repo**); importable against staging.
- **`dispatch-timeline.tsx`:** read-only render of courier + tracking note + status updates from the order data already passed to `page.tsx`; token-styled, 360px, no client fetch waterfall (server-rendered data). Copy via `orders.dispatch.*`.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; jobs **idempotent under re-run/overlap** (double-run → no double transition/release); held orders untouched; internal endpoints not reachable by customers (token-guarded, secret in env); timeline read-only; no secrets in the n8n JSON.

## 10. Tests (RUN before reporting)

`test_order_jobs.py`: **double-run idempotency** (run auto-confirm/auto-release twice → transition + release fire exactly once each); **dispute skip** (held/disputed order untouched); **window boundary** (47h59m vs 48h01m for confirm; <7d vs >7d for release); **internal-token guard** (missing/wrong token → 401/403); **timeline render** (component test: courier + tracking + statuses). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Re-running jobs never double-fires transitions/releases; held orders untouched; customer sees dispatch updates ≤1 min after admin entry.
- [ ] Endpoints internal-token-guarded (env secret, none in repo/n8n JSON); `orders.dispatch.*` appended (append-rule); sole editor of `orders/[id]/page.tsx`; full API suite + customer build green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P10 — Scheduled jobs & manual-dispatch surfaces
**STATUS/FILES/DEVIATIONS** (note the internal-token mechanism + which order fields the timeline reads from M13-P06) **/TESTS** (paste double-run idempotency + dispute-skip + window-boundary + internal-token + timeline-render + full-pytest tail) **/EXCERPTS** the idempotent batch job + the `evaluate_and_release` call site — nothing else **/QUESTIONS**
