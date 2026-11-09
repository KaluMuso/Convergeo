// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchFollowFeed: vi.fn() }));
vi.mock("../../../../../lib/engagement-api", () => api);
vi.mock("../../../(shop)/_components/plp/listing-grid", () => ({
  ListingGrid: ({ listings }: { listings: Array<{ title: string }> }) => (
    <ul>
      {listings.map((l) => (
        <li key={l.title}>{l.title}</li>
      ))}
    </ul>
  ),
}));

import { FollowFeedPanel } from "./follow-feed-panel";

const labels = {
  title: "Following",
  description: "New from stores you follow",
  emptyTitle: "Nothing new yet",
  emptyBody: "Follow stores",
  browseVendors: "Browse vendors",
  signIn: "Sign in to see the stores you follow",
  signInCta: "Sign in",
  loadFailed: "Couldn't load",
  retry: "Try again",
  loadMore: "Show more",
  loading: "Loading…",
  grid: {} as never,
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const item = (title: string) => ({
  id: title,
  title,
  product_slug: title,
  vendor_name: "Shop",
  price_ngwee: 1000,
  condition: "new",
  in_stock: true,
  image_public_id: null,
  rating: 0,
  review_count: 0,
  distance_m: null,
});

describe("FollowFeedPanel", () => {
  it("renders listings with a Show more control when paged", async () => {
    api.fetchFollowFeed.mockResolvedValue({
      items: [item("Solar lamp")],
      next_offset: 24,
    });
    render(<FollowFeedPanel locale="en" labels={labels} />);
    expect(await screen.findByText("Solar lamp")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Show more" }),
    ).toBeInTheDocument();
  });

  it("asks signed-out shoppers to sign in", async () => {
    api.fetchFollowFeed.mockResolvedValue("signed_out");
    render(<FollowFeedPanel locale="en" labels={labels} />);
    expect(await screen.findByText(labels.signIn)).toBeInTheDocument();
  });

  it("shows the empty state with a route to vendors", async () => {
    api.fetchFollowFeed.mockResolvedValue({ items: [], next_offset: null });
    render(<FollowFeedPanel locale="en" labels={labels} />);
    expect(await screen.findByText("Nothing new yet")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Browse vendors" }),
    ).toHaveAttribute("href", "/en/vendors");
  });
});
