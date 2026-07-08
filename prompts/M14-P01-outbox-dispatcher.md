> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 6 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN — no migration** (the outbox table exists). Stay dep-free (`httpx` available).

# M14-P01 — Outbox dispatcher & channel adapter interface

## 1. Context

**Wave 6 (parallel ×8).** Grounded against as-built `master` — **use the existing table, no migration:**

- **`public.notification_outbox`** (`0007`): `id, dedupe_key text NOT NULL UNIQUE, channel text check in ('whatsapp','sms','email'), template text, payload jsonb, status text check in ('pending','sent','failed') default 'pending', attempts int default 0, next_retry_at timestamptz, created_at, updated_at`; index `(status, next_retry_at)`. **Service-role only** (zero client policies) — read/write via `app/supabase_client.py` (the ONE service-role module).
- API: routers auto-discover (never edit `main.py`); error envelope standard. **`app/services/` does NOT exist** — create `app/services/notifications/` (own `__init__.py`); **do NOT create `app/services/__init__.py`** (implicit namespace package; siblings added in parallel).
- **Scope:** the dispatcher + the **adapter _interface_ (protocol)** only. The WhatsApp/SMS/email adapter _implementations_ are later pebbles (M14-P02/P04) — ship a `base.py` protocol + a trivial no-op/log adapter for tests.
- Recipient channel preference comes from customer prefs (M04-P05, same wave) — read defensively (fall back to a default order whatsapp→sms→email if prefs absent).
- `infra/n8n/` may not exist — create it for your workflow JSON (you are its only W6 toucher).
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P01.

## 2. Objective & scope

An at-least-once outbox dispatcher with idempotent (exactly-once-per-event-per-channel) send, per-channel pacing, retry backoff + dead-letter, and a channel-adapter protocol.
**Non-goals:** no real WhatsApp/SMS/email adapters (M14-P02/P04 — protocol + no-op only), no new schema, no admin dead-letter UI (expose data only).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/notifications/__init__.py` · `notifications/dispatcher.py` · `notifications/adapters/base.py` (adapter protocol + a no-op/log adapter) · `notifications/dedupe.py` · `services/api/app/routers/internal_dispatch.py` (cron tick endpoint) · `infra/n8n/notification-dispatch.json` · `services/api/tests/test_dispatcher.py`
  **Guardrail: nothing else. Do NOT create `app/services/__init__.py`, edit `main.py`, add schema/`db.ts`, or write real channel adapters.**

## 4. Implementation spec

- **`dispatcher.py`:** poll `notification_outbox` for `status='pending' AND (next_retry_at IS NULL OR next_retry_at <= now())` (uses the existing index); resolve channel per recipient prefs + template; call the adapter; on success → `sent`; on **retryable** failure → increment `attempts`, set `next_retry_at` with exponential backoff; on **permanent** failure or attempts ≥ N → **dead-letter** (`status='failed'`). Per-channel rate pacing. Processes a bounded batch per tick.
- **Idempotency / exactly-once (`dedupe.py`):** `dedupe_key = f"{event_type}:{entity_id}:{channel}"`; rely on the **UNIQUE(dedupe_key)** constraint so a re-run / crash-mid-batch cannot double-send (insert-or-skip; a send is guarded so replay is a no-op). This is M14's headline success criterion.
- **`adapters/base.py`:** a `Protocol`/ABC `ChannelAdapter.send(message) -> SendResult` with a failure taxonomy (`retryable` vs `permanent`); a `NoopAdapter`/`LogAdapter` for tests.
- **`internal_dispatch.py`:** a cron-tick endpoint (internal/service-role-guarded, not public) that runs one dispatch batch; `infra/n8n/notification-dispatch.json` calls it on cadence.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

N/A. **Security:** outbox is service-role-only (no client access); the cron endpoint is internal/guarded (not publicly callable); no secrets (adapter tokens later, from env).

## 10. Tests (RUN before reporting — `uv run pytest`, `ruff`, `mypy --explicit-package-bases`)

`test_dispatcher.py`: **crash-mid-batch replay** → no double-send (exactly-once via dedupe_key); **dedupe collision** honored (unique constraint); **backoff schedule** (attempts increment, next_retry_at grows); **permanent-failure routing** → dead-letter after N; retryable vs permanent taxonomy; pending-lookup uses the `(status,next_retry_at)` index. Use the NoopAdapter + a service-role/seeded outbox rows.

## 11. Acceptance criteria / DoD

- [ ] Exactly-once per event per channel under re-run / crash-mid-batch (dedupe tested).
- [ ] Retry backoff + dead-letter after N (visible via status='failed'); dispatcher processes bounded batches.
- [ ] Adapter protocol + no-op adapter; cron endpoint internal-only; no schema/deps; ruff+mypy+pytest green.

## 12. IMPLEMENTATION REPORT

Output exactly:
**PEBBLE:** M14-P01 — Outbox dispatcher & channel adapter interface
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste crash-replay/exactly-once + backoff + dead-letter output
**EXCERPTS:** the dedupe/exactly-once guard + the adapter protocol — nothing else
**QUESTIONS:** (or "none")
