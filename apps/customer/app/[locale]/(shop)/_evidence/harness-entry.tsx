/**
 * Browser-side evidence harness for the discovery-slice/sticky-ATC/search-focus
 * fixes integrated onto staging (M17-CUST-INTEGRATION follow-up).
 *
 * NOT part of the app: `_evidence` is a Next.js private folder, nothing imports
 * this module, and it is never routed or bundled into the shipped app. It exists
 * so the sticky-ATC layout and search-focus evidence is captured against the
 * REAL `StickyMobileAtc` / `MobileHeaderSearch` components and the REAL compiled
 * Tailwind + design tokens, rather than a hand-written copy that could drift.
 *
 * Driven by scripts/qa/evidence/customer-integration/run.mjs (scratchpad-local,
 * not committed — see the manifest for why).
 *
 * Boundary, stated so this is not over-read: this mounts the components
 * directly, driven by fixture props matching the existing, type-checked test
 * fixtures in sticky-mobile-atc.test.tsx — it does NOT traverse Next.js
 * routing, the FastAPI backend, Cloudinary, or any live/staging data. It proves
 * layout and focus behaviour at 360/390/1440px — not routing, data-fetching, or
 * authorization, which the vendor component/page test suites already cover.
 */
"use client";

import { NextIntlClientProvider } from "next-intl";
import { useTranslations } from "next-intl";
import { createRef } from "react";
import { createRoot } from "react-dom/client";

import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";
import navMessages from "../../../../../../packages/i18n/messages/en/nav.json";
import searchMessages from "../../../../../../packages/i18n/messages/en/search.json";
import { MobileHeaderSearch } from "../_components/mobile-header-search";
import { StickyMobileAtc } from "../_components/pdp/sticky-mobile-atc";

import type { BuyBoxLabels, BuyBoxListing } from "../_components/pdp/buy-box";
import type { ListingPurchaseControls } from "../_components/pdp/use-listing-purchase";

declare global {
  interface Window {
    __EVIDENCE_READY__?: boolean;
  }
}

const buyBoxLabels: BuyBoxLabels = {
  priceLabel: "Price",
  quantityLabel: "Quantity",
  buyBoxAriaLabel: "Purchase options",
  decreaseLabel: "Decrease",
  increaseLabel: "Increase",
  decreaseSymbol: "−",
  increaseSymbol: "+",
  addToCartLabel: "Add to cart",
  addingToCartLabel: "Adding…",
  addToCartErrorLabel: "Could not add to cart.",
  inStockLabel: "In stock",
  outOfStockLabel: "Out of stock",
  alwaysAvailableLabel: "Available",
  singleVendorLabel: "Single vendor",
  conditionNewLabel: "New",
  conditionRefurbishedLabel: "Refurbished",
  conditionUsedLabel: "Used",
  conditionAuthenticityLabel: "Condition & Authenticity",
};

// Reproduces the original defect's numbers: K249.00 (76px rendered), MOQ note
// pushing the stock line to "In stock · Minimum order: 3" (long enough to
// truncate), matching the fixture in sticky-mobile-atc.test.tsx.
const listing: BuyBoxListing = {
  id: "listing-1",
  title: "Tecno Spark 20C 128GB Dual SIM Smartphone",
  priceNgwee: 24_900,
  condition: "new",
  stockMode: "tracked",
  stockQty: 12,
  moq: 3,
  inStock: true,
};

function makePurchase(overrides: Partial<ListingPurchaseControls> = {}): ListingPurchaseControls {
  return {
    quantity: 3,
    decrease: () => {},
    increase: () => {},
    atMin: false,
    atMax: false,
    adding: false,
    addError: null,
    addedMessage: null,
    handleAddToCart: () => {},
    stockLabel: "In stock",
    maxQuantity: 12,
    pickupBranchTracked: false,
    pickupLocations: [],
    pickupLocationsLoading: false,
    pickupLocationsLoadError: false,
    selectedPickupLocationId: null,
    selectPickupLocation: () => {},
    ...overrides,
  };
}

function StickyAtcHarness() {
  const observeRef = createRef<HTMLElement | null>();

  // A real IntersectionObserver drives StickyMobileAtc's own visibility (it
  // returns null while the anchor is in view), so the harness reproduces a
  // real PDP buy box: content tall enough to scroll the anchor out of the
  // viewport, exactly as a Playwright scroll would encounter on the real page.
  return (
    <div style={{ position: "relative" }}>
      <div
        ref={observeRef as never}
        data-testid="evidence-buybox-anchor"
        style={{ height: 220, background: "var(--bg-2)", padding: 16 }}
      >
        Buy box (anchor) — scroll past this to reveal the sticky bar.
      </div>
      <div style={{ height: 1400, padding: 16 }}>
        Filler content standing in for PDP description/reviews sections.
      </div>
      <StickyMobileAtc
        listing={listing}
        labels={buyBoxLabels}
        purchase={makePurchase()}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />
    </div>
  );
}

function SearchHarness() {
  // Same keys layout.tsx sources MobileHeaderSearch's labels from (nav.shop.* +
  // search.*), so the harness renders the real strings, not stand-ins.
  const tNav = useTranslations("nav");
  const tSearch = useTranslations("search");

  return (
    <div style={{ padding: 16 }}>
      <button type="button" data-testid="evidence-before-trigger" style={{ marginRight: 12 }}>
        {tNav("shop.home")}
      </button>
      <MobileHeaderSearch
        locale="en"
        sheetTitle={tSearch("title")}
        triggerLabel={tNav("shop.searchPlaceholder")}
        labels={{
          placeholder: tNav("shop.searchPlaceholder"),
          submit: tNav("shop.searchSubmit"),
          ariaLabel: tSearch("input.ariaLabel"),
          suggestionsLabel: tSearch("input.suggestionsLabel"),
          noSuggestions: tSearch("input.noSuggestions"),
          recentTitle: tSearch("recent.title"),
        }}
      />
    </div>
  );
}

const rootEl = document.getElementById("root");
const mode = rootEl?.dataset.mode;

if (rootEl && mode === "sticky-atc") {
  createRoot(rootEl).render(
    <NextIntlClientProvider locale="en" messages={{ catalog: catalogMessages }}>
      <StickyAtcHarness />
    </NextIntlClientProvider>,
  );
  window.__EVIDENCE_READY__ = true;
} else if (rootEl && mode === "search") {
  createRoot(rootEl).render(
    <NextIntlClientProvider locale="en" messages={{ nav: navMessages, search: searchMessages }}>
      <SearchHarness />
    </NextIntlClientProvider>,
  );
  window.__EVIDENCE_READY__ = true;
}
