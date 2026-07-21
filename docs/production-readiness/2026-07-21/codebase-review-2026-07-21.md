# Codebase Review vs `docs/plan` — 2026-07-21

**HEAD:** `d7891b8` (Merge #400) · **Reviewer:** Claude (architect/reviewer role) · **Method:** 4 parallel assessment agents (launch-readiness, docs↔code drift, documented-debt verification, money/quality scan) + direct code verification of every money-path claim.

> **One-line verdict:** The **code is disciplined and materially AHEAD of its own planning docs.** The five previously-documented code debts are all fixed; ~90% of the "open code gaps" in the 2026-07-20 readiness docs are already closed at HEAD. The genuinely-open *code* work is narrow (5 items below). The real launch blocker is unchanged and correctly documented elsewhere: **deploy + live money/ops proof + founder/legal gates — none of which is repo code.**

This document is the reconciliation the `2026-07-20/gap-analysis-vs-docs.md` and `2026-07-20/master-vs-docs-representation-report.md` need: they assess an older tree (~#350–352 era, migration ledger ≤`0063`) and now list many closed items as open. **For current truth prefer `2026-07-20/current-implementation-board.md` + this file over the two gap docs.**

---

## 1. Documented code-debts — all CLOSED at HEAD

The `00-status.md` "carried code debts" and `master-vs-docs` open list are stale. Verified against current files:

| Debt (as documented) | Status | Evidence |
| --- | --- | --- |
| `account/privacy/page.tsx` references ~23 missing `account.privacy.export.*`/`delete.*` i18n keys (runtime `MISSING_MESSAGE`) | ✅ FIXED | All keys present `packages/i18n/messages/en/account.json:121-163` |
| `embedding_jobs` / `reconciliation_reports` lack RLS-matrix rows | ✅ FIXED | `tests/rls/test_matrix.py:619`, `:1662`; `test_no_untested_tables` passes |
| Orphan components `report-review` / `accept-flow` / `claim-banner` never mounted | ✅ FIXED | Wired via `reviews-section.tsx:156`, `account/jobs/[id]/page.tsx:226`, `account/tickets/page.tsx:91` |
| ~12 vendor components on raw Tailwind palette (won't dark-theme) | ✅ FIXED | Zero `neutral-*`/`red-*`/`emerald-*`/`amber-*`/`gray-*` in `apps/vendor/**` |
| Desktop cart-count badge unwired / hardcoded to 0 | ✅ FIXED | Live via `useCartStore()` → `getCartItemCount()` `desktop-header.tsx:46-181` |

Additionally closed since the 07-20 gap docs were written: FORCE RLS on the 3 launch tables (`0064`), refund `source_key` uniqueness (`0065`), wishlist/recently-viewed (`0066`), server-side demo exclusion for products/listings/vendors, both prescribed E2E specs (`checkout-false-success`, `critical-path`), `zh` de-route from the public switcher, uptime-webhook auth + money error-alert n8n JSONs, and the OpenGraph Edge Function slimmed under 1 MB (`2ac18e7`). **These should be struck from the open lists.**

---

## 2. Genuinely-open CODE items (ranked) — the actual "improvements"

| # | Item | Sev | Where | Fix size | Prompt |
| --- | --- | --- | --- | --- | --- |
| 1 | **Demo services/events leak into public search** — `drop_demo_listing_hits` has no `service`/`event` branch (only `listing`/`product`/`vendor`); demo marker is image-`public_id` based, which service/event rows don't carry. `Laptop & Phone Repair (demo)` surfaces in live `/search`. | High (trust/discovery) | `services/listings/demo.py:125-163`; `services/search/__init__.py`; `services/ask/retrieve.py`; `routers/catalog.py` | S | `FIX-H` |
| 2 | **Restocking-fee unit divergence (bps vs pct).** `returns/lane2.py` uses `restocking_fee_pct` (whole %, clamp 5–15) and falls back to `bps // 100` (lossy) when the pct key is absent; `refunds/math.py` + `disputes/service.py` use `restocking_fee_bps` (clamp 500–1500). Same order refunded via returns vs disputes diverges at sub-percent granularity (e.g. 1250 bps → 12% vs 12.5%). Bounded but real. | High (money consistency) | `services/returns/lane2.py:20-25,113-150`; `services/refunds/{config,math}.py`; `services/disputes/service.py:167` | S–M | ✅ **DONE** (`FIX-I` implemented on this branch: lane2 unified on bps, 19/19 tests + regression golden green) |
| 3 | **Non-atomic state transitions on KYC + Returns.** Orders/Disputes are compare-and-swap / row-locked; **KYC** (`kyc/state_machine.py` `_update_vendor`) and **Returns lane-1 approve/reject** are read-then-write with no CAS. The `guard_vendor_status_update` trigger early-returns for `service_role`, so it does not backstop the KYC matrix. Concurrent transitions can both pass the guard. | Med (race safety) | `services/kyc/state_machine.py:279-289,424-475`; `services/returns/lane1.py:410-424,512` | S + tests | `FIX-J` |
| 4 | **Event cancellation / schedule-change notifications are placeholders.** `TODO(M14)` emits a `"todo"` template token instead of a real WhatsApp template, so organisers/buyers aren't properly notified on cancel/reschedule. (Live send still needs founder gate F5, but the mapping is code.) | Med | `services/events/cancellation.py:29,153`; `routers/organiser_events.py:581` | S | `FIX-K` |
| 5 | **Vernacular `legal` namespace missing (bem/nya).** 13/17 namespaces localized; `admin`/`ai`/`vendor`/`legal` remain. `legal` (+ checkout consent) is the D27 public-launch soft-blocker; it needs **human native review**, not MT. EN deep-merge fallback means no runtime break today. | Med (launch soft-block) | `packages/i18n/messages/{bem,nya}/` | M (human) | founder action + optional scaffold |

**Lower-signal (hygiene, optional):** `admin_orders.py:680` ledger-engine stub `TODO(M08-P05)`; `sell/_components/commission-rates.ts:4` commission rates hardcoded pending live-config bind; undocumented floor-vs-half-up rounding policy (intentional but unwritten); CSP nonce **enforce** promotion (report-only already landed — needs a clean RO-violation window before flipping, so it's evidence-gated not code-gated).

**Not code (config/ops):** `/search?degraded=true` is honest behavior — resolves when the embeddings cron is active + `OPENROUTER_API_KEY` is healthy, not by a code change.

---

## 3. The real launch lever (unchanged — not repo code)

Every *engineering* launch gate in `docs/plan/launch-checklist.md` is green/tested (RLS isolation, ledger Σ=0, oversell race, invoice-gapless-under-concurrency, prohibited-category block, beta capacity-race). What remains, per `2026-07-20/go-no-go-report.md` (verdict **NO_GO**) and `2026-07-21/api-recovery-and-ops.md`:

- **Deploy/promote:** promote customer/vendor/admin to master tip (OG fix already merged — this is now an ops redeploy); record API image digest + git SHA (`/fingerprint` still `git_sha=unknown`); activate the money n8n workflows (6/8 active, payment-reconciliation + error-alert unpublished).
- **Live ops proof (all NOT_RUN):** Lenco sandbox money/KYC/false-success drills (S1–S6), backup + ≤30-min restore, rollback drill, k6 load p95<500ms @100cc, Sentry/UptimeRobot live capture.
- **Founder/legal (P0):** F9b Lenco creds, F5 WhatsApp templates, F2 PACRA+TPIN, F4 escrow counsel (NPS Act 2026), Sentry projects + DSNs, UptimeRobot monitors.
- **Live flags (unchanged):** `public_launch=false`, `zamtel_collections=false`, `cod_cap_ngwee=50000`; money tables all `0`; live DB tip `0066` (trails master).

---

## 4. Fix-prompt index (parallel-safe — disjoint file ownership, no migrations, no `db.ts`)

`prompts/fixes/FIX-H-demo-service-event-exclusion.md` · `FIX-I-restocking-fee-unit-unify.md` (✅ **already implemented on this branch**) · `FIX-J-kyc-returns-transition-atomicity.md` · `FIX-K-event-cancellation-notifications.md`. All branch from + PR against `master`, touch disjoint files, and can run concurrently.

**FIX-H / FIX-J / FIX-K were left as prompts on purpose:** each needs a live Postgres to verify its behaviour (FIX-H demo-exclusion queries; FIX-J two-thread compare-and-swap concurrency proof; FIX-K outbox-backed notification tests). This review environment has no Postgres server, so shipping them unverified on the discovery / state-machine / money-adjacent paths would violate the heightened-review bar. Run them in Cursor/CI where the DB-backed tests execute. **FIX-I** was pure-Python and fully verified, so it was implemented directly.
