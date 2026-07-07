// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TierPriceTable } from "./tier-price-table";

describe("TierPriceTable", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders tier rows with MOQ", () => {
    render(
      <TierPriceTable
        tiers={[
          { minQty: 10, ngwee: 50000 },
          { minQty: 50, ngwee: 45000 },
          { minQty: 100, ngwee: 40000 },
        ]}
        moq={10}
        quantityHeader="Quantity"
        priceHeader="Unit price"
        moqLabel="MOQ:"
      />,
    );

    expect(screen.getByTestId("tier-moq")).toHaveTextContent("MOQ:");
    expect(screen.getByTestId("tier-moq")).toHaveTextContent("10");
    expect(screen.getByTestId("tier-row-10")).toHaveTextContent("K500.00");
    expect(screen.getByTestId("tier-row-50")).toHaveTextContent("K450.00");
    expect(screen.getByTestId("tier-row-100")).toHaveTextContent("K400.00");
  });

  it("handles single-tier edge case", () => {
    render(
      <TierPriceTable
        tiers={[{ minQty: 1, ngwee: 99900 }]}
        moq={1}
        quantityHeader="Qty"
        priceHeader="Price"
        moqLabel="Minimum order:"
      />,
    );

    expect(screen.getAllByTestId(/^tier-row-/)).toHaveLength(1);
    expect(screen.getByTestId("tier-row-1")).toHaveTextContent("K999.00");
  });
});
