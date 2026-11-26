import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValueTrustStrip } from "./trust-strip";

describe("ValueTrustStrip", () => {
  it("renders only provided items", () => {
    render(
      <ValueTrustStrip
        ariaLabel="Trust"
        escrow="Held by Vergeo5"
        momoCod="Pay with Mobile Money (MTN or Airtel)"
      />,
    );
    expect(screen.getByTestId("value-trust-escrow")).toBeInTheDocument();
    expect(screen.getByTestId("value-trust-momo")).toBeInTheDocument();
    expect(screen.queryByTestId("value-trust-verified")).not.toBeInTheDocument();
    expect(screen.queryByTestId("value-trust-returns")).not.toBeInTheDocument();
  });

  it("renders nothing when no copy is passed", () => {
    const { container } = render(<ValueTrustStrip ariaLabel="Trust" />);
    expect(container.firstChild).toBeNull();
  });
});
