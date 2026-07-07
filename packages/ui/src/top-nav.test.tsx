// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TopNav } from "./top-nav";

describe("TopNav", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hides cart badge when count is 0", () => {
    render(
      <TopNav
        logo={<span>Logo</span>}
        cartIcon={<span data-testid="cart-icon" />}
        cartCount={0}
        cartLabel="Cart"
        skipLinkTargetId="main-content"
        navAriaLabel="Primary"
      />,
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByTestId("cart-icon")).toBeInTheDocument();
  });

  it("shows cart badge when count is greater than 0", () => {
    render(
      <TopNav
        logo={<span>Logo</span>}
        cartIcon={<span />}
        cartCount={5}
        cartLabel="Cart"
        skipLinkTargetId="main-content"
        navAriaLabel="Primary"
      />,
    );
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("toggles scrolled shadow class after scroll", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });

    Object.defineProperty(window, "scrollY", { value: 0, writable: true, configurable: true });

    const { container } = render(
      <TopNav
        logo={<span>Logo</span>}
        cartIcon={<span />}
        cartCount={2}
        cartLabel="Cart"
        skipLinkTargetId="main-content"
        navAriaLabel="Primary"
      />,
    );

    const header = container.querySelector("header");
    expect(header).not.toHaveClass("top-nav--scrolled");

    act(() => {
      Object.defineProperty(window, "scrollY", { value: 80, writable: true, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });

    expect(header).toHaveClass("top-nav--scrolled");
    expect(header).toHaveStyle({ boxShadow: "var(--shadow-1)" });
  });
});
