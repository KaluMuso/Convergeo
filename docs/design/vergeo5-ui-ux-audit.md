# Vergeo5 Customer Marketplace — UI/UX Audit & Redesign Strategy

**Date:** 2026-07-20  
**Live site audited:** https://vergeo5.com/en  
**Repository branch audited:** `master` @ commit contemporaneous with this report  
**Scope:** Customer app (`apps/customer`) + shared design system (`packages/ui`)  
**Evidence screenshots:** [`evidence/`](./evidence/)  
**Live field notes:** [`evidence/live-audit-findings.md`](./evidence/live-audit-findings.md)

This is an **audit and redesign-planning** document. It does not ship production UI changes. Recommendations are sized for sequential, reviewable PRs.

---

## 1. Executive verdict

### Present design maturity

Vergeo5’s customer UI is a **scaffold-grade marketplace shell with real commerce bones**, not a finished commercial product. The token system, multi-vendor PDP, escrow messaging, progressive PLP loading, and locale architecture are ahead of typical early MVPs. Visual coherence, iconography, navigation discipline, engagement loops (wishlist / recently viewed), and dark-mode palette quality are behind the bar set by Amazon/eBay/Alibaba _principles_ (discovery density, seller confidence, purchase clarity).

**Overall commercial readiness: 5.0 / 10.**

### Five most damaging problems

1. **Aubergine/purple dark mode** — page ground remapped to `--panel: #241B30` / `--panel-2: #2E2440`. Confirmed live; rooted in `SELECTION.md` §5 synthesis that does **not** appear in any of the six HTML design sources. Undermines product photography and trust.
2. **Brand typography never loads** — `fontVariables()` in `packages/ui/src/fonts.ts` is unused by all apps. Live UI falls back to Georgia/system stacks, so the designed DM Sans / DM Serif Display identity never ships.
3. **Emoji-as-iconography + dual headers** — shop chrome uses emoji for nav/cart (`apps/customer/app/[locale]/(shop)/layout.tsx`); desktop reimplements nav outside `TopNav`. Reads as unfinished, not marketplace-grade.
4. **Hero is trust-essay, not merchandising plane** — first viewport is an inset gradient card with escrow pills and dual CTAs, no product imagery (`HomeHeroBand`). Purpose is clear; commercial desire and brand dominance are weak.
5. **Dead marketplace affordances** — wishlist/quick-add labels exist but `ListingGrid` never wires handlers; bottom nav omits Orders and duplicates Browse/Categories; Directory is a pillar but absent from primary nav.

### Strongest existing elements

- Multi-vendor PDP comparison + `/compare` (core marketplace differentiator).
- Escrow honesty in copy and checkout (You pay → Held → Released).
- Tokenised light palette (cream ground, navy primary, gold accent) with tested contrast pairs.
- Progressive PLP load with Save-Data-aware “Load more”.
- Theme FOUC prevention (`ThemeScript` + `data-theme`) — architecture is sound; palette values are wrong.
- Category pastel tile language (live and in concepts) — distinctive for Zambia without copying Amazon.

### Refinement vs redesign

**Partial redesign of chrome + foundations; retain commerce IA.**  
Do **not** throw away the shop route map, PDP comparison model, or token pipeline. Do **replace** dark palette, icon system, hero composition, nav model, and enforce component usage. Treat as **major visual/system consolidation**, not a greenfield rewrite.

### Recommended overall design direction

**“Warm light marketplace, charcoal dark optional.”**

- Light-first cream page ground + white product surfaces + navy actions + gold sale/trust accents.
- Mobile shell: sticky search, bottom nav `Home · Browse · Ask · Orders · Account`.
- Discovery density closer to Amazon principles; seller/trust clarity closer to eBay; category merchandising closer to Alibaba — **without copying their visuals**.
- Dark mode kept as `system`/`light`/`dark`, but **neutral warm charcoal**, not aubergine. Theme control moves to Account → Preferences (and account menu), not primary navbar.
- Hybrid of HTML concepts: Offline Bundle cards + Prototype-offline mobile nav + Wireframes escrow/multi-vendor flows + Prototype Standalone trust ladder; **reject** SELECTION aubergine panels and Offline’s floating hero collage as default.

---

## 2. Evidence log

Legend for **Evidence class:**

| Class         | Meaning                                                     |
| ------------- | ----------------------------------------------------------- |
| **Live**      | Observed on https://vergeo5.com                             |
| **Code**      | Confirmed in repository                                     |
| **Inference** | Reasonable conclusion; needs product/analytics confirmation |
| **Untested**  | Could not exercise in this audit                            |
| **Drift**     | Live behaviour vs `master` may diverge (env/API/content)    |

