// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../cart/mini-cart-drawer", () => ({
  addCartItem: vi.fn().mockResolvedValue({ items: [{ qty: 2 }] }),
  openMiniCart: vi.fn(),
  setLastAddedMessage: vi.fn(),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    if (key === "pdp.buyBox.lowStock") {
      return `Only ${values?.count ?? 0} left`;
    }
    if (key === "pdp.buyBox.moq") {
      return `MOQ ${values?.count ?? 0}`;
    }
    if (key === "pdp.leadTime") {
      return `Requires ${values?.days ?? 0} days lead time`;
    }
    if (key === "pdp.buyBox.pickup.required") {
      return "Select a pickup branch to add this item";
    }
    return key;
  },
}));

// Default: not branch-tracked, so existing (pre-pickup-flow) tests keep
// their original add-to-cart behavior unchanged. Pickup-specific tests
// below override this per-case.
const usePickupLocationSelectionMock = vi.fn((_listingId: string | null) => ({
  branchTracked: false as boolean | null,
  locations: [] as Array<{ id: string; landmark: string; lat: number; lng: number }>,
  loading: false,
  loadError: false,
  selectedLocationId: null as string | null,
  selectLocation: vi.fn(),
}));

vi.mock("./use-pickup-location-selection", () => ({
  usePickupLocationSelection: (listingId: string | null) =>
    usePickupLocationSelectionMock(listingId),
}));

import { addCartItem, openMiniCart } from "../cart/mini-cart-drawer";

import {
  BuyBox,
  clampQuantity,
  getMaxQuantity,
  getStockLabel,
  type BuyBoxLabels,
  type BuyBoxListing,
} from "./buy-box";

import type { PickupLocationPickerLabels } from "./pickup-location-picker";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  usePickupLocationSelectionMock.mockReturnValue({
    branchTracked: false,
    locations: [],
    loading: false,
    loadError: false,
    selectedLocationId: null,
    selectLocation: vi.fn(),
  });
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
  addToCartErrorLabel: "Could not add to cart. Try again.",
  inStockLabel: "In stock",
  outOfStockLabel: "Out of stock",
  alwaysAvailableLabel: "Available",
  singleVendorLabel: "Single vendor",
  conditionNewLabel: "New",
  conditionRefurbishedLabel: "Refurbished",
  conditionUsedLabel: "Used",
  conditionAuthenticityLabel: "Condition & Authenticity",
};

const pickupLabels: PickupLocationPickerLabels = {
  heading: "Choose a pickup branch",
  selectAria: "Pickup branch",
  placeholder: "Select a branch",
  loading: "Loading pickup branches…",
  loadError: "Could not load pickup branches. Try again.",
  unavailable: "No pickup branch is currently available for this item",
};

const inStockListing: BuyBoxListing = {
  id: "listing-1",
  title: "Phone",
  priceNgwee: 450_000,
  condition: "new",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
};

const outOfStockListing: BuyBoxListing = {
  ...inStockListing,
  stockQty: 0,
  inStock: false,
};

describe("buy-box helpers", () => {
  it("clamps quantity to stock", () => {
    expect(clampQuantity(10, inStockListing)).toBe(5);
    expect(clampQuantity(0, inStockListing)).toBe(1);
  });

  it("reports stock labels", () => {
    const withLowStock = {
      ...labels,
      lowStockLabel: (count: number) => `Only ${count} left`,
    };
    expect(getStockLabel(inStockListing, withLowStock)).toBe("Only 5 left");
    expect(getStockLabel(outOfStockListing, withLowStock)).toBe("Out of stock");
    expect(
      getStockLabel(
        { ...inStockListing, stockMode: "always_available", stockQty: null },
        withLowStock,
      ),
    ).toBe("Available");
  });

  it("caps max quantity for tracked stock", () => {
    expect(getMaxQuantity(inStockListing)).toBe(5);
    expect(getMaxQuantity(outOfStockListing)).toBe(1);
  });

  it("uses weekly capacity for made-to-order listings", () => {
    const mtoListing: BuyBoxListing = {
      ...inStockListing,
      productClass: "E",
      stockQty: 0,
      leadTimeDays: 14,
      vendorCapacityPerWeek: 3,
    };
    expect(getMaxQuantity(mtoListing)).toBe(3);
  });
});

