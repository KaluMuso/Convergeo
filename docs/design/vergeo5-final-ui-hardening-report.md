# Vergeo5 Customer — Final UI Hardening Report (Phase 4.5)

**Date:** 2026-07-20  
**Branch:** `cursor/customer-ui-hardening-077d`  
**Base:** `master` @ `d9839db349887ab48a52c18546e05961a62498d6`  
**Scope:** `apps/customer` + `packages/ui` (+ i18n cart-count strings)  
**Approved audit:** [`vergeo5-ui-ux-audit.md`](./vergeo5-ui-ux-audit.md)  
**Evidence:** [`evidence/hardening/`](./evidence/hardening/)  
**PR:** https://github.com/KaluMuso/Convergeo/pull/383

This phase hardens accessibility, Core Web Vitals risks, server/client boundaries, and cross-page consistency. It is **not** a redesign.

---

## 1. Executive go/no-go verdict

### Verdict: **GO** for merge of this hardening PR (with documented residuals)

No known **P0** accessibility blockers remain in the hardened surface. Primary shop, marketing, and auth chrome now expose a single `<main>` landmark, keyboard skip links, visible focus affordances, AA dark muted text, ≥44px shared control sizes for the controls we touched, and cart/wishlist status announcements.

Commerce payment/settlement logic was **not** modified.

### Caveats (do not hide)

1. **Phase 4.3 / 4.4** (cart/checkout presentation polish; account hub / wishlist / recently viewed routes) live on separate PRs and are **not** fully present on this base SHA. Hardening targets the merged master baseline plus shared-system fixes that those branches will inherit.
2. Local preview cannot exercise live catalog/search/API (upstream unavailable) — same class as audit E08/E09. Loading skeletons and honesty empty/error paths remain.
3. Headless Chrome sometimes renders SVG icons oversized (`1.15em` without a stable parent font) — treat as capture artefact unless reproduced in real browsers; deferred as P2 icon-size hardening.
4. PDP First Load JS is **139 kB** (shared 104 + route). Still under the 150 kB gz customer budget for the route payload shape Next reports; keep watching PDP client islands.

---

## 2. Prioritised findings (pre-edit audit)

| ID  | Severity              | Finding                                                                            | Resolution                                                      |
| --- | --------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| H01 | P1                    | Nested `<main>` under shop layout (PDP, search, loadings, post-job, card checkout) | Converted nested mains → `div`; shop keeps `#shop-main`         |
| H02 | P1                    | Dark `--text-3` `#8A837A` on surface ~4.34:1 (fails AA)                            | Raised to `#918A80` (~4.76:1); contrast pairs + CSS             |
| H03 | P1                    | Wishlist toggle had `aria-pressed` only — no status announcement                   | Polite live region via `wishlistStatusAnnouncement`             |
| H04 | P1                    | Cart badge count missing from accessible name / live region                        | `cartWithCount` i18n + TopNav/DesktopHeader live region         |
| H05 | P1                    | Touch targets &lt;44px (`Button` sm, search submit, feedback close, stepper)       | Shared component min-height → 44px                              |
| H06 | P1                    | Skip link only on shop chrome                                                      | Account, auth, marketing skip links + landmark ids              |
| H07 | P1                    | Cloudinary images lacked intrinsic height attrs (CLS risk)                         | `width` + derived `height` from `ratio`                         |
| H08 | P0 (audit historical) | Aubergine dark / missing fonts / emoji nav                                         | Already fixed on master before this PR — verified charcoal dark |
| H09 | P2                    | Mega-menu outside-click focus restore                                              | Deferred                                                        |
| H10 | P2                    | axe CI gate / further RSC splits                                                   | Deferred                                                        |
| H11 | P2                    | Headless oversized SVG icons                                                       | Deferred (verify in real browsers)                              |

---

## 3. Accessibility findings and fixes

### Fixed

- **Landmarks:** one `<main>` on shop (`#shop-main`), marketing (`#marketing-main`), auth (`#auth-main`), account (`#account-main`).
- **Skip links:** shop (existing), marketing layout, auth layout, account layout. Manual CDP: first Tab focuses “Skip to content” → `#shop-main`.
- **Contrast:** dark muted text AA; pairs `dark-text-3-on-surface` / `dark-text-3-on-bg` enforced in `tokens.test.ts`. Runtime computed `--text-3` in dark = `#918a80`.
- **Cart announcements:** accessible name includes count; polite `aria-live` region updates.
- **Wishlist announcements:** ListingCard / search product cards announce label changes after toggle (skip first mount).
- **Touch targets:** shared `Button`/`LinkButton` `sm`, desktop + search submit, feedback close, stepper circles ≥44px.
- **Reduced motion:** prior card-lift displacement fix retained (`base.css`); no new motion dependencies.

