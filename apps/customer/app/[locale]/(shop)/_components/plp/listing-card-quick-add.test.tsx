// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const addCartItem = vi.fn().mockResolvedValue({ items: [] });
const openMiniCart = vi.fn();
const setLastAddedMessage = vi.fn();

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: (...args: unknown[]) => addCartItem(...args),
  openMiniCart: (...args: unknown[]) => openMiniCart(...args),
  setLastAddedMessage: (...args: unknown[]) => setLastAddedMessage(...args),
}));

vi.mock("./use-local-wishlist", () => ({
  useLocalWishlist: () => ({
    isWishlisted: false,
    toggleWishlist: vi.fn(),
    enabled: true,
  }),
}));

import { ListingCard } from "./listing-card";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const labels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews",
  reviewCount: "({count})",
  quickAdd: "Quick add",
  quickAddError: "Could not add",
  wishlist: "Save",
  outOfStock: "Out of stock",
  distance: "{distance} away",
};

describe("ListingCard quick-add", () => {
  it("adds the listing to cart by listing id", async () => {
    const user = userEvent.setup();
    render(
      <ListingCard
        locale="en"
        labels={labels}
        listing={{
          id: "listing-123",
          title: "Phone",
          productSlug: "phone",
          vendorName: "Alpha",
          priceNgwee: 100_000,
          condition: "new",
          inStock: true,
          imagePublicId: null,
          rating: 0,
          reviewCount: 0,
          distanceM: null,
        }}
      />,
    );

    await user.click(screen.getByTestId("product-card-quick-add"));
    await waitFor(() => {
      expect(addCartItem).toHaveBeenCalledWith("listing-123", 1);
      expect(openMiniCart).toHaveBeenCalled();
    });
  });

  it("hides quick-add when out of stock", () => {
    render(
      <ListingCard
        locale="en"
        labels={labels}
        listing={{
          id: "listing-123",
          title: "Phone",
          productSlug: "phone",
          vendorName: "Alpha",
          priceNgwee: 100_000,
          condition: "new",
          inStock: false,
          imagePublicId: null,
          rating: 0,
          reviewCount: 0,
          distanceM: null,
        }}
      />,
    );
    expect(screen.queryByTestId("product-card-quick-add")).not.toBeInTheDocument();
  });
});