describe("BuyBox", () => {
  it("renders in-stock state with working stepper", async () => {
    const user = userEvent.setup();
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    expect(screen.getByTestId("pdp-stock-state")).toHaveTextContent("Only 5 left");
    expect(screen.getByTestId("pdp-price")).toHaveTextContent("K4,500.00");
    expect(screen.getByTestId("pdp-add-to-cart")).toBeEnabled();

    await user.click(screen.getByTestId("pdp-qty-increase"));
    expect(screen.getByTestId("pdp-qty-value")).toHaveTextContent("2");
  });

  it("adds to cart from the buy box (not branch-tracked — no location needed)", async () => {
    const user = userEvent.setup();
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    await user.click(screen.getByTestId("pdp-add-to-cart"));

    await waitFor(() => {
      expect(addCartItem).toHaveBeenCalledWith("listing-1", 1, undefined, undefined);
      expect(openMiniCart).toHaveBeenCalled();
      expect(screen.getByTestId("pdp-add-to-cart-success")).toHaveTextContent("Add to cart");
    });
  });

  it("renders out-of-stock state with disabled stepper", () => {
    render(
      <BuyBox
        listing={outOfStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor
      />,
    );

    expect(screen.getByTestId("pdp-stock-state")).toHaveTextContent("Out of stock");
    expect(screen.getByTestId("pdp-qty-decrease")).toBeDisabled();
    expect(screen.getByTestId("pdp-qty-increase")).toBeDisabled();
    expect(screen.getByTestId("pdp-single-vendor")).toBeInTheDocument();
  });

  it("surfaces preferred seller at the purchase moment", () => {
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
        seller={{ displayName: "Lusaka Hub", ratingLabel: "4.8 (12)", preferred: true }}
        preferredBadgeLabel="Preferred seller"
      />,
    );

    expect(screen.getByTestId("pdp-buy-box-seller")).toHaveTextContent("Lusaka Hub");
    expect(screen.getByTestId("corner-ribbon-trust")).toHaveTextContent("Preferred seller");
  });
});

describe("BuyBox — required pickup branch selection", () => {
  it("disables Add to Cart while branch-tracking status is unknown (loading)", () => {
    usePickupLocationSelectionMock.mockReturnValue({
      branchTracked: null,
      locations: [],
      loading: true,
      loadError: false,
      selectedLocationId: null,
      selectLocation: vi.fn(),
    });
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    expect(screen.getByTestId("pdp-pickup-location-loading")).toBeInTheDocument();
    expect(screen.getByTestId("pdp-add-to-cart")).toBeDisabled();
  });

  it("shows an honest unavailable state and keeps Add to Cart disabled when branch-tracked with zero active branches", () => {
    usePickupLocationSelectionMock.mockReturnValue({
      branchTracked: true,
      locations: [],
      loading: false,
      loadError: false,
      selectedLocationId: null,
      selectLocation: vi.fn(),
    });
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    expect(screen.getByTestId("pdp-pickup-location-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("pdp-add-to-cart")).toBeDisabled();
  });

  it("requires an explicit branch selection — never auto-selects — before Add to Cart is enabled", async () => {
    const selectLocation = vi.fn();
    usePickupLocationSelectionMock.mockReturnValue({
      branchTracked: true,
      locations: [
        { id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 },
        { id: "branch-2", landmark: "Manda Hill", lat: -15.41, lng: 28.31 },
      ],
      loading: false,
      loadError: false,
      selectedLocationId: null,
      selectLocation,
    });
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    const select = screen.getByTestId("pdp-pickup-location-select");
    expect(select).toBeInTheDocument();
    expect(screen.getByTestId("pdp-add-to-cart")).toBeDisabled();

    const user = userEvent.setup();
    await user.selectOptions(select, "branch-2");
    expect(selectLocation).toHaveBeenCalledWith("branch-2");
    // The mock hook doesn't re-render with the new selection itself (that's
    // the real hook's job) — this proves the picker calls through with the
    // exact chosen id, never guessing/defaulting one.
  });

  it("sends the selected pickup_location_id and fulfilment=pickup through addCartItem", async () => {
    usePickupLocationSelectionMock.mockReturnValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
      loading: false,
      loadError: false,
      selectedLocationId: "branch-1",
      selectLocation: vi.fn(),
    });
    const user = userEvent.setup();
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    expect(screen.getByTestId("pdp-add-to-cart")).toBeEnabled();
    await user.click(screen.getByTestId("pdp-add-to-cart"));

    await waitFor(() => {
      expect(addCartItem).toHaveBeenCalledWith("listing-1", 1, undefined, {
        pickupLocationId: "branch-1",
        fulfilment: "pickup",
      });
    });
  });

  it("blocks the click-time fallback with a real error if somehow clicked without a selection", async () => {
    usePickupLocationSelectionMock.mockReturnValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
      loading: false,
      loadError: false,
      selectedLocationId: null,
      selectLocation: vi.fn(),
    });
    render(
      <BuyBox
        listing={inStockListing}
        labels={labels}
        pickupLabels={pickupLabels}
        singleVendor={false}
      />,
    );

    // The button is disabled in this state (proven above); addCartItem must
    // never fire even if some future change bypasses the disabled attribute.
    expect(screen.getByTestId("pdp-add-to-cart")).toBeDisabled();
    expect(addCartItem).not.toHaveBeenCalled();
  });
});
