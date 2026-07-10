> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 14 runs 9 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M11-P02 — Post-a-job (RFQ)

## 1. Context

**Wave 14 (parallel ×9).** Grounded against as-built `master`:

- **`jobs` table EXISTS (0004:33):** `status ('open','quoted','accepted','completed','cancelled')`, `budget_band_min/max_ngwee`, category. RLS present. **No migration** — the 7d-expiry `expired` state maps via a job that transitions stale `open` jobs (no new enum value: use `cancelled` with an expiry note, OR confirm the enum — **the enum has no `expired`; use `cancelled` + `resolve_snapshot`/note to mark expiry** to stay additive). `job_quotes` (0004:62) exists for M11-P03.
- **⚙ Depends on M11-P01 (parallel):** matching selects from `services`/vendors by category + service-area. Code against the merged `services` schema (M11-P01 adds UI, not schema) — no code import from P01.
- **Broadcast:** match providers by **category + service-area**, **cap ~8** (config), rank by **badge/rating/proximity**, notify via the **merged outbox** (`enqueue_outbox_row` / notification path). No matches → honest "we'll notify you" + admin visibility.
- **Auth (M04 merged):** guest can DRAFT, must auth to POST. Owner-only sees own job pre-quote.
  Spec: `docs/plan/02-pebbles/M11-services-rfq.md` §M11-P02. **i18n `services` (append-rule):** append `services.postJob.*` (M11-P01 also appends to `services.json` — disjoint sections).

## 2. Objective & scope

Post-a-job RFQ: near-zero-friction form (description, category, date, budget band, optional photos), **provider matching** (category + service-area, cap ~8, ranked, outbox-notified), job lifecycle (`open→quoted→accepted→completed|cancelled|expired-7d`), guest-draft→auth-to-post.
**Non-goals:** no quotes submit/compare (M11-P03), no service listings UI (M11-P01), no new schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/services/post-job/page.tsx` (form) · `services/api/app/services/rfq/broadcast.py` (match + cap + rank + outbox notify) · `services/api/app/routers/jobs.py` (post/get/lifecycle, authz) · `services/api/app/routers/internal_job_jobs.py` (internal-token: 7d-expiry tick) · `services/api/tests/test_rfq.py`
- **Modify (APPEND-RULE — disjoint section):** `packages/i18n/messages/en/services.json` (append `services.postJob.*`)
  **Guardrail: nothing else. Do NOT touch `services_listings.py`/service pages (M11-P01), `job_quotes` logic (M11-P03), the outbox dispatcher (call `enqueue_outbox_row`), `main.py`, schema/db.ts. No migration (expiry via `cancelled`+note).**

## 4. Implementation spec

- **`broadcast.py`:** `match_providers(*, category, service_area, cap)` — select active `services`/vendors by category ∩ service-area, rank by badge/rating/proximity, **cap ~8 (config)**; `broadcast_job(job_id)` → enqueue outbox notifications to matched providers; **no matches → mark for admin visibility + honest ack** (no silent drop).
- **`jobs.py`** (auth, uniform envelope, rate-limited): `POST /jobs` (auth required — guest draft is client-side until auth), owner reads own; lifecycle transitions (guarded, audited if applicable). Owner-only sees own job pre-quote.
- **`internal_job_jobs.py`:** `POST /internal/jobs/expire-tick` (internal-token) → transition stale `open` jobs >7d to closed (`cancelled` + expiry note) with notice; idempotent batch.
- **Form:** minimal-friction (360px), photos optional (merged media seam), budget band; copy via `services.postJob.*`.

## 5–9. Security etc.

360px; **cap respected**; no-match → honest ack + admin visibility (no silent drop); auth-to-post; **owner-only pre-quote visibility** (authz test); internal expiry token-guarded; no secrets.

## 10. Tests (RUN before reporting)

`test_rfq.py`: **matching/cap logic** (category ∩ area, ranked, capped at ~8; no-match → ack+admin flag); **expiry job** (>7d open → closed with notice, idempotent); **authz** (only owner sees own job pre-quote; guest cannot post). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Cap respected; no matching providers → honest "we'll notify you" + admin visibility; job expiry auto-closes with notice.
- [ ] `services.postJob.*` appended (append-rule); expiry via `cancelled`+note (no migration); customer build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M11-P02 — Post-a-job (RFQ)
**STATUS/FILES/DEVIATIONS** (matching/rank/cap source; how expiry maps without an enum value; outbox notify) **/TESTS** (paste matching-cap + expiry + authz + full-pytest tail) **/EXCERPTS** the `match_providers` cap+rank + the expiry transition — nothing else **/QUESTIONS**
