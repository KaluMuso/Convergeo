// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DesktopHeader } from "./desktop-header";

vi.mock("./category-mega-menu", () => ({
  CategoryMegaMenu: ({ labels }: { labels: { trigger: string } }) => (
    <button type="button">{labels.trigger}</button>
  ),
}));

vi.mock("./cart/mini-cart-drawer", () => ({
  useCartStore: () => ({ cart: null }),
  useCartActions: () => ({ refresh: vi.fn() }),
  getCartItemCount: () => 0,
}));

afterEach(cleanup);

const labels = {
  appName: "Vergeo5",
  skipToContent: "Skip to content",
  navAriaLabel: "Primary navigation",
  searchPlaceholder: "Search products, services, events…",
  searchSubmit: "Search",
  allCategories: "All Categories",
  categoriesPanelAria: "All categories",
  categoriesLoading: "Loading…",
  categoriesEmpty: "Empty",
  viewAllCategories: "View all",
  directory: "Directory",
  services: "Services",
  events: "Events",
  askVergeo: "Ask Vergeo",
  account: "Account",
  cart: "Cart",
  cartWithCount: "Cart, {count} items",
};

describe("DesktopHeader", () => {
  it("exposes search-forward primary nav with Directory and without theme control", () => {
    render(<DesktopHeader locale="en" labels={labels} />);

    expect(screen.getByTestId("desktop-header")).toBeInTheDocument();
    expect(screen.getByRole("search")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Directory" })).toHaveAttribute(
      "href",
      "/en/directory",
    );
    expect(screen.getByRole("link", { name: "Services" })).toHaveAttribute("href", "/en/services");
    expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute("href", "/en/events");
    expect(screen.getByRole("link", { name: "Ask Vergeo" })).toHaveAttribute("href", "/en/ask");
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("href", "/en/account");
    expect(screen.getByRole("link", { name: "Cart" })).toHaveAttribute("href", "/en/cart");
    expect(screen.queryByRole("link", { name: /browse/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /theme|dark|light/i })).not.toBeInTheDocument();
  });

  it("matches the approved desktop chrome structure snapshot", () => {
    const { container } = render(<DesktopHeader locale="en" labels={labels} />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
