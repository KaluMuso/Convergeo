> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — `invoice_counters`/`invoices`/`next_invoice_no` exist. Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P12 — Commission engine & sequential invoicing

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **Gapless numbering already exists (0006):** `invoice_counters(series, next_no)` + **`public.next_invoice_no(p_series text)`** which allocates via `SELECT … FOR UPDATE` (docstring: gapless). `invoices` table exists. **Reuse `next_invoice_no` — do NOT re-implement numbering** (concurrency-safe already). **No migration.**
- **Commission source = the PURCHASE-TIME snapshot** on `orders.commission_snapshot` (M07-P06, merged) — **never live `commission_rates` post-purchase**. `commission_rates(category_key, rate_bps)` (0008) for reference only. **Supplies +3% stacking** per CLAUDE.md (wholesale lines add 3% to the category bps). Money = int **ngwee**, bps→ngwee **integer math** (no float — review-blocking).
- **Ledger merged (M08-P05):** commission capture posts via `app.services.ledger` templates (`commission_capture`) — call it; do NOT post ad-hoc. `app/services/` implicit namespace — create `commissions/` + `invoicing/` each with **own `__init__.py`**; **no `app/services/__init__.py`**. VAT flag **off at launch** (compliant non-VAT invoice) + a documented **VSDC seam stub**. No router (called by the payment-success/completion paths).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P12.

## 2. Objective & scope

Commission engine (bps from snapshot, supplies +3% stacking, integer-exact) + invoicing (**gapless sequential via `next_invoice_no` FOR UPDATE**, receipt on payment success + tax-invoice data on order completion, ZRA-ready fields, VAT-flag aware — off at launch, VSDC seam stub).
**Non-goals:** no PDF render (M15-P07 — payload/data only), no live-config commission (snapshot only), no numbering re-impl, no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/commissions/__init__.py` · `commissions/engine.py` (bps from snapshot + supplies +3% stack; → commission ngwee, integer-exact) · `services/api/app/services/invoicing/__init__.py` · `invoicing/*.py` (allocate number via `next_invoice_no`; receipt + tax-invoice payload builder; VAT-flag aware; VSDC seam stub) · `services/api/tests/test_commissions_invoicing.py`
  **Guardrail: nothing else. Do NOT touch `0006`/`invoice_counters`/`next_invoice_no` (call it), `app/services/ledger/*` (M08-P05 — call), `app/services/__init__.py`, `main.py`, schema.**

## 4. Implementation spec

- **`commissions/engine.py`:** commission per line = `line_total_ngwee × rate_bps / 10000` using **integer math** (document rounding — round half-up or floor, consistently); rate_bps from `orders.commission_snapshot` (purchase-time, immutable); **wholesale/supplies lines add +3% (300 bps)** on top of the category rate. Free events → 0%. Posts `commission_capture` via M08-P05 (or returns the amount for the caller to post — pick one, state it).
- **`invoicing/`:** on **payment success → receipt**; on **order completion → tax-invoice data**. Number via **`next_invoice_no(series)`** (gapless, FOR UPDATE — concurrency-safe). ZRA-ready fields (seller TPIN slot, sequential no, date, line VAT columns). **VAT flag off at launch** → compliant non-VAT invoice; **VSDC seam** = a documented stub function (no live integration). No float on any amount.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; commission integer-exact from snapshot (no float, no live config); numbering gapless under concurrency; VAT-off compliant; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_commissions_invoicing.py`: **concurrent invoice issuance → gapless sequence** (parallel workers, no gaps/dupes — exercise `next_invoice_no` under contention); **commission matrix per D4 categories** (incl. free events 0%, supplies +3% stack) integer-exact; **snapshot immunity** (change `commission_rates` after purchase → commission unchanged); **VAT-off** yields compliant non-VAT invoice. **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Concurrent issuance gapless (parallel-worker test); commission uses purchase-time snapshot; supplies +3% stack correct; free events 0%.
- [ ] Integer-exact (no float); VAT-off compliant invoice + VSDC seam stub; reuses `next_invoice_no` (no re-impl); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P12 — Commission engine & sequential invoicing
**STATUS/FILES/DEVIATIONS** (state commission rounding rule + whether it posts commission_capture or returns it) **/TESTS** (paste gapless-concurrency + commission-matrix + snapshot-immunity + full-pytest tail) **/EXCERPTS** the bps→ngwee integer math + the `next_invoice_no` allocation — nothing else **/QUESTIONS**
