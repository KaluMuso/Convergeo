> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**; do NOT touch `pnpm-lock.yaml`, `packages/ui/package.json`, `packages/ui/tsconfig.json`, or any `messages/*.json`.

# M02-P08 — Media primitives

## 1. Context

**Wave 2 (parallel ×7).** On `master`: tokens + CSS vars/keyframes (`shimmer`), fonts, i18n. Test toolchain pre-wired (react 19, RTL, user-event, jest-dom, jsdom): component tests start with a `// @vitest-environment jsdom` docblock + `import "@testing-library/jest-dom/vitest";` — do NOT add a vitest.config.ts. Deep imports via `@vergeo/ui/src/*` (pattern spans subdirs, so `@vergeo/ui/src/media/cloudinary-image` resolves). Spec: `docs/plan/02-pebbles/M02-design-system.md` §P08. Data-cost frugality is a core market requirement — these three components carry most of it.

## 2. Objective & scope

Media kit: CloudinaryImage (URL builder + responsive `<img>`), ImageGallery (≤8, swipeable), UploadDropzone (UI only).
**Non-goals:** NO upload wiring/signing (M05-P10 and M12-P05 own that — the dropzone emits files via callback only), no `next/image` dependency (plain `<img>` keeps the lib framework-light; apps may wrap later), no siblings' files, no new deps, no barrel.

## 3. Files (create ONLY these — all under `packages/ui/src/media/`)

`cloudinary-url.ts` (pure URL builder — separate file so it's unit-testable without DOM) · `cloudinary-image.tsx` · `image-gallery.tsx` · `upload-dropzone.tsx` + colocated `*.test.ts(x)`.
**Guardrail: nothing else.**

## 4. Implementation spec

- **`cloudinary-url.ts`:** `cldUrl(publicId, {width, quality?, cloudName?})` → `https://res.cloudinary.com/<cloud>/image/upload/f_auto,q_auto,w_<w>/<publicId>`; cloud name from arg or `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`; `cldSrcSet(publicId)` → widths **360/720/1080**; LQIP variant (`w_24,e_blur:1000,q_30`) for the blur placeholder. Reject empty publicId; never URL-encode surprises (test slashes in publicId).
- **`CloudinaryImage`:** renders `<img>` with `srcset` + `sizes` (prop, sensible default `100vw`→card sizes), **`loading="lazy"` by default** (`priority` prop opts out), `decoding="async"`, **aspect-ratio box** (prop `ratio` e.g. `1`, `4/3`) so zero CLS, LQIP blur-up background until load, `alt` REQUIRED (TS-level), shimmer skeleton while loading.
- **`ImageGallery`:** swipeable strip (pointer/touch scroll-snap — CSS scroll-snap, no JS carousel lib), thumbnail row, **hard cap 8 images** (slice + dev warn beyond), keyboard arrows, current-index indicator, uses CloudinaryImage internally.
- **`UploadDropzone`:** UI ONLY — drag-over state, file picker, client-side preview thumbs, **reorder** (buttons, not DnD-lib), per-file progress bar fed by props, compress-hint slot, ≤8 enforcement with callback rejection, `onFilesChange(files)` — no network calls whatsoever.
- Copy via props (no literals).

## 5. UI/UX & styling

Shimmer during load; `--r` on media boxes; gallery snap alignment; dropzone dashed token border.

## 6. Responsiveness

Gallery full-bleed at 360px with snap; thumbs scrollable; dropzone stacks.

## 7. Performance

This IS the perf pebble: lazy by default, 3-step srcset, f_auto/q_auto, LQIP ~1KB, aspect-ratio boxes (CLS 0). No JS beyond React; scroll-snap does the carousel work.

## 8. SEO

`alt` required; plain `<img>` crawlable.

## 9. Security

Only `res.cloudinary.com` URLs constructible; publicId sanitized into the path (no protocol smuggling — test `publicId` containing `https://`); no file contents read beyond preview object URLs (revoked on unmount).

## 10. Tests (RUN before reporting)

URL builder: exact URL shape, f_auto/q_auto present, 360/720/1080 srcset string, LQIP params, empty-id throws, protocol-smuggling publicId neutralized. CloudinaryImage: `<img>` carries srcset+sizes+loading=lazy+decoding, priority disables lazy, aspect-ratio style present, alt enforced. Gallery: 9th image dropped + dev warn, arrows navigate, indicator updates. Dropzone: ≤8 rejection callback, reorder swaps, object URLs revoked on unmount (spy).
Commands: `pnpm --filter @vergeo/ui test|typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Rendered `<img>` carries srcset + sizes + loading=lazy; zero-CLS aspect boxes.
- [ ] Gallery hard-caps 8; scroll-snap swipe; keyboard operable.
- [ ] Dropzone is network-free; upload wiring explicitly deferred.
- [ ] URL builder pure + fully unit-tested incl. smuggling case; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P08 — Media primitives
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste actual test output
**EXCERPTS:** full code of `cloudinary-url.ts` (URL-construction security surface) — nothing else
**QUESTIONS:** (or "none")
