// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    if (key === "pdp.buyBox.moq") {
      return `Minimum order: ${values?.count ?? 0}`;
    }
    if (key === "pdp.stickyAtc.stockMoqSeparator") {
      return "·";
    }
    return key;
  },
}));

import { StickyMobileAtc } from "./sticky-mobile-atc";

import type { BuyBoxLabels, BuyBoxListing } from "./buy-box";
import type { ListingPurchaseControls } from "./use-listing-purchase";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
  title: "Tecno Spark",
  priceNgwee: 450_000,
  condition: "new",
  stockMode: "tracked",
  stockQty: 5,
  moq: 1,
  inStock: true,
};

function makePurchase(overrides: Partial<ListingPurchaseControls> = {}): ListingPurchaseControls {
  return {
    quantity: 2,
    decrease: vi.fn(),
    increase: vi.fn(),
    atMin: false,
    atMax: false,
    adding: false,
    addError: null,
    addedMessage: null,
    handleAddToCart: vi.fn(),
    stockLabel: "In stock",
    maxQuantity: 5,
    ...overrides,
  };
}

describe("StickyMobileAtc", () => {
  let observerCallback: IntersectionObserverCallback | null = null;

  beforeEach(() => {
    observerCallback = null;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: IntersectionObserverCallback) {
          observerCallback = cb;
        }
        observe = vi.fn();
        disconnect = vi.fn();
        unobserve = vi.fn();
        takeRecords = vi.fn(() => []);
        root = null;
        rootMargin = "";
        thresholds = [];
      },
    );
  });

  it("stays hidden while the buy box intersects the viewport", () => {
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");
    const purchase = makePurchase();

    render(
      <StickyMobileAtc
        listing={listing}
        labels={labels}
        purchase={purchase}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    expect(observerCallback).not.toBeNull();
    observerCallback?.(
      [
        {
          isIntersecting: true,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(screen.queryByTestId("pdp-sticky-mobile-atc")).not.toBeInTheDocument();
  });

  it("shows qty + ATC when buy box leaves the viewport and syncs controls", async () => {
    const user = userEvent.setup();
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");
    const purchase = makePurchase();

    render(
      <StickyMobileAtc
        listing={listing}
        labels={labels}
        purchase={purchase}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    observerCallback?.(
      [
        {
          isIntersecting: false,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(await screen.findByTestId("pdp-sticky-mobile-atc")).toBeInTheDocument();
    expect(screen.getByTestId("pdp-sticky-qty-value")).toHaveTextContent("2");
    expect(screen.getByTestId("pdp-sticky-price")).toHaveTextContent(/K/);
    expect(screen.getByTestId("pdp-sticky-stock")).toHaveTextContent("In stock");

    await user.click(screen.getByTestId("pdp-sticky-qty-increase"));
    expect(purchase.increase).toHaveBeenCalled();

    await user.click(screen.getByTestId("pdp-sticky-add-to-cart"));
    expect(purchase.handleAddToCart).toHaveBeenCalled();
  });

  it("appends MOQ on the sticky stock line when required", async () => {
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");

    render(
      <StickyMobileAtc
        listing={{ ...listing, moq: 3 }}
        labels={labels}
        purchase={makePurchase()}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    observerCallback?.(
      [
        {
          isIntersecting: false,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(await screen.findByTestId("pdp-sticky-stock")).toHaveTextContent(
      "In stock · Minimum order: 3",
    );
  });

  /**
   * Regression: on one flex line the fixed-width qty stepper and CTA starved the
   * summary column — measured at 32px wide on a 360px viewport and 62px at 390px
   * — so `K249.00` (76px) spilled out of its box and painted over the decrement
   * control, and the stock line read "In s…". jsdom has no layout engine, so the
   * structural contract is asserted here and the widths are covered by the
   * measured browser evidence.
   */
  it("keeps the summary off the control line until there is room for both", async () => {
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");

    render(
      <StickyMobileAtc
        listing={listing}
        labels={labels}
        purchase={makePurchase()}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    observerCallback?.(
      [
        {
          isIntersecting: false,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    const bar = await screen.findByTestId("pdp-sticky-mobile-atc");
    const row = bar.firstElementChild as HTMLElement;

    // Stacked on phones, side by side only once the row can hold both.
    expect(row.className).toContain("flex-col");
    expect(row.className).toContain("sm:flex-row");

    // The price is clipped inside its own column, never painted over a control.
    expect(screen.getByTestId("pdp-sticky-price").className).toContain("truncate");

    // The stepper and the CTA still share one line.
    const controls = screen.getByTestId("pdp-sticky-qty-decrease").parentElement!.parentElement!;
    expect(controls).toContainElement(screen.getByTestId("pdp-sticky-add-to-cart"));
  });

  it("does not render when listing is out of stock", () => {
    const observeRef = createRef<HTMLElement | null>();
    observeRef.current = document.createElement("section");
    const purchase = makePurchase();

    render(
      <StickyMobileAtc
        listing={{ ...listing, inStock: false }}
        labels={labels}
        purchase={purchase}
        observeRef={observeRef}
        ariaLabel="Quick add to cart"
      />,
    );

    observerCallback?.(
      [
        {
          isIntersecting: false,
          target: observeRef.current!,
        } as unknown as IntersectionObserverEntry,
      ],
      {} as IntersectionObserver,
    );

    expect(screen.queryByTestId("pdp-sticky-mobile-atc")).not.toBeInTheDocument();
  });
});
