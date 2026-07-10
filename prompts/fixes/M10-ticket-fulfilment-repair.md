> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. This is a **standalone convergence repair** (not part of a parallel wave) — you may touch every file listed below; there are no concurrent owners. **Run the FULL `uv run pytest` before reporting, and ensure the DB-backed ticket suites actually execute in CI (they skip locally without Postgres — CI has the stack).**

# M10-FIX — Ticket fulfilment repair (P03↔P04↔P06 seam)

## 1. Why this exists

Phase-4 review found the merged ticketing path (M10-P03 purchase, M10-P04 wallet, M10-P06 verify) is **non-functional end-to-end** — each pebble's tests seed their own ticket rows, so isolation passed while the real seam is broken. Six defects, in priority order:

1. **CRITICAL — issued tickets have NULL secrets.** `_insert_issued_tickets` (`services/api/app/services/tickets/purchase.py`) and the claim insert (`services/api/app/services/tickets/inventory.py`) write neither `qr_secret` nor `pin_hash`. Result: the wallet can't render a QR (`ticket_wallet.py` raises on missing `qr_secret`), QR check-in raises `ticket_qr_unavailable`, and PIN check-in returns `ticket_invalid_pin`. **No ticket the code issues can be displayed or checked in.**
2. **CRITICAL — issuance never fires.** `POST /internal/tickets/issue-tick` has no invoker (no `infra/n8n/*` workflow references tickets; no payment-success hook). A paid order sits unissued forever.
3. **HIGH — capacity leaks.** `release_ticket_claim` has no callers. Claims are inserted as `status='issued'` with `order_item_id IS NULL` and **count against capacity**, so abandoned/failed checkouts lock seats permanently.
4. **MEDIUM — PIN format mismatch.** `qr.py seal_pin_storage` stores `pin_hash` as `"{digest}${wrapped}"`; `ticket_verify.py verify_ticket_pin` compares the bare digest **without splitting on `$`** → PIN verify always fails even once secrets exist.
5. **MEDIUM — under-issue.** `_link_claimed_tickets` returns `len(ticket_ids)` instead of the real UPDATE rowcount; if a claim id is void/missing, `existing` is inflated and the shortfall is never inserted.
6. **LOW — picker unmounted + holds indistinguishable.** `ticket-picker.tsx` is built but `e/[slug]/page.tsx` never imports it (still the M05-P11 stub). Unpaid holds (`status='issued'`, `order_item_id IS NULL`) are only distinguished from paid tickets by the null FK.

QR window algorithm is **correct** (byte-identical P04↔P06, golden-verified) — **do not touch it.**

## 2. Objective & scope

Make the ticket purchase→issue→verify path work end-to-end: **populate secrets at issuance**, **wire auto-issuance + capacity-release**, **align the PIN format**, **fix the link rowcount**, **mount the picker**, and **exclude unpaid holds** from wallet/verify. Add real DB-backed tests that exercise the whole path (they must run in CI).
**Non-goals:** no change to the QR window algorithm/goldens, no new payment-router edits (keep issuance decoupled via the tick), no schema migration unless strictly required (prefer additive; if a claim TTL column is needed, justify it).

## 3. Files (touch as needed — single-owner convergence PR)

- `services/api/app/services/tickets/purchase.py` — write secrets on issue + link; fix `_link_claimed_tickets` rowcount
- `services/api/app/services/tickets/inventory.py` — (claim insert stays secret-less; secrets are set at issue/link, not at hold) — only touch if needed for the holds filter
- `services/api/app/services/tickets/qr.py` — reuse existing helpers (`generate_pin`, `seal_pin_storage`, `verify_pin`); add a `generate_qr_secret()` helper if you want it centralized
- `services/api/app/routers/internal_tickets.py` — add `POST /internal/tickets/release-tick` (stale-claim sweeper); confirm `/issue-tick`
- `services/api/app/routers/ticket_verify.py` — **delegate PIN verify to `qr.verify_pin`** (split-aware); require `order_item_id IS NOT NULL` for a valid check-in
- `services/api/app/routers/ticket_wallet.py` — list only real tickets (`order_item_id IS NOT NULL`)
- `infra/n8n/tickets-issue.json` (NEW) + `infra/n8n/tickets-release.json` (NEW) — cron → the two ticks (internal token as an n8n credential, never inline)
- `apps/customer/app/[locale]/(shop)/e/[slug]/page.tsx` — mount `<TicketPicker instances=… ticketTypes=… eventSlug=… isSoldOut=… />` replacing the stub, mapping the page's `event.instances`/`event.ticket_types`
- `services/api/tests/test_ticket_purchase.py`, `test_ticket_wallet.py`, `test_ticket_verify.py` — extend
  **Guardrail: do NOT change the QR window algorithm (`window_code`/`window_sig`/payload/±1) or `qr_window_goldens.json`; do NOT edit payment routers; do NOT touch unrelated pebbles.**

## 4. Implementation spec

