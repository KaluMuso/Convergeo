> **Prepend `prompts/_header.md`.** Branch `agent/ui-p4-desktop-responsive` from + PR against **`master`**. **⚙ Do NOT use `git stash`.** Foreground blocking only. Commit trailers required:
> `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
> `Claude-Session: https://claude.ai/code/session_0182ebfSrQf83JNZCiKqjAby`
> PR title: `UI-P4: customer desktop-responsive layer + homepage richness`.

# UI-P4 — Customer app: professional desktop layout (≥1024px) + homepage that never looks empty

## Why (founder feedback, 2026-07-12, on the live staging deploy)

The customer app renders its 360px mobile-first layout at ALL viewport widths: on a laptop the founder sees a narrow column, a mobile bottom-tab bar, and oversized display type — it reads as unfinished next to the committed design intent in `docs/designs/` and mainstream marketplaces. **Mobile (<1024px) is the locked primary experience and must remain pixel-identical.** This pebble adds a distinct, professional **desktop layer** at `lg:` (1024px+), plus a homepage that renders rich content from live data even before admin merch slots are configured.

## Ground truth to read FIRST

- `docs/designs/SELECTION.md` + `docs/designs/TOKENS.md` — locked tokens & strongest design elements.
- `docs/designs/Vergeo_v1_Standalone.html` and `Vergeo_Prototype_Standalone.html` — committed design variants (open, study header/hero/category/product-grid structures).
- `apps/customer/app/[locale]/(shop)/layout.tsx` — the shell (bottom nav lives here or nearby).
- The existing token utilities in `packages/ui/src/styles/theme.css` (bg/surface/panel/text/primary/etc. + motion utilities from UI-P2). **No new colors — tokens only.**

## Tasks

1. **Responsive shell (`lg:` breakpoint):**
   - **Desktop header** (lg+ only): logo · full-width search bar · primary nav links (Browse, Services, Events, Ask Vergeo) · account + cart + theme toggle on the right. Sticky, `bg-surface`/`border-border`.
   - **Hide the bottom tab bar on lg+** (`lg:hidden`) — it is mobile chrome.
   - Content container: `max-w-7xl mx-auto` (~1280px) with sensible gutters on lg; keep the current single-column mobile flow untouched below lg.
   - Footer: multi-column on lg (already columnar — verify + align to container).

2. **Homepage richness (data-driven default, config still wins):**
   - Today the home renders only config-driven merch slots → empty DB = empty page. Add a **data-driven default**: when no merch config exists, render (a) a hero band (existing escrow/trust messaging + CTA, token gradient `from-primary-deep to-primary`), (b) a **category tile rail** from the live category tree (top departments, `cat-*` token accents), (c) **product rails** ("New on Vergeo5", per-department rows) from the catalog, (d) the existing sell-on-Vergeo5 CTA. If admin merch slots ARE configured, they take precedence (do not remove that path).
   - Empty-DB safety: every rail renders nothing (not a broken section) when its query is empty — the current welcome message remains the final fallback.
   - SSR/ISR-friendly: fetch via the existing server-side data paths (Supabase server client / existing catalog fetchers) — no new client-side data libraries.

3. **PLP/search on desktop:** filters/facets as a left sidebar on lg (they're a sheet/accordion on mobile — keep that); product grid `lg:grid-cols-4` (mobile stays 2); PDP two-column on lg (gallery left, buy-box right, sticky buy-box within viewport).

4. **Type & density on lg:** the display font sizes are clamp()-based and mobile-tuned; verify hero/h1 don't balloon on desktop (cap via the existing clamp upper bounds or lg overrides). Cards get denser padding on lg. Touch targets stay ≥44px on mobile.

## Files (ownership)

- `apps/customer/**` (layout shell, home page, PLP/PDP/search pages, components) — responsive + homepage-default work.
- `packages/ui/src/**` ONLY if a shared component needs a responsive variant prop/classes (e.g. product-card density) — additive, keep snapshots green (update + say so if markup changes).
- **Do NOT touch** `apps/vendor`, `apps/admin`, `services/api`, `supabase/migrations`, `packages/types/src/db.ts`, `pnpm-lock.yaml` (no new deps), `ci.yml`/`perf.yml`. `lighthouserc.json`: if a route's gz JS genuinely grows past its ceiling, STOP and report the delta — responsive work is CSS-classes-first and should be ~free; data-driven home rails may add a little RSC payload but NOT client JS.

## Constraints

- **Mobile (<1024px) visually unchanged** — this is additive `lg:` layering, not a redesign.
- Tokens only (no ad-hoc colors/spacing); zero hardcoded user-facing strings (new strings → `home.json`/existing namespaces via next-intl, EN + key parity per the i18n lint).
- Customer routes stay ≤150KB gz JS; images keep WebP/AVIF+lazy; reuse UI-P2 motion utilities (`motion-rise` etc.) for the new rails; `prefers-reduced-motion` already global.
- A11y AA: header nav keyboard-navigable, landmarks (`header`/`nav`/`main`), focus states.

## Build/verify (scoped; no full turbo build)

```
pnpm --filter @vergeo/ui test
pnpm --filter customer typecheck && pnpm --filter customer lint && pnpm --filter customer test
pnpm --filter customer build   # note any route size deltas
```

(Package name may be `customer` not `@vergeo/customer` — verify with `cat apps/customer/package.json`.)

## Report

STATUS / FILES / DEVIATIONS / WHAT-MOVED (desktop shell, homepage rails + fallback chain, PLP sidebar, PDP 2-col, type caps) / TESTS (5 tails + route deltas) / SCREENSHOT-DESCRIPTION (mobile unchanged; desktop before→after) / QUESTIONS.
