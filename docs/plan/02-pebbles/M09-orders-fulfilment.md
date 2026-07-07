# M09 — Orders, Fulfilment & Post-Order — Pebbles

10 pebbles. All status changes via the guarded state machine (P01) — raw UPDATEs are RLS-blocked (M03-P04) and review-blocking. Owns i18n namespace `orders`.

---

### M09-P01 — Order state machine `L`
**Deps:** M03-P04 · **Files:** `services/api/app/services/orders/state.py` (transition table Placed→Confirmed→Processing→Ready|Shipped→Delivered→Completed + Cancelled branches; actor-permission per transition: customer/vendor/admin/system), `orders/audit.py` (order_events writer), `services/api/tests/test_order_state.py`
**The transition test table is generated from the spec table in this file** — every legal transition tested, every illegal one rejected, every transition writes an audit row with actor + note.
**AC:** exhaustive matrix (state × event × actor) has an explicit expectation; cancellation rules encode payment status (paid → refund path required, unpaid → straight cancel).
**Tests:** generated matrix; audit completeness; concurrent conflicting transitions (row lock, one wins).

### M09-P02 — Vendor order actions `M`
**Deps:** P01, M04-P03 · **Files:** `services/api/app/routers/vendor_orders.py` (confirm/reject-with-reason/pack/ship-with-tracking-note/ready-for-pickup), `apps/vendor/app/orders/[id]/page.tsx` (order detail + action buttons), `apps/vendor/app/orders/_components/action-bar.tsx`, `packages/i18n/messages/en/vendor.json` (orders section)
Actions gated by state machine + vendor ownership; reject requires reason (customer-visible, triggers refund path if paid); ship captures free-text tracking note; big-button mobile-first action bar.
**AC:** vendor B cannot act on vendor A's order (authz test); reject on paid order enqueues refund; actions emit outbox events.
**Tests:** authz matrix, state-gated action availability, reject→refund event.

### M09-P03 — Pickup QR+PIN issuance & verify API `M`
**Deps:** P01 · **Files:** `services/api/app/services/pickup/` (issue on ready_for_pickup: signed QR token + 6-digit PIN hash, single-use), `app/routers/pickup_verify.py` (vendor-scoped verify: QR or PIN, marks collected → Delivered transition), `services/api/tests/test_pickup.py`
QR = signed payload (order, vendor, nonce); verify is **single-use** (atomic claim), vendor-scoped (can only verify own orders); PIN fallback for no-camera; re-issue invalidates prior.
**AC:** second verify attempt rejected; cross-vendor verify rejected; verify transitions order via state machine (audited).
**Tests:** single-use race (two simultaneous verifies → one success), wrong-vendor, expired/reissued token.

