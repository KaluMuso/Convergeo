// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../../packages/i18n/messages/en/catalog.json";

import { recordAdEvent, resetAdEventsForTest } from "./ad-events";
import { FeedSectionView } from "./feed-section";
import {
  isRenderableSection,
  localizeHref,
  resolveSectionTitle,
  type FeedLabels,
  type FeedSection,
} from "./feed-types";
import { buildFeedLabels, HomeFeed } from "./home-feed";

vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.test${path}`,
}));

vi.mock("../../../../../lib/customer-session", () => ({
  getReadyCustomerSession: async () => null,
}));

const fetchFeedPage = vi.fn();
vi.mock("./feed-pages", async () => {
  const actual = await vi.importActual<typeof import("./feed-pages")>("./feed-pages");
  return { ...actual, fetchFeedPage: (...args: unknown[]) => fetchFeedPage(...args) };
});

const t = createTranslator({
  locale: "en",
  messages: { catalog: catalogMessages },
  namespace: "catalog",
}) as unknown as Parameters<typeof buildFeedLabels>[0];

const labels: FeedLabels = buildFeedLabels(t, {
  vendor: "By {vendor}",
  noReviews: "No reviews",
  reviewCount: "({count})",
  quickAdd: "Add",
  wishlist: "Save",
  outOfStock: "Out of stock",
});

function section(overrides: Partial<FeedSection>): FeedSection {
  return {
    id: "s1",
    key: "under_k100",
    section_type: "rule",
    layout: "rail",
    title: null,
    title_key: "home.feed.sections.underK100",
    view_all_href: "/c/all",
    listings: [],
    services: [],
    events: [],
    vendors: [],
    ad: null,
    explanation: null,
    ...overrides,
  };
}

const listing = {
  id: "l1",
  title: "Phone case",
  product_slug: "phone-case",
  vendor_name: "Shop",
  price_ngwee: 8000,
  condition: "new",
  in_stock: true,
  image_public_id: null,
  rating: 0,
  review_count: 0,
  distance_m: null,
};

const ad = {
  placement_id: "11111111-1111-4111-8111-111111111111",
  advertiser_name: "Acme",
  image_public_id: "ads/acme",
  headline: "Acme sale",
  body: null,
  cta_label: null,
  cta_href: "/c/electronics",
  external: false,
  sponsored: true,
};

class FakeObserver {
  static instances: FakeObserver[] = [];
  constructor(public cb: IntersectionObserverCallback) {
    FakeObserver.instances.push(this);
  }
  observe() {}
  disconnect() {}
  trigger() {
    this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this as never);
  }
}

beforeEach(() => {
  FakeObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  resetAdEventsForTest();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  fetchFeedPage.mockReset();
});

describe("feed-types helpers", () => {
  it("resolves admin text before i18n keys", () => {
    expect(resolveSectionTitle(section({}), labels)).toBe("Cheap finds under K100");
    expect(resolveSectionTitle(section({ title: "Custom" }), labels)).toBe("Custom");
    expect(resolveSectionTitle(section({ title_key: "unknown.key" }), labels)).toBeNull();
  });

  it("locale-prefixes internal links and passes external through", () => {
    expect(localizeHref("/c/all", "fr")).toBe("/fr/c/all");
    expect(localizeHref("/en/c/all", "fr")).toBe("/en/c/all");
    expect(localizeHref("https://acme.co.zm", "en")).toBe("https://acme.co.zm");
  });

  it("treats empty sections and creative-less ad slots as non-renderable", () => {
    expect(isRenderableSection(section({}))).toBe(false);
    expect(isRenderableSection(section({ section_type: "ad_slot", layout: "ad" }))).toBe(false);
    expect(isRenderableSection(section({ listings: [listing] }))).toBe(true);
  });
});

describe("FeedSectionView", () => {
  it("renders a listing rail with localized view-all", () => {
    render(
      <FeedSectionView section={section({ listings: [listing] })} locale="en" labels={labels} />,
    );
    expect(screen.getByRole("heading", { name: "Cheap finds under K100" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: labels.viewAll })).toHaveAttribute("href", "/en/c/all");
  });

  it("marks sponsored placements accessibly and counts impression + click", () => {
    const sendBeacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon, onLine: true });
    vi.useFakeTimers();
    render(
      <FeedSectionView
        section={section({ section_type: "ad_slot", layout: "ad", ad })}
        locale="en"
        labels={labels}
      />,
    );
    const link = screen.getByRole("link", { name: /Sponsored: Acme sale/ });
    expect(link).toHaveAttribute("href", "/en/c/electronics");
    expect(screen.getByText("Sponsored")).toBeInTheDocument();
    act(() => FakeObserver.instances[0]?.trigger());
    link.addEventListener("click", (event) => event.preventDefault());
    fireEvent.click(link);
    vi.runAllTimers();
    vi.useRealTimers();
    const bodies = sendBeacon.mock.calls.map((call) => (call as unknown[])[0]);
    expect(bodies.every((url) => url === "https://api.test/home/ads/events")).toBe(true);
    expect(sendBeacon).toHaveBeenCalled();
  });

  it("dedupes impressions per placement", () => {
    const sendBeacon = vi.fn(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon, onLine: true });
    vi.useFakeTimers();
    recordAdEvent("p1", "impression");
    recordAdEvent("p1", "impression");
    vi.runAllTimers();
    vi.useRealTimers();
    expect(sendBeacon).toHaveBeenCalledTimes(1);
  });
});

describe("HomeFeed infinite loading", () => {
  it("loads the next page when the sentinel intersects and shows an end state", async () => {
    fetchFeedPage.mockResolvedValueOnce({
      sections: [
        section({ id: "s2", key: "trending_now", title: "Trending", listings: [listing] }),
      ],
      carousel: [],
      next_cursor: null,
    });
    render(
      <HomeFeed
        page={{ sections: [section({ listings: [listing] })], carousel: [], next_cursor: "v1.4" }}
        locale="en"
        labels={labels}
      />,
    );
    expect(screen.queryByTestId("home-feed-end")).not.toBeInTheDocument();
    await act(async () => FakeObserver.instances.at(-1)?.trigger());
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Trending" })).toBeInTheDocument(),
    );
    expect(fetchFeedPage).toHaveBeenCalledWith("v1.4", "en", null);
    expect(screen.getByTestId("home-feed-end")).toHaveTextContent(labels.end);
  });

  it("offers retry after a failed page load", async () => {
    fetchFeedPage.mockRejectedValueOnce(new Error("boom"));
    render(
      <HomeFeed
        page={{ sections: [section({ listings: [listing] })], carousel: [], next_cursor: "v1.4" }}
        locale="en"
        labels={labels}
      />,
    );
    await act(async () => FakeObserver.instances.at(-1)?.trigger());
    await waitFor(() => expect(screen.getByText(labels.loadError)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: labels.retry })).toBeInTheDocument();
  });
});
