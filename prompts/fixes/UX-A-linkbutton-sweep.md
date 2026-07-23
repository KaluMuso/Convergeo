> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **No migration. No i18n changes.** Run `pnpm --filter customer typecheck && pnpm --filter customer lint && pnpm --filter customer test` before reporting. Manual 360px visual check on the touched routes.

# UX-A — Adopt shared `LinkButton` for button-styled `<Link>`s

## Findings (docs/design audit §6 — component consistency)

`packages/ui/src/link-button.tsx` (`LinkButton`, pulls variant/size classes from `button.tsx`) exists but is adopted in only 2 files (`(marketing)/_components/marketing-app-header.tsx`, `(shop)/_components/home-hero-carousel.tsx`). ~42 raw `<Link className="inline-flex min-h-11 items-center justify-center rounded bg-… / border …">` button-links remain hand-rolled across ~28 files — inconsistent focus rings, heights, and hover states.

## Required fix

Replace button-styled `<Link>`s with `<LinkButton href=… variant=… size=… LinkComponent={Link} …rest>`.

- `bg-primary … text-surface|text-[var(--primary-btn-fg)]` → `variant="primary"`; outline `border border-border text-text` → `variant="secondary"`.
- Default height `min-h-11`/`h-11` → `size="md"`; `h-12 min-h-12` → `size="lg"`.
- **Zero visual regression is the bar.** Preserve every NON-variant class (`w-full`, `gap-*`, margins, custom `px-*` that differs from the size default) by passing it through `className`. `...rest` already forwards `data-testid`/`aria-label`/`onClick` — keep them intact.
- **Edge cases** (`rounded-pill bg-panel-text`/`rounded-pill bg-primary`): `flash-deal.tsx:73`, `home-default.tsx:368` — use `variant` + a `className` override for the pill radius/tokens.
- **OUT OF SCOPE — do NOT touch** (chip family + rails, owned by UX-B): `browse-discovery-chips.tsx`, `plp/child-category-nav.tsx`, `services/_components/vertical-filter-chips.tsx`, `category-grid.tsx`, `home-recently-viewed-rail.tsx`, `account/_components/account-nav.tsx`. Also do NOT touch `_components/pdp/comparison.tsx` / `buyer-trust-panel.tsx` (owned by UX-C).

## Files (ONLY — the button-link sites)

Root: `app/not-found.tsx`. Under `apps/customer/app/[locale]/`: `not-found.tsx`, `error.tsx`, `(marketing)/about/page.tsx`, `(marketing)/help/page.tsx`, `(marketing)/help/[slug]/page.tsx`, `(marketing)/sell/_components/hero.tsx`, `(marketing)/beta/_components/beta-gate.tsx`, `(shop)/compare/page.tsx`, `(shop)/supplies/page.tsx`, `(shop)/s/[slug]/page.tsx`, `(shop)/p/[slug]/page.tsx` (the CTA `<Link>` ~L427 only), `(shop)/wishlist/_components/saved-items-panel.tsx`, `(shop)/checkout/card/[paymentId]/page.tsx`, `(shop)/checkout/_components/ussd-wait.tsx`, `(shop)/_components/cart/mini-cart-drawer.tsx`, `(shop)/_components/cart/vendor-groups.tsx`, `(shop)/_components/search/zero-results.tsx`, `(shop)/_components/search/search-unavailable-panel.tsx`, `(shop)/_components/pdp/no-sellers-panel.tsx`, `(shop)/_components/flash-deal.tsx`, `(shop)/_components/home-default.tsx`, `account/tickets/page.tsx`, `account/orders/page.tsx`, `account/jobs/page.tsx`, `account/business/page.tsx`, `account/recent/_components/recently-viewed-panel.tsx`, `offline/page.tsx`.

## Tests (RUN)

`pnpm --filter customer typecheck`; `pnpm --filter customer lint`; `pnpm --filter customer test`; the blocking i18n-lint gate stays green (no new strings). Confirm the primary/secondary/lg buttons look identical at 360px on `not-found`, `compare`, and `mini-cart-drawer`.

## Report

STATUS / FILES / DEVIATIONS / TESTS / EXCERPTS (before→after for one primary + one secondary + one edge-case) / QUESTIONS.
