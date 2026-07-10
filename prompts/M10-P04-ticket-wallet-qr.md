> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M10-P04 — Ticket wallet (dynamic QR + PIN)

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **`tickets` (0004:149) exists:** `qr_secret`, `pin_hash`, `status ('issued','checked_in','transferred','void')`, holder-scoped RLS + a guard trigger making status/secrets **server-controlled**. Tickets are issued by M10-P03 (parallel). **No migration** — the wallet reads/serves; the secret NEVER ships to the client.
- **⚠ PINNED QR WINDOW ALGORITHM (shared verbatim with M10-P06 verify):**
  `code = HMAC_SHA256(ticket_secret, str(window))` where **`window = floor(unix_seconds / 60)`** (60s rotation). Payload = **`ticket_id + window + truncated_sig`** (sig truncated to a fixed length, e.g. first 16 hex). Verify accepts **window ±1** (M10-P06). A stale screenshot dies with its 60s window.
- **You OWN the shared golden fixture** `services/api/tests/fixtures/qr_window_goldens.json` (deterministic `(secret, window) → code` vectors) — **M10-P06 reads it** to prove verify matches issuance. ⚙ Keep the algorithm identical in `qr.py`.
- **Offline horizon:** the ticket secret must NOT reach the client. On sync, the server issues the **next N window codes** (a bounded horizon) + the PIN → the PWA caches those; offline wallet shows valid codes for the cached horizon, then degrades to PIN.
- **PWA/serwist config MERGED (M01):** add a wallet-route cache fragment `apps/customer/sw-wallet.ts` (do not rewrite the app's serwist config).
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P04. **i18n `events` (append-rule):** append `events.wallet.*` (M10-P03 also appends to `events.json` — disjoint sections).

## 2. Objective & scope

Ticket wallet: rotating **HMAC(ticket_secret, floor(now/60s))** QR (60s progress ring) + 6-digit PIN backup, offline-viewable via a **server-issued bounded horizon of window codes** (secret never client-side), holder-scoped. Wallet list + live ticket detail.
**Non-goals:** no verify/check-in (M10-P06 — you export the algorithm + goldens), no issuance/purchase (M10-P03), no transfer (M10-P07), no scanner (M10-P05), no schema change.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/tickets/qr.py` (window code + horizon issuance + PIN verify helpers) · `services/api/app/routers/ticket_wallet.py` (holder-scoped: wallet list, ticket detail, sync-next-horizon) · `apps/customer/app/[locale]/account/tickets/page.tsx` (list) · `apps/customer/app/[locale]/account/tickets/[id]/page.tsx` (live QR + 60s ring + PIN + event info) · `apps/customer/sw-wallet.ts` (serwist cache fragment for the wallet route) · `services/api/tests/fixtures/qr_window_goldens.json` (**shared with M10-P06**) · `services/api/tests/test_ticket_wallet.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/events.json` (append `events.wallet.*`)
  **Guardrail: nothing else. Do NOT touch `ticket_verify.py` (M10-P06), `purchase.py` (M10-P03), the `tickets` guard trigger, the app's main serwist config, `main.py`, schema/db.ts.**

## 4. Implementation spec

- **`qr.py`:** `current_window(now) -> int` = `floor(unix_seconds/60)`; `window_code(ticket_secret, window) -> str` = truncated `HMAC_SHA256`; `issue_horizon(ticket_secret, from_window, n) -> list[{window, code}]`; PIN verify against `pin_hash`. **The secret stays server-side** — endpoints return codes, never the secret.
- **`ticket_wallet.py`** (auth, holder-scoped, uniform envelope): wallet list (own tickets, statuses); ticket detail (event info + PIN + current window code); `GET /account/tickets/{id}/horizon?n=…` returns the next N `{window, code}` for offline caching. Other users' tickets → 404.
- **UI:** live QR re-renders each 60s with a progress ring; PIN fallback visible; offline banner + cached-horizon behavior; token-styled; 360px. Copy via `events.wallet.*`.

## 5–9. Security etc.

360px; **secret never client-side** (only codes); QR rotates every 60s; offline shows cached-horizon codes then PIN; RLS holder-scoped (other user → 404); no secrets in bundle.

## 10. Tests (RUN before reporting)

`test_ticket_wallet.py`: **rotation timing** (window changes each 60s; `window_code` deterministic vs the golden fixture); **horizon expiry** (codes valid for horizon then require re-sync); **RLS** (other holder → 404); transfer-state rendering; PIN verify. Assert `qr_window_goldens.json` vectors match `window_code`. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] QR changes every 60s; secret never leaves the server; offline wallet shows cached-horizon codes + degrades to PIN; other users' tickets inaccessible.
- [ ] `qr_window_goldens.json` created (shared w/ M10-P06); `events.wallet.*` appended (append-rule); customer build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P04 — Ticket wallet (dynamic QR + PIN)
**STATUS/FILES/DEVIATIONS** (confirm the exact HMAC/window/truncation + the golden fixture shape M10-P06 consumes + horizon size) **/TESTS** (paste rotation + golden-match + horizon-expiry + RLS + full-pytest tail) **/EXCERPTS** `window_code` + `issue_horizon` — nothing else **/QUESTIONS**
