// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ordersMessages from "../../../../../../../packages/i18n/messages/en/orders.json";

import { BuyAgain, canBuyAgain, type BuyAgainLabels } from "./buy-again";

// A plain function (not vi.fn) so a rejected call is only ever handled by the component.
const api = vi.hoisted(() => {
  const calls: unknown[][] = [];
  const state: { impl: (path: string, init: unknown) => Promise<unknown> } = {
    impl: async () => undefined,
  };
  return {
    calls,
    state,
    request: (path: string, init: unknown) => {
      calls.push([path, init]);
      return state.impl(path, init);
    },
  };
});

vi.mock("@vergeo/config", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number) {
      super("api");
      this.status = status;
    }
  },
  createApiClient: () => ({ request: api.request }),
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "http://api.test",
}));

const b = ordersMessages.buyAgain;
const labels: BuyAgainLabels = {
  button: b.button,
  loading: b.loading,
  error: b.error,
  rateLimited: b.rateLimited,
  added: b.added,
  nothingAdded: b.nothingAdded,
  skippedTitle: b.skippedTitle,
  skippedReasons: b.skipped,
  priceChangeTitle: b.priceChangeTitle,
  priceChangeLine: b.priceChangeLine,
  goToCart: b.goToCart,
};

function renderIt(status = "delivered") {
  return render(
    <BuyAgain orderId="order-1" accessToken="tok" locale="en" status={status} labels={labels} />,
  );
}

describe("BuyAgain", () => {
  beforeEach(() => {
    api.calls.length = 0;
  });
  afterEach(cleanup);

  it("only offers buy again for delivered or completed orders", () => {
    expect(canBuyAgain("delivered")).toBe(true);
    expect(canBuyAgain("completed")).toBe(true);
    for (const status of ["placed", "confirmed", "shipped", "cancelled"]) {
      expect(canBuyAgain(status)).toBe(false);
    }
    renderIt("shipped");
    expect(screen.queryByTestId("buy-again-button")).not.toBeInTheDocument();
  });

  it("reports added, skipped and changed-price lines before checkout", async () => {
    api.state.impl = async () => ({
      order_id: "order-1",
      added: [{ listing_id: "l1", title: "Cable", qty: 2, unit_price_ngwee: 13_500 }],
      skipped: [{ listing_id: "l2", title: "Case", reason: "out_of_stock" }],
      price_changes: [
        {
          listing_id: "l1",
          title: "Cable",
          previous_unit_price_ngwee: 12_000,
          current_unit_price_ngwee: 13_500,
        },
      ],
    });
    renderIt();
    await userEvent.click(screen.getByTestId("buy-again-button"));

    await waitFor(() => expect(screen.getByTestId("buy-again-result")).toBeInTheDocument());
    expect(api.calls[0]?.[0]).toBe("/cart/reorder/order-1");
    expect(api.calls[0]?.[1]).toMatchObject({ method: "POST" });
    expect(screen.getByTestId("buy-again-price-changes")).toHaveTextContent(
      "Cable: was K120.00, now K135.00",
    );
    expect(screen.getByTestId("buy-again-skipped")).toHaveTextContent("Case");
    expect(screen.getByTestId("buy-again-skipped")).toHaveTextContent(b.skipped.out_of_stock);
    expect(screen.getByTestId("buy-again-go-to-cart")).toHaveAttribute("href", "/en/cart");
  });

  it("shows no price section when prices are unchanged", async () => {
    api.state.impl = async () => ({
      order_id: "order-1",
      added: [{ listing_id: "l1", title: "Cable", qty: 1, unit_price_ngwee: 12_000 }],
      skipped: [],
      price_changes: [],
    });
    renderIt("completed");
    await userEvent.click(screen.getByTestId("buy-again-button"));
    await waitFor(() => expect(screen.getByTestId("buy-again-result")).toBeInTheDocument());
    expect(screen.queryByTestId("buy-again-price-changes")).not.toBeInTheDocument();
    expect(screen.queryByTestId("buy-again-skipped")).not.toBeInTheDocument();
  });

  it("explains when nothing could be added and offers no cart link", async () => {
    api.state.impl = async () => ({
      order_id: "order-1",
      added: [],
      skipped: [{ listing_id: "l2", title: "Case", reason: "unavailable" }],
      price_changes: [],
    });
    renderIt();
    await userEvent.click(screen.getByTestId("buy-again-button"));
    await waitFor(() => expect(screen.getByText(b.nothingAdded)).toBeInTheDocument());
    expect(screen.queryByTestId("buy-again-go-to-cart")).not.toBeInTheDocument();
  });

  it("surfaces a failure and keeps the button usable", async () => {
    api.state.impl = async () => {
      throw new Error("boom");
    };
    renderIt();
    await userEvent.click(screen.getByTestId("buy-again-button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(b.error);
    expect(screen.getByTestId("buy-again-button")).toBeEnabled();
  });
});
