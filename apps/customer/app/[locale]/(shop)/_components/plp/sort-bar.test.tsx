// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/en/c/all",
  useSearchParams: () => new URLSearchParams("sort=cheapest&cursor=abc"),
}));

import { SortBar } from "./sort-bar";

const labels = {
  label: "Sort by",
  relevance: "Relevance",
  cheapest: "Lowest price",
  nearest: "Nearest",
  newest: "Newest",
  best: "Best match",
  verified: "Verified sellers",
  bundles: "Bundles",
  cheapestChip: "Cheapest",
};

afterEach(() => {
  cleanup();
  push.mockReset();
});

describe("SortBar chips", () => {
  it("renders the quick sort chips with the active one pressed", () => {
    render(<SortBar labels={labels} value="cheapest" hasLocation={false} />);
    expect(screen.getByRole("group", { name: "Sort by" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cheapest" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Nearest" })).toBeDisabled();
  });

  it("sets the API sort param and drops the cursor", () => {
    render(<SortBar labels={labels} value="cheapest" hasLocation />);
    fireEvent.click(screen.getByRole("button", { name: "Verified sellers" }));
    expect(push).toHaveBeenCalledWith("/en/c/all?sort=verified", {
      scroll: false,
    });
    fireEvent.click(screen.getByRole("button", { name: "Bundles" }));
    expect(push).toHaveBeenLastCalledWith("/en/c/all?sort=bundle", {
      scroll: false,
    });
  });

  it("Best match clears the sort param", () => {
    render(<SortBar labels={labels} value="cheapest" hasLocation />);
    fireEvent.click(screen.getByRole("button", { name: "Best match" }));
    expect(push).toHaveBeenCalledWith("/en/c/all", { scroll: false });
  });
});
