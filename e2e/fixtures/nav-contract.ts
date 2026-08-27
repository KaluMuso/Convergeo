/**
 * Semantic accessibility contracts the suite locates real Customer-app
 * navigation landmarks by, instead of a `data-testid` that production never
 * renders. These strings mirror the English source of truth —
 * `packages/i18n/messages/en/nav.json` (`shop.bottomAriaLabel`) — which
 * `BottomNavClient` (apps/customer/.../(shop)/layout.tsx) passes straight
 * into `BottomNav`'s `aria-label` (packages/ui/src/bottom-nav.tsx). The suite
 * always runs `E2E_LOCALE=en` (see fixtures/env.ts), so the English string is
 * the only one that ever needs to match live.
 *
 * `scripts/qa/self-test/e2e-nav-contract.test.mjs` reads the real nav.json
 * off disk and asserts it still equals this constant, so a translation-copy
 * edit that drifts from this locator fails CI instead of silently breaking
 * the bottom-nav E2E check the next time it runs.
 */
export const BOTTOM_NAV_ARIA_LABEL = "Primary shop navigation";
