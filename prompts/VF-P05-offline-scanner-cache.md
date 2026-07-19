> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VF-P05 — Offline scanner cache + scan-sync `[CODE]`

## 1. Context
**Wave 5.** Source: `01-audit-findings.md` §3 (events); MR-V03; BG-4; events BL-006. **Live:** the vendor organiser scanner PWA (`apps/vendor/sw-scanner.ts`) exists, but offline ticket verification is incomplete — a venue with no signal cannot verify tickets. M10-P05 shipped per-ticket window-sigs + an IndexedDB queue + first-scan-wins reconcile; this pebble completes the offline cache + sync robustness.
**Type:** `[CODE]`.

## 2. Objective & scope
Cache event tickets for offline verification and reconcile queued scans on reconnect with first-scan-wins.
**Non-goals:** ticket issuance workflow (VD-P02); customer wallet.

## 3. Files (edit ONLY these)
- `apps/vendor/sw-scanner.ts`
- `apps/vendor/app/[locale]/**/events/[id]/scan/_components/*` (scanner UI + sync logic)
**Guardrail: touch ONLY the vendor scanner SW + scan components; QR secret must never leave the server (window-sigs only).**

## 4. Implementation spec
- Pre-cache the event's valid ticket window-sigs (not the secret) so the scanner can verify offline.
- Queue offline scans (IndexedDB); on reconnect, sync to `ticket_scan_sync` and reconcile **first-scan-wins** (a duplicate offline scan loses to the earliest accepted one).
- Show clear offline/queued/synced states; live count updates on sync.

## 9. Security
- Only window-sigs cached; the HMAC secret stays server-side. No PII beyond what the scanner needs.

## 10. Tests (RUN before reporting)
- Offline: a valid ticket verifies from cache; an invalid/expired one is rejected.
- Reconnect: queued scans sync; a duplicate offline scan is reconciled as a loss to the first.
- `pnpm --filter vendor test` / typecheck green.

## 11. Acceptance criteria / DoD (MR-V03/BG-4)
- [ ] Offline verification works from cache; sync on reconnect.
- [ ] First-scan-wins on duplicate offline scans.
- [ ] Secret never client-side.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VF-P05 — Offline scanner cache + scan-sync
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste offline/sync/dup tests · **EXCERPTS:** the reconcile logic · **QUESTIONS:** …
