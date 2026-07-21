// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShopHeader } from "./shop-header";

const eligible = vi.fn<() => boolean>();

vi.mock("./use-business-eligibility", () => ({
  useBusinessEligibility: () => eligible(),
}));

vi.mock("./category-mega-menu", () => ({
  CategoryMegaMenu: ({ labels }: { labels: { trigger: string } }) => (
    <button type="button">{labels.trigger}</button>
  ),
}));

vi.mock("./desktop-header-search", () => ({
  DesktopHeaderSearch: () => <div role="search">Search</div>,
}));

vi.mock("./cart/mini-cart-drawer", () => ({
  useCartStore: () => ({ cart: null }),
  useCartActions: () => ({ refresh: vi.fn() }),
  getCartItemCount: () => 0,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const labels = {
  appName: "Vergeo5",
  skipToContent: "Skip to content",
  navAriaLabel: "Shop navigation",
  desktopAriaLabel: "Primary navigation",
  searchPlaceholder: "Search products, services, events…",
  searchSubmit: "Search",
  allCategories: "All Categories",
  categoriesPanelAria: "All categories",
  categoriesLoading: "Loading…",
  categoriesEmpty: "Empty",
  viewAllCategories: "View all",
  featuredTitle: "New on Vergeo5",
  featuredPromo: "Compare sellers online.",
  featuredPromoCta: "Search marketplace",
  directory: "Directory",
  services: "Services",
  events: "Events",
  askVergeo: "Ask Vergeo",
  supplies: "Supplies",
  account: "Account",
  cart: "Cart",
  cartWithCount: "Cart, {count} items",
  searchInput: {
    placeholder: "Search products, services, events…",
    submit: "Search",
    ariaLabel: "Search",
    suggestionsLabel: "Search suggestions",
    noSuggestions: "No suggestions",
    recentTitle: "Recent searches",
  },
};

describe("ShopHeader", () => {
  it("exposes search-forward primary nav with Directory and without theme control", () => {
    eligible.mockReturnValue(false);
    render(<ShopHeader locale="en" labels={labels} />);

    expect(screen.getByTestId("shop-header")).toBeInTheDocument();
    expect(screen.getByRole("search")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Directory" })).toHaveAttribute(
      "href",
      "/en/directory",
    );
    expect(screen.getByRole("link", { name: "Services" })).toHaveAttribute("href", "/en/services");
    expect(screen.getByRole("link", { name: "Events" })).toHaveAttribute("href", "/en/events");
    expect(screen.getByRole("link", { name: "Ask Vergeo" })).toHaveAttribute("href", "/en/ask");
    expect(screen.getAllByRole("link", { name: "Account" })[0]).toHaveAttribute(
      "href",
      "/en/account",
    );
    expect(screen.getAllByRole("link", { name: "Cart" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /browse/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /theme|dark|light/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Supplies" })).not.toBeInTheDocument();
  });

  it("shows gated Supplies link for eligible business buyers", () => {
    eligible.mockReturnValue(true);
    render(<ShopHeader locale="en" labels={labels} />);
    expect(screen.getByRole("link", { name: "Supplies" })).toHaveAttribute("href", "/en/supplies");
  });

  it("matches the approved desktop chrome structure snapshot", () => {
    eligible.mockReturnValue(false);
    const { container } = render(<ShopHeader locale="en" labels={labels} />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
