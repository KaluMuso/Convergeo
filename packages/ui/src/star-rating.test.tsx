// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StarRating } from "./star-rating";

describe("StarRating display mode", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders 3.5 rating with a half-filled star", () => {
    render(<StarRating value={3.5} reviewCount={12} reviewCountLabel="(12)" />);
    const container = screen.getByTestId("star-rating-display");
    const fills = Array.from(
      within(container).getByTestId("star-rating-stars").querySelectorAll("[data-star-fill]"),
    ).map((star) => star.getAttribute("data-star-fill"));
    expect(fills.filter((f) => f === "full")).toHaveLength(3);
    expect(fills.filter((f) => f === "half")).toHaveLength(1);
    expect(fills.filter((f) => f === "empty")).toHaveLength(1);
  });

  it("renders no-reviews slot instead of zero stars", () => {
    render(
      <StarRating
        value={0}
        reviewCount={0}
        noReviewsSlot={<span data-testid="no-reviews">No reviews yet</span>}
      />,
    );
    expect(screen.getByTestId("no-reviews")).toBeInTheDocument();
    expect(screen.queryByTestId("star-rating-stars")).not.toBeInTheDocument();
  });
});

describe("StarRating input mode", () => {
  afterEach(() => {
    cleanup();
  });

  it("supports keyboard selection via arrow keys", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <StarRating
        mode="input"
        value={2}
        onChange={onChange}
        name="rating"
        inputAriaLabel="Rate this product"
      />,
    );

    const group = screen.getByTestId("star-rating-input");
    group.focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith(3);
  });
});
