// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import commonEn from "../../../../../../../packages/i18n/messages/en/common.json";

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn(async () => ({ common: commonEn })),
  setRequestLocale: vi.fn(),
}));
vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.test${path}`,
}));
vi.mock("../../_components/directory/follow-vendor-button", () => ({
  FollowVendorButton: ({ labels }: { labels: { follow: string } }) => (
    <button type="button">{labels.follow}</button>
  ),
}));
vi.mock("../../../_components/share-link-button", () => ({
  ShareLinkButton: ({ label }: { label: string }) => <button type="button">{label}</button>,
}));
vi.mock("../../_components/directory/storefront-products", () => ({
  StorefrontProducts: ({
    listings,
  }: {
    listings: Array<{
      id: string;
      title: string;
      deliveryAvailable: boolean;
      pickupAvailable: boolean;
      compare?: { href: string; label: string } | null;
    }>;
  }) => (
    <ul data-testid="mock-products">
      {listings.map((l) => (
        <li
          key={l.id}
          data-delivery={String(l.deliveryAvailable)}
          data-pickup={String(l.pickupAvailable)}
        >
          {l.title}
          {l.compare ? <a href={l.compare.href}>{l.compare.label}</a> : null}
        </li>
      ))}
    </ul>
  ),
}));

import VendorProfilePage, { generateMetadata, revalidate } from "./page";

const PROFILE = {
  vendor: {
    id: "v1",
    slug: "mama-chanda",
    display_name: "Mama Chanda's Kitchen",
    description: "Home cooking in Kabwata since 2012.",
    logo_url: "https://res.cloudinary.com/demo/logo.png",
    cover_url: "https://res.cloudinary.com/demo/cover.jpg",
    whatsapp_msisdn: "260971234567",
    preferred_badge: false,
    kyc_tier: 2,
    commercial_tier: "gold",
    verified: true,
    order_count: 40,
    location: {
      landmark: "Kabwata Market",
      lat: -15.44,
      lng: 28.3,
      hours: { mon: { open: "08:00", close: "17:00", closed: false } },
      schedule: [{ day: "mon", opens: "08:00", closes: "17:00" }],
    },
    locations: [
      {
        landmark: "Kabwata Market",
        lat: -15.44,
        lng: 28.3,
        hours: {},
        schedule: [{ day: "mon", opens: "08:00", closes: "17:00" }],
      },
    ],
    created_at: "2025-01-01T00:00:00Z",
    brand_theme: null,
  },
  listings: [
    {
      id: "l1",
      title: "Chikanda (500g)",
      product_slug: "chikanda-500g",
      price_ngwee: 6_000,
      condition: "new",
      in_stock: true,
      image_public_id: null,
      product_class: "A",
      sale_unit: "each",
      unit_step_milli: 1000,
      min_steps: 1,
      fulfilment_mode: "stocked",
      lead_time_days: null,
      delivery_available: true,
      pickup_available: true,
      other_offers_count: 2,
      other_min_price_ngwee: 5_500,
    },
    {
      id: "l2",
      title: "House relish",
      product_slug: null,
      price_ngwee: 4_000,
      condition: "new",
      in_stock: false,
      image_public_id: null,
      product_class: "A",
      sale_unit: "each",
      unit_step_milli: 1000,
      min_steps: 1,
      fulfilment_mode: "stocked",
      lead_time_days: null,
      delivery_available: true,
      pickup_available: true,
      other_offers_count: 0,
      other_min_price_ngwee: null,
    },
  ],
  services: [
    {
      id: "s1",
      title: "Party catering",
      category: "catering",
      from_price_ngwee: 150_000,
      image_public_id: null,
      service_area: "Lusaka",
      bookable: false,
      booking_price_ngwee: null,
    },
  ],
  events: [],
  reviews_summary: { rating_avg: 4.6, rating_count: 18 },
  clips: [],
  offers_enabled: false,
};

const params = (slug = "mama-chanda") => Promise.resolve({ locale: "en", slug });

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      String(url).endsWith("/directory/mama-chanda")
        ? new Response(JSON.stringify(PROFILE), { status: 200 })
        : new Response("{}", { status: 404 }),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Business Home SEO metadata", () => {
  it("is ISR-cached and indexable with the shop's own name, canonical and sign", async () => {
    expect(revalidate).toBe(3600);
    const metadata = await generateMetadata({ params: params() });
    expect(metadata.title).toBe("Mama Chanda's Kitchen on Convergeo");
    expect(metadata.robots).toEqual({ index: true, follow: true });
    expect(String(metadata.alternates?.canonical)).toContain("/en/v/mama-chanda");
    expect(metadata.openGraph?.images).toEqual(["https://res.cloudinary.com/demo/logo.png"]);
    expect(metadata.openGraph?.description).toBe("Home cooking in Kabwata since 2012.");
  });

  it("noindexes a missing business", async () => {
    const metadata = await generateMetadata({ params: params("nope") });
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });
});

describe("Business Home page", () => {
  it("shows the sign, story, offerings, reviews and find-us blocks customer-first", async () => {
    render(await VendorProfilePage({ params: params() }));

    expect(
      screen.getByRole("heading", { level: 1, name: "Mama Chanda's Kitchen" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Our story" })).toHaveTextContent(
      "Home cooking in Kabwata since 2012.",
    );

    // Products carry delivery/pickup and a compare action to other shops.
    const products = screen.getByTestId("mock-products");
    const chikanda = within(products).getByText("Chikanda (500g)").closest("li")!;
    expect(chikanda).toHaveAttribute("data-delivery", "true");
    expect(chikanda).toHaveAttribute("data-pickup", "true");
    expect(
      within(chikanda).getByRole("link", { name: /Compare with 2 other shops/ }),
    ).toHaveAttribute("href", "/en/p/chikanda-500g#compare");
    const relish = within(products).getByText("House relish").closest("li")!;
    expect(within(relish).queryByRole("link")).toBeNull();

    // Services stay in the HTML even though Products is the first tab (SEO).
    expect(screen.getByText("Party catering")).toBeInTheDocument();
    expect(screen.getByText("From K1,500.00")).toBeInTheDocument();
    expect(screen.getByText("Serves Lusaka")).toBeInTheDocument();

    expect(screen.getByTestId("bh-directions")).toHaveAttribute(
      "href",
      "https://www.google.com/maps/dir/?api=1&destination=-15.44,28.3",
    );
    expect(screen.getByRole("region", { name: "Find us" })).toHaveTextContent("08:00–17:00");
    expect(
      screen.getByText("Only customers who bought here through Convergeo can leave a review."),
    ).toBeInTheDocument();
    // Flags off: no clips row and no offers placeholder.
    expect(screen.queryByTestId("bh-clips")).toBeNull();
    expect(screen.queryByTestId("bh-offers")).toBeNull();
    // Never trap the customer on one shop.
    expect(screen.getByTestId("bh-other-shops")).toHaveAttribute("href", "/en/vendors");
    // The vendor's plan tier is never shown to buyers.
    expect(document.body.textContent).not.toMatch(/gold/i);
  });
});
