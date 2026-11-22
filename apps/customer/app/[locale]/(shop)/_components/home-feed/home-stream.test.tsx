// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./home-stream-client-lazy", () => ({
  HomeStreamClient: () => <div data-testid="home-stream-client" />,
}));

vi.mock("../plp/listing-grid", () => ({
  ListingGrid: () => <div data-testid="listing-grid" />,
}));

vi.mock("../../../(marketing)/sell/_components/vendor-app", () => ({
  getVendorSignupUrl: () => null,
}));

import { HomeListingStream } from "./home-stream";

afterEach(() => {
  cleanup();
});

const cardLabels = {
  vendor: "By {vendor}",
  noReviews: "No reviews",
  reviewCount: "({count})",
  quickAdd: "Add",
  wishlist: "Save",
  outOfStock: "Out of stock",
} as const;

const labels = {
  title: "Popular now",
  loadMore: "Load more",
  loading: "Loading…",
  moreLoaded: "{count} more items loaded.",
  endOfResults: "You're all caught up",
  loadError: "Couldn't load more right now.",
  retry: "Try again",
  empty: {
    title: "New products are on the way",
    body: "Sellers are listing more every week.",
    cta: "Sell on Convergeo",
  },
};

describe("HomeListingStream", () => {
  it("shows a friendly empty state when the stream has no listings", () => {
    render(
      <HomeListingStream
        page={{ items: [], next_cursor: null }}
        sectionListingIds={[]}
        locale="en"
        cardLabels={cardLabels}
        labels={labels}
      />,
    );

    expect(screen.getByTestId("home-stream")).toBeInTheDocument();
    expect(screen.getByTestId("home-stream-empty")).toBeInTheDocument();
    expect(screen.getByText("New products are on the way")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sell on Convergeo" })).toHaveAttribute(
      "href",
      "/en/sell",
    );
    expect(screen.queryByTestId("home-stream-client")).not.toBeInTheDocument();
  });

  it("keeps the client stream when a next cursor remains", () => {
    render(
      <HomeListingStream
        page={{ items: [], next_cursor: "c1" }}
        sectionListingIds={[]}
        locale="en"
        cardLabels={cardLabels}
        labels={labels}
      />,
    );

    expect(screen.getByTestId("home-stream-client")).toBeInTheDocument();
    expect(screen.queryByTestId("home-stream-empty")).not.toBeInTheDocument();
  });
});
