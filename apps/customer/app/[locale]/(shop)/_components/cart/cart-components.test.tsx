// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";

import { ChangeNotices } from "./change-notices";
import { MiniCartEmptyState } from "./mini-cart-drawer";
import { QtyStepper } from "./qty-stepper";
import { CartEmptyState, VendorGroups, indexNoticesByListing } from "./vendor-groups";

import type { CartLine, CartResponse, ChangeNotice, VendorGroup } from "./mini-cart-drawer";

const lineLabels = {
  decrease: checkoutMessages.cart.qtyDecrease,
  increase: checkoutMessages.cart.qtyIncrease,
  value: checkoutMessages.cart.qtyValue,
  updating: checkoutMessages.cart.updating,
  decreaseSymbol: "-",
  increaseSymbol: "+",
  unitPrice: checkoutMessages.cart.unitPrice,
  lineTotal: checkoutMessages.cart.lineTotal,
  remove: checkoutMessages.cart.remove,
  removeLabel: checkoutMessages.cart.removeLabel,
  outOfStockLine: checkoutMessages.cart.outOfStockLine,
};

const vendorLabels = {
  vendorGroup: checkoutMessages.cart.vendorGroup,
  vendorSubtotal: checkoutMessages.cart.vendorSubtotal,
  deliveryEligible: checkoutMessages.cart.deliveryEligible,
  deliveryHint: checkoutMessages.cart.deliveryHint,
  deliveryThreshold: checkoutMessages.cart.deliveryThreshold,
  deliveryScopeNote: checkoutMessages.cart.deliveryScopeNote,
  freeDeliveryProgress: checkoutMessages.cart.freeDeliveryProgress,
  freeDeliveryUnlocked: checkoutMessages.cart.freeDeliveryUnlocked,
  sellerIndex: checkoutMessages.cart.sellerIndex,
};

const noticeLabels = {
  title: checkoutMessages.cart.noticesTitle,
  priceChanged: checkoutMessages.cart.noticePriceChanged,
  outOfStock: checkoutMessages.cart.noticeOutOfStock,
  qtyReduced: checkoutMessages.cart.noticeQtyReduced,
};

const emptyTrustLabels = {
  escrow: checkoutMessages.cart.emptyTrustEscrow,
  delivery: checkoutMessages.cart.emptyTrustDelivery,
  pickup: checkoutMessages.cart.emptyTrustPickup,
};

const sampleLine: CartLine = {
  id: "line-1",
  listing_id: "listing-1",
  vendor_id: "vendor-a",
  qty: +2,
  unit_price_ngwee: 50_000,
  wholesale: false,
  line_total_ngwee: 100_000,
  title_override: "Sample phone",
};

const belowThresholdGroup: VendorGroup = {
  vendor_id: "vendor-a",
  items: [sampleLine],
  subtotal_ngwee: 100_000,
  delivery_eligible: false,
};

