// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.test${path}`,
}));

import {
  buildElsewhereCards,
  ELSEWHERE_RAIL_LIMIT,
  OtherShopsRail,
  type ElsewherePayload,
} from "./other-shops-rail";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const DATA: ElsewherePayload = {
  products: [
    {
      listing_id: "l1",
      title: "Tecno Spark",
      product_slug: "tecno-spark",
      price_ngwee: 300_000,
      in_stock: true,
      image_public_id: null,
      vendor_slug: "phone-planet",
      vendor_name: "Phone Planet",
    },
    {
      listing_id: "l2",
      title: "No slug",
      product_slug: null,
      price_ngwee: 100,
      in_stock: true,
      image_public_id: null,
      vendor_slug: "x",
      vendor_name: "X",
    },
  ],
  services: [
    {
      id: "s1",
      title: "Battery swap",
      from_price_ngwee: 15_000,
      bookable: false,
      booking_price_ngwee: null,
      image_public_id: null,
      vendor_slug: "phone-planet",
      vendor_name: "Phone Planet",
    },
  ],
  events: [
    {
      id: "e1",
      slug: "phone-expo",
      title: "Phone Expo",
      image_public_id: null,
      next_starts_at: "2099-03-01T10:00:00+00:00",
      vendor_slug: "expo-co",
      vendor_name: "Expo Co",
    },
  ],
};

const labels = {
  atShop: (shop: string) => `at ${shop}`,
  inStock: "In stock",
  outOfStock: "Out of stock",
  serviceFrom: (price: string) => `From ${price}`,
  serviceBook: (price: string) => `Book for ${price}`,
  serviceQuote: "Ask for a price",
  eventDate: () => "Sat 1 Mar",
};

describe("buildElsewhereCards", () => {
  it("leads with the page's own kind and skips the item being viewed", () => {
    const cards = buildElsewhereCards({
      locale: "en",
      data: DATA,
      lead: "event",
      excludeIds: ["s1"],
      labels,
    });
    expect(cards.map((c) => c.key)).toEqual(["e-e1", "p-l1"]);
    expect(cards[1]).toMatchObject({
      href: "/en/p/tecno-spark?listing=l1",
      detail: "K3,000.00",
      stock: { inStock: true, label: "In stock" },
      shop: "at Phone Planet",
    });
  });

  it("prices services customer-first and caps the rail", () => {
    const many: ElsewherePayload = {
      ...DATA,
      services: Array.from({ length: 12 }, (_, i) => ({ ...DATA.services[0]!, id: `s${i}` })),
    };
    const cards = buildElsewhereCards({ locale: "en", data: many, lead: "service", labels });
    expect(cards).toHaveLength(ELSEWHERE_RAIL_LIMIT);
    expect(cards[0]).toMatchObject({ kind: "service", detail: "From K150.00", stock: null });
  });
});

describe("OtherShopsRail", () => {
  it("renders other shops' items under a detail page", async () => {
    const fetchMock = vi.fn(
      async (_url: string) => new Response(JSON.stringify(DATA), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      await OtherShopsRail({
        locale: "en",
        vendorSlug: "tech-hub",
        lead: "product",
        focusProductSlug: "itel-a70",
      }),
    );
    expect(String(fetchMock.mock.calls[0]![0])).toBe(
      "https://api.test/directory/tech-hub/elsewhere?product=itel-a70",
    );
    const rail = screen.getByRole("region", { name: "From other shops" });
    const links = within(rail).getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/en/p/tecno-spark?listing=l1");
    expect(within(links[0]!).getByText("at Phone Planet")).toBeInTheDocument();
    expect(within(rail).getByText("Battery swap")).toBeInTheDocument();
  });

  it("renders nothing when the API fails or has nothing (never an empty rail)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 500 })),
    );
    expect(await OtherShopsRail({ locale: "en", vendorSlug: "x", lead: "event" })).toBeNull();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ products: [], services: [], events: [] }), {
            status: 200,
          }),
      ),
    );
    const { container } = render(
      await OtherShopsRail({ locale: "en", vendorSlug: "x", lead: "event" }),
    );
    expect(container).toBeEmptyDOMElement();
  });
});
