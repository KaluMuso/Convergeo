/** @vitest-environment jsdom */
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CustomerTrustStrip } from "./customer-trust-strip";

describe("CustomerTrustStrip", () => {
  it("renders IconTile-backed trust items", () => {
    render(
      <CustomerTrustStrip
        ariaLabel="Trust cues"
        data-testid="trust-strip"
        items={[
          {
            id: "cod",
            label: "Pay on delivery",
            hue: "green",
            testId: "trust-cod",
            icon: <span aria-hidden>icon</span>,
          },
        ]}
      />,
    );

    expect(screen.getByTestId("trust-strip")).toBeInTheDocument();
    expect(screen.getByTestId("trust-cod")).toHaveTextContent("Pay on delivery");
  });
});
