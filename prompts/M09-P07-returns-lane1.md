> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M09-P07 — Returns lane 1 (faulty/wrong)

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **`returns` table EXISTS (0007_trust_ops.sql:57)** — columns: `order_item_id uuid`, `lane int check (1,2)`, `evidence_paths text[]`, `fee_breakdown jsonb`, `status text check ('requested','approved','rejected','completed')`. **No migration needed** — you write to this table via the service role. RLS already isolates customer/vendor/admin (customer selects/inserts own order-item; vendor reads own listing; admin all).
- **Report-problem entry EXISTS (M09-P06, merged `order_confirmation.py`):** faulty/wrong within 48h records a **lane-1 return intent** (`event_type="lane1-return-intent"`) + guidance — **it does NOT create the return row.** You own the actual return **submission** (evidence-mandatory) via the customer return page → your `returns.py` endpoint. **Do NOT edit `order_confirmation.py`** (M09-P09 owns the sole edit to it this wave).
- **Evidence → the private `order-evidence` bucket** (added by M09-P06). Reuse the merged `POST /orders/{id}/evidence/sign` signed-upload endpoint pattern — evidence paths are passed into your return submission. **Return submit is BLOCKED without ≥1 evidence path.**
- **48h window:** report/return allowed ≤48h of `Delivered`. Reuse the delivered-at lookup convention from `order_confirmation.py` (order_events / order timestamp).
- **Refund composition (lane 1) = full: item + delivery**, sourced from escrow via **M08-P10 lane-1** (`refunds/execute.py` merged). Return shipping is **charged to the vendor** (ledger entry). **⚙ Same-wave note:** you record the return + vendor accept/contest + (on accept) trigger the lane-1 refund via the merged M08-P10 path; **contest → admin dispute queue** (a `disputes` row / arbitration flag — reuse the disputes table, status `open`).
- **⚙ Lane-2 seam (M09-P08, parallel):** your `returns.py` router exposes BOTH lanes; the **lane-2 branch imports `app.services.returns.lane2`** — guard with `importlib.import_module` + `TODO(M09-P08)` and skip cleanly if unmerged (unit-test lane-1 independently). M09-P08 owns `lane2.py` + the returnable badge only.
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P07.

## 2. Objective & scope

Customer files a faulty/wrong return ≤48h of delivery **with mandatory photo evidence** → `returns` row (lane 1) → **vendor notified (accept/contest)** → on accept, **full refund (item + delivery) from escrow** via M08-P10 lane 1 + return-shipping ledger charge to vendor; **contest → admin dispute/arbitration**.
**Non-goals:** no lane-2 fee math (M09-P08 — call/stub `lane2.py`), no disputes console (M13-P05, W14), no `order_confirmation.py` edit, no refund-engine internals (M08-P10 — call the merged path).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/returns/lane1.py` (return record + window/evidence gate + accept→refund composition + contest→arbitration) · `services/api/app/routers/returns.py` (customer submit + vendor respond; lane-2 branch stubs `lane2`) · `apps/customer/app/[locale]/account/orders/[id]/return/page.tsx` (evidence-mandatory return form; renders BOTH lane branches — lane-2 UI reads eligibility from the API) · `apps/vendor/app/[locale]/returns/page.tsx` (vendor accept/contest queue) · `services/api/tests/test_returns_lane1.py`
- **Modify (APPEND-RULE — add ONLY your disjoint nested section; rebase & re-append on conflict, never remove others'):** `packages/i18n/messages/en/orders.json` (append `orders.return.*` — customer return flow) · `packages/i18n/messages/en/vendor.json` (append `vendor.returns.*` — vendor queue)
  **Guardrail: nothing else. Do NOT touch `order_confirmation.py`, `escrow/*`, `refunds/*` internals (call the merged M08-P10 path), `returns/lane2.py` (M09-P08 — import/stub), `main.py`, schema/db.ts, `orders/state.py`.**

## 4. Implementation spec

- **`lane1.py`:** `create_lane1_return(service_client, *, order_item_id, customer_id, evidence_paths)` — assert ≤48h of Delivered + `len(evidence_paths) >= 1` (else uniform-envelope 400) + owner-scoped; insert `returns` row `lane=1, status='requested'`, `evidence_paths`, `fee_breakdown` = `{"item_ngwee":…, "delivery_ngwee":…, "total_ngwee":…, "return_shipping_charged_to":"vendor"}` (integer ngwee only). Vendor **accept** → `status='approved'` → invoke **M08-P10 lane-1 refund** (full item+delivery from escrow) + **ledger charge of return shipping to vendor** (via the merged ledger post path); vendor **contest** → open an admin **arbitration** (`disputes` row `status='open'` linked to the order) — no auto-refund. Escrow-vs-clawback **source selection** = defer to M08-P10 (it picks escrow if held, clawback if already released).
- **`returns.py`** (auth, owner/vendor-scoped): `POST /returns` (customer submit — lane in body; lane 1 → `lane1.py`; lane 2 → stubbed `lane2.py`); `POST /returns/{id}/respond` (vendor accept|contest, ownership-gated). Uniform error envelope; rate-limited.
- **Pages:** return form (evidence upload to `order-evidence`, submit disabled until ≥1 photo + refund-breakdown preview shown before commit); vendor queue = big-button accept/contest, 360px. All copy via `orders`/`vendor` keys.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; evidence MANDATORY (submit blocked without); owner-scoped (other customer → 404, vendor B cannot act on vendor A's return — authz test); refund breakdown ngwee-exact (item+delivery, **no float**); private evidence bucket (RLS); 48h window enforced server-side; no secrets.

## 10. Tests (RUN before reporting)

`test_returns_lane1.py`: **window enforcement** (47h59m ok / 48h01m blocked); **evidence gate** (0 photos → blocked); **refund composition** = item + delivery exactly (ngwee goldens); **vendor accept → M08-P10 lane-1 invoked** (spy) + return-shipping ledger charge; **vendor contest → arbitration/dispute row**; **escrow-vs-clawback source** left to M08-P10 (assert the call, not the internals); authz (cross-customer, cross-vendor). Note whether `lane2` was merged or stubbed. `pnpm --filter customer build && pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Evidence required (submit blocked without); refund breakdown = item + delivery exactly; contest lands in admin dispute/arbitration queue; accept fires M08-P10 lane-1 + vendor return-shipping ledger charge.
- [ ] `orders.return.*` + `vendor.returns.*` appended (disjoint, append-rule); lane-2 branch import-guarded; full API suite + 3 app builds green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P07 — Returns lane 1 (faulty/wrong)
**STATUS/FILES/DEVIATIONS** (note whether `lane2` was merged or stubbed; how M08-P10 lane-1 + return-shipping ledger were invoked) **/TESTS** (paste window + evidence-gate + refund-composition + accept→M08-P10 + contest→dispute + full-pytest tail) **/EXCERPTS** the return-creation gate + accept→refund composition — nothing else **/QUESTIONS**
