// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import type { CartLine, CartResponse, VendorGroup } from "./mini-cart-drawer";

/**
 * Cart page surface contract (Run #68 regression).
 *
 * `data-testid="cart-page"` was added when the Cart body was a single
 * unconditional render, then silently lost when that render was split into the
 * loading / load-error / empty / populated branches — every one of which
 * returns early. Run #68's failing screenshots showed a fully healthy, populated
 * Cart while `getByTestId("cart-page")` still found nothing, because the
 * attribute simply no longer existed anywhere in the tree.
 *
 * These tests assert the surface marker across ALL FOUR states, so a future
 * branch split cannot quietly drop it again. They deliberately assert the
 * canonical testid itself — not a weaker fallback selector.
 */

const storeState = {
  cart: null as CartResponse | null,
  notices: [] as never[],
  loading: true,
  loadError: false,
};

const refresh = vi.fn(async () => null);
const updateQty = vi.fn(async () => null);
const removeItem = vi.fn(async () => null);
const saveForLater = vi.fn(async () => null);

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("./mini-cart-drawer", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./mini-cart-drawer")>();
  return {
    ...actual,
    useCartStore: () => storeState,
    useCartActions: () => ({
      refresh,
      addItem: vi.fn(),
      updateQty,
      removeItem,
      saveForLater,
    }),
  };
});

const { CartPageView } = await import("./vendor-groups");

const cartMessages = checkoutMessages.cart;

const labels = {
  title: cartMessages.title,
  loading: cartMessages.loading,
  emptyTitle: cartMessages.emptyTitle,
  emptyBody: cartMessages.emptyBody,
  emptyTrust: {
    escrow: cartMessages.emptyTrustEscrow,
    delivery: cartMessages.emptyTrustDelivery,
    pickup: cartMessages.emptyTrustPickup,
  },
  browseCta: cartMessages.browseCta,
  itemCount: cartMessages.itemCount,
  subtotal: cartMessages.subtotal,
  total: cartMessages.total,
  checkoutCta: cartMessages.checkoutCta,
  updateError: cartMessages.updateError,
  loadErrorTitle: cartMessages.loadErrorTitle,
  loadErrorBody: cartMessages.loadErrorBody,
  loadErrorRetry: cartMessages.loadErrorRetry,
  multiSellerNote: cartMessages.multiSellerNote,
  escrowTeaser: cartMessages.escrowTeaser,
  escrowSteps: ["You pay", "Held by Convergeo", "Released"],
  stockUnavailableNotice: cartMessages.stockUnavailableNotice,
  summaryHeading: cartMessages.summaryHeading,
  vendor: {
    vendorGroup: cartMessages.vendorGroup,
    vendorSubtotal: cartMessages.vendorSubtotal,
    deliveryEligible: cartMessages.deliveryEligible,
    deliveryHint: cartMessages.deliveryHint,
    deliveryThreshold: cartMessages.deliveryThreshold,
    deliveryScopeNote: cartMessages.deliveryScopeNote,
    freeDeliveryProgress: cartMessages.freeDeliveryProgress,
    freeDeliveryUnlocked: cartMessages.freeDeliveryUnlocked,
    sellerIndex: cartMessages.sellerIndex,
  },
  line: {
    decrease: cartMessages.qtyDecrease,
    increase: cartMessages.qtyIncrease,
    value: cartMessages.qtyValue,
    updating: cartMessages.updating,
    decreaseSymbol: "-",
    increaseSymbol: "+",
    unitPrice: cartMessages.unitPrice,
    unitPriceMeasured: cartMessages.unitPriceMeasured,
    saleUnits: cartMessages.saleUnits,
    madeToOrderLeadTime: cartMessages.madeToOrderLeadTime,
    lineTotal: cartMessages.lineTotal,
    quotedPriceBadge: cartMessages.quotedPriceBadge,
    remove: cartMessages.remove,
    removeLabel: cartMessages.removeLabel,
    saveForLater: cartMessages.saveForLater,
    saveForLaterLabel: cartMessages.saveForLaterLabel,
    outOfStockLine: cartMessages.outOfStockLine,
  },
  notices: {
    title: cartMessages.noticesTitle,
    priceChanged: cartMessages.noticePriceChanged,
    outOfStock: cartMessages.noticeOutOfStock,
    qtyReduced: cartMessages.noticeQtyReduced,
  },
  miniCart: {
    title: cartMessages.title,
    close: cartMessages.close,
    viewCart: cartMessages.viewCart,
    checkout: cartMessages.checkoutCta,
    empty: cartMessages.emptyTitle,
    emptyBody: cartMessages.emptyBody,
    emptyTrust: {
      escrow: cartMessages.emptyTrustEscrow,
      delivery: cartMessages.emptyTrustDelivery,
      pickup: cartMessages.emptyTrustPickup,
    },
    browseCta: cartMessages.browseCta,
    subtotal: cartMessages.subtotal,
    vendorGroup: cartMessages.vendorGroup,
    loadError: cartMessages.loadErrorTitle,
    retry: cartMessages.loadErrorRetry,
    addedToCart: cartMessages.addedToCart,
    openCart: cartMessages.openCart,
  },
} as unknown as Parameters<typeof CartPageView>[0]["labels"];

