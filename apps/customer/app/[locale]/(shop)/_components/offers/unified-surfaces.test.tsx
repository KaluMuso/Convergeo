// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";
import checkoutMessages from "../../../../../../../packages/i18n/messages/en/checkout.json";
import { getCartItemCount } from "../cart/cart-store";
import { TicketLinesGroup } from "../cart/vendor-groups";
import { mapFeedListing } from "../home-feed/feed-types";
import { SearchProductCard, type ResultsTabsLabels } from "../search/results-tabs";

import { buildOfferBadgeLabels } from "./offer-badge";

import type { CartResponse, CartTicketLine } from "../cart/mini-cart-drawer";

afterEach(cleanup);

const cart = checkoutMessages.cart;
const ticketLabels = {
  typeProducts: cart.types.products,
  typeEventTickets: cart.types.eventTickets,
  line: cart.tickets.line,
  remove: cart.tickets.remove,
  removeLabel: cart.tickets.removeLabel,
  unavailable: cart.tickets.unavailable,
  platformFee: cart.tickets.platformFee,
  prepaidOnly: cart.tickets.prepaidOnly,
};

const ticket: CartTicketLine = {
  id: "t1",
  item_type: "event_ticket",
  event_id: "e1",
  event_title: "Lusaka Jazz Night",
  ticket_type_id: "tt1",
  type_name: "VIP",
  instance_id: "i1",
  vendor_id: "v1",
  qty: 2,
  unit_price_ngwee: 15_050,
  line_total_ngwee: 20_167,
  list_line_total_ngwee: 30_100,
  offer_id: "o1",
};

const badgeLabels = buildOfferBadgeLabels((key) => {
  const [, , leaf] = key.split(".");
  return catalogMessages.offers.badge[leaf as keyof typeof catalogMessages.offers.badge];
});

describe("unified cart: event-ticket group", () => {
  it("labels the group as event tickets and shows each line with its offer price", () => {
    render(
      <TicketLinesGroup
        lines={[ticket]}
        unavailableIds={[]}
        labels={ticketLabels}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByTestId("cart-type-event-tickets")).toHaveTextContent("Event tickets");
    const line = screen.getByTestId("cart-ticket-line-t1");
    expect(line).toHaveTextContent("Lusaka Jazz Night");
    expect(line).toHaveTextContent("VIP × 2");
    expect(line).toHaveTextContent("K201.67");
    expect(line).toHaveTextContent("K301.00");
    expect(screen.getByTestId("cart-ticket-prepaid")).toHaveTextContent(/cash on delivery/i);
  });

  it("flags an unavailable line and removes a line by id", () => {
    const onRemove = vi.fn(async () => undefined);
    render(
      <TicketLinesGroup
        lines={[ticket]}
        unavailableIds={["t1"]}
        labels={ticketLabels}
        onRemove={onRemove}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/no longer be bought/i);
    fireEvent.click(screen.getByRole("button", { name: "Remove tickets for Lusaka Jazz Night" }));
    expect(onRemove).toHaveBeenCalledWith("t1");
  });

  it("renders nothing without ticket lines", () => {
    const { container } = render(
      <TicketLinesGroup lines={[]} unavailableIds={[]} labels={ticketLabels} onRemove={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("counts ticket lines in the cart badge", () => {
    const response = {
      cart_id: "c",
      items: [{ id: "p1" }],
      vendor_groups: [],
      subtotal_ngwee: 0,
      conflicts: [],
      ticket_lines: [ticket],
    } as unknown as CartResponse;
    expect(getCartItemCount(response)).toBe(2);
    expect(getCartItemCount({ ...response, ticket_lines: undefined })).toBe(1);
  });
});

describe("offer badges on new card surfaces (server-side data)", () => {
  it("maps the home feed / stream wire badge onto the listing card", () => {
    const listing = mapFeedListing({
      id: "l1",
      title: "Kettle",
      product_slug: "kettle",
      vendor_name: "Shop",
      price_ngwee: 10_000,
      condition: "new",
      in_stock: true,
      image_public_id: null,
      rating: 0,
      review_count: 0,
      distance_m: null,
      offer_badge: { offer_id: "o", offer_type: "buy_n_pay_m", buy_n: 3, pay_m: 2 },
    });
    expect(listing.offerBadge?.offer_id).toBe("o");
    const plain = mapFeedListing({
      id: "l2",
      title: "Pan",
      product_slug: null,
      vendor_name: "Shop",
      price_ngwee: 5_000,
      condition: "new",
      in_stock: true,
      image_public_id: null,
      rating: 0,
      review_count: 0,
      distance_m: null,
    });
    expect(plain.offerBadge).toBeUndefined();
  });

  it("shows the offer pill on a search product card", () => {
    const labels = {
      count: "{count}",
      marketplaceListing: "Marketplace listing",
      wishlist: "Add to wishlist",
      wishlistRemove: "Remove from wishlist",
      mediaEmpty: "No image",
      noReviews: "No reviews yet",
      reviewCount: "({count})",
      offerBadge: badgeLabels,
    } as unknown as ResultsTabsLabels;
    render(
      <SearchProductCard
        hit={{
          id: "sd-1",
          entity_kind: "product",
          entity_id: "p1",
          title: "Kettle",
          body: null,
          category_path: null,
          price_min_ngwee: 10_000,
          price_max_ngwee: 10_000,
          lat: null,
          lng: null,
          locale_terms: null,
          boost_signals: {},
          rrf_score: 1,
          slug: "kettle",
          offer_badge: { offer_id: "o", offer_type: "bxgy", buy_qty: 2, get_qty: 1 },
        }}
        locale="en"
        labels={labels}
      />,
    );
    expect(screen.getByText("Buy 2 get 1 free")).toBeInTheDocument();
  });
});
