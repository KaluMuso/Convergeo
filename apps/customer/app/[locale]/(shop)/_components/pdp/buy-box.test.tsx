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

import { addCartItem, openMiniCart } from "../cart/mini-cart-drawer";

import {
  BuyBox,
  clampQuantity,
  getMaxQuantity,
  getStockLabel,
  type BuyBoxLabels,
  type BuyBoxListing,
} from "./buy-box";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const labels: BuyBoxLabels = {
  priceLabel: "Price",
  quantityLabel: "Quantity",
  decreaseLabel: "Decrease",
  increaseLabel: "Increase",
  decreaseSymbol: "-",
  increaseSymbol: "+",
  addToCartLabel: "Add to cart",
  addToCartSoonLabel: "Add to cart (coming soon)",
  inStockLabel: "In stock",
  outOfStockLabel: "Out of stock",
  lowStockLabel: (count) => `Only ${count} left`,
  alwaysAvailableLabel: "Available",
  singleVendorLabel: "Single vendor",
  moqLabel: (count) => `MOQ ${count}`,
  conditionNewLabel: "New",
  conditionRefurbishedLabel: "Refurbished",
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
    expect(getStockLabel(inStockListing, labels)).toBe("Only 5 left");
    expect(getStockLabel(outOfStockListing, labels)).toBe("Out of stock");
    expect(
      getStockLabel({ ...inStockListing, stockMode: "always_available", stockQty: null }, labels),
    ).toBe("Available");
  });

  it("caps max quantity for tracked stock", () => {
    expect(getMaxQuantity(inStockListing)).toBe(5);
    expect(getMaxQuantity(outOfStockListing)).toBe(1);
  });
});

describe("BuyBox", () => {
  it("renders in-stock state with working stepper", async () => {
    const user = userEvent.setup();
    render(<BuyBox listing={inStockListing} labels={labels} singleVendor={false} />);

    expect(screen.getByTestId("pdp-stock-state")).toHaveTextContent("Only 5 left");
    expect(screen.getByTestId("pdp-price")).toHaveTextContent("K4,500.00");
    expect(screen.getByTestId("pdp-add-to-cart")).toBeEnabled();

    await user.click(screen.getByTestId("pdp-qty-increase"));
    expect(screen.getByTestId("pdp-qty-value")).toHaveTextContent("2");
  });

  it("adds to cart from the buy box", async () => {
    const user = userEvent.setup();
    render(<BuyBox listing={inStockListing} labels={labels} singleVendor={false} />);

    await user.click(screen.getByTestId("pdp-add-to-cart"));

    await waitFor(() => {
      expect(addCartItem).toHaveBeenCalledWith("listing-1", 1);
      expect(openMiniCart).toHaveBeenCalled();
      expect(screen.getByTestId("pdp-add-to-cart-success")).toHaveTextContent("Add to cart");
    });
  });

  it("renders out-of-stock state with disabled stepper", () => {
    render(<BuyBox listing={outOfStockListing} labels={labels} singleVendor />);

    expect(screen.getByTestId("pdp-stock-state")).toHaveTextContent("Out of stock");
    expect(screen.getByTestId("pdp-qty-decrease")).toBeDisabled();
    expect(screen.getByTestId("pdp-qty-increase")).toBeDisabled();
    expect(screen.getByTestId("pdp-single-vendor")).toBeInTheDocument();
  });
});
