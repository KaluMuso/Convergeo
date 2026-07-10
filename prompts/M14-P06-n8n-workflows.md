> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M14-P06 — n8n operational workflows

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **Principle: logic stays in the API; n8n = scheduling/glue only** (solo-ops maintainability). Each workflow just calls an **API data endpoint** you create in `internal_n8n.py` and forwards the result to WhatsApp/notification (via the merged notification path).
- **Internal-token auth:** these endpoints are n8n-facing, **not customer-authed** — guard with the internal shared-secret header pattern (secret from env, never in repo or the workflow JSON). Mirror the internal-endpoint convention (see M09-P10's `internal_order_jobs.py` if merged; otherwise a validated `X-Internal-Token` header).
- **Data sources = EXISTING tables** (do **not** depend on M13-P09 dashboards — W14): stalled KYC = `kyc_records`/vendor applications >48h in `pending`; payout failures = `payouts.status='failed'`; low-stock = listings stock/qty fields (catalog); post-completion +24h = orders in `Completed` (for review request). Query these directly; **no migration.**
- **`abandoned-cart.json` ships flag-gated OFF** (inert while the flag is off — the actual abandoned-checkout events are M07-P08, W15). Its data endpoint returns empty / is gated so nothing fires.
- **`payout-failure-alert` → founder WhatsApp**; **`low-stock-alert` → vendor**; **`review-request` → customer +24h post-completion**; **`kyc-nudge` → 48h stalled applicant.**
- **Registry doc:** `docs/ops/n8n-workflows.md` — **you create/own it this wave** (M13-P11 finalizes it in W16, different wave). **Do NOT touch `infra/n8n/order-jobs.json`** (M09-P10 owns it, same dir — disjoint filename).
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P06. **Outbox pattern for any send** (merged M14-P01 dispatcher).

## 2. Objective & scope

Five n8n workflows (`kyc-nudge`, `payout-failure-alert`, `low-stock-alert`, `review-request`, `abandoned-cart` [OFF]) — each **importable + runnable against staging** — backed by **internal-token API data endpoints** (`internal_n8n.py`) querying existing tables, plus the `n8n-workflows.md` registry. Sends go through the merged notification/outbox path.
**Non-goals:** no business logic in n8n (API only), no dashboards (M13-P09), no abandoned-cart events (M07-P08 — flag OFF), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `infra/n8n/kyc-nudge.json` · `infra/n8n/payout-failure-alert.json` · `infra/n8n/low-stock-alert.json` · `infra/n8n/review-request.json` · `infra/n8n/abandoned-cart.json` (flag-gated OFF) · `services/api/app/routers/internal_n8n.py` (internal-token data endpoints per workflow) · `docs/ops/n8n-workflows.md` (registry — create/own) · `services/api/tests/test_internal_n8n.py`
  **Guardrail: nothing else. Do NOT touch `infra/n8n/order-jobs.json` (M09-P10), the notification dispatcher/adapters (M14-P01…P05 — call the merged path), `main.py`, any schema/db.ts. No migration.**

## 4. Implementation spec

- **`internal_n8n.py`** (internal-token guard, uniform envelope): `GET /internal/n8n/kyc-stalled` (applications >48h `pending`), `GET /internal/n8n/payout-failures` (`payouts.status='failed'`, recent), `GET /internal/n8n/low-stock` (listings under threshold), `GET /internal/n8n/review-requests` (orders `Completed` +24h, not already requested), `GET /internal/n8n/abandoned-carts` (**flag-gated → empty while OFF**). Each returns the minimal payload the workflow needs (recipient + template slots); **missing/wrong token → 401/403.** Actual sends use the merged outbox/notification path where applicable.
- **Workflow JSON:** each = schedule/trigger → HTTP call to its endpoint (token via n8n credential/expression, **never inline**) → map to a WhatsApp/notification send. `abandoned-cart.json` disabled/flag-gated so it's inert. Importable against staging.
- **`n8n-workflows.md`:** registry table (workflow, trigger/schedule, endpoint, recipient, on/off, owner-pebble) — the single source M13-P11 will finalize.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Internal endpoints unreachable without the token (secret in env, none in repo/JSON); abandoned-cart inert while flag off; payloads minimal (data frugality); no secrets in workflow JSON.

## 10. Tests (RUN before reporting)

`test_internal_n8n.py`: **endpoint tests per data source** (kyc-stalled/payout-failures/low-stock/review-requests return correct rows from fixtures); **flag gating** (abandoned-cart → empty while OFF); **alert payloads** (payout-failure payload shape for founder WhatsApp); **internal-token guard** (missing/wrong → 401/403). `pnpm typecheck && pnpm lint` (if any TS touched — else API-only), `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Each workflow importable + runs against staging; abandoned-cart inert while flag off; failure alert fires on injected payout failure.
- [ ] Endpoints internal-token-guarded (env secret, none in repo/JSON); `n8n-workflows.md` registry created; no migration; full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M14-P06 — n8n operational workflows
**STATUS/FILES/DEVIATIONS** (note the internal-token mechanism + which existing tables each endpoint queries + how sends reuse the outbox path) **/TESTS** (paste per-endpoint + flag-gating + alert-payload + internal-token + full-pytest tail) **/EXCERPTS** the internal-token guard + one representative data endpoint — nothing else **/QUESTIONS**