| ID  | Route / screen    | Viewport | Screenshot                                                                         | Code path                                                           | Observed problem                                                                                                              | Why it matters                                                                                              | Recommended change                                                                          | Class                    |
| --- | ----------------- | -------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------ |
| E01 | All (dark)        | 1366     | `evidence/live-dark-mode-purple-tint-1366.png`, `live-products-dark-mode-1366.png` | `packages/ui/src/styles/base.css` L98–127; `tokens.ts` L11–14       | Page bg/surfaces are purple-aubergine                                                                                         | Weakens photos, prices, commercial trust; matches user complaint                                            | Remap dark to warm charcoal; stop aliasing `--bg` to `--panel`                              | Live + Code              |
| E02 | Footer (light)    | 1366     | `live-home-1366.png` (DevTools shows `#241B30`)                                    | `packages/ui/src/footer.tsx`                                        | Footer hard-codes JS `tokens.colors.panel`                                                                                    | Purple footer in light mode; jarring                                                                        | Footer uses `bg-panel` CSS vars after panel→charcoal; or `bg-bg-2` light footer             | Live + Code              |
| E03 | Global            | all      | —                                                                                  | `packages/ui/src/fonts.ts`; `apps/customer/app/[locale]/layout.tsx` | `fontVariables()` never applied                                                                                               | Designed typeface identity missing                                                                          | Wire on `<html>` in customer/vendor/admin layouts                                           | Code                     |
| E04 | Shop chrome       | 360–1440 | `live-home-360-top.png`                                                            | `(shop)/layout.tsx` `navIcon`                                       | Emoji icons in top/bottom nav                                                                                                 | Unprofessional; a11y/font fallback risk                                                                     | SVG icon set in `@vergeo/ui`                                                                | Live + Code              |
| E05 | Home              | 360/1366 | `live-home-360-top.png`, `live-home-1366.png`                                      | `home-default.tsx` `HomeHeroBand`                                   | Inset gradient hero; escrow pills dominate first viewport; no product image plane                                             | Feels like a trust landing page, not a marketplace                                                          | Full-bleed or edge-to-edge merch hero; escrow → compact trust strip below fold of hero CTAs | Live + Code              |
| E06 | Home              | 1366     | `live-home-1366.png`                                                               | category grid components                                            | Very large radii, low density category tiles                                                                                  | Looks soft/template; weak browse efficiency on desktop                                                      | Tighten radius to `--r`/`--r-lg`; denser 6–8 tile grid on desktop                           | Live                     |
| E07 | PLP/home cards    | 1366     | `live-category-electronics-1366.png`                                               | `product-card.tsx`; `listing-grid.tsx`                              | SAMPLE LISTING badges; wishlist/quick-add unwired                                                                             | Demo residue + dead affordances                                                                             | Hide sample in prod; wire wishlist or remove labels                                         | Live + Code              |
| E08 | Search            | 1366     | `live-search-unavailable-1366.png`                                                 | search page + API                                                   | “Search unavailable” for `q=phone`                                                                                            | Blocks primary discovery                                                                                    | Treat as **ops/API reliability** P0; UI empty/error state already exists                    | Live / Drift             |
| E09 | PDP ATC           | 1366     | `live-add-to-cart-error-1366.png`                                                  | buy-box + cart API                                                  | Add to cart connection error                                                                                                  | Blocks conversion                                                                                           | Ops/API P0; keep resilient error UX                                                         | Live / Drift             |
| E10 | PDP               | 1366     | `live-product-detail-1366.png`                                                     | `p/[slug]/page.tsx`                                                 | Placeholder/wrong image; sparse below fold; table-biased compare                                                              | Damages trust; mobile compare weak                                                                          | Content QA; mobile compare as cards; sticky ATC on mobile                                   | Live                     |
| E11 | Nav               | mobile   | `live-home-360-top.png`                                                            | `(shop)/layout.tsx` bottomItems                                     | Bottom: Home / All Categories / Browse / Ask / Account — no Orders; Categories+Browse compete                                 | IA overload; Orders orphaned                                                                                | SELECTION synthesis: Home · Browse · Ask · Orders · Account                                 | Live + Code              |
| E12 | Nav               | desktop  | `live-home-1366.png`                                                               | `desktop-header.tsx`                                                | Theme toggle in primary header; Directory missing; verticals crowded                                                          | Theme competes with cart/account; Directory buried                                                          | Theme → preferences; add Directory; demote Supplies                                         | Live + Code              |
| E13 | Theme             | —        | —                                                                                  | `theme-toggle.tsx`, shop layout                                     | Toggle permanently in mobile top + desktop header                                                                             | User preference + conversion priority argue against                                                         | Keep system default; relocate control                                                       | Code                     |
| E14 | Cards             | —        | —                                                                                  | `product-card.tsx`                                                  | Dual styling (inline CSS vars) vs Tailwind primitives; ♥ wishlist                                                             | Inconsistent polish                                                                                         | Refactor to token utilities + icon components                                               | Code                     |
| E15 | Images            | —        | —                                                                                  | `cloudinary-image.tsx`                                              | Client `<img>`, no `next/image`                                                                                               | Hydration cost on grids                                                                                     | RSC-safe image shell                                                                        | Code                     |
| E16 | A11y              | —        | —                                                                                  | `tokens.ts` contrastPairs                                           | `--text-3` ~3.2:1 excluded from AA tests; dark danger on surface fails                                                        | Muted UI + destructive CTAs unsafe                                                                          | Raise muted text; `--on-danger` token                                                       | Code                     |
| E17 | Motion            | —        | —                                                                                  | `base.css`, `theme.css`                                             | Tokens good; float/pulse unused; card-lift still displaces under reduced-motion; invalid chained `@keyframes` in reduce block | Incomplete motion system                                                                                    | Fix reduce path; ship restrained matrix only                                                | Code                     |
| E18 | Auth              | 1366     | `live-auth-signin-1366.png`                                                        | auth login shell                                                    | Small brand mark; Google button visually weak                                                                                 | Weak brand-first auth                                                                                       | Larger wordmark; clear secondary Google style                                               | Live                     |
| E19 | Account           | —        | —                                                                                  | `account/layout.tsx`                                                | Account leaves shop chrome (no bottom nav)                                                                                    | Orders/tickets feel disconnected                                                                            | Shared chrome or persistent bottom nav                                                      | Code                     |
| E20 | Hamburger         | 360      | —                                                                                  | shop layout                                                         | Live note claimed hamburger broken                                                                                            | **Correction:** no hamburger exists; mobile uses condensed TopNav + bottom nav. Likely mistap of theme/cart | Do not “fix hamburger”; improve Browse sheet instead                                        | Inference / Live misread |
| E21 | HTML concepts     | —        | —                                                                                  | `docs/designs/*.html`, `SELECTION.md`                               | Aubergine `#241B30` invented in SELECTION, not in HTML sources                                                                | Dark purple is a synthesis error                                                                            | Revise tokens; amend SELECTION dark section                                                 | Code                     |
| E22 | Checkout          | —        | —                                                                                  | checkout routes                                                     | Escrow stepped checkout in code                                                                                               | **Untested live** (cart broken)                                                                             | Verify after cart API healthy                                                               | Untested                 |
| E23 | Auth’d account    | —        | —                                                                                  | `/account/*`                                                        | Preferences exist for theme home                                                                                              | **Untested** without credentials                                                                            | Confirm theme relocation UX                                                                 | Untested                 |
| E24 | Wishlist / recent | —        | —                                                                                  | no routes                                                           | No wishlist or recently-viewed pages                                                                                          | Missing retention loops                                                                                     | P4 after wire local wishlist                                                                | Code                     |

---

## 3. Current-state scorecard

| Dimension                        | Score | Justification                                                                                                      |
| -------------------------------- | ----: | ------------------------------------------------------------------------------------------------------------------ |
| Brand coherence                  |     4 | Cream/navy intent exists in tokens; live fonts unwired; aubergine panels fight brand; wordmark is text-only in nav |
| Visual polish                    |     4 | Soft radii, emoji chrome, inset hero, SAMPLE badges — scaffold polish, not commercial                              |
| Typography                       |     3 | Designed scale unused; Georgia fallback; serif/sans mix inconsistent when fonts fail                               |
| Colour system                    |     5 | Light tokens coherent; dark aubergine fails; `--text-3`/accent contrast gaps                                       |
| Layout consistency               |     5 | Token spacing used; dual headers, nested `<main>`, one-off CTAs                                                    |
| Navigation                       |     5 | Search-forward desktop OK; mobile IA overloaded; Orders/Directory misplaced                                        |
| Mobile usability                 |     6 | Bottom nav + 44px targets mostly OK; one-handed path incomplete; no Browse sheet                                   |
| Product discovery                |     6 | Categories + PLP facets + progressive load strong; live search API failure; no personalisation                     |
| Product-card effectiveness       |     5 | Vendor/price/rating present; logistics pills/wishlist/quick-add missing or dead                                    |
| Product-detail effectiveness     |     7 | Multi-vendor + sticky desktop buy box strong; mobile sticky ATC / compare cards weaker                             |
| Marketplace trust                |     7 | Escrow messaging excellent; verification ladder not on browse cards; sample listings hurt                          |
| Accessibility                    |     6 | Focus traps/modals/tabs solid; contrast + mega-menu focus + sm targets lag                                         |
| Motion and feedback              |     6 | CSS motion tokens good; sparse application; cart live regions exist                                                |
| Performance / perceived speed    |     7 | Bundle gate, lazy Sentry/GA, progressive load; client images + home motion stacking                                |
| Design-system maturity           |   5.5 | Broad component kit + tests; not enforced end-to-end                                                               |
| **Overall commercial readiness** | **5** | Credible soft-launch shell; not yet purchase-confident marketplace chrome                                          |

