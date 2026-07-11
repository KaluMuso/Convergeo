> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **⚙ CI GATING (M10 lesson):** your DB-backed `test_service_escrow.py` must be **isolation-clean** (seed + tear down your own rows — shared Postgres) and green via `uv run pytest tests/test_service_escrow.py` on a real DB; per-pebble seeding is CI-invisible. **Do NOT edit `.github/workflows/ci.yml`** (converger wires your file into the rls-job blocking step at merge). **Run the FULL `uv run pytest` before reporting.**

# M11-P04 — Accept → deposit & balance via escrow (MONEY-CRITICAL)

## 1. Context

**Grounded against as-built `master` (order/payment/commission/escrow spine MERGED):**

- **Schema is READY — NO migration:** `order_items.item_kind` (0005:82) already allows `'service_deposit'` and `'service_balance'`; `order_item_services` table (0005:110) exists; commission for services is seeded `('services', 1200)` = **12% (1200 bps)** in `commission_rates` (0008:34).
- **Reuse the merged money spine (do NOT reimplement):** commission via `app.services.commissions.engine` (`compute_order_commission`/`capture_order_commission`, snapshot, integer-exact); checkout/payment via M07/M08 (deposit goes through standard checkout → Lenco payment); escrow release via `app.services.escrow.release` (`RELEASE_TO_VENDOR`); ledger via `post_transaction` (sole write path). **Float on money = review-blocking bug.**
- **⚠ COMMISSION SEAM — 12% on TOTAL job value, counted ONCE.** The 12% commission basis is `deposit + balance` (total job value), snapshotted at accept time. It must be captured exactly once across the two legs — NOT 12% on deposit AND again 12% on balance in a way that double-counts. Snapshot the total-job commission at accept; capture proportionally or on the balance leg — document your exact approach and prove single-count in tests.
- **Deposit %** — read from `platform_config` (key e.g. `service_deposit_pct`) with a sensible code default (D2 model) if unset; no migration to seed it (read-with-default like other config reads).
  Spec: `docs/plan/02-pebbles/M11-services-rfq.md` §M11-P04.

## 2. Objective & scope

Accept a quote → create the money spine: a `service_deposit` order item (deposit % of total job value) paid through standard checkout/payment; provider notified; on completion (M11-P05, separate) a `service_balance` item → payment → escrow release. Commission = **12% of total job value, snapshot, counted once**; deposit refundable per dispute rules pre-work; ledger balanced across both legs.
**Non-goals:** no new payment method (reuse M08), no completion flow (M11-P05), no schema migration, no commission-rate change.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/rfq/engagement.py` (accept → order w/ `item_kind='service_deposit'`; deposit % from config+default; total-job commission snapshot; helper to create the `service_balance` item at completion) · `apps/customer/app/[locale]/account/jobs/[id]/_components/accept-flow.tsx` (accept UI → deposit checkout hand-off) · `services/api/app/routers/rfq_engagement.py` (accept endpoint, auth, owner-scoped) if a new router is needed (auto-discovered — do NOT edit `main.py`) · `services/api/tests/test_service_escrow.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/services.json` (append `services.accept.*`) — **you are the sole Wave-16 editor of services.json.**
  **Guardrail: nothing else. Do NOT edit `commissions/engine.py`, `escrow/release.py`, `templates.py`, `purchase.py`, `quotes.py` (M11-P06 owns it this wave), `main.py`, db.ts, migrations.**

## 4. Implementation spec

- **`engagement.py`:** `accept_quote(service_client, *, job_id, quote_id, customer_id)` → validate the job is open + the customer owns it + the quote belongs to the job; compute `deposit_ngwee = round(total_job_ngwee * deposit_pct)` (integer ngwee, `deposit_pct` from config default); **snapshot the full-job commission** (`compute_order_commission` on the total with the `services` rate) into the order's `commission_snapshot`; create an order + `order_item_services` + `service_deposit` order item; hand off to the existing checkout/payment path for the deposit. Provide `create_balance_item(order_id)` for completion (M11-P05) — the `service_balance` item = total − deposit. **Commission is captured once for the total** — do not re-capture on the balance leg; document the exact single-capture point.
- **`accept-flow.tsx`:** accept CTA → confirm deposit amount (`formatK`) → redirect into the deposit checkout. 360px; copy via `services.accept.*`.

## 5–9. Security etc.

Owner-scoped accept (customer owns the job); commission **12% of total, integer-exact, captured once**; deposit through the audited M08 payment path (no ad-hoc money); ledger balanced across deposit + balance legs; snapshot immunity (rate change post-accept doesn't alter the order); rate-limited accept; no float; no secrets.

## 10. Tests (RUN before reporting)

`test_service_escrow.py` (isolation-clean, real DB): **two-leg commission math** (12% of deposit+balance total, captured exactly once — assert total commission == round(total*0.12) and NOT double-counted); **cancellation-after-deposit refund** path (deposit refundable pre-work per dispute rules); **snapshot immunity** (change `commission_rates` after accept → order commission unchanged); deposit = round(total*deposit_pct) integer-exact; owner-authz (non-owner accept → 403). Full `uv run pytest`, `uv run ruff check .`, `uv run mypy .`.

## 11. Acceptance criteria / DoD

- [ ] Commission = 12% of deposit+balance exactly once (proven not double-counted); deposit refundable per dispute rules pre-work; ledger balanced across both legs; snapshot immune to later rate changes.
- [ ] No migration (schema ready); no float; `services.accept.*` appended; full API suite green (or DB tests skip); ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M11-P04 — Accept → deposit & balance via escrow
**STATUS/FILES/DEVIATIONS** (the exact single-capture commission point; deposit%/rounding; how the deposit reuses M08 checkout; balance-item creation) **/TESTS** (paste two-leg-commission + cancel-refund + snapshot-immunity + authz + full-pytest tail) **/EXCERPTS** the full commission-snapshot + single-capture path + deposit/balance ngwee math — nothing else **/QUESTIONS**
