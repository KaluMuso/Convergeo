// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShopHeader } from "./shop-header";

const eligible = vi.fn<() => boolean>();
const cartMocks = vi.hoisted(() => ({
  refreshCart: vi.fn().mockResolvedValue(null),
  openMiniCart: vi.fn(),
  setStoreState: vi.fn(),
}));
vi.mock("./cart/mini-cart-drawer", () => cartMocks);

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

vi.mock("./cart/cart-store", () => ({
  useCartStore: () => ({ cart: null }),
  setStoreState: cartMocks.setStoreState,
  getCartItemCount: () => 0,
  CartNavTrigger: ({
    labels,
    cartIcon,
    className,
  }: {
    labels: { openCart: string };
    cartIcon: React.ReactNode;
    className?: string;
  }) => (
    <button
      type="button"
      aria-label={labels.openCart}
      className={className}
      data-testid="cart-nav-trigger"
      onClick={cartMocks.openMiniCart}
    >
      {cartIcon}
    </button>
  ),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.doMock("./cart/mini-cart-drawer", () => cartMocks);
});

const labels = {
  appName: "Convergeo",
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
  featuredTitle: "New on Convergeo",
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
  openCart: "Open cart",
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
    expect(screen.getAllByTestId("cart-nav-trigger").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Open cart" }).length).toBeGreaterThan(0);
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function scheduledIdle() {
  let run!: () => void;
  const cancel = vi.fn();
  vi.stubGlobal(
    "requestIdleCallback",
    vi.fn((callback: () => void) => {
      run = callback;
      return 7;
    }),
  );
  vi.stubGlobal("cancelIdleCallback", cancel);
  return { run: () => run(), cancel };
}

describe("deferred header cart hydration", () => {
  it("opens the cart before idle loading and cancels a refresh when unmounted during import", async () => {
    const idle = scheduledIdle();
    const module = deferred<typeof cartMocks>();
    const load = vi.fn(() => module.promise);
    vi.doMock("./cart/mini-cart-drawer", load);
    const view = render(<ShopHeader locale="en" labels={labels} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Open cart" })[0]!);
    expect(cartMocks.openMiniCart).toHaveBeenCalledOnce();
    expect(load).not.toHaveBeenCalled();
    expect(cartMocks.refreshCart).not.toHaveBeenCalled();
    act(() => idle.run());
    await waitFor(() => expect(load).toHaveBeenCalledOnce());
    view.unmount();
    expect(idle.cancel).toHaveBeenCalledExactlyOnceWith(7);
    await act(async () => {
      module.resolve(cartMocks);
    });
    expect(cartMocks.refreshCart).not.toHaveBeenCalled();
    expect(cartMocks.setStoreState).not.toHaveBeenCalled();
  });

  it("marks import failure as a load error and can hydrate on the next mounted attempt", async () => {
    const idle = scheduledIdle();
    vi.doMock("./cart/mini-cart-drawer", () => {
      throw new Error("Chunk unavailable");
    });
    const view = render(<ShopHeader locale="en" labels={labels} />);
    act(() => idle.run());
    await waitFor(() =>
      expect(cartMocks.setStoreState).toHaveBeenCalledExactlyOnceWith({
        loading: false,
        loadError: true,
      }),
    );
    expect(cartMocks.refreshCart).not.toHaveBeenCalled();
    view.unmount();
    vi.doMock("./cart/mini-cart-drawer", () => cartMocks);
    render(<ShopHeader locale="en" labels={labels} />);
    act(() => idle.run());
    await waitFor(() => expect(cartMocks.refreshCart).toHaveBeenCalledOnce());
  });
});
