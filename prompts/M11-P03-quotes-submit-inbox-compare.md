> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 15 runs pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M11-P03 — Quotes: submit, inbox, compare

## 1. Context

**Wave 15 (parallel).** Grounded against as-built `master`:

- **`job_quotes` table EXISTS (0004:62):** `amount_ngwee > 0`, `status ('submitted','accepted','declined','expired')`, job ref, provider ref. **RLS proven (M03-P03):** provider A **cannot read provider B's quote** — enforce at the API layer too (explicit authz test, not just RLS).
- **Jobs/RFQ MERGED (M11-P02):** `jobs` + `broadcast` (matched providers). This pebble = the quote lifecycle on top: providers quote on matched jobs, customer compares.
- **Money = integer ngwee.** Response-time badge / rating come from M11-P01 (merged) — reuse for compare cards.
- **i18n `vendor` (append-rule):** vendor jobs inbox → `vendor.jobs.*`; customer compare → `services.json` (`services.quotes.*`). **M15-P01 also appends to `vendor.json` this wave — disjoint sections.**
  Spec: `docs/plan/02-pebbles/M11-services-rfq.md` §M11-P03.

## 2. Objective & scope

Quote lifecycle: provider submits a quote (amount, message, validity) on a matched job; customer compares quotes **side-by-side** (price, rating, badge, response time); decline-with-reason optional; quote **withdrawal before acceptance**. **Providers never see rivals' quotes** (RLS + API-layer authz).
**Non-goals:** no accept→deposit/escrow (M11-P04), no job posting/broadcast (M11-P02 merged), no service listings (M11-P01).

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/routers/quotes.py` (submit/withdraw/list-own; customer compare fetch) · `apps/vendor/app/[locale]/jobs/page.tsx` (matched-jobs inbox + quote form) · `apps/customer/app/[locale]/account/jobs/page.tsx` (list) + `account/jobs/[id]/page.tsx` (compare cards) · `services/api/tests/test_quotes.py`
- **Modify (APPEND-RULE — disjoint sections):** `packages/i18n/messages/en/vendor.json` (append `vendor.jobs.*`) · `packages/i18n/messages/en/services.json` (append `services.quotes.*`)
  **Guardrail: nothing else. Do NOT touch `jobs.py`/`rfq/broadcast.py` (M11-P02), `job_quotes` schema, `main.py`, db.ts. No migration.**

## 4. Implementation spec

- **`quotes.py`** (auth, RLS + explicit authz, uniform envelope, rate-limited): `POST /jobs/{id}/quotes` (provider submit — amount_ngwee >0, message, validity) on a job they were matched to; `POST /quotes/{id}/withdraw` (before acceptance); `GET /jobs/{id}/quotes` — **provider sees ONLY their own** (assert at API), **customer (job owner) sees all**; decline-with-reason optional. Withdrawn/expired quotes drop from compare.
- **Pages:** vendor jobs inbox (matched jobs + quote form, 360px); customer compare (quote cards side-by-side sorted by price/rating, withdrawn excluded). Copy via `vendor.jobs.*` / `services.quotes.*`; money via `formatK`.

## 5–9. Security etc.

360px; **rival-quote isolation proven at the API layer** (provider A fetching a job's quotes → own only); compare sorts by price/rating; withdrawn quotes excluded; owner-only customer view; no float; no secrets.

## 10. Tests (RUN before reporting)

`test_quotes.py`: **isolation** (provider A `GET /jobs/{id}/quotes` → only own quote; provider B's invisible); **quote validity expiry** (expired → dropped from compare); **compare ordering** (price/rating sort); withdrawal before acceptance; authz (non-matched provider cannot quote; non-owner customer cannot view). `pnpm --filter customer build && pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Rival-quote isolation proven at API layer too; compare sorts by price/rating; withdrawn quotes drop from compare.
- [ ] `vendor.jobs.*` + `services.quotes.*` appended (append-rule); 2 app builds + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M11-P03 — Quotes: submit, inbox, compare
**STATUS/FILES/DEVIATIONS** (how API-layer rival isolation is enforced beyond RLS; validity/expiry handling) **/TESTS** (paste isolation + validity-expiry + compare-ordering + withdrawal + full-pytest tail) **/EXCERPTS** the provider-scoped quote fetch (own-only) — nothing else **/QUESTIONS**
