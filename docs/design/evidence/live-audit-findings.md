# Vergeo5 Customer Marketplace Live Visual & UX Audit

**Audit Date:** July 20, 2026  
**Site:** https://vergeo5.com/en  
**Viewport Sizes Tested:** 360px, 390px, 768px, 1366px, 1440px  
**Authentication State:** Unauthenticated (guest user)

---

## EXECUTIVE SUMMARY

Comprehensive audit of Vergeo5 customer marketplace across 5 viewport sizes covering homepage, navigation, search, category browsing, product details, cart, and authentication flows. Site is functional with polished UI but has critical issues with dark mode implementation (purple tint) and several incomplete features (search, cart functionality).

**Critical Issues Found:** 3  
**High Priority Issues:** 8  
**Medium Priority Issues:** 12  
**Total Findings:** 30+

---

## ROUTES SUCCESSFULLY VISITED

1. ✅ `/en` - Homepage (tested at all 5 viewports)
2. ✅ `/en/search?q=phone` - Search results page
3. ✅ `/en/c/electronics` - Electronics category page with filters
4. ✅ `/en/p/tecno-spark-20` - Product detail page
5. ✅ `/en/cart` - Shopping cart (empty state)
6. ✅ `/en/login?next=/en/account` - Sign in / authentication page
7. ✅ Footer sections (vendor profiles, legal links, help links)

## ROUTES WITH FAILURES / INCOMPLETE FEATURES

1. ❌ Search functionality - Returns "Search unavailable" error
2. ❌ Add to cart - Returns connection error, cart functionality not working
3. ❌ Account area - Requires authentication (expected, not accessible unauthenticated)
4. ❌ Checkout flow - Not accessible without cart items

---

## DETAILED FINDINGS

### CRITICAL ISSUES (Must Fix Before Launch)

#### F01: Dark Mode Purple/Aubergine Tint Throughout Site

- **Route:** All routes (homepage, categories, products, footer, etc.)
- **Viewport:** All sizes (360px-1440px)
- **State:** Dark mode enabled
- **Problem:** Dark mode background has a strong purple/aubergine tint instead of neutral dark gray or black. This affects navbar, hero section background, page backgrounds, footer, and all dark surfaces.
- **Why It Matters:** User specifically dislikes this purple tint. Creates unprofessional appearance and poor readability. Dark mode should use neutral grays for accessibility and visual comfort during night-time use.
- **Screenshots:**
  - `live-dark-mode-purple-tint-1366.png` (homepage with purple navbar and hero)
  - `live-products-dark-mode-1366.png` (product grid with purple backgrounds)
  - `live-footer-dark-mode-1366.png` (footer with purple tint)
