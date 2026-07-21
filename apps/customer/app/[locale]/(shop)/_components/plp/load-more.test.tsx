// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlpBrowseClient } from "./load-more";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const gridLabels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews yet",
  reviewCount: "({count})",
  quickAdd: "Quick add",
  wishlist: "Save",
  outOfStock: "Out of stock",
  distance: "{distance} away",
};

const controlLabels = {
  loadMore: "Load more",
  loading: "Loading…",
  moreLoaded: "{count} more results loaded.",
  endOfResults: "End of results",
  loadError: "Couldn’t load more results.",
  retry: "Retry",
};

const initialListings = [
  {
    id: "1",
    title: "Listing One",
    productSlug: "one",
    vendorName: "Vendor A",
    priceNgwee: 1000,
    condition: "new",
    inStock: true,
    imagePublicId: null,
    rating: 4,
    reviewCount: 2,
    distanceM: null,
  },
];

describe("PlpBrowseClient progressive loading", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn(function MockIO(this: { observe: () => void; disconnect: () => void }) {
        this.observe = vi.fn();
        this.disconnect = vi.fn();
      }),
    );
  });

  it("keeps the first page in the document for crawlers", () => {
    render(
      <PlpBrowseClient
        locale="en"
        initialListings={initialListings}
        gridLabels={gridLabels}
        apiBaseUrl="https://api.example.test"
        queryString="category_path=electronics"
        nextCursor="cursor-2"
        labels={controlLabels}
      />,
    );

    expect(screen.getByText("Listing One")).toBeInTheDocument();
    expect(screen.getByTestId("product-card")).toHaveAttribute("data-density", "compact");
    expect(screen.getByTestId("plp-load-more")).toBeInTheDocument();
  });

  it("appends the next catalog page without duplicates", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "1",
            title: "Listing One again",
            product_slug: "one",
            vendor_name: "Vendor A",
            price_ngwee: 1000,
            condition: "new",
            in_stock: true,
            image_public_id: null,
            rating: 4,
            review_count: 2,
            distance_m: null,
          },
          {
            id: "2",
            title: "Listing Two",
            product_slug: "two",
            vendor_name: "Vendor B",
            price_ngwee: 2000,
            condition: "new",
            in_stock: true,
            image_public_id: null,
            rating: 5,
            review_count: 1,
            distance_m: null,
          },
        ],
        next_cursor: null,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <PlpBrowseClient
        locale="en"
        initialListings={initialListings}
        gridLabels={gridLabels}
        apiBaseUrl="https://api.example.test"
        queryString="category_path=electronics&cursor=stale"
        nextCursor="cursor-2"
        labels={controlLabels}
      />,
    );

    await user.click(screen.getByTestId("plp-load-more"));

    await waitFor(() => {
      expect(screen.getByText("Listing Two")).toBeInTheDocument();
    });

    expect(screen.getAllByText(/Listing One/).length).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/catalog/listings?category_path=electronics&cursor=cursor-2",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByTestId("plp-aria-live")).toHaveTextContent("1 more results loaded.");
  });
});
