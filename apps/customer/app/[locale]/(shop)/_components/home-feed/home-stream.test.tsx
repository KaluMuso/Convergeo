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

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.test${path}`,
}));

const { fetchJson } = vi.hoisted(() => ({
  fetchJson: vi.fn(),
}));

vi.mock("../../../../../lib/fetch-json", () => ({
  fetchJson,
}));

import { HomeListingStream, loadHomeStreamFirstPage } from "./home-stream";

afterEach(() => {
  cleanup();
  fetchJson.mockReset();
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
    cta: "Sell on Vergeo5",
  },
};

describe("loadHomeStreamFirstPage", () => {
  it("returns error when the API fetch fails", async () => {
    fetchJson.mockRejectedValue(new Error("down"));
    await expect(loadHomeStreamFirstPage()).resolves.toEqual({ status: "error" });
  });

  it("returns ok with a normalised page on success", async () => {
    fetchJson.mockResolvedValue({ items: [{ id: "a" }], next_cursor: "c1" });
    await expect(loadHomeStreamFirstPage()).resolves.toEqual({
      status: "ok",
      page: { items: [{ id: "a" }], next_cursor: "c1" },
    });
  });
});

describe("HomeListingStream", () => {
  it("renders nothing when the stream failed to load", () => {
    const { container } = render(
      <HomeListingStream
        stream={{ status: "error" }}
        sectionListingIds={[]}
        locale="en"
        cardLabels={cardLabels}
        labels={labels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a friendly empty state when the catalogue is truly empty", () => {
    render(
      <HomeListingStream
        stream={{ status: "ok", page: { items: [], next_cursor: null } }}
        sectionListingIds={[]}
        locale="en"
        cardLabels={cardLabels}
        labels={labels}
      />,
    );

    expect(screen.getByTestId("home-stream-empty")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sell on Vergeo5" })).toHaveAttribute(
      "href",
      "/en/sell",
    );
    expect(screen.queryByTestId("home-stream-client")).not.toBeInTheDocument();
  });

  it("renders nothing when every item was already shown above", () => {
    const { container } = render(
      <HomeListingStream
        stream={{
          status: "ok",
          page: { items: [{ id: "dup" } as never], next_cursor: null },
        }}
        sectionListingIds={["dup"]}
        locale="en"
        cardLabels={cardLabels}
        labels={labels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("home-stream-empty")).not.toBeInTheDocument();
  });

  it("keeps the client stream when a next cursor remains", () => {
    render(
      <HomeListingStream
        stream={{ status: "ok", page: { items: [], next_cursor: "c1" } }}
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
