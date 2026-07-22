// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createTranslator, NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";

import { HomeHeroBand, HomeProductRail, type HomeDefaultData } from "./home-default";
import { planHomeLayout, resolveHomeLayoutMode } from "./home-layout";
import {
  hasEffectiveMerchConfig,
  isPlaceholderHeroSlot,
  type CategoryRow,
  type MerchSlotRow,
} from "./merch-data";

import type { CatalogListing } from "./plp/listing-grid";

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: ({ alt }: { alt: string }) => <img alt={alt} data-testid="cloudinary-image" />,
}));

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const t = createTranslator({
  locale: "en",
  messages: { catalog: catalogMessages },
  namespace: "catalog",
}) as unknown as (key: string, values?: Record<string, string | number>) => string;

const OPERATIONAL_PLACEHOLDER_TITLE = "Welcome to Vergeo5";
const OPERATIONAL_PLACEHOLDER_SUBTITLE =
  "Your config-driven storefront will appear here as merchandising slots go live.";
const BUYER_FALLBACK_TITLE = "Shop products, services, and events across Zambia";

function makeSeedPlaceholderHero(overrides: Partial<MerchSlotRow> = {}): MerchSlotRow {
  return {
    id: "seed-hero",
    slot_key: "hero",
    variant_key: "editorial-light",
    payload: {
      title_key: "merch.hero.placeholder.title",
      subtitle_key: "merch.hero.placeholder.subtitle",
    },
    schedule_from: "2026-01-01T00:00:00.000Z",
    schedule_to: null,
    position: 0,
    active: true,
    ...overrides,
  };
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

const emptyDefaultData: HomeDefaultData = {
  newest: [],
  departmentRails: [],
  services: [],
  topVendors: [],
};

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

describe("placeholder-only merchandising detection", () => {
  it("identifies the migration seed hero as a placeholder slot", () => {
    expect(isPlaceholderHeroSlot(makeSeedPlaceholderHero())).toBe(true);
    expect(hasEffectiveMerchConfig([makeSeedPlaceholderHero()])).toBe(false);
  });

  it("treats a real hero campaign as effective merch config", () => {
    const campaignHero = makeSeedPlaceholderHero({
      payload: {
        title_key: "home.hero.fallbackTitle",
        subtitle_key: "home.hero.fallbackSubtitle",
        image_public_id: "campaign/summer-sale",
      },
    });

    expect(isPlaceholderHeroSlot(campaignHero)).toBe(false);
    expect(hasEffectiveMerchConfig([campaignHero])).toBe(true);
  });

  it("uses hybrid when a campaign module exists alongside catalogue rails", () => {
    const slots = [
      makeSeedPlaceholderHero(),
      {
        id: "flash-1",
        slot_key: "flash_deal",
        variant_key: "default",
        payload: { ends_at: "2030-12-31T23:59:59.000Z", headline: "Flash sale" },
        schedule_from: null,
        schedule_to: null,
        position: 1,
        active: true,
      },
    ];
    const now = new Date("2026-07-09T12:00:00.000Z");

    expect(hasEffectiveMerchConfig(slots, now)).toBe(true);
    const plan = planHomeLayout(
      slots,
      [makeCategory()],
      { ...emptyDefaultData, newest: [makeListing()] },
      now,
    );
    expect(plan.mode).toBe("hybrid");
    expect(plan.showDefaultRails).toBe(true);
    expect(plan.campaignSectionKeys).toContain("flash_deal");
    expect(plan.campaignSectionKeys).not.toContain("hero");
    expect(plan.useDefaultHero).toBe(true);
  });
});

describe("resolveHomeLayoutMode", () => {
  it("uses the data-driven default when only the seed placeholder hero exists and listings are available", () => {
    const mode = resolveHomeLayoutMode([makeSeedPlaceholderHero()], [makeCategory()], {
      ...emptyDefaultData,
      newest: [makeListing()],
    });

    expect(mode).toBe("default");
  });

  it("falls back to hero-only when the catalogue is fully empty", () => {
    expect(resolveHomeLayoutMode([makeSeedPlaceholderHero()], [], emptyDefaultData)).toBe(
      "hero-only",
    );
  });

  it("uses hero-only when there are no slots and no catalogue content", () => {
    expect(resolveHomeLayoutMode([], [], emptyDefaultData)).toBe("hero-only");
  });

  it("uses default when categories exist even without listings", () => {
    expect(
      resolveHomeLayoutMode([makeSeedPlaceholderHero()], [makeCategory()], emptyDefaultData),
    ).toBe("default");
  });
});

describe("default homepage storefront rendering", () => {
  it("renders buyer merch hero and a product rail for placeholder-only seed config", () => {
    const mode = resolveHomeLayoutMode([makeSeedPlaceholderHero()], [makeCategory()], {
      ...emptyDefaultData,
      newest: [makeListing()],
    });
    expect(mode).toBe("default");

    render(
      <NextIntlClientProvider
        locale="en"
        messages={{ catalog: catalogMessages }}
        onError={() => {}}
      >
        <HomeHeroBand locale="en" t={t} brandName="Vergeo5" />
        <HomeProductRail
          id="home-rail-new"
          title={t("home.rails.newTitle")}
          viewAllHref="/en/c/all"
          viewAllLabel={t("home.rails.viewAll")}
          listings={[makeListing()]}
          locale="en"
          labels={railLabels}
        />
      </NextIntlClientProvider>,
    );

    expect(screen.getByTestId("home-hero-brand")).toHaveTextContent("Vergeo5");
    expect(
      screen.getByRole("heading", { level: 1, name: BUYER_FALLBACK_TITLE }),
    ).toBeInTheDocument();
    expect(screen.queryByText("You pay")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "New on Vergeo5" })).toBeInTheDocument();
    expect(screen.getByTestId("product-card")).toBeInTheDocument();
    expect(screen.queryByText(OPERATIONAL_PLACEHOLDER_TITLE)).not.toBeInTheDocument();
    expect(screen.queryByText(OPERATIONAL_PLACEHOLDER_SUBTITLE)).not.toBeInTheDocument();
  });

  it("keeps catalogue rails when only a partial campaign module is configured", () => {
    const plan = planHomeLayout(
      [
        {
          id: "flash-1",
          slot_key: "flash_deal",
          variant_key: "default",
          payload: { ends_at: "2030-12-31T23:59:59.000Z", headline: "Flash sale" },
          schedule_from: null,
          schedule_to: null,
          position: 1,
          active: true,
        },
      ],
      [makeCategory()],
      { ...emptyDefaultData, newest: [makeListing()] },
      new Date("2026-07-09T12:00:00.000Z"),
    );

    expect(plan.mode).toBe("hybrid");
    expect(plan.showDefaultRails).toBe(true);
    expect(plan.showSellCta).toBe(true);
    expect(plan.campaignSectionKeys).toEqual(["flash_deal", "category_grid"]);
  });
});
