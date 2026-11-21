// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { CourierStatusCard, type VendorCourierDispatch } from "./courier-status";

afterEach(() => {
  cleanup();
});

function renderCard(dispatch: VendorCourierDispatch) {
  return render(
    <NextIntlClientProvider locale="en" messages={{ vendor: vendorMessages }}>
      <CourierStatusCard dispatch={dispatch} />
    </NextIntlClientProvider>,
  );
}

const base: VendorCourierDispatch = {
  status: "accepted",
  courier_name: "TownStar",
  courier_reference: "TS-1042",
  cod_amount_ngwee: 105_050,
  timeline: [
    { status: "accepted", at: "2026-11-09T08:20:00.000Z" },
    { status: "requested", at: "2026-11-09T08:00:00.000Z" },
  ],
};

describe("CourierStatusCard", () => {
  it("shows the assigned courier, status and COD amount", () => {
    renderCard(base);
    expect(screen.getByText("TownStar")).toBeInTheDocument();
    expect(screen.getByTestId("vendor-courier-status")).toHaveAttribute("data-status", "accepted");
    expect(screen.getByText("Courier reference: TS-1042")).toBeInTheDocument();
    expect(
      screen.getByText("The rider collects K1,050.50 cash from the buyer"),
    ).toBeInTheDocument();
  });

  it("lists timeline steps oldest first and never shows a handover code", () => {
    renderCard(base);
    const steps = screen
      .getAllByRole("listitem")
      .map((item) => item.querySelector("span")?.textContent);
    expect(steps).toEqual(["Looking for a rider", "Rider found"]);
    expect(screen.queryByText(/^[0-9]{6}$/)).not.toBeInTheDocument();
  });
});
