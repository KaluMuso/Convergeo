// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { PaymentRailChoice } from "./payment-rail-choice";

afterEach(() => {
  cleanup();
});

describe("PaymentRailChoice", () => {
  it("renders brand swatch and selects on click", async () => {
    const user = userEvent.setup();
    let selected: "mtn" | "airtel" = "mtn";

    render(
      <>
        <PaymentRailChoice
          name="momo-rail"
          rail="mtn"
          label="MTN Mobile Money"
          checked={selected === "mtn"}
          onChange={() => {
            selected = "mtn";
          }}
        />
        <PaymentRailChoice
          name="momo-rail"
          rail="airtel"
          label="Airtel Money"
          checked={selected === "airtel"}
          onChange={() => {
            selected = "airtel";
          }}
        />
      </>,
    );

    expect(screen.getByTestId("payment-rail-mtn")).toHaveAttribute("data-selected", "true");
    await user.click(screen.getByLabelText("Airtel Money"));
    expect(selected).toBe("airtel");
  });
});