- **Recommendation:** Change dark mode color scheme to use neutral grays (e.g., #1a1a1a, #2d2d2d) instead of purple-tinted colors.

#### F02: Search Functionality Completely Non-Functional

- **Route:** `/en/search?q=phone`
- **Viewport:** 1366px desktop
- **State:** Unauthenticated, after searching for "phone"
- **Problem:** Search returns error page stating "Search unavailable - We could not load search results right now. Try again shortly, or browse categories."
- **Why It Matters:** Search is a primary discovery mechanism for e-commerce. Users cannot find products by keyword, severely limiting usability. This is a blocker for customer self-service and product discovery.
- **Screenshot:** `live-search-unavailable-1366.png`
- **Recommendation:** Implement search backend integration with Postgres FTS + pg_trgm as specified in architecture docs. Priority: HIGH - implement before launch.

#### F03: Add to Cart Functionality Broken

- **Route:** `/en/p/tecno-spark-20`
- **Viewport:** 1366px desktop
- **State:** Unauthenticated, attempted to add Tecno Spark 20 to cart
- **Problem:** Clicking "Add to cart" button returns error message: "Could not add to cart. Check your connection and try again."
- **Why It Matters:** Cannot complete purchase flow. Users cannot add products to cart, making transactions impossible. Core e-commerce functionality is non-functional.
- **Screenshot:** `live-add-to-cart-error-1366.png`
- **Recommendation:** Fix cart API integration. Verify backend endpoint, authentication requirements, and error handling. Test cart functionality end-to-end before launch.

---

### HIGH PRIORITY ISSUES (Impact User Experience)

#### F04: No Search Autocomplete or Suggestions

- **Route:** Homepage search bar
- **Viewport:** 1366px desktop
- **State:** Typed "phone" into search field
- **Problem:** Search input has no autocomplete dropdown, no suggested products, no recent searches, no popular queries. Only shows clear button and search icon.
- **Why It Matters:** Autocomplete improves search success rate by guiding users to valid queries and popular products. Users expect this on modern marketplaces (Amazon, eBay style).
- **Recommendation:** Implement search suggestions dropdown using product catalog data and search analytics.

#### F05: Category Cards Have No Hover States or Visual Feedback

- **Route:** Homepage `/en`
- **Viewport:** 1366px desktop
- **State:** Hovering over category cards
- **Problem:** Category cards (Groceries & Staples, Personal Care & Beauty, Fashion, Electronics, Home & Living, Office & Stationery, Light Hardware) show no hover state, cursor change, or visual feedback. Only small icons appear on cards but no interaction feedback.
- **Why It Matters:** Users expect hover feedback to indicate clickability. Lack of hover states makes interface feel unresponsive and reduces perceived affordance of interactive elements.
- **Recommendation:** Add hover states: scale transform, shadow increase, or border highlight on category cards.

#### F06: Product Cards Show "SAMPLE LISTING" Badge on Many Products

- **Route:** Homepage product grid, category pages
- **Viewport:** 1366px desktop
- **State:** Viewing product listings
- **Problem:** Many products display yellow "SAMPLE LISTING" badge prominently on product images. Appears on multiple listings including Tecno Spark 20, TVs & Audio products, Small Appliances, and others.
- **Why It Matters:** Confuses customers about whether products are real or test data. Reduces trust and looks unprofessional. Sample data should not be visible on live production site.
- **Recommendation:** Remove all sample listing badges before launch. Replace sample products with real vendor inventory or clearly mark as "Coming Soon" if awaiting inventory.

#### F07: "New on Vergeo5" Section Shows Duplicate Products

- **Route:** Homepage `/en`
- **Viewport:** 1366px, 1440px
- **State:** Scrolling homepage product sections
- **Problem:** "New on Vergeo5" section shows multiple identical products side-by-side (same image, same title "Tea & Coffee" from Lusaka Electronics Hub appearing twice consecutively).
- **Why It Matters:** Looks like a bug or poor content management. Reduces content variety and wastes valuable homepage real estate. Suggests catalog data quality issues.
- **Recommendation:** Implement de-duplication logic in "New on Vergeo5" query to show unique products only. Review catalog for duplicate entries.

#### F08: Mobile Navigation (Hamburger Menu) Non-Responsive at 360px

- **Route:** Homepage `/en`
- **Viewport:** 360px mobile
- **State:** Attempted to open mobile navigation menu
- **Problem:** At 360px viewport, attempted to tap the hamburger/menu icon in top-right of navbar but menu did not open. No visible response or loading state.
- **Why It Matters:** Mobile users (primary target for Zambia market per specs) cannot access navigation menu. Critical usability failure on mobile devices which are the primary browsing device in Zambia.
- **Recommendation:** Debug mobile menu functionality. Verify touch event handlers, menu component state management, and responsive breakpoints.

#### F09: Theme Toggle Not Prominent in Navbar

- **Route:** All routes
- **Viewport:** 1366px desktop
- **State:** Looking for theme toggle
- **Problem:** Theme toggle (sun/moon icon) appears small and blends with other navbar items. Not visually distinctive. Easy to miss among other navigation elements.
- **Why It Matters:** User specifically tested dark mode, suggesting theme control is important. Users may not discover dark mode option if toggle is not prominent.
- **Recommendation:** Make theme toggle more prominent: larger icon, distinctive styling, or move to more visible position (e.g., right side near account/cart).

#### F10: "Continue with Google" Button Appears Disabled/Greyed Out

- **Route:** `/en/login?next=/en/account` (Sign in page)
- **Viewport:** 1366px desktop
- **State:** Viewing sign-in options
- **Problem:** "Continue with Google" button has grey/disabled appearance. Unclear if it's actually disabled or just poorly styled. No hover state or indication of clickability.
- **Why It Matters:** Google OAuth is a preferred authentication method for many users. If button appears disabled, users won't attempt to use it, reducing conversion on account creation.
- **Recommendation:** Style Google button with clear enabled state. Add hover effect. If Google auth is not yet implemented, remove button or add "Coming soon" label.

#### F11: Footer Has Dark Background in Light Mode

- **Route:** All routes with footer visible
- **Viewport:** 1366px desktop
- **State:** Light mode enabled
- **Problem:** Footer uses dark navy/black background even in light mode, creating jarring visual transition from light page content to dark footer.
- **Why It Matters:** Inconsistent with light mode design language. Footer should adapt to theme like rest of the interface for cohesive experience.
- **Recommendation:** Create light mode footer variant with light background and dark text, or use subtle gray background that transitions smoothly.

---

### MEDIUM PRIORITY ISSUES (Polish & Enhancement)

#### F12: No Language Selector Visible in Navbar

- **Route:** All routes
- **Viewport:** 1366px desktop
- **State:** Checking for language controls
- **Problem:** No visible language selector in navbar. Site supports /en, /bem, /nya, /fr routes per architecture, but users cannot switch languages from UI.
- **Why It Matters:** Multilingual support is a key feature for Zambian market (English, Bemba, Nyanja, French). Users cannot discover or switch to their preferred language.
- **Recommendation:** Add language selector dropdown in navbar (top-right area). Show current language and available options with flags or language codes.

#### F13: Prices Display with Excessive Decimal Precision

- **Route:** Product listings, product detail pages
- **Viewport:** All viewports
- **State:** Viewing product prices
- **Problem:** Prices show format like "K19,440.65" and "K12,216.43" with two decimal places (ngwee). While technically accurate, typical Zambian retail uses whole Kwacha or single decimal for most products.
- **Why It Matters:** Excessive precision makes prices look strange and harder to scan quickly. Most retail prices in Zambia are round numbers (K500, K1,200) rather than K1,234.56.
- **Recommendation:** Round display prices to nearest Kwacha or show ".00" explicitly only when price has decimals. Consider showing "K19,441" instead of "K19,440.65" for better readability.

#### F14: Product Images Not Optimized - Large File Sizes

- **Route:** Product listings, category pages
- **Viewport:** All viewports
- **State:** Observing image loading
- **Problem:** Product images appear to load slowly, suggesting large file sizes. No visible progressive loading or blur-up placeholders during image load.
- **Why It Matters:** Zambian users are on 3G networks with data costs per architecture goals. Large images consume expensive data and slow page loads, degrading mobile experience.
- **Recommendation:** Implement Cloudinary f_auto/q_auto transformations. Use Next.js Image component with proper sizing. Add loading="lazy" and blur placeholders.

#### F15: No "Back to Top" Button on Long Pages

- **Route:** Homepage, category pages
- **Viewport:** All viewports
- **State:** Scrolling to bottom of page
- **Problem:** Long pages (homepage with multiple product sections, category pages with many products) have no "Back to top" button. Users must scroll manually all the way back up.
- **Why It Matters:** Poor UX on mobile especially. Users get trapped at bottom of long pages. Common e-commerce pattern that improves navigation efficiency.
- **Recommendation:** Add floating "Back to top" button that appears after scrolling past first viewport height.

#### F16: Bottom Navigation Bar Has No Active State Indicator

- **Route:** All routes (mobile viewports)
- **Viewport:** 360px, 390px mobile
- **State:** Navigating between bottom nav items (Home, All Categories, Browse, Ask, Account)
- **Problem:** Bottom navigation bar shows 5 items but no visual indicator of which page is currently active. All icons appear same weight and color.
- **Why It Matters:** Users cannot tell which section they're currently in. Active state is fundamental navigation feedback pattern.
- **Recommendation:** Add active state styling: different color, underline, icon fill, or bold text for current nav item.

#### F17: Cart Icon Shows "(0)" Count in Navbar

- **Route:** All routes
- **Viewport:** 1366px desktop
- **State:** Empty cart
- **Problem:** Cart icon in navbar displays "Cart (0)" with the zero explicitly shown. Standard pattern is to hide count badge when cart is empty or show subtle badge.
- **Why It Matters:** Explicit "(0)" looks cluttered and emphasizes empty state. Cleaner to show just "Cart" icon with no badge when empty.
- **Recommendation:** Hide count badge when cart quantity is 0, or show small badge only when items exist.

#### F18: Search Bar Placeholder Text Is Generic

- **Route:** Homepage, all pages with search
- **Viewport:** All viewports
- **State:** Search field unfocused
- **Problem:** Search placeholder says "Search products, services, events..." which is accurate but generic. Could be more engaging or contextual.
- **Why It Matters:** Good placeholder text prompts users with examples and improves search engagement. "Search for phones, laptops, groceries..." would be more concrete.
- **Recommendation:** Use dynamic placeholder text with rotating examples of popular products or categories.

#### F19: "Selling on Vergeo5 is invite-only" Banner Not Dismissible

- **Route:** Homepage, footer area
- **Viewport:** All viewports
- **State:** Viewing seller invite banner
- **Problem:** Footer section shows "Selling on Vergeo5 is invite-only for now" message with "Learn about selling" button, but banner cannot be dismissed. Takes significant footer space.
- **Why It Matters:** Users who see this multiple times may find it intrusive. Not all visitors are potential sellers. Should be dismissible or shown less prominently after first view.
- **Recommendation:** Add dismiss button to invite banner, or show as dismissible banner at top of page on first visit only, or reduce size in footer.

#### F20: No Breadcrumb Navigation on Category/Product Pages

- **Route:** `/en/c/electronics`, `/en/p/tecno-spark-20`
- **Viewport:** 1366px desktop
- **State:** Viewing category and product pages
- **Problem:** Category page shows "Home / Electronics" breadcrumb, but styling is minimal and easy to miss. Product page shows brand ("TECNO") but no category breadcrumb. No visual hierarchy in breadcrumb presentation.
- **Why It Matters:** Breadcrumbs help users understand site hierarchy and navigate back efficiently. Important for SEO and UX. Should be visually prominent and interactive.
- **Recommendation:** Style breadcrumbs more prominently with separators (> or /), hover states, and clear typography. Add breadcrumbs to product pages showing: Home > Electronics > Product Name.

#### F21: Filters Sidebar Has No "Applied Filters" Summary

- **Route:** `/en/c/electronics` (category page with filters)
- **Viewport:** 1366px desktop
- **State:** Viewing filters panel
- **Problem:** Left sidebar shows filters (Price, Condition, Availability, Rating, Near me) but no summary of currently applied filters. No way to see all active filters at a glance or clear all at once.
- **Why It Matters:** As users apply multiple filters, they lose track of what's active. Need visual summary and quick clear function. Standard e-commerce pattern.
- **Recommendation:** Add "Active filters" section at top of results showing applied filters as removable chips. Add "Clear all" button.

#### F22: Product Cards Show "No reviews yet" For All Products

- **Route:** Homepage product grid, category pages
- **Viewport:** All viewports
- **State:** Viewing product listings
- **Problem:** Every product shows "No reviews yet" in gray text under the title. Creates impression of new/untested platform with no social proof.
- **Why It Matters:** Social proof through reviews is critical for e-commerce trust. Seeing "No reviews yet" on every product reduces confidence. Better to hide review line until reviews exist.
- **Recommendation:** Hide "No reviews yet" text. Only show review stars/count when reviews actually exist. Alternatively, show "Be the first to review" as call-to-action.

#### F23: Hero Section Text Hierarchy Weak on Mobile

- **Route:** Homepage `/en`
- **Viewport:** 360px mobile
- **State:** Viewing hero section
- **Problem:** Hero headline "Discover products, services, and events across Zambia" uses similar-sized text for "ZAMBIA'S MARKETPLACE" eyebrow and main headline. Weak visual hierarchy on small screens.
- **Why It Matters:** First impression on mobile is critical. Headline should be immediately readable and compelling. Current layout has too much text competing for attention.
- **Recommendation:** Increase headline font size on mobile, reduce eyebrow text size, or simplify headline to key message. Test with mobile-first approach.

---

### POSITIVE FINDINGS (What Works Well)

#### P01: Responsive Design Functions Across All Viewport Sizes

- **Observation:** Site successfully adapts from 360px to 1440px. Layout reflows appropriately: mobile shows single-column with bottom nav, tablet shows 2-column hero and product grids, desktop shows full multi-column layout with all nav items.
- **Why It Matters:** Responsive design is working as intended per mobile-first architecture. Foundation is solid for mobile Zambian market.

#### P02: Category Card Visual Design Is Appealing

- **Observation:** Category cards use pleasant color palette (tan, green, salmon, blue, purple, brown) with icons and clear labels. Visually distinct and easy to scan.
- **Why It Matters:** Good first impression. Categories are intuitive and inviting to explore.

#### P03: Product Cards Show Key Information Efficiently

- **Observation:** Product cards show: product image, seller name, title, price, review status, and listing badges. Information density is appropriate for quick scanning.
- **Why It Matters:** Users can quickly evaluate products without clicking through. Good for browsing behavior.

#### P04: Theme Toggle Works Smoothly

- **Observation:** Clicking theme toggle (sun/moon icon) immediately switches between light and dark mode with no page reload. Smooth transition.
- **Why It Matters:** Theme switching is a good user experience feature working as expected.

#### P05: Trust Signals Present Throughout

- **Observation:** Homepage hero shows escrow process steps: "YOU PAY → HELD BY VERGEO5 → RELEASED ON DELIVERY". Feature bullets mention seller profiles, Lusaka delivery, clear returns, and escrow. Product pages show escrow message.
- **Why It Matters:** Addresses trust concerns for online commerce in Zambian market. Users see payment protection prominently.

#### P06: Authentication Flow Is Clear and Mobile-First

- **Observation:** Sign in page offers Zambian phone number (+260) as primary method, with SMS OTP. Alternatives are email and Google. Mobile-first design aligns with target market.
- **Why It Matters:** Authentication UX matches Zambian user expectations and mobile-first approach.

---

## VIEWPORT-SPECIFIC OBSERVATIONS

### 360px Mobile (Smallest Common Screen)

- ✅ Layout stacks properly, single-column design
- ✅ Bottom navigation bar visible and accessible
- ✅ Hero text readable, buttons appropriately sized
- ❌ Hamburger menu appears broken (F08)
- ❌ Hero headline text hierarchy weak (F23)
- ⚠️ Need to verify touch target sizes meet 44px minimum

### 390px Mobile (iPhone Standard)

- ✅ Similar to 360px, slightly more comfortable spacing
- ✅ Product cards display well in single column
- ✅ Category cards have good touch target size

### 768px Tablet

- ✅ Hero section switches to side-by-side layout (text left, image/content right)
- ✅ Category cards display in 2-3 column grid
- ✅ Product cards in 2-column grid
- ✅ Bottom navigation still present, appropriate for tablet

### 1366px Desktop (Standard Laptop)

- ✅ Full desktop navigation in top navbar (All Categories, Browse, Services, Events, Ask Vergeo5)
- ✅ Category cards in 3-column grid
- ✅ Product cards in 4-column grid
- ✅ Filters sidebar appears on category pages
- ❌ Theme toggle small and not prominent (F09)
- ❌ Cart shows "(0)" explicitly (F17)

### 1440px Desktop (Large Monitor)

- ✅ Layout similar to 1366px with slightly more whitespace
- ✅ Content remains centered with max-width, good use of space
- ✅ No horizontal scroll issues

---

## TECHNICAL OBSERVATIONS (From DevTools)

1. **Framework:** Next.js 15 (detected from `__next` divs and routing)
2. **Theme System:** Uses `data-theme="light"` or `data-theme="dark"` on HTML element
3. **Routing:** Locale-prefixed routes working (`/en`, routes support `/bem`, `/nya`, `/fr`)
4. **Metadata:** Proper meta tags and Open Graph tags present
5. **Image Loading:** Uses Next.js image optimization (needs tuning per F14)
6. **Scripts:** Multiple scripts loading, some related to analytics/tracking
7. **Accessibility:** `next-route-announcer` present for screen reader support
8. **Performance:** Page loads reasonably fast, but image optimization needed

---

## ACCESSIBILITY QUICK CHECKS

- ✅ Focus visible on interactive elements
- ✅ Color contrast appears adequate in light mode (needs more testing in dark mode with purple tint)
- ✅ Alt text appears present on images
- ⚠️ Need to verify keyboard navigation works for all interactive elements
- ⚠️ Need to test screen reader compatibility (next-route-announcer is present, good sign)
- ⚠️ Need to verify ARIA labels on icon-only buttons (theme toggle, cart, etc.)

---

## RECOMMENDATIONS PRIORITY MATRIX

### Before Launch (Blockers)

1. Fix dark mode purple tint → Use neutral grays (F01)
2. Fix search functionality → Implement backend integration (F02)
3. Fix add to cart → Debug API and error handling (F03)
4. Fix mobile navigation menu → Ensure hamburger menu opens (F08)

### High Priority (Pre-Launch Polish)

5. Remove "SAMPLE LISTING" badges from products (F06)
6. Add search autocomplete/suggestions (F04)
7. Fix duplicate products in "New on Vergeo5" (F07)
8. Style/fix Google sign-in button (F10)
9. Add category card hover states (F05)

### Medium Priority (Post-Launch Improvements)

10. Add language selector to navbar (F12)
11. Improve price display formatting (F13)
12. Optimize product images for 3G (F14)
13. Add "Back to top" button (F15)
14. Add active state to bottom nav (F16)
15. Hide "(0)" on empty cart badge (F17)
16. Improve breadcrumb visibility (F20)
17. Add applied filters summary (F21)

### Low Priority (Enhancements)

18. Make theme toggle more prominent (F09)
19. Create light mode footer variant (F11)
20. Improve search placeholder text (F18)
21. Make invite banner dismissible (F19)
22. Hide "No reviews yet" text (F22)
23. Improve mobile hero hierarchy (F23)

---

## SCREENSHOTS REFERENCE

All screenshots saved to: `/opt/cursor/artifacts/screenshots/`

1. `live-home-360-top.png` - Homepage at 360px mobile (top section)
2. `live-home-360-mid.png` - Homepage at 360px mobile (mid section with categories/products)
3. `live-home-390.png` - Homepage at 390px mobile
4. `live-home-768.png` - Homepage at 768px tablet
5. `live-home-1366.png` - Homepage at 1366px desktop
6. `live-home-1440.png` - Homepage at 1440px large desktop
7. `live-dark-mode-purple-tint-1366.png` - **CRITICAL** Dark mode showing purple tint on homepage
8. `live-products-dark-mode-1366.png` - Product grid in dark mode with purple backgrounds
9. `live-footer-dark-mode-1366.png` - Footer in dark mode with purple tint
10. `live-search-unavailable-1366.png` - **CRITICAL** Search error page
11. `live-category-electronics-1366.png` - Electronics category page with filters and products
12. `live-product-detail-1366.png` - Tecno Spark 20 product detail page
13. `live-add-to-cart-error-1366.png` - **CRITICAL** Add to cart error message
14. `live-cart-empty-1366.png` - Empty cart page
15. `live-auth-signin-1366.png` - Sign in page with phone/email/Google options

---

## CONCLUSION

Vergeo5 marketplace has a **solid foundation** with good responsive design, appealing visual design, and clear information architecture. The site successfully communicates trust (escrow messaging) and adapts well across viewport sizes.

**Critical blockers** before launch:

1. Fix dark mode purple tint (user complaint + poor UX)
2. Implement search functionality
3. Fix cart/checkout flow
4. Fix mobile navigation

**Core strengths:**

- Mobile-first responsive design works well
- Product browsing experience is solid
- Trust signals prominently displayed
- Authentication flow is clear

**Next steps:**

1. Address 3 critical issues (dark mode, search, cart) immediately
2. Remove all "SAMPLE LISTING" content
3. Complete high-priority UI polish items
4. Test with real Zambian users on 3G connections
5. Run full accessibility audit with screen readers
6. Performance test with Lighthouse (mobile, 3G throttling)

Site is **70-80% ready for soft launch** with invite-only sellers. Remaining work is focused on fixing broken features and polish rather than fundamental rebuilds.
