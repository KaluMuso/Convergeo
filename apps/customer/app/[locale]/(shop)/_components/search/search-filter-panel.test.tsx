// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/en/search",
  useSearchParams: () => new URLSearchParams("q=phone"),
}));

import { SearchFilterPanel } from "./search-filter-panel";

const labels = {
  heading: "Filter products",
  price: "Price",
  minPrice: "Min",
  maxPrice: "Max",
  category: "Category",
  categoryAll: "All categories",
  apply: "Apply filters",
  clear: "Clear filters",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SearchFilterPanel", () => {
  beforeEach(() => {
    cleanup();
  });

  it("pushes filter params on apply", async () => {
    const user = userEvent.setup();
    render(
      <SearchFilterPanel
        labels={labels}
        categories={[{ path: "electronics", label: "Electronics" }]}
        initialState={{}}
      />,
    );

    await user.type(screen.getByLabelText("Min"), "100");
    await user.selectOptions(screen.getByLabelText("Category"), "electronics");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(push).toHaveBeenCalledWith(
      "/en/search?q=phone&min_price=100&category_path=electronics",
      expect.objectContaining({ scroll: false }),
    );
  });
});