- **Secrets at issuance (Defect 1).** Everywhere a ticket becomes a _real_ ticket (direct `_insert_issued_tickets`, the claim→paid link in `_link_claimed_tickets`, and the RSVP issue path), set per-ticket: `qr_secret = secrets.token_hex(32)` and `pin_hash = seal_pin_storage(pin=generate_pin(), ticket_id=<that ticket's id>)`. Because `seal_pin_storage` needs the ticket id, **generate the ticket UUID in Python** and insert explicit rows (service-role write — the `tickets` guard trigger allows server-side secret writes; it only blocks client mutation). For the link path, the ticket ids already exist → `UPDATE … SET order_item_id=…, qr_secret=…, pin_hash=…` per row. **Holds stay secret-less** (secrets appear only when order_item_id is set), which also naturally prevents scanning an unpaid hold.
- **Auto-issuance (Defect 2).** Add `infra/n8n/tickets-issue.json`: a schedule trigger (~60s) → HTTP POST `/internal/tickets/issue-tick` with the internal token. Keep issuance idempotent (already scoped per order_item). Document the ~60s issuance latency.
- **Capacity release (Defect 3).** Add `POST /internal/tickets/release-tick` (internal token) that voids **stale unpaid claims** — `order_item_id IS NULL AND status='issued' AND created_at < now() - <claim TTL>` (reuse the reservation TTL from M07-P02/config; do not invent a divergent value) — via the existing idempotent `release_ticket_claim` logic (which only voids unlinked, non-void rows). Add `infra/n8n/tickets-release.json` cron. This frees leaked capacity.
- **PIN format (Defect 4).** In `ticket_verify.py`, replace the local non-splitting compare with a call to `qr.verify_pin(pin=…, ticket_id=…, pin_hash=stored)` (it strips `digest$wrapped` correctly and uses the identical pepper). Remove the duplicated hash path or keep it only if it delegates. A sealed PIN must now verify.
- **Under-issue (Defect 5).** `_link_claimed_tickets` returns the **actual number of rows updated** (from the UPDATE result), not `len(ticket_ids)`; callers already recompute `needed` from it, so the shortfall gets inserted.
- **Holds vs paid (Defect 6a).** Wallet list and verify require `order_item_id IS NOT NULL` so an unpaid hold is never shown or checked in.
- **Picker mount (Defect 6b).** Import `TicketPicker` into `e/[slug]/page.tsx`, map `event.instances`→`TicketPickerInstance[]` and `event.ticket_types`→`TicketPickerType[]` (the fields already exist on the page's data), pass `eventSlug`/`isSoldOut`. **Keep the `e/[slug]` route within the 150 KB gz customer budget** — dynamic-import the client picker or keep the page a server shell if needed (the wallet detail hit this budget; watch it).

## 5–9. Security etc.

Secrets server-side only (guard trigger); PIN sealed (holder-recoverable via wallet, never plaintext at rest); internal ticks token-guarded (env secret, none in repo/n8n JSON); release only voids unlinked non-void holds (never a paid ticket); QR unchanged; 150 KB budget on `e/[slug]`; no float; no secrets in the bundle.

## 10. Tests (MUST run in CI, not just skip)

Extend the DB-backed suites so they exercise the real path:

- **Issued ticket has non-null `qr_secret` + `pin_hash`** (both direct-issue and claim→link and RSVP paths).
- **End-to-end QR check-in** on a freshly-issued ticket succeeds (was `ticket_qr_unavailable`).
- **End-to-end PIN check-in** on a freshly-issued (sealed) ticket succeeds (Defect 4 regression).
- **Release frees capacity**: a stale unpaid claim → `release-tick` voids it → capacity recovered; a paid (linked) ticket is untouched; re-run is idempotent.
- **Issue-tick issues a paid order** and is idempotent on replay.
- **Under-issue guard**: a claim list with a void id still results in exactly `qty` issued.
  Add **pure-unit** tests (no DB) for: `seal_pin_storage` → `qr.verify_pin` round-trip == True and the bare-digest mismatch is gone; `_link_claimed_tickets` rowcount reflects actual updates. Frontend: `pnpm --filter customer build` (assert `e/[slug]` within budget), `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Every issued/linked/RSVP ticket has non-null `qr_secret` + sealed `pin_hash`; wallet renders a QR + PIN; QR and PIN check-in both succeed end-to-end.
- [ ] `/issue-tick` + `/release-tick` are invoked by n8n workflows (token via credential); paid tickets issue automatically; stale claims release and free capacity.
- [ ] PIN verify uses the split-aware `qr.verify_pin`; `_link_claimed_tickets` returns real rowcount (no under-issue); wallet/verify exclude unpaid holds.
- [ ] `TicketPicker` mounted on `e/[slug]` within the 150 KB budget. DB-backed ticket tests **run green in CI** (not skipped); full suite + 1 app build green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-FIX — Ticket fulfilment repair
**STATUS/FILES/DEVIATIONS** (how secrets are generated per path; whether a claim-TTL column was needed; issuance/release cron intervals; how the picker stayed within budget) **/TESTS** (paste: issued-ticket-has-secrets, end-to-end QR check-in, end-to-end PIN check-in, release-frees-capacity, issue-tick, under-issue guard, PIN round-trip unit — and confirm they RAN in CI, not skipped) **/EXCERPTS** the secret-writing issue path + the `verify_ticket_pin`→`qr.verify_pin` change + the release-tick sweeper — nothing else **/QUESTIONS**
