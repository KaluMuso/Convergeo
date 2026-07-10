> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — `webhook_events` already exists. Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M08-P03 — Lenco webhook endpoint

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **`webhook_events` exists (0006):** `(id, provider, event_id text, signature_valid bool, processed_at, raw jsonb)` + **unique `(provider, event_id)`** → **idempotent ingestion is via that unique key** (dup insert → conflict → 200 no-op). **No migration.**
- **Webhook verify already built (M08-P02, merged):** `LencoStrategy.verify_webhook_signature(raw_body, signature, token)` = `HMAC-SHA512(raw_body, key=SHA256(api-token))`. **Reuse it** — you own a thin `webhook_verify.py` that wraps/records, not a re-implementation. Verify on the **RAW body BEFORE JSON parse**.
- Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Add your module to `app/services/payments/` (dir exists) — **do NOT edit `payments/__init__.py`** (import directly).
- **⚙ Same-wave edge — M08-P04 (payment state machine):** you **ingest + store + fast-200**; M08-P04 **consumes stored `webhook_events` rows** to drive payment-state transitions. Decouple via the table: you persist `raw` + mark for processing; do NOT inline heavy domain work. Reference: `docs/ops/lenco/lenco-api-distilled.md`.
  Spec: `docs/plan/02-pebbles/M08-payments-escrow.md` §M08-P03. **Live E2E needs F9b (sandbox creds) — mock/fixture-tested here.**

## 2. Objective & scope

`POST /webhooks/lenco`: HMAC-SHA512 verify on the **raw** body → **idempotent ingest** (`webhook_events.event_id` unique, dup → 200 no-op) → out-of-order tolerance (status-precedence) → **forged/invalid sig → 401 + alert log** → enqueue domain processing (never inline) → **always fast-200 on valid+stored**; raw payload persisted for audit.
**Non-goals:** no payment state machine (M08-P04 — consumes your rows), no ledger posting (M08-P05), no order mutation, no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/webhooks_lenco.py` · `services/api/app/services/payments/webhook_verify.py` (wraps M08-P02's verify + raw-body capture + event_id extraction) · `services/api/tests/test_webhooks.py`
  **Guardrail: nothing else. Do NOT touch `payments/__init__.py`, `payments/lenco/*` (M08-P02 — import), `payments/state.py` (M08-P04), `webhook_events`/`0006`, `main.py`, schema.**

## 4. Implementation spec

- **`webhook_verify.py`:** read the **raw request body** (not the parsed model), verify via M08-P02's `verify_webhook_signature`; extract `event_id`; return a typed verified/failed result. Invalid sig → do NOT parse/act.
- **`webhooks_lenco.py`:** `POST /webhooks/lenco` — (1) verify raw body; forged/invalid → **401 + alert log** (no processing). (2) Insert into `webhook_events` `(provider='lenco', event_id, signature_valid=true, raw)`; **on unique conflict → 200 no-op** (idempotent; already stored). (3) Mark for async domain processing (a `processed_at IS NULL` row M08-P04 will pick up — do NOT inline heavy work). (4) **Fast-200.** **Unknown event type → stored + flagged + 200** (not an error). Out-of-order: rely on M08-P04's status-precedence — you just store faithfully. Malformed JSON on a **sig-valid** body → store raw + flag + 200 (never 500-loop; Lenco retries 30min×24h).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; verify RAW body before parse; secrets env-only; idempotent by `event_id`; forged → 401 + alert; fast-200 (no inline heavy work); raw persisted for audit; no secrets committed.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_webhooks.py`: **duplicate** (same `event_id` twice → one stored, 2nd 200 no-op); **out-of-order** (stored faithfully; precedence deferred to M08-P04); **forged/invalid sig → 401 + alert log, nothing stored/processed**; **replayed** webhook → no double effect; **malformed JSON** on valid sig → stored+flagged+200; **unknown event type → stored+flagged+200**. **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Duplicate / out-of-order / forged / replayed each handled per spec (all tested); raw payload persisted for audit.
- [ ] Sig verified on raw body before parse; idempotent by `event_id`; always fast-200 on valid+stored; no inline heavy work.
- [ ] Reuses M08-P02 verify (no re-impl); no `payments/__init__.py` edit; full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M08-P03 — Lenco webhook endpoint
**STATUS/FILES/DEVIATIONS/TESTS** (paste dup + forged-401 + out-of-order + unknown-type + full-pytest tail) **/EXCERPTS** the raw-body verify + idempotent insert-on-conflict — nothing else **/QUESTIONS** (flag F9b for live)
