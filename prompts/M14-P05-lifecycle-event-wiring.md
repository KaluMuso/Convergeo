> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` (import guard) before reporting.**

# M14-P05 — Lifecycle event wiring

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **Dispatcher + adapters ready:** `notifications/dispatcher.py` (`resolve_channel(requested_channel, prefs)`, `DEFAULT_CHANNEL_ORDER`, pace) + `adapters/base.py` (`ChannelAdapter`); **concrete adapters merged (W10):** `adapters/whatsapp.py` (M14-P02), `adapters/sms.py`/`email.py` (M14-P04) + `fallback.py`. **They are built but NOT yet registered** — the dispatcher has no channel→adapter map. **You wire them** (a registry the dispatcher consumes). You are the **sole `dispatcher.py` editor this wave** (keep the edit minimal — prefer a new registry module the dispatcher imports).
- **`notification_outbox` (0007):** rows carry `(channel, template, payload, dedupe_key)`. Each domain event → **outbox rows with dedupe keys** (exactly-once). Prefs in `profiles.notif_prefs`/`vendors.notif_prefs` (0002).
- **⚙ Same-wave edge — M08-P04 (payment state machine):** payment received/failed events come from M08-P04's states. Code the mapping against the **event names**; if M08-P04 unmerged, the coverage test uses the documented event list (stub). M09-P01 order states (merged) + M12-P02 KYC + disputes + tickets + quotes complete the list.
- **New files only — no edits to merged domain emitters** (`orders/state.py`, `orders/create.py`, `payments/state.py`, etc.). Provide the mapping registry + per-domain `events.py` emitter helpers **as new files**; where live wiring would require editing a merged domain file, resolve it via the dispatcher/registry consuming the emitted domain-event (or a documented `TODO(wire)`), and prove coverage via the test.
  Spec: `docs/plan/02-pebbles/M14-notifications.md` §M14-P05.

## 2. Objective & scope

The **single mapping** `domain event → template + audience + channel policy` for the full lifecycle (order placed/confirmed/shipped/ready/delivered/completed, payment received/failed, payout sent/failed, KYC approved/rejected, dispute opened/resolved, ticket issued/transferred, quote received/accepted), the adapter→dispatcher wiring, and per-domain `events.py` emitter helpers — each domain event → outbox rows with dedupe keys, **vendor vs customer audiences separated**.
**Non-goals:** no new adapters (M14-P02/04), no webhook (M14-P03), no schema, no editing merged domain-emitter files.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/notifications/events.py` (the single domain-event→template+audience+channel registry) · `notifications/adapter_registry.py` (channel→concrete adapter map: whatsapp/sms/email) · per-domain `app/services/{orders,payments,kyc,disputes,tickets,quotes}/events.py` emitter helpers (**new files only**; skip a domain if its subdir doesn't exist yet + note it) · `services/api/tests/test_event_wiring.py`
- **Modify (minimal, sole editor this wave):** `services/api/app/services/notifications/dispatcher.py` (consume `adapter_registry` so it can actually dispatch — smallest possible change)
  **Guardrail: nothing else. Do NOT touch `adapters/*` (M14-P02/04 — import), `fallback.py`, `orders/state.py`/`create.py`, `payments/state.py` (M08-P04), `webhooks_whatsapp.py` (M14-P03), `main.py`, schema.**

## 4. Implementation spec

- **`events.py`:** ONE registry mapping each domain event to `{template, audience (vendor|customer), channel_policy}`. Covers the full list above. **Vendor vs customer audiences separated** (a `vendor_new_order` goes to the vendor; `order_confirmed` to the customer). Each mapping produces **outbox rows with a deterministic dedupe_key** (event + entity id → exactly-once).
- **`adapter_registry.py`:** `channel → ChannelAdapter` for whatsapp/sms/email (instantiate the merged adapters). The dispatcher consumes this to send.
- **`dispatcher.py` (minimal edit):** import + use `adapter_registry` so `resolve_channel` → a concrete adapter → `.send()`. No behavior change beyond wiring.
- **Per-domain `events.py`:** small helpers a domain caller _can_ invoke to enqueue the right outbox row(s) for an event (new files; do not edit the domain state machines).

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend only; exactly-once via dedupe keys; audiences separated (no cross-leak); prefs respected via the dispatcher; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_event_wiring.py`: **lifecycle fixture sweep** — drive an order through the state machine (+ payment/KYC/etc. events) and assert **each event fires the correct message exactly once** (dedupe holds); **audience routing** (vendor events → vendor, customer events → customer, no cross-leak); **coverage completeness** — **every state-machine transition / documented domain event has a mapping** (no event without one). **Full `uv run pytest` (import guard) + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Full order lifecycle fires the correct messages **exactly once each** (fixture through the state machine); no event without a mapping (coverage test).
- [ ] Vendor vs customer audiences separated; adapters wired into the dispatcher (minimal edit, sole editor); dedupe keys exactly-once.
- [ ] New files only for emitters (no merged domain-file edits); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M14-P05 — Lifecycle event wiring
**STATUS/FILES/DEVIATIONS** (note the dispatcher edit size + any domain subdir skipped / `TODO(wire)`) **/TESTS** (paste lifecycle-sweep + audience-routing + coverage-completeness + full-pytest tail) **/EXCERPTS** the event→template+audience registry (a few rows) + the coverage-completeness check — nothing else **/QUESTIONS**
