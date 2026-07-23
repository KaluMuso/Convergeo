# Design Selection — Vergeo5 Phase 1

Source-of-truth analysis of the six committed design HTML files in `docs/designs/`, executed per the founder's selection policy in `SOURCES.md` (pick strongest elements, state why, flag admin-swappable items). Legacy live prototype (Firebase, Material-style, screenshot-audited) treated as weakest reference.

> **How these files are built (matters for salvage):** all six are Claude Design _offline bundles_ — a small HTML shell whose `<script type="__bundler/manifest">` holds gzip+base64 resources (React 18 dev, Babel standalone, app JSX modules) and `<script type="__bundler/template">` holds the real app HTML/CSS. The design source is therefore **readable React JSX + plain CSS**, directly minable for the production `packages/ui`. No build tooling; components attach to `window.*` and are compiled in-browser by Babel.

---

## 1. Per-file inventory

### 1.1 `Vergeo_Offline_Bundle.html` — "Vergeo — Zambia's National Marketplace" (v2) — **★ flagship, 5/5**

Hi-fi customer marketplace web app; the most complete and most refined variant. **Verdict 5/5 — production-grade component vocabulary, real token system, strict superset of v1.**

- **Screens:** Home (editorial hero + floating image cards + stats · category grid with wide card · flash-deal banner with live countdown · tabbed product rows Featured/Top Deals/New Arrivals · Services row · Upcoming Events row · Top Vendors · "Grow Your Business" sell-CTA · promo strip · footer with app-store buttons & MoMo note) · Shop (sidebar filters, price slider, sort, breadcrumb, pagination, results count, no-results state) · Product Detail (thumb gallery, discount/save chips, qty stepper, delivery rows, tabs Description/Specs/Reviews with rating bars, related) · Services + Service Detail (per-category `SERVICE_THEMES` dark gradient heroes, booking sidebar: date+notes → confirm state, portfolio, trust block) · Events + Event Detail (hero, schedule timeline, speakers, ticket card with qty, spots/capacity block, map placeholder) · Vendors + Vendor Detail (tier strip Platinum/Gold/Silver/Bronze with `TIER_META` perks; cover, avatar, quick stats, dynamic tabs Products/Services/Events, branches, contact card) · Cart drawer (mixed line types: product/service/**ticket** with type badges, qty, empty state) · Mega menu (hover subcats + featured minis + promo block) · toasts · scroll-top · search suggestions.
- **Design language:** cream ground `#FAF7F2`/`#F3EDE3`, slate primary `#4c5470`, navy accent `#2d4a7a`, near-black warm dark `#1C1308`, warm-brown text scale `#2a1f0e/#6b5a3e/#9c8a72`, border `#e8dfd0`. Display serif **Cormorant Garamond**, body **DM Sans**. Radius 12/18px, pills 18px. Layered soft shadows keyed to warm black `rgba(28,19,8,…)`. Includes a warm **dark mode** class (`--bg:#18120a`, surface `#231c10`, text `#f0e8d5`). Density: comfortable desktop-first, responsive to 640px (grids 4→3→2, hamburger `mobile-nav` — **no bottom tab bar**).
- **Animations:** `page-in` (route fade+rise, .3s `cubic-bezier(.2,.8,.3,1)`) · `toast-in/out` (same spring-out ease) · `shimmer` image skeleton (1.4s) · `float-a/b` hero badge bobbing (4–5s) · quick-add button hover-reveal (translateY+opacity .25s) · nav shadow on scroll · card lift `transform .25s, box-shadow .25s` · animated `spots-fill` capacity bar · ticking `FlashCountdown`.
- **Notable components:** ProductCard (badge, −% chip, vendor line, ★+count, `K {price.toLocaleString()}` + struck old price, quick-add, wishlist heart, logistics tag pills **Nearest/Cheapest/International/7-Day Wait** using the `color+'18'` bg / `color+'33'` border alpha-tint recipe) · EventCard (badge Free/Selling Fast, category pill, date, location, **capacity bar**, price, ticket CTA) · VendorCard with tier chip · booking sidebar with inline confirm state · runtime theming: tweaks JSON → `document.documentElement.style.setProperty('--primary', …)`.
- **Currency:** K throughout. Copy is Zambia-literate (10 provinces, Lusaka→Livingstone, MTN/Airtel/Zamtel).

### 1.2 `Vergeo_v1_Standalone.html` — "Vergeo — Zambia's National Marketplace" (v1) — **3/5**

Same codebase one generation earlier; shared-components module is **byte-identical** to the flagship's. **Verdict 3/5 — fully superseded by the Offline Bundle; keep only its gold theme.**

- Differences: `--primary: #C8861A` (amber-gold) with gold-tinted shadows, `--radius-lg: 20px`; **missing** Vendors/Vendor-Detail pages, toast system, page transitions, shimmer skeleton (only `float-a/b` keyframes). CSS 40K vs 64K.
- Value: proves the token system supports a full re-skin by swapping ~6 values → the founder's "seasonal theme" ambition is already demonstrated. Gold preset worth keeping as an admin theme (e.g. Independence season).

### 1.3 `Convergeo_Platform_Standalone.html` — "Convergeo — Platform Prototype" — **4/5**

Three-frontend architecture demo: **Customer PWA (phone frame) · Vendor Dashboard · Admin Console** behind a mode switcher. **Verdict 4/5 — the only variant with real vendor/admin operational surfaces and a PWA bottom nav; visual language is competent SaaS but off-deck; uses ZMW not K.**

- **Screens:** Customer PWA — header with location "Lusaka, Zambia", search, **bottom nav Home/Search/Orders/Profile** (dot indicator), Browse categories, Trending Now, product sheet, cart toast, **B2B/wholesale mode toggle** with banner. Vendor — sidebar nav _Dashboard / Orders / Catalogue / Inventory / B2B Inbox / Payouts & Finance / Insights / Marketing / Storefront_; KPI cards with progress fills ("Today's Revenue ZMW 12,450 +18%"), orders table, catalogue with SKU/stock/low-stock flags, sales bars. Admin — _Platform Overview / Vendor Management / Product Moderation / Financial / Trust & Safety_; KPI grid (GMV, commission, dispute rate), **moderation queue with flag reasons** ("Price anomaly: ZMW 420 vs market ZMW 980", "Duplicate canonical record", "Missing regulatory approval"), **trust flags with severity** high/medium/low + actions (Review/Flag/Investigate), GMV bar chart, vendor archetype selector (Market Trader → Event Organiser).
- **Design language:** forest green `#1f4d30`/`#2d6b43`, cream `#faf7f2`/`#f2ede4`, green-cast ink scale `#0e1a12→#94ada3`, modern `oklch()` amber & teal accents, red `#e54a2a`. Font **Plus Jakarta Sans**. Radius 10/16/24. Two shadow levels. Bootstrap-ish status chips (`#d4edda/#155724` etc.). Dark-sidebar tweak toggle.
- **Animations:** minimal — .15/.2s transitions, `transform .3s cubic-bezier(.4,0,.2,1)`, bar `height .5s`. No keyframes.

### 1.4 `Vergeo_Prototype_Standalone.html` — "Vergeo — Platform Prototype" (dark) — **4/5**

Dark-luxe mobile prototype in an iOS-26 device frame + Chrome frame for vendor desktop. **Verdict 4/5 — best flow design (booking stepper, vendor onboarding wizard, trust ladder) and the strongest "premium dark panel" language; scope is services-only, ZMW, demo-framed.**

- **Screens:** Customer — Home (Playfair wordmark, category pills, vendor cards with price ranges), Search, Storefront (tabs Services/About/Reviews, service rows duration+price), **Booking stepper: Date & Time → Staff → Payment** (time chips, staff cards with ratings, methods MTN MoMo/Airtel/Zamtel/Card), Confirmation (**spring pop ✓** `cubic-bezier(0.34,1.56,0.64,1)`). Vendor — Dashboard (Overview/Catalogue/Bookings/Insights, Playfair stat numerals, quick actions _Add Service / Block Time Off / Run Promotion_), **Onboarding wizard**: Business Type (6 archetypes: Bookable Service / Physical Products / Stays & Rentals / Food & Dining / Quote-Based Jobs / Events & Tickets) → Details → Location (Town/Suburb/Street) → **Verification ladder: Self-Listed → ID Verified (NRC + PACRA) → Sector Verified (HPCZ, ZAMRA, Tourism Council) → Vergeo Preferred (50+ orders, 4.7+)**, step fade transitions.
- **Design language:** near-black plum surfaces `#0a0a0d/#131318/#1b1b23/#252532`, hairline borders `rgba(255,255,255,.07)`, warm text `#eeeae3`, caramel accent `#c8935c`, semantic green/blue/red `#5ab88a/#5a9fc8/#e06b5a`. **Playfair Display + DM Sans.** Pill radius 99 everywhere (NavPill), cards 12–16. Glow shadow ring.

### 1.5 `Vergeo_Prototype_offline.html` — "Vergeo — Multi-Vendor Platform · Zambia" — **4/5**

Light warm **mobile-first services app** — the best 360px information architecture in the set. **Verdict 4/5 — winning bottom-nav pattern (incl. AI tab per decision D23), best payment screen and AI chat; services-only, no products/events.**

- **Screens:** bottom nav **Home / Search / AI ✦ / Saved**; Home (dark gradient hero `#1c1c1e→#2e2420→accent` with decorative rings, DM Serif Display two-line headline "Find any service, / anywhere in Zambia.", inline search, **pastel category tiles with subcategories**, trending vendor cards); Search (list + **SVG map view** with vendor pins, hover labels, user-location ring, distances); Vendor detail (Open tag, services); Booking (choose service → date → time → review → confirmed); **Payment** (method cards MTN MoMo `#f5b400` / Airtel `#e02020` / Zamtel Kwacha `#0a7a30` / Card "Processed via DPO Pay", **phone-prefix hints "+260 97/076"**, select → success card — no wait state); **AI chat** (assistant intro, simulated RAG answers citing vendor cards, staggered typing-dot `pulse`, suggestion chips).
- **Design language:** warm cream `#f9f6f2/#f5f2ee`, hairline `#ece8e3`, neutral text ramp `#222/#555/#888/#aaa`, tweakable caramel accent (default `#a1815e`), **pastel category fills** `#c9a88a · #7aab8a · #c9836a · #7a9ab5 · #b5a07a · #8a8ab5`. **DM Sans + DM Serif Display.** Radius 10/12/20, chip pills. Three soft shadow levels. 4-step **verification TierBadge pills ○ / ✓ / ✓✓ / ★**.
- **Animations:** `fadeSlideUp` screen-enter .25s (keyed remount per route) · `pulse` typing dots (1.2s, `i*0.2s` stagger) · .15s hover transitions.

### 1.6 `Convergeo_Wireframes.html` — "Convergeo — Wireframes" — **4/5 as flow spec, 1/5 as visual**

Lo-fi annotated paper wireframes (Caveat/Kalam handwriting + JetBrains Mono, paper `#f6f1e7`, ink `#1b1915`, burnt-orange accent `#c8531a`, hard offset shadows `2px 2px 0 ink`, sketchy uneven radii). Nine tabbed boards with A/B/C layout variations. **Verdict: unmatched flow breadth — the only variant covering checkout/escrow, KYC, RFQ, QR tickets and admin queues; visuals intentionally disposable.**

- **Boards:** Onboarding (customer splash+OTP, **language EN·Bemba·Nyanja**, interest picker; vendor 3-lane signup _NRC-only 10min / PACRA verified / premium brand_, **KYC upload "STEP 2 OF 4 · IDENTITY — Upload NRC, front & back, we auto-read the number"**, first product) · Home ×3 (search-first "Muli bwanji, Chisomo 👋" / category-first / feed-first TikTok-style) + desktop magazine mix · Product (dense card; **multi-vendor comparison "7 vendors selling this"** with shared canonical photo; verified reviews) · Hub/Directory (**logo grid** "2,418 businesses", map view, vendor profile with WhatsApp CTA) · Events (feed with ribbons; **dynamic QR ticket "CONVERGEO · LIVE TICKET" with rotating code + REFRESH + Transfer**; organiser create-event with ticket tiers & 5% fee) · City & Services (**RFQ post form: category, describe job, when, budget K400–700, photos, "Send to 8 providers", "3–5 providers usually reply in an hour"**; Livingstone city guide) · **Checkout ×3 (linear 1-page / stepped 3-step / escrow-explained)** with **escrow state timeline: You paid → Held by Convergeo → Delivered → Vendor paid** + Report issue · Vendor (mobile daily-driver: TODAY K2,860, Mark packed, "Escrow held · K1,840"; desktop dashboard + product table with CSV upload) · Admin (**command centre: GMV today K184k, vendor approvals queue, product review queue ·14, payout ledger "K48,210 → vendors", disputes with Refund buyer / Extend escrow**).
- K currency everywhere; MoMo rails named; the richest Zambian-context copywriting of any variant.

### 1.7 Legacy live prototype (screenshot reference) — **1/5**

Material-Design cards, hero carousel, Upcoming Events row with **corner ribbons SOLD OUT / PROMOTION / PUBLIC**, thumbs up/down counts, K prices, cart icons; Featured Products row (★+count, vendor name, K price); tabs Products/Events/Services/Viewpoints. **Verdict 1/5 visually (generic Material), but it validates:** events as first-class homepage merchandise, ribbon status vocabulary, per-card vendor attribution, K-pricing. Carry the _ribbon status concept_ forward as chips; drop thumbs-down voting and raw Material chrome.

---

## 2. Token extraction (per file)

| Token          | Offline Bundle (flagship)                            | v1 Standalone                  | Convergeo Platform                                | Prototype Standalone (dark)              | Prototype offline (mobile)                            | Wireframes                      |
| -------------- | ---------------------------------------------------- | ------------------------------ | ------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------- | ------------------------------- |
| Primary        | `#4c5470` slate                                      | `#C8861A` gold                 | `#1f4d30` forest green                            | `#c8935c` caramel                        | accent tweak (`#a1815e`)                              | `#c8531a` burnt orange          |
| Secondary      | `#363c52` / `#d0d4e8`                                | `#a86c12` / `#f0d4a0`          | `#2d6b43` / `#e8f3ec`                             | surf ramp `#131318→#252532`              | category pastels (below)                              | `#e0a23b` amber                 |
| Accent         | `#2d4a7a` navy                                       | `#2d4a7a` navy                 | oklch amber + teal, `#e54a2a` red                 | green/blue/red `#5ab88a/#5a9fc8/#e06b5a` | `#2a7a4a` green, `#4a90d9` blue                       | `#2f7a4a` good / `#8a5a00` warn |
| Surface/ground | `#FAF7F2`/`#F3EDE3`/#fff; dark `#18120a/#231c10`     | same cream                     | `#faf7f2`/`#f2ede4`/#fff                          | `#0a0a0d` + plum surfaces                | `#f9f6f2`/`#f5f2ee`/#fff                              | paper `#f6f1e7`/`#efe7d5`       |
| Text           | `#2a1f0e/#6b5a3e/#9c8a72` warm                       | same                           | `#0e1a12→#94ada3` green-ink                       | `#eeeae3/#9090a8/#54546a`                | `#222/#555/#888/#aaa`                                 | ink `#1b1915/#3a362f/#6d675a`   |
| Border         | `#e8dfd0`                                            | same                           | `#e8e2d8`                                         | `rgba(255,255,255,.07)`                  | `#ece8e3`                                             | solid ink lines                 |
| Font display   | Cormorant Garamond                                   | Cormorant Garamond             | (none — one sans)                                 | Playfair Display                         | DM Serif Display                                      | Caveat (annotation)             |
| Font body      | DM Sans                                              | DM Sans                        | Plus Jakarta Sans                                 | DM Sans                                  | DM Sans                                               | Kalam + JetBrains Mono          |
| Radius scale   | 12 / 18 / pills 18 / 50%                             | 12 / 20                        | 10 / 16 / 24 / chips 50px                         | 12 / 14 / 16 / pill 99                   | 10 / 12 / 20 / pill 20                                | 2 / sketch-uneven               |
| Shadows        | `0 4px 24px rgba(28,19,8,.07)` · `0 12px 48px …,.13` | same (gold-tinted focus rings) | `0 2px 12px rgba(0,0,0,.07)` · `0 8px 32px …,.12` | hairline ring + caramel glow             | `0 1px 4px .04` · `0 4px 24px .08` · `0 8px 40px .08` | offset hard `2px 2px 0 ink`     |
| Motion         | .15–.4s; `cubic-bezier(.2,.8,.3,1)`; 6 keyframes     | .15–.4s; 2 keyframes           | .1–.5s; material `(.4,0,.2,1)`                    | .15–.4s; spring `(.34,1.56,.64,1)`       | .15–.25s; 2 keyframes                                 | ~none (.15s)                    |
| Currency       | **K**                                                | **K**                          | ZMW                                               | ZMW                                      | (K implied, unlabeled)                                | **K**                           |

Pastel category fills (Prototype offline `VergeoData`): beauty `#c9a88a` · health `#7aab8a` · food `#c9836a` · fitness `#7a9ab5` · home `#b5a07a` · auto `#8a8ab5`.

---

## 3. Strongest-elements selection

| Area                                              | Winner (source)                                                                    | Why · what to take                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Global nav (desktop/top)**                      | Offline Bundle `Nav` + `MegaMenu`                                                  | Sticky cream bar that gains shadow on scroll; logo; "All Categories" mega-menu (hover column of categories → subcategory grid + featured mini-products + promo block); inline search with suggestions; cart button with count badge; "Sell on Vergeo" CTA. Complete and calm.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Bottom mobile nav**                             | Prototype offline (pattern) + Convergeo Platform (labels)                          | Prototype offline proves the 360px tab bar **with a dedicated ✦ AI tab** (matches decision D23); Platform PWA supplies the commerce tab set + active-dot indicator. Production: **Home · Browse · Ask Vergeo ✦ · Orders · Account**, active dot + label, 56px bar. No variant's flagship had one — this is a synthesis, flagged in prompts.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Hero / home merchandising**                     | Offline Bundle home, with Prototype-offline hero as variant                        | Editorial hero: uppercase eyebrow, serif clamp headline with `<em>` second line, sub, dual CTA, stats trio, collage of floating image cards with `float-a/b` bob + free-delivery badge. Then: category grid (one wide card), **flash-deal banner with live countdown**, tabbed product rows, services/events/vendors rows, sell CTA, promo strip (🚚 Nationwide · 🔒 Secure Payments · ↩️ 7-Day Returns · 🏆 Verified Vendors). The dark-gradient ring hero (Prototype offline) becomes hero variant #2. Legacy carousel becomes variant #3 (admin-rotatable).                                                                                                                                                                                                              |
| **Product card + grid**                           | Offline Bundle `ProductCard`                                                       | Badge chip + −% discount chip on image; quick-add reveal on hover (tap-visible on mobile); vendor attribution line; ★ + review count; `K 1,250` + struck old price; **logistics tag pills (Nearest / Cheapest / International / 7-Day Wait)** with the `color+'18'` tint recipe — uniquely Zambian value prop. Grid 4→3→2 with shimmer skeletons. Legacy card contributes nothing extra.                                                                                                                                                                                                                                                                                                                                                                                    |
| **Event card + ticket UI**                        | Offline Bundle `EventCard`/Event Detail + Wireframes QR ticket                     | Card: image, status badge (Free/Selling Fast — extend with legacy SOLD OUT/PROMOTION vocabulary), category pill, date+location with inline SVG icons, **capacity `spots-bar`**, price, "Get ticket" CTA. Detail: schedule timeline, speakers, sticky ticket card with qty. Ticket wallet = Wireframes' **dynamic QR "LIVE TICKET"** (rotating code, REFRESH, Transfer, Directions) — anti-screenshot design, spec-ready.                                                                                                                                                                                                                                                                                                                                                    |
| **Service card / RFQ entry**                      | Offline Bundle service pages + Wireframes RFQ + Prototype Standalone archetype     | ServiceCard with availability + tag pills; Service Detail's per-category **`SERVICE_THEMES` dark gradient heroes** (the deck's dark-panel move) + booking sidebar (date+notes → inline confirm). RFQ entry from Wireframes: "Need something done? Post what you need — providers quote you." + form (category, description, when, budget range, photos, "Send to N providers", reply-time promise). Quote-Based Jobs archetype (Prototype Standalone) defines when RFQ replaces book-now.                                                                                                                                                                                                                                                                                   |
| **Vendor / directory card**                       | Offline Bundle vendor pages + Prototype offline trust pills + Wireframes logo grid | Full VendorCard: cover, avatar, tier chip, category, location, stats row. **Two distinct ladders, never conflate:** commercial tier (Platinum/Gold/Silver/Bronze `TIER_META` with perks) vs **trust ladder ○ Self-Listed / ✓ ID Verified / ✓✓ Sector Verified / ★ Preferred** (Prototype Standalone semantics + Prototype offline pill styling). Directory adds the Wireframes "hub of logos" grid + map view (SVG pin map from Prototype offline Search). WhatsApp contact CTA from Wireframes profile.                                                                                                                                                                                                                                                                    |
| **PDP layout**                                    | Offline Bundle Product Detail + Wireframes comparison                              | Gallery with thumbs; name, ★ bars, price row with save-chip; qty stepper; delivery info rows; tabs Description/Specs/Reviews (rating distribution bars); related products. Fold in Wireframes' **multi-vendor comparison block ("7 vendors selling this", distance/price per vendor, shared canonical photo)** — it matches the canonical-product/moderation model ("Duplicate canonical record" flag in Platform admin).                                                                                                                                                                                                                                                                                                                                                   |
| **Cart / checkout steps**                         | Offline Bundle cart drawer + Wireframes stepped-escrow + Prototype offline payment | Slide-in cart drawer holding **mixed line types (product/service/ticket)** with type badges and per-vendor grouping (Wireframes: "Items · 2 vendors"). Checkout = Wireframes' **stepped shape: Items → Delivery (home/pickup point) → Pay**, with the **escrow explainer timeline (You paid → Held → Delivered → Vendor paid)**. Payment step = Prototype offline method cards (brand-colored MTN/Airtel/Zamtel/Card, phone-prefix hints, DPO card rail) + Prototype Standalone's stepper polish. No hi-fi checkout exists — build from this composite.                                                                                                                                                                                                                     |
| **Badges / ribbons / status chips**               | Offline Bundle + Platform + legacy vocabulary                                      | Image-corner chips (dark pill 18px) for product/event states; tinted alpha pills for tags; Platform's soft status chips (green/amber/red bg + deep text) for orders/admin; trust pills ○✓✓✓★; escrow state chips from Wireframes. Unify legacy ribbon words (SOLD OUT, PROMOTION, PUBLIC) into the chip enum — chips, not diagonal ribbons.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Empty / loading states**                        | Offline Bundle + Prototype offline                                                 | `img-shimmer` gradient skeleton (1.4s) on all media; `no-results` (icon + copy + reset action); `cart-empty` (🛒 + "Your cart is empty" + Start Shopping CTA); toast stack (max 4, auto-dismiss 2.8s) with type icons 🛒/📅/🎟; AI typing pulse dots. Platform/v1 offer none — extend the flagship's pattern everywhere.                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Animations & micro-interactions worth keeping** | (named → effect)                                                                   | `page-in` → route change fade+8px rise, .3s `cubic-bezier(.2,.8,.3,1)` · `toast-in/out` → toast slide-spring in, fade out · `shimmer` → skeleton sweep · `float-a/b` → hero collage bob 4–5s · **quick-add reveal** → CTA rises over product image on hover/tap · **nav-scrolled** → shadow materializes after 40px scroll · **card lift** → `transform+box-shadow .25s` hover · **spots-fill** → capacity bar width ease · **FlashCountdown** → per-second HH:MM:SS blocks · `fadeSlideUp` → mobile screen-enter .25s · `pulse` → staggered AI typing dots · **confirm spring pop** → success ✓ scales .7→1, .4s `cubic-bezier(.34,1.56,.64,1)` · wizard step fade (200ms out/in). Drop: none of these are gratuitous; all ≤.4s and GPU-friendly (opacity/transform only). |
| **Typography system**                             | DM Sans body (4 of 6 files) + serif display                                        | Body/UI: **DM Sans** — unanimous winner. Display: standardize on **DM Serif Display** (same family pairing, heavier strokes → legible at 360px on low-end Android; already carries the flagship-style hero in Prototype offline), keep **Cormorant Garamond** only as the desktop oversized-hero alternate (founder taste call; both stay in the font pipeline, one active via token). Numerals/IDs/USSD codes: **JetBrains Mono** (from Wireframes tables). Playfair reserved for the dark "premium" theme preset if ever shipped.                                                                                                                                                                                                                                         |

---

## 4. Admin-swappable candidates (CMS-configurable modules)

The founder wants hero/banner elements rotatable from the admin portal. The bundles already prove the mechanism: `tweaks-defaults` JSON → runtime `setProperty('--token', value)`. Elevate these to first-class admin config:

1. **Hero module registry** — homepage hero is a slot rendering one of: `editorial-light` (flagship: eyebrow/headline `<em>`/sub/2 CTAs/stats/3 image-card slots), `gradient-dark` (Prototype offline rings hero), `carousel` (legacy pattern, rebuilt). Admin fields: variant, headline rich-text (the `heroHeadline` tweak exists today), sub, CTA labels+targets, image slots, stats trio, schedule window.
2. **Flash-deal banner** — on/off, tag copy ("⚡ Flash Deals"), headline ("Up to 40% off Electronics"), target collection/URL, **countdown end-datetime**, background image.
3. **Homepage row order & visibility** — the home is already a linear list of sections (Categories → Flash → Product tabs → Services → Events → Vendors → Sell CTA → Promo strip); make it an ordered array of module instances with per-row on/off.
4. **Featured collections** — the Featured / Top Deals / New Arrivals tab set becomes admin-defined collections (name + product query/hand-pick); same for Services row, Events row, Top Vendors row.
5. **Category grid** — which categories, order, which gets the wide card, per-category image + **pastel fill color** (VergeoData already stores color per category) + subcategory lists (drives mega-menu too).
6. **Promo strip** — 4 icon+title+sub value-prop slots.
7. **Sell-CTA block** — image, headline, bullet features, CTA.
8. **Theme presets (seasonal)** — token bundle {primary, accent, bg, dark, darkMode} as named presets: _Vergeo Slate_ (`#4c5470`, current), _Harvest Gold_ (`#C8861A`, v1), _Dusty Mauve_ (`#ddc5d2` bg experiment found in the bundle's tweaks), _Warm Dark_ (dark-mode vars). One-click activate + schedule.
9. **Badge/status vocabulary** — enum of card chips (SOLD OUT, PROMOTION, PUBLIC, Selling Fast, Free, New, Featured) with color mapping, editable.
10. **Mega-menu featured slots** — featured mini-products + promo block per category.
11. **Announcement bar / footer** — app-store links, MoMo payment note, link columns.
12. **`SERVICE_THEMES`** — per-service-category detail-hero gradient/accent/icon set, editable per category.

---

## 5. Proposed unified token set (production design system)

Reconciles the flagship's cream/serif system, the dark prototype's panels, the pastel category fills, and the deck language (cream ground · dark navy serif display · aubergine dark panels · pastel category fills · pill tags · K-pricing). 360px-first.

```css
:root {
  /* ── Ground & surfaces ── */
  --bg: #faf7f2; /* cream page ground (unanimous across variants) */
  --bg-2: #f3ede3; /* recessed cream */
  --surface: #ffffff; /* cards */
  --border: #e8dfd0;
  /* ── Dark panels (deck: aubergine; used for service heroes, footer, promo strip, dark mode) ── */
  --panel: #241b30; /* aubergine — reconciles SERVICE_THEMES #2a1f3d / #1a1a2e and dark-proto plum surfaces */
  --panel-2: #2e2440; /* elevated aubergine */
  --panel-text: #eeeae3;
  --panel-muted: #9f94b0;
  --panel-border: rgba(255, 255, 255, 0.08);
  /* ── Ink & display ── */
  --text: #2a2118; /* warm near-black body ink (flagship) */
  --text-2: #6b5a3e;
  --text-3: #9c8a72;
  --display-ink: #23324e; /* dark navy for serif display headlines (deck) */
  /* ── Brand & semantic ── */
  --primary: #2d4a7a; /* navy — actions, links, active nav (flagship accent, promoted) */
  --primary-deep: #1f3557;
  --primary-tint: #e8f0fa;
  --accent: #c8861a; /* gold — prices-on-sale, stars, flash & promo highlights (v1 heritage) */
  --success: #3a7a4a;
  --danger: #c0392b;
  --warning: #d4a020;
  --info: #2a6a9a;
  /* ── Category pastels (fills for tiles/pills; text always --text on top) ── */
  --cat-beauty: #c9a88a;
  --cat-health: #7aab8a;
  --cat-food: #c9836a;
  --cat-fitness: #7a9ab5;
  --cat-home: #b5a07a;
  --cat-auto: #8a8ab5;
  /* tint recipe for tag pills: bg = color @ 10% (hex+'1A'), border = color @ 20% (hex+'33'), text = color */
  /* ── Type (360px-first) ── */
  --font-display: "DM Serif Display", Georgia, serif; /* alt preset: 'Cormorant Garamond' */
  --font-body: "DM Sans", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", monospace; /* order ids, OTP, amounts in tables */
  --fs-hero: clamp(2rem, 6vw, 3.9rem); /* serif, line-height 1.1 */
  --fs-h1: 1.75rem;
  --fs-h2: clamp(1.35rem, 2.4vw, 2.1rem); /* serif, lh 1.15–1.2 */
  --fs-h3: 1.0625rem; /* sans 600 */
  --fs-body: 0.9375rem; /* 15px, lh 1.55 */
  --fs-sm: 0.8125rem;
  --fs-micro: 0.6875rem; /* caps, ls .08em */
  --fs-price: 1.02rem; /* 700, K-formatted */
  /* ── Space (4px base) ── */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;
  --sp-6: 24px;
  --sp-8: 32px;
  --sp-12: 48px;
  --sp-16: 64px;
  /* card padding 12–16 mobile / 16–20 desktop; section padding 28 mobile / 48 desktop */
  /* ── Radii ── */
  --r-sm: 8px;
  --r: 12px;
  --r-lg: 18px;
  --r-pill: 999px; /* avatars 50% */
  /* ── Shadows (warm-black keyed) ── */
  --shadow-1: 0 1px 4px rgba(28, 19, 8, 0.05);
  --shadow-2: 0 4px 24px rgba(28, 19, 8, 0.07);
  --shadow-3: 0 12px 48px rgba(28, 19, 8, 0.13);
  --focus-ring: 0 0 0 3px rgba(45, 74, 122, 0.18);
  /* ── Motion ── */
  --dur-fast: 150ms;
  --dur: 250ms;
  --dur-slow: 400ms;
  --ease-out: cubic-bezier(0.2, 0.8, 0.3, 1); /* pages, toasts, reveals */
  --ease-std: cubic-bezier(0.4, 0, 0.2, 1); /* vendor/admin surfaces */
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1); /* success confirmations only */
}
```

- **Dark mode / dark panels:** **Superseded 2026-07-20** by [`docs/design/vergeo5-ui-ux-audit.md`](../design/vergeo5-ui-ux-audit.md) §6 and the live token implementation — warm **charcoal** panels (`#1A1816` family) and independent dark page grounds (`#141312`…), not aubergine `#241B30`. See [`docs/designs/TOKENS.md`](./TOKENS.md). The CSS snippet above retains aubergine only as historical selection context.
- **K-pricing:** single formatter `K {n.toLocaleString('en-ZM')}` (flagship pattern); ZMW only in admin finance exports/ledgers. Old price struck in `--text-3`; savings chip in `--accent` tint.
- **Pill tags:** all tags/chips are pills (`--r-pill`) using the alpha-tint recipe; corner badges on imagery are solid `--panel`/status color pills.
- **Keyframes shipped in `packages/ui`:** `page-in`, `toast-in/out`, `shimmer`, `float-a/b`, `fadeSlideUp`, `pulse-dots`, plus reduced-motion media query disabling all but opacity fades.
- **Vendor/admin apps** use the same tokens with `--font-display` applied only to KPI numerals (dark-proto Playfair-stat pattern, executed with DM Serif Display) and `--ease-std` motion.

