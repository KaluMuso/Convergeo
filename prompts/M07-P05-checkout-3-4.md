> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 9 runs 6 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — no migration. Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M07-P05 — Checkout steps 3–4 (payment method & review)

## 1. Context

**Wave 9 (parallel ×6).** Grounded against as-built `master`:

- **Checkout front half merged (M07-P04, W8):** `apps/customer/app/[locale]/(shop)/checkout/page.tsx` (stepper shell) + `checkout/_components/{step-contact,step-fulfilment,reservation-countdown}.tsx` + `services/api/app/routers/checkout.py` (session init + step validation). You **add steps 3–4** to the stepper (wire into `page.tsx`) + two new step components; server totals/fees come from the existing checkout session — **you do NOT recompute them**.
- **COD cap:** `platform_config.cod_cap_ngwee` = **50000** (K500) (0008). COD is **gated ≤ cap on the ORDER TOTAL** and **server re-validated** (a tampered client cannot force COD above cap). Rails: MoMo **MTN + Airtel** only; **Zamtel hidden pending F9a**; card = hosted-widget explainer (no card fields — PCI). Payer number `+260` validation.
- `(shop)` group exists; routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). i18n `checkout` namespace registered — **you solely own `checkout.json` this wave** (append a nested `payment` + `review` block; do NOT reformat the `cart`/`checkout` siblings).
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P05. **No order creation / payment execution (M07-P06 + M08, W10) — step 4 is review + consent only.**

## 2. Objective & scope

Step 3 (payment method: MoMo rail select + payer number, card-widget explainer, **COD gated ≤K500 with a clear ineligibility message**) + step 4 (review: line items, fees, totals, **escrow trust copy** "You pay → Held by Vergeo5 → Released on delivery", T&C consent checkbox) + a method-validation endpoint that **server-re-validates COD eligibility and rail**.
**Non-goals:** no order/payment creation (M07-P06/M08), no Lenco client, no new schema, no changes to steps 1–2 logic.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/checkout/_components/step-payment.tsx` · `checkout/_components/step-review.tsx` · `services/api/app/routers/checkout_payment.py` (method + COD re-validation) · `services/api/tests/test_checkout_payment.py`
- **Modify:** `apps/customer/app/[locale]/(shop)/checkout/page.tsx` (add steps 3–4 to the stepper — M07-P04's file, merged; you are the sole checkout editor this wave) · `packages/i18n/messages/en/checkout.json` (append nested `payment` + `review` sections)
  **Guardrail: nothing else. Do NOT touch `checkout.py` / steps 1–2 components (call/extend, don't rewrite), `cart/*`, `main.py`, schema.**

## 4. Implementation spec

- **`checkout_payment.py`** (`POST /checkout/payment-method` or similar): validate the chosen method against the **server-computed order total** — **COD allowed only when total ≤ `cod_cap_ngwee`** (re-read from `platform_config`, do not trust the client); MoMo rail ∈ {mtn, airtel}; **Zamtel rejected**; payer number `+260` format. A tampered client (COD above cap, or a disabled rail) → 4xx with a typed reason. **Totals are read from the existing checkout session — never recomputed here.**
- **Step 3 (`step-payment.tsx`):** method radio; MoMo → rail + `+260` payer number; card → widget explainer (no fields); **COD hidden/disabled above cap** with the ineligibility message. **Step 4 (`step-review.tsx`):** line items + fees + totals (from the server session), escrow trust copy, T&C consent checkbox (required to advance). All copy via `checkout` (`checkout.payment.*` / `checkout.review.*`); tokens; 360px-first; **fee/total display via `formatK`, integers ngwee**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; checkout is `noindex`; **COD re-validated server-side** (client can't force it); no card fields (PCI); rail allowlist enforced server-side; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_checkout_payment.py`: **COD boundary** (total `=` cap allowed, `+1` ngwee rejected); **Zamtel rejected**, MoMo rail accepted; **payer-number validation**; **server re-validation of a tampered client** (COD above cap / disabled rail → 4xx). Component: COD hidden above cap; consent gates advance. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite.**

## 11. Acceptance criteria / DoD

- [ ] COD hidden/disabled above cap and **server re-validates** (=cap ok, +1 ngwee no); rail allowlist enforced; payer `+260` validated.
- [ ] Review totals match the server session exactly; escrow copy + consent present; `checkout.payment.*`/`checkout.review.*` nested (append-rule); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M07-P05 — Checkout steps 3–4
**STATUS/FILES/DEVIATIONS/TESTS** (paste COD-boundary + tampered-client + rail-allowlist + full-pytest tail) **/EXCERPTS** the server COD re-validation — nothing else **/QUESTIONS**
