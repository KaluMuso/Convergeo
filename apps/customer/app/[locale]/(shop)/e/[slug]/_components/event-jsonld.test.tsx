import { describe, expect, it } from "vitest";

import {
  buildEventJsonLd,
  buildEventOffers,
  EVENT_NOINDEX_GRACE_DAYS,
  isEventIndexable,
  latestInstanceStart,
  type EventJsonLdInput,
} from "./event-jsonld";

const BASE: EventJsonLdInput = {
  name: "Zed Summer Festival",
  slug: "zed-summer-festival",
  locale: "en",
  description: "A weekend of music.",
  venue: "Lusaka Showgrounds",
  landmark: "Near Great East Road",
  lat: -15.4167,
  lng: 28.2833,
  imageUrls: ["https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,w_960/events/hero"],
  instances: [{ startsAt: "2026-09-12T18:00:00+02:00" }],
  ticketTypes: [
    {
      name: "General Admission",
      priceNgwee: 50000,
      isFree: false,
      isSoldOut: false,
    },
    { name: "VIP", priceNgwee: 150000, isFree: false, isSoldOut: true },
  ],
  organiserName: "Event House Lusaka",
  isFree: false,
};

const DAY_MS = 24 * 60 * 60 * 1000;

describe("buildEventOffers", () => {
  it("maps paid ticket types to exact ZMW decimal offers with availability", () => {
    const offers = buildEventOffers(BASE, "https://vergeo5.com/en/e/zed-summer-festival");
    expect(offers).toEqual([
      {
        "@type": "Offer",
        name: "General Admission",
        price: "500.00",
        priceCurrency: "ZMW",
        availability: "https://schema.org/InStock",
        url: "https://vergeo5.com/en/e/zed-summer-festival",
      },
      {
        "@type": "Offer",
        name: "VIP",
        price: "1500.00",
        priceCurrency: "ZMW",
        availability: "https://schema.org/SoldOut",
        url: "https://vergeo5.com/en/e/zed-summer-festival",
      },
    ]);
  });

  it("emits a single zero-price InStock offer for free events", () => {
    const offers = buildEventOffers(
      { ...BASE, isFree: true },
      "https://vergeo5.com/en/e/free-meetup",
    );
    expect(offers).toEqual([
      {
        "@type": "Offer",
        price: "0",
        priceCurrency: "ZMW",
        availability: "https://schema.org/InStock",
        url: "https://vergeo5.com/en/e/free-meetup",
      },
    ]);
  });
});

describe("buildEventJsonLd", () => {
  it("produces a valid Event object with location, organizer and offers array", () => {
    const jsonLd = buildEventJsonLd(BASE);
    expect(jsonLd["@context"]).toBe("https://schema.org");
    expect(jsonLd["@type"]).toBe("Event");
    expect(jsonLd.name).toBe("Zed Summer Festival");
    expect(jsonLd.url).toBe("https://vergeo5.com/en/e/zed-summer-festival");
    expect(jsonLd.startDate).toBe("2026-09-12T18:00:00+02:00");
    expect(jsonLd.eventStatus).toBe("https://schema.org/EventScheduled");
    expect(jsonLd.location).toEqual({
      "@type": "Place",
      name: "Lusaka Showgrounds",
      address: {
        "@type": "PostalAddress",
        streetAddress: "Near Great East Road",
        addressLocality: "Lusaka",
        addressCountry: "ZM",
      },
      geo: {
        "@type": "GeoCoordinates",
        latitude: -15.4167,
        longitude: 28.2833,
      },
    });
    expect(jsonLd.organizer).toEqual({
      "@type": "Organization",
      name: "Event House Lusaka",
    });
    expect(Array.isArray(jsonLd.offers)).toBe(true);
  });

  it("collapses a single offer to an object (free event)", () => {
    const jsonLd = buildEventJsonLd({ ...BASE, isFree: true });
    expect(jsonLd.offers).toMatchObject({ "@type": "Offer", price: "0" });
  });

  it("uses an explicit instance end for endDate", () => {
    const jsonLd = buildEventJsonLd({
      ...BASE,
      instances: [{ startsAt: "2026-09-12T18:00:00+02:00", endsAt: "2026-09-14T22:00:00+02:00" }],
    });
    expect(jsonLd.endDate).toBe(new Date("2026-09-14T22:00:00+02:00").toISOString());
  });

  it("falls back to a 2h endDate when the instance has no end", () => {
    const jsonLd = buildEventJsonLd(BASE);
    expect(jsonLd.endDate).toBe(
      new Date(new Date("2026-09-12T18:00:00+02:00").getTime() + 2 * 60 * 60 * 1000).toISOString(),
    );
  });
});

describe("isEventIndexable / noindex after +30d", () => {
  const now = new Date("2026-09-20T00:00:00Z").getTime();

  it("indexes an upcoming event", () => {
    expect(isEventIndexable([{ startsAt: "2026-10-01T18:00:00+02:00" }], now)).toBe(true);
  });

  it("indexes a past-but-recent event (within grace)", () => {
    const tenDaysAgo = new Date(now - 10 * DAY_MS).toISOString();
    expect(isEventIndexable([{ startsAt: tenDaysAgo }], now)).toBe(true);
  });

  it("noindexes an event whose last instance ended more than 30d ago", () => {
    const staleStart = new Date(now - (EVENT_NOINDEX_GRACE_DAYS + 2) * DAY_MS).toISOString();
    expect(isEventIndexable([{ startsAt: staleStart }], now)).toBe(false);
  });

  it("indexes when there are no instances", () => {
    expect(isEventIndexable([], now)).toBe(true);
    expect(latestInstanceStart([])).toBeNull();
  });

  it("keeps a multi-day event indexable by its real end, not its start", () => {
    // Start is well beyond the grace window, but the explicit end is recent —
    // with the old start+2h logic this would have wrongly noindexed.
    const start = new Date(now - (EVENT_NOINDEX_GRACE_DAYS + 5) * DAY_MS).toISOString();
    const end = new Date(now - DAY_MS).toISOString();
    expect(isEventIndexable([{ startsAt: start, endsAt: end }], now)).toBe(true);
  });

  it("noindexes when the explicit end is beyond the grace window", () => {
    const start = new Date(now - (EVENT_NOINDEX_GRACE_DAYS + 10) * DAY_MS).toISOString();
    const end = new Date(now - (EVENT_NOINDEX_GRACE_DAYS + 2) * DAY_MS).toISOString();
    expect(isEventIndexable([{ startsAt: start, endsAt: end }], now)).toBe(false);
  });
});
