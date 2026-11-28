// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BuyerTrustPanel } from "./buyer-trust-panel";

afterEach(() => {
  cleanup();
});

const pillLabels = {
  delivery: "Lusaka delivery",
  pickup: "Pickup available",
};

describe("BuyerTrustPanel", () => {
  it("renders seller status, escrow, and returns link without inventing fulfillment", () => {
    render(
      <BuyerTrustPanel
        sellerStatusLabel="Preferred seller — Cairo Road Fashions"
        logisticsPillLabels={pillLabels}
        returnsLabel="Returns & refunds"
        returnsHref="/en/legal/returns"
        escrowLabel="When online payment is available, Vergeo5 holds your money until delivery."
      />,
    );

    expect(screen.getByTestId("pdp-trust-seller")).toHaveTextContent("Preferred seller");
    expect(screen.getByTestId("pdp-trust-escrow")).toHaveTextContent(
      "When online payment is available",
    );
    expect(screen.getByTestId("pdp-trust-returns")).toHaveAttribute("href", "/en/legal/returns");
    expect(screen.queryByTestId("pdp-trust-logistics")).not.toBeInTheDocument();
  });

  it("shows delivery/pickup pills only when fulfillment is available", () => {
    render(
      <BuyerTrustPanel
        sellerStatusLabel="Sold by Demo Vendor"
        deliveryAvailable
        pickupAvailable
        logisticsPillLabels={pillLabels}
        returnsLabel="Returns & refunds"
        returnsHref="/en/legal/returns"
        escrowLabel="Escrow wording"
      />,
    );

    expect(screen.getByTestId("pdp-trust-logistics")).toBeInTheDocument();
    expect(screen.getByText("Lusaka delivery")).toBeInTheDocument();
    expect(screen.getByText("Pickup available")).toBeInTheDocument();
  });
});
