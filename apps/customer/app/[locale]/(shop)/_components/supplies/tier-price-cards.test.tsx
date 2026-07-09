// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { MoqBadge } from "./moq-badge";
import {
  lineTotalNgwee,
  normalizeTiers,
  QtyPricePreview,
  selectUnitPriceNgwee,
} from "./qty-price-preview";
import {
  filterWholesaleListings,
  sortSupplyListings,
  TierPriceCards,
  type SupplyListing,
} from "./tier-price-cards";

afterEach(() => {
  cleanup();
});

const tiers = [
  { min_qty: 1, price_ngwee: 8_500 },
  { min_qty: 10, price_ngwee: 8_000 },
  { min_qty: 50, price_ngwee: 7_500 },
];

const normalizedTiers = normalizeTiers(tiers, 8_500);

const wholesaleListing: SupplyListing = {
  id: "listing-wholesale",
  title: "Bulk Flour 50kg",
  productSlug: "bulk-flour-50kg",
  vendorName: "Lusaka Mills",
  priceNgwee: 8_500,
  wholesale: true,
  moq: 10,
  priceTiers: tiers,
  imagePublicId: null,
};

const retailListing: SupplyListing = {
  ...wholesaleListing,
  id: "listing-retail",
  wholesale: false,
};

const cardLabels = {
  vendor: "Sold by {vendor}",
  quantityLabel: "Preview quantity",
  decrease: "Decrease quantity",
  increase: "Increase quantity",
  decreaseSymbol: "−",
  increaseSymbol: "+",
  noImage: "No image",
  viewListing: "View listing",
  tierQuantityHeader: "Qty",
  tierPriceHeader: "Unit price",
  moqBadge: "MOQ {qty}",
  moqTableLabel: "MOQ:",
  previewLine: "{qty} × {unitPrice} = {total}",
};

describe("tier price selection at boundary qtys", () => {
  it("uses base tier at minimum qty", () => {
    expect(selectUnitPriceNgwee(8_500, true, 1, normalizedTiers)).toBe(8_500);
    expect(lineTotalNgwee(1, 8_500)).toBe(8_500);
  });

  it("uses middle tier between breakpoints", () => {
    expect(selectUnitPriceNgwee(8_500, true, 12, normalizedTiers)).toBe(8_000);
    expect(lineTotalNgwee(12, 8_000)).toBe(96_000);
  });

  it("uses highest tier at huge qty", () => {
    expect(selectUnitPriceNgwee(8_500, true, 120, normalizedTiers)).toBe(7_500);
    expect(lineTotalNgwee(120, 7_500)).toBe(900_000);
  });

  it("renders exact ngwee preview at boundary qty 120", () => {
    const unit = selectUnitPriceNgwee(8_500, true, 120, normalizedTiers);
    render(
      <QtyPricePreview qty={120} unitPriceNgwee={unit} lineTemplate={cardLabels.previewLine} />,
    );

    expect(screen.getByTestId("supplies-qty-preview")).toHaveTextContent(
      "120 × K75.00 = K9,000.00",
    );
  });
});

describe("wholesale-only filtering", () => {
  it("excludes non-wholesale listings", () => {
    expect(filterWholesaleListings([wholesaleListing, retailListing])).toEqual([wholesaleListing]);
  });

  it("never renders retail cards in the grid", () => {
    render(
      <TierPriceCards
        locale="en"
        listings={[wholesaleListing, retailListing]}
        labels={cardLabels}
      />,
    );

    expect(screen.getByTestId("supply-card-listing-wholesale")).toBeInTheDocument();
    expect(screen.queryByTestId("supply-card-listing-retail")).not.toBeInTheDocument();
  });
});

describe("MOQ badge and qty preview render", () => {
  it("shows MOQ badge", () => {
    render(<MoqBadge moq={10} label="MOQ {qty}" />);
    expect(screen.getByTestId("supplies-moq-badge")).toHaveTextContent("MOQ 10");
  });

  it("updates preview when quantity changes", async () => {
    const user = userEvent.setup();
    render(
      <TierPriceCards
        locale="en"
        listings={[wholesaleListing]}
        labels={cardLabels}
        previewQty={10}
      />,
    );

    expect(screen.getByTestId("supplies-qty-preview")).toHaveTextContent("10 × K80.00 = K800.00");

    await user.click(screen.getByLabelText("Increase quantity"));
    expect(screen.getByTestId("supplies-qty-preview")).toHaveTextContent("11 × K80.00 = K880.00");
  });
});

describe("business sort", () => {
  it("sorts by MOQ ascending", () => {
    const highMoq: SupplyListing = { ...wholesaleListing, id: "high", moq: 50 };
    const lowMoq: SupplyListing = { ...wholesaleListing, id: "low", moq: 5 };
    expect(sortSupplyListings([highMoq, lowMoq], "moq").map((item) => item.id)).toEqual([
      "low",
      "high",
    ]);
  });
});
