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
  pickRailDepartments,
  type HomeDefaultData,
} from "./home-default";

import type { CategoryRow } from "./merch-data";
import type { CatalogListing } from "./plp/listing-grid";

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ alt }: { alt: string }) => <img alt={alt} data-testid="cloudinary-image" />,
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
  const emptyData: HomeDefaultData = { newest: [], departmentRails: [] };

  it("is false with no categories and no listings (welcome fallback)", () => {
    expect(hasDefaultHomeContent([], emptyData)).toBe(false);
  });

  it("is true when categories exist even with an empty catalog", () => {
    expect(hasDefaultHomeContent([makeCategory()], emptyData)).toBe(true);
  });

  it("is true when the new-listings rail has data", () => {
    expect(hasDefaultHomeContent([], { newest: [makeListing()], departmentRails: [] })).toBe(true);
  });

  it("is true when only a department rail has data", () => {
    expect(
      hasDefaultHomeContent([], {
        newest: [],
        departmentRails: [{ category: makeCategory(), listings: [makeListing()] }],
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

describe("HomeHeroBand", () => {
  it("renders the escrow trust messaging and both CTAs", () => {
    render(<HomeHeroBand locale="en" t={t} />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByText("You pay")).toBeInTheDocument();
    expect(screen.getByText("Held by Vergeo5")).toBeInTheDocument();
    expect(screen.getByText("Released on delivery")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start browsing" })).toHaveAttribute(
      "href",
      "/en/search",
    );
    expect(screen.getByRole("link", { name: "Sell on Vergeo5" })).toHaveAttribute(
      "href",
      "/en/sell",
    );
  });
});

describe("HomeSellCta", () => {
  it("links to the sell page", () => {
    render(<HomeSellCta locale="en" t={t} />);
    expect(screen.getByRole("link", { name: "Start selling" })).toHaveAttribute("href", "/en/sell");
  });
});
