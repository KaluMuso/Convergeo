// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomNavClient, shouldRenderShopBottomNav } from "./bottom-nav-client";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(),
}));

vi.mock("./merch-preview-nav", () => ({
  useMerchPreviewToken: () => null,
  withMerchPreviewParam: (href: string) => href,
}));

vi.mock("@vergeo/ui/src/bottom-nav", () => ({
  BottomNav: () => <div data-testid="bottom-nav-ui" />,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const items = [
  { key: "home", href: "/en", label: "Home", icon: null },
  { key: "browse", href: "/en/search", label: "Browse", icon: null },
];

describe("shouldRenderShopBottomNav", () => {
  it.each([
    ["/en", true],
    ["/en/search", true],
    ["/en/cart", false],
    ["/en/checkout", false],
    ["/en/checkout/pending", false],
    ["/en/p/phone", true],
  ])("pathname %s → %s", (pathname, expected) => {
    expect(shouldRenderShopBottomNav(pathname, "en")).toBe(expected);
  });
});

describe("BottomNavClient", () => {
  it("does not mount on cart or checkout routes", () => {
    vi.mocked(usePathname).mockReturnValue("/en/checkout");
    const { container: checkout } = render(
      <BottomNavClient items={items} ariaLabel="Nav" locale="en" />,
    );
    expect(checkout).toBeEmptyDOMElement();

    vi.mocked(usePathname).mockReturnValue("/en/cart");
    const { container: cart } = render(
      <BottomNavClient items={items} ariaLabel="Nav" locale="en" />,
    );
    expect(cart).toBeEmptyDOMElement();
  });

  it("renders on ordinary shop routes", () => {
    vi.mocked(usePathname).mockReturnValue("/en");
    render(<BottomNavClient items={items} ariaLabel="Nav" locale="en" />);
    expect(screen.getByTestId("bottom-nav-ui")).toBeInTheDocument();
  });
});
