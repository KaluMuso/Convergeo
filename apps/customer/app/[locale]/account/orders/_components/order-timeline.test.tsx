// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import orders from "../../../../../../../packages/i18n/messages/en/orders.json";

import { OrderTimeline } from "./order-timeline";

afterEach(cleanup);

const labels = {
  title: orders.timeline.title,
  steps: {
    placed: orders.timeline.placed,
    paymentCod: orders.timeline.paymentCod,
    confirmed: orders.timeline.confirmed,
    shipped: orders.timeline.shipped,
    delivered: orders.timeline.delivered,
  },
  escrow: { cod: orders.escrow.cod },
  explain: orders.timeline.explain,
  now: orders.timeline.now,
};

describe("OrderTimeline plain-language guidance", () => {
  it("explains only the current step and marks it as the current step", () => {
    render(
      <OrderTimeline
        labels={labels}
        timeline={[
          { step_key: "placed", state: "completed", occurred_at: null, escrow_copy_key: "none" },
          { step_key: "confirmed", state: "current", occurred_at: null, escrow_copy_key: "none" },
          { step_key: "shipped", state: "upcoming", occurred_at: null, escrow_copy_key: "none" },
        ]}
      />,
    );

    expect(screen.getByTestId("order-timeline-explain-confirmed")).toHaveTextContent(
      orders.timeline.explain.confirmed,
    );
    expect(screen.queryByText(orders.timeline.explain.placed)).not.toBeInTheDocument();
    expect(screen.queryByText(orders.timeline.explain.shipped)).not.toBeInTheDocument();
    expect(screen.getByText(orders.timeline.now)).toBeInTheDocument();
    expect(screen.getByText(orders.timeline.confirmed).closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
  });

  it("still renders without the optional guidance labels", () => {
    render(
      <OrderTimeline
        labels={{ title: labels.title, steps: labels.steps, escrow: labels.escrow }}
        timeline={[
          { step_key: "placed", state: "current", occurred_at: null, escrow_copy_key: "none" },
        ]}
      />,
    );
    expect(screen.getByText(orders.timeline.placed)).toBeInTheDocument();
    expect(screen.queryByText(orders.timeline.now)).not.toBeInTheDocument();
  });
});
