> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own the ONLY `config.toml` change this wave** (a private evidence bucket) — no db.ts change. Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M09-P06 — Confirm-received & report-problem

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **⚙ Same-wave edge — escrow release (M08-P08):** **confirm-received → order Completed + fires the release path** — call M08-P08's `evaluate_and_release(order_id)` interface; **if M08-P08 unmerged, stub behind a thin local interface + `TODO(M08-P08)`** and unit-test the confirm idempotency independently. **Order states merged (M09-P01):** confirm = `transition_order(confirm_received)` → Completed (idempotent; a **double-tap fires release exactly once**).
- **Customer order pages merged (M09-P05):** `account/orders/[id]/page.tsx` + `_components/` — you **add** `confirm-received.tsx` + `report-problem.tsx` to that `_components/` dir (disjoint new files; do NOT touch `page.tsx` or M09-P05's components). i18n `orders` namespace — **you solely own `orders.json` this wave** (append confirm/report keys).
- **Evidence upload → a PRIVATE bucket.** Only `kyc-docs` exists; add a **new private `order-evidence` bucket to `config.toml`** (`public=false`, image/pdf mimes, ~10 MiB) + a **signed-upload endpoint** (mirror the merged `kyc_media.py` `/media/kyc-doc/sign` pattern — Supabase Storage `create_signed_upload_url`, owner-scoped). **`disputes` (0007) has `evidence_paths text[]`** — a not-delivered report creates a dispute with the uploaded paths. **`config.toml` change is untestable locally (affects `supabase db start`)** — CI validates it; you are the **sole `config.toml` editor this wave**.
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P06. Report routing: **faulty/wrong → returns lane 1 (M09-P07, later — record the intent + guidance)**; **not-delivered → dispute (disputes table)**; **other → support**.

## 2. Objective & scope

Confirm-received (→ Completed + escrow release, idempotent) + report-problem (guided triage: faulty/wrong → lane-1 intent; not-delivered → dispute; other → support) with **evidence upload to a private bucket** (RLS-scoped). Within a 48h window, faulty/wrong routes to lane-1; after → guidance.
**Non-goals:** no release engine (M08-P08 — call/stub), no returns lane logic (M09-P07), no dispute console (M13-P05), no db.ts change.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/account/orders/[id]/_components/{confirm-received,report-problem}.tsx` · `services/api/app/routers/order_confirmation.py` (confirm + report + evidence sign) · `services/api/tests/test_order_confirmation.py`
- **Modify:** `packages/i18n/messages/en/orders.json` (append confirm/report keys) · `supabase/config.toml` (add the private `order-evidence` bucket — sole config.toml editor)
  **Guardrail: nothing else. Do NOT touch `account/orders/[id]/page.tsx` or M09-P05's components, `escrow/*` (M08-P08 — call/stub), `orders/state.py`, `kyc_media.py`, `main.py`, schema/db.ts.**

## 4. Implementation spec

- **`order_confirmation.py`** (auth, **owner-scoped**): `POST /orders/{id}/confirm-received` → `transition_order(confirm_received)` → Completed + **fire the release path** (M08-P08). **Idempotent — a double-tap fires release exactly once** (the transition + the ledger idempotency guard). `POST /orders/{id}/report-problem` → guided triage: **faulty/wrong within 48h → lane-1 return intent** (record + guidance; lane-1 execution = M09-P07); **not-delivered → create a `disputes` row** with `evidence_paths`; **other → support**. A **signed-upload endpoint** for evidence → the private `order-evidence` bucket (owner-scoped, mirror `kyc_media.py`). Report after the 48h window → guidance (no auto-lane-1).
- **Components:** `confirm-received.tsx` (confirm button + escrow-release trust copy, disabled after confirm) + `report-problem.tsx` (triage form + evidence upload). All copy via `orders` (`confirm.*`/`report.*`); 360px.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; owner-scoped (other customer → 404); **confirm idempotent (double-tap → one release)**; evidence in a PRIVATE bucket (RLS, owner-scoped signed upload); 48h window enforced; no secrets.

## 10. Tests (RUN before reporting)

`test_order_confirmation.py`: **double-confirm idempotency** (two taps → Completed once, release fired once); **48h window boundary** (within → lane-1 routing; after → guidance); **triage routing** (faulty/wrong → lane-1 intent, not-delivered → dispute row, other → support); evidence sign owner-scoped. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Confirm fires release exactly once (idempotent double-tap); report within 48h → lane-1, after → guidance; triage routes correctly.
- [ ] Evidence stored private (RLS, owner-scoped signed upload); `order-evidence` bucket added to `config.toml` (sole editor); `orders.confirm.*`/`report.*` nested; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P06 — Confirm-received & report-problem
**STATUS/FILES/DEVIATIONS** (note whether M08-P08 release was merged or stubbed + the evidence bucket) **/TESTS** (paste double-confirm + 48h-window + triage-routing + full-pytest tail) **/EXCERPTS** the idempotent confirm→release + the triage routing — nothing else **/QUESTIONS**
