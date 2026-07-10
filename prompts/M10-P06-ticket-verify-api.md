> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M10-P06 — Verify API & check-in

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **`tickets` (0004:149):** `qr_secret`, `pin_hash`, `status ('issued','checked_in','transferred','void')`, `checked_in_at`, guard trigger (status server-controlled). Organiser-scoped RLS (`tickets_organiser_select`, 0004:758) lets an organiser read own-event tickets incl. secrets. **No migration** — check-in transitions `issued → checked_in` atomically.
- **⚠ PINNED QR WINDOW ALGORITHM (identical to M10-P04 — must match exactly):**
  `code = HMAC_SHA256(ticket_secret, str(window))`, `window = floor(unix_seconds/60)`, payload `ticket_id + window + truncated_sig`. **Verify accepts window ±1; ±2 rejected.** A screenshot >60s old fails.
- **⚙ Shared goldens (M10-P04 owns `services/api/tests/fixtures/qr_window_goldens.json`):** read it to prove verify accepts codes M10-P04 issues. Since M10-P04 is **parallel**, code your verify against the pinned algorithm (recompute `HMAC(secret, window)` server-side from the ticket's `qr_secret`); if the fixture file is absent at test time, guard the golden test with a skip + `TODO(M10-P04)`.
- **Atomic single-use check-in:** claim the transition under a lock / conditional UPDATE (`WHERE status='issued'`) so **concurrent verifies → exactly one check-in**. **Void/transferred tickets rejected.** Cross-organiser verify rejected.
- **Batch endpoint (offline-queue sync):** accepts a queue of scans, **first-scan-wins by earliest timestamp** (later = flagged duplicate), idempotent replay.
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P06. **API-only — no i18n, no UI** (scanner PWA = M10-P05, not this wave).

## 2. Objective & scope

Organiser-scoped verify + check-in API: **QR window ±1** (±2 rejected) or PIN fallback, **atomic single-use** check-in (`issued → checked_in`), a **batch offline-sync endpoint** with earliest-timestamp-wins conflict resolution + idempotent replay. Void/transferred rejected; cross-organiser denied.
**Non-goals:** no scanner UI (M10-P05), no wallet/QR issuance (M10-P04 — recompute the pinned algorithm), no transfer (M10-P07), no schema change.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/ticket_verify.py` (organiser-scoped verify QR/PIN + atomic check-in + batch sync) · `services/api/tests/test_ticket_verify.py`
  **Guardrail: nothing else. Do NOT touch `qr.py`/`ticket_wallet.py` (M10-P04 — recompute the algorithm locally), `purchase.py` (M10-P03), the `tickets` guard trigger, `main.py`, schema/db.ts. Read (not edit) the shared golden fixture.**

## 4. Implementation spec

- **`ticket_verify.py`** (auth, **organiser-scoped**, uniform envelope, rate-limited): `POST /tickets/verify` — QR (`ticket_id + window + sig`) validated by recomputing `HMAC(qr_secret, window)` and accepting **window ±1**; PIN fallback vs `pin_hash`; on success **atomic check-in** (conditional UPDATE `status='issued' → 'checked_in'` + `checked_in_at`); reject void/transferred/already-checked-in + cross-organiser (organiser owns the event). `POST /tickets/verify/batch` — list of `{ticket_id, code|pin, scanned_at}`; resolve **earliest `scanned_at` wins**, later duplicates flagged; idempotent (replay → same result, one check-in).

## 5–9. Security etc.

Organiser-scoped (can only verify own events' tickets — authz test); **window ±1 accept / ±2 reject**; atomic single-use (race → one check-in); void/transferred rejected; batch replay idempotent; no secrets in responses beyond the check-in result.

## 10. Tests (RUN before reporting)

`test_ticket_verify.py`: **window matrix** (0/±1 accepted, ±2 rejected — vs recomputed codes / shared goldens if present); **race** (two concurrent verifies of the same ticket → one check-in, one rejected); **batch conflict** (earliest `scanned_at` wins, later flagged duplicate) + **idempotent replay**; **cross-organiser denial**; **void/transferred rejection**. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Window ±1 accepted, ±2 rejected; concurrent verify → exactly one check-in; batch replay idempotent + earliest-wins; screenshot >60s fails.
- [ ] Cross-organiser + void/transferred rejected; algorithm matches M10-P04 (goldens); full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P06 — Verify API & check-in
**STATUS/FILES/DEVIATIONS** (confirm the recomputed HMAC matches M10-P04's algorithm; whether goldens were present or skipped; the atomic check-in mechanism) **/TESTS** (paste window-matrix + race + batch-conflict + cross-organiser + void-reject + full-pytest tail) **/EXCERPTS** the atomic single-use check-in + the ±1 window check — nothing else **/QUESTIONS**
