# Customer-integration evidence — manifest

Closes the base-correction follow-up for `claude/brave-ritchie-uxmyz2`
(originally integrated onto `master`; re-integrated here onto `staging`).

## Original captures: not recoverable, stated honestly

The original session's capture scripts, fixture backend and screenshots lived
in **that session's own ephemeral scratchpad** — a per-session directory this
session has no access to, and nothing was committed to git (`git status` on
the branch's own commit is clean; no evidence files are part of
`77f9e911`). They could not be transferred because they no longer exist
anywhere reachable. Nothing below claims to be a recovery of them.

Everything in this directory was captured **fresh, in this session, against
the integrated tree** (head `c17b19113220c1e19266e7b105de323910027292`,
tree `eb5ae2d8d989b1fe9db85586cfafd7bf96fe35fa`), using a newly built harness
that follows the same component-mounting methodology used earlier in this
session for unrelated evidence work (see `apps/vendor/.../_evidence/` on
other branches) — not a reconstruction of the original session's specific
script.

## What was actually exercised

Real Chromium (`/opt/pw-browsers/chromium`, via Playwright), at 360×800,
390×844 and 1440×900, mounting the **real** `StickyMobileAtc` and
`MobileHeaderSearch` components through the **real** compiled Tailwind entry
and design tokens (`apps/customer/app/[locale]/(shop)/_evidence/harness.css`,
same `@import "tailwindcss"` + `@import "@vergeo/ui/styles/theme.css"` the app
itself compiles). Search harness labels come from the real `en/nav.json` and
`en/search.json` catalogues via a real `NextIntlClientProvider`, sourced from
the same keys `layout.tsx` actually passes to `MobileHeaderSearch`.

**Boundary, stated so this isn't over-read:** the harness mounts these two
components directly. It does **not** traverse Next.js App Router, the FastAPI
backend, or Cloudinary — `next/navigation`'s `useRouter` is stubbed (a
no-op `push`), since `SearchInput`'s only navigation dependency is
`router.push()` on submit/select, which is out of scope for the open/Escape/
close/reopen focus behaviour this harness proves. This is **local-fixture,
component-level evidence of layout and focus behaviour** — not routing,
data-fetching, or authorization, which the 139-file / 712-test passing
Customer suite already covers. No staging, no deployment, no network call,
no cart/order mutation — nothing shared is touched by running this.

## Files

