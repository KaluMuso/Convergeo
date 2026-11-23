# Task T22: Order tracking: show "You paid → Held by Vergeo5 → Released"

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/order-tracking-trust-copy` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T22 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/app/[locale]/account/orders/_components/order-timeline.tsx` (+ test), the `escrow` label wiring in `account/orders/[id]/page.tsx`, and `packages/i18n/messages/*/orders.json` (`escrow` block only)

## Problem

The order page only shows one line of escrow text (`orders.escrow.held`: "We keep your money safe until you get your order."). The product rule is a clear three-step trust strip: **You paid → Held by Vergeo5 → Released**. Checkout has similar steps (`checkout.json` `escrowStep1-3`), the order page does not. UI only: don't touch payment or ledger code.

## Steps

1. Add `escrow.strip.{paid,held,released}` to `orders.json` (en: "You paid", "Held by Vergeo5", "Released"). Add the same keys to bem, nya, fr, zh as English copy for review, no machine translation.
2. In `order-timeline.tsx` render a small 3-step strip for prepaid orders only, using the existing order status and `escrow_copy_key` to mark the current step (paid and held done at held; released when released; refunded shows the existing refunded line instead). No strip at all for COD (`payment_mode === "cod"`): keep the existing COD wording.
3. Strip must work at 360px, use design tokens only, and carry `aria-current="step"` on the active step.
4. Extend `order-timeline.test.tsx`: prepaid held, prepaid released, refunded, COD (no strip).

## Done means

A prepaid order shows the three steps with the right one active, COD shows none. Tests, typecheck and lint pass. Under 200 lines changed.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time: `pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
