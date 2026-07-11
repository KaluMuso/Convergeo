> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 (ticketing sub-batch, dispatched after M10-FIX merged). **Touch ONLY your files below.** **Run the FULL `uv run pytest` before reporting.** **⚙ CI GATING (M10 lesson):** your `test_ticket_scan_sync.py` DB file must be **isolation-clean** (seed AND tear down your own rows — assume a shared Postgres running alongside other suites) and green via `uv run pytest tests/test_ticket_scan_sync.py` against a **real DB**. Per-pebble seeding is CI-invisible — it hid all 6 M10 ticket seam bugs. **Do NOT edit `.github/workflows/ci.yml`** — the converger wires your file into the rls-job blocking step at merge (M10-FIX pattern).

# M10-P05 — Organiser scanner PWA

## 1. Context

**Grounded against as-built `master` (M10-FIX merged — tickets now carry real `qr_secret`/`pin_hash`):**

- **Verify API MERGED + REPAIRED (M10-P06 + M10-FIX):** `ticket_verify.py` — window `floor(unix/60)`, `window_sig = HMAC_SHA256(qr_secret, str(window))[:16]`, payload `{ticket_id}:{window}:{sig}`, verify **±1**, atomic single-use check-in, batch endpoint (earliest-scan-wins), `order_item_id IS NOT NULL` required. PIN verify delegates to `qr.verify_pin`. **Reuse the online batch verify for reconcile; do NOT edit `ticket_verify.py`.**
- **⚙ Offline sync needs a NEW organiser endpoint** — the scanner must validate offline WITHOUT the ticket secret leaving the server. Add `services/api/app/routers/ticket_scan_sync.py` (organiser-scoped): for an instance, return per issued ticket **`{ticket_id, [window_sig for each window across the event horizon]}`** (server derives sigs from each ticket's `qr_secret` — now populated post-M10-FIX). The device caches these; an offline scan validates the scanned `{ticket_id, window, sig}` against the cached sigs (**±1 window** for clock skew). **The raw `qr_secret` NEVER ships.**
- **Offline-first (serwist MERGED, M01):** add `apps/vendor/sw-scanner.ts` cache fragment; IndexedDB store for the synced verification data + a pending check-in queue; **first-scan-wins** reconciled on sync (send the queue to the batch verify endpoint; server resolves duplicates by earliest `scanned_at`).
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P05. **i18n `vendor` (append-rule):** append `vendor.scan.*` (M10-P08 also appends to `vendor.json` — disjoint sections).

## 2. Objective & scope

Organiser scanner PWA: pre-event sync downloads per-ticket window-sig horizons (secret stays server-side) → **offline scans validated locally (±1 window skew), queued** → **first-scan-wins** reconciled via the merged batch verify on reconnect; live check-in count (online) / local count (offline); camera scan + green/red flash.
**Non-goals:** no verify-API change (M10-P06 — reuse batch verify), no ticket issuance/wallet (M10-P03/P04), no window-algorithm change.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/events/[id]/scan/page.tsx` + `scan/_components/*` (camera scanner, result flash + count) · `apps/vendor/app/[locale]/events/[id]/scan/_lib/offline-store.ts` (IndexedDB cache + pending queue) · `apps/vendor/sw-scanner.ts` (serwist fragment) · `services/api/app/routers/ticket_scan_sync.py` (organiser-scoped sync) · `services/api/tests/test_ticket_scan_sync.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/vendor.json` (append `vendor.scan.*`)
  **Guardrail: nothing else. Do NOT touch `ticket_verify.py`/`qr.py`/`ticket_wallet.py`/`purchase.py` (M10-P06/P04/P03/M10-FIX — reuse), the vendor app's main serwist config, `main.py`, schema/db.ts. No migration.**

## 4. Implementation spec

- **`ticket_scan_sync.py`** (auth, **organiser-scoped** — organiser owns the event, uniform envelope): `GET /events/{event_id}/instances/{instance_id}/scan-sync` → for each issued ticket (`order_item_id IS NOT NULL`, status `issued`/`transferred`), compute `window_sig` for each window across the event horizon (a bounded set around the event time, ±skew) and return `{ticket_id, window_sigs, pin_hash_present}`. **Never return `qr_secret`.** Cross-organiser → 403.
- **`offline-store.ts`:** IndexedDB — store the synced `{ticket_id → window_sigs}`; validate an offline scan `{ticket_id, window, sig}` (accept if sig matches a cached sig within ±1 window); queue accepted check-ins with `scanned_at`; on reconnect, POST the queue to the merged batch verify (`/tickets/verify/batch`) → server resolves first-scan-wins.
- **UI:** camera scanner (jsQR-class within bundle budget), green/red flash + running count, offline banner, recent-verifications; 360px. Copy via `vendor.scan.*`.

## 5–9. Security etc.

Organiser-scoped (own events only); **secret never ships** (only window sigs); ±1 window skew tolerance; first-scan-wins on reconcile (duplicate → red); offline queue survives reload; bundle budget on the scan route; no secrets in the bundle.

## 10. Tests (RUN before reporting)

`test_ticket_scan_sync.py`: sync returns window sigs for issued tickets (NO `qr_secret` in payload); cross-organiser → 403; a computed sig matches `window_sig` for the ticket's secret (parity with verify). Frontend component/logic tests: **offline validate/queue/sync cycle**; **first-scan-wins conflict** (two devices, same ticket → one check-in, other flagged); **skew simulation** (±60s still validates via ±1). `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Airplane-mode scan works end-to-end; duplicate scan (either device) flagged red on reconcile; skewed-clock device (±60s) still validates.
- [ ] `scan-sync` never returns `qr_secret`; organiser-scoped; `vendor.scan.*` appended (append-rule); vendor build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P05 — Organiser scanner PWA
**STATUS/FILES/DEVIATIONS** (the scan-sync payload shape; how offline validation matches verify's ±1; queue reconcile via batch verify) **/TESTS** (paste no-secret-in-sync + sig-parity + offline-cycle + first-scan-wins + skew + full-pytest tail) **/EXCERPTS** the sync sig derivation (server-side) + the offline validate — nothing else **/QUESTIONS**
