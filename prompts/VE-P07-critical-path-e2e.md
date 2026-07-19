> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VE-P07 — Critical-path happy E2E `[CODE]`

## 1. Context
**Wave 4.** Source: `release-gates.md` G16/S7. **Depends on VA-P01** + the sandbox stack. Complements VB-P07 (false-success) with the **happy path**. Standalone `e2e/` Playwright package, Fast-3G/360px, `e2e.yml`.
**Type:** `[CODE]`. **Owns a DISTINCT spec file from VB-P07** (parallel-safe).

## 2. Objective & scope
End-to-end browse → cart → sandbox checkout → order confirmation across the customer app.
**Non-goals:** false-success paths (VB-P07's file); perf budgets (VE-P06).

## 3. Files (create ONLY these)
- `e2e/specs/critical-path.spec.ts`
**Guardrail: do NOT edit `e2e/specs/checkout-false-success.spec.ts` (VB-P07).**

## 4. Implementation spec
- Journey: land on home → open a PLP/PDP → add to cart → checkout (contact/fulfilment/payment) → complete a **Lenco sandbox** MoMo (or card) pay → land on order confirmation with pickup/tracking state.
- Gate credential-dependent legs with `test.skip()` when sandbox creds absent (existing `e2e/` pattern); assert the pre-payment journey credential-free.
- Assert 360px/Fast-3G project profile.

## 10. Tests (RUN before reporting)
- `pnpm e2e` (or `pnpm --filter e2e test -g "critical-path"`) green on the sandbox stack.
- The journey fails loudly if any step (cart total, confirmation state) is wrong.

## 11. Acceptance criteria / DoD (G16)
- [ ] Browse→cart→sandbox-checkout→confirm green at 360px/Fast-3G.
- [ ] Credential-free legs run without Lenco creds; paid leg `test.skip`s when absent.
- [ ] Distinct spec file from VB-P07.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VE-P07 — Critical-path happy E2E
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste Playwright run · **EXCERPTS:** none · **QUESTIONS:** …
