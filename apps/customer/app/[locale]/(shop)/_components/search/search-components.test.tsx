// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const request = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams("q=phone"),
}));

vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
});

import { addRecentSearch, readRecentSearches, RecentSearches } from "./recent-searches";
import { ResultsTabs } from "./results-tabs";
import { SearchInput } from "./search-input";
import { ZeroResults } from "./zero-results";

const searchInputLabels = {
  placeholder: "Search Vergeo5",
  submit: "Search",
  ariaLabel: "Search",
  suggestionsLabel: "Search suggestions",
  noSuggestions: "No suggestions",
};

const resultsTabsLabels = {
  ariaLabel: "Filter results by type",
  all: "All",
  products: "Products",
  services: "Services",
  events: "Events",
  vendors: "Vendors",
  count: "{label} ({count})",
  resultsCount: "2 results",
  degraded: "Keyword only",
  priceFrom: "From {price}",
  category: "In {category}",
  marketplaceListing: "Marketplace listing",
  wishlist: "Save to wishlist",
  wishlistRemove: "Remove from wishlist",
  mediaEmpty: "No product image",
  noReviews: "No reviews yet",
  reviewCount: "({count})",
  loadMore: "Load more",
  loading: "Loading more…",
  moreLoaded: "{count} more results loaded.",
  endOfResults: "End of results",
  loadError: "Couldn’t load more results.",
  retry: "Retry",
};

const sampleResponse = {
  query: "phone",
  expanded_query: "phone",
  page: 1,
  page_size: 20,
  total: 2,
  degraded: false,
  results: [
    {
      id: "1",
      entity_kind: "product",
      entity_id: "prod-1",
      title: "Itel A70 Smartphone",
      body: "Budget smartphone",
      category_path: "electronics/phones",
      price_min_ngwee: 450000,
      price_max_ngwee: 450000,
      lat: null,
      lng: null,
      locale_terms: null,
      boost_signals: {},
      rrf_score: 1,
      slug: "itel-a70",
    },
    {
      id: "2",
      entity_kind: "vendor",
      entity_id: "vendor-1",
      title: "Phone Hub Lusaka",
      body: null,
      category_path: null,
      price_min_ngwee: null,
      price_max_ngwee: null,
      lat: null,
      lng: null,
      locale_terms: null,
      boost_signals: {},
      rrf_score: 0.8,
      slug: "phone-hub-lusaka",
    },
  ],
};

describe("SearchInput autocomplete", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    request.mockResolvedValue({
      query: "ite",
      suggestions: [
        { title: "Itel A70 Smartphone", entity_kind: "product", entity_id: "prod-1" },
        { title: "Itel accessories", entity_kind: "product", entity_id: "prod-2" },
      ],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces suggest requests and supports keyboard selection", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SearchInput locale="en" labels={searchInputLabels} />);

    const input = screen.getByRole("searchbox");
    await user.type(input, "ite");

    expect(request).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(200);

    await waitFor(() => {
      expect(request).toHaveBeenCalledWith("/search/suggest?q=ite&limit=8");
    });

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    await user.keyboard("{Enter}");

    expect(push).toHaveBeenCalledWith("/en/search?q=Itel%20A70%20Smartphone");
  });
});

