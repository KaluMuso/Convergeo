> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Branch from and PR against **`master`**. Wave 2 runs 7 pebbles in parallel — **touch ONLY your files below**; do NOT touch `pnpm-lock.yaml`, `packages/ui/package.json`, `packages/ui/tsconfig.json`, or any `messages/*.json`.

# M02-P06 — Navigation

## 1. Context

**Wave 2 (parallel ×7).** On `master`: tokens + CSS vars/keyframes, fonts, i18n. Test toolchain pre-wired (react 19, RTL, user-event, jest-dom, jsdom): component tests start with a `// @vitest-environment jsdom` docblock + `import "@testing-library/jest-dom/vitest";` — do NOT add a vitest.config.ts. Deep imports via `@vergeo/ui/src/*`. Spec: `docs/plan/02-pebbles/M02-design-system.md` §P06; patterns: `docs/designs/SELECTION.md` §3 (TopNav/BottomNav rows).

## 2. Objective & scope

Navigation kit: TopNav, BottomNav, Tabs, Breadcrumbs, Stepper, Pagination (load-more pattern).
**Non-goals:** no routing logic (framework-agnostic: hrefs + `active` flags via props; accept a `LinkComponent` prop defaulting to `<a>` so apps inject `next/link`), no mega-menu content (app concern later), no forms/cards/overlays/media (siblings), no new deps, no barrel.

## 3. Files (create ONLY these — all under `packages/ui/src/`)

`top-nav.tsx` · `bottom-nav.tsx` · `tabs.tsx` · `breadcrumbs.tsx` · `stepper.tsx` · `pagination.tsx` + colocated `*.test.tsx`.
**Guardrail: nothing else.**

## 4. Implementation spec

- **TopNav:** sticky cream bar; slots: logo node, **search slot** (ReactNode — search itself is M05), action buttons, **cart badge** (count prop, hidden at 0, "99+" cap); gains `--shadow-1` after scroll (IntersectionObserver or scroll listener, passive); `<header>`/`<nav>` semantics + skip-link target id.
- **BottomNav:** **5 config-driven slots** (`{key, icon: ReactNode, label, href, active, badge?}[]` — apps decide tabs, e.g. Home · Browse · Ask ✦ · Orders · Account); fixed bottom, 56px + **safe-area inset padding** (`env(safe-area-inset-bottom)`); active state = dot + label color per SELECTION; ≥44px targets; `aria-current="page"` on active.
- **Tabs:** roving-tabindex tablist (arrow keys), `aria-selected`, panel wiring; controlled + uncontrolled.
- **Breadcrumbs:** `<nav aria-label>` + ordered list, collapses middle items >3 deep at 360px, current item `aria-current`.
- **Stepper:** checkout progress (≤4 steps): done/current/upcoming states, screen-reader step announcement ("step 2 of 4" via visually-hidden text), never interactive-forward (only completed steps clickable, optional).
- **Pagination:** **"load more" pattern primary** (data frugality — button + loading state + remaining-count prop); classic numbered pager as secondary export in the same file for admin tables.
- All copy/labels/aria strings via props; no literals.

## 5. UI/UX & styling

Tokens only; active dot + pill highlights per SELECTION; `--ease-std` for nav surfaces.

## 6. Responsiveness

BottomNav thumb-reachable at 360px, hidden ≥768px (class hook, app decides); TopNav condenses (slots stack via props, not media queries inside the lib where avoidable).

## 7. Performance

Scroll listener passive + throttled; no layout thrash; zero new deps.

## 8. SEO

Real `<a>` hrefs via LinkComponent ensure crawlable nav; semantic `<nav>` landmarks.

## 9. Security

Hrefs rendered as given — no `javascript:` filtering needed at lib level but do not eval anything; no innerHTML.

## 10. Tests (RUN before reporting)

BottomNav: renders 5 slots, `aria-current` on active, badge count + 99+ cap, safe-area style present. TopNav: cart badge hides at 0, scrolled-shadow class toggles (mock scroll). Tabs: arrow-key roving focus + `aria-selected`. Breadcrumbs: collapse >3, `aria-current`. Stepper: states + SR text. Pagination: load-more fires with loading state, remaining count renders.
Commands: `pnpm --filter @vergeo/ui test|typecheck`, `pnpm lint`, `pnpm test`.

## 11. Acceptance criteria / DoD

- [ ] BottomNav config-driven, 44px targets, safe-area insets, active dot per SELECTION.
- [ ] Tabs fully keyboard-operable; breadcrumbs collapse at depth.
- [ ] Load-more is the primary pagination export.
- [ ] Framework-agnostic links via LinkComponent prop; no literals; repo green.

## 12. IMPLEMENTATION REPORT

When finished, output an **Implementation Report** in exactly this format:
**PEBBLE:** M02-P06 — Navigation
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** each path + one-line description
**DEVIATIONS:** (or "none")
**TESTS:** paste actual test output
**EXCERPTS:** none expected — state "none"
**QUESTIONS:** (or "none")
