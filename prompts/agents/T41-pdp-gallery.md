# Task T41: Product page — multi-image gallery with zoom, specs table, sticky section nav, "bought together"

**Agent:** Cursor. **Model:** Composer 2.5. **Branch:** `cursor/pdp-gallery-zoom` from `master`. Open one PR to `master`; don't merge.
**Board:** claim row T41 in `docs/ops/agent-board.md` first. Set it to `ready for review` when done.

**Owns (edit only these):**

- `apps/customer/app/[locale]/(shop)/_components/pdp/gallery.tsx`, `lightbox.tsx`, `gallery-labels.ts`, `pdp-interactive-gallery*` and their tests
- `apps/customer/app/[locale]/(shop)/_components/pdp/pdp-details-tabs.tsx` (+ test)
- new files under `apps/customer/app/[locale]/(shop)/_components/pdp/` named `gallery-*`, `zoom-*`, `spec-table*`, `section-nav*`, `bought-together*`, `more-from-seller*`
- in `apps/customer/app/[locale]/(shop)/p/[slug]/page.tsx`: **only** the JSX that places the gallery, the details tabs and the new sections. Don't touch data fetching, metadata or JSON-LD.
- `packages/i18n/messages/*/customer.json` (`pdp.gallery.*`, `pdp.specs.*`, `pdp.sectionNav.*`, `pdp.boughtTogether.*`, `pdp.moreFromSeller.*` only)

**Not yours:** `buy-box.tsx`, `comparison*`, `buyer-trust-panel*`, `price-drop-alert*` (T36A owns those), reviews (`p/[slug]/_components/reviews-*`), checkout, cart logic, money.

## Why

King (founder) compared our product page with Amazon and Alibaba and wants that level of polish, especially **zoom across multiple images**. Today the gallery shows one image at a time with a basic lightbox.

## What the reference pages do (described, since you can't see the screenshots)

**Desktop (≥1024 px)**

- A **vertical thumbnail strip** on the left of the main image, about 56–64 px square thumbnails with a 2 px accent ring on the active one.
  - Hovering a thumbnail switches the main image; clicking also switches it.
  - If there are more thumbnails than fit, show the first 6 and a final "+N" tile that opens the lightbox.
  - Thumbnails sit in a sticky column, so they stay in view while the details scroll.
- A **large main image** (square, object-contain on a white/neutral surface).
  - **Hover magnifier:** when the pointer is over the main image, show a translucent lens (dotted/hatched) over the hovered region and a **zoom pane** to the right that covers the details column at about 2.5× zoom. It follows the pointer and hides when the pointer leaves.
  - Load the zoom pane's high-res image (Cloudinary `w_1600,q_auto,f_auto`) only when hover starts.
  - Small icons on the image: share (top right) and a "fullscreen" magnifier button.
  - Text below: "Roll over image to zoom in" on desktop, "Tap to expand" on touch (i18n).
- **Click the main image → fullscreen lightbox:**
  - white modal with the large image on the left;
  - on the right: product title, the selected variant (e.g. "Colour: Black"), and a **grid of all thumbnails** (4 per row);
  - Tabs "Images" (and "Videos" only if video data exists; we have none today, so hide it);
  - prev/next arrows, Esc closes, ←/→ keys move, focus is trapped and returns to the trigger on close.
- **Variant swatches with images** (where the listing has variants with their own image): small image cards with the price under them. Picking one swaps the gallery to that variant's images. Reuse the existing variant data; if variants have no images, keep today's chips.

**Mobile (360 px first)**

- Full-width swipeable carousel (CSS scroll-snap, no library) with a dot indicator and an "1/6" counter chip.
- Tap opens a fullscreen viewer with **pinch-zoom and double-tap zoom** (pointer events with two pointers; translate and scale clamped to the image bounds), swipe between images, and swipe down to close.
- Wishlist heart and share buttons over the image (reuse `pdp-wishlist-button`).

**Below the fold**