describe("ResultsTabs tab counts", () => {
  it("renders tab labels with counts", () => {
    render(
      <ResultsTabs
        locale="en"
        query="phone"
        activeKind="all"
        page={1}
        response={sampleResponse}
        tabCounts={{
          all: 5,
          products: 2,
          services: 1,
          events: 0,
          vendors: 1,
        }}
        labels={resultsTabsLabels}
        apiBaseUrl="https://api.example.test"
      />,
    );

    expect(screen.getByTestId("search-tab-all")).toHaveTextContent("All (5)");
    expect(screen.getByTestId("search-tab-products")).toHaveTextContent("Products (2)");
    expect(screen.getByTestId("search-tab-events")).toHaveTextContent("Events (0)");
    expect(screen.getByTestId("search-results-list")).toBeInTheDocument();
    expect(screen.getByTestId("search-product-grid")).toHaveClass(
      "gap-2",
      "lg:grid-cols-4",
      "xl:grid-cols-5",
    );
    expect(screen.getByTestId("search-result-row")).toHaveClass("p-2.5");
    // Search → PDP must use the public slug, never the entity UUID.
    expect(screen.getByTestId("search-product-card-link")).toHaveAttribute(
      "href",
      "/en/p/itel-a70",
    );
    expect(screen.getByRole("heading", { name: "Itel A70 Smartphone" })).toBeInTheDocument();
    // Wholesale supplies are a B2B-gated surface (own /supplies page), not a
    // global-search tab — it must not render here.
    expect(screen.queryByTestId("search-tab-supplies")).not.toBeInTheDocument();
  });

  it("appends the next search page without router navigation", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        query: "phone",
        expanded_query: "phone",
        page: 2,
        page_size: 2,
        total: 3,
        degraded: false,
        results: [
          {
            id: "3",
            entity_kind: "product",
            entity_id: "prod-3",
            title: "Extra Phone",
            body: null,
            category_path: null,
            price_min_ngwee: 1000,
            price_max_ngwee: 1000,
            lat: null,
            lng: null,
            locale_terms: null,
            boost_signals: {},
            rrf_score: 0.5,
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <ResultsTabs
        locale="en"
        query="phone"
        activeKind="all"
        page={1}
        response={{
          ...sampleResponse,
          page_size: 2,
          total: 3,
        }}
        tabCounts={{
          all: 3,
          products: 2,
          services: 0,
          events: 0,
          vendors: 1,
        }}
        labels={resultsTabsLabels}
        apiBaseUrl="https://api.example.test"
      />,
    );

    expect(screen.getByTestId("search-load-more")).toBeInTheDocument();
    await user.click(screen.getByTestId("search-load-more"));

    await waitFor(() => {
      expect(screen.getByText("Extra Phone")).toBeInTheDocument();
    });
    expect(push).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/search?q=phone&page=2&page_size=2",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByTestId("search-end-of-results")).toBeInTheDocument();
  });
});

describe("ZeroResults", () => {
  it("renders category suggestions and Ask Vergeo teaser slot", () => {
    render(
      <ZeroResults
        query="zzzz-no-match"
        locale="en"
        labels={{
          title: 'No results for "zzzz-no-match"',
          suggestionsTitle: "Try searching for",
          categoriesTitle: "Browse categories",
          suggestionTerms: ["chitenge", "kitchenware"],
          categories: [
            { key: "electronics", href: "/en/c/electronics", label: "Electronics" },
            { key: "fashion", href: "/en/c/fashion-beauty", label: "Fashion & beauty" },
          ],
          askVergeoTitle: "Ask Vergeo",
          askVergeoTeaser: "Not sure what to search?",
          askVergeoSlotLabel: "Ask Vergeo assistant slot",
        }}
      />,
    );

    expect(screen.getByTestId("search-zero-results")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "chitenge" })).toHaveAttribute(
      "href",
      "/en/search?q=chitenge",
    );
    expect(screen.getByRole("link", { name: "Electronics" })).toHaveAttribute(
      "href",
      "/en/c/electronics",
    );
    expect(screen.getByTestId("ask-vergeo-slot")).toHaveAttribute(
      "aria-label",
      "Ask Vergeo assistant slot",
    );
  });
});

describe("Recent searches localStorage", () => {
  it("persists and renders recent searches", async () => {
    addRecentSearch("chitenge");
    addRecentSearch("itel");

    expect(readRecentSearches()).toEqual(["itel", "chitenge"]);

    render(
      <RecentSearches
        locale="en"
        labels={{ title: "Recent searches", clear: "Clear all", remove: "Remove {term}" }}
      />,
    );

    expect(screen.getByRole("link", { name: "itel" })).toHaveAttribute("href", "/en/search?q=itel");
    expect(screen.getByRole("link", { name: "chitenge" })).toBeInTheDocument();
  });
});

describe("search i18n messages", () => {
  it("loads nested search namespace keys", async () => {
    const { loadNamespace, clearMessageCache } = await import("@vergeo/i18n");
    clearMessageCache();
    const messages = (await loadNamespace("en", "search")) as {
      placeholder?: string;
      tabs?: { all?: string };
      askVergeo?: { slotLabel?: string };
    };

    expect(messages.placeholder).toBe("Search Vergeo5");
    expect(messages.tabs?.all).toBe("All");
    expect(messages.askVergeo?.slotLabel).toBe("Ask Vergeo assistant slot");
    expect(Object.keys(messages).some((key) => key.includes("."))).toBe(false);
  });
});
