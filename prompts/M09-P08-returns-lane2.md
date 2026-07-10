> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 13 runs 8 pebbles in parallel — **touch ONLY your files below**. **Run the FULL `uv run pytest` before reporting.**

# M09-P08 — Returns lane 2 (change-of-mind)

## 1. Context

**Wave 13 (parallel ×8).** Grounded against as-built `master`:

- **Vendor opt-in flag EXISTS on listings (0003_catalog.sql:99–100):** `returnable boolean not null default false`, `return_window_hours integer`. **No migration** — you read these. Window per D-spec is 48h–7d; use `return_window_hours` (fallback/clamp to 48–168h if null/out-of-range).
- **`returns` table EXISTS (0007:57)** with `lane int check (1,2)`, `fee_breakdown jsonb`, `status` — lane-2 rows are `lane=2`. **You do NOT own `returns.py` or `return/page.tsx`** (M09-P07 owns both). You own **`lane2.py`** (imported by P07's `returns.py` via the ⚙ seam) + the **returnable badge** on the PDP.
- **⚙ Same-wave seam (M09-P07):** P07's `returns.py` lane-2 branch imports `app.services.returns.lane2` (import-guarded). Your `lane2.py` must expose the exact contract P07 calls: `check_eligibility(...)` + `compute_lane2_breakdown(...)` + `create_lane2_return(service_client, *, order_item_id, customer_id)`. Keep the signatures self-describing; P07 verifies integration in Phase 4.
- **Refund (lane 2) = `item − outbound_delivery − return_transport − restocking`.** Restocking = **config 5–15%, default 10%**, computed server-side, **integer ngwee, `Decimal`/rounding rules only — no float**. Itemized breakdown shown to the customer **before they commit**, and it must equal the M08-P10 lane-2 execution exactly.
- **Restocking config seam:** read the restocking pct from platform config if a key exists; otherwise use the module default `10` clamped to `[5,15]` (leave a `TODO` config key). Do not add a migration for it.
  Spec: `docs/plan/02-pebbles/M09-orders-fulfilment.md` §M09-P08.

## 2. Objective & scope

Lane-2 (change-of-mind) return: **eligibility** (listing `returnable` on + within window + unused declaration) → **server-side itemized refund** (`item − outbound delivery − return transport − restocking`) shown before commit → `returns` row (lane 2) via the merged M08-P10 lane-2 path. Surface a **returnable badge** on the PDP for eligible listings.
**Non-goals:** no `returns.py` router (M09-P07 owns; you're imported by it), no lane-1 logic, no refund-engine internals (M08-P10), no dispute/arbitration.

## 3. Files (create/modify ONLY these)

- **Create:** `services/api/app/services/returns/lane2.py` (eligibility + fee math + return creation) · `apps/customer/app/[locale]/(shop)/p/[slug]/_components/returnable-badge.tsx` (shows "Returnable within N days" when `returnable` on) · `services/api/tests/test_returns_lane2.py`
- **Modify (APPEND-RULE — disjoint nested section only):** `packages/i18n/messages/en/catalog.json` (append `catalog.returnableBadge.*`)
  **Guardrail: nothing else. Do NOT create/edit `returns.py` or `return/page.tsx` (M09-P07), `refunds/*` internals (M08-P10 — the breakdown must match its execution), `lane1.py`, PDP `page.tsx` (add ONLY the badge component file), `main.py`, schema/db.ts.**

## 4. Implementation spec

- **`lane2.py`:** `check_eligibility(service_client, *, order_item_id, customer_id)` → listing `returnable` true + within `return_window_hours` + owner-scoped (else ineligible reason). `compute_lane2_breakdown(*, item_ngwee, outbound_delivery_ngwee, return_transport_ngwee, restocking_pct)` → `{item, outbound_delivery, return_transport, restocking, refund_ngwee}` **integer-exact** (restocking = floor/round-half-even per money convention on `item_ngwee`; refund = item − outbound − return_transport − restocking, clamped ≥0). `create_lane2_return(...)` inserts `returns` row `lane=2`, `fee_breakdown` = the breakdown, then invokes **M08-P10 lane-2** — the executed refund must equal `refund_ngwee`.
- **`returnable-badge.tsx`:** renders only when `returnable` true; shows window in days; token-styled; no layout shift.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px; ineligible listings show **no** lane-2 option / no badge; breakdown ngwee-exact = execution (**no float**); owner-scoped; window boundary respected; no secrets.

## 10. Tests (RUN before reporting)

`test_returns_lane2.py`: **eligibility matrix** (flag off → ineligible, window expired → ineligible, owner mismatch → ineligible); **fee math goldens** (restocking 5/10/15% on representative amounts, integer-exact, clamp ≥0); **breakdown = M08-P10 lane-2 execution** (spy/assert equality); restocking default+clamp. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Ineligible listings show no lane-2 option; breakdown ngwee-exact matches M08-P10 execution; window boundary respected.
- [ ] `lane2.py` exposes the eligibility+breakdown+create contract P07 imports; `catalog.returnableBadge.*` appended (append-rule); full API suite + customer build green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M09-P08 — Returns lane 2 (change-of-mind)
**STATUS/FILES/DEVIATIONS** (note the exact `lane2.py` contract P07 imports + how the breakdown ties to M08-P10 lane-2 + restocking config source) **/TESTS** (paste eligibility-matrix + fee-math goldens + breakdown=execution + full-pytest tail) **/EXCERPTS** the `compute_lane2_breakdown` fee math — nothing else **/QUESTIONS**
