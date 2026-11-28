// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FilterBox, FilterChip } from "./filter-box";
import { ProductCard } from "./product-card";
import { SignalBadge, SignalBadgeRow } from "./signal-badge";
import { SignalRibbon } from "./signal-ribbon";
import { TierPriceLadder } from "./tier-price-ladder";

afterEach(cleanup);

describe("SignalBadge", () => {
  it("renders label with token classes and no raw colours", () => {
    render(<SignalBadge kind="cheapest" label="Cheapest" />);
    const el = screen.getByTestId("signal-badge-cheapest");
    expect(el).toHaveTextContent("Cheapest");
    expect(el.className).toContain("bg-primary-tint");
    expect(el.outerHTML).not.toMatch(/#[0-9a-f]{3,6}/i);
  });

  it("caps the row at two badges", () => {
    render(
      <SignalBadgeRow
        badges={[
          { kind: "cheapest", label: "A" },
          { kind: "near_you", label: "B" },
          { kind: "new", label: "C" },
        ]}
      />,
    );
    expect(screen.getAllByTestId(/^signal-badge-/).filter((n) => n.dataset.kind)).toHaveLength(2);
    expect(screen.queryByText("C")).toBeNull();
  });

  it("renders nothing for an empty row", () => {
    const { container } = render(<SignalBadgeRow badges={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("SignalRibbon", () => {
  it.each(["preferred", "verified_business", "verified_id"] as const)("renders %s", (kind) => {
    render(<SignalRibbon kind={kind} label={`L-${kind}`} />);
    expect(screen.getByTestId("signal-ribbon")).toHaveAttribute("data-kind", kind);
  });
});

describe("TierPriceLadder", () => {
  const props = { rangeLabel: "{min}–{max}", openRangeLabel: "{min}+" };

  it("sorts tiers, formats integer ngwee and shows savings vs the first tier", () => {
    render(
      <TierPriceLadder
        {...props}
        tiers={[
          { minQty: 200, unitNgwee: 400 },
          { minQty: 50, maxQty: 199, unitNgwee: 500 },
        ]}
      />,
    );
    const steps = screen.getAllByTestId("tier-price-step");
    expect(steps.map((s) => s.dataset.minQty)).toEqual(["50", "200"]);
    expect(steps[0]).toHaveTextContent("50–199");
    expect(steps[0]).toHaveTextContent("K5.00");
    expect(steps[1]).toHaveTextContent("200+");
    expect(steps[1]).toHaveTextContent("−20%");
  });

  it("drops invalid tiers and renders nothing when none remain", () => {
    const { container } = render(
      <TierPriceLadder {...props} tiers={[{ minQty: 10, unitNgwee: 12.5 }]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("FilterBox / FilterChip", () => {
  it("renders a titled box with selectable chips and counts", () => {
    render(
      <FilterBox title="Seller">
        <FilterChip label="Verified" selected count={4} href="/x?verified=1" />
        <FilterChip label="Deals" selected={false} count={0} href="/x" disabled />
      </FilterBox>,
    );
    expect(screen.getByText("Seller")).toBeInTheDocument();
    const chips = screen.getAllByTestId("filter-chip");
    expect(chips[0]).toHaveAttribute("aria-pressed", "true");
    expect(chips[0]).toHaveAttribute("href", "/x?verified=1");
    expect(chips[1]).toHaveAttribute("aria-disabled", "true");
    expect(chips[1]!.tagName).toBe("SPAN");
  });

  it("uses onNavigate instead of a full page load when provided", () => {
    const onNavigate = vi.fn();
    render(<FilterChip label="Deals" selected={false} href="/x?deals=1" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByTestId("filter-chip"));
    expect(onNavigate).toHaveBeenCalledWith("/x?deals=1");
  });
});

describe("ProductCard signal slots", () => {
  it("renders ribbon and signals only when provided", () => {
    const base = {
      title: "Cup",
      vendorLabel: "by A",
      ngwee: 1000,
      rating: 0,
      reviewCount: 0,
      quickAddLabel: "Add",
      wishlistLabel: "Save",
    };
    const { rerender } = render(<ProductCard {...base} />);
    expect(screen.queryByTestId("product-card-ribbon")).toBeNull();
    expect(screen.queryByTestId("product-card-signals")).toBeNull();
    rerender(
      <ProductCard
        {...base}
        ribbon={<SignalRibbon kind="verified_id" label="ID verified" />}
        signals={<SignalBadge kind="new" label="New" />}
      />,
    );
    expect(screen.getByTestId("product-card-ribbon")).toHaveTextContent("ID verified");
    expect(screen.getByTestId("product-card-signals")).toHaveTextContent("New");
  });
});
