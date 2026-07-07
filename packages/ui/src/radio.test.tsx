// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { Radio } from "./radio";

describe("Radio", () => {
  it("renders as a radio input with label", () => {
    render(
      <Radio
        id="delivery-pickup"
        name="delivery"
        value="pickup"
        label="checkout.delivery.pickup"
      />,
    );

    const radio = screen.getByRole("radio", { name: "checkout.delivery.pickup" });
    expect(radio).toHaveAttribute("type", "radio");
    expect(radio).toHaveAttribute("name", "delivery");
  });
});