1. **Sticky section nav** (appears after scrolling past the buy area): "Top · About this item · Specifications · Reviews · Similar". It includes a tiny thumbnail plus the product title on the right (desktop only), highlights the current section (IntersectionObserver), and smooth-scrolls on click. On mobile it becomes a horizontal scroll chip row.
2. **"About this item":** the description as bullet points when it has line breaks; otherwise paragraphs. Clamp to 6 lines with "See more".
3. **Specifications table:** a 2-column key/value table built from the existing attributes/specs data, grouped into collapsible cards ("Features & specs", "Item details", "Measurements", "Materials & care") when a group key exists; otherwise one card. Show zebra rows, keys in muted bold, and 2 cards side by side on desktop, stacked on mobile. Don't show empty groups.
4. **"Frequently bought together":** only if the API already returns related/also-bought products; check `fetch-product.ts` and the existing related rails first. If no such data exists, **skip this section** and note it in the PR (don't invent an endpoint). When shown: up to 3 items with checkboxes, "+" between, and a "Total price" computed in ngwee with integers and shown with `formatK`. "Add selected to cart" uses the existing add-to-cart action.
5. **"More from this seller":** a horizontal rail with arrows on desktop and swipe on mobile, from existing data only (same rule: skip if not available).

## Build notes

- Images come from the existing `ProductImage[]` (`fetch-product.ts`). Use Cloudinary transforms for each size: thumbnails at 128 px, main image with a `sizes`/`srcset` at 480/800/1200, zoom at 1600. Images must be WebP/AVIF via `f_auto`, lazy except the first (which stays `priority` for LCP).
- **Performance:** the magnifier, the lightbox and pinch-zoom code must be **dynamically imported** (load on first hover or tap). The product route stays ≤150 KB gz JS; report the before/after numbers from the bundle guard in the PR. No new npm dependencies.
- Use design-system v2 tokens and motion utilities from `packages/ui` (page-in, pop, reduced motion). No ad-hoc colours.
- **Accessibility:** thumbnails are buttons with `aria-label` "Image 2 of 6"; the main image has the product alt text; the lightbox is a `dialog` with a label; all zoom is optional (keyboard users get the lightbox). Everything turns off under `prefers-reduced-motion`.
- A product with **one image** shows no strip and no counter. **No images** shows the existing placeholder.
- Keep the existing tests passing; update snapshots on purpose and say so.

## Tests (required)

- Gallery: hover/click on a thumbnail changes the main image; "+N" tile appears with more than 6 images; one image → no strip.
- Magnifier: lens position and zoom background-position follow pointer coordinates (unit-test the pure maths function); hides on pointer leave; not rendered on touch.
- Lightbox: opens on click, ←/→ and Esc work, focus returns to the trigger.
- Pinch/double-tap: the pure clamp function keeps the image inside bounds.
- Spec table: groups render, empty groups hidden.
- Bought together (if built): total in ngwee is the integer sum of the checked items.
- Section nav: clicking scrolls to the section id.

## Done means

On a laptop, hovering the main image shows an Amazon-style zoom pane, and thumbnails switch images. Clicking opens a fullscreen viewer with every image. On a phone, swipe, pinch and double-tap zoom work. The page has a sticky section nav and a clean specs table. Tests, typecheck, lint and the bundle guard pass. Post before/after screenshots (desktop 1440 and mobile 360, light and dark) in the PR.

## Rules

1. Claim your board row (`in progress — cursor`) in your first commit. One agent per row.
2. Work only in the files you OWN. Need another file? Stop and note it on the board.
3. Testing: run only related tests, one command at a time (`pnpm --filter customer exec vitest related <files> --run`), then `pnpm --filter customer typecheck` and `pnpm --filter customer lint`. Never the full e2e suite.
4. Never touch `supabase/`, `scripts/ci/`, `.github/`, `infra/`, payments, escrow, ledger, payouts, webhooks, auth or checkout money logic. No secrets. Never merge, force-push or `git stash`.
5. bem, nya, fr and zh: copy the English text and mark it for review.
6. When done: row to `ready for review`, one line of notes, PR link in Slack #convergeo-dev.