### Verified structurally (local prod @ `:3010`)

| Route            | `<main>` count | Landmark id      | Skip link |
| ---------------- | -------------: | ---------------- | --------- |
| `/en`            |              1 | `shop-main`      | yes       |
| `/en/search`     |              1 | `shop-main`      | yes       |
| `/en/p/itel-a70` |              1 | `shop-main`      | yes       |
| `/en/cart`       |              1 | `shop-main`      | yes       |
| `/en/about`      |              1 | `marketing-main` | yes       |
| `/en/login`      |              1 | `auth-main`      | yes       |

### Remaining a11y residuals (P2)

- Mega-menu focus restore on outside click.
- Automated axe in CI.
- Account shell still lacks shop bottom nav (audit E19 — product IA choice; not reopened here).
- Some form `sm` inputs remain `h-9` (`field-styles`) — text fields are exempt from the 44px target-size SC in many interpretations; leave unless product wants larger fields.

---

## 4. Performance findings and fixes

### Fixed / improved

- **CLS:** CloudinaryImage sets intrinsic `width`/`height` when `ratio` is known; containers already use CSS `aspect-ratio`.
- **LCP:** no hero imagery demotion; priority paths on listing media unchanged.
- **Client boundaries:** ProductCard remains RSC-safe; announcement strings owned by client parents (ListingCard / search). No new large client frameworks.

### Build evidence (customer production build)

Shared First Load JS: **104 kB**

| Route              | Size    | First Load JS |
| ------------------ | ------- | ------------- |
| Home `/[locale]`   | 3.18 kB | 127 kB        |
| PLP `/c/[...slug]` | 9.22 kB | 133 kB        |
| Search             | 9.17 kB | 133 kB        |
| Cart               | 4.25 kB | 130 kB        |
| Checkout           | 11.2 kB | 131 kB        |
| PDP `/p/[slug]`    | 3.03 kB | **139 kB**    |

Build completed successfully after clean `.next` rebuild (`NEXT_TELEMETRY_DISABLED=1 pnpm build` in `apps/customer`).

### Residuals

- PDP still heaviest commerce First Load — further island splits deferred (P2).
- Categories upstream fails locally (`customer.categories.load_failed`) — ops/API, not UI regression.
- No third-party script removals in this pass (Sentry retained).

---

## 5. Server / client boundary findings

| Item                               | Status                                                             |
| ---------------------------------- | ------------------------------------------------------------------ |
| ProductCard without `"use client"` | Preserved; announcement prop is a string                           |
| Cart count in Server layout        | Still resolved via client `MobileTopNav` / `DesktopHeader` + store |
| Theme FOUC script                  | Unchanged; charcoal dark verified                                  |
| Non-serialisable props             | None introduced                                                    |
| Unnecessary new client roots       | None                                                               |

No aggressive “use client” deletions were made where cart/wishlist localStorage requires a client boundary.

---

## 6. Cross-page consistency findings

### Aligned

- Single shop landmark + padding ownership (nested pages dropped duplicate `px-4` where layout already gutters).
- Skip-link visual treatment shared (primary pill, `min-h-11`).
- Dark palette remains warm charcoal (no purple surfaces).
- Product cards / prices / badges unchanged in structure — systemic a11y/perf only.

### Intentionally preserved differences

- Marketing vs shop chrome.
- Auth branded card shell.
- Account authenticated shell without bottom nav (existing product decision).

---

## 7. Before-and-after screenshots

| Evidence                                                                                                 | Description                                                                                      |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [`evidence/hardening/home-light-360.png`](./evidence/hardening/home-light-360.png)                       | After — mobile home light                                                                        |
| [`evidence/hardening/home-light-1366.png`](./evidence/hardening/home-light-1366.png)                     | After — desktop home light                                                                       |
| [`evidence/hardening/home-dark-1366.png`](./evidence/hardening/home-dark-1366.png)                       | After — desktop home dark (charcoal, not aubergine)                                              |
| [`evidence/hardening/home-skip-focus-dark-1366.png`](./evidence/hardening/home-skip-focus-dark-1366.png) | After — skip link focused via keyboard                                                           |
| Audit before (purple dark)                                                                               | [`evidence/live-dark-mode-purple-tint-1366.png`](./evidence/live-dark-mode-purple-tint-1366.png) |

