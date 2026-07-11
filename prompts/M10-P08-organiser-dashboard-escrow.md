> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 (ticketing sub-batch, dispatched after M10-FIX merged). **Touch ONLY your files below.** **Run the FULL `uv run pytest` before reporting.** **⚙ CI GATING (M10 lesson):** your `test_event_release.py` DB file must be **isolation-clean** (seed AND tear down your own rows — assume a shared Postgres running alongside other suites) and green via `uv run pytest tests/test_event_release.py` against a **real DB**. Per-pebble seeding is CI-invisible — it hid all 6 M10 ticket seam bugs. **Do NOT edit `.github/workflows/ci.yml`** — the converger wires your file into the rls-job blocking step at merge (M10-FIX pattern).

# M10-P08 — Organiser dashboard-lite & event escrow timing

## 1. Context

**Grounded against as-built `master`:**

- **Escrow release engine MERGED (M08-P08, `services/escrow/release.py`):** `evaluate_and_release(service_client, order_id, *, now)` is **order-delivery-based** (`delivered + 48h` / `shipped + 7d`), posts via `LedgerTemplate.RELEASE_TO_VENDOR` under idempotency key **`release-{order_id}`**, and holds on open disputes (`OPEN_DISPUTE_STATUSES`). **Ticket orders have no delivered/shipped events**, so the order engine never auto-releases them — event release is a **separate, event-date-based path** you add.
- **⚠ MONEY SEAM — no double-release:** your `event_release.py` must use **distinct idempotency keys** (e.g. `event-release-{order_id}-full`, `event-release-{order_id}-phase1`, `-phase2`) so it can never collide with or double-post against the order engine's `release-{order_id}`. Reuse `post_transaction` + `RELEASE_TO_VENDOR` (the sole ledger write path) — never raw ledger writes. Respect dispute/cancellation holds.
- **Timing rules (D5):** event instance `starts_at` (`event_instances`, 0004) is the anchor. **Event ≤14 days out at purchase → release T+24h post-event (single full release).** **Event >14 days out → 50% at T-7d, 50% at T+1d** (two phased releases, distinct keys). **Cancelled event → block releases + flag mass refund (admin-executed).**
- **Escrow held from M10-P03 ticket purchase** (commission snapshot 5%/0% already set). Organiser sees **pending vs released** split (ledger-derived, like M12-P08).
- **Run by an internal tick** (mirror `internal_order_jobs.py` — token-guarded, batch, idempotent), scheduled by n8n.
  Spec: `docs/plan/02-pebbles/M10-events-ticketing.md` §M10-P08. **i18n `vendor` (append-rule):** append `vendor.eventDashboard.*` (M10-P05 also appends to `vendor.json` — disjoint sections).

## 2. Objective & scope

Organiser dashboard-lite (sales by type, revenue `formatK`, check-in progress, pending/released escrow split) + **event escrow timing** plugged in as event-date rules: ≤14d → full release T+24h; >14d → 50% T-7d + 50% T+1d; cancellation blocks releases + flags mass refund. Correct ledger posts on schedule, no double-release.
**Non-goals:** no change to the order-based release engine (`release.py` — parallel path only), no ticket purchase/verify (M10-P03/P06), no admin refund execution (event cancel only _flags_ it).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/escrow/event_release.py` (timing rules + phased ledger posts via `post_transaction`/`RELEASE_TO_VENDOR`, distinct idempotency keys, dispute/cancel holds) · `services/api/app/routers/internal_event_release.py` (internal-token tick: batch event orders due for release) · `services/api/app/routers/organiser_stats.py` (organiser-scoped sales/check-in/escrow-split) · `apps/vendor/app/[locale]/events/[id]/dashboard/page.tsx` (+ `_components/*`) · `infra/n8n/event-release.json` (cron) · `services/api/tests/test_event_release.py`
- **Modify (APPEND-RULE):** `packages/i18n/messages/en/vendor.json` (append `vendor.eventDashboard.*`)
  **Guardrail: nothing else. Do NOT edit `release.py` (M08-P08 — parallel path; if a shared hold-check helper is needed, import it read-only), ledger `templates.py`, `purchase.py`/`ticket_verify.py`, `main.py`, other `infra/n8n/*`, db.ts. No migration (timing derives from `starts_at` + ledger; event status from `events.status`).**

## 4. Implementation spec

- **`event_release.py`:** `evaluate_event_release(service_client, order_id, *, now)` — resolve the event instance `starts_at` + the ≤14d/>14d branch (decided at purchase time — snapshot the branch or derive from purchase vs starts_at); compute due phase(s); if event `status='cancelled'` → **no release** (flag mass refund via an admin-visible marker); if a dispute holds → skip; else `post_transaction(idempotency_key=…, template=RELEASE_TO_VENDOR, order_id, amount_ngwee=<full or 50%>, vendor_id)`. **Phased 50/50 uses integer-exact halves (first = floor, second = remainder — sum == net, no ngwee lost).** Idempotent (re-run posts each phase at most once via its distinct key).
- **`internal_event_release.py`:** `POST /internal/event-release/tick` (internal token) → batch event ticket-orders whose next phase is due, call `evaluate_event_release`. `event-release.json` cron.
- **`organiser_stats.py`** (auth, organiser-scoped): sales by ticket type, revenue (`formatK`), check-in progress (issued vs checked_in), **pending vs released escrow** (ledger-derived). Cross-organiser → 403.
- **Dashboard page:** 360px, live-ish poll for check-in count; copy via `vendor.eventDashboard.*`.

## 5–9. Security etc.

Organiser-scoped stats; **no double-release** (distinct keys vs `release-{order_id}`); 50/50 integer-exact (no float, no lost ngwee); cancelled event blocks releases + flags refund; dispute hold respected; internal tick token-guarded; stats match ticket truth; no secrets.

## 10. Tests (RUN before reporting)

`test_event_release.py`: **timing matrix** (13d-out order → single full release at T+24h; 15d-out → 50% at T-7d + 50% at T+1d, halves sum to net); **cancellation hold** (cancelled event → no release + refund flag); **dispute hold** respected; **idempotent re-run** (each phase posts once — distinct keys, never collides with `release-{order_id}`); **stats aggregation** (sales/check-in/escrow-split match fixtures); organiser authz. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Both timing branches post correct ledger transactions on schedule; cancelled event blocks releases + flags mass refund; stats match ticket truth.
- [ ] Distinct idempotency keys (no double-release vs order engine); 50/50 integer-exact; `release.py` untouched; `vendor.eventDashboard.*` appended (append-rule); vendor build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M10-P08 — Organiser dashboard-lite & event escrow timing
**STATUS/FILES/DEVIATIONS** (how the ≤14d/>14d branch is decided + snapshotted; the exact idempotency keys vs `release-{order_id}`; 50/50 rounding; how event release stays off the order engine) **/TESTS** (paste timing-matrix + cancellation-hold + dispute-hold + idempotent-rerun + stats + full-pytest tail) **/EXCERPTS** the phased release with distinct keys + integer-exact halves — nothing else **/QUESTIONS**
