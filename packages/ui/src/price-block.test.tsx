// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PriceBlock } from "./price-block";

describe("PriceBlock", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders integer ngwee as K1,234.56", () => {
    render(<PriceBlock ngwee={123456} />);
    expect(screen.getByTestId("price-block")).toHaveTextContent("K1,234.56");
  });

  it("throws on non-integer ngwee in test env", () => {
    expect(() => render(<PriceBlock ngwee={123.45} />)).toThrow(/integer/);
  });

  it("renders struck old price and savings chip", () => {
    render(<PriceBlock ngwee={100000} oldNgwee={150000} savingsLabel="Save K500.00" />);
    expect(screen.getByText("K1,000.00")).toBeInTheDocument();
    expect(screen.getByText("K1,500.00")).toHaveStyle({ textDecoration: "line-through" });
    expect(screen.getByTestId("price-savings")).toHaveTextContent("Save K500.00");
  });
});
