// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Badge } from "./badge";
import { ProductCard } from "./product-card";

const LONG_NYANJA_TITLE =
  "Zogulani zogwiritsira ntchito pa msika wa digito ku Zambia ndi ntchito zambiri";

describe("ProductCard", () => {
  afterEach(() => {
    cleanup();
  });

  const baseProps = {
    title: "Wireless Earbuds",
    vendorLabel: "TechHub Lusaka",
    ngwee: 250000,
    rating: 4.2,
    reviewCount: 18,
    reviewCountLabel: "(18)",
    quickAddLabel: "Quick add",
    wishlistLabel: "Add to wishlist",
  };

  it("renders required fields", () => {
    render(<ProductCard {...baseProps} />);
    expect(screen.getByTestId("product-card")).toBeInTheDocument();
    expect(screen.getByText("Wireless Earbuds")).toBeInTheDocument();
    expect(screen.getByText("TechHub Lusaka")).toBeInTheDocument();
    expect(screen.getByText("K2,500.00")).toBeInTheDocument();
  });

  it("renders a struck compare-at price and discount chip when on sale", () => {
    render(<ProductCard {...baseProps} ngwee={250000} oldNgwee={400000} discountLabel="−38%" />);
    const struck = screen.getByText("K4,000.00");
    expect(struck).toBeInTheDocument();
    expect(struck.className).toMatch(/line-through/);
    expect(screen.getByTestId("product-card-discount")).toHaveTextContent("−38%");
  });

  it("omits the discount chip with no compare-at price", () => {
    render(<ProductCard {...baseProps} />);
    expect(screen.queryByTestId("product-card-discount")).not.toBeInTheDocument();
  });

  it("renders skeleton variant", () => {
    render(<ProductCard {...baseProps} skeleton />);
    expect(screen.getByTestId("product-card-skeleton")).toBeInTheDocument();
  });

  it("truncates long Nyanja title with line-clamp", () => {
    render(<ProductCard {...baseProps} title={LONG_NYANJA_TITLE} />);
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading.className).toMatch(/line-clamp-2/);
    expect(heading.textContent).toBe(LONG_NYANJA_TITLE);
  });

  it("renders an empty media stage when no image is provided", () => {
    render(<ProductCard {...baseProps} />);
    expect(screen.getByTestId("product-card-media-empty")).toBeInTheDocument();
  });

  it("does not render dead wishlist/quick-add controls without handlers", () => {
    render(<ProductCard {...baseProps} />);
    expect(screen.queryByTestId("product-card-wishlist")).not.toBeInTheDocument();
    expect(screen.queryByTestId("product-card-quick-add")).not.toBeInTheDocument();
  });

  it("supports compact density and unavailable state", () => {
    render(<ProductCard {...baseProps} density="compact" unavailable />);
    const card = screen.getByTestId("product-card");
    expect(card).toHaveAttribute("data-density", "compact");
    expect(card).toHaveAttribute("data-unavailable", "true");
    expect(card.firstElementChild).toHaveClass("aspect-[4/3]");
    expect(card.children[1]).toHaveClass("p-[var(--sp-2)]");
  });

  it("renders optional meta without inventing content", () => {
    render(<ProductCard {...baseProps} meta={<span>Pickup available</span>} />);
    expect(screen.getByText("Pickup available")).toBeInTheDocument();
  });

  it("fires quick-add and wishlist callbacks", async () => {
    const user = userEvent.setup();
    const onQuickAdd = vi.fn();
    const onWishlistToggle = vi.fn();

    render(
      <ProductCard
        {...baseProps}
        onQuickAdd={onQuickAdd}
        onWishlistToggle={onWishlistToggle}
        badge={<Badge variant="new" label="New" />}
      />,
    );

    await user.click(screen.getByTestId("product-card-quick-add"));
    await user.click(screen.getByTestId("product-card-wishlist"));
    expect(onQuickAdd).toHaveBeenCalledTimes(1);
    expect(onWishlistToggle).toHaveBeenCalledTimes(1);
  });

  it("announces wishlist status changes via a polite live region", () => {
    render(
      <ProductCard
        {...baseProps}
        onWishlistToggle={() => undefined}
        isWishlisted
        wishlistStatusAnnouncement="Saved to wishlist"
      />,
    );
    const status = screen.getByTestId("product-card-wishlist-status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Saved to wishlist");
  });

  it("fits two cards in a 360px grid without horizontal overflow", () => {
    const { container } = render(
      <div
        data-testid="grid"
        style={{
          width: 360,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
        }}
      >
        <ProductCard {...baseProps} title="Card A" />
        <ProductCard {...baseProps} title="Card B" />
      </div>,
    );

    const grid = screen.getByTestId("grid");
    expect(grid.scrollWidth).toBeLessThanOrEqual(360);
    expect(container.querySelectorAll("[data-testid='product-card']")).toHaveLength(2);
  });
});
