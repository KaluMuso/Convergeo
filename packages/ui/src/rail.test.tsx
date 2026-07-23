// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Rail } from "./rail";

afterEach(() => {
  cleanup();
});

describe("Rail", () => {
  it("renders children in a div by default", () => {
    render(
      <Rail data-testid="rail">
        <span>Chip A</span>
        <span>Chip B</span>
      </Rail>,
    );

    const rail = screen.getByTestId("rail");
    expect(rail.tagName).toBe("DIV");
    expect(screen.getByText("Chip A")).toBeInTheDocument();
    expect(screen.getByText("Chip B")).toBeInTheDocument();
  });

  it("renders as ul when as=ul", () => {
    render(
      <Rail as="ul" data-testid="rail">
        <li>Item</li>
      </Rail>,
    );

    expect(screen.getByTestId("rail").tagName).toBe("UL");
  });

  it("applies hidden-scrollbar overflow classes", () => {
    render(<Rail data-testid="rail">child</Rail>);

    const rail = screen.getByTestId("rail");
    expect(rail.className).toMatch(/overflow-x-auto/);
    expect(rail.className).toMatch(/\[scrollbar-width:none\]/);
    expect(rail.className).toMatch(/\[&::-webkit-scrollbar\]:hidden/);
  });

  it("applies snap classes only when snap is true", () => {
    const { rerender } = render(<Rail data-testid="rail">child</Rail>);
    expect(screen.getByTestId("rail").className).not.toMatch(/snap-x/);

    rerender(
      <Rail snap data-testid="rail">
        child
      </Rail>,
    );
    const snapped = screen.getByTestId("rail");
    expect(snapped.className).toMatch(/snap-x/);
    expect(snapped.className).toMatch(/snap-mandatory/);
  });

  it("merges caller className", () => {
    render(
      <Rail className="flex gap-2 pb-1" data-testid="rail">
        child
      </Rail>,
    );

    const rail = screen.getByTestId("rail");
    expect(rail.className).toMatch(/flex gap-2 pb-1/);
    expect(rail.className).toMatch(/overflow-x-auto/);
  });
});
