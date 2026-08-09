// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ordersMessages from "../../../../../../../../packages/i18n/messages/en/orders.json";

import {
  OrderPostDeliveryActions,
  shouldShowPostDeliveryActions,
} from "./order-post-delivery-actions";

afterEach(() => {
  cleanup();
});

const labels = {
  actionsTitle: ordersMessages.detail.actionsTitle,
  requestReturn: ordersMessages.detail.requestReturn,
  openDispute: ordersMessages.detail.openDispute,
};

describe("OrderPostDeliveryActions", () => {
  it("exposes return and dispute entry points for delivered orders", () => {
    render(
      <OrderPostDeliveryActions
        locale="en"
        orderId="order-123"
        status="delivered"
        labels={labels}
      />,
    );

    expect(screen.getByTestId("order-post-delivery-actions")).toBeInTheDocument();
    expect(screen.getByTestId("order-request-return")).toHaveAttribute(
      "href",
      "/en/account/orders/order-123/return",
    );
    expect(screen.getByTestId("order-open-dispute")).toHaveAttribute(
      "href",
      "/en/account/orders/order-123/dispute",
    );
    expect(screen.getByTestId("order-request-return")).toHaveClass("min-h-11");
  });

  it("hides actions before shipment", () => {
    const { container } = render(
      <OrderPostDeliveryActions
        locale="en"
        orderId="order-123"
        status="processing"
        labels={labels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(shouldShowPostDeliveryActions("processing")).toBe(false);
    expect(shouldShowPostDeliveryActions("shipped")).toBe(true);
  });
});
