// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { resetLocalWishlistStoreForTests } from "../plp/use-local-wishlist";

import { SearchProductCard, type ResultsTabsLabels, type SearchHit } from "./results-tabs";

const LABELS: ResultsTabsLabels = {
  loadMore: "Load more",
  loading: "Loading…",
  moreLoaded: "More loaded",
  endOfResults: "End of results",
  loadError: "Could not load",
  retry: "Retry",
  ariaLabel: "Search results",
  all: "All",
  products: "Products",
  services: "Services",
  events: "Events",
  vendors: "Vendors",
  count: "{count}",
  resultsCount: "{count} results",
  degraded: "Some results may be missing",
  priceFrom: "from {price}",
  category: "in {category}",
  distanceAway: "{km} km away",
  openNow: "Open now",
  closedNow: "Closed",
  marketplaceListing: "Marketplace listing",
  productGridAria: "Products",
  wishlist: "Add to wishlist",
  wishlistRemove: "Remove from wishlist",
  mediaEmpty: "No image",
  noReviews: "No reviews yet",
  reviewCount: "({count})",
};

const baseHit: SearchHit = {
  id: "sd-1",
  entity_kind: "product",
  entity_id: "e1000000-0000-4000-8000-000000000001",
  title: "Synthetic multiseller product A",
  body: null,
  category_path: null,
  price_min_ngwee: null,
  price_max_ngwee: null,
  lat: null,
  lng: null,
  locale_terms: null,
  boost_signals: {},
  rrf_score: 1,
  slug: "stg-rv-20260719-product-a",
};

/**
 * RC-4 regression coverage (E2E run #52, PR-F2): search_upsert_product()
 * used to hardcode price_min_ngwee/price_max_ngwee = NULL for every
 * product, and this card coerced that NULL to 0 (`?? 0`), rendering a
 * fabricated "K0.00" for a real, priced, multi-vendor product. The DB fix
 * (20260827020000_search_product_price_projection.sql) makes the migration
 * populate real prices for a product with eligible listings; this covers
 * the client mapping so a genuinely priceless hit (no eligible listing at
 * all) still never displays K0.00 either.
 */
describe("SearchProductCard price mapping", () => {
  beforeEach(() => {
    resetLocalWishlistStoreForTests();
  });

  afterEach(() => {
    cleanup();
    resetLocalWishlistStoreForTests();
  });

  it("renders no price line — never K0.00 — when both price fields are null", () => {
    render(<SearchProductCard hit={baseHit} locale="en" labels={LABELS} />);
    expect(screen.queryByTestId("price-block")).not.toBeInTheDocument();
    expect(screen.queryByText(/K0\.00/)).not.toBeInTheDocument();
    expect(screen.getByText("Synthetic multiseller product A")).toBeInTheDocument();
  });

  it("renders the real price when price_min_ngwee is populated (the confirmed defect case)", () => {
    render(
      <SearchProductCard
        hit={{ ...baseHit, price_min_ngwee: 12500, price_max_ngwee: 14900 }}
        locale="en"
        labels={LABELS}
      />,
    );
    expect(screen.getByText("K125.00")).toBeInTheDocument();
    expect(screen.queryByText(/K0\.00/)).not.toBeInTheDocument();
  });

  it("falls back to price_max_ngwee when price_min_ngwee is absent", () => {
    render(
      <SearchProductCard
        hit={{ ...baseHit, price_min_ngwee: null, price_max_ngwee: 14900 }}
        locale="en"
        labels={LABELS}
      />,
    );
    expect(screen.getByText("K149.00")).toBeInTheDocument();
  });
});
