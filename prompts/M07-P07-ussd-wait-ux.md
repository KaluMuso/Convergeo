> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 12 runs 9 pebbles in parallel — **touch ONLY your files below**. **⚠ SCHEMA FROZEN.** Stay dep-free. **Run the FULL `uv run pytest` before reporting.**

# M07-P07 — Order-pending & USSD wait UX

## 1. Context

**Wave 12 (parallel ×9).** Grounded against as-built `master`:

- **Payment states merged (M08-P04):** `payments.status` = initiated/ussd_pushed/pay_offline/success/failed/expired/cancelled. **Checkout merged (M07-P04/P05, W8/W9):** the `(shop)/checkout/` stepper + `checkout/_components/` (M07-P05 owns `step-payment.tsx`/`step-review.tsx` — **do NOT touch**). Order creation merged (M07-P06): `POST /orders` returns the checkout group; a **retry creates a NEW payment attempt against the SAME order (no duplicate order)**.
- Customer app `localePrefix:"always"`. Routers auto-discover (never edit `main.py`); service-role via `app.deps.get_supabase_client` (import-guard; local `Protocol`). i18n `checkout` namespace — **shared with M08-P06 this wave**; you own a nested **`pending`/`ussd`** section (append-rule; do NOT reformat `cart`/`checkout`/`payment`/`review` siblings).
  Spec: `docs/plan/02-pebbles/M07-cart-checkout.md` §M07-P07. **⚙ Same-wave edge M08-P06 (card):** disjoint files (you own `pending/` + `ussd-wait`/`payment-failed`; M08-P06 owns `card/`).

## 2. Objective & scope

Post-submit pending screen (`checkout/pending/[groupId]`): **"Check your phone — approve the K\___ prompt"** per rail with rail-specific helper copy; a **customer-scoped status poll** (2s → backoff); states **waiting → success (→ order confirmation) / failed / expired (retry = new payment attempt, same order) / user-cancelled**; **COD path skips to confirmation** with COD instructions.
**Non-goals:** no card widget (M08-P06), no payment initiation internals (M08-P04), no order creation (M07-P06), no schema.

## 3. Files (create/modify ONLY these)

- **Create:** `apps/customer/app/[locale]/(shop)/checkout/pending/[groupId]/page.tsx` · `checkout/_components/{ussd-wait,payment-failed}.tsx` · `services/api/app/routers/payment_status.py` (customer-scoped status poll) · `services/api/tests/test_payment_status.py`
- **Modify:** `packages/i18n/messages/en/checkout.json` (append nested `pending`/`ussd` section)
  **Guardrail: nothing else. Do NOT touch `step-payment.tsx`/`step-review.tsx` (M07-P05), `checkout/card/*` (M08-P06), `checkout.py`, `main.py`, schema.**

## 4. Implementation spec

- **`payment_status.py`** (auth required, **owner-scoped**): `GET /payments/status?group=…` (or by payment id) → the current payment status for the caller's own checkout group; **another user → 403**. Read-only (reflects M08-P04 states).
- **Pending page:** poll (2s, backoff) → render **waiting** (rail helper copy + the exact K amount via `formatK`), **success** → redirect to order confirmation, **failed/expired** → `payment-failed.tsx` with **retry** (retry initiates a NEW payment attempt against the SAME order — no duplicate order) + actionable timeout guidance, **user-cancelled** → guidance. **COD** → skip to confirmation with COD instructions. All copy via `checkout` (`pending.*`/`ussd.*`); 360px-first.

## 5–9. UI/UX · Responsiveness · Performance · SEO · Security

360px-first; checkout `noindex`; **poll owner-scoped (other user 403)**; retry = new attempt not new order; amount via `formatK`; no secrets.

## 10. Tests (RUN before reporting)

`test_payment_status.py`: **poll authz** (other user → 403); status reflects M08-P04 state. Component: **state-transition renders** (waiting/success/failed/expired/cancelled); **retry idempotency** (retry → new payment attempt, same order, no duplicate order). `pnpm --filter customer build`, `pnpm typecheck`, `pnpm lint`, `pnpm test`. **Full `uv run pytest`.**

## 11. Acceptance criteria / DoD

- [ ] Retry creates a new payment attempt against the same order (no duplicate order); poll authz-scoped (other user 403); timeout guidance actionable.
- [ ] All states render; COD skips to confirmation; `checkout.pending.*`/`ussd.*` nested (append-rule); full API suite + repo green.

## 12. IMPLEMENTATION REPORT

**PEBBLE:** M07-P07 — Order-pending & USSD wait UX
**STATUS/FILES/DEVIATIONS/TESTS** (paste poll-authz + state-renders + retry-idempotency) **/EXCERPTS** the owner-scoped status poll — nothing else **/QUESTIONS**
