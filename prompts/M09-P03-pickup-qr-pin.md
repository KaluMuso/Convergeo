> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 11 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own ONE additive migration `0017` + you are the SOLE `db.ts` editor this wave.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M09-P03 — Pickup QR + PIN issuance & verify API

## 1. Context

**Wave 11 (parallel ×8).** Grounded against as-built `master`:

- **Orders have NO pickup fields** — add migration **`0017_order_pickup_tokens.sql`** giving pickup storage. **Mirror the `tickets` pattern (0004):** `tickets` has `qr_secret text` + `pin_hash text` + a **server-controlled guard trigger** ("status and secrets are server-controlled"). Add to **`orders`** (fulfilment='pickup'): `pickup_qr_secret text`, `pickup_pin_hash text`, `pickup_collected_at timestamptz`, `pickup_token_version int not null default 0` (re-issue bumps the version → prior invalidated), and a **guard trigger** so clients can't write these (service-role/definer only). **You are the SOLE `db.ts` editor this wave** — hand-update the `orders` Row/Insert/Update with the new columns (CI `db` job validates drift). Additive/reversible.
- **State machine merged (M09-P01):** verify → **`transition_order(order_id, event=collected/confirm_received, actor=vendor)`** → Delivered. Import `transition_order`; do NOT edit `state.py`. Single-use = **atomic claim** (mark `pickup_collected_at` in the same guarded update that transitions). Vendor-scoped: a vendor can only verify **their own** orders.
- `app/services/` implicit namespace — create `pickup/` with **own `__init__.py`**. Router auto-discovers (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). QR = **signed token** (order + vendor + nonce, HMAC or itsdangerous-style using an env secret — no new dep; reuse the app's signing util if one exists, else stdlib `hmac`).
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P03. **Scanner UI = M09-P04 (not this wave).**

## 2. Objective & scope

Issue a pickup QR (signed payload: order+vendor+nonce) + a 6-digit PIN (hashed) on `ready_for_pickup`, single-use; a vendor-scoped verify API (QR or PIN) that atomically claims the order and transitions it to Delivered via the state machine; re-issue invalidates the prior token.
**Non-goals:** no scanner UI (M09-P04), no event tickets (0004 tickets are separate), no notifications.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/pickup/__init__.py` · `pickup/*.py` (issue signed QR + PIN hash on ready_for_pickup; verify+claim) · `services/api/app/routers/pickup_verify.py` (vendor-scoped verify: QR or PIN → collected → Delivered) · `services/api/tests/test_pickup.py` · `supabase/migrations/0017_order_pickup_tokens.sql`
- **Modify:** `packages/types/src/db.ts` (add the new `orders` pickup columns — sole db.ts editor this wave)
  **Guardrail: nothing else. Do NOT touch `orders/state.py` (M09-P01 — call), `0005`, `tickets`/`0004`, `main.py`, other tables.**

## 4. Implementation spec

- **Issue (on `ready_for_pickup`):** generate `pickup_qr_secret` (signed: order_id+vendor_id+nonce+version) + a **6-digit PIN** stored as `pickup_pin_hash` (hash, never plaintext); bump `pickup_token_version` (re-issue invalidates the prior QR/PIN). Written via the guarded/definer path (clients can't set these).
- **`pickup_verify.py`** (`require_role('vendor')` + ownership): accept a QR token OR a PIN; validate signature/version + PIN hash; **single-use atomic claim** — one guarded UPDATE that checks `pickup_collected_at IS NULL` and the current version, sets `pickup_collected_at`, and calls `transition_order(... collected → Delivered)`. **Second concurrent verify → rejected** (atomic; only one wins). **Cross-vendor verify → 403.** Expired/re-issued (stale version) token → rejected.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

Backend + API; QR signed (env secret); PIN hashed (never plaintext); single-use atomic; vendor-scoped (cross-vendor 403); pickup fields server-controlled (guard trigger); no secrets committed.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_pickup.py`: **single-use race** (two simultaneous verifies → exactly one success, one rejected); **wrong-vendor** verify → 403; **expired/re-issued** (stale version) token rejected; PIN fallback works; verify transitions via state machine (audited → Delivered). Confirm `0017` replays clean + `db.ts` matches gen-types. **Full `uv run pytest` + ruff + mypy.**

## 11. Acceptance criteria / DoD

- [ ] Second verify attempt rejected (single-use atomic); cross-vendor verify rejected; re-issue invalidates prior.
- [ ] Verify transitions the order via `transition_order` (audited); PIN hashed; QR signed.
- [ ] `0017` additive/reversible; `db.ts` matches gen-types (sole editor); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P03 — Pickup QR + PIN issuance & verify
**STATUS/FILES/DEVIATIONS** (confirm `0017` + db.ts hand-update + the signing util used) **/TESTS** (paste single-use-race + wrong-vendor + reissue-invalidation + full-pytest tail) **/EXCERPTS** the atomic single-use claim + the QR sign/verify — nothing else **/QUESTIONS**
