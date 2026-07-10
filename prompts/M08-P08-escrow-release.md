> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — no migration (config windows + ledger accounts exist). Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P08 — Escrow release rules engine

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **Ledger merged (M08-P05):** post via `app.services.ledger` `post_transaction(*, idempotency_key, template, order_id=None, …, **args)` with the **existing `release_to_vendor(*, net_ngwee, vendor_id)`** template — **release credits `vendor_payable(vendor)`, debits `escrow`**. Accounts (0006): `escrow`, `vendor_payable`(per-vendor), `platform_cash`, `commission_revenue`. **Templates are the ONLY write path** — never ad-hoc postings.
- **Order states merged (M09-P01):** read `orders.status` + `order_events` timing; release windows from **`platform_config`: `release_after_delivered_hours`=48, `release_after_shipped_days`=7** (D5). **Disputes merged (0007):** an **open `disputes` row for the order blocks release** (hold beats every timer).
- `app/services/` implicit namespace — create `escrow/` with its **own `__init__.py`**; **no `app/services/__init__.py`**. The release job router auto-discovers (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Money = int **ngwee** (no float).
- **⚙ Same-wave edge:** release **enqueues payout eligibility** consumed by **M08-P09 (payouts)** — signal via the ledger (`vendor_payable` credit = eligible balance) + optionally an outbox/marker; do NOT build payouts here. **M09-P06 (confirm-received) calls YOUR release path** — expose a clean `evaluate_and_release(order_id)` interface.
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P08. Event-escrow timing (T+24h / 50-50) is **consumed by M10-P08** — leave the rule hooks but do not build event payout scheduling.

## 2. Objective & scope

Rule evaluation for escrow release: **buyer-confirm** / **48h-after-delivered auto** / **7d-after-shipped fallback** / **dispute-hold**; each release posts the `release_to_vendor` ledger template **exactly once** and marks payout eligibility; a re-runnable idempotent job. Windows read from config (change without deploy). **Dispute-open beats every timer.**
**Non-goals:** no payouts (M08-P09), no refunds (M08-P10), no event payout scheduling (M10-P08), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/escrow/__init__.py` · `escrow/release.py` (rule engine + `evaluate_and_release`) · `services/api/app/routers/internal_release_job.py` (internal-token-guarded tick) · `infra/n8n/release-job.json` · `services/api/tests/test_release.py`
  **Guardrail: nothing else. Do NOT touch `app/services/ledger/*` (M08-P05 — call), `payouts/*` (M08-P09), `orders/state.py`, `0006`/`0007`/`0008`, `main.py`, schema.**

## 4. Implementation spec

- **`release.py`:** for an order, evaluate the rules in priority order: **(1) an open dispute → HOLD** (no release, return held); (2) **buyer-confirm** (order Completed via confirm-received) → release now; (3) **delivered + ≥ `release_after_delivered_hours`** → auto-release; (4) **shipped + ≥ `release_after_shipped_days`** (fallback) → release. Windows read live from `platform_config`. A release = **one** `post_transaction(idempotency_key=f"release-{order_id}", template=release_to_vendor, order_id=..., net_ngwee=<order net after commission>, vendor_id=...)` — the idempotency key guarantees **exactly one release posting per order** even under job overlap. Compute `net_ngwee` = order amount − commission (from `orders.commission_snapshot`, integer math). Mark payout eligibility (the `vendor_payable` credit is the eligible balance).
- **Release job (`internal_release_job.py` + `release-job.json`):** internal-only tick that sweeps release-eligible orders and calls `evaluate_and_release`; **idempotent under re-run/overlap** (the ledger idempotency key + a status guard prevent double-release).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; templates = only write path; dispute-hold absolute; idempotent (one posting per order); windows config-driven; job internal-only; no float; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_release.py`: **timer matrix** (buyer-confirm early / auto-48h-after-delivered / 7d-after-shipped fallback → each produces **exactly one** release posting); **dispute interleavings** (open dispute → HOLD beats every timer; resolve → release resumes); **double-run idempotency** (overlapping job ticks → still one posting); **config window change respected** (shorten the window → release fires). **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Each rule path produces **exactly one** release posting; dispute-hold beats every timer; config window change respected without deploy.
- [ ] Release marks payout eligibility (vendor_payable credit); job idempotent under re-run/overlap; net = amount − commission (integer-exact).
- [ ] Templates-only writes (no ad-hoc postings); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P08 — Escrow release rules engine
**STATUS/FILES/DEVIATIONS** (note how payout eligibility is signalled to M08-P09) **/TESTS** (paste timer-matrix + dispute-hold + double-run-idempotency + full-pytest tail) **/EXCERPTS** the rule-priority evaluation + the idempotent release post — nothing else **/QUESTIONS**
