# M02 — Design System & UI Kit — Pebbles

8 pebbles. Tokens from `docs/designs/SELECTION.md`. **No barrel file** in `packages/ui` — deep imports (`@vergeo5/ui/button`) so parallel pebbles never touch a shared index. All components: i18n-key props only (no literal copy), focus-visible styles, ≥44px touch targets, dark-safe contrast per token contrast pairs.

---

### M02-P01 — Design tokens & Tailwind theme `M`
**Deps:** M01-P04 · **Files:** `packages/ui/tailwind-preset.ts` (replaces stub), `packages/ui/src/tokens.ts`, `packages/ui/src/styles/base.css`, `docs/designs/TOKENS.md`
Encode SELECTION.md: cream ground, navy serif display type, aubergine panels, pastel category fills, full type scale, spacing, radii, shadows, motion durations — as Tailwind 4 theme + exported token object. Contrast pairs documented.
**AC:** token change in ONE file propagates to all apps; TOKENS.md maps every token → SELECTION.md source; no ad-hoc color/spacing possible without lint complaint (tailwind config disallows arbitrary values for color).
**Tests:** snapshot of resolved theme; contrast assertions (WCAG AA) on token pairs.

### M02-P02 — i18n foundation & formatters `M`
**Deps:** M01-P04 · **Files:** `packages/i18n/src/` (config, namespace loader, `format/money.ts` **`formatK(ngwee:number)`**, `format/datetime.ts`, `format/number.ts`), `packages/i18n/messages/en/` namespace skeletons (`common`, `auth`, `catalog`, `search`, `checkout`, `orders`, `vendor`, `admin`, `events`, `services`, `supplies`, `directory`, `legal`, `notifications`, `account`, `ai`), `packages/config/eslint-rules/no-hardcoded-strings` (wired into preset)
ICU messages; `formatK` takes **integer ngwee** → "K1,234.56" locale-aware (the ONLY money display path); date/number locale-aware; per-namespace files so feature pebbles each own their namespace file exclusively; lint rule fails on literal JSX strings.
**AC:** `formatK(123456)` = "K1,234.56"; lint rule catches a planted literal; namespaces load lazily per route.
**Tests:** formatter unit tests (zero, negative, >1M ngwee, rounding never occurs — ints only); lint rule fixture tests.

### M02-P03 — Form controls `M`
**Deps:** P01, P02 · **Files:** `packages/ui/src/button.tsx`, `input.tsx`, `select.tsx`, `textarea.tsx`, `otp-field.tsx`, `checkbox.tsx`, `radio.tsx`, `switch.tsx`, `form-field.tsx` (label/help/error wrapper)
Variants (primary/secondary/ghost/destructive), sizes, loading + disabled states; OTP field: 6-digit, auto-advance, paste support, numeric keyboard on mobile.
**AC:** keyboard + screen-reader operable; error states announced; 44px min targets.
**Tests:** vitest + testing-library per component incl. OTP paste/backspace behavior.

### M02-P04 — Cards, badges & price primitives `M`
**Deps:** P01, P02 · **Files:** `packages/ui/src/product-card.tsx`, `event-card.tsx`, `service-card.tsx`, `vendor-card.tsx`, `badge.tsx`, `corner-ribbon.tsx`, `pill.tsx`, `price-block.tsx`, `star-rating.tsx`, `tier-price-table.tsx`
Cards per SELECTION.md (pastel category fills, ribbons for Preferred/Verified); `PriceBlock` consumes `formatK` (ngwee in, never floats); `TierPriceTable` for supplies (qty-tier rows + MOQ); `StarRating` display + input modes.
**AC:** cards render from typed props only; PriceBlock rejects non-integer input (TS + runtime dev assert); skeleton variant per card.
**Tests:** render tests incl. long Bemba/Nyanja strings (truncation), zero-review rating state, tier table edge (single tier).

### M02-P05 — Overlays & feedback `M`
**Deps:** P01, P02 · **Files:** `packages/ui/src/modal.tsx`, `bottom-sheet.tsx`, `toast.tsx` (+provider), `skeleton.tsx`, `spinner.tsx`, `empty-state.tsx`, `error-state.tsx`, `confirm-dialog.tsx`
Bottom sheet is the mobile-primary overlay (drag-dismiss); toasts queued, auto-dismiss, a11y live region; standard empty/error patterns with retry slot.
**AC:** focus trap + scroll lock correct; ESC/back-gesture dismiss; reduced-motion respected.
**Tests:** focus-trap, toast queue ordering, reduced-motion snapshot.

### M02-P06 — Navigation `M`
**Deps:** P01, P02 · **Files:** `packages/ui/src/top-nav.tsx`, `bottom-nav.tsx`, `tabs.tsx`, `breadcrumbs.tsx`, `stepper.tsx`, `pagination.tsx`
BottomNav: 5 slots (config-driven labels/icons/hrefs — apps decide tabs); TopNav with search slot + cart badge; Stepper for checkout (≤4 steps); pagination = "load more" pattern primary (data frugality).
**AC:** bottom nav thumb-reachable at 360px; active states; safe-area insets.
**Tests:** render + active-route logic; stepper progression.

### M02-P07 — Component preview page `S`
**Deps:** P03–P06, P08 · **Files:** `apps/customer/app/[locale]/(dev)/ui/page.tsx` (+ section files under `(dev)/ui/`)
Non-prod-gated gallery rendering EVERY kit component in all states, EN keys via i18n.
**AC:** every exported component appears; Lighthouse a11y ≥95 on the page; gated off in production build.
**Tests:** CI Lighthouse a11y run; export-coverage check (script diffs `packages/ui/src/*` vs preview imports).

### M02-P08 — Media primitives `M`
**Deps:** P01 · **Files:** `packages/ui/src/media/cloudinary-image.tsx`, `media/image-gallery.tsx`, `media/upload-dropzone.tsx`
`CloudinaryImage`: builds `f_auto,q_auto` URLs, responsive `srcset` (360/720/1080), LQIP blur placeholder, lazy by default; `ImageGallery`: swipeable, ≤8 images, thumbnails; `UploadDropzone`: UI only (compress hint, progress, reorder) — upload wiring lands in M05-P10/M12-P05.
**AC:** rendered `<img>` carries srcset+sizes+loading=lazy; gallery hard-caps 8; no layout shift (aspect-ratio boxes).
**Tests:** URL-builder unit tests; gallery cap; CLS-guard snapshot.
