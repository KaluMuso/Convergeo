> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**; especially do NOT touch `pnpm-lock.yaml`, `packages/ui/package.json`, `packages/ui/tsconfig.json`, or any `messages/*.json`.

# M02-P03 — Form controls

## 1. Context

**Wave 2 (parallel ×7).** Merged and available on `master`: design tokens (`@vergeo/ui/tokens`, Tailwind preset, `src/styles/base.css` CSS vars + keyframes), fonts helper, i18n foundation. **Test toolchain is pre-wired:** react 19, @testing-library/react + user-event + jest-dom, jsdom are already devDeps of `@vergeo/ui`; deep imports resolve via the `./src/*` wildcard export. Component tests opt into the DOM with a `// @vitest-environment jsdom` docblock as the FIRST line and `import "@testing-library/jest-dom/vitest";` at the top — **do not add a vitest.config.ts** (a shared config breaks the snapshot client here). Spec source: `docs/plan/02-pebbles/M02-design-system.md` §P03.

## 2. Objective & scope

The form-control kit for all three apps: Button, Input, Select, Textarea, OtpField, Checkbox, Radio, Switch, FormField wrapper.
**Non-goals:** no cards/overlays/nav/media (sibling pebbles), no app usage, no new dependencies, no barrel file.

## 3. Files (create ONLY these — all under `packages/ui/src/`)

`button.tsx` · `input.tsx` · `select.tsx` · `textarea.tsx` · `otp-field.tsx` · `checkbox.tsx` · `radio.tsx` · `switch.tsx` · `form-field.tsx` — plus a colocated `*.test.tsx` per component.
**Guardrail: nothing else. Sibling pebbles own other `src/` files this wave.**

## 4. Implementation spec

- **Button:** variants `primary | secondary | ghost | destructive` (token colors only — navy primary, danger red), sizes `sm | md | lg`, `loading` (spinner + `aria-busy`, click-suppressed) and `disabled` states, renders `<button>` with `type` defaulting to `"button"`.
- **Input/Select/Textarea:** controlled + uncontrolled, error state (token danger border + `aria-invalid`), sizes; Select is a styled native `<select>` (data-frugal, mobile-correct).
- **OtpField:** 6 digits, one cell each; auto-advance on input, backspace moves back, **full-code paste distributes across cells**, `inputMode="numeric"` + `autocomplete="one-time-code"`, fires `onComplete(code)`.
- **Checkbox/Radio/Switch:** native inputs visually styled via tokens (no div-role fakery); Switch is a checkbox with `role="switch"`.
- **FormField:** wraps any control with label / help text / error message; wires `htmlFor`, `aria-describedby` (help + error ids), required marker.
- **No user-facing literals anywhere** — every string (label, error, placeholder, aria-label) arrives via props; apps translate. Enforce with the lint rule already active at warn.
- All interactive targets **≥44px** at `md`; `focus-visible` ring via `--focus-ring` token; motion uses token durations/easings and respects `prefers-reduced-motion` (keyframes already global in `base.css`).

## 5. UI/UX & styling

Tokens only (Tailwind preset classes / CSS vars) — arbitrary color values are rejected by the preset. Pill radius for Switch, `--r` for fields, JetBrains Mono for OTP cells.

## 6. Responsiveness

360px-first: fields full-width by default; OTP cells fit 6-up at 360px with ≥44px touch targets.

## 7. Performance

Zero new deps; no client-side JS beyond React itself; components are client components only where interactivity requires (`"use client"` on interactive ones).

## 8. SEO

N/A (library).

## 9. Security

No `dangerouslySetInnerHTML`; OtpField never logs values; no autofill traps.

## 10. Tests (RUN before reporting)

Per component with RTL (`// @vitest-environment jsdom` docblock): Button click/disabled/loading-suppression; Input error `aria-invalid`; OtpField typing auto-advance, backspace, **paste fills 6 cells**, `onComplete` fires once; Switch `role="switch"` toggles; FormField associates label + describedby (help and error). Keyboard operability (tab/space/enter) on Button/Checkbox/Switch.
Commands: `pnpm --filter @vergeo/ui test`, `pnpm --filter @vergeo/ui typecheck`, `pnpm lint`, `pnpm test` (repo green).

## 11. Acceptance criteria / DoD

- [ ] All 9 components render from typed props, keyboard + screen-reader operable, errors announced.
- [ ] OTP paste/backspace/auto-advance behavior tested; numeric keyboard on mobile.
- [ ] ≥44px targets at md; focus-visible rings; zero user-facing literals.
- [ ] No files outside the list; no new deps; repo suite green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P03 — Form controls
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste actual test output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
