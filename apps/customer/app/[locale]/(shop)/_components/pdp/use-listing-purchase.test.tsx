// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: vi.fn().mockResolvedValue({ items: [{ qty: 1 }] }),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));

vi.mock("./pickup-locations", () => ({
  fetchPickupLocations: vi.fn(),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

import { addCartItem } from "../cart/mini-cart-drawer";

import { fetchPickupLocations } from "./pickup-locations";
import { useListingPurchase } from "./use-listing-purchase";

import type { BuyBoxLabels, BuyBoxListing } from "./buy-box";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const labels: BuyBoxLabels = {
  priceLabel: "Price",
  quantityLabel: "Quantity",
  buyBoxAriaLabel: "Purchase options",
  decreaseLabel: "Decrease",
  increaseLabel: "Increase",
  decreaseSymbol: "-",
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

const listing: BuyBoxListing = {
  id: "listing-1",
  title: "Phone",
  priceNgwee: 450_000,
  condition: "new",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
};

describe("useListingPurchase — required pickup branch gate", () => {
  it("calls addCartItem with no location options for a non-branch-tracked listing", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({ branchTracked: false, locations: [] });
    const { result } = renderHook(() => useListingPurchase(listing, labels));
    await waitFor(() => expect(result.current?.pickupBranchTracked).toBe(false));

    await act(async () => {
      result.current?.handleAddToCart();
    });

    await waitFor(() => {
      expect(addCartItem).toHaveBeenCalledWith("listing-1", 1, undefined, undefined);
    });
  });

  it("refuses to call addCartItem when branch-tracked and no branch is selected", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
    });
    const { result } = renderHook(() => useListingPurchase(listing, labels));
    await waitFor(() => expect(result.current?.pickupBranchTracked).toBe(true));

    act(() => {
      result.current?.handleAddToCart();
    });

    expect(addCartItem).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current?.addError).toBeTruthy());
  });

  it("sends pickup_location_id + fulfilment=pickup once a branch is selected", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
    });
    const { result } = renderHook(() => useListingPurchase(listing, labels));
    await waitFor(() => expect(result.current?.pickupBranchTracked).toBe(true));

    act(() => {
      result.current?.selectPickupLocation("branch-1");
    });
    await waitFor(() => expect(result.current?.selectedPickupLocationId).toBe("branch-1"));

    await act(async () => {
      result.current?.handleAddToCart();
    });

    await waitFor(() => {
      expect(addCartItem).toHaveBeenCalledWith("listing-1", 1, undefined, {
        pickupLocationId: "branch-1",
        fulfilment: "pickup",
      });
    });
  });

  it("refuses to add while branch-tracking status is still unknown (loading)", async () => {
    vi.mocked(fetchPickupLocations).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useListingPurchase(listing, labels));

    expect(result.current?.pickupBranchTracked).toBeNull();
    act(() => {
      result.current?.handleAddToCart();
    });
    expect(addCartItem).not.toHaveBeenCalled();
  });
});
