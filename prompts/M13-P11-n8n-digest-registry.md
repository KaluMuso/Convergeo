> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 16 (parallel). **Touch ONLY your files below.** **⚠ You are the SOLE Wave-16 editor of `docs/ops/n8n-workflows.md`.** **Run the FULL `uv run pytest` before reporting.**

# M13-P11 — n8n admin hooks & daily digest

## 1. Context

**Grounded against as-built `master` (internal-token tick pattern + many n8n workflows MERGED):**

- **Internal-token pattern** (mirror exactly): `services/api/app/routers/internal_order_jobs.py` — env-var token, `X-Internal-Token` header guard, `AppError(401)` on mismatch. Use a distinct env var (e.g. `INTERNAL_DIGEST_TOKEN`).
- **n8n JSON shape** (mirror): `infra/n8n/tickets-release.json` (scheduleTrigger + HTTP POST to `{{$env.API_URL}}/internal/...` with `X-Internal-Token` via `genericCredentialType`/`httpHeaderAuth`).
- **Existing n8n workflows to register:** `ls infra/n8n/*.json` — includes abandoned-cart, embeddings-cron, funnel-abandon, kyc-nudge, low-stock-alert, notification-dispatch, order-jobs, payment-sweeper, tickets-issue, tickets-release, event-release (+ your new admin-digest). The registry doc must list **every** `infra/n8n/*.json`.
- **Digest data** = founder morning view: GMV, orders, payouts due, reconciliation status, KYC queue depth, flags pending — ledger/orders-derived.
  Spec: `docs/plan/02-pebbles/M13-admin-merchandising.md` §M13-P11.

## 2. Objective & scope

A daily founder digest (WhatsApp/email via n8n) backed by an internal-token digest data endpoint, plus `docs/ops/n8n-workflows.md` — the complete registry of every n8n workflow (ownership + schedule table), with a completeness check.
**Non-goals:** no dashboard UI change (M13-P09), no notification-adapter change, no new money logic (read-only aggregates), no migration.

## 3. Files (create/modify ONLY these)

- **Create:** `infra/n8n/admin-digest.json` (daily schedule → POST the digest endpoint → WhatsApp/email) · `services/api/app/routers/internal_digest.py` (`POST /internal/digest` or `GET` internal-token: returns GMV, orders, payouts-due, reconciliation status, KYC queue depth, flags pending) · `docs/ops/n8n-workflows.md` (registry: every `infra/n8n/*.json` with owner + schedule + purpose) · `services/api/tests/test_internal_digest.py` · `services/api/tests/test_n8n_registry.py` (completeness: every `infra/n8n/*.json` appears in `n8n-workflows.md`)
  **Guardrail: nothing else. Do NOT edit other `infra/n8n/*.json`, `internal_order_jobs.py`, dashboards, `main.py`, db.ts, ci.yml (M06-P05 owns it), migrations.**

## 4. Implementation spec

- **`internal_digest.py`** (internal-token guard, mirror `internal_order_jobs.py` with a distinct env var): return the digest aggregates — GMV (ledger/orders), order counts by status, payouts due (payouts pending), reconciliation status (latest reconciliation report), KYC queue depth (pending kyc_records), flags pending. Read-only. Non-token → 401.
- **`admin-digest.json`:** daily scheduleTrigger (e.g. 06:00) → HTTP POST `{{$env.API_URL}}/internal/digest` with `X-Internal-Token` → format → WhatsApp/email node. Mirror the existing n8n JSON structure exactly (node ids/names/types).
- **`n8n-workflows.md`:** a table — every workflow file, owner pebble, schedule/trigger, purpose. Include a note on import/export procedure.
- **`test_n8n_registry.py`:** globs `infra/n8n/*.json`, asserts each filename is referenced in `n8n-workflows.md` (this is the completeness CI check — a plain pytest, no live n8n).

## 5–9. Security etc.

Internal-token guarded (distinct env var, not publicly callable); read-only aggregates; numbers match the dashboard truth; no secrets in the n8n JSON (token via `{{$env}}`); registry completeness enforced by test.

## 10. Tests (RUN before reporting)

`test_internal_digest.py`: digest aggregates correct vs fixtures + token auth (401 without token). `test_n8n_registry.py`: every `infra/n8n/*.json` listed in the registry doc (fails if a workflow is undocumented). Full `uv run pytest`, `uv run ruff check .`, `uv run mypy .`.

## 11. Acceptance criteria / DoD

- [ ] Digest returns real numbers matching dashboard truth; token-guarded; registry lists **every** `infra/n8n/*.json` (completeness test passes).
- [ ] No other n8n file touched; full API suite green; ruff/mypy clean.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M13-P11 — n8n admin hooks & daily digest
**STATUS/FILES/DEVIATIONS** (digest aggregate sources; the token guard env var; the registry completeness-test approach) **/TESTS** (paste digest-auth + aggregate + registry-completeness + full-pytest tail) **/EXCERPTS** the digest aggregate query + internal-token guard — nothing else **/QUESTIONS**
