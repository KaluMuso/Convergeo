// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createTranslator, NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";

import {
  hasDefaultHomeContent,
  HomeHeroBand,
  HomeProductRail,
  HomeSellCta,
  HomeServicesRail,
  HomeVendorsRail,
  pickHeroVisualPublicId,
  pickRailDepartments,
  type HomeDefaultData,
} from "./home-default";

import type { CategoryRow } from "./merch-data";
import type { CatalogListing } from "./plp/listing-grid";

vi.mock("@vergeo/ui/src/media/cloudinary-image-static", () => ({
  CloudinaryImageStatic: ({ alt }: { alt: string }) => (
    <img alt={alt} data-testid="cloudinary-image-static" />
  ),
}));

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({
    alt,
    priority,
    publicId,
  }: {
    alt: string;
    priority?: boolean;
    publicId?: string;
  }) => (
    <img
      alt={alt}
      data-testid="cloudinary-image"
      data-priority={priority ? "true" : "false"}
      data-public-id={publicId}
    />
  ),
}));

function mockMatchMedia(matches: Record<string, boolean> = {}) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: matches[query] ?? false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  mockMatchMedia();
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

const t = createTranslator({
  locale: "en",
  messages: { catalog: catalogMessages },
  namespace: "catalog",
}) as unknown as (key: string, values?: Record<string, string | number>) => string;

function renderHomeHeroBand(props: {
  locale: string;
  t: (key: string, values?: Record<string, string | number>) => string;
  brandName: string;
  visualPublicId?: string | null;
}) {
  return render(
    <NextIntlClientProvider locale="en" messages={{ catalog: catalogMessages }} onError={() => {}}>
      <HomeHeroBand {...props} />
    </NextIntlClientProvider>,
  );
}

function makeCategory(overrides: Partial<CategoryRow> = {}): CategoryRow {
  return {
    id: "cat-1",
    name: "Electronics",
    slug: "electronics",
    path: "electronics",
    position: 0,
    parent_id: null,
    prohibited: false,
    ...overrides,
  };
}

function makeListing(overrides: Partial<CatalogListing> = {}): CatalogListing {
  return {
    id: "listing-1",
    title: "itel A70",
    productSlug: "itel-a70",
    vendorName: "Kabwata Electronics",
    priceNgwee: 129900,
    condition: "new",
    inStock: true,
    imagePublicId: null,
    rating: 0,
    reviewCount: 0,
    distanceM: null,
    belowMedian: false,
    deliveryAvailable: false,
    pickupAvailable: false,
    ...overrides,
  };
}

const railLabels = {
  vendor: "Sold by {vendor}",
  noReviews: "No reviews yet",
  reviewCount: "{count} reviews",
  quickAdd: "Quick add",
  wishlist: "Save",
  outOfStock: "Out of stock",
  logistics: {
    nearest: "{distance} away",
    belowMedian: "Below median",
    delivery: "Lusaka delivery",
    pickup: "Pickup available",
  },
};

describe("pickRailDepartments", () => {
  it("takes at most three departments, preserving order", () => {
    const categories = ["a", "b", "c", "d"].map((slug, index) =>
      makeCategory({ id: slug, slug, path: slug, position: index }),
    );
    expect(pickRailDepartments(categories).map((category) => category.id)).toEqual(["a", "b", "c"]);
  });

  it("is empty-safe", () => {
    expect(pickRailDepartments([])).toEqual([]);
  });
});

describe("hasDefaultHomeContent", () => {
  const emptyData: HomeDefaultData = {
    newest: [],
    departmentRails: [],
    services: [],
    topVendors: [],
  };

  it("is false with no categories and no listings (welcome fallback)", () => {
    expect(hasDefaultHomeContent([], emptyData)).toBe(false);
  });

  it("is true when categories exist even with an empty catalog", () => {
    expect(hasDefaultHomeContent([makeCategory()], emptyData)).toBe(true);
  });

  it("is true when the new-listings rail has data", () => {
    expect(
      hasDefaultHomeContent([], {
        newest: [makeListing()],
        departmentRails: [],
        services: [],
        topVendors: [],
      }),
    ).toBe(true);
  });

  it("is true when only a department rail has data", () => {
    expect(
      hasDefaultHomeContent([], {
        newest: [],
        departmentRails: [{ category: makeCategory(), listings: [makeListing()] }],
        services: [],
        topVendors: [],
      }),
    ).toBe(true);
  });
});

