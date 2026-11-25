# Task T32: Customer app — modern, professional polish on design system v2

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/customer-polish` from `master`, **after T31 (design system v2) is merged**. Open one PR to `master`; don't merge.
**Board:** claim row T32 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.
**Owns (edit only these):** `apps/customer/app/**` and `apps/customer/components/**` (presentation only), `packages/i18n/messages/*/customer.json`. **Not** `packages/ui` (ask on the board if a shared component is missing), and not `next.config.ts`, `middleware.ts` or API clients.

## Why

King, 24 Nov: "the user experience for the admin panel, vendor app and customer apps today was amateur and not modern ... more features and professionalism is required ... include visuals, images and professional colored icons of reasonable size." The new design system (T31) gives neutral black/white by default with an optional Green accent, `IconTile` colour icons, motion utilities, `PageHeader`, `StatCard`, `Skeleton` and spot illustrations. Apply it so every screen of the Customer app looks like a polished product in the class of Takealot, Jumia, Amazon and Airbnb (mobile web).

## Do this for EVERY route in the app (list them in the PR with before/after screenshots at 360 px and 1280 px, light and dark)

1. **Layout:** a `PageHeader` on every page, consistent spacing (4/8 px grid), and max widths. Home gets a real hero (image plus headline plus search), category tiles with icon tiles, and horizontally scrolling rails with snap.
2. **Icons:** replace bare or monochrome icons in navigation, cards, quick actions, stats and empty states with `IconTile` (sizes 40–48 for tiles, 20–24 inline), using the category → hue map where it applies.
3. **Images:** product, vendor, service and event cards always show an image (Cloudinary `f_auto,q_auto`, `srcset`, lazy, fixed aspect ratio, blurred placeholder). When a listing has no photo, show a tasteful category illustration or icon tile, never a grey box. Vendor storefronts show the cover and logo prominently.
4. **States:** a `Skeleton` that matches the final layout for every loading state (no spinners on page loads); `EmptyState` with an illustration and one clear next action; friendly error states with retry.
5. **Motion:** page-in on route content, hover lift on cards, press scale on buttons, animated tab and segment indicators, sheet and dialog transitions, toasts. Everything respects reduced motion.
6. **Detail work:** tabular numbers for money (always `formatK`), status chips with consistent colours, truncation and line-clamp instead of overflow, focus rings visible, touch targets ≥ 44 px, sticky action bars on mobile forms.
7. **Customer value cues** (presentation only): trust strip (escrow, verified seller, returns) on product and checkout pages, a clear "total you pay" line, and delivery and pickup chips on cards. Deeper value features come in T36; don't build those here.

## Tests (required)

Update the affected component and snapshot tests; add tests for any new empty or skeleton state; run axe on the main routes (no serious or critical issues); run the bundle guard (report per-route JS; customer routes ≤150 KB gz).

## Done means

Every route matches the design system, light and dark, mono and green, at 360 px and desktop. No raw hex colours or ad-hoc spacing (lint). Screenshots are in the PR. Tests, typecheck, lint and the bundle guard pass.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time (`pnpm --filter customer exec vitest related <files> --run`, then `pnpm --filter customer typecheck` and lint). Never the full e2e suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic (presentation of checkout may change; amounts, calls and flows may not). No secrets. Never merge, force-push or `git stash`.
5. Zero hardcoded strings. For bem, nya, fr and zh, copy the English text and mark it for review.
6. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.

## Additions (King, 25 Nov): Amazon and Alibaba home and category patterns

Don't touch the product page; T41 owns it.

1. **"Shop by department" drawer** (the "All" menu):
   - A left slide-in drawer with the signed-in greeting at the top.
   - Top-level categories each have a coloured icon tile (the T31 category map) and a chevron.
   - Tapping one slides to a sub-panel with "← Main menu" and that category's children.
   - On desktop, hovering a top-level category opens a mega-menu with circular category images.
2. **Home deal rails:**
   - A full-width band (accent-tinted surface) with a bold title and a "›" link, plus a horizontal rail of white product cards.
   - Each card shows the image, a red "−35%" badge plus a label (e.g. "Deal"), the price via `formatK` and the struck-through old price.
   - Use only real compare-at/old-price data; when there's no discount, show no badge.
   - Rails use arrows on desktop and swipe on mobile.
3. **Quad category cards:**
   - A grid of 4-up cards ("Phones & accessories", "Home & kitchen" …).
   - Each card has a title, a "›" link and a 2×2 grid of sub-category images with labels.
   - Use 4 columns on desktop, a horizontal swipe on mobile.
4. **Category landing:**
   - a banner;
   - a row of circular "Shop by category" images;
   - then rails ("Best sellers", "New in", "Under K500").
5. **Trust strip** with coloured icons: "Pay with MTN/Airtel MoMo", "Money held until you confirm delivery", "Verified sellers", "Lusaka delivery / nationwide pickup".
