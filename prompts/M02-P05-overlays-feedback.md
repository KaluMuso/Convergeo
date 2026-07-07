> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**; do NOT touch `pnpm-lock.yaml`, `packages/ui/package.json`, `packages/ui/tsconfig.json`, or any `messages/*.json`.

# M02-P05 — Overlays & feedback

## 1. Context

**Wave 2 (parallel ×7).** On `master`: tokens + CSS vars/keyframes (`toast-in`, `toast-out`, `fadeSlideUp`, `shimmer`, `pulse-dots` already global in `@vergeo/ui/styles/base.css`), fonts, i18n. Test toolchain pre-wired (react 19, RTL, user-event, jest-dom, jsdom): component tests start with a `// @vitest-environment jsdom` docblock + `import "@testing-library/jest-dom/vitest";` — do NOT add a vitest.config.ts. Deep imports via `@vergeo/ui/src/*`. Spec: `docs/plan/02-pebbles/M02-design-system.md` §P05.

## 2. Objective & scope

Overlay + feedback kit: Modal, BottomSheet, Toast (+provider), Skeleton, Spinner, EmptyState, ErrorState, ConfirmDialog.
**Non-goals:** no forms/cards/nav/media (siblings), no new deps (build on native `<dialog>`/portals — no radix/headlessui), no barrel.

## 3. Files (create ONLY these — all under `packages/ui/src/`)

`modal.tsx` · `bottom-sheet.tsx` · `toast.tsx` (component + `ToastProvider` + `useToast` in this one file) · `skeleton.tsx` · `spinner.tsx` · `empty-state.tsx` · `error-state.tsx` · `confirm-dialog.tsx` + colocated `*.test.tsx`.
**Guardrail: nothing else.**

## 4. Implementation spec

- **Modal:** portal + focus trap (focus moves in on open, cycles, restores on close), scrim click + ESC dismiss (both suppressible), scroll lock on body, `role="dialog"` + `aria-modal` + labelled-by wiring. Prefer native `<dialog>` with a fallback path if jsdom limits testing — document the choice.
- **BottomSheet:** mobile-primary overlay; slides from bottom (`fadeSlideUp`/transform via tokens), **drag-to-dismiss** (pointer events, threshold), snap-open height prop, same a11y contract as Modal, back-gesture/ESC dismiss.
- **Toast:** provider + `useToast()`; queue (max 4, FIFO eviction), auto-dismiss ~2.8s (configurable), pause-on-hover, `toast-in/out` keyframes, **`aria-live="polite"` region**, type variants (success/error/info/cart) with token colors; copy passed by caller.
- **ConfirmDialog:** Modal composition — title/body/confirm/cancel via props, destructive variant, promise-style `onConfirm`.
- **Skeleton:** shimmer block/line/circle shapes (reuses global keyframe). **Spinner:** token-colored, `role="status"` + visually-hidden label prop. **EmptyState / ErrorState:** icon slot + title/body + action slot; retry callback on ErrorState; copy via props only.
- Reduced-motion: all transitions collapse to opacity fades (media query already in base.css — ensure components use token durations, not hardcoded ms).

## 5. UI/UX & styling

Aubergine scrim (`--panel` at alpha), `--r-lg` sheets, `--shadow-3` elevation, spring easing ONLY on success confirmations per token docs.

## 6. Responsiveness

BottomSheet is the default pattern ≤640px; Modal centers on desktop. Sheet content scrolls internally; body never scrolls behind.

## 7. Performance

Portals render `null` until open; no layout thrash from drag (transform-only); zero new deps.

## 8. SEO

N/A.

## 9. Security

No `dangerouslySetInnerHTML`; toasts never render untrusted HTML.

## 10. Tests (RUN before reporting)

Modal: focus trapped + restored, ESC + scrim dismiss, scroll lock toggles. BottomSheet: open/close, drag past threshold dismisses (pointer-event simulation), below threshold snaps back. Toast: queue caps at 4 with FIFO eviction, auto-dismiss timer (fake timers), live region present, pause-on-hover. ConfirmDialog: confirm/cancel callbacks, destructive variant. ErrorState retry fires. Reduced-motion snapshot (matchMedia mock).
Commands: `pnpm --filter @vergeo/ui test|typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] Focus trap + restore correct; ESC/back-gesture dismiss; scroll lock verified.
- [ ] Toast queue ordering + max-4 + live region tested.
- [ ] Drag-dismiss works via pointer events; reduced-motion respected.
- [ ] No new deps; no files outside list; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P05 — Overlays & feedback
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste actual test output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
