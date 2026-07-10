> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — `refunds` table exists. Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P10 — Refunds & clawbacks

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **NO Lenco refunds API** — a refund = a **payout to the customer's MoMo** + balancing ledger postings (D17). **`refunds` (0006):** `(id, order_id, lane in (1,2), amount_ngwee, status, payout_ref → payouts)`. Ledger merged (M08-P05): **`refund_lane1(*, refund_ngwee)` / `refund_lane2(*, refund_ngwee)` + `clawback` templates** — call `post_transaction`; templates are the only write path. Accounts: `escrow`, `vendor_payable`, `platform_cash`.
- **⚙ Same-wave siblings:** refund execution goes out as a **payout via M08-P09** (sibling) / the M08-P01 strategy — code against the payout interface; **if M08-P09 unmerged, stub the payout leg behind a thin local interface + `TODO(M08-P09)`** and unit-test the refund math + ledger independently.
- **Pre-release vs post-release:** a **pre-release** refund comes **from escrow**; a **post-release** refund creates a **vendor clawback balance** (a negative `vendor_payable`) **netted from the vendor's next payouts**. **Lane-2 math (D17): `item − outbound delivery − return transport − restocking fee`**; restocking fee from `platform_config` (`restocking_fee_bps`, **default 1000 = 10%**, clamp 500–1500) — if the key is absent use the default + note it. Money = int **ngwee**, integer math (no float).
- `app/services/` implicit namespace — create `refunds/` with own `__init__.py`. Router auto-discovers (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P10. Admin/dispute-triggered.

## 2. Objective & scope

Refunds (**lane-1 full incl. delivery**; **lane-2 computed = item − outbound delivery − return transport − restocking fee**) executed as **payouts to the customer** with balancing postings; **pre-release from escrow, post-release via vendor clawback** netted from future payouts; idempotent, double-execution-guarded.
**Non-goals:** no returns UI/lane logic (M09-P07), no dispute UI (M13-P05), no payout engine internals (M08-P09 — call), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/refunds/__init__.py` · `refunds/*.py` (lane-1/lane-2 math, pre/post-release routing, clawback netting) · `services/api/app/routers/refunds.py` (admin/dispute-triggered) · `services/api/tests/test_refunds.py`
  **Guardrail: nothing else. Do NOT touch `app/services/ledger/*` (M08-P05 — call), `payouts/*` (M08-P09 — call/stub), `escrow/*` (M08-P08), `0006`, `main.py`, schema.**

## 4. Implementation spec

- **Lane-1 (full):** refund the full amount **including delivery**. **Lane-2 (computed):** `refund = item_ngwee − outbound_delivery_ngwee − return_transport_ngwee − restocking_fee` where `restocking_fee = floor(item_ngwee × restocking_fee_bps / 10000)` (config, default 1000 bps). **Integer-exact, no float**; never negative (clamp ≥ 0).
- **Routing:** **pre-release** (escrow still holds the funds) → refund posted from `escrow` (`refund_lane1/2` template) + payout to customer. **Post-release** (already paid to vendor) → create a **vendor clawback** (`clawback` template → negative `vendor_payable`) + refund the customer; the clawback is **netted from the vendor's next payout(s)** — support **partial netting across multiple future payouts** until the clawback balance clears.
- **Execution + idempotency:** create a `refunds` row; the customer refund goes out as a **payout (M08-P09)** with an idempotent `rfd-*`-derived reference; **double-execution guard** (a refund executes once — re-trigger returns the existing refund, no double payout).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; lane math integer-exact (no float); templates-only writes; refund idempotent; clawback nets correctly; no secrets. **F9b for live payout.**

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_refunds.py`: **lane-2 fee matrix** (min/max restocking config → ngwee-exact per D17); **pre vs post-release paths** (escrow vs clawback); **partial clawback across 3 payouts** (nets down to zero, no over-claw); **double-execution guard** (re-trigger → one refund, no double payout). **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Lane-2 math ngwee-exact per D17 (restocking min/max); clawback nets correctly across multiple future payouts (no over-claw); refund idempotent.
- [ ] Pre-release from escrow vs post-release clawback routed correctly; templates-only writes; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P10 — Refunds & clawbacks
**STATUS/FILES/DEVIATIONS** (note whether M08-P09 payout was merged or stubbed + the restocking config fallback) **/TESTS** (paste lane-2-matrix + pre/post-release + partial-clawback + double-exec-guard + full-pytest tail) **/EXCERPTS** the lane-2 math + clawback netting — nothing else **/QUESTIONS**
