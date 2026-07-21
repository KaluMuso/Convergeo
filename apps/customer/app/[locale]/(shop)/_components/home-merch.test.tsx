// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import catalogMessages from "../../../../../../packages/i18n/messages/en/catalog.json";

import { HomeHero } from "./hero";
import {
  filterActiveSlots,
  getRenderableSectionKeys,
  hasEffectiveMerchConfig,
  HOME_SECTION_ORDER,
  isPlaceholderHeroSlot,
  isSlotInSchedule,
  type MerchSlotRow,
} from "./merch-data";

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

function makeSlot(overrides: Partial<MerchSlotRow> = {}): MerchSlotRow {
  return {
    id: "slot-1",
    slot_key: "hero",
    variant_key: "editorial-light",
    payload: {},
    schedule_from: null,
    schedule_to: null,
    position: 0,
    active: true,
    ...overrides,
  };
}

describe("merch slot scheduling", () => {
  it("includes active in-schedule slots", () => {
    const now = new Date("2026-07-09T12:00:00.000Z");
    const slots = [
      makeSlot({
        id: "active",
        schedule_from: "2026-07-01T00:00:00.000Z",
        schedule_to: "2026-07-31T23:59:59.000Z",
      }),
      makeSlot({
        id: "expired",
        slot_key: "banner_row",
        schedule_from: "2026-06-01T00:00:00.000Z",
        schedule_to: "2026-07-01T00:00:00.000Z",
        position: 1,
      }),
      makeSlot({
        id: "future",
        slot_key: "events_row",
        schedule_from: "2026-08-01T00:00:00.000Z",
        schedule_to: null,
        position: 2,
      }),
    ];

    const active = filterActiveSlots(slots, now);
    expect(active.map((slot) => slot.id)).toEqual(["active"]);
    expect(isSlotInSchedule(slots[1]!, now)).toBe(false);
    expect(isSlotInSchedule(slots[2]!, now)).toBe(false);
  });

  it("orders events row before featured collections in IA", () => {
    const eventsIndex = HOME_SECTION_ORDER.indexOf("events_row");
    const featuredIndex = HOME_SECTION_ORDER.indexOf("featured_collections");
    expect(eventsIndex).toBeGreaterThan(-1);
    expect(featuredIndex).toBeGreaterThan(eventsIndex);
  });

  it("renders section keys with events before featured when both slots exist", () => {
    const slots = [
      makeSlot({ slot_key: "featured_collections", position: 3 }),
      makeSlot({ slot_key: "events_row", position: 2 }),
      makeSlot({ slot_key: "hero", position: 0 }),
    ];

    const keys = getRenderableSectionKeys(slots, []);
    expect(keys.indexOf("events_row")).toBeLessThan(keys.indexOf("featured_collections"));
  });
});

describe("HomeHero fallback", () => {
  it("renders default hero when variant is unknown", () => {
    render(
      <HomeHero
        locale="en"
        t={t}
        slot={makeSlot({
          variant_key: "does-not-exist",
          payload: {
            title_key: "home.hero.fallbackTitle",
            subtitle_key: "home.hero.fallbackSubtitle",
          },
        })}
      />,
    );

    expect(screen.getByTestId("hero-default")).toBeInTheDocument();
    expect(
      screen.getByText("Shop products, services, and events across Zambia"),
    ).toBeInTheDocument();
  });

  it("renders buyer fallback copy instead of operational placeholder strings", () => {
    render(
      <HomeHero
        locale="en"
        t={t}
        slot={makeSlot({
          variant_key: "editorial-light",
          payload: {
            title_key: "home.hero.placeholder.title",
            subtitle_key: "home.hero.placeholder.subtitle",
          },
        })}
      />,
    );

    expect(screen.getByTestId("hero-editorial-light")).toBeInTheDocument();
    expect(
      screen.getByText("Shop products, services, and events across Zambia"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Welcome to Vergeo5")).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        "Your config-driven storefront will appear here as merchandising slots go live.",
      ),
    ).not.toBeInTheDocument();
  });

  it("maps seeded merch.* placeholder keys to buyer-facing fallback strings", () => {
    render(
      <HomeHero
        locale="en"
        t={t}
        slot={makeSlot({
          payload: {
            title_key: "merch.hero.placeholder.title",
            subtitle_key: "merch.hero.placeholder.subtitle",
          },
        })}
      />,
    );

    expect(
      screen.getByText("Shop products, services, and events across Zambia"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Welcome to Vergeo5")).not.toBeInTheDocument();
  });
});

describe("placeholder-only seed merchandising", () => {
  it("does not block the catalogue-backed default homepage", () => {
    const seedHero = makeSlot({
      payload: {
        title_key: "merch.hero.placeholder.title",
        subtitle_key: "merch.hero.placeholder.subtitle",
      },
    });

    expect(isPlaceholderHeroSlot(seedHero)).toBe(true);
    expect(hasEffectiveMerchConfig([seedHero])).toBe(false);
  });
});

describe("catalog.home i18n completeness", () => {
  const home = catalogMessages.home as Record<string, unknown>;

  it("includes nested home meta, nav, hero, and section labels", () => {
    expect(home.meta).toBeTruthy();
    expect(home.nav).toBeTruthy();
    expect(home.hero).toBeTruthy();
    expect(home.bannerRow).toBeTruthy();
    expect(home.events).toBeTruthy();
    expect(home.featured).toBeTruthy();
    expect(home.categories).toBeTruthy();
  });
});