| File                                                         | What it shows                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sticky-atc-360.png`, `sticky-atc-390.png`                   | **AFTER** (integrated fix): price/stock fully visible, controls on their own row below                                                                                                                                                                                        |
| `sticky-atc-1440.png`                                        | Confirms `lg:hidden` — the bar is correctly absent (not a regression) at desktop width                                                                                                                                                                                        |
| `BEFORE-sticky-atc-360.png`, `BEFORE-sticky-atc-390.png`     | **BEFORE** (`origin/master`'s unpatched component, temporarily swapped in, then restored and verified byte-identical to the integrated version before this evidence was captured) — price overflowing/painting over the decrement control, stock line truncated to "In stoc…" |
| `search-open-360.png`, `search-open-390.png`                 | Sheet opens with real keyboard focus (Tab → Enter) landing on the search input                                                                                                                                                                                                |
| `search-after-escape-360.png`, `search-after-escape-390.png` | Focus after Escape — visibly back on the trigger button, not `<body>`                                                                                                                                                                                                         |
| `evidence.json`                                              | Full machine-readable results: AAA layout measurements (no overflow, no truncation) at 360/390, `lg:hidden` confirmation at 1440, and focus state at every step (open, Escape, reopen, second Escape) at 360/390                                                              |
| `before-regression.json`                                     | The BEFORE run's layout measurements: price box starved to 61–91px, stock text (175px of content) truncated at both widths                                                                                                                                                    |

## Numbers, not just screenshots

|                       | BEFORE (master)                                              | AFTER (integrated)                       |
| --------------------- | ------------------------------------------------------------ | ---------------------------------------- |
| 360px price box width | 61px (overflows: `scrollWidth > clientWidth`)                | 328px, no overflow                       |
| 360px stock line      | truncated (175px content in 61px)                            | fully visible, no truncation             |
| 390px price box width | 91px                                                         | 358px, no overflow                       |
| 390px stock line      | truncated                                                    | fully visible                            |
| 1440px sticky bar     | _(not captured for BEFORE — same `lg:hidden` class in both)_ | present in DOM, `display:none` (correct) |

## Search focus — the exact regression this fix targets

At both 360 and 390: focus starts on the trigger (real Tab) → opens the sheet
→ real focus moves to the search input → **Escape returns focus to the
trigger button** (`data-testid="mobile-header-search-trigger"`, confirmed via
`document.activeElement`, not inferred from screenshots alone) → **reopens**
(Enter) → **Escape a second time still returns to the trigger** — proving the
fix holds across repeated cycles, not just once.

## Reproduce

```
node scripts/qa/evidence/customer-integration/run.mjs <repo-root> <out-dir>
```

Not committed — `scripts/qa/evidence/.gitignore` is `*` (repo-wide
convention predating this work), so the runner lives only on the machine that
ran it. The harness component it drives (`_evidence/harness-entry.tsx` /
`harness.css`) **is** committed, matching that same established convention:
the reusable, real-component harness ships; the disposable capture script
does not.

## Labeled honestly, per instruction

- **next-dev**: not used. Nothing here goes through `next dev` or Next's
  router/data-fetching — see Boundary above.
- **Local fixtures**: the `listing`/`purchase`/`labels` props are hand-built
  fixtures matching the exact shape of the existing, type-checked fixtures in
  `sticky-mobile-atc.test.tsx` (same price-class defect: a long title, a MOQ
  note, a price chosen to be representative of the original K249.00/76px
  report — not a byte-identical reproduction of the original session's exact
  numbers, which aren't recoverable either).
- **Cloudinary**: not invoked. Neither harnessed component renders a
  Cloudinary image, so there is no broken-image state to label — this is
  a non-issue for this specific evidence, not a stubbed-over one.

## Found while integrating, not fixed — separate owned follow-ups

1. **"1 items" plural bug — confirmed, NOT the same defect this fix
   addressed, and NOT fixed here.** `packages/i18n/messages/en/nav.json`
   `shop.cartWithCount` = `"Cart, {count} items"` — a plain template
   (`{count}`), not an ICU plural, substituted via
   `labels.cartWithCount.replace("{count}", ...)` in **two** places:
   `apps/customer/app/[locale]/(shop)/_components/shop-header.tsx:105` and
   `apps/customer/app/[locale]/account/_components/account-header-client.tsx:71`.
   At count=1 this reads "Cart, 1 items". Exactly the class of bug the
   branch fixed for `checkout.cart.itemCount` (raw ICU plural via
   `useTranslations`) — but in the `nav` namespace, in two files neither this
   branch nor the original 18-file fix touched. Left alone; flagging for a
   dedicated fix.
2. **Breadcrumb ellipsis — hardcoded string, pre-existing, minor.**
   `apps/customer/app/[locale]/(shop)/c/[...slug]/page.tsx:316` passes
   `ellipsisLabel="…"` as a literal, not through an i18n key, to the shared
   `Breadcrumbs` component. Not flagged by `pnpm lint` or the repo's
   `i18n-lint.mjs` sweep (both ran clean on the integrated tree), likely
   because it's a single non-linguistic punctuation glyph — but it's still a
   literal outside the catalogue. Confirmed by direct source read; left
   alone as out of scope for this fix.

Both are genuinely present on the integrated tree today; neither was
introduced by this integration, and neither is part of the sticky-ATC/
search-focus/i18n-template-label fix this branch delivers.
