> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA: you own migration `0021` (vendor payout method + hold) this wave.** **Run the FULL `uv run pytest` before reporting.**

# M12-P08 — Payouts view & statements

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **Ledger is the single source of truth (M08-P05, merged).** Balances (**escrow-held vs released vs paid-out**) are **ledger-derived** — sum the relevant accounts (`escrow`, `vendor_payable/{vendor}`, payout postings). **No parallel balance bookkeeping.** The property to hold: view sums == ledger account balances.
- **`payouts` table EXISTS (0006_money.sql:78):** `vendor_id`, `amount_ngwee`, `rail ('mtn','airtel','zamtel','card','cod')`, `lenco_reference`, `status ('pending','processing','paid','failed')`, `resolve_snapshot jsonb`. RLS: vendor reads own; writes service-role only. Payout **execution** = M08-P09 (merged); refund→payout wiring is a known debt (out of scope here).
- **No payout-method storage on `vendors`** (columns: slug/display_name/status/kyc_tier/caps_snapshot…). **Migration `0021_vendor_payout_method.sql`:** additive — add `payout_msisdn text`, `payout_rail text check (payout_rail in ('mtn','airtel','zamtel') or null)`, `payout_hold_until timestamptz` to `vendors` (all nullable). Reversible header. **First check M08-P09's payout executor for where the destination is sourced and align — do not contradict it** (if it already reads a destination, extend rather than duplicate; report what you found).
- **Method change = fraud vector:** MoMo number change → **OTP re-auth + 24h payout hold + notification.** Set `payout_hold_until = now()+24h` on change; block payouts while held. **Enforcement:** your `vendor_payouts.py` refuses to surface/initiate payouts while held; add a **single guard** honouring `payout_hold_until` in M08-P09's payout-initiation path (**you are the sole W13 editor of that file** — if its shape is unclear, add the guard where a payout row is created + leave a precise `TODO`). Re-verify the new number via the merged Lenco `/resolve` seam + a cooldown guard.
- **Statement download:** CSV now (ledger-derived, per month); **PDF = M15-P07 (stub the PDF link)**.
- **i18n:** `vendor.json` (`vendor.payouts.*`, append-rule).
  Spec: `docs/plan/02-pebbles/M12-vendor-portal.md` §M12-P08. **Money = integer ngwee; `formatK` display; no float.**

## 2. Objective & scope

Vendor **payouts view** (ledger-derived balances: escrow-held / released / paid-out; payout history with status; **monthly statement CSV**) + **payout-method management** (MoMo number change → OTP re-auth + **24h hold** + notification + re-verify). Everything **ledger-backed** — no parallel bookkeeping.
**Non-goals:** no payout execution (M08-P09), no refund→payout wiring (separate debt), no PDF render (M15-P07 — stub), no admin payout ops.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/vendor/app/[locale]/payouts/page.tsx` (balances + history + statement CSV download) · `apps/vendor/app/[locale]/payouts/method/page.tsx` (method change → OTP + hold notice) · `apps/vendor/app/[locale]/payouts/_components/` (your files) · `services/api/app/routers/vendor_payouts.py` (balances/history/statement/method-change) · `supabase/migrations/0021_vendor_payout_method.sql` · `services/api/tests/test_vendor_payouts.py`
- **Modify:** `services/api/app/services/payouts/…` M08-P09 initiation path (**add ONLY the `payout_hold_until` guard — sole W13 editor; if uncertain, guard at row-creation + `TODO`**) · `packages/i18n/messages/en/vendor.json` (append `vendor.payouts.*`, append-rule)
  **Guardrail: nothing else. Do NOT touch ledger engine internals (M08-P05 — read via the query seam), `payouts` schema beyond `0021` on `vendors`, refund/clawback code, `main.py`, other vendor pages, db.ts beyond `0021`.**

## 4. Implementation spec

- **`vendor_payouts.py`** (auth, vendor-owned, uniform envelope, rate-limited): `GET /vendor/payouts` (balances **derived from ledger** — escrow-held, released-available, paid-out; property: sums == account balances); `GET /vendor/payouts/history`; `GET /vendor/payouts/statement?month=YYYY-MM` (CSV, ledger-derived, ngwee-exact); `POST /vendor/payouts/method` (OTP re-auth required → update `payout_msisdn`/`payout_rail`, `payout_hold_until=now()+24h`, re-verify via `/resolve` + cooldown, emit notification). **Held → payouts blocked** (guard in M08-P09 path + surfaced in view).
- **Pages:** balances card (escrow-held / released / paid-out via `formatK`), payout history with status chips, statement month picker + CSV download, method page with OTP + explicit "payouts paused 24h" copy + PDF-statement stub. 360px. Copy via `vendor.payouts.*`.
- **`0021` migration:** additive nullable payout-method + hold columns; reversible header.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; **balances = ledger truth exactly** (property test: view sums == account balances); method change → OTP + 24h hold + notification; statement math == ledger; vendor-owned (cross-vendor → 404); no float; no secrets.

## 10. Tests (RUN before reporting)

`test_vendor_payouts.py`: **balance derivation vs fixtures** (escrow-held/released/paid-out sums == ledger accounts); **method-change hold** (change → `payout_hold_until` set + payout blocked while held + notification emitted); **statement generation** (CSV ngwee-exact == ledger for a month); **authz** (cross-vendor rejected); `0021` replay note. `pnpm --filter vendor build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Balances == ledger truth exactly (property: view sums == account balances); method change triggers hold + notice; statement math matches ledger.
- [ ] `0021` adds payout-method + hold columns (additive, nullable, aligned with M08-P09); hold guard added to the payout path; `vendor.payouts.*` appended (append-rule); vendor build + full API suite green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M12-P08 — Payouts view & statements
**STATUS/FILES/DEVIATIONS** (note where M08-P09 sources the payout destination + how the `payout_hold_until` guard was wired + `0021`) **/TESTS** (paste balance-derivation-vs-ledger + method-change-hold + statement-generation + authz + full-pytest tail) **/EXCERPTS** the ledger-derived balance query + the hold guard — nothing else **/QUESTIONS**
