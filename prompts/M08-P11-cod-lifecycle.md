> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P11 — COD lifecycle

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **Ledger merged (M08-P05):** post via `post_transaction` with the **existing `cod_collected` template** + `commission_capture`; account **`cod_receivable`(per-vendor)** (0006) holds the order-time receivable. Order creation merged (M07-P06): a **COD order has `orders.cod = true`** and flows the **SAME ledger + commission pipeline** as prepaid — it just **skips Lenco**.
- **Cap ≤K500 re-enforced server-side at order creation** from `platform_config.cod_cap_ngwee` (already enforced in M07-P05/P06 — you re-assert it in the COD confirm path is NOT needed; the cap is at order time). Commission from `orders.commission_snapshot` (purchase-time). Money = int **ngwee** (no float).
- `app/services/payments/` exists — add **`cod.py`** (new file; **do NOT edit `payments/__init__.py`** / `state.py`). Router auto-discovers (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Confirm-collection is **admin/vendor**-scoped.
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P11.

## 2. Objective & scope

COD ledger lifecycle: **order-time `cod_receivable` postings**; **delivery-collection confirmation → cash-collected postings + commission capture**; **vendor-remit vs platform-collect reconciliation entries**; **uncollected/refused-delivery → order cancelled + receivable reversed**. COD flows the same ledger+commission pipeline as prepaid (skips Lenco).
**Non-goals:** no order creation (M07-P06 — sets `cod=true`), no Lenco (COD skips it), no refunds (M08-P10), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/payments/cod.py` (receivable + collection + reversal postings) · `services/api/app/routers/cod.py` (admin/vendor confirm-collection endpoints) · `services/api/tests/test_cod.py`
  **Guardrail: nothing else. Do NOT touch `payments/__init__.py`/`state.py` (call), `app/services/ledger/*` (M08-P05 — call), `app/services/commissions/*` (M08-P12 — call), `0006`/`0008`, `main.py`, schema.**

## 4. Implementation spec

- **`cod.py`:** on a COD order (`cod=true`), the order-time posting records a **`cod_receivable`** for the collectable amount. **On collection confirmation** (delivery): post **cash-collected** (`cod_collected` template) + **capture commission** (via M08-P12) — the platform's commission from the collected cash; the vendor keeps the remainder (vendor-remit vs platform-collect reconciliation entries — document which side holds the cash). **Refused/uncollected delivery → the order is cancelled and the `cod_receivable` is reversed** (balancing postings, no dangling receivable). All idempotent (confirm once; the ledger idempotency key guards double-collection). Integer ngwee, no float.
- **`cod.py` router** (`require_role('vendor')`/`require_role('admin')` + ownership): confirm-collection endpoint(s) that drive the collection postings. **The K500 cap is enforced at order time (M07-P05/P06)** — do not re-open the order; just handle the COD money lifecycle.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; templates-only writes; collection idempotent (one confirm); reversal clean (no dangling receivable); commission integer-exact; scoped confirm; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_cod.py`: **collection-confirm postings** (cash-collected + commission captured, balances Σ=0); **refusal reversal** (receivable reversed cleanly, order cancelled); **commission math** (integer-exact from snapshot); **double-confirm idempotency** (one collection). (Cap enforcement lives at order creation — reference, don't duplicate.) **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] COD commission captured on collection confirmation; refused-delivery reverses the receivable cleanly (order cancelled); collection idempotent.
- [ ] COD flows the same ledger + commission pipeline as prepaid (skips Lenco); templates-only writes; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P11 — COD lifecycle
**STATUS/FILES/DEVIATIONS** (note the vendor-remit vs platform-collect side that holds cash) **/TESTS** (paste collection-postings + refusal-reversal + commission + double-confirm + full-pytest tail) **/EXCERPTS** the collection postings + the reversal — nothing else **/QUESTIONS**
