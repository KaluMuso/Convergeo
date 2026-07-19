// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BuyerTrustPanel } from "./buyer-trust-panel";

afterEach(() => {
  cleanup();
});

describe("BuyerTrustPanel", () => {
  it("renders seller status, escrow, and returns link without inventing fulfillment", () => {
    render(
      <BuyerTrustPanel
        sellerStatusLabel="Preferred seller — Cairo Road Fashions"
        returnsLabel="Returns & refunds"
        returnsHref="/en/legal/returns"
        escrowLabel="When online payment is available, Vergeo5 holds your money until delivery."
      />,
    );

    expect(screen.getByTestId("pdp-trust-seller")).toHaveTextContent("Preferred seller");
    expect(screen.getByTestId("pdp-trust-escrow")).toHaveTextContent("When online payment is available");
    expect(screen.getByTestId("pdp-trust-returns")).toHaveAttribute("href", "/en/legal/returns");
    expect(screen.queryByTestId("pdp-trust-delivery")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pdp-trust-pickup")).not.toBeInTheDocument();
  });

  it("shows delivery/pickup only when labels are provided", () => {
    render(
      <BuyerTrustPanel
        sellerStatusLabel="Sold by Demo Vendor"
        deliveryLabel="Delivery available for this seller"
        pickupLabel="Pickup available for this seller"
        returnsLabel="Returns & refunds"
        returnsHref="/en/legal/returns"
        escrowLabel="Escrow wording"
      />,
    );

    expect(screen.getByTestId("pdp-trust-delivery")).toHaveTextContent("Delivery available");
    expect(screen.getByTestId("pdp-trust-pickup")).toHaveTextContent("Pickup available");
  });
});
