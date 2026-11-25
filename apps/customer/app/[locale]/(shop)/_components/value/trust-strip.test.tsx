import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ValueTrustStrip } from "./trust-strip";

afterEach(() => {
  cleanup();
});

describe("ValueTrustStrip", () => {
  it("renders only provided trust lines", () => {
    render(<ValueTrustStrip ariaLabel="Trust" escrow="Held" verified="Verified" />);
    expect(screen.getByTestId("value-trust-escrow")).toHaveTextContent("Held");
    expect(screen.queryByTestId("value-trust-returns")).not.toBeInTheDocument();
  });

  it("returns null when every item is omitted", () => {
    const { container } = render(<ValueTrustStrip ariaLabel="Trust" />);
    expect(container).toBeEmptyDOMElement();
  });
});
