// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BottomNav, type BottomNavItem } from "./bottom-nav";

const items: BottomNavItem[] = [
  { key: "home", icon: <span data-testid="icon-home" />, label: "Home", href: "/en", active: true },
  { key: "browse", icon: <span />, label: "Browse", href: "/en/browse", active: false },
  { key: "ask", icon: <span />, label: "Ask", href: "/en/ask", active: false },
  { key: "orders", icon: <span />, label: "Orders", href: "/en/orders", active: false, badge: 3 },
  {
    key: "account",
    icon: <span />,
    label: "Account",
    href: "/en/account",
    active: false,
    badge: 120,
  },
];

describe("BottomNav", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders 5 config-driven slots", () => {
    render(<BottomNav items={items} ariaLabel="Main navigation" />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Account")).toBeInTheDocument();
  });

  it("sets aria-current on the active item", () => {
    const { container } = render(<BottomNav items={items} ariaLabel="Main navigation" />);
    const active = container.querySelector('[aria-current="page"]');
    expect(active).toHaveTextContent("Home");
    const browse = container.querySelector('a[href="/en/browse"]');
    expect(browse).not.toHaveAttribute("aria-current", "page");
  });

  it("renders badge counts and caps at 99+", () => {
    const { container } = render(<BottomNav items={items} ariaLabel="Main navigation" />);
    const ordersLink = container.querySelector('a[href="/en/orders"]');
    expect(ordersLink).toHaveTextContent("3");
    const accountLink = container.querySelector('a[href="/en/account"]');
    expect(accountLink).toHaveTextContent("99+");
  });

  it("applies safe-area inset padding", () => {
    const { container } = render(<BottomNav items={items} ariaLabel="Main navigation" />);
    const nav = container.querySelector("nav");
    expect(nav).toHaveStyle({ paddingBottom: "env(safe-area-inset-bottom, 0px)" });
  });
});
