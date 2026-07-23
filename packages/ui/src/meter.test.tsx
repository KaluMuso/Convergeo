// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Meter } from "./meter";

afterEach(cleanup);

describe("Meter", () => {
  it("exposes progressbar semantics with the localised label", () => {
    render(<Meter value={42} label="Completion" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-label", "Completion");
  });

  it("clamps out-of-range values into 0..100", () => {
    const { rerender } = render(<Meter value={150} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    rerender(<Meter value={-20} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("rounds fractional values and drives the fill width + tone", () => {
    render(<Meter value={33.6} label="x" tone="success" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "34");
    const fill = bar.firstChild as HTMLElement;
    expect(fill).toHaveStyle({ width: "34%" });
    expect(fill).toHaveClass("bg-success");
  });
});
