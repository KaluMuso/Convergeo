> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** **Mind the ≤150 KB gz bundle budget (perf-CI is live)** — a QR-decode lib must fit. **Run the FULL `uv run pytest` before reporting.**

# M09-P04 — Vendor pickup scanner UI

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **Pickup verify merged (M09-P03):** `POST /vendor/pickup/verify` — body `{qr_token}` OR `{order_id, pin}` → single-use atomic claim → transitions the order to Delivered; vendor-scoped. **You build the scanner UI that calls it.** Pickup issuance now fires on `ready_for_pickup` (M14-P05) and the customer receives the PIN via WhatsApp.
- Vendor app `localePrefix:"always"` → pages at **`apps/vendor/app/[locale]/scan/`** (spec's `app/scan/` is stale). **Camera via `getUserMedia` + a small in-bundle QR decoder** (e.g. `jsqr`-class) — **keep within the bundle budget** (perf-CI enforces ≤150 KB gz per route; if the decoder is heavy, dynamic-`import()` it so it doesn't inflate the first-load JS). **PIN-entry fallback** when the camera is denied. i18n `vendor` namespace — **you solely own `vendor.json` this wave** (append a nested `scan` section).
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P04. **Full offline scanning is M10's event scanner — pickup verify requires connectivity (show an offline notice).**

## 2. Objective & scope

A vendor camera scanner (`scan/`): `getUserMedia` + QR decode → **verify API → success/failure feedback (visual + haptic)**; **PIN-entry fallback** when camera-denied; **offline notice** (verify needs connectivity); a recent-verifications list; a clear **wrong-QR (event ticket) mismatch** message.
**Non-goals:** no verify API (M09-P03 — call), no event ticket scanning (M10), no schema, no offline scanning.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/scan/page.tsx` · `apps/vendor/app/[locale]/scan/_components/*` (camera scanner, PIN fallback, result states, recent list)
- **Modify:** `packages/i18n/messages/en/vendor.json` (append nested `scan` section)
  **Guardrail: nothing else. Do NOT touch `vendor/orders/*` (M09-P02/M12-P07), `pickup_verify.py` (M09-P03 — call), `main.py`, schema, other namespaces.**

## 4. Implementation spec

- **Scanner page:** `getUserMedia` camera stream → decode QR (dynamic-import the decoder to protect the bundle budget) → call `POST /vendor/pickup/verify {qr_token}` → **success (visual + haptic) / failure feedback**; a **wrong-QR** (e.g. an event ticket token) → a **clear mismatch message** (verify returns a typed error). **Camera-denied → PIN-entry fallback** (`{order_id, pin}`) — clean transition. **Offline → a notice** (verify needs connectivity). A **recent-verifications** list (session-local). All copy via `vendor` (`scan.*`); 360px; **scan→verified target ≤3s** on mid-range Android.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; camera-denied → PIN fallback (clean); offline notice; **within the ≤150 KB gz budget** (dynamic-import the decoder); vendor-scoped via M09-P03; haptic feedback; no secrets.

## 10. Tests (RUN before reporting)

Component (mocked scanner stream): **scan → verified** flow; **PIN fallback** (camera-denied → PIN path); **error-state renders** (wrong-QR mismatch, offline, verify-failure). i18n `vendor.scan.*` nested. `pnpm --filter vendor build` (confirm the decoder doesn't blow the bundle budget), `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`** (no API change — confirm green).

## 11. Acceptance criteria / DoD

- [ ] Scan → verified path works (mocked stream); camera-denied falls back to PIN cleanly; wrong-QR gives a clear mismatch message; offline notice shown.
- [ ] Within the bundle budget (decoder dynamic-imported); `vendor.scan.*` nested (sole owner); repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P04 — Vendor pickup scanner UI
**STATUS/FILES/DEVIATIONS** (note the QR decoder chosen + how the bundle budget was protected) **/TESTS** (paste scan-flow + PIN-fallback + error-states + `--filter vendor build` bundle line) **/EXCERPTS** (none) **/QUESTIONS**
