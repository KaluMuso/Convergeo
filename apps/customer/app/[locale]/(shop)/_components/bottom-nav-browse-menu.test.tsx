// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomNavClient } from "./bottom-nav-client";
import { OPEN_MOBILE_MENU_EVENT } from "./mega-menu/menu-events";

import type { BottomNavLinkProps } from "@vergeo/ui/src/bottom-nav";
import type { ComponentType, ReactNode } from "react";

vi.mock("next/navigation", () => ({ usePathname: vi.fn(() => "/en") }));
vi.mock("./merch-preview-nav", () => ({
  useMerchPreviewToken: () => null,
  withMerchPreviewParam: (href: string) => href,
}));
vi.mock("@vergeo/ui/src/bottom-nav", () => ({
  BottomNav: ({
    items,
    LinkComponent,
  }: {
    items: Array<{ key: string; href: string; label: ReactNode }>;
    LinkComponent: ComponentType<BottomNavLinkProps>;
  }) => (
    <nav>
      {items.map((item) => (
        <LinkComponent key={item.key} href={item.href}>
          {item.label}
        </LinkComponent>
      ))}
    </nav>
  ),
}));

afterEach(cleanup);

const items = [
  { key: "home", href: "/en", label: "Home", icon: null },
  { key: "browse", href: "/en/search", label: "Browse", icon: null },
];

describe("bottom nav Browse tab", () => {
  it("opens the department drawer instead of navigating, but stays a link to /search", () => {
    vi.mocked(usePathname).mockReturnValue("/en");
    const opened = vi.fn();
    window.addEventListener(OPEN_MOBILE_MENU_EVENT, opened);
    render(<BottomNavClient items={items} ariaLabel="Nav" locale="en" />);

    const browse = screen.getByRole("link", { name: "Browse" });
    expect(browse).toHaveAttribute("href", "/en/search");
    expect(browse).toHaveAttribute("aria-haspopup", "dialog");

    expect(fireEvent.click(browse)).toBe(false); // default prevented -> no navigation
    expect(opened).toHaveBeenCalledTimes(1);

    // Modified clicks keep native link behaviour (open in new tab).
    fireEvent.click(browse, { ctrlKey: true });
    expect(opened).toHaveBeenCalledTimes(1);

    // Other tabs are plain links.
    const home = screen.getByRole("link", { name: "Home" });
    expect(home).not.toHaveAttribute("aria-haspopup");
    window.removeEventListener(OPEN_MOBILE_MENU_EVENT, opened);
  });
});
