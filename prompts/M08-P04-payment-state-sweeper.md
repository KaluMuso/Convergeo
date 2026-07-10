> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own ONE additive migration `0016` that WIDENS `payments.status` — it does NOT change `db.ts`** (status is typed `string`). Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M08-P04 — Payment state machine & orphan sweeper

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **`payments.status` (0006) currently checks only `('initiated','pending','success','failed','expired')`** — the spec's `created→ussd_pushed→pay_offline→success|failed|expired|cancelled` needs more values. **Add migration `0016_payment_status_states.sql`: drop + re-add the CHECK to the SUPERSET `('initiated','ussd_pushed','pay_offline','success','failed','expired','cancelled')`** (additive/reversible; `initiated`='created'). **`status` is `string` in `db.ts` → NO `db.ts` change, NO drift** (you are NOT a db.ts editor; M09-P03 is). There is **no guard/audit trigger on `payments`** — audit transitions to the generic **`audit_log`** table (0002); do NOT add a payment_events table (would touch db.ts).
- **Webhook ingestion is M08-P03 (same wave):** you **consume stored `webhook_events` rows** (`provider='lenco'`, `processed_at IS NULL`) and apply **status-precedence** (a later `success` after a spurious `failed`; ignore stale). Decouple via the `webhook_events` table (merged 0006) — if M08-P03 unmerged, your tests seed `webhook_events` directly. **Initiate collection** calls M08-P02's `LencoStrategy` (merged) + M08-P01 money converters.
- `app/services/payments/` exists — add `state.py` + `initiate.py`; **do NOT edit `payments/__init__.py`**. Sweeper router auto-discovers (never edit `main.py`). Service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`).
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P04. **Live E2E needs F9b — mock/fixture-tested here.**

## 2. Objective & scope

The payment state machine (guarded transitions `created(initiated)→ussd_pushed→pay_offline→success|failed|expired|cancelled`, every transition audited to `audit_log`), collection kickoff (`initiate.py`), and the **orphan sweeper** that marks stale `pay_offline` **expired — but only after re-querying Lenco** (never blindly) — and releases the order for retry.
**Non-goals:** no webhook endpoint (M08-P03 — consume its rows), no ledger posting (M08-P05), no order state machine (M09-P01), no notifications.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/payments/state.py` (transition table + guarded `transition_payment`; audit to `audit_log`) · `payments/initiate.py` (collection kickoff for an order/checkout_group via M08-P02) · `services/api/app/routers/internal_payment_sweeper.py` (internal-only sweeper tick) · `infra/n8n/payment-sweeper.json` (n8n schedule → the sweeper) · `services/api/tests/test_payment_state.py` · `supabase/migrations/0016_payment_status_states.sql`
  **Guardrail: nothing else. Do NOT touch `payments/__init__.py`, `payments/lenco/*`/`base.py`/`money.py` (import), `webhooks_lenco.py` (M08-P03), `0006`, `db.ts`, `main.py`, other tables.**

## 4. Implementation spec

- **`state.py`:** declarative transition table `(from, event) → to`; illegal transitions **raise**; every transition writes an `audit_log` row (actor/system + from + to + note). Processing a `webhook_events` row applies **status-precedence** (success is terminal-winning; a `failed`/`expired` does not override a prior/later `success` — document the precedence). Guarded via service role.
- **`initiate.py`:** start a collection for an order/checkout_group — creates the `payments` row (`initiated`), calls M08-P02 `initiate_collection` (rail from the chosen method; amount via M08-P01 `ngwee_to_major_str`), moves to `ussd_pushed`. No float.
- **Sweeper (`internal_payment_sweeper.py` + `payment-sweeper.json`):** on tick, find stale `pay_offline`/`ussd_pushed` past TTL → **re-query Lenco status (M08-P02 `query_status`) FIRST**; only if still unpaid → `expired` + release the order for retry; if Lenco now says `success` → the **late-success reconciliation path** (transition to `success`, don't expire). Internal-only (not public). **The orphaned-state risk (mountain's biggest) is closed by re-query-before-expire.**

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; transitions guarded + audited; sweeper re-queries before expiring (no blind expiry); sweeper internal-only; `Decimal`/int money; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_payment_state.py`: **full transition table** (every legal transition; every illegal → raises); **sweeper re-query behavior** (stale + Lenco-still-unpaid → expired + released; stale + Lenco-now-success → success, NOT expired = late-success reconciliation); **status-precedence** (late `success` after `failed` wins; stale event ignored); collection kickoff moves `initiated→ussd_pushed`. Confirm `0016` replays clean + `db.ts` unchanged (no drift). **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Full transition table legal/illegal enforced; every transition audited to `audit_log`.
- [ ] Sweeper re-queries Lenco before expiring; **late-success reconciliation** handled (success-after-expiry); orphaned states closed.
- [ ] `0016` additive/reversible, **`db.ts` unchanged**; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P04 — Payment state machine & orphan sweeper
**STATUS/FILES/DEVIATIONS** (confirm `0016` widens the check + db.ts untouched) **/TESTS** (paste transition-table + sweeper-requery + late-success + full-pytest tail) **/EXCERPTS** the sweeper re-query-before-expire + status-precedence — nothing else **/QUESTIONS** (flag F9b for live)
