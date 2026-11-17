// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";
import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";
import { VendorGroups } from "../cart/vendor-groups";

import { offerBadgeLabel } from "./offer-badge";

import type { VendorGroup } from "../cart/mini-cart-drawer";

afterEach(cleanup);

const badgeLabels = catalogMessages.offers.badge;

describe("offerBadgeLabel", () => {
  it("renders each offer type", () => {
    expect(
      offerBadgeLabel(
        { offer_id: "o", offer_type: "bxgy", buy_qty: 2, get_qty: 1 },
        badgeLabels,
      ),
    ).toBe("Buy 2 get 1 free");
    expect(
      offerBadgeLabel(
        {
          offer_id: "o",
          offer_type: "bundle",
          bundle_pricing: "addon_percent_off",
          addon_percent_off: 75,
        },
        badgeLabels,
      ),
    ).toBe("-75% add-ons");
    expect(
      offerBadgeLabel(
        { offer_id: "o", offer_type: "bundle", bundle_pricing: "fixed_price" },
        badgeLabels,
      ),
    ).toBe("Bundle deal");
    expect(
      offerBadgeLabel(
        { offer_id: "o", offer_type: "buy_n_pay_m", buy_n: 3, pay_m: 2 },
        badgeLabels,
      ),
    ).toBe("3 for 2");
    expect(
      offerBadgeLabel({ offer_id: "o", offer_type: "free_gift" }, badgeLabels),
    ).toBe("Free gift");
    expect(
      offerBadgeLabel({ offer_id: "o", offer_type: "unknown" }, badgeLabels),
    ).toBeNull();
  });
});

describe("cart shows offer discounts and free gifts", () => {
  const cart = checkoutMessages.cart;
  const group: VendorGroup = {
    vendor_id: "vendor-a",
    vendor_name: "Shop A",
    subtotal_ngwee: 2_000,
    delivery_eligible: false,
    savings_ngwee: 1_000,
    items: [
      {
        id: "c1",
        listing_id: "l1",
        vendor_id: "vendor-a",
        qty: 3,
        unit_price_ngwee: 1_000,
        wholesale: false,
        line_total_ngwee: 2_000,
        list_line_total_ngwee: 3_000,
        offer_id: "offer-1",
        title_override: "Soap",
      },
    ],
    gifts: [
      {
        offer_id: "offer-2",
        listing_id: "gift-1",
        qty: 1,
        title: "Tote",
        reference_unit_price_ngwee: 2_500,
      },
    ],
  };

  it("strikes the list total, shows the saving and the free gift at K0", () => {
    render(
      <VendorGroups
        groups={[group]}
        noticesByListingId={{}}
        labels={{
          vendorGroup: cart.vendorGroup,
          vendorSubtotal: cart.vendorSubtotal,
          deliveryEligible: cart.deliveryEligible,
          deliveryHint: cart.deliveryHint,
          deliveryThreshold: cart.deliveryThreshold,
          deliveryScopeNote: cart.deliveryScopeNote,
          freeDeliveryProgress: cart.freeDeliveryProgress,
          freeDeliveryUnlocked: cart.freeDeliveryUnlocked,
          offerGift: cart.offerGift,
          offerGiftWorth: cart.offerGiftWorth,
        }}
        lineLabels={{
          decrease: cart.qtyDecrease,
          increase: cart.qtyIncrease,
          value: cart.qtyValue,
          updating: cart.updating,
          decreaseSymbol: "-",
          increaseSymbol: "+",
          unitPrice: cart.unitPrice,
          unitPriceMeasured: cart.unitPriceMeasured,
          saleUnits: cart.saleUnits,
          madeToOrderLeadTime: cart.madeToOrderLeadTime,
          lineTotal: cart.lineTotal,
          quotedPriceBadge: cart.quotedPriceBadge,
          remove: cart.remove,
          removeLabel: cart.removeLabel,
          saveForLater: cart.saveForLater,
          saveForLaterLabel: cart.saveForLaterLabel,
          outOfStockLine: cart.outOfStockLine,
          offerSaving: cart.offerSaving,
        }}
        onQtyChange={async () => {}}
        onRemove={async () => {}}
      />,
    );
    expect(screen.getByTestId("cart-line-list-l1")).toHaveTextContent("K30.00");
    expect(screen.getByTestId("cart-line-offer-saving-l1")).toHaveTextContent(
      "K10.00",
    );
    const gift = screen.getByTestId("cart-offer-gift-gift-1");
    expect(gift).toHaveTextContent("Free gift: Tote × 1");
    expect(gift).toHaveTextContent("K25.00");
    expect(gift).toHaveTextContent("K0.00");
  });
});