describe("HomeProductRail", () => {
  it("renders nothing for an empty rail (no broken section)", () => {
    const { container } = render(
      <HomeProductRail
        id="home-rail-new"
        title="New on Vergeo5"
        viewAllHref="/en/c/all"
        viewAllLabel="View all"
        listings={[]}
        locale="en"
        labels={railLabels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders heading, view-all link and product cards when populated", () => {
    render(
      <HomeProductRail
        id="home-rail-new"
        title="New on Vergeo5"
        viewAllHref="/en/c/all"
        viewAllLabel="View all"
        listings={[makeListing()]}
        locale="en"
        labels={railLabels}
      />,
    );
    expect(screen.getByRole("heading", { name: "New on Vergeo5" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all" })).toHaveAttribute("href", "/en/c/all");
    expect(screen.getByTestId("product-card")).toBeInTheDocument();
  });
});

describe("pickHeroVisualPublicId", () => {
  it("returns the first listing public id and skips empty ids", () => {
    expect(pickHeroVisualPublicId([])).toBeNull();
    expect(
      pickHeroVisualPublicId([
        makeListing({ imagePublicId: null }),
        makeListing({ id: "2", imagePublicId: "  " }),
        makeListing({ id: "3", imagePublicId: "demo/categories/phones" }),
      ]),
    ).toBe("demo/categories/phones");
  });
});

describe("HomeHeroBand", () => {
  it("renders brand-first carousel hero with CTAs and no escrow pill row", () => {
    renderHomeHeroBand({ locale: "en", t, brandName: "Vergeo5" });
    expect(screen.getByTestId("home-hero-band")).toBeInTheDocument();
    expect(screen.getByTestId("hero-carousel")).toHaveAttribute("role", "region");
    expect(screen.getByTestId("hero-carousel")).toHaveAttribute("aria-roledescription", "carousel");
    expect(screen.getByTestId("home-hero-brand")).toHaveTextContent("Vergeo5");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Shop products, services, and events/i,
    );
    expect(screen.getAllByTestId("cloudinary-image").length).toBeGreaterThan(0);
    expect(screen.queryByText("You pay")).not.toBeInTheDocument();
    expect(screen.queryByText("Held by Vergeo5")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start browsing" })).toHaveAttribute(
      "href",
      "/en/search",
    );
    expect(screen.getByRole("link", { name: "Learn about selling" })).toHaveAttribute(
      "href",
      "/en/sell",
    );
  });

  it("uses curated fallback slides with priority on the first image", () => {
    renderHomeHeroBand({ locale: "en", t, brandName: "Vergeo5" });
    const images = screen.getAllByTestId("cloudinary-image");
    expect(images[0]).toHaveAttribute("data-priority", "true");
    expect(images[0]).toHaveAttribute("data-public-id", "demo/categories/mobile-phones");
    expect(images.slice(1).every((image) => image.getAttribute("data-priority") === "false")).toBe(
      true,
    );
  });

  it("uses live catalogue imagery on slide 1 when visualPublicId is provided", () => {
    renderHomeHeroBand({
      locale: "en",
      t,
      brandName: "Vergeo5",
      visualPublicId: "vendors/acme/listing-hero",
    });
    const images = screen.getAllByTestId("cloudinary-image");
    expect(images[0]).toHaveAttribute("data-public-id", "vendors/acme/listing-hero");
    expect(images[1]).toHaveAttribute("data-public-id", "demo/categories/traditional-wear");
  });
});

describe("HomeSellCta", () => {
  it("links to the sell page with invite-only messaging", () => {
    render(<HomeSellCta locale="en" t={t} />);
    expect(
      screen.getByRole("heading", { name: "Selling on Vergeo5 is invite-only for now" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Public self-service signup is not open yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Learn about selling" })).toHaveAttribute(
      "href",
      "/en/sell",
    );
  });
});

const servicesRailLabels = {
  provider: "By {provider}",
  fromPrice: "From",
  noReviews: "New provider",
  view: "View service",
};

const vendorsRailLabels = {
  listings: "Products",
  reviews: "Reviews",
  rating: "{rating} ({count})",
  noReviews: "New",
  preferred: "Preferred",
  verified: "Verified",
  location: "Zambia",
  view: "Visit store",
};

describe("HomeServicesRail", () => {
  it("renders nothing for an empty rail", () => {
    const { container } = render(
      <HomeServicesRail
        id="home-rail-services"
        title="Services near you"
        viewAllHref="/en/services"
        viewAllLabel="View all"
        services={[]}
        locale="en"
        labels={servicesRailLabels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a service card and view-all link when populated", () => {
    render(
      <HomeServicesRail
        id="home-rail-services"
        title="Services near you"
        viewAllHref="/en/services"
        viewAllLabel="View all"
        services={[
          {
            id: "s1",
            slug: "deep-clean",
            title: "Deep clean",
            providerName: "SparkleCo",
            fromNgwee: 50000,
            imagePublicId: null,
          },
        ]}
        locale="en"
        labels={servicesRailLabels}
      />,
    );
    expect(screen.getByRole("heading", { name: "Services near you" })).toBeInTheDocument();
    expect(screen.getByTestId("service-card")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all" })).toHaveAttribute("href", "/en/services");
  });
});

describe("HomeVendorsRail", () => {
  it("renders nothing for an empty rail", () => {
    const { container } = render(
      <HomeVendorsRail
        id="home-rail-vendors"
        title="Top vendors"
        viewAllHref="/en/directory"
        viewAllLabel="View all"
        vendors={[]}
        locale="en"
        labels={vendorsRailLabels}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a vendor card when populated", () => {
    render(
      <HomeVendorsRail
        id="home-rail-vendors"
        title="Top vendors"
        viewAllHref="/en/directory"
        viewAllLabel="View all"
        vendors={[
          {
            id: "v1",
            slug: "kabwata",
            displayName: "Kabwata Electronics",
            logoUrl: null,
            preferredBadge: true,
            verified: true,
            landmark: "Lusaka",
            categories: ["electronics"],
            ratingAvg: 4.6,
            ratingCount: 12,
            listingCount: 30,
          },
        ]}
        locale="en"
        labels={vendorsRailLabels}
      />,
    );
    expect(screen.getByRole("heading", { name: "Top vendors" })).toBeInTheDocument();
    expect(screen.getByTestId("vendor-card")).toBeInTheDocument();
  });
});
