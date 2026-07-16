// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const eligible = vi.fn<() => boolean>();

vi.mock("./use-business-eligibility", () => ({
  useBusinessEligibility: () => eligible(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/search",
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { BottomNavClient } from "./bottom-nav-client";
import { SuppliesNavLink } from "./supplies-nav-link";

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

describe("SuppliesNavLink (desktop)", () => {
  it("renders the wholesale link for verified business buyers", () => {
    eligible.mockReturnValue(true);
    render(
      <ul>
        <SuppliesNavLink locale="en" label="Supplies" />
      </ul>,
    );
    expect(screen.getByRole("link", { name: "Supplies" })).toHaveAttribute("href", "/en/supplies");
  });

  it("renders nothing for guests / non-eligible viewers", () => {
    eligible.mockReturnValue(false);
    render(
      <ul>
        <SuppliesNavLink locale="en" label="Supplies" />
      </ul>,
    );
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
    // Base tabs still render.
    expect(screen.getByRole("link", { name: /Browse/ })).toBeInTheDocument();
  });
});
