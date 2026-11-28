// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { OrderNextStepCard, OrderPaymentExplainer, OrderStatusTimeline } from "./order-guidance";

afterEach(() => {
  cleanup();
});

function wrap(node: React.ReactNode) {
  return render(
    <NextIntlClientProvider
      locale="en"
      messages={{ vendor: vendorMessages }}
      timeZone="Africa/Lusaka"
    >
      {node}
    </NextIntlClientProvider>,
  );
}

describe("order guidance", () => {
  it("tells the vendor what to do now on a new delivery order, with the cut-off", () => {
    wrap(
      <OrderNextStepCard
        locale="en"
        order={{ status: "placed", fulfilment: "delivery", cod: true, paid: false }}
      />,
    );
    const card = screen.getByTestId("vendor-order-next-step");
    expect(within(card).getByText("What to do now")).toBeInTheDocument();
    expect(within(card).getByText("Accept or reject this order")).toBeInTheDocument();
    expect(within(card).getByTestId("vendor-dispatch-cutoff")).toBeInTheDocument();
  });

  it("links pickup handover to the Scan page", () => {
    wrap(
      <OrderNextStepCard
        locale="en"
        order={{ status: "ready", fulfilment: "pickup", cod: false, paid: true }}
      />,
    );
    expect(screen.getByText("What happens next")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Scan to hand over" })).toHaveAttribute(
      "href",
      "/en/scan",
    );
    expect(screen.queryByTestId("vendor-dispatch-cutoff")).not.toBeInTheDocument();
  });

  it("explains COD: the customer pays the rider and Vergeo5 settles", () => {
    wrap(<OrderPaymentExplainer cod paid={false} />);
    expect(screen.getByText(/pays the rider in cash/)).toBeInTheDocument();
    expect(screen.getByText(/Vergeo5 settles the order money with you/)).toBeInTheDocument();
  });

  it("renders the full lifecycle with the current step marked", () => {
    wrap(
      <OrderStatusTimeline
        order={{
          status: "processing",
          fulfilment: "delivery",
          timeline: [{ to_status: "placed", note: null, created_at: "2026-11-13T07:00:00Z" }],
        }}
        statusLabel={(status) => status}
      />,
    );
    const items = within(screen.getByTestId("vendor-order-timeline")).getAllByRole("listitem");
    expect(items).toHaveLength(6);
    expect(items[2]).toHaveAttribute("aria-current", "step");
    expect(items[2]).toHaveAttribute("data-step-status", "processing");
    expect(items[5]).toHaveAttribute("data-step-state", "upcoming");
  });
});