---

## 6. Gaps — flows with no design in ANY variant (wireframe-by-spec in prompts)

Hi-fi = usable high-fidelity design exists. WF = lo-fi wireframe only. ∅ = nothing anywhere.

> **Reconciliation — 2026-07-21 (customer app verified against source).** Most items below are no longer open. The list is retained for historical scope; use this status map instead:
>
> - **Closed (shipped, customer):** #1 Checkout — real stepped `contact→fulfilment→payment→review` flow (`checkout/page.tsx` → `CheckoutShell`, no "Coming soon"). · #2 Mobile-money USSD wait — full pending/approve/timeout/retry/failed/COD (`checkout/pending/[groupId]` → `ussd-wait.tsx`, backoff poll). · #5 Disputes & returns — `account/orders/[id]/dispute` + `/return`. · #8 Order tracking — `account/orders` + per-step `order-timeline.tsx`. · #11 Wishlist / account / addresses — `wishlist`, `account/profile`, `account/addresses`, `account/recent`. · #14 Search results (mobile) — `search` + `results-tabs.tsx`.
> - **Partial (customer):** #6 RFQ — entry `services/post-job` + inbox `account/jobs` exist; vendor quote-compose unverified. · #9 Onboarding — `login/otp/signup` exist; language/interest picker not built. · #13 PWA/system — `offline` route + `sw.ts` exist; install-prompt/low-bandwidth fallbacks partial.
> - **Still open / not audited here (vendor & admin apps):** #3 KYC upload · #4 Admin queue detail views · #7 Scanner/check-in · #10 Buyer↔vendor messaging · #12 Vendor payout detail. Ticket QR on `account/tickets/[id]` now renders a **scannable SVG matrix** via `packages/ui` `QrCode` (fixed 2026-07-23; covered by `packages/ui/src/qr.test.tsx`).
>
> Remaining **design-fidelity** deltas (elements weaker than the source bundles) are tracked separately: ~~logistics pills (§3)~~, ~~PLP struck-price/discount-% chip~~, ~~default-hero product imagery~~, ~~PDP tabs polish~~, ~~payment-rail brand colours~~, ~~commercial-tier ladder activation~~.