---

## 4. Page-by-page assessment

### 4.1 Homepage `/[locale]`

| Aspect                 | Assessment                                                                                                                                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Current purpose**    | Explain Vergeo5 + surface categories/products/services/vendors                                                                                                                                                                   |
| **Weaknesses**         | Hero = escrow essay in inset card; categories after trust; SAMPLE badges; emoji nav; no recently viewed; end promo strip missing                                                                                                 |
| **Proposed hierarchy** | 1) Sticky search chrome 2) Merch hero (brand + 1 headline + 1 sentence + CTAs + image plane) 3) Compact trust chips 4) Category grid 5) Flash/campaign 6) New/department rails 7) Events 8) Services+RFQ 9) Vendors 10) Sell CTA |
| **Desktop**            | Contained max-w-7xl rails; hero can be full-bleed; mega-menu featured minis                                                                                                                                                      |
| **Mobile**             | No stats/float collage; horizontal rails; trust as 2×2 chips                                                                                                                                                                     |
| **Retain**             | Trust strip content, category pastels, product rails, sell CTA module system                                                                                                                                                     |
| **Redesign**           | `HomeHeroBand`, category density, nav chrome                                                                                                                                                                                     |
| **Remove/relocate**    | Escrow step pills from hero → trust strip; theme toggle from top bar                                                                                                                                                             |

### 4.2 Search `/search`

| Aspect              | Assessment                                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| **Current purpose** | Universal search across kinds                                                                          |
| **Weaknesses**      | Live API failure; suggestions not obvious on home field; kind tabs good when healthy                   |
| **Proposed**        | Persistent search; suggestion dropdown; facets for products after query; zero-state → categories + Ask |
| **Pagination**      | Progressive append within kind; reset on query/kind change                                             |
| **Retain**          | Kind tabs, recent searches, Ask fallback                                                               |
| **Redesign**        | Error/empty visual weight; suggestion UI                                                               |

### 4.3 Categories `/categories`, PLP `/c/[...slug]`

| Aspect              | Assessment                                                                        |
| ------------------- | --------------------------------------------------------------------------------- |
| **Current purpose** | Taxonomy browse + faceted listing                                                 |
| **Weaknesses**      | SAMPLE badges; unwired card actions; filter summary weak                          |
| **Proposed**        | Breadcrumb + count + sort + filter chips summary; 2-col mobile / 3–4 desktop grid |
| **Pagination**      | Cursor progressive + Load more (keep); Save-Data button-only                      |
| **Retain**          | Facets, sort, progressive load                                                    |
| **Redesign**        | ProductCard composition; applied-filter bar                                       |

### 4.4 Product detail `/p/[slug]`

| Aspect              | Assessment                                                                                              |
| ------------------- | ------------------------------------------------------------------------------------------------------- |
| **Current purpose** | Canonical product + choose listing/seller + buy                                                         |
| **Weaknesses**      | Image quality; compare table on mobile; trust below fold on small screens; no sticky ATC mobile         |
| **Mobile order**    | Title → gallery → price/stock → sticky ATC bar → trust → seller compare cards → vendor → tabs → related |
| **Desktop order**   | Keep gallery \| sticky buy box; full-width compare table                                                |
| **Retain**          | Multi-offer selection, `/compare`, escrow honesty, related rail                                         |
| **Redesign**        | Mobile compare; sticky purchase bar; wishlist                                                           |

### 4.5 Compare `/compare`

| Aspect                                                        | Assessment |
| ------------------------------------------------------------- | ---------- |
| **Retain** as first-class marketplace tool                    |
| **Enhance** with delivery/pickup/ETA columns when data mature |

### 4.6 Cart `/cart`

| Aspect         | Assessment                                                            |
| -------------- | --------------------------------------------------------------------- |
| **Current**    | Vendor-grouped cart page + empty state                                |
| **Weaknesses** | Live ATC broken (drift); empty state emoji                            |
| **Proposed**   | Keep page (not only drawer) for MoMo/mixed types; optional mini-cart  |
| **Retain**     | Vendor grouping, qty stepper                                          |
| **Redesign**   | Empty illustration (non-emoji); clearer escrow teaser before checkout |

### 4.7 Checkout `/checkout*`

| Aspect            | Assessment                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Code strength** | Stepped flow + escrow timeline                                                                                           |
| **Live**          | Untested                                                                                                                 |
| **Proposed**      | Keep stepped Items → Delivery → Pay; MoMo method cards (Prototype offline); explicit STK pending (never jump to success) |

### 4.8 Auth `/login` `/signup` `/otp`

| Aspect         | Assessment                                        |
| -------------- | ------------------------------------------------- |
| **Strengths**  | Phone-first +260                                  |
| **Weaknesses** | Brand-weak shell; Google button appearance        |
| **Proposed**   | Brand-dominant auth layout; clear secondary OAuth |

### 4.9 Account `/account/*`

| Aspect           | Assessment                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------- |
| **Weaknesses**   | Leaves shop chrome; Orders/Tickets/Jobs not in account primary nav list; theme buried       |
| **Proposed hub** | Orders · Tickets · Jobs · Saved · Addresses · Preferences (theme here) · Privacy · Business |
| **Retain**       | Preferences form, address manager, order timeline                                           |

### 4.10 Directory `/directory`, Vendor `/v/[slug]`

| Aspect                                                                       | Assessment |
| ---------------------------------------------------------------------------- | ---------- |
| **Promote** Directory into desktop primary nav                               |
| **Surface** verification ladder on cards (○/✓/✓✓/★) separate from paid tiers |

### 4.11 Services / Events / Ask / Supplies

| Surface  | Notes                                                     |
| -------- | --------------------------------------------------------- |
| Services | Keep RFQ entry; panel heroes → charcoal not aubergine     |
| Events   | Keep capacity patterns from concepts                      |
| Ask      | Keep bottom-nav presence; add typing pulse when streaming |
| Supplies | Gated; remove from always-on primary clutter              |

### 4.12 Loading / empty / error

