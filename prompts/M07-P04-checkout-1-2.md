> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 8 runs 10 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN** — reuse existing tables (`checkout_groups`, `stock_reservations`, `delivery_zones`); add NO migration. **Run the FULL `uv run pytest` before reporting.**

# M07-P04 — Checkout steps 1–2 (contact & fulfilment)

## 1. Context

**Wave 8 (parallel ×10).** Grounded against as-built `master`:

- **Cart merged (M07-P01):** `cart.py` (grouped cart + server totals). **Reservations merged (M07-P02):** `app/services/stock/claim.py` (atomic claim + TTL from `platform_config.reservation_ttl_min`) + `revalidate.py`. **`delivery_zones(zone_key, label, fee_ngwee, active)`** (`0008`); free-delivery threshold in `platform_config`. **`checkout_groups`** + `stock_reservations` exist (`0005`). **Auth merged (M04-P04/P05):** OTP flow + addresses.
- The `(shop)` group exists. API routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). i18n `checkout` namespace registered; **`checkout.json` shared with M07-P03** — you own the **`checkout`** section (append-rule).
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P04. **Payment/review = M07-P05 (not this wave).**

## 2. Objective & scope

Checkout stepper shell + step 1 (contact) + step 2 (per-vendor-group fulfilment: Lusaka delivery w/ zone fee or pickup), with reservation claimed on checkout entry + a visible countdown; session-init + step-validation endpoints.
**Non-goals:** no payment method/review (M07-P05), no order creation/payment (M08), no cart page (M07-P03).

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/checkout/page.tsx` (stepper shell) · `checkout/_components/{step-contact,step-fulfilment,reservation-countdown}.tsx` · `services/api/app/routers/checkout.py` (session init + step validation) · `services/api/tests/test_checkout.py`
- **Modify:** `packages/i18n/messages/en/checkout.json` (add a nested `checkout` section — append-rule)
  **Guardrail: nothing else. Do NOT touch `cart.py`/`cart/*` (M07-P03), `app/services/stock/*` (M07-P02 — call it), `main.py`, schema.**

## 4. Implementation spec

- **`checkout.py`:** `POST /checkout/session` (init from the cart → **claim reservations** via `app.services.stock.claim` with the config TTL; return a checkout session + expiry) + step-validation endpoints. **Zone fee** resolved by GPS/landmark → `delivery_zones` (free ≥ threshold **per group**); **mixed delivery+pickup groups** supported. **Countdown expiry → return to cart with a notice** (reservations released by the M07-P02 sweeper).
- **Step 1 contact:** logged-in skip; **guest phone + inline OTP** (embed the M04 flow). **Step 2 fulfilment:** per-group Lusaka delivery (zone fee) or pickup (vendor location + landmark + hours); **visible reservation countdown**.
- All copy via `checkout` (`checkout.*`); tokens; 360px-first; **fee math ngwee-exact**.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; countdown visible; reservations claimed server-side (client can't oversell); fee math exact; no secrets.

## 10. Tests (RUN before reporting — full `uv run pytest` + ruff + mypy)

`test_checkout.py`: **zone resolution edge** (outside zones → pickup-only); **fee math ngwee-exact** per seed zones; **mixed delivery+pickup groups**; guest-OTP-in-checkout flow; reservation claim on session init + expiry→cart notice. `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full API suite.**

## 11. Acceptance criteria / DoD

- [ ] Zone fee correct per seed zones (ngwee-exact); mixed delivery+pickup supported; outside-zone → pickup-only.
- [ ] Reservation claimed on checkout entry w/ visible countdown; expiry → cart with notice.
- [ ] `checkout.checkout.*` nested (append-rule); full API suite + repo green.

## checkout.json rule (shared with M07-P03 this wave)

Append ONLY your nested `checkout` section; do NOT reorder/reformat siblings. The later-merging checkout PR combines sections.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M07-P04 — Checkout steps 1–2
**STATUS/FILES/DEVIATIONS/TESTS** (paste zone-fee + mixed-group + reservation-claim + full-pytest tail) **/EXCERPTS** the reservation-claim + zone-fee code — nothing else **/QUESTIONS**
