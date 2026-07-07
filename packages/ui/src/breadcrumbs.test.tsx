// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Breadcrumbs } from "./breadcrumbs";

const items = [
  { key: "home", label: "Home", href: "/en" },
  { key: "shop", label: "Shop", href: "/en/shop" },
  { key: "electronics", label: "Electronics", href: "/en/shop/electronics" },
  { key: "phones", label: "Phones" },
];

describe("Breadcrumbs", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: query.includes("360px"),
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
  });

  it("collapses middle items when depth exceeds 3 on narrow viewports", () => {
    render(
      <Breadcrumbs
        items={items}
        ariaLabel="Breadcrumb"
        ellipsisLabel="More"
        collapseAtWidth={360}
      />,
    );
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("More")).toBeInTheDocument();
    expect(screen.getByText("Phones")).toBeInTheDocument();
    expect(screen.queryByText("Electronics")).not.toBeInTheDocument();
  });

  it("sets aria-current on the current item", () => {
    const { container } = render(
      <Breadcrumbs
        items={items}
        ariaLabel="Breadcrumb"
        ellipsisLabel="More"
        collapseAtWidth={9999}
      />,
    );
    const current = container.querySelector('[aria-current="page"]');
    expect(current).toHaveTextContent("Phones");
  });
});