| State   | Recommendation                                                     |
| ------- | ------------------------------------------------------------------ |
| Loading | Keep shimmer skeletons; reduce home-wide stagger                   |
| Empty   | Icon (SVG) + one sentence + one CTA — no emoji                     |
| Error   | Existing search error pattern is OK; add retry + browse categories |

---

## 5. Proposed information architecture

### 5.1 Site map (customer)

```
/[locale]
├── search
├── categories
├── c/[...slug]          # PLP
├── p/[slug]             # PDP
├── compare
├── cart → checkout → pending|card
├── directory → v/[slug]
├── services → s/[slug], services/post-job
├── events → e/[slug]
├── ask
├── supplies (gated)
├── wishlist             # NEW
├── account/
│   ├── (hub)
│   ├── orders...
│   ├── tickets...
│   ├── jobs...
│   ├── addresses, preferences, privacy, business
│   └── recent           # OPTIONAL later
├── login|signup|otp
├── about|beta|contact|help|sell|legal/*
└── offline
```

### 5.2 Desktop navigation

**Primary:** Logo · **Search** · All Categories ▾ · Directory · Services · Events · Ask  
**Utilities:** Account · Cart  
**Not in primary:** Theme, Language (account/preferences or footer), Supplies (account/gated), Sell (footer + occasional CTA)

**Sticky on scroll:** Logo + Search + Cart (+ Account icon). Mega-menu closes on scroll/Escape.

### 5.3 Mobile navigation

| Layer            | Contents                                                            |
| ---------------- | ------------------------------------------------------------------- |
| Top (sticky)     | Logo · Search field/link · Cart badge                               |
| Bottom           | **Home · Browse · Ask · Orders · Account**                          |
| Browse           | Opens search with chips: Categories · Directory · Services · Events |
| Theme / language | Account → Preferences                                               |

### 5.4 Account menu

1. Orders
2. Tickets
3. Jobs (RFQ)
4. Saved / Wishlist
5. Addresses
6. Preferences (theme: system/light/dark; locale; notifications)
7. Business buyer
8. Privacy
9. Sign out

### 5.5 Footer

Legal · Help · Contact · Sell on Vergeo5 · MoMo note · Locale links · optional app badges (later).  
Light mode: `bg-bg-2` or charcoal panel **after** panel token revision — never purple.

### 5.6 Search + category discovery model

1. Universal search (products default tab).
2. Category tree via mega-menu (desktop) and `/categories` (mobile Browse chip).
3. Directory for seller-led discovery.
4. Ask Vergeo as assisted discovery, not a replacement for browse.

---

## 6. Proposed design system

### 6.1 Colour (semantic tokens)

Keep light cream marketplace; **revise dark/panel**.

| Token                            | Light                                                            | Dark (recommended)                                 | Role                                      |
| -------------------------------- | ---------------------------------------------------------------- | -------------------------------------------------- | ----------------------------------------- |
| `background`                     | `#FAF7F2`                                                        | `#141312`                                          | Page ground                               |
| `background-subtle` (`bg-2`)     | `#F3EDE3`                                                        | `#1C1A18`                                          | Recessed bands                            |
| `surface`                        | `#FFFFFF`                                                        | `#22201E`                                          | Cards, inputs                             |
| `surface-elevated`               | `#FFFFFF` + shadow-2                                             | `#2A2826`                                          | Sheets, sticky bars                       |
| `foreground`                     | `#2A2118`                                                        | `#F2EDE6`                                          | Body                                      |
| `muted`                          | `#6B5A3E`                                                        | `#B0A99F`                                          | Secondary (≥4.5:1)                        |
| `muted-subtle`                   | raise from `#9C8A72` → `#7A6A52` or restrict to large/decorative | `#8A837A`                                          | Tertiary                                  |
| `border`                         | `#E8DFD0`                                                        | `rgba(255,255,255,0.10)`                           | Hairlines                                 |
| `brand` / `primary`              | `#2D4A7A`                                                        | `#7AA0D4`                                          | Actions, links                            |
| `brand-deep`                     | `#1F3557`                                                        | `#5A82B8`                                          | Hover                                     |
| `brand-tint`                     | `#E8F0FA`                                                        | `#2A323C`                                          | Chips                                     |
| `accent`                         | `#C8861A`                                                        | `#D4A04A`                                          | Sale, stars (large text)                  |
| `success` / `warning` / `danger` | keep                                                             | keep + **`on-danger`** light text for dark buttons |
| `price`                          | foreground / brand                                               | foreground                                         | Price emphasis                            |
| `discount`                       | danger or accent-deep                                            | same                                               | −% chips                                  |
| `panel` (marketing chrome only)  | `#1A1816` charcoal                                               | same family                                        | Footer/heroes — **not** page ground alias |

**Reject:** `#241B30`, `#2E2440`, `#9F94B0` as global dark grounds.

### 6.2 Typography

Wire `fontVariables()`:

- Body/UI: **DM Sans**
- Display: **DM Serif Display** (360px-first)
- Mono: JetBrains Mono for IDs/OTP
- Scale: keep `--fs-hero` → `--fs-micro`, `--fs-price`

### 6.3 Spacing / breakpoints / grid

- Keep 4px base (`sp-1`…`sp-16`).
- Breakpoints: retain Tailwind defaults; treat **360** as design floor, **lg (1024)** as desktop chrome switch (already used).
- Content grid: `max-w-7xl` + 16/24px gutters; product grids 2 / 3 / 4 cols.

### 6.4 Radius / border / elevation

| Token    | Value   | Use                                      |
| -------- | ------- | ---------------------------------------- |
| `r-sm`   | 8px     | inputs, chips                            |
| `r`      | 12px    | cards default                            |
| `r-lg`   | 16–18px | hero media only                          |
| `r-pill` | 999px   | search field, badges — **not** every CTA |

Reduce overuse of pill buttons on primary CTAs (prefer `rounded` 12px for solid buttons; pills for filters/search).

Shadows: keep warm `shadow-1/2/3` in light; black-based in dark.

### 6.5 Icons

Replace emoji with 24px stroke SVG set: home, search, ask, orders, account, cart, heart, share, filter, location. Slot API on `BottomNav` / `TopNav`.

### 6.6 Components (foundations)

- **Buttons:** primary / secondary / ghost / danger; RSC-safe `Button` + `LinkButton`.
- **Forms:** existing FormField patterns; ensure 44px targets (deprecate `sm` for primary actions).
- **Cards:** Product / Service / Event / Vendor — white surface, 12px radius, logistics pills.
- **Badges:** NEW, SALE, SAMPLE(dev-only), stock, sponsored.
- **States:** Skeleton (shimmer), EmptyState, ErrorState — SVG illustrations optional later.

### 6.7 Dark mode product decisions (Q&A)

