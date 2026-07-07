// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  cleanup();
});

import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  it("renders block shape by default", () => {
    render(<Skeleton />);
    const el = screen.getByTestId("skeleton");
    expect(el).toHaveAttribute("data-shape", "block");
    expect(el).toHaveStyle({ animation: "shimmer 1.4s var(--ease-std) infinite" });
  });

  it("renders line and circle shapes", () => {
    const { rerender } = render(<Skeleton shape="line" data-testid="line" />);
    expect(screen.getByTestId("line")).toHaveAttribute("data-shape", "line");

    rerender(<Skeleton shape="circle" data-testid="circle" />);
    expect(screen.getByTestId("circle")).toHaveAttribute("data-shape", "circle");
  });

  it("accepts custom dimensions", () => {
    render(<Skeleton width="10rem" height="2rem" />);
    expect(screen.getByTestId("skeleton")).toHaveStyle({ width: "10rem", height: "2rem" });
  });
});