### M09-P04 — Vendor pickup scanner UI `M`
**Deps:** P03 · **Files:** `apps/vendor/app/scan/page.tsx`, `apps/vendor/app/scan/_components/` (camera scanner via getUserMedia + jsQR-class lib within bundle budget, PIN-entry fallback, result states)
Camera scan → verify API → success/failure feedback (visual + haptic); offline notice (pickup verify requires connectivity — full offline scanning is M10's event scanner); recent-verifications list.
**AC:** scan→verified ≤3s on mid-range Android; camera-denied falls back to PIN cleanly; wrong-QR (event ticket) gives clear mismatch message.
**Tests:** component tests with mocked scanner stream; PIN fallback flow; error-state renders.

### M09-P05 — Customer order pages `M`
**Deps:** P01, M02 · **Files:** `apps/customer/app/[locale]/account/orders/page.tsx` (list), `orders/[id]/page.tsx` (timeline detail, pickup QR/PIN display when applicable, receipt/invoice download link), `services/api/app/routers/customer_orders.py`, `packages/i18n/messages/en/orders.json`
Timeline maps state machine + audit events to customer-friendly steps with escrow trust copy ("Held by Vergeo5 → Released"); invoice/receipt PDF fetch (signed URL from M08-P12 data; PDF render in M15-P07 — link stubs until then); per-vendor sub-orders grouped under checkout group.
**AC:** timeline accurate for every state incl. cancelled/refunded; QR/PIN visible only for ready pickup orders, only to owner.
**Tests:** timeline mapping per state fixture; authz (other customer 404); COD vs prepaid copy differences.

### M09-P06 — Confirm-received & report-problem `M`
**Deps:** P05, M08-P08 · **Files:** `apps/customer/app/[locale]/account/orders/[id]/_components/confirm-received.tsx`, `report-problem.tsx`, `services/api/app/routers/order_confirmation.py`
Confirm-received → Completed + escrow release trigger (M08-P08 path); report-problem → guided triage (faulty/wrong → returns lane 1 (P07); not-delivered → dispute (P09); other → support) with evidence upload (private bucket).
**AC:** confirm fires release exactly once (idempotent double-tap); report within 48h window routes to lane 1, after → guidance; evidence stored private (RLS).
**Tests:** double-confirm idempotency, 48h window boundary, triage routing.

### M09-P07 — Returns lane 1 (faulty/wrong) `M`
**Deps:** P06 · **Files:** `services/api/app/services/returns/lane1.py`, `app/routers/returns.py`, `apps/customer/app/[locale]/account/orders/[id]/return/page.tsx`, vendor-side response in `apps/vendor/app/returns/page.tsx`
Report ≤48h of delivered + photo evidence mandatory → return record → vendor notified (accept/contest) → admin arbitration on contest → **full refund incl. delivery** from escrow (M08-P10 lane 1); return shipping charged to vendor (ledger entry).
**AC:** evidence required (submit blocked without); refund breakdown = item + delivery exactly; contest path lands in admin dispute queue.
**Tests:** window enforcement, refund composition, vendor-contest flow, escrow-vs-clawback source selection.

### M09-P08 — Returns lane 2 (change-of-mind) `M`
**Deps:** P07 · **Files:** `services/api/app/services/returns/lane2.py`, vendor `returnable` toggle surfacing in `apps/customer/app/[locale]/(shop)/p/[slug]/_components/returnable-badge.tsx`, customer flow reuse via `return/page.tsx` lane branch (files split from P07 by lane module + badge component)
Vendor opt-in per listing (flag + window 48h–7d from M03-P02); eligibility check (window, unused declaration); **refund = item − outbound delivery − return transport − restocking (config 5–15%, default 10%)** computed server-side with itemized breakdown shown before customer commits.
**AC:** ineligible listings show no lane-2 option; breakdown ngwee-exact matches M08-P10 execution; window boundary respected.
**Tests:** eligibility matrix (flag off, window expired), fee math goldens, breakdown display = executed refund.

### M09-P09 — Disputes `L`
**Deps:** P06, M08-P08 · **Files:** `services/api/app/services/disputes/` (state machine: opened→vendor_responded→under_review→resolved(refund|release|partial)), `app/routers/disputes.py`, `apps/customer/app/[locale]/account/orders/[id]/dispute/page.tsx`, `apps/vendor/app/disputes/page.tsx` (+detail), `packages/i18n/messages/en/orders.json` gains dispute keys (same file as P05 — **sequenced in a later wave**)
Evidence both sides (private bucket), vendor response window, admin decision executes refund/release via M08 services; **dispute open = escrow hold** (M08-P08 integration); resolution audited.
**AC:** hold takes effect immediately on open; decision options map to exact ledger outcomes; parties see only their dispute.
**Tests:** hold-beats-timer test, resolution → correct M08 call per decision type, RLS isolation.

### M09-P10 — Scheduled jobs & manual-dispatch surfaces `M`
**Deps:** P01, P06, M08-P08 · **Files:** `services/api/app/routers/internal_order_jobs.py` (48h auto-confirm after Delivered, 7d auto-release after Shipped — both via state machine + release engine), `infra/n8n/order-jobs.json`, delivery timeline surfaces: `apps/customer/.../orders/[id]/_components/dispatch-timeline.tsx` (admin-pasted tracking from M13-P06 rendered for customer), `services/api/tests/test_order_jobs.py`
Jobs idempotent under re-run/overlap; skip disputed/held orders; batch-safe (LIMIT + cursor); dispatch timeline shows courier + tracking note + status updates.
**AC:** re-running jobs never double-fires transitions/releases; held orders untouched; customer sees dispatch updates ≤1min after admin entry.
**Tests:** double-run idempotency, dispute skip, window boundary (47h59m vs 48h01m), timeline render.