const sampleLine: CartLine = {
  id: "line-1",
  listing_id: "listing-1",
  vendor_id: "vendor-a",
  qty: 2,
  unit_price_ngwee: 50_000,
  wholesale: false,
  line_total_ngwee: 100_000,
  title_override: "Sample phone",
};

const populatedGroup: VendorGroup = {
  vendor_id: "vendor-a",
  items: [sampleLine],
  subtotal_ngwee: 100_000,
  delivery_eligible: false,
};

const populatedCart: CartResponse = {
  cart_id: "cart-1",
  items: [sampleLine],
  vendor_groups: [populatedGroup],
  subtotal_ngwee: 100_000,
  conflicts: [],
};

const emptyCart: CartResponse = {
  cart_id: "cart-1",
  items: [],
  vendor_groups: [],
  subtotal_ngwee: 0,
  conflicts: [],
};

beforeEach(() => {
  storeState.cart = null;
  storeState.notices = [];
  storeState.loading = true;
  storeState.loadError = false;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("cart page surface contract", () => {
  it("marks the surface while the cart is still loading", () => {
    storeState.loading = true;
    storeState.cart = null;

    render(<CartPageView locale="en" labels={labels} />);

    expect(screen.getByTestId("cart-page")).toBeInTheDocument();
    // Proves we are genuinely in the loading branch, not a fallback render.
    expect(screen.getByTestId("cart-loading")).toBeInTheDocument();
  });

  it("marks the surface when the cart failed to load", () => {
    storeState.loading = false;
    storeState.loadError = true;
    storeState.cart = null;

    render(<CartPageView locale="en" labels={labels} />);

    expect(screen.getByTestId("cart-page")).toBeInTheDocument();
    expect(screen.getByTestId("cart-load-error")).toBeInTheDocument();
  });

  it("marks the surface when the cart is empty", () => {
    storeState.loading = false;
    storeState.cart = emptyCart;

    render(<CartPageView locale="en" labels={labels} />);

    expect(screen.getByTestId("cart-page")).toBeInTheDocument();
    expect(screen.getByTestId("cart-empty-state")).toBeInTheDocument();
  });

  it("marks the surface when the cart is populated (the Run #68 failure case)", () => {
    storeState.loading = false;
    storeState.cart = populatedCart;

    render(<CartPageView locale="en" labels={labels} />);

    expect(screen.getByTestId("cart-page")).toBeInTheDocument();
    // The exact surfaces Run #68's screenshots proved were rendering fine while
    // `cart-page` was missing — so this asserts the contract, not the feature.
    expect(screen.getByTestId("cart-order-summary")).toBeInTheDocument();
    expect(screen.getByTestId("cart-subtotal")).toBeInTheDocument();
    expect(screen.getByTestId("cart-checkout-cta")).toBeInTheDocument();
  });

  it("keeps exactly one cart-page marker per render", () => {
    storeState.loading = false;
    storeState.cart = populatedCart;

    render(<CartPageView locale="en" labels={labels} />);

    expect(screen.getAllByTestId("cart-page")).toHaveLength(1);
  });
});
