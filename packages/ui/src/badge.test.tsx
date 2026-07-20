// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge, type BadgeVariant } from "./badge";

const variants: BadgeVariant[] = [
  "sold_out",
  "promotion",
  "public",
  "selling_fast",
  "free",
  "new",
  "featured",
  "sale",
  "in_stock",
  "out_of_stock",
  "sponsored",
  "sample",
];

describe("Badge", () => {
  afterEach(() => {
    cleanup();
  });

  it.each(variants)("renders %s variant with token classes", (variant) => {
    render(<Badge variant={variant} label={`Label ${variant}`} />);
    const badge = screen.getByTestId(`badge-${variant}`);
    expect(badge).toHaveTextContent(`Label ${variant}`);
    expect(badge).toHaveAttribute("data-variant", variant);
  });

  it("uses danger token classes for sold_out", () => {
    render(<Badge variant="sold_out" label="Sold out" />);
    expect(screen.getByTestId("badge-sold_out").className).toMatch(/bg-danger/);
    expect(screen.getByTestId("badge-sold_out").className).toMatch(/text-on-danger/);
  });
});
