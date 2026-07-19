// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React, { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProgressiveLoadControls } from "./progressive-load-controls";
import { useProgressiveLoad, type ProgressivePage } from "./use-progressive-load";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

type Item = { id: string; title: string };

const labels = {
  loadMore: "Load more",
  loading: "Loading…",
  moreLoaded: "{count} more results loaded.",
  endOfResults: "End of results",
  loadError: "Couldn’t load more results.",
  retry: "Retry",
};

function Harness({
  initialItems,
  initialCursor,
  resetKey,
  fetchPage,
  preferButtonOnly = true,
}: {
  initialItems: Item[];
  initialCursor: string | null;
  resetKey: string;
  fetchPage: (cursor: string, signal: AbortSignal) => Promise<ProgressivePage<Item>>;
  preferButtonOnly?: boolean;
}) {
  const state = useProgressiveLoad<Item>({
    initialItems,
    initialCursor,
    resetKey,
    fetchPage,
    preferButtonOnly,
  });

  return (
    <div>
      <ul data-testid="items">
        {state.items.map((item) => (
          <li key={item.id}>{item.title}</li>
        ))}
      </ul>
      <ProgressiveLoadControls
        status={state.status}
        hasMore={state.hasMore}
        lastAppendedCount={state.lastAppendedCount}
        labels={labels}
        onLoadMore={state.loadMore}
        sentinelRef={state.sentinelRef}
        testIdPrefix="test"
      />
    </div>
  );
}

describe("useProgressiveLoad", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn(function MockIO(this: { observe: () => void; disconnect: () => void }) {
        this.observe = vi.fn();
        this.disconnect = vi.fn();
      }),
    );
  });

  it("renders the first page for crawlable SSR content", () => {
    render(
      <Harness
        initialItems={[
          { id: "a", title: "Alpha" },
          { id: "b", title: "Beta" },
        ]}
        initialCursor="c1"
        resetKey="k1"
        fetchPage={async () => ({ items: [], nextCursor: null })}
      />,
    );

    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByTestId("test-load-more")).toBeInTheDocument();
  });

  it("appends load-more results without duplicates", async () => {
    const user = userEvent.setup();
    const fetchPage = vi.fn(async (cursor: string) => {
      if (cursor === "c1") {
        return {
          items: [
            { id: "b", title: "Beta duplicate" },
            { id: "c", title: "Gamma" },
          ],
          nextCursor: null,
        };
      }
      return { items: [], nextCursor: null };
    });

    render(
      <Harness
        initialItems={[
          { id: "a", title: "Alpha" },
          { id: "b", title: "Beta" },
        ]}
        initialCursor="c1"
        resetKey="k1"
        fetchPage={fetchPage}
      />,
    );

    await user.click(screen.getByTestId("test-load-more"));

    await waitFor(() => {
      expect(screen.getByText("Gamma")).toBeInTheDocument();
    });

    const items = screen.getAllByRole("listitem").map((node) => node.textContent);
    expect(items).toEqual(["Alpha", "Beta", "Gamma"]);
    expect(screen.getByTestId("test-aria-live")).toHaveTextContent("1 more results loaded.");
    expect(screen.getByTestId("test-end-of-results")).toBeInTheDocument();
  });

  it("resets items and cursor when resetKey changes", async () => {
    const fetchPage = vi.fn(async () => ({
      items: [{ id: "z", title: "Zulu" }],
      nextCursor: null,
    }));

    function Wrapper() {
      const [resetKey, setResetKey] = useState("phones");
      const [initial, setInitial] = useState<Item[]>([{ id: "a", title: "Alpha" }]);
      return (
        <div>
          <button
            type="button"
            onClick={() => {
              setResetKey("laptops");
              setInitial([{ id: "l", title: "Laptop" }]);
            }}
          >
            Change filters
          </button>
          <Harness
            initialItems={initial}
            initialCursor="c1"
            resetKey={resetKey}
            fetchPage={fetchPage}
          />
        </div>
      );
    }

    const user = userEvent.setup();
    render(<Wrapper />);

    await user.click(screen.getByTestId("test-load-more"));
    await waitFor(() => expect(screen.getByText("Zulu")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Change filters" }));

    expect(screen.getByText("Laptop")).toBeInTheDocument();
    expect(screen.queryByText("Zulu")).not.toBeInTheDocument();
    expect(screen.getByTestId("test-load-more")).toBeInTheDocument();
  });

  it("surfaces a retryable error after a failed request", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const fetchPage = vi.fn(async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("network down");
      }
      return {
        items: [{ id: "c", title: "Gamma" }],
        nextCursor: null,
      };
    });

    render(
      <Harness
        initialItems={[{ id: "a", title: "Alpha" }]}
        initialCursor="c1"
        resetKey="k1"
        fetchPage={fetchPage}
      />,
    );

    await user.click(screen.getByTestId("test-load-more"));
    await waitFor(() => {
      expect(screen.getByTestId("test-load-error")).toHaveTextContent(
        "Couldn’t load more results.",
      );
    });

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("Gamma")).toBeInTheDocument());
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it("keeps Load more keyboard-reachable and announces via aria-live", async () => {
    const user = userEvent.setup();
    const fetchPage = vi.fn(async () => ({
      items: [
        { id: "b", title: "Beta" },
        { id: "c", title: "Gamma" },
      ],
      nextCursor: null,
    }));

    render(
      <Harness
        initialItems={[{ id: "a", title: "Alpha" }]}
        initialCursor="c1"
        resetKey="k1"
        fetchPage={fetchPage}
      />,
    );

    const button = screen.getByTestId("test-load-more");
    button.focus();
    expect(button).toHaveFocus();

    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(screen.getByTestId("test-aria-live")).toHaveTextContent("2 more results loaded.");
    });
  });

  it("ignores stale responses after abort/reset", async () => {
    let resolveFirst!: (page: ProgressivePage<Item>) => void;
    const first = new Promise<ProgressivePage<Item>>((resolve) => {
      resolveFirst = resolve;
    });

    const fetchPage = vi
      .fn()
      .mockImplementationOnce(() => first)
      .mockResolvedValueOnce({
        items: [{ id: "new", title: "Fresh" }],
        nextCursor: null,
      });

    function Wrapper() {
      const [resetKey, setResetKey] = useState("a");
      return (
        <div>
          <button type="button" onClick={() => setResetKey("b")}>
            Reset
          </button>
          <Harness
            initialItems={[{ id: "1", title: "One" }]}
            initialCursor="c1"
            resetKey={resetKey}
            fetchPage={fetchPage}
          />
        </div>
      );
    }

    const user = userEvent.setup();
    render(<Wrapper />);

    await user.click(screen.getByTestId("test-load-more"));
    await user.click(screen.getByRole("button", { name: "Reset" }));

    await act(async () => {
      resolveFirst({
        items: [{ id: "stale", title: "Stale" }],
        nextCursor: null,
      });
    });

    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
    expect(screen.getByText("One")).toBeInTheDocument();
  });
});

describe("homepage isolation", () => {
  it("does not import progressive loading into the homepage route", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const homeDir = path.resolve(__dirname, "../../page.tsx");
    // shop home is app/[locale]/(shop)/page.tsx — two levels up from progressive-load/
    const shopHome = path.resolve(__dirname, "../../page.tsx");
    void homeDir;
    const source = await fs.readFile(shopHome, "utf8");
    expect(source).not.toMatch(/useProgressiveLoad|ProgressiveLoadControls|PlpBrowseClient/);
  });
});
