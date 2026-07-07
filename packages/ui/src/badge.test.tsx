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
];

describe("Badge", () => {
  afterEach(() => {
    cleanup();
  });

  it.each(variants)("maps %s variant to token colors", (variant) => {
    render(<Badge variant={variant} label={`Label ${variant}`} />);
    const badge = screen.getByTestId(`badge-${variant}`);
    expect(badge).toHaveTextContent(`Label ${variant}`);
    expect(badge).toHaveStyle({ backgroundColor: expect.any(String) });
  });

  it("uses danger token for sold_out", () => {
    render(<Badge variant="sold_out" label="Sold out" />);
    expect(screen.getByTestId("badge-sold_out")).toHaveStyle({
      backgroundColor: "rgb(192, 57, 43)",
    });
  });
});
