// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const cartMocks = vi.hoisted(() => ({
  addCartItem: vi.fn().mockResolvedValue({ items: [{ qty: 1 }] }),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));
vi.mock("../cart/mini-cart-drawer", () => cartMocks);
const { addCartItem, openMiniCart } = cartMocks;

vi.mock("./pickup-locations", () => ({
  fetchPickupLocations: vi.fn(),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

import { fetchPickupLocations } from "./pickup-locations";
import { useListingPurchase } from "./use-listing-purchase";

import type { BuyBoxLabels, BuyBoxListing } from "./buy-box";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.doMock("../cart/mini-cart-drawer", () => cartMocks);
  cartMocks.addCartItem.mockReset().mockResolvedValue({ items: [{ qty: 1 }] });
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("shared purchase while cart actions load", () => {
  it("publishes retry success only after replay delivery and client completion", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({ branchTracked: false, locations: [] });
    cartMocks.addCartItem.mockRejectedValueOnce(new Error("Response lost after commit"));
    const { result } = renderHook(() => useListingPurchase(listing, labels));
    await waitFor(() => expect(result.current?.pickupBranchTracked).toBe(false));
    act(() => result.current?.handleAddToCart());
    await waitFor(() => expect(result.current?.addError).toBe(labels.addToCartErrorLabel));
    expect(result.current?.adding).toBe(false);

    const delivery = deferred<void>();
    const clientCompletion = deferred<void>();
    cartMocks.addCartItem.mockImplementationOnce(async () => {
      await delivery.promise;
      await clientCompletion.promise;
      return { items: [{ qty: 1 }] };
    });
    vi.useFakeTimers();
    try {
      act(() => result.current?.handleAddToCart());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(addCartItem).toHaveBeenCalledTimes(2);
      expect(result.current?.adding).toBe(true);
      expect(result.current?.addedMessage).toBeNull();
      expect(openMiniCart).not.toHaveBeenCalled();
      await act(async () => {
        delivery.resolve();
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current?.adding).toBe(true);
      expect(result.current?.addedMessage).toBeNull();
      expect(openMiniCart).not.toHaveBeenCalled();
      await act(async () => {
        clientCompletion.resolve();
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current?.adding).toBe(false);
      expect(result.current?.addError).toBeNull();
      expect(result.current?.addedMessage).toBe(labels.addToCartLabel);
      expect(cartMocks.setLastAddedMessage).toHaveBeenCalledExactlyOnceWith(labels.addToCartLabel);
      expect(openMiniCart).toHaveBeenCalledOnce();
      expect(addCartItem).toHaveBeenNthCalledWith(2, "listing-1", 1, undefined, undefined);
    } finally {
      delivery.resolve();
      clientCompletion.resolve();
      vi.useRealTimers();
    }
  });

  it("holds concurrent controls through loading and the request while preserving pickup arguments", async () => {
    const module = deferred<typeof cartMocks>();
    const response = deferred<{ items: Array<{ qty: number }> }>();
    const load = vi.fn(() => module.promise);
    vi.doMock("../cart/mini-cart-drawer", load);
    cartMocks.addCartItem.mockReturnValueOnce(response.promise);
    vi.mocked(fetchPickupLocations).mockResolvedValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "Mall", lat: -15.4, lng: 28.3 }],
    });
    const { result } = renderHook(() => useListingPurchase(listing, labels));
    await waitFor(() => expect(result.current?.pickupLocations).toHaveLength(1));
    act(() => result.current?.selectPickupLocation("branch-1"));
    act(() => {
      result.current?.handleAddToCart();
      result.current?.handleAddToCart();
    });
    expect(result.current?.adding).toBe(true);
    await waitFor(() => expect(load).toHaveBeenCalledOnce());
    expect(addCartItem).not.toHaveBeenCalled();
    await act(async () => {
      module.resolve(cartMocks);
    });
    await waitFor(() => expect(addCartItem).toHaveBeenCalledOnce());
    expect(addCartItem).toHaveBeenCalledWith("listing-1", 1, undefined, {
      pickupLocationId: "branch-1",
      fulfilment: "pickup",
    });
    act(() => result.current?.handleAddToCart());
    expect(addCartItem).toHaveBeenCalledOnce();
    expect(openMiniCart).not.toHaveBeenCalled();
    expect(result.current?.addedMessage).toBeNull();
    await act(async () => {
      response.resolve({ items: [{ qty: 1 }] });
    });
    await waitFor(() => expect(result.current?.adding).toBe(false));
    expect(openMiniCart).toHaveBeenCalledOnce();
    expect(cartMocks.setLastAddedMessage).toHaveBeenCalledExactlyOnceWith(labels.addToCartLabel);
    expect(result.current?.addedMessage).toBe(labels.addToCartLabel);
  });

  it("reports import and request failure without success effects and permits retry", async () => {
    vi.doMock("../cart/mini-cart-drawer", () => {
      throw new Error("Chunk unavailable");
    });
    vi.mocked(fetchPickupLocations).mockResolvedValue({ branchTracked: false, locations: [] });
    const { result } = renderHook(() => useListingPurchase(listing, labels));
    await waitFor(() => expect(result.current?.pickupBranchTracked).toBe(false));
    act(() => result.current?.handleAddToCart());
    await waitFor(() => expect(result.current?.addError).toBe(labels.addToCartErrorLabel));
    expect(result.current?.adding).toBe(false);
    expect(addCartItem).not.toHaveBeenCalled();
    expect(openMiniCart).not.toHaveBeenCalled();
    vi.doMock("../cart/mini-cart-drawer", () => cartMocks);
    cartMocks.addCartItem.mockRejectedValueOnce(new Error("Request unavailable"));
    act(() => result.current?.handleAddToCart());
    await waitFor(() => expect(result.current?.adding).toBe(false));
    expect(result.current?.addError).toBe(labels.addToCartErrorLabel);
    expect(openMiniCart).not.toHaveBeenCalled();
    expect(cartMocks.setLastAddedMessage).not.toHaveBeenCalled();
    act(() => result.current?.handleAddToCart());
    await waitFor(() => expect(openMiniCart).toHaveBeenCalledOnce());
    expect(addCartItem).toHaveBeenCalledTimes(2);
    expect(result.current?.addError).toBeNull();
    expect(result.current?.adding).toBe(false);
  });
});
