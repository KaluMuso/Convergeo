// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { PaymentRailChoice } from "./payment-rail-choice";

import type { MomoRail } from "./step-payment";

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
