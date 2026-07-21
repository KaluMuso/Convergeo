// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppHeader } from "./app-header";

describe("AppHeader", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders marketing links and sign-in slot", () => {
    render(
      <AppHeader
        variant="marketing"
        logo={<span>Vergeo5</span>}
        navAriaLabel="Marketing"
        links={[
          { key: "about", href: "/en/about", label: "About" },
          { key: "contact", href: "/en/contact", label: "Contact" },
        ]}
        signInSlot={<a href="/en/login">Sign in</a>}
      />,
    );

    expect(screen.getByTestId("app-header")).toHaveAttribute("data-variant", "marketing");
    expect(screen.getAllByRole("link", { name: "About" }).length).toBe(2);
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders account search, menu, and cart slots", () => {
    render(
      <AppHeader
        variant="account"
        logo={<span>Vergeo5</span>}
        navAriaLabel="Account"
        searchSlot={<a href="/en/search">Search products</a>}
        accountMenuSlot={<button type="button">Account menu</button>}
        cartSlot={<a href="/en/cart">Cart</a>}
      />,
    );

    expect(screen.getByTestId("app-header")).toHaveAttribute("data-variant", "account");
    expect(screen.getByRole("link", { name: "Search products" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Account menu" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cart" })).toBeInTheDocument();
  });

  it("renders optional skip link", () => {
    render(
      <AppHeader
        variant="marketing"
        logo={<span>Vergeo5</span>}
        navAriaLabel="Marketing"
        skipLink={{ targetId: "marketing-main", label: "Skip to content" }}
      />,
    );

    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute(
      "href",
      "#marketing-main",
    );
  });

  it("toggles scrolled shadow class after scroll", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });

    const { container } = render(
      <AppHeader variant="marketing" logo={<span>Vergeo5</span>} navAriaLabel="Marketing" />,
    );

    const header = container.querySelector('[data-testid="app-header"]');
    expect(header).not.toBeNull();
    expect(header).not.toHaveClass("app-header--scrolled");

    act(() => {
      Object.defineProperty(window, "scrollY", { value: 80, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });

    expect(header).toHaveClass("app-header--scrolled");
  });
});
