// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { testFilterLabels } from "../filters/test-labels";

const push = vi.fn();
let search = "q=phone";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/en/search",
  useSearchParams: () => new URLSearchParams(search),
}));

import { SearchFilterPanel } from "./search-filter-panel";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  search = "q=phone";
});

const categories = [{ path: "electronics", label: "Electronics" }];

describe("SearchFilterPanel (filter boxes)", () => {
  it("renders titled boxes, with counts beside category chips", () => {
    render(
      <SearchFilterPanel
        labels={testFilterLabels}
        categories={categories}
        categoryCounts={{ electronics: 4 }}
      />,
    );
    const boxes = screen.getAllByTestId("filter-box");
    expect(boxes.length).toBeGreaterThanOrEqual(6);
    const category = boxes[0]!;
    expect(within(category).getByText("Electronics")).toBeInTheDocument();
    expect(within(category).getByText("4")).toBeInTheDocument();
    // Search has no Made in Zambia facet yet: hidden unless already selected.
    expect(screen.queryByText("Made in Zambia")).toBeNull();
  });

  it("toggles URL params instantly and resets pagination", async () => {
    search = "q=phone&page=3";
    const user = userEvent.setup();
    render(<SearchFilterPanel labels={testFilterLabels} categories={categories} />);
    await user.click(screen.getByText("Verified sellers"));
    expect(push).toHaveBeenCalledWith("/en/search?q=phone&verified=1", { scroll: false });
    await user.click(screen.getByText("In stock"));
    expect(push).toHaveBeenLastCalledWith("/en/search?q=phone&in_stock=1", {
      scroll: false,
    });
  });

  it("applies a price band and category chip", async () => {
    const user = userEvent.setup();
    render(<SearchFilterPanel labels={testFilterLabels} categories={categories} />);
    await user.click(screen.getByText("K500–K2,000"));
    expect(push).toHaveBeenCalledWith("/en/search?q=phone&min_price=500&max_price=2000", {
      scroll: false,
    });
    await user.click(screen.getByText("Electronics"));
    expect(push).toHaveBeenLastCalledWith("/en/search?q=phone&category_path=electronics", {
      scroll: false,
    });
  });

  it("marks selected chips from the URL and clears filters but keeps the query", async () => {
    search = "q=phone&verified=1&deals=1&min_price=500&max_price=2000";
    const user = userEvent.setup();
    render(<SearchFilterPanel labels={testFilterLabels} categories={categories} />);
    const verified = screen.getByText("Verified sellers").closest("a")!;
    expect(verified).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("K500–K2,000").closest("a")).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByTestId("filter-boxes-clear"));
    expect(push).toHaveBeenCalledWith("/en/search?q=phone", { scroll: false });
  });

  it("submits custom min/max price", async () => {
    const user = userEvent.setup();
    render(<SearchFilterPanel labels={testFilterLabels} categories={[]} />);
    await user.type(screen.getByLabelText("Min"), "100");
    await user.click(screen.getByText("Set price"));
    expect(push).toHaveBeenCalledWith("/en/search?q=phone&min_price=100", { scroll: false });
  });

  it("hides price boxes for non-commerce tabs", () => {
    render(
      <SearchFilterPanel labels={testFilterLabels} categories={[]} showPriceFilters={false} />,
    );
    expect(screen.queryByText("K500–K2,000")).toBeNull();
  });
});
