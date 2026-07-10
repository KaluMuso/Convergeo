> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own ONE additive migration `0018` + you are the SOLE `db.ts` editor this wave.** Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P07 — Reconciliation poller & daily report

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **Mandatory per the Lenco distilled doc** — the poller closes webhook gaps. **Payment states merged (M08-P04):** re-query non-terminal `payments` via **M08-P04's transitions (never raw updates)**; Lenco status via **M08-P02 `query_status`**. **Ledger merged (M08-P05):** the daily report diffs **Lenco balance/transactions vs the ledger** (ngwee-exact). `webhook_events` (0006) for gap detection.
- **No reconciliation-report table exists** → add **`0018_reconciliation_reports.sql`**: `reconciliation_reports(id, report_date date, summary jsonb, discrepancies jsonb, created_at)` (RLS service-role/admin read). **You are the SOLE `db.ts` editor this wave** — hand-add the new table to `packages/types/src/db.ts` (CI `db` job validates drift). Additive/reversible.
- `app/services/payments/` exists — add **`reconcile.py`** (new file; do NOT edit `payments/__init__.py`/`state.py`). Router auto-discovers (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Report surfaced to M13 dashboard + founder digest (persisted rows).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P07. **This is the integration net for the whole payment wave. Live E2E needs F9b — mock/fixture-tested here.**

## 2. Objective & scope

The **30-min poller** (re-query non-terminal payments → drive them terminal via M08-P04, closing lost-webhook gaps) + the **daily reconciliation report** (Lenco balance/transactions vs ledger: ngwee-exact diff, orphaned-Lenco txns, ledger-only txns) persisted to `reconciliation_reports` + surfaced.
**Non-goals:** no webhook endpoint (M08-P03), no state machine (M08-P04 — use it), no dashboard UI (M13), no schema beyond `0018`.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/payments/reconcile.py` (poll + report) · `services/api/app/routers/internal_reconciliation.py` (internal-token-guarded: 30-min poll tick + daily report trigger) · `infra/n8n/reconciliation.json` · `services/api/tests/test_reconcile.py` · `supabase/migrations/0018_reconciliation_reports.sql`
- **Modify:** `packages/types/src/db.ts` (add `reconciliation_reports` — sole db.ts editor this wave)
  **Guardrail: nothing else. Do NOT touch `payments/__init__.py`/`state.py` (M08-P04 — call), `payments/lenco/*` (M08-P02 — call), `app/services/ledger/*`, `main.py`, other tables.**

## 4. Implementation spec

- **Poller (30-min):** find `payments` in non-terminal states (initiated/ussd_pushed/pay_offline/pending) past a threshold; **re-query Lenco (`query_status`)** and apply the result **through M08-P04's `transition_payment`** (never a raw UPDATE) — a lost `success` webhook is completed by the poller. **Idempotent re-run.**
- **Daily report:** compare Lenco balance + transaction list against the ledger for the day: **ngwee-exact diff**, **orphaned Lenco txns** (in Lenco, not in ledger), **ledger-only txns** (in ledger, not in Lenco). Persist a `reconciliation_reports` row (`summary` + `discrepancies` jsonb). A clean day → zero discrepancies.
- **Router:** internal-token-guarded tick(s); not publicly callable.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; poller uses state-machine transitions (never raw updates); report ngwee-exact; internal-only; `0018` RLS service-role/admin; no secrets. **F9b for live.**

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_reconcile.py`: **gap-closing** (a payment stuck non-terminal + Lenco says success → poller completes it via M08-P04); **mismatch detection** (injected fixture discrepancy → flagged in the report: orphaned/ledger-only/ngwee diff); **idempotent re-run** (poller + report re-run → no double effect, stable report). Confirm `0018` replays clean + `db.ts` matches gen-types. **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Injected mismatch flagged in the report; poller closes webhook gaps via M08-P04 transitions (never raw updates); report matches to the ngwee.
- [ ] Poller + report idempotent on re-run; `0018` additive/reversible, `db.ts` matches (sole editor); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P07 — Reconciliation poller & daily report
**STATUS/FILES/DEVIATIONS** (confirm `0018` + db.ts hand-update) **/TESTS** (paste gap-closing + mismatch-detection + idempotent-rerun + full-pytest tail) **/EXCERPTS** the poller re-query→transition + the report diff — nothing else **/QUESTIONS** (flag F9b)
