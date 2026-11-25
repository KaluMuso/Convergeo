# Marketplace UI patterns for Convergeo (Zambia, mobile-first)

**Source caveat.** Baymard's detailed guideline text for product pages, product lists, filtering, homepage and checkout is paywalled (Baymard Premium). Free pages gave headline statistics and some guidance. Amazon, eBay and Alibaba mobile page layouts could not be read from text, so pixel sizes and element orders are not sourced. Items tagged **[Rec]** are our recommendations, not findings from a source. Statistics from the Baymard checkout article are from 2015 and are dated.

## 1. Home and navigation

- Show product categories as top-level items in the mobile menu, not behind one generic tap target. 22% of sites do this wrong. Highlight the current scope inside the menu. ([Baymard navigation](https://baymard.com/blog/ecommerce-navigation-best-practice))
- Use subcategory thumbnails on intermediate category pages, with subcategories as the main content above promotions. 39% of sites have missing or unreadable thumbnails, and 38% put promotions first. ([same](https://baymard.com/blog/ecommerce-navigation-best-practice))
- Where a category has about 10 or more subcategories, split it. Users feel overwhelmed at that size. Present shared attributes (size, brand, price) as filters, not as extra categories. 79% of sites use categories where filters would work better. ([same](https://baymard.com/blog/ecommerce-navigation-best-practice))
- **[Rec]** Put one row of 5 tiles above the fold: Products, Services, Events, Supplies, Directory. Put rails (for example "Near you in Lusaka" or "Ending soon") below. Keep the tiles icon-led, with text labels in the chosen language.

## 2. Product card

No sourced card specification was retrieved. **[Rec]** for ZMW and 3G:
- Image first at a fixed ratio (1:1 or 4:5). Serve WebP with srcset and lazy-load. Cap at 8 images per listing (matches our data budget).
- Price directly under the image, formatted with `formatK()` (K1,234.56). Show a strike-through price only when it is a real prior price.
- Vendor name with a verified badge, then the delivery line ("Delivery to Lusaka, 1 to 2 days" or "Pickup available"). Show rating and review count only when the reviews are verified purchases.
- Clamp the title to two lines. Keep the card's total payload small: no hover-only information.

## 3. Product detail page and buy box

- Baymard's free guidance: a buy section with too much information or too many options distracts users from adding to cart. ([Baymard buy section](https://baymard.com/guidelines/789-what-to-include-in-the-buy-section))
- **[Rec]** Buy-box order: title, price (with what it includes), stock status, delivery estimate by area (landmark or GPS-based), seller with verified badge, primary CTA, then secondary actions (save, compare). Put the escrow line ("You pay, held by Vergeo5, released when you confirm") right above the CTA.
- **[Rec]** On mobile, use a sticky bottom bar with price and CTA after the buy box scrolls away.
- **[Rec]** Specs table: show the first 5 rows, then "See all specs." Reviews: show a summary (average, count, breakdown) before the list.
- Returns wording benchmark, from eBay's policy: "Item not as described" can be opened for 30 days after delivery. The seller must respond within 3 business days and refund within 2 business days of receiving the return. ([eBay Money Back Guarantee](https://www.ebay.com/help/policies/ebay-money-back-guarantee-policy/ebay-money-back-guarantee-policy?id=4210)) Copy the structure of this promise in the trust section, with our own windows.

## 4. Search and filters on mobile

- Open filters in a full-screen layer or bottom sheet from a labeled button. Keep a sticky "Filter & Sort" trigger while scrolling. ([Baymard filter UI](https://baymard.com/blog/ecommerce-filter-ui))
- Do not update results on every tap. Use a "Show X results" button whose count changes as selections change. Keep tap targets at least 44x44 pt.
- Show applied filters as removable chips above the results.
- Show a count beside each filter option ("Blue (34)"). Baymard calls this one of the highest-impact improvements.
- Observed failures: 14% of sites do not allow multi-select, 20% lose applied filters, and 40% of mobile stores use unclear labels. ([same](https://baymard.com/blog/ecommerce-filter-ui))
- **[Rec]** Paginate at 20 results. Lazy-load images. Keep search suggestions text-only to save data.

## 5. Checkout and trust

- **Guest checkout must be easy to find.** 80% of mobile checkouts offer it, but 88% hide it so that 60% of testers missed it. ([Baymard mobile checkout, 2015](https://baymard.com/blog/mobile-ecommerce-checkout-forms))
- **Show the total before payment details.** 33% of sites ask for card details before showing the total. 24% show cost and speed for only some shipping options. 47% of sites with pickup do not list it next to delivery. ([same](https://baymard.com/blog/mobile-ecommerce-checkout-forms))
- Mark required fields consistently (94% do not), put labels above fields (38% use inline labels), and replace generic errors with specific ones (92% use generic errors). ([same](https://baymard.com/blog/mobile-ecommerce-checkout-forms))
- **Escrow wording (Alibaba Trade Assurance).** Five steps: agree terms, buyer pays into escrow, seller ships with tracking, buyer inspects, funds release on confirmation, or automatically if no dispute is raised in the inspection window. Full cancellation is available within two hours of payment and before shipment. ([Alibaba seller blog](https://seller.alibaba.com/blogs/2026/southeast-asia/apparel-accessories/platform-escrow-payment-guide-alibaba-b2b), [Alibaba buyer guide summary via WorldFirst](https://www.worldfirst.com/af/blog/online-sellers/how-to-pay-on-alibaba-africa/)) Its tagline, "protection follows the payment, not the supplier," fits our escrow message.
- **Pay on-platform rule (eBay).** Coverage applies only to purchases paid through eBay. Payment outside the platform is excluded. ([eBay MBG](https://www.ebay.com/help/policies/ebay-money-back-guarantee-policy/ebay-money-back-guarantee-policy?id=4210)) Put "Pay in Convergeo to be protected" in the payment step, and show a warning if someone asks to pay off-platform.
- **Jumia baseline.** Jumia's buyer payment page clearly offers cash on delivery and calls it "safe, fast and easy." It does not describe escrow or buyer protection. ([JumiaPay](https://group.jumia.com/business/pay)) **[Rec]** Keep COD (up to K500, per our guardrails) as a visible option, and place MTN/Airtel MoMo above it.

## 6. Seller dashboard and listing flow

- eBay's mobile listing flow starts with photos and a title. AI proposes item specifics and category from the photo, and the seller reviews them. eBay reports a 50% cut in listing steps in UK testing (its own claim). Available to private sellers in the US, UK and Germany. ([eBay Innovation](https://innovation.ebayinc.com/stories/ebay-reduces-the-time-to-list-on-mobile-with-new-simplified-selling-tool-now-featuring-magical-listing-ai-technology/))
- **[Rec]** Zambian vendor listing order: photos, then title, then category suggestion (accept or change), then price in ZMW, stock, and delivery area (landmark or GPS). Autosave a draft at each step so that a dropped 3G connection loses nothing.
- **[Rec]** Order management: group orders by the action needed ("Ship today," "Awaiting confirmation," "Held in escrow"), not by date. Each row shows the escrow status in plain words. One tap marks an order shipped and asks for tracking or a delivery note.
- **Not covered.** Seller Hub and Seller Central dashboard layouts (KPI tiles, order tables) were not fetched in text. Treat dashboard specifics as unverified.

## Gaps and next steps

- Baymard's full product-page, cart and filter findings need Premium access. Without it, product card and buy-box specifics stay at the recommendation level.
- Amazon and Jumia mobile product-page layouts could be checked by screenshot review (Baymard's public Amazon mobile page, or a Mobbin search) in a follow-up.
- Pixel values in this document are not sourced. Verify them in a design review before adopting.

## Sources

- [Baymard, ecommerce navigation best practice](https://baymard.com/blog/ecommerce-navigation-best-practice)
- [Baymard, ecommerce filter UI](https://baymard.com/blog/ecommerce-filter-ui)
- [Baymard, mobile ecommerce checkout forms (2015)](https://baymard.com/blog/mobile-ecommerce-checkout-forms)
- [Baymard, buy section guideline](https://baymard.com/guidelines/789-what-to-include-in-the-buy-section)
- [Baymard, Amazon mobile product page (paywalled)](https://baymard.com/ecommerce-design-examples/41-product-page/17968-amazon)
- [eBay Money Back Guarantee policy](https://www.ebay.com/help/policies/ebay-money-back-guarantee-policy/ebay-money-back-guarantee-policy?id=4210)
- [eBay Innovation, mobile listing tool](https://innovation.ebayinc.com/stories/ebay-reduces-the-time-to-list-on-mobile-with-new-simplified-selling-tool-now-featuring-magical-listing-ai-technology/)
- [Alibaba seller blog, platform escrow](https://seller.alibaba.com/blogs/2026/southeast-asia/apparel-accessories/platform-escrow-payment-guide-alibaba-b2b)
- [WorldFirst, paying on Alibaba from Africa](https://www.worldfirst.com/af/blog/online-sellers/how-to-pay-on-alibaba-africa/)
- [JumiaPay for business](https://group.jumia.com/business/pay)