| #   | Question                           | Recommendation                                                                                                                              |
| --- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Appropriate now?                   | **Yes, keep** — many Android users force dark; architecture exists. But light-first for merchandising.                                      |
| 2   | Toggle in main navbar?             | **No.** Competes with search/cart; not a conversion control.                                                                                |
| 3   | Better in preferences?             | **Yes** — Account → Preferences, with light/dark/system. Optional entry in account menu.                                                    |
| 4   | Default?                           | **`system`** — agree with preference.                                                                                                       |
| 5   | Current dark weaken photos/prices? | **Yes** — aubergine cast + lilac muted text.                                                                                                |
| 6   | Tokens causing purple?             | `--panel`, `--panel-2`, `--panel-muted`, dark `--text-3:#7a7088`, dark `--primary-tint:#2e2440`, footer JS hex.                             |
| 7   | Neutral palette?                   | Warm charcoal table in §6.1.                                                                                                                |
| 8   | Surfaces definition?               | Separate `background` / `surface` / `surface-elevated` / `panel` (chrome only).                                                             |
| 9   | Unauth visible theme control?      | **No** in primary chrome. System default handles most; power users find it in account/prefs after signup, or a quiet footer link “Display”. |
| 10  | Persist without FOUC?              | Keep `ThemeScript` + `localStorage` + `data-theme` pre-paint (already good).                                                                |

**Challenge to preference:** Only keep a navbar theme control if analytics show >15% of sessions toggle theme in first visit _and_ support tickets cite discoverability — currently no such evidence. **Decision: relocate.**

---

## 7. Component inventory

| Component            | Current file                                   | Pages         | Problem                     | Action                  | Priority | Destination         |
| -------------------- | ---------------------------------------------- | ------------- | --------------------------- | ----------------------- | -------- | ------------------- |
| Tokens / base.css    | `packages/ui/src/tokens.ts`, `styles/base.css` | all           | Aubergine dark              | **refactor**            | P0       | `@vergeo/ui`        |
| fontVariables        | `packages/ui/src/fonts.ts`                     | unused        | Not wired                   | **retain** + wire       | P0       | app layouts         |
| ThemeToggle          | `theme-toggle.tsx`                             | shop headers  | Wrong placement             | **relocate**            | P0       | account preferences |
| ThemeProvider/Script | theme-*.tsx                                    | layouts       | Solid                       | **retain**              | —        | `@vergeo/ui`        |
| Footer               | `footer.tsx`                                   | locale layout | Hard-coded panel hex        | **refactor**            | P0       | `@vergeo/ui`        |
| TopNav               | `top-nav.tsx`                                  | mobile shop   | Parallel to DesktopHeader   | **merge** slots         | P1       | `@vergeo/ui`        |
| DesktopHeader        | `desktop-header.tsx`                           | shop lg+      | Duplication                 | **merge** into TopNav   | P1       | customer → ui       |
| BottomNav            | `bottom-nav.tsx`                               | shop          | Wrong IA items; emoji       | **refactor**            | P1       | `@vergeo/ui`        |
| ProductCard          | `product-card.tsx`                             | home/PLP      | Inline styles; dead actions | **refactor**            | P1       | `@vergeo/ui`        |
| ListingGrid          | `listing-grid.tsx`                             | PLP/home      | No wishlist/quick-add       | **refactor**            | P1       | customer            |
| PriceBlock           | `price-block.tsx`                              | cards/PDP     | Good (`formatK`)            | **retain**              | —        | `@vergeo/ui`        |
| CloudinaryImage      | `media/cloudinary-image.tsx`                   | media         | Client island               | **refactor**            | P2       | `@vergeo/ui`        |
| Button               | `button.tsx`                                   | forms         | Needless client; underused  | **refactor**            | P2       | `@vergeo/ui`        |
| LinkButton           | —                                              | —             | Missing; 85+ one-off Links  | **add**                 | P1       | `@vergeo/ui`        |
| Icon set             | —                                              | —             | Emoji                       | **add**                 | P0       | `@vergeo/ui/icons`  |
| HomeHeroBand         | `home-default.tsx`                             | home          | Trust essay                 | **replace**             | P1       | customer merch      |
| Hero registry        | `merch/hero-*.tsx`                             | home          | Not full-bleed              | **refactor**            | P1       | `@vergeo/ui/merch`  |
| Panel heroes         | services/events/directory pages                | hubs          | Copy-paste aubergine        | **extract** `PanelHero` | P2       | `@vergeo/ui`        |
| Badge/Pill/Ribbon    | badge/pill/corner-ribbon                       | cards         | Static light hex            | **refactor**            | P2       | `@vergeo/ui`        |
| CategoryMegaMenu     | `category-mega-menu.tsx`                       | desktop       | No focus trap               | **refactor**            | P1       | customer            |
| ImageGallery         | `media/image-gallery.tsx`                      | PDP           | OK client                   | **retain**              | —        | `@vergeo/ui`        |
| Empty/Error/Skeleton | empty-state, error-state, skeleton             | many          | Emoji empty                 | **refactor**            | P2       | `@vergeo/ui`        |
| Qty steppers         | ui `stepper` vs cart `qty-stepper`             | checkout/cart | Name collision              | **retain** + rename     | P3       | clarify             |
| FeedbackWidget       | `feedback-widget.tsx`                          | ?             | a11y gaps                   | **refactor** or remove  | P3       | `@vergeo/ui`        |
| Wishlist page        | —                                              | —             | Missing                     | **add**                 | P4       | customer            |
| AuthLoginShell       | `(auth)/_components`                           | auth          | Brand-weak                  | **refactor**            | P1       | customer            |

**Duplicates / near-duplicates:** DesktopHeader vs TopNav; one-off CTA class strings vs Button; hub aubergine heroes; multiple qty steppers.

---

## 8. Motion specification

**Principle:** Restrained, opacity/transform only, ≤400ms, CSS-first. **Do not add Framer Motion** (bundle gate ≤150KB gz).

| Interaction                | Animation                         | Duration    | Easing       | Reduced-motion     | Implementation                          |
| -------------------------- | --------------------------------- | ----------- | ------------ | ------------------ | --------------------------------------- |
| Section enter              | Fade + 8px rise                   | 250ms       | `--ease-out` | Opacity only       | `.motion-rise` (cap: hero + first rail) |
| Toast in/out               | Slide+fade                        | 250 / 150ms | out / std    | Opacity only       | existing keyframes                      |
| Modal / sheet              | Fade+slide up                     | 250ms       | out          | Opacity only       | modal/bottom-sheet                      |
| Card hover                 | Lift −2px + shadow-1→2            | 250ms       | out          | No movement        | `.card-lift` fix                        |
| Tap / button press         | Scale 0.98                        | 150ms       | std          | No scale           | `.tap` / Button                         |
| Mega-menu open             | Fade + 4px                        | 150–200ms   | std          | Instant show       | CSS                                     |
| Drawer / sheet             | TranslateY                        | 250ms       | out          | Instant            | bottom-sheet                            |
| Accordion / tabs indicator | Height/opacity / underline        | 200ms       | std          | Instant            | tabs                                    |
| Cart / wishlist confirm    | Toast + aria-live                 | 250ms       | out          | Toast opacity      | toast + live region                     |
| Gallery                    | Native scroll; optional crossfade | ≤200ms      | std          | Instant swap       | image-gallery                           |
| Skeleton → content         | Fade                              | 150ms       | std          | Instant            | opacity                                 |
| Filter apply               | List fade                         | 150ms       | std          | Instant            | PLP                                     |
| Progressive load           | Spinner + live region             | —           | —            | Static status text | existing                                |
| Route change               | Optional View Transitions later   | ≤250ms      | out          | Skip               | native VT — **not now**                 |
| Hero float badges          | —                                 | —           | —            | —                  | **Do not ship** on 3G                   |
| Confirm success            | Scale spring                      | 400ms       | spring       | Opacity            | confirm-dialog only                     |

