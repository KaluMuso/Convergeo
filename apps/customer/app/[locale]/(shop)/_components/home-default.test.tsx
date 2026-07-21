// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

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
    <img alt={alt} data-testid="cloudinary-image" />
  ),
}));

afterEach(() => {
  cleanup();
});

const t = createTranslator({
  locale: "en",
  messages: { catalog: catalogMessages },
  namespace: "catalog",
}) as unknown as (key: string, values?: Record<string, string | number>) => string;

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
  distance: "{distance} away",
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
  it("renders brand-first merch hero with CTAs and no escrow pill row", () => {
    render(<HomeHeroBand locale="en" t={t} brandName="Vergeo5" />);
    expect(screen.getByTestId("home-hero-brand")).toHaveTextContent("Vergeo5");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Shop products, services, and events/i,
    );
    expect(screen.getByTestId("home-hero-visual")).toBeInTheDocument();
    expect(screen.queryByTestId("cloudinary-image")).not.toBeInTheDocument();
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

  it("matches the approved merch-first hero structure snapshot", () => {
    const { container } = render(<HomeHeroBand locale="en" t={t} brandName="Vergeo5" />);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("uses a full-bleed catalogue image when a public id is provided", () => {
    render(
      <HomeHeroBand
        locale="en"
        t={t}
        brandName="Vergeo5"
        visualPublicId="demo/categories/phones"
      />,
    );
    expect(screen.getByTestId("cloudinary-image")).toBeInTheDocument();
    expect(screen.getByTestId("home-hero-brand")).toHaveTextContent("Vergeo5");
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
