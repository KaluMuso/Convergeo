// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import orders from "../../../../../../../packages/i18n/messages/en/orders.json";

import { OrderTimeline } from "./order-timeline";

import type { TimelineStep } from "./orders-api";

afterEach(cleanup);

const strip = orders.escrow.strip;
const step = (
  step_key: TimelineStep["step_key"],
  state: TimelineStep["state"],
  escrow_copy_key: TimelineStep["escrow_copy_key"],
): TimelineStep => ({ step_key, state, occurred_at: null, escrow_copy_key });

const labels = {
  title: orders.timeline.title,
  steps: {
    placed: orders.timeline.placed,
    paymentHeld: orders.timeline.paymentHeld,
    paymentCod: orders.timeline.paymentCod,
    confirmed: orders.timeline.confirmed,
    shipped: orders.timeline.shipped,
    completed: orders.timeline.completed,
    refunded: orders.timeline.refunded,
  },
  escrow: {
    cod: orders.escrow.cod,
    held: orders.escrow.held,
    released: orders.escrow.released,
    refunded: orders.escrow.refunded,
    strip,
  },
  explain: orders.timeline.explain,
  now: orders.timeline.now,
};

function renderTimeline(timeline: TimelineStep[], paymentMode: "cod" | "prepaid" = "prepaid") {
  return render(<OrderTimeline labels={labels} paymentMode={paymentMode} timeline={timeline} />);
}

describe("OrderTimeline plain-language guidance", () => {
  it("explains only the current step and marks it as the current step", () => {
    renderTimeline([
      step("placed", "completed", "none"),
      step("confirmed", "current", "none"),
      step("shipped", "upcoming", "none"),
    ]);

    expect(screen.getByTestId("order-timeline-explain-confirmed")).toHaveTextContent(
      orders.timeline.explain.confirmed,
    );
    expect(screen.queryByText(orders.timeline.explain.placed)).not.toBeInTheDocument();
    expect(screen.getByText(orders.timeline.confirmed).closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
  });

  it("still renders without the optional guidance labels", () => {
    render(
      <OrderTimeline
        labels={{ title: labels.title, steps: labels.steps, escrow: labels.escrow }}
        paymentMode="prepaid"
        timeline={[step("placed", "current", "none")]}
      />,
    );
    expect(screen.getByText(orders.timeline.placed)).toBeInTheDocument();
    expect(screen.queryByText(orders.timeline.now)).not.toBeInTheDocument();
  });
});

describe("OrderTimeline escrow trust strip", () => {
  const heldTimeline = [
    step("placed", "completed", "none"),
    step("payment_held", "completed", "held"),
    step("confirmed", "current", "none"),
  ];
  const releasedTimeline = [...heldTimeline.slice(0, 2), step("completed", "current", "released")];

  it("marks held and released as the active strip step for prepaid orders", () => {
    renderTimeline(heldTimeline);
    const escrowStrip = screen.getByTestId("order-escrow-strip");
    expect(within(escrowStrip).getByText(strip.held).closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.queryByText(orders.escrow.held)).not.toBeInTheDocument();

    cleanup();
    renderTimeline(releasedTimeline);
    const releasedStrip = screen.getByTestId("order-escrow-strip");
    expect(within(releasedStrip).getByText(strip.released).closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.queryByText(orders.escrow.released)).not.toBeInTheDocument();
  });

  it("hides the strip for refunded and COD orders", () => {
    renderTimeline([...heldTimeline, step("refunded", "current", "refunded")]);
    expect(screen.queryByTestId("order-escrow-strip")).not.toBeInTheDocument();
    expect(screen.getByText(orders.escrow.refunded)).toBeInTheDocument();

    cleanup();
    renderTimeline(
      [
        step("placed", "completed", "none"),
        step("payment_cod", "completed", "cod"),
        step("confirmed", "current", "none"),
      ],
      "cod",
    );
    expect(screen.queryByTestId("order-escrow-strip")).not.toBeInTheDocument();
    expect(screen.getByText(orders.escrow.cod)).toBeInTheDocument();
  });
});