const eligibleGroup: VendorGroup = {
  ...belowThresholdGroup,
  subtotal_ngwee: 250_000,
  delivery_eligible: true,
  items: [{ ...sampleLine, line_total_ngwee: 250_000, qty: 5, unit_price_ngwee: 50_000 }],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("checkout.cart i18n", () => {
  it("includes nested cart keys", () => {
    expect(checkoutMessages.cart.title).toBeTruthy();
    expect(checkoutMessages.cart.noticePriceChanged).toContain("{oldPrice}");
    expect(checkoutMessages.cart.freeDeliveryProgress).toContain("{threshold}");
    expect(checkoutMessages.cart.emptyTrustEscrow).toContain("Vergeo5");
    expect(checkoutMessages.cart.emptyTrustDelivery.toLowerCase()).toContain("lusaka");
    expect(checkoutMessages.cart.emptyTrustPickup.toLowerCase()).toContain("pickup");
  });

  it("keeps free-delivery copy Lusaka/zone honest (LB-P2-04)", () => {
    expect(checkoutMessages.cart.deliveryThreshold).toContain("{threshold}");
    expect(checkoutMessages.cart.deliveryThreshold.toLowerCase()).toContain("lusaka");
    expect(checkoutMessages.cart.deliveryScopeNote.toLowerCase()).toContain("lusaka");
    expect(checkoutMessages.cart.deliveryScopeNote.toLowerCase()).toMatch(/zone|pickup/);
    expect(checkoutMessages.cart.freeDeliveryUnlocked.toLowerCase()).toContain("qualifies");
    expect(checkoutMessages.cart.deliveryEligible.toLowerCase()).toContain("checkout");
  });
});

describe("ChangeNotices", () => {
  const notices: ChangeNotice[] = [
    {
      listing_id: "listing-1",
      kind: "price_changed",
      requested_qty: 2,
      available_qty: 5,
      snapshot_price_ngwee: 50_000,
      current_price_ngwee: 55_000,
    },
    {
      listing_id: "listing-2",
      kind: "out_of_stock",
      requested_qty: 1,
      available_qty: 0,
      snapshot_price_ngwee: 10_000,
      current_price_ngwee: 10_000,
    },
  ];

  it("renders price and stock change banners", () => {
    render(
      <ChangeNotices
        notices={notices}
        labels={noticeLabels}
        titleByListingId={{ "listing-1": "Phone", "listing-2": "Case" }}
      />,
    );

    expect(screen.getByTestId("cart-change-notices")).toBeInTheDocument();
    expect(screen.getByTestId("cart-notice-price_changed-listing-1")).toHaveTextContent("K500.00");
    expect(screen.getByTestId("cart-notice-out_of_stock-listing-2")).toHaveTextContent(
      checkoutMessages.cart.noticeOutOfStock,
    );
  });
});

describe("VendorGroups", () => {
  it("renders free-delivery progress nudge below threshold", () => {
    render(
      <VendorGroups
        groups={[belowThresholdGroup]}
        noticesByListingId={{}}
        labels={vendorLabels}
        lineLabels={lineLabels}
        onQtyChange={vi.fn().mockResolvedValue(undefined)}
        onRemove={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByTestId("cart-free-delivery-progress")).toBeInTheDocument();
    expect(screen.queryByTestId("cart-free-delivery-unlocked")).not.toBeInTheDocument();
  });

  it("shows unlocked free delivery when group is eligible", () => {
    render(
      <VendorGroups
        groups={[eligibleGroup]}
        noticesByListingId={{}}
        labels={vendorLabels}
        lineLabels={lineLabels}
        onQtyChange={vi.fn().mockResolvedValue(undefined)}
        onRemove={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByTestId("cart-free-delivery-unlocked")).toBeInTheDocument();
    expect(screen.getByTestId("cart-free-delivery-eligible")).toHaveTextContent(
      checkoutMessages.cart.deliveryEligible,
    );
    expect(screen.getByTestId("cart-delivery-scope-note")).toHaveTextContent(
      checkoutMessages.cart.deliveryScopeNote,
    );
  });

  it("always shows Lusaka/zone scope note on the delivery nudge (LB-P2-04)", () => {
    render(
      <VendorGroups
        groups={[belowThresholdGroup]}
        noticesByListingId={{}}
        labels={vendorLabels}
        lineLabels={lineLabels}
        onQtyChange={vi.fn().mockResolvedValue(undefined)}
        onRemove={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByTestId("cart-delivery-scope-note")).toBeInTheDocument();
    expect(screen.getByText(/Free Lusaka delivery from/i)).toBeInTheDocument();
  });

  it("marks out-of-stock lines from notices", () => {
    const notices: ChangeNotice[] = [
      {
        listing_id: "listing-1",
        kind: "out_of_stock",
        requested_qty: 2,
        available_qty: 0,
        snapshot_price_ngwee: 50_000,
        current_price_ngwee: 50_000,
      },
    ];

    render(
      <VendorGroups
        groups={[belowThresholdGroup]}
        noticesByListingId={indexNoticesByListing(notices)}
        labels={vendorLabels}
        lineLabels={lineLabels}
        onQtyChange={vi.fn().mockResolvedValue(undefined)}
        onRemove={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByTestId("cart-line-oos")).toHaveTextContent(
      checkoutMessages.cart.outOfStockLine,
    );
  });

  it("labels multi-seller groups with seller index", () => {
    const secondGroup: VendorGroup = {
      vendor_id: "vendor-b",
      items: [{ ...sampleLine, id: "line-2", listing_id: "listing-2", vendor_id: "vendor-b" }],
      subtotal_ngwee: 100_000,
      delivery_eligible: false,
    };

    render(
      <VendorGroups
        groups={[belowThresholdGroup, secondGroup]}
        noticesByListingId={{}}
        labels={vendorLabels}
        lineLabels={lineLabels}
        onQtyChange={vi.fn().mockResolvedValue(undefined)}
        onRemove={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByText("Seller 1 of 2")).toBeInTheDocument();
    expect(screen.getByText("Seller 2 of 2")).toBeInTheDocument();
  });
});

describe("cart presentation i18n", () => {
  it("includes load-error and multi-seller honesty keys", () => {
    expect(checkoutMessages.cart.loadErrorTitle).toBeTruthy();
    expect(checkoutMessages.cart.loadErrorRetry).toBeTruthy();
    expect(checkoutMessages.cart.multiSellerNote.toLowerCase()).toContain("different");
    expect(checkoutMessages.cart.escrowTeaser.toLowerCase()).toContain("holds");
    expect(checkoutMessages.cart.summaryHeading).toBeTruthy();
  });
});

describe("QtyStepper optimistic rollback", () => {
  it("rolls back quantity when the API rejects the update", async () => {
    const user = userEvent.setup();
    const onChange = vi
      .fn()
      .mockImplementationOnce(async (qty: number) => qty)
      .mockRejectedValueOnce(new Error("failed"));

    function Harness() {
      const [value, setValue] = useState(2);
      return (
        <QtyStepper
          value={value}
          min={1}
          max={9}
          labels={lineLabels}
          onChange={async (qty) => {
            await onChange(qty);
            setValue(qty);
          }}
        />
      );
    }

    render(<Harness />);

    const value = screen.getByTestId("cart-qty-stepper-value");
    expect(value).toHaveTextContent("2");

    await user.click(screen.getByTestId("cart-qty-stepper-increase"));
    await waitFor(() => expect(value).toHaveTextContent("3"));
    expect(onChange).toHaveBeenCalledWith(3);

    await user.click(screen.getByTestId("cart-qty-stepper-increase"));
    await waitFor(() => expect(value).toHaveTextContent("3"));
    expect(onChange).toHaveBeenCalledTimes(2);
  });
});

describe("empty cart render state", () => {
  it("renders the page empty state with trust cues and no emoji icon", () => {
    render(
      <CartEmptyState
        locale="en"
        labels={{
          emptyTitle: checkoutMessages.cart.emptyTitle,
          emptyBody: checkoutMessages.cart.emptyBody,
          emptyTrust: emptyTrustLabels,
          browseCta: checkoutMessages.cart.browseCta,
        }}
      />,
    );

    expect(screen.getByTestId("cart-empty-state")).toHaveTextContent(
      checkoutMessages.cart.emptyTitle,
    );
    expect(screen.getByTestId("cart-empty-trust-list")).toHaveTextContent(
      checkoutMessages.cart.emptyTrustEscrow,
    );
    expect(screen.getByTestId("cart-empty-panel")).not.toHaveTextContent("🛒");
    expect(screen.getByRole("link", { name: checkoutMessages.cart.browseCta })).toHaveAttribute(
      "href",
      "/en",
    );
  });

  it("renders mini-cart empty state with the same trust cues", () => {
    render(
      <MiniCartEmptyState
        locale="en"
        labels={{
          emptyTitle: checkoutMessages.cart.emptyTitle,
          emptyBody: checkoutMessages.cart.emptyBody,
          emptyTrust: emptyTrustLabels,
          browseCta: checkoutMessages.cart.browseCta,
        }}
      />,
    );

    expect(screen.getByTestId("mini-cart-empty")).toHaveTextContent(
      checkoutMessages.cart.emptyBody,
    );
    expect(screen.getByTestId("cart-empty-trust-list")).toHaveTextContent(
      checkoutMessages.cart.emptyTrustPickup,
    );
    expect(screen.getByRole("link", { name: checkoutMessages.cart.browseCta })).toHaveAttribute(
      "href",
      "/en",
    );
  });

  it("indexes notices by listing id", () => {
    const notices: ChangeNotice[] = [
      {
        listing_id: "listing-1",
        kind: "qty_reduced",
        requested_qty: 5,
        available_qty: 2,
        snapshot_price_ngwee: 10_000,
        current_price_ngwee: 10_000,
      },
    ];

    expect(indexNoticesByListing(notices)["listing-1"]?.kind).toBe("qty_reduced");
  });

  it("recognises an empty cart response", () => {
    const emptyCart: CartResponse = {
      cart_id: "cart-1",
      items: [],
      vendor_groups: [],
      subtotal_ngwee: 0,
      conflicts: [],
    };

    expect(emptyCart.items).toHaveLength(0);
  });
});
