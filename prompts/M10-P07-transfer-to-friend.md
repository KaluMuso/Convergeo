> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 (ticketing sub-batch, dispatched after M10-FIX merged). **Touch ONLY your files below.** **⚠ SCHEMA: you own migration `0026` (ticket transfers) this wave** (renumber to next free slot if claimed at merge). **Run the FULL `uv run pytest` before reporting.** **⚙ CI GATING (M10 lesson):** your `test_ticket_transfer.py` DB file must be **isolation-clean** (seed AND tear down your own rows — assume a shared Postgres running alongside other suites) and green via `uv run pytest tests/test_ticket_transfer.py` against a **real DB**. Per-pebble seeding is CI-invisible — it hid all 6 M10 ticket seam bugs. **Do NOT edit `.github/workflows/ci.yml`** — the converger wires your file into the rls-job blocking step at merge (M10-FIX pattern).

# M10-P07 — Transfer-to-friend

## 1. Context

**Grounded against as-built `master` (M10-FIX merged):**

- **`tickets` (0004:149):** `status ('issued','checked_in','transferred','void')`, `holder_user_id`, `qr_secret`, `pin_hash`; guard trigger = server-controlled status/secrets. Wallet (M10-P04) + verify (M10-P06/M10-FIX) require `order_item_id IS NOT NULL`.
- **⚙ Reissue-on-claim uses the M10-FIX secret helpers:** `from app.services.tickets.qr import generate_qr_secret, generate_pin, seal_pin_storage` — on claim, **void the old secret + reissue a fresh `qr_secret`/`pin_hash`** so the sender's old QR/PIN stops working. Reuse the exact helpers (do NOT reimplement).
- **Transfer state (migration `0026_ticket_transfers.sql`):** a `ticket_transfers` table — `ticket_id`, `from_user_id`, `to_phone` (E.164), `status ('pending','claimed','cancelled','expired')`, `expires_at`, timestamps; **partial-unique `(ticket_id) where status='pending'`** enforces **one pending transfer at a time**. RLS: sender + admin read; service-role writes.
- **Rules (D2 — no resale, free transfer only):** initiate by phone until **T-6h** (6h before the event instance `starts_at`); recipient **claims on signup/login** (phone match); **cancellable before claim**; **checked-in ticket is untransferable**. Notify via the merged outbox.
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P07. **i18n `events` (append-rule):** append `events.transfer.*`.

## 2. Objective & scope

Free ticket transfer: sender initiates by phone until T-6h → recipient claims on signup/login (phone match) → **holder reassigned + old QR/PIN voided + fresh secret reissued** (original ticket rejected by verify); one pending transfer at a time; cancellable before claim; checked-in tickets untransferable. Outbox notifications.
**Non-goals:** no resale/payment, no wallet/verify change (reuse M10-P04/P06 + M10-FIX helpers), no scanner (M10-P05).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/ticket_transfer.py` (initiate / cancel / claim) · `apps/customer/app/[locale]/account/tickets/[id]/transfer/page.tsx` · `apps/customer/app/[locale]/account/tickets/_components/claim-banner.tsx` (standalone — reachable without editing M10-P04's `tickets/page.tsx`) · `supabase/migrations/0026_ticket_transfers.sql` · `services/api/tests/test_ticket_transfer.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/events.json` (append `events.transfer.*`)
  **Guardrail: nothing else. Do NOT touch `ticket_wallet.py`/`tickets/page.tsx`/`[id]/page.tsx` (M10-P04 — add NEW files only), `ticket_verify.py`/`qr.py` (reuse helpers), `purchase.py`, `main.py`, db.ts beyond `0026`.**

## 4. Implementation spec

- **`ticket_transfer.py`** (auth, owner-scoped, uniform envelope, rate-limited): `POST /tickets/{id}/transfer` (holder only; ticket `status='issued'` + `order_item_id` set + **now < starts_at − 6h** + no existing pending → insert `ticket_transfers` pending + `expires_at`; notify `to_phone` via outbox); `POST /tickets/transfers/{tid}/cancel` (sender, before claim); `POST /tickets/transfers/{tid}/claim` (authed user whose verified phone == `to_phone` → reassign `holder_user_id`, **`generate_qr_secret()` + `seal_pin_storage(generate_pin(), ticket_id)`** overwrite the old secrets, transfer → `claimed`). **Checked-in/void/transferred ticket → reject.** T-6h cutoff enforced.
- **`0026`:** `ticket_transfers` + partial-unique pending guard + RLS.
- **Pages:** transfer form (phone input, cutoff notice); claim-banner (shows a pending inbound transfer to claim). 360px; copy via `events.transfer.*`.

## 5–9. Security etc.

Holder-only initiate; **original ticket unusable post-claim** (old secret voided + reissued → verify rejects the old QR/PIN); T-6h cutoff; one pending transfer (partial-unique); checked-in untransferable; claim requires phone match; secrets server-side; no secrets in bundle.

## 10. Tests (RUN before reporting)

`test_ticket_transfer.py`: **cutoff boundary** (T-6h01m ok / T-5h59m rejected); **void-after-claim** (post-claim, the sender's old QR/PIN → verify rejects; new holder's works); **double-transfer guard** (second pending → 409 via partial-unique); **claim by new-signup phone** (phone match required; mismatch → 403); checked-in ticket → untransferable; cancel before claim. `0026` replay note. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Original ticket unusable post-claim (verify rejects); T-6h cutoff enforced; unclaimed transfer cancellable; checked-in ticket untransferable.
- [ ] `0026` additive+reversible (one-pending partial-unique); reissue uses the M10-FIX secret helpers; `events.transfer.*` appended (append-rule); customer build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P07 — Transfer-to-friend
**STATUS/FILES/DEVIATIONS** (how reissue voids the old secret via the M10-FIX helpers; the one-pending guard; claim phone-match) **/TESTS** (paste cutoff + void-after-claim + double-transfer + claim-by-phone + checked-in-untransferable + full-pytest tail) **/EXCERPTS** the claim → reissue-secret path — nothing else **/QUESTIONS**
