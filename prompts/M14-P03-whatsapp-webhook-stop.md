> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M14-P03 — WhatsApp webhook & opt-in/STOP

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **WhatsApp adapter merged (M14-P02, W10):** `adapters/whatsapp.py` + templates. **`notification_outbox` (0007):** `(channel, status in ('pending','sent','failed'), attempts, dedupe_key)` — delivery/read status callbacks **update the matching outbox row's status**. **Prefs live in `notif_prefs jsonb`** on **both** `public.profiles` (customer) and `public.vendors` (vendor) (0002) — a **STOP writes prefs across ALL channels** for that recipient (whatsapp+sms+email off); START re-enables.
- Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). Meta verify-token handshake (GET challenge) + **signature verify** on inbound POST. **Do NOT edit `dispatcher.py`** (wiring = M14-P05, same wave) or `adapters/*` (M14-P02).
- **Quality-safety:** STOP honored **instantly** (Meta quality-rating protection). Status callbacks **drive the SMS fallback decision** (M14-P04's `fallback.py`, merged) — you update outbox status; the dispatcher/fallback reacts. Unknown inbound → **support log** (M13-P10 visibility later — structured log now).
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P03. **Live E2E needs F5 (Meta setup) — mock/fixture-tested here.**

## 2. Objective & scope

`webhooks_whatsapp.py`: Meta verify-token handshake + inbound **signature verify**; **delivery/read status callbacks → update the matching `notification_outbox` row**; **inbound STOP/START → prefs update across ALL channels** (STOP disables whatsapp+sms+email for the recipient; START re-enables); unknown sender/inbound → support log.
**Non-goals:** no WhatsApp send (M14-P02), no SMS/email/fallback (M14-P04), no dispatcher wiring (M14-P05), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/webhooks_whatsapp.py` · `services/api/tests/test_wa_webhook.py`
  **Guardrail: nothing else. Do NOT touch `dispatcher.py`/`adapters/*`/`fallback.py` (M14-P01/02/04/05), `notification_outbox`/`0007`, `profiles`/`vendors` schema (write `notif_prefs` via service role, no DDL), `main.py`.**

## 4. Implementation spec

- **`webhooks_whatsapp.py`:** `GET /webhooks/whatsapp` = Meta verify-token challenge echo. `POST /webhooks/whatsapp` = **verify signature first** (forged → reject, nothing applied); then route by payload type:
  - **status callback** (sent/delivered/read/failed) → find the outbox row by the message ref and **update its `status`** idempotently (**duplicate status events → no double effect**). A `failed`/undelivered status is what M14-P04's fallback keys on.
  - **inbound STOP** (case-insensitive, from a recipient) → set that recipient's `notif_prefs` to disable **whatsapp + sms + email** (write to `profiles.notif_prefs` or `vendors.notif_prefs` — resolve which by the phone/recipient), **instantly**. **START** → re-enable.
  - **unknown sender / unrecognized inbound** → structured support log, 200.
- All prefs writes via service role (RLS-guarded tables); no DDL.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; signature verified before any action; STOP honored instantly across channels; status updates idempotent; secrets env-only; no secrets committed.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_wa_webhook.py`: **verify-token handshake** (GET challenge echo); **signature verify** (forged POST → rejected, nothing applied); **STOP → prefs off across whatsapp+sms+email** (+ START re-enables); **duplicate status events idempotent** (no double outbox update); **unknown-sender** → logged + 200. **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] STOP honored across ALL channels instantly; START re-enables; forged webhook rejected; status updates idempotent.
- [ ] Status callbacks update the matching outbox row (drives fallback); unknown inbound → support log; no `dispatcher.py`/schema edits.
- [ ] Full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M14-P03 — WhatsApp webhook & opt-in/STOP
**STATUS/FILES/DEVIATIONS** (note how the recipient→profiles/vendors prefs row is resolved) **/TESTS** (paste STOP-across-channels + forged-reject + dup-status-idempotent + full-pytest tail) **/EXCERPTS** the STOP prefs-across-channels write + signature verify — nothing else **/QUESTIONS** (flag F5 for live)