1. **Checkout (hi-fi)** — WF only (3 shapes). No hi-fi cart→delivery→pay→review page flow in any variant; the flagship's "Proceed to Checkout" routes to an explicit _"This page is part of the full build. Coming soon."_ placeholder.
2. **Mobile-money USSD/STK-push wait state** — ∅. Prototype offline jumps select→success. Needs: "Approve on your phone" pending screen (with the operator's USSD dial-code fallback), timeout/retry, failed-payment recovery, offline-queued state. **Critical Zambian flow.**
3. **KYC upload (hi-fi)** — WF only (NRC front/back auto-read, PACRA docs). Needs camera capture, review/blur check, status pending/rejected states. (Trust-ladder _semantics_ designed in Prototype Standalone; screens missing.)
4. **Admin queues (hi-fi, production IA)** — Platform demo has overview/moderation/trust lists but no detail views: approve/reject modal with reasons, vendor KYC review screen, audit trail, bulk actions. WF adds approvals/review/payout-ledger queues. Compose both into real admin specs.
5. **Disputes & returns** — ∅ beyond one WF line ("Report issue", admin "Refund buyer / Extend escrow"). Needs customer dispute wizard with evidence upload, status timeline, resolution outcomes, vendor response side.
6. **RFQ lifecycle** — entry form WF'd; ∅ for vendor quote-compose, customer quote-comparison inbox, accept→order conversion, expiry.
7. **Scanner mode** — ∅. Organiser ticket check-in (camera QR scan, valid/invalid/duplicate states, offline scan cache); the dynamic QR ticket exists (WF) but no scanning side.
8. **Order tracking / My Orders** — ∅. Platform's bottom nav names an Orders tab with no screen; escrow timeline (WF) is the seed for order-status detail (placed→packed→shipped→delivered→confirm-receipt), list + detail + reorder needed.
9. **Onboarding (hi-fi customer)** — WF only (OTP, language EN/Bemba/Nyanja, interest picker). Vendor wizard exists hi-fi (dark proto) but must be re-skinned to unified tokens.
10. **Messaging/chat (buyer↔vendor)** — ∅ (WF mentions "Messages · 2 new"). AI chat UI (Prototype offline) can seed the thread layout.
11. **Wishlist page, profile/account, address book, notifications center** — ∅ (hearts and Profile tabs exist as affordances only).
12. **Vendor payout detail / finance statements** — KPI cards + WF ledger line only; needs statement, fees breakdown, withdraw-to-MoMo flow.
13. **PWA/system states** — install prompt, offline banner, low-bandwidth image fallbacks, error pages: ∅ (bundle's shimmer/no-results are the only system states).
14. **Search results (hi-fi mobile)** — desktop shop grid exists; the 360px filter sheet/sort UX must be synthesized (Prototype offline map+list is services-only).

**Also normalize during build:** currency ZMW→K in Platform/dark-proto derived screens; add the missing bottom tab bar to the flagship-derived customer app; two-ladder badge discipline (commercial tier vs trust tier); replace legacy thumbs-up/down with ★ ratings everywhere.

---

_Analysis method: bundles unpacked from `__bundler/template` + gzip'd `__bundler/manifest` resources; CSS custom properties, hex frequency, keyframes/transitions, component inventories and copy extracted from the decompressed JSX (React 18 + Babel, `window.*` modules). Base64 image blobs excluded from analysis._
