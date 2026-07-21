// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/search",
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { BottomNavClient } from "./bottom-nav-client";
import { ShopHeader } from "./shop-header";

const baseItems = [
  { key: "home", icon: <span>H</span>, label: "Home", href: "/en" },
  { key: "browse", icon: <span>B</span>, label: "Browse", href: "/en/search" },
];

const suppliesItem = {
  key: "supplies",
  icon: <span>S</span>,
  label: "Supplies",
  href: "/en/supplies",
};

const headerLabels = {
  appName: "Vergeo5",
  skipToContent: "Skip to content",
  navAriaLabel: "Shop navigation",
  desktopAriaLabel: "Primary navigation",
  searchPlaceholder: "Search",
  searchSubmit: "Search",
  allCategories: "All Categories",
  categoriesPanelAria: "Categories",
  categoriesLoading: "Loading",
  categoriesEmpty: "Empty",
  viewAllCategories: "View all",
  featuredTitle: "Featured",
  featuredPromo: "Promo",
  featuredPromoCta: "CTA",
  directory: "Directory",
  services: "Services",
  events: "Events",
  askVergeo: "Ask Vergeo",
  supplies: "Supplies",
  account: "Account",
  cart: "Cart",
  cartWithCount: "Cart, {count} items",
  searchInput: {
    placeholder: "Search",
    submit: "Search",
    ariaLabel: "Search",
    suggestionsLabel: "Suggestions",
    noSuggestions: "None",
    recentTitle: "Recent",
  },
};

describe("ShopHeader supplies gating (desktop)", () => {
  it("renders the wholesale link for verified business buyers", () => {
    eligible.mockReturnValue(true);
    render(<ShopHeader locale="en" labels={headerLabels} />);
    expect(screen.getByRole("link", { name: "Supplies" })).toHaveAttribute("href", "/en/supplies");
  });

  it("renders nothing for guests / non-eligible viewers", () => {
    eligible.mockReturnValue(false);
    render(<ShopHeader locale="en" labels={headerLabels} />);
    expect(screen.queryByRole("link", { name: "Supplies" })).not.toBeInTheDocument();
  });
});

describe("BottomNavClient supplies gating (mobile)", () => {
  it("appends the Supplies tab when the viewer is eligible", () => {
    eligible.mockReturnValue(true);
    render(
      <BottomNavClient items={baseItems} ariaLabel="nav" locale="en" suppliesItem={suppliesItem} />,
    );
    expect(screen.getByRole("link", { name: /Supplies/ })).toHaveAttribute("href", "/en/supplies");
  });

  it("omits the Supplies tab for non-eligible viewers", () => {
    eligible.mockReturnValue(false);
    render(
      <BottomNavClient items={baseItems} ariaLabel="nav" locale="en" suppliesItem={suppliesItem} />,
    );
    expect(screen.queryByRole("link", { name: /Supplies/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Browse/ })).toBeInTheDocument();
  });
});