---

## 9. HTML concept evaluation

Concepts reviewed: all six files in `docs/designs/` (see also prior `SELECTION.md`, **challenged** on dark panels).

### 9.1 Per-concept summary

| Concept                         | Philosophy                   | Works                                           | Fails                                               | Marketplace fit         | Translation         |
| ------------------------------- | ---------------------------- | ----------------------------------------------- | --------------------------------------------------- | ----------------------- | ------------------- |
| **Vergeo_Offline_Bundle**       | Editorial cream catalog      | Best ProductCard, mega-menu, mixed cart, motion | No checkout; no bottom nav; busy hero; indigo leaks | Best customer UI shell  | **Large**           |
| **Vergeo_v1_Standalone**        | Gold skin of Offline         | Seasonal theme proof                            | Superseded polish                                   | Theme preset only       | **Medium** (preset) |
| **Convergeo_Platform**          | Green ops PWA + vendor/admin | Bottom nav, moderation, B2B, compare seed       | Placeholder product tiles; ZMW; generic SaaS        | Ops IA gold             | **Medium** patterns |
| **Vergeo_Prototype_Standalone** | Dark-luxe services           | Trust ladder, booking stepper                   | Services-only; dark-default                         | Trust/KYC flows         | **Medium**          |
| **Vergeo_Prototype_offline**    | Cream mobile + AI            | Best 360px nav, MoMo cards, pastel cats         | Services-only; payment skips pending                | Mobile shell + payments | **Small–Medium**    |
| **Convergeo_Wireframes**        | Lo-fi flow spec              | Escrow, multi-vendor PDP, QR, RFQ, KYC          | Not a visual system                                 | Spec backbone           | **Small** as spec   |

### 9.2 Concept scorecards (overall commercial readiness)

| Concept          | Brand | Polish | Type | Colour | Layout | Nav | Mobile | Discovery | Card | PDP | Trust | A11y | Motion | Perf |  DS | **Ready** |
| ---------------- | ----: | -----: | ---: | -----: | -----: | --: | -----: | --------: | ---: | --: | ----: | ---: | -----: | ---: | --: | --------: |
| Offline Bundle   |     8 |      8 |    8 |      7 |      8 |   6 |      5 |         8 |    9 |   7 |     5 |    4 |      8 |    5 |   8 |     **6** |
| v1 Standalone    |     7 |      6 |    8 |      7 |      7 |   5 |      4 |         7 |    9 |   7 |     4 |    4 |      5 |    5 |   7 |     **5** |
| Platform         |     5 |      6 |    6 |      6 |      7 |   8 |      7 |         5 |    3 |   4 |     8 |    4 |      4 |    7 |   5 |     **6** |
| Proto Standalone |     6 |      8 |    7 |      7 |      7 |   6 |      7 |         3 |    2 |   5 |     9 |    4 |      8 |    7 |   5 |     **5** |
| Proto offline    |     7 |      7 |    8 |      7 |      6 |   9 |      9 |         4 |    3 |   5 |     7 |    4 |      7 |    8 |   4 |     **5** |
| Wireframes       |     3 |      2 |    2 |      3 |      5 |   7 |      7 |         7 |    6 |   8 |     9 |    2 |      1 |    5 |   1 |    **3*** |

\*Wireframes: **3 visual / 9 as flow spec**.

### 9.3 Hybrid direction (adopt)

1. Offline Bundle → product/event cards, logistics pills, mega-menu, flash countdown, K formatting.
2. Prototype offline → bottom nav + AI tab, MoMo cards, focused hero variant, pastel categories.
3. Platform → Orders in tab set, vendor/admin IA, moderation vocabulary.
4. Prototype Standalone → verification ladder (separate from paid tiers).
5. Wireframes → escrow timeline, multi-vendor PDP, QR tickets, RFQ, checkout steps.
6. v1 → Harvest Gold seasonal preset only.

### 9.4 Reject in production

- Aubergine `#241B30` dark (SELECTION invention).
- Indigo `#6366f1` service/tier chrome.
- Floating hero collage + stats as default first viewport.
- Checkout “Coming soon”.
- Payment success without STK pending.
- Placeholder letter product images.
- Emoji-as-sole iconography.
- ZMW on customer (use `formatK` / K).
- Conflating Platinum tier with ID verification.

### 9.5 Strongest overall concept

**Offline Bundle** for visual/component vocabulary; **Prototype offline + Platform** for mobile IA; **Wireframes** for missing commerce flows. No single HTML file is production-complete.

### 9.6 SELECTION.md revision note

Keep cream / navy / gold / DM fonts / pastel cats. **Revise §5 panel + dark block** to charcoal. Document as follow-up doc change in the same PR series as token work.

---

## 10. Prioritised remediation roadmap

### P0 — Foundational credibility

| Item                          | User impact               | Evidence | Pages               | Files                                                              | Deps            | Complexity | Risk                  | Acceptance                                                             | Tests                                        |
| ----------------------------- | ------------------------- | -------- | ------------------- | ------------------------------------------------------------------ | --------------- | ---------- | --------------------- | ---------------------------------------------------------------------- | -------------------------------------------- |
| Neutral charcoal dark + panel | Removes purple distrust   | E01, E21 | all                 | `tokens.ts`, `base.css`, `theme.css`, `footer.tsx`, contrast tests | SELECTION amend | Medium     | Low–med (visual snap) | Dark bg chroma ≈ neutral; AA pairs pass; footer not purple in light    | `tokens.test.ts` contrast + visual snapshots |
| Wire fonts                    | Brand identity appears    | E03      | all apps            | locale layouts, `fonts.ts`                                         | none            | Small      | Font bytes on 3G      | DM Sans/Serif active in computed styles                                | layout unit + optional LH font check         |
| SVG icon set for shop chrome  | Stops emoji scaffold look | E04      | shop                | new icons, layout, TopNav/BottomNav                                | none            | Medium     | Low                   | No emoji in primary nav                                                | component tests + a11y names                 |
| Relocate theme toggle         | Cleaner conversion chrome | E12, E13 | shop, account prefs | layout, desktop-header, preferences-form                           | prefs i18n      | Small      | Low                   | Toggle absent from primary nav; present in Preferences; default system | prefs + theme-provider tests                 |
| Hide SAMPLE in production     | Trust                     | E07      | home/PLP            | merch/listing flags                                                | env flag        | Small      | Low                   | No SAMPLE on prod host                                                 | unit on badge gate                           |
| Search/cart API health        | Can find & buy            | E08, E09 | search, PDP         | API/ops (out of pure UI)                                           | infra           | —          | High if ignored       | Search returns results; ATC succeeds in staging                        | API + e2e smoke                              |

