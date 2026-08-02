> **Prepend `prompts/_header.md` (PROJECT HEADER) above this prompt.** Composer sessions share no memory — the header is required context.

# R02-P19 — Grade-A browser pass: UX, a11y, SEO, performance against live data `[OPS+CODE]`

## 1. Context
**Wave W7.** Runs **after W1–W6** — against real vendors and real inventory (R02-P09), because a UX verdict formed on demo data is a verdict about demo data.

Prior UI work (UI-P1/P2/P3, 2026-07-12) delivered design tokens, dark mode, a motion layer, skeletons and a desktop layer, and fixed the orphaned-token bug. That was a **code** pass. It has never been validated **page by page in a browser against the deployed product**, which is the only thing that can justify calling the experience Grade A.

Chromium + Playwright are pre-installed (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); **do not run `playwright install`**.

**Type:** `[OPS+CODE]` — findings are recorded here; anything beyond a trivial fix becomes its own pebble.

## 2. Objective & scope
A route-by-route verified record of UX, accessibility, SEO and performance, with in-scope defects fixed and the rest triaged.
**Non-goals:** redesign; new features; changing design tokens wholesale.

## 3. Files (edit ONLY these)
- `docs/production-readiness/<YYYY-MM-DD>/grade-a-browser-pass.md` (new — the deliverable)
- `e2e/specs/a11y-smoke.spec.ts` — extend the existing spec
- Targeted fixes only, each ≤~20 lines and named in the report

## 4. Implementation spec
Walk **every customer route** (home, PLP, PDP, search, compare, categories, cart, checkout, order, account, directory, events, services, supplies, clips, share pages, legal), plus vendor and admin entry points, at **360px Fast-3G first**, then 768px and desktop, in **light and dark**, in **en** and **bem**.

Per route record: LCP, CLS, INP, first-load gz JS, Lighthouse Perf/SEO/A11y, axe violations by severity, and a screenshot.

Check specifically:
- **Budgets** — ≤150KB gz per customer route; LCP ≤2.5s Fast-3G/360px; Lighthouse mobile Perf ≥90 / SEO ≥95 / A11y ≥95.
- **A11y** — keyboard traversal and visible focus on every interactive element; touch targets ≥44px; AA contrast in **both** themes (the dark primary-button contrast fix is precedent); form labels and error announcement; heading order; `prefers-reduced-motion` neutralises every animation.
- **SEO** — one `h1`; canonical; OG/Twitter; `hreflang` across the four public locales; JSON-LD on product/event; sitemap; `noindex` where intended (supplies gate) and **not** where it is not.
- **Honesty** — no `localhost` in served HTML; no demo listing on any public surface (R02-P09); empty states that read as intentional rather than broken; escrow language present and consistent ("You paid → Held by Vergeo5 → Released").
- **Data cost** — total transfer for a 10-item browse session and a full checkout, in KB. This is a 3G market; a number nobody measured is a number nobody managed.

## 5. Security / conventions
Read-only against production; no test orders on production. Redact PII in screenshots. No new runtime dependency.

## 10. Tests (RUN before reporting)
- `pnpm e2e` (Playwright, Fast-3G/360px) — extend `a11y-smoke.spec.ts` to cover every route in the walk.
- Lighthouse CI via `lighthouserc.json`.
- `node scripts/ci/bundle-guard.mjs`.
- Re-run after each fix; paste before/after for anything changed.

## 11. Acceptance criteria / DoD
- [ ] Every route has recorded metrics + screenshot; none skipped silently.
- [ ] Zero critical/serious axe violations, or each is triaged with an owner.
- [ ] All budgets met or a documented waiver exists.
- [ ] `prefers-reduced-motion` respected everywhere.
- [ ] Both themes AA; both locales render without overflow at 360px.
- [ ] Session data-cost numbers recorded.

## 12. IMPLEMENTATION REPORT
**PEBBLE:** R02-P19 — Grade-A browser pass
**STATUS:** COMPLETE | PARTIAL | BLOCKED
**FILES:** … · **DEVIATIONS:** … · **TESTS:** paste the per-route table · **EXCERPTS:** worst three routes + what was fixed · **QUESTIONS:** list follow-up pebbles
