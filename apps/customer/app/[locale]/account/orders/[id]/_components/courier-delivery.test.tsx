// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CourierDeliveryBlock, type CourierDeliveryLabels } from "./courier-delivery";

import type { CourierDelivery } from "../../_components/orders-api";

afterEach(() => {
  cleanup();
});

const labels: CourierDeliveryLabels = {
  title: "Courier delivery",
  courier: "Courier",
  reference: "Courier reference",
  statuses: {
    requested: "Courier requested",
    accepted: "Courier assigned",
    picked_up: "On the way to you",
    delivered: "Delivered",
    failed: "Delivery attempt failed",
    cancelled: "Courier cancelled",
  },
  codDue: (amount) => `Pay the rider ${amount} in cash`,
  handoverTitle: "Your handover code",
  handoverBody: "Give this code to the rider only once you have your items.",
  handoverAria: (code) => `Handover code ${code}`,
  failedBody: "We will arrange another delivery.",
};

function delivery(overrides: Partial<CourierDelivery> = {}): CourierDelivery {
  return {
    status: "picked_up",
    courier_name: "TownStar",
    courier_reference: "TS-1042",
    cod_amount_ngwee: 105_050,
    timeline: [
      { status: "picked_up", at: "2026-11-09T09:30:00.000Z" },
      { status: "requested", at: "2026-11-09T08:00:00.000Z" },
      { status: "accepted", at: "2026-11-09T08:20:00.000Z" },
    ],
    handover_code: "004211",
    ...overrides,
  };
}

describe("CourierDeliveryBlock", () => {
  it("renders the courier status timeline in chronological order", () => {
    render(<CourierDeliveryBlock delivery={delivery()} labels={labels} />);
    const timeline = screen.getByRole("list", { name: "Courier delivery" });
    const items = within(timeline).getAllByRole("listitem");
    expect(items.map((item) => item.querySelector("p")?.textContent)).toEqual([
      "Courier requested",
      "Courier assigned",
      "On the way to you",
    ]);
    expect(screen.getByText("TownStar")).toBeInTheDocument();
    expect(screen.getByText("TS-1042")).toBeInTheDocument();
  });

  it("shows the handover code while the courier is on the way", () => {
    render(<CourierDeliveryBlock delivery={delivery()} labels={labels} />);
    expect(screen.getByLabelText("Handover code 004211")).toHaveTextContent("004211");
    expect(screen.getByText("Your handover code")).toBeInTheDocument();
  });

  it("shows the COD amount via formatK from integer ngwee", () => {
    render(<CourierDeliveryBlock delivery={delivery()} labels={labels} />);
    expect(screen.getByText("Pay the rider K1,050.50 in cash")).toBeInTheDocument();
  });

  it("hides the COD line for prepaid deliveries", () => {
    render(<CourierDeliveryBlock delivery={delivery({ cod_amount_ngwee: 0 })} labels={labels} />);
    expect(screen.queryByText(/Pay the rider/)).not.toBeInTheDocument();
  });

  it("never renders a code once the dispatch is closed", () => {
    render(
      <CourierDeliveryBlock
        delivery={delivery({
          status: "delivered",
          timeline: [
            { status: "requested", at: "2026-11-09T08:00:00.000Z" },
            { status: "delivered", at: "2026-11-09T10:00:00.000Z" },
          ],
        })}
        labels={labels}
      />,
    );
    expect(screen.queryByTestId("handover-code")).not.toBeInTheDocument();
    expect(screen.queryByText("004211")).not.toBeInTheDocument();
    expect(screen.queryByText(/Pay the rider/)).not.toBeInTheDocument();
    expect(screen.getByText("Delivered")).toBeInTheDocument();
  });

  it("explains a failed attempt without a code", () => {
    render(
      <CourierDeliveryBlock
        delivery={delivery({ status: "failed", handover_code: null })}
        labels={labels}
      />,
    );
    expect(screen.getByText("We will arrange another delivery.")).toBeInTheDocument();
    expect(screen.queryByTestId("handover-code")).not.toBeInTheDocument();
  });
});
