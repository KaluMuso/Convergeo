// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoadMorePagination } from "./pagination";

describe("LoadMorePagination", () => {
  it("fires onLoadMore when clicked", async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();

    render(
      <LoadMorePagination
        onLoadMore={onLoadMore}
        loading={false}
        loadMoreLabel="Load more"
        loadingLabel="Loading"
        remainingCount={12}
        remainingLabel={(count) => `${count} remaining`}
      />,
    );

    expect(screen.getByText("12 remaining")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("shows loading state and disables the button while loading", () => {
    render(
      <LoadMorePagination
        onLoadMore={vi.fn()}
        loading
        loadMoreLabel="Load more"
        loadingLabel="Loading"
      />,
    );

    const button = screen.getByRole("button", { name: "Loading" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
  });
});