### P1 — Core marketplace experience

| Item                                           | User impact          | Evidence | Complexity | Acceptance                                                                          |
| ---------------------------------------------- | -------------------- | -------- | ---------- | ----------------------------------------------------------------------------------- |
| Bottom nav IA → Home/Browse/Ask/Orders/Account | Wayfinding           | E11      | Small      | Orders reachable in one tap; Categories via Browse                                  |
| Merge DesktopHeader into TopNav slots          | Consistency          | E12      | Medium     | One header system                                                                   |
| Hero redesign (merch-first)                    | Desire + clarity     | E05      | Medium     | First viewport: brand, 1 headline, 1 line, CTAs, image plane; escrow in trust strip |
| ProductCard refactor + wire wishlist/quick-add | Engagement           | E07, E14 | Medium     | Heart toggles; quick-add on desktop hover / mobile explicit                         |
| Sticky mobile ATC on PDP                       | Conversion           | E10      | Small      | Bar visible while scrolling buy info                                                |
| Mobile seller compare as cards                 | Multi-vendor clarity | E10      | Medium     | Usable at 360px                                                                     |
| Mega-menu focus trap                           | A11y/quality         | E16      | Small      | Tab cycles panel; Escape closes                                                     |
| Auth brand shell                               | First-run trust      | E18      | Small      | Brand-dominant login                                                                |
| Directory in desktop primary                   | Seller discovery     | E11      | Small      | Link present                                                                        |

### P2 — Design-system consolidation

LinkButton; PanelHero; Badge CSS vars; Cloudinary RSC split; Button RSC-safe; radius/pill policy; `--on-danger`; raise muted contrast; nested `<main>` cleanup; hub page token sweep.

### P3 — Motion and polish

Fix reduced-motion card-lift; remove invalid keyframes block; apply motion matrix sparingly; toast polish; skeleton→content fade; category hover compact.

### P4 — Advanced engagement

Wishlist page; recently viewed rail; personalized recommendations; logistics pills when listing tags reliable; mega-menu featured minis CMS; language switcher UX; back-to-top.

---

## 11. Suggested implementation sequence (PR series)

Avoid one mega-redesign PR. Proposed sequence:

### PR1 — `Mxx-Pxx: Neutral dark tokens + footer CSS vars`

- **Scope:** Replace aubergine panel/dark remap; footer uses CSS variables; extend contrast tests; amend `docs/designs/SELECTION.md` §5 dark note + link to this audit.
- **Files:** `packages/ui/src/tokens.ts`, `styles/base.css`, `footer.tsx`, `tokens.test.ts`, `docs/designs/SELECTION.md`, `docs/designs/TOKENS.md`
- **Deps:** none
- **AC:** Dark mode screenshots show charcoal; light footer non-purple; AA tests include new pairs
- **Visual regression:** home/PDP light+dark 360 & 1366
- **Tests:** token contrast unit tests
- **A11y:** contrast
- **Perf:** none

### PR2 — `Mxx-Pxx: Wire fonts + SVG shop icons + relocate theme toggle`

- **Scope:** `fontVariables` on layouts; icon components; remove emoji from shop layout; theme control → preferences (keep ThemeProvider).
- **Files:** app layouts, `(shop)/layout.tsx`, `desktop-header.tsx`, preferences form, new `packages/ui/src/icons/*`
- **Deps:** PR1 preferred (icons on correct contrast)
- **AC:** Computed font-family DM Sans; no emoji in bottom/top nav; theme toggle not in primary chrome
- **Visual regression:** nav mobile/desktop
- **Tests:** icon a11y labels; theme prefs
- **A11y:** 44px targets retained
- **Perf:** font subset latin; document Save-Data future

### PR3 — `Mxx-Pxx: Navigation IA + LinkButton + hero merchandising`

- **Scope:** Bottom nav SELECTION set; Directory desktop link; `LinkButton`; new hero composition; trust strip absorbs escrow pills.
- **Files:** shop layout, desktop-header, home-default, home-trust-strip, ui Button/LinkButton, i18n keys
- **Deps:** PR2 icons
- **AC:** Orders in bottom nav; hero matches §4.1; no escrow pill row inside hero
- **Visual regression:** home 360/1366
- **Tests:** nav href tests; i18n keys present
- **A11y:** heading order h1 once
- **Perf:** no new client islands

### Later PRs (4+)

4. ProductCard + ListingGrid wishlist/quick-add
5. PDP mobile sticky ATC + compare cards
6. Mega-menu focus trap + a11y contrast leftovers
7. Cloudinary RSC image split
8. Wishlist route + recently viewed
9. Motion matrix cleanup

---

## 12. Final recommendation

### What Vergeo5 should look and feel like

A **warm, light, search-first Zambian marketplace**: cream ground, white product stages, navy actions, gold for value/sale, pastel category tiles, calm density, escrow trust without shouting. On mobile it should feel like a reliable commerce utility (thumb reach, Orders one tap); on desktop like a confident multi-vendor catalogue with comparison superpowers.

### What should remain distinctive

- Escrow clarity (“Held by Vergeo5”).
- Multi-vendor comparison on canonical products.
- Category pastel language.
- Ask Vergeo as a nav peer.
- Kwacha via `formatK`, phone-first auth, logistics reality (Lusaka delivery / nationwide pickup).

### Change immediately

1. Charcoal dark + stop purple panels.
2. Wire fonts.
3. Kill emoji chrome; relocate theme toggle.
4. Fix search/cart reliability (ops) so design work is not judged on broken APIs.

### Deliberately do **not** copy from Amazon / eBay / Alibaba

- Amazon’s dense grey utilitarian chrome and endless above-fold clutter.
- eBay’s dated auction-era visual noise.
- Alibaba’s industrial supplier aesthetic / overwhelming B2B tables on consumer home.
- **Do** copy their _principles_: search primacy, refine-after-query, seller confidence, category scale.

### Dark mode

**Keep** with `system` default; **neutral charcoal**; control in **Preferences**, not primary navbar.

### Attached design direction to adopt

