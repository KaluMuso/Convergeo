> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0019` (dispute-status widen) this wave.** **Run the FULL `uv run pytest` before reporting.**

# M09-P09 — Disputes

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **`disputes` table EXISTS (0007_trust_ops.sql:34):** `order_id`, `opener_user_id`, `evidence_paths text[]`, `vendor_response text`, `admin_decision text`, `status text` — **current CHECK = `('open','vendor_responded','resolved_refund','resolved_release','rejected')`** (default `'open'`). RLS: parties select (order customer + fulfilling vendor), opener insert, admin all.
- **⚠ Status widen (migration `0019_dispute_status_states.sql`):** the spec state machine is `open → vendor_responded → under_review → resolved(refund|release|partial)`. The enum is **missing `under_review` and `resolved_partial`.** **Additive-safe = DROP the CHECK + re-add the widened set:** `('open','vendor_responded','under_review','resolved_refund','resolved_release','resolved_partial','rejected')`. Reversible (documented in the migration header). Keep `'open'` (NOT `'opened'`) to match the existing default.
- **⚠⚠ CRITICAL escrow-hold integration (edit `escrow/release.py` — you are the SOLE W13 editor of it):** the release engine holds escrow via `OPEN_DISPUTE_STATUSES = frozenset({"open", "vendor_responded"})` (`release.py:19`, queried in `_has_open_dispute`). **`under_review` is NOT in that set** — a dispute under admin review would leak escrow (auto-release during review). **You MUST add `under_review`** → `frozenset({"open", "vendor_responded", "under_review"})`. Resolved/rejected statuses stay OUT (release resumes after resolution). This is the "hold takes effect immediately on open + persists through review" AC.
- **Report-problem entry (M09-P06, merged `order_confirmation.py`):** `_create_dispute` currently **inserts a `disputes` row directly**. **You own the SOLE W13 edit to `order_confirmation.py`:** route not-delivered dispute creation through your **`open_dispute` service** so the guarded transition + audit + hold semantics are consistent (the row already lands in `open`, which already holds escrow — the edit makes the state machine the single write path).
- **Decision → exact ledger outcome (M08 services, merged):** `resolved_refund` → M08-P10 refund; `resolved_release` → M08-P08 `evaluate_and_release`; `resolved_partial` → partial refund + release remainder. Call the merged paths; do not reimplement ledger.
- **i18n:** dispute keys go in `orders.json` (`orders.dispute.*`) + vendor console in `vendor.json` (`vendor.disputes.*`) — **append-rule** (disjoint sections; other W13 pebbles also append to these files).
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P09. **All status changes via your guarded state machine — never raw UPDATEs** (audited).

## 2. Objective & scope

Two-sided dispute lifecycle (`open → vendor_responded → under_review → resolved(refund|release|partial)` / `rejected`) with evidence both sides (private `order-evidence` bucket), a vendor response window, and **admin decisions that execute the exact M08 ledger outcome**. **Dispute open (and under_review) holds escrow immediately** (via the `release.py` hold set). Resolution is audited; parties see only their own dispute.
**Non-goals:** no disputes console beyond the vendor detail page (admin console = M13-P05, W14), no ledger internals (call M08-P08/P10), no returns lanes (M09-P07/P08).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/disputes/__init__.py` · `services/api/app/services/disputes/state.py` (guarded transition table + actor perms + audit) · `services/api/app/services/disputes/service.py` (`open_dispute`, `vendor_respond`, `escalate_to_review`, `resolve` → M08 dispatch) · `services/api/app/routers/disputes.py` (customer open/view, vendor respond/view, admin resolve) · `apps/customer/app/[locale]/account/orders/[id]/dispute/page.tsx` · `apps/vendor/app/[locale]/disputes/page.tsx` + `apps/vendor/app/[locale]/disputes/[id]/page.tsx` · `supabase/migrations/0019_dispute_status_states.sql` · `services/api/tests/test_disputes.py`
- **Modify:** `services/api/app/services/escrow/release.py` (**add `under_review` to `OPEN_DISPUTE_STATUSES` — sole W13 editor; nothing else in this file**) · `services/api/app/routers/order_confirmation.py` (**route `_create_dispute` through `open_dispute` — sole W13 editor**) · `packages/i18n/messages/en/orders.json` (append `orders.dispute.*`, append-rule) · `packages/i18n/messages/en/vendor.json` (append `vendor.disputes.*`, append-rule)
  **Guardrail: nothing else. Do NOT touch `escrow/release.py` beyond the one `OPEN_DISPUTE_STATUSES` line, `refunds/*`/`payouts/*` internals (call merged M08), `orders/state.py`, `main.py`, `returns/*`, db.ts beyond what the `db` job regenerates from `0019`.**

