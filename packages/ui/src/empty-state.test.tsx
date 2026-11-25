// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders title, body, icon and action slots", () => {
    render(
      <EmptyState
        icon={<span data-testid="icon">📭</span>}
        title="Nothing here"
        body="Try again later"
        action={<button type="button">Browse</button>}
      />,
    );

    expect(screen.getByTestId("icon")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
    expect(screen.getByText("Try again later")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browse" })).toBeInTheDocument();
  });

  it("renders a spot illustration when illustration is set", () => {
    render(<EmptyState illustration="empty-cart" title="Cart is empty" />);
    expect(screen.getByRole("img", { hidden: true })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cart is empty" })).toBeInTheDocument();
  });
});
