// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VendorCard } from "./vendor-card";

const LONG_BEMBA_NAME =
  "Ukusunga kwa malonda ya bukolwe ne fintu ifiletelela abantu abalinga ukutandalila";

describe("VendorCard", () => {
  afterEach(() => {
    cleanup();
  });

  const baseProps = {
    name: "FarmFresh Supplies",
    categoryLabel: "Agriculture",
    locationLabel: "Kabwe, Central Province",
    trust: "sector_verified" as const,
    trustLabel: "Sector Verified",
    tier: "gold" as const,
    tierLabel: "Gold",
    stats: [
      { label: "Products", value: "128" },
      { label: "Rating", value: "4.7" },
      { label: "Orders", value: "540" },
    ],
    ctaLabel: "View store",
  };

  it("renders required fields with trust pill and tier chip", () => {
    render(<VendorCard {...baseProps} />);
    expect(screen.getByTestId("vendor-card")).toBeInTheDocument();
    expect(screen.getByTestId("corner-ribbon-trust")).toHaveTextContent("Sector Verified");
    expect(screen.getByTestId("corner-ribbon-tier")).toHaveTextContent("Gold");
    expect(screen.getByTestId("vendor-stats")).toBeInTheDocument();
  });

  it("renders skeleton variant", () => {
    render(<VendorCard {...baseProps} skeleton />);
    expect(screen.getByTestId("vendor-card-skeleton")).toBeInTheDocument();
  });

  it("truncates long Bemba vendor name", () => {
    render(<VendorCard {...baseProps} name={LONG_BEMBA_NAME} />);
    const heading = screen.getByTestId("vendor-card").querySelector("h3");
    expect(heading).toHaveStyle({ textOverflow: "ellipsis", whiteSpace: "nowrap" });
  });

  it("fires CTA callback", async () => {
    const user = userEvent.setup();
    const onCtaClick = vi.fn();
    render(<VendorCard {...baseProps} onCtaClick={onCtaClick} />);
    await user.click(screen.getByTestId("vendor-card-cta"));
    expect(onCtaClick).toHaveBeenCalledTimes(1);
  });
});
