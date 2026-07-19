> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# VB-P07 — Checkout false-success E2E `[CODE]`

## 1. Context
**Wave 2.** Source: `01-audit-findings.md` MR-C08; `release-gates.md` S6/G4. **Depends on VA-P01** (frontends promoted) + the isolated sandbox stack. Parallel-safe with VB-P01…P06 (owns a distinct spec file). **Build state:** the customer checkout UI hardening is CODE_COMPLETE (#289 — card requires `order_confirmed`, MoMo `confirming ≠ paid`), but **no E2E proves** a pending/failed payment never renders as "paid." Existing E2E lives in the standalone `e2e/` package (Playwright, Fast-3G/360px, `e2e.yml`).
**Type:** `[CODE]` — a Cursor coding agent writes the spec and runs it against the sandbox stack.

## 2. Objective & scope
Add Playwright specs proving no false payment-success state across the three risk paths.
**Non-goals:** editing checkout application code (it is correct; a real bug → DEVIATIONS + stop); the happy-path E2E (that is VE-P07, a different file); enabling production money.

## 3. Files (create ONLY these)
- `e2e/specs/checkout-false-success.spec.ts`
- `e2e/fixtures/lenco-sandbox.ts` **only if** a shared sandbox helper is required (else reuse existing fixtures → note in DEVIATIONS)
**Guardrail: modify ONLY these files — do NOT edit VE-P07's `critical-path.spec.ts` or app code.**

## 4. Implementation spec
Three scenarios, each asserting the UI never claims success without a confirmed payment + ledger policy:
- **Abandoned MoMo (pending):** initiate MoMo, never approve the USSD push → the pending/poll page (`checkout/pending/[groupId]`) shows "awaiting/processing", **never** an order-confirmed/paid state.
- **Delayed webhook:** simulate a late success webhook → the success state appears **only after** the confirmed policy (card `order_confirmed`; MoMo `confirming ≠ paid`), not on optimistic client state.
- **COD ≤ K500:** a COD order never renders MoMo/card "paid" copy; escrow/held wording matches COD, not prepaid.
Use the sandbox Lenco legs; gate credential-dependent steps with `test.skip()` when creds absent (existing `e2e/` pattern), but the pending/COD assertions must run credential-free.

## 5–8. UI/UX · Responsiveness · Performance · SEO
Assert at **360px / Fast-3G** (existing `e2e/` project profile). No UI code changes.

## 9. Security
- No secrets in the spec; sandbox creds via env only. Never assert on or log real payment refs.

## 10. Tests (RUN before reporting)
- `pnpm --filter e2e test -g "false-success"` (or the repo's `pnpm e2e` invocation) green against the sandbox stack.
- Confirm the three assertions fail loudly if a "paid" state leaks (temporarily invert one to prove the test has teeth, then revert).

## 11. Acceptance criteria / DoD (maps to S6/G4)
- [ ] Pending MoMo never shows paid/confirmed.
- [ ] Success only after confirmed policy (not optimistic client state).
- [ ] COD ≤K500 never claims MoMo/card success.
- [ ] Spec green in CI on the sandbox stack; credential-free assertions run without Lenco creds.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** VB-P07 — Checkout false-success E2E
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** any departure from spec, and why (or "none")
**TESTS:** paste Playwright run output
**EXCERPTS:** the three scenario assertions
**QUESTIONS:** uncertainties needing a reviewer decision (or "none")
