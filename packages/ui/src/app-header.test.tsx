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

  it("renders shop variant with Directory primary link and gated supplies slot", () => {
    render(
      <AppHeader
        variant="shop"
        appName="Vergeo5"
        cartLabel="Cart"
        skipLinkTargetId="shop-main"
        navAriaLabel="Shop navigation"
        navLinks={[
          { key: "directory", href: "/en/directory", label: "Directory" },
          { key: "services", href: "/en/services", label: "Services" },
        ]}
        desktopSearchSlot={<div role="search">Search</div>}
        suppliesSlot={
          <li>
            <a href="/en/supplies">Supplies</a>
          </li>
        }
        LinkComponent={({ href, children, className }) => (
          <a href={href} className={className}>
            {children}
          </a>
        )}
      />,
    );

    expect(screen.getByRole("link", { name: "Directory" })).toHaveAttribute(
      "href",
      "/en/directory",
    );
    expect(screen.getByRole("link", { name: "Supplies" })).toHaveAttribute("href", "/en/supplies");
    expect(screen.getByRole("search")).toBeInTheDocument();
  });

  it("hides cart badge when count is 0", () => {
    render(
      <AppHeader
        variant="shop"
        appName="Vergeo5"
        cartLabel="Cart"
        cartCount={0}
        cartHref="/en/cart"
        skipLinkTargetId="shop-main"
        navAriaLabel="Shop navigation"
        LinkComponent={({ href, children, ...rest }) => (
          <a href={href} {...rest}>
            {children}
          </a>
        )}
      />,
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("includes cart count in accessible name and live region", () => {
    render(
      <AppHeader
        variant="shop"
        appName="Vergeo5"
        cartLabel="Cart"
        cartCount={3}
        cartCountLabel="Cart, 3 items"
        cartHref="/en/cart"
        skipLinkTargetId="shop-main"
        navAriaLabel="Shop navigation"
        LinkComponent={({ href, children, ...rest }) => (
          <a href={href} {...rest}>
            {children}
          </a>
        )}
      />,
    );
    expect(screen.getAllByRole("link", { name: "Cart, 3 items" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cart, 3 items").length).toBe(1);
  });

  it("renders auth variant with hero wordmark and no cart", () => {
    render(
      <AppHeader
        variant="auth"
        appName="Vergeo5"
        tagline="Discover Zambia"
        skipLinkTargetId="auth-main"
        skipLinkLabel="Skip to content"
        navAriaLabel="Auth"
        secondaryLink={<a href="/en">Back to shop</a>}
      />,
    );

    expect(screen.getByTestId("app-header-wordmark")).toHaveTextContent("Vergeo5");
    expect(screen.getByText("Discover Zambia")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to shop" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /cart/i })).not.toBeInTheDocument();
  });

  it("toggles compact scrolled state on shop variant", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    Object.defineProperty(window, "scrollY", { value: 0, writable: true, configurable: true });

    const { container } = render(
      <AppHeader
        variant="shop"
        appName="Vergeo5"
        cartLabel="Cart"
        cartCount={2}
        skipLinkTargetId="shop-main"
        navAriaLabel="Shop navigation"
      />,
    );

    const header = container.querySelector("header");
    expect(header).toHaveAttribute("data-compact", "false");

    act(() => {
      Object.defineProperty(window, "scrollY", { value: 80, writable: true, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });

    expect(header).toHaveAttribute("data-compact", "true");
    expect(header).toHaveStyle({ boxShadow: "var(--shadow-1)" });
  });
});