Artifacts also copied under `/opt/cursor/artifacts/hardening/`.

---

## 8. Test and build evidence

| Check                                                | Result                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------- |
| `pnpm --filter @vergeo/ui test`                      | Pass (181 tests)                                              |
| `pnpm --filter customer test`                        | Pass (368 tests)                                              |
| `pnpm --filter @vergeo/i18n test` + Phase-1 overlays | Pass                                                          |
| `pnpm --filter customer lint`                        | Pass                                                          |
| `pnpm --filter customer typecheck`                   | Pass (after clearing stale `.next/types` from other branches) |
| Customer production build                            | Pass                                                          |
| Contrast unit pairs (incl. dark text-3)              | Pass                                                          |
| Manual landmark HTML parse                           | Pass (table above)                                            |
| Manual keyboard skip (CDP Tab)                       | Pass — focuses Skip to content                                |
| Dark computed `--text-3`                             | `#918a80`                                                     |

New/updated unit coverage:

- TopNav cart count accessible name + live region
- ProductCard wishlist status live region
- Button `sm` min touch target
- Cloudinary intrinsic height from ratio
- DesktopHeader snapshot + cartWithCount label

---

## 9. Remaining risks

1. **API-dependent commerce paths** still fail closed when upstream is down — UI honesty present; conversion blocked by ops.
2. **Phase 4.3/4.4 merge order** — rebase/merge those PRs after this one (or vice versa) and re-check nested landmarks on any new pages they add (`/wishlist`, `/account/recent`, etc.).
3. **PDP bundle** near budget — avoid adding client weight without measurement.
4. **Headless icon sizing** may mask real SVG sizing bugs — spot-check in Safari/Chrome device once.

---

## 10. Deferred recommendations

1. Wire axe (or `@axe-core/playwright`) into CI for shop + checkout smoke.
2. Mega-menu focus trap/restore audit.
3. Optional RSC split of PDP comparison client islands.
4. Normalise SVG icon explicit `size` props (fix headless/em quirks).
5. Land Phase 4.3/4.4, then re-run this checklist on wishlist / account hub / checkout sticky summary.
6. Consider `prefers-reduced-data` still more aggressively on home merch rails.

---

## 11. Final customer-application scorecard

Scores vs audit §3 baseline (commercial readiness then **5.0 / 10**). Hardening moves system quality; content/API reliability still cap the ceiling.

| Dimension                    | Audit | After 4.5 | Notes                                                  |
| ---------------------------- | ----: | --------: | ------------------------------------------------------ |
| Visual system / tokens       |     5 |   **7.5** | Charcoal dark + AA muted text                          |
| Navigation / IA chrome       |     5 |     **7** | Skip links + cart a11y; IA already improved on master  |
| Accessibility                |   4.5 |   **7.5** | Landmarks, focus, announcements, targets               |
| Performance / CWV hygiene    |   5.5 |   **6.5** | Intrinsic image dims; budgets watched                  |
| Commerce trust / states      |     6 |     **6** | Unchanged domain; honesty states retained              |
| Engagement loops             |     3 |     **3** | Wishlist pages still on 4.4 PR                         |
| Overall commercial readiness |   5.0 |   **6.5** | Hardening complete; content/API + 4.3/4.4 still needed |

---

## 12. Confirmation vs approved audit

| Audit theme                             | Satisfied by this PR?                                               |
| --------------------------------------- | ------------------------------------------------------------------- |
| Remove purple dark / charcoal           | Yes (verified; already on master + contrast raise)                  |
| Brand fonts wired                       | Yes (pre-existing on master; retained)                              |
| SVG icons / theme out of primary chrome | Yes (pre-existing; retained)                                        |
| Wishlist / engagement routes            | Partial — local wishlist a11y improved; dedicated pages = Phase 4.4 |
| Nested landmarks / skip links           | Yes                                                                 |
| AA muted text / danger on-color         | Yes (text-3 dark + prior on-danger)                                 |
| Motion reduce without layout thrash     | Yes (retained)                                                      |
| Performance without gutting hierarchy   | Yes                                                                 |

**Conclusion:** Phase 4.5 acceptance criteria for **known P0 a11y**, keyboard primary chrome, focus visibility, dark contrast, hydration/serialisation hygiene, image space reservation, shared-component consistency, and green lint/typecheck/tests/build are met. Remaining items are explicitly documented above rather than suppressed.