## 4. Implementation spec

- **`state.py`:** transition table `open→{vendor_responded, under_review, rejected}`, `vendor_responded→{under_review, rejected}`, `under_review→{resolved_refund, resolved_release, resolved_partial, rejected}`; actor perms (customer opens; vendor responds; admin escalates/resolves); every transition writes an audit row (reuse the order-audit convention). Raw UPDATE forbidden.
- **`service.py`:** `open_dispute(...)` (validates order party, inserts `open` with `evidence_paths`, idempotent per order); `vendor_respond(...)` (`vendor_response` text + evidence, → `vendor_responded`); `escalate_to_review(...)` (→ `under_review`, admin); `resolve(..., decision)` → `resolved_refund` calls M08-P10 refund / `resolved_release` calls M08-P08 `evaluate_and_release(service_client, order_id)` / `resolved_partial` = partial refund + release remainder — each recorded in `admin_decision` + audited.
- **`disputes.py`** (auth, party/admin-scoped, uniform envelope, rate-limited): customer open+view own; vendor respond+view own; admin resolve. Evidence upload reuses the merged `order-evidence` signed-upload endpoint.
- **`0019` migration:** header documents reversibility; `alter table public.disputes drop constraint <name>;` then re-add the widened CHECK. (Confirm the existing constraint name via the table DDL.)
- **Pages:** customer dispute (open form + evidence + status timeline + trust copy); vendor disputes list + detail (respond form + evidence). 360px; copy via keys.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; **hold-beats-timer** (open/under_review escrow is not auto-released); RLS isolation (each party sees only their dispute; other party/customer → 404); decisions map to exact ledger calls; evidence private; audited transitions; no secrets.

## 10. Tests (RUN before reporting)

`test_disputes.py`: **hold-beats-timer** (order past auto-release window but `open`/`under_review` → `_has_open_dispute` true → held; assert `under_review` now holds); **resolution → correct M08 call per decision** (`resolved_refund`→M08-P10, `resolved_release`→M08-P08 `evaluate_and_release`, `resolved_partial`→both — spies); **RLS isolation** (party A cannot read party B's dispute; cross-order 404); **guarded transitions** (illegal transition rejected + audit row on every legal one); **report-problem → `open_dispute`** path (not-delivered creates via the service). Include a migration replay note if run. `pnpm --filter customer build && pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Hold takes effect immediately on open AND persists through `under_review` (release.py set updated); decision options map to exact ledger outcomes; parties see only their dispute.
- [ ] `0019` widens the status CHECK (reversible, `'open'` retained); `order_confirmation._create_dispute` routes through `open_dispute`; `orders.dispute.*` + `vendor.disputes.*` appended (append-rule); full API suite + 2 app builds green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P09 — Disputes
**STATUS/FILES/DEVIATIONS** (confirm the `0019` widen + the `release.py` `OPEN_DISPUTE_STATUSES` edit + how `order_confirmation` was rerouted) **/TESTS** (paste hold-beats-timer incl. under_review + resolution→M08-call-per-decision + RLS-isolation + guarded-transition + full-pytest tail) **/EXCERPTS** the resolve→M08 dispatch + the `OPEN_DISPUTE_STATUSES` diff — nothing else **/QUESTIONS**
