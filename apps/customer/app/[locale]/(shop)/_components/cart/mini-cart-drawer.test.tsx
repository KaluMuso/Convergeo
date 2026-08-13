// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import {
  CartNavTrigger,
  MiniCartDrawer,
  closeMiniCart,
  openMiniCart,
  setLastAddedMessage,
  setStoreStateForTests,
} from "./mini-cart-drawer";

vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: vi.fn(async () => ({
    auth: { getSession: async () => ({ data: { session: null } }) },
  })),
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "http://localhost:8000",
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const labels = {
  title: checkoutMessages.cart.miniCartTitle,
  close: checkoutMessages.cart.miniCartClose,
  itemCount: checkoutMessages.cart.itemCount,
  subtotal: checkoutMessages.cart.subtotal,
  total: checkoutMessages.cart.total,
  viewCart: checkoutMessages.cart.viewCart,
  checkoutCta: checkoutMessages.cart.checkoutCta,
  emptyTitle: checkoutMessages.cart.emptyTitle,
  emptyBody: checkoutMessages.cart.emptyBody,
  emptyTrust: {
    escrow: checkoutMessages.cart.emptyTrustEscrow,
    delivery: checkoutMessages.cart.emptyTrustDelivery,
    pickup: checkoutMessages.cart.emptyTrustPickup,
  },
  browseCta: checkoutMessages.cart.browseCta,
  openCart: checkoutMessages.cart.openCart,
  loadErrorTitle: checkoutMessages.cart.loadErrorTitle,
  loadErrorBody: checkoutMessages.cart.loadErrorBody,
  loadErrorRetry: checkoutMessages.cart.loadErrorRetry,
  quantityValue: checkoutMessages.cart.qtyValue,
  saleUnits: checkoutMessages.cart.saleUnits,
  madeToOrderLeadTime: checkoutMessages.cart.madeToOrderLeadTime,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        cart_id: "cart-1",
        items: [],
        vendor_groups: [],
        subtotal_ngwee: 0,
        conflicts: [],
      }),
    ),
  );
  setStoreStateForTests({
    cart: null,
    notices: [],
    loading: false,
    loadError: false,
    drawerOpen: false,
    lastAddedMessage: null,
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  closeMiniCart();
});

describe("MiniCartDrawer a11y", () => {
  it("exposes dialog semantics, close control, and live region for ATC", async () => {
    const user = userEvent.setup();
    setLastAddedMessage("Added to cart");
    openMiniCart();

    render(<MiniCartDrawer locale="en" labels={labels} />);

    expect(screen.getByTestId("mini-cart-live")).toHaveTextContent("Added to cart");
    expect(screen.getByRole("dialog", { name: labels.title })).toBeInTheDocument();
    const close = screen.getByTestId("mini-cart-close");
    expect(close).toHaveClass("min-h-11");
    await user.click(close);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not claim empty when cart load failed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );
    openMiniCart();

    render(<MiniCartDrawer locale="en" labels={labels} />);

    expect(await screen.findByTestId("mini-cart-load-error")).toBeInTheDocument();
    expect(screen.queryByTestId("mini-cart-empty")).not.toBeInTheDocument();
  });

  it("CartNavTrigger opens the drawer with a 44px target", async () => {
    const user = userEvent.setup();
    render(
      <>
        <CartNavTrigger labels={{ openCart: labels.openCart }} cartIcon={<span>Cart</span>} />
        <MiniCartDrawer locale="en" labels={labels} />
      </>,
    );

    const trigger = screen.getByTestId("cart-nav-trigger");
    expect(trigger).toHaveClass("min-h-11");
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: labels.title })).toBeInTheDocument();
  });

  it("shows made-to-order lead time in the cart summary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          cart_id: "cart-1",
          items: [
            {
              id: "line-1",
              listing_id: "listing-1",
              vendor_id: "vendor-1",
              qty: 1,
              unit_price_ngwee: 50_000,
              wholesale: false,
              line_total_ngwee: 50_000,
              title_override: "Custom table",
              fulfilment_mode: "made_to_order",
              lead_time_days: 10,
            },
          ],
          vendor_groups: [],
          subtotal_ngwee: 50_000,
          conflicts: [],
        }),
      ),
    );
    openMiniCart();

    render(<MiniCartDrawer locale="en" labels={labels} />);

    expect(await screen.findByTestId("mini-cart-lead-time-listing-1")).toHaveTextContent(
      "Made to order · ready in 10 days",
    );
  });
});
