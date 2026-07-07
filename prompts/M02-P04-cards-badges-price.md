> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**; do NOT touch `pnpm-lock.yaml`, `packages/ui/package.json`, `packages/ui/tsconfig.json`, or any `messages/*.json`.

# M02-P04 — Cards, badges & price primitives

## 1. Context

**Wave 2 (parallel ×7).** On `master`: tokens (`@vergeo/ui/tokens` incl. category pastels + `tagTint()`), CSS vars/keyframes (`shimmer` skeleton), fonts, i18n with **`formatK` from `@vergeo/i18n`** (integer ngwee → `K1,234.56`; dev-throws on non-integer). Test toolchain pre-wired (react, RTL, jsdom): component tests start with a `// @vitest-environment jsdom` docblock as the FIRST line + `import "@testing-library/jest-dom/vitest";` — do NOT add a vitest.config.ts. Deep imports via `@vergeo/ui/src/*`. Spec: `docs/plan/02-pebbles/M02-design-system.md` §P04; visual language: `docs/designs/SELECTION.md` §3 + `docs/designs/TOKENS.md`.

## 2. Objective & scope

The commerce card vocabulary: ProductCard, EventCard, ServiceCard, VendorCard, Badge, CornerRibbon, Pill, PriceBlock, StarRating, TierPriceTable.
**Non-goals:** no data fetching (typed props only), no forms/overlays/nav/media (siblings), no new deps, no barrel.

## 3. Files (create ONLY these — all under `packages/ui/src/`)

`product-card.tsx` · `event-card.tsx` · `service-card.tsx` · `vendor-card.tsx` · `badge.tsx` · `corner-ribbon.tsx` · `pill.tsx` · `price-block.tsx` · `star-rating.tsx` · `tier-price-table.tsx` + colocated `*.test.tsx`.
**Guardrail: nothing else.**

## 4. Implementation spec

- **PriceBlock:** props `ngwee: number`, optional `oldNgwee`; renders via `formatK` — **never accepts floats** (TS `number` + runtime dev assert delegating to formatK's guard); struck old price in `--text-3`, savings chip in `--accent` tint. This is the ONLY money display path.
- **StarRating:** display mode (fractional fill, review count) + input mode (keyboard-operable radio group 1–5); zero-review state renders "no reviews" slot, not 0 stars.
- **Badge / Pill:** status chip enum (`sold_out | promotion | public | selling_fast | free | new | featured`) with token color mapping; Pill uses the `tagTint()` alpha recipe. **CornerRibbon** for the trust/commercial ladders — two distinct props, never conflated: `trust` (self_listed | id_verified | sector_verified | preferred) vs `tier` (bronze | silver | gold | platinum).
- **ProductCard:** image slot (aspect-ratio box; the actual `CloudinaryImage` lands in M02-P08 — accept a `media` ReactNode slot so there's no cross-pebble import), badge, vendor line, StarRating, PriceBlock, pastel category fill, quick-add callback, wishlist-heart callback, **skeleton variant** (shimmer keyframe).
- **EventCard:** date/venue lines, capacity bar (`spots-fill`), status badge, PriceBlock or "Free". **ServiceCard:** from-price optional, tag pills. **VendorCard:** cover/avatar slots, tier chip + trust pill, stats row. All cards: skeleton variant + typed props only + copy via props (no literals).

## 5. UI/UX & styling

SELECTION.md language: pastel fills for category accents, warm-black shadows (`--shadow-1/2`), `--r-lg` cards, pill tags. Card lift on hover via token motion; reduced-motion respected.

## 6. Responsiveness

Cards fluid; 2-up grid at 360px must not overflow; text truncation with CSS line-clamp (test with long Bemba/Nyanja strings).

## 7. Performance

Aspect-ratio boxes prevent CLS; skeletons for loading; no images fetched by the library itself (slots).

## 8. SEO

Cards emit semantic HTML (article, headings hierarchy-agnostic via `as` prop).

## 9. Security

No `dangerouslySetInnerHTML`; all strings via props.

## 10. Tests (RUN before reporting)

PriceBlock: integer renders `K1,234.56`; non-integer throws in test env; old-price strike + savings. StarRating: 3.5 renders half-fill; zero-review state; input mode keyboard select. Badge enum→color mapping; ribbon trust vs tier isolation (both renderable together, distinct labels). Each card: required fields render, skeleton variant, long-string truncation (e.g. 60-char Nyanja title), callbacks fire. TierPriceTable: tier rows + MOQ, single-tier edge.
Commands: `pnpm --filter @vergeo/ui test|typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Cards render from typed props only; skeleton variant per card.
- [ ] PriceBlock rejects non-integer input (dev assert, tested); formatK is the only money path.
- [ ] Trust ladder vs commercial tier never share a prop/component.
- [ ] Long Bemba/Nyanja strings truncate cleanly; 2-up at 360px.
- [ ] No files outside list; no new deps; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P04 — Cards, badges & price primitives
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste actual test output
**EXCERPTS:** full code of `price-block.tsx` (money display path) — nothing else
**QUESTIONS:** (or "none")
