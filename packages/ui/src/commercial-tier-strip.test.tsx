// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CommercialTierStrip } from "./commercial-tier-strip";

describe("CommercialTierStrip", () => {
  afterEach(() => {
    cleanup();
  });

  const items = [
    { id: "bronze" as const, label: "Bronze", perk: "Basic listing" },
    { id: "silver" as const, label: "Silver", perk: "Standard + analytics" },
    { id: "gold" as const, label: "Gold", perk: "Featured + reports" },
    { id: "platinum" as const, label: "Platinum", perk: "Priority + B2B" },
  ];

  it("renders all tiers and marks active tier", () => {
    render(
      <CommercialTierStrip activeTier="gold" items={items} ariaLabel="Vendor subscription tier" />,
    );

    expect(screen.getByTestId("commercial-tier-strip")).toBeInTheDocument();
    expect(screen.getByTestId("commercial-tier-tab-gold")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("commercial-tier-tab-bronze")).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });
});
