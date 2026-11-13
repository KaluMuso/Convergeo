// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadStreamPage, HomeStreamClient, type StreamFetcher } from "./home-stream-client";

import type { FeedLabels, FeedListingWire, HomeStreamPage } from "./feed-types";

vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.test${path}`,
}));

const cardLabels: FeedLabels["card"] = {
  vendor: "By {vendor}",
  noReviews: "No reviews",
  reviewCount: "({count})",
  quickAdd: "Add",
  wishlist: "Save",
  outOfStock: "Out of stock",
};

const labels = {
  loadMore: "Load more",
  loading: "Loading…",
  moreLoaded: "{count} more items loaded.",
  endOfResults: "You're all caught up",
  loadError: "Couldn't load more right now.",
  retry: "Try again",
};

function listing(id: string): FeedListingWire {
  return {
    id,
    title: `Title ${id}`,
    product_slug: `slug-${id}`,
    vendor_name: "Shop",
    price_ngwee: 12_300,
    condition: "new",
    in_stock: true,
    image_public_id: null,
    rating: 0,
    review_count: 0,
    distance_m: null,
  };
}

function page(ids: string[], next: string | null): HomeStreamPage {
  return { items: ids.map(listing), next_cursor: next };
}

type ObserverRecord = { callback: IntersectionObserverCallback; disconnect: () => void };
let observers: ObserverRecord[] = [];

function installObserver() {
  observers = [];
  class FakeObserver {
    constructor(callback: IntersectionObserverCallback) {
      const record = { callback, disconnect: vi.fn() };
      observers.push(record);
      this.disconnect = record.disconnect;
    }
    observe = vi.fn();
    unobserve = vi.fn();
    takeRecords = () => [];
    disconnect: () => void;
  }
  vi.stubGlobal("IntersectionObserver", FakeObserver);
}

/** Fire the most recent observer as if the sentinel entered the viewport. */
async function intersect() {
  const latest = observers[observers.length - 1];
  if (!latest) throw new Error("no IntersectionObserver registered");
  await act(async () => {
    latest.callback(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
  });
}

function mount(fetcher: StreamFetcher, props: { cursor?: string | null; seen?: string[] } = {}) {
  return render(
    <HomeStreamClient
      initialCursor={props.cursor === undefined ? "c1" : props.cursor}
      seenIds={props.seen ?? ["ssr-1"]}
      locale="en"
      cardLabels={cardLabels}
      labels={labels}
      fetcher={fetcher}
    >
      <div data-testid="ssr-batch">server rendered</div>
    </HomeStreamClient>,
  );
}

beforeEach(() => {
  installObserver();
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("HomeStreamClient", () => {
  it("renders the server batch and fetches nothing until the sentinel intersects", () => {
    const fetcher = vi.fn<StreamFetcher>();
    mount(fetcher);
    expect(screen.getByTestId("ssr-batch")).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByTestId("home-stream-load-sentinel")).toBeInTheDocument();
  });

  it("loads the next page when the sentinel intersects and announces the count", async () => {
    const fetcher = vi.fn<StreamFetcher>().mockResolvedValue(page(["a", "b", "c"], "c2"));
    mount(fetcher);
    await intersect();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[0]).toBe("c1");
    expect(await screen.findByText("Title a")).toBeInTheDocument();
    expect(screen.getByText("Title c")).toBeInTheDocument();
    expect(screen.getByTestId("home-stream-aria-live")).toHaveTextContent("3 more items loaded.");
    // More pages remain: the keyboard-reachable button is still there.
    expect(screen.getByTestId("home-stream-load-more")).toBeEnabled();
  });

  it("shows a skeleton while a page is in flight", async () => {
    let resolve: (value: HomeStreamPage) => void = () => undefined;
    const fetcher = vi.fn<StreamFetcher>().mockReturnValue(
      new Promise<HomeStreamPage>((r) => {
        resolve = r;
      }),
    );
    mount(fetcher);
    await intersect();
    expect(await screen.findByTestId("home-stream-skeleton")).toBeInTheDocument();
    await act(async () => resolve(page(["a"], null)));
    await waitFor(() => expect(screen.queryByTestId("home-stream-skeleton")).toBeNull());
  });

  it("surfaces an error with a retry button that refetches the same cursor", async () => {
    const fetcher = vi
      .fn<StreamFetcher>()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce(page(["a"], null));
    const user = userEvent.setup();
    mount(fetcher);
    await intersect();
    expect(await screen.findByTestId("home-stream-load-error")).toHaveTextContent(
      "Couldn't load more right now.",
    );
    const retry = screen.getByRole("button", { name: "Try again" });
    await user.click(retry);
    expect(await screen.findByText("Title a")).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1]?.[0]).toBe("c1");
  });

  it("shows the end-of-feed message and no Load more once the cursor is exhausted", async () => {
    const fetcher = vi.fn<StreamFetcher>().mockResolvedValue(page(["z"], null));
    mount(fetcher);
    await intersect();
    expect(await screen.findByText("Title z")).toBeInTheDocument();
    expect(screen.getByTestId("home-stream-end-of-results")).toHaveTextContent(
      "You're all caught up",
    );
    expect(screen.queryByTestId("home-stream-load-more")).toBeNull();
  });

  it("is already at the end when the server batch had no next cursor", () => {
    mount(vi.fn<StreamFetcher>(), { cursor: null });
    expect(screen.getByTestId("home-stream-end-of-results")).toBeInTheDocument();
    expect(screen.queryByTestId("home-stream-load-more")).toBeNull();
  });

  it("falls back to the Load more button when IntersectionObserver is unavailable", async () => {
    delete (globalThis as { IntersectionObserver?: unknown }).IntersectionObserver;
    const fetcher = vi.fn<StreamFetcher>().mockResolvedValue(page(["a"], "c2"));
    const user = userEvent.setup();
    mount(fetcher);
    expect(fetcher).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Title a")).toBeInTheDocument();
  });

  it("does not auto-load under data saver but keeps the Load more button", async () => {
    vi.stubGlobal("navigator", { ...window.navigator, connection: { saveData: true } });
    const fetcher = vi.fn<StreamFetcher>().mockResolvedValue(page(["a"], null));
    mount(fetcher);
    await act(async () => undefined);
    // Any observer created before the flag resolved must be disconnected again.
    expect(
      observers.every(
        (record) => (record.disconnect as ReturnType<typeof vi.fn>).mock.calls.length > 0,
      ),
    ).toBe(true);
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Load more" })).toBeEnabled();
  });
});

describe("loadStreamPage", () => {
  const signal = new AbortController().signal;

  it("drops listings already shown above", async () => {
    const fetcher = vi.fn<StreamFetcher>().mockResolvedValue(page(["x", "y"], "n"));
    const result = await loadStreamPage(fetcher, "c", signal, new Set(["x"]));
    expect(result.items.map((i) => i.id)).toEqual(["y"]);
    expect(result.nextCursor).toBe("n");
  });

  it("keeps walking when a whole page is duplicates so the observer never stalls", async () => {
    const fetcher = vi
      .fn<StreamFetcher>()
      .mockResolvedValueOnce(page(["x"], "c2"))
      .mockResolvedValueOnce(page(["fresh"], "c3"));
    const result = await loadStreamPage(fetcher, "c1", signal, new Set(["x"]));
    expect(fetcher.mock.calls.map((call) => call[0])).toEqual(["c1", "c2"]);
    expect(result.items.map((i) => i.id)).toEqual(["fresh"]);
    expect(result.nextCursor).toBe("c3");
  });

  it("stops when the cursor ends on an all-duplicate page", async () => {
    const fetcher = vi.fn<StreamFetcher>().mockResolvedValue(page(["x"], null));
    const result = await loadStreamPage(fetcher, "c1", signal, new Set(["x"]));
    expect(result).toEqual({ items: [], nextCursor: null });
  });
});
