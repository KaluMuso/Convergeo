// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, useState } from "vitest";

import type { MomoRail } from "./step-payment";
import { PaymentRailChoice } from "./payment-rail-choice";

afterEach(() => {
  cleanup();
});

function RailHarness() {
  const [selected, setSelected] = useState<MomoRail>("mtn");

  return (
    <>
      <PaymentRailChoice
        name="momo-rail"
        rail="mtn"
        label="MTN Mobile Money"
        checked={selected === "mtn"}
        onChange={() => {
          setSelected("mtn");
        }}
      />
      <PaymentRailChoice
        name="momo-rail"
        rail="airtel"
        label="Airtel Money"
        checked={selected === "airtel"}
        onChange={() => {
          setSelected("airtel");
        }}
      />
      <span data-testid="selected-rail">{selected}</span>
    </>
  );
}

describe("PaymentRailChoice", () => {
  it("renders brand swatch and selects on click", async () => {
    const user = userEvent.setup();

    render(<RailHarness />);

    expect(screen.getByTestId("payment-rail-mtn")).toHaveAttribute("data-selected", "true");
    await user.click(screen.getByLabelText("Airtel Money"));
    expect(screen.getByTestId("selected-rail")).toHaveTextContent("airtel");
  });
});