**Hybrid:** Offline Bundle (cards/system) + Prototype offline (mobile IA) + Wireframes (commerce flows) + Platform (Orders tab / ops) + Prototype Standalone (trust ladder). **Reject SELECTION aubergine dark.**

### First three implementation PRs

1. Neutral dark tokens + footer CSS vars (+ SELECTION dark revision).
2. Wire fonts + SVG icons + relocate theme toggle.
3. Navigation IA + LinkButton + merch-first hero.

---

## Appendix A — Homepage structure (detail)

### Mobile

| Pos | Section          | Purpose         | User question      | Layout           | Personalised | Visible | Objective     | Now/Later |
| --: | ---------------- | --------------- | ------------------ | ---------------- | ------------ | ------- | ------------- | --------- |
|   1 | Chrome search    | Start finding   | Where do I search? | Sticky           | No           | Initial | Query         | Now       |
|   2 | Hero             | Brand + promise | What is Vergeo5?   | Full-bleed/band  | No           | Initial | Browse CTA    | Now       |
|   3 | Trust chips      | Safety          | Is my money safe?  | 2×2              | No           | Initial | Confidence    | Now       |
|   4 | Categories       | Department      | What aisle?        | Grid             | No           | Initial | PLP           | Now       |
|   5 | Flash/campaign   | Urgency         | Any deal?          | Banner           | Admin        | If live | Campaign      | Now       |
|   6 | New rail         | Browse fuel     | What’s new?        | H-scroll / 2-col | No           | Initial | PDP           | Now       |
|   7 | Department rails | Depth           | More like this?    | Rails            | Category     | Lazy    | PLP           | Now       |
|   8 | Events           | Tickets         | What’s on?         | Cards            | No           | Lazy    | Ticket        | Now       |
|   9 | Services + RFQ   | Jobs            | Who can help?      | Rail             | No           | Lazy    | RFQ           | Now       |
|  10 | Vendors          | Trust browse    | Who sells well?    | Cards            | No           | Lazy    | Storefront    | Now       |
|  11 | Sell CTA         | Supply          | Can I sell?        | Panel            | No           | Lazy    | Vendor signup | Now       |
|  12 | Recently viewed  | Continue        | Where was I?       | Rail             | Yes          | Lazy    | PDP           | Later     |

### Desktop

Same order; denser grids; mega-menu featured products; hero may use editorial collage **only** as an admin hero variant, not default.

---

## Appendix B — PDP layout (detail)

### Mobile

1. Title + brand + “N sellers” link
2. Gallery
3. Price, discount, stock
4. **Sticky purchase bar** (qty + ATC)
5. Trust (seller status, delivery/pickup, escrow, returns)
6. Seller offers as **cards**
7. Vendor profile teaser
8. Tabs: Overview · Specs · Reviews
9. Related
10. Later: wishlist, Q&A, recently viewed

### Desktop

Current two-column skeleton is correct: gallery | sticky buy box → compare table → vendor → tabs → related.

---

## Appendix C — Live vs repository drift

| Topic           | Live (2026-07-20)         | Repository                   | Interpretation                     |
| --------------- | ------------------------- | ---------------------------- | ---------------------------------- |
| Dark purple     | Confirmed                 | Token aubergine              | **Aligned defect** (not drift)     |
| Fonts           | Serif/system mix          | Tokens declare DM*; unwired  | **Aligned defect**                 |
| Search failure  | Confirmed                 | Search UI + API client exist | Likely **API/env drift** or outage |
| ATC failure     | Confirmed                 | Buy-box + cart client exist  | Likely **API/env drift**           |
| SAMPLE listings | Visible                   | Badge supported for demo     | **Content/config** on prod         |
| Theme in navbar | Visible                   | Explicit in shop layout      | **Aligned** (relocate by design)   |
| No hamburger    | Confirmed in code/screens | Bottom nav model             | Live note F08 is **misread**       |

---

## Appendix D — Zambia / mobile-first checklist

| Concern              | Recommendation                                                                                                                                  |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Mobile-heavy traffic | Bottom nav + sticky search; thumb CTAs `min-h-11`                                                                                               |
| Low-end devices      | CSS motion only; cap home stagger; progressive PLP                                                                                              |
| Data cost            | Cloudinary `f_auto/q_auto`; font subset; Save-Data load-more                                                                                    |
| One-handed           | Orders in bottom nav; sticky ATC                                                                                                                |
| Long place names     | Truncate with title tooltip; 2-line max on cards                                                                                                |
| Phone formats        | Keep +260 hints on auth/pay                                                                                                                     |
| Currency             | Keep integer ngwee + `formatK` (K1,234.56 is correct per platform rules; do not “round away” ngwee in display layer without a product decision) |
| Languages            | Locale routes exist; add switcher in preferences/footer                                                                                         |
| First-time users     | Hero clarity + trust chips; avoid SAMPLE                                                                                                        |
| Trust                | Escrow + verification ladder on vendor surfaces                                                                                                 |

---

## Appendix E — Screenshot index

| File                                           | Route                  | Viewport | Notes                    |
| ---------------------------------------------- | ---------------------- | -------- | ------------------------ |
| `evidence/live-home-360-top.png`               | `/en`                  | ~360–380 | Mobile hero + bottom nav |
| `evidence/live-home-360-mid.png`               | `/en`                  | ~360     | Mid-page                 |
| `evidence/live-home-390.png`                   | `/en`                  | ~390     | Standard mobile          |
| `evidence/live-home-768.png`                   | `/en`                  | ~768     | Tablet                   |
| `evidence/live-home-1366.png`                  | `/en`                  | 1366     | Desktop light            |
| `evidence/live-home-1440.png`                  | `/en`                  | 1440     | Large desktop            |
| `evidence/live-dark-mode-purple-tint-1366.png` | `/en`                  | 1366     | Purple dark confirmed    |
| `evidence/live-products-dark-mode-1366.png`    | `/en`                  | 1366     | Product rails dark       |
| `evidence/live-footer-dark-mode-1366.png`      | `/en`                  | 1366     | Footer dark              |
| `evidence/live-search-unavailable-1366.png`    | `/en/search?q=phone`   | 1366     | Search failure           |
| `evidence/live-category-electronics-1366.png`  | `/en/c/electronics`    | 1366     | PLP                      |
| `evidence/live-product-detail-1366.png`        | `/en/p/tecno-spark-20` | 1366     | PDP                      |
| `evidence/live-add-to-cart-error-1366.png`     | PDP                    | 1366     | ATC error                |
| `evidence/live-cart-empty-1366.png`            | `/en/cart`             | 1366     | Empty cart               |
| `evidence/live-auth-signin-1366.png`           | `/en/login`            | 1366     | Auth                     |
| `evidence/live-audit-findings.md`              | —                      | —        | Raw live notes           |

---

_End of audit. Implement via the PR sequence in §11; do not open a single redesign mega-PR._
