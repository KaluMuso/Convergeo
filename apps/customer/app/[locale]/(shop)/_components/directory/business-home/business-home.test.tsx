// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { buildStorefrontCompare, CompareOtherShopsLink } from "./compare-other-shops";
import { isOpenAt, OpenStatus, type DaySchedule } from "./open-status";
import {
  ClipsRow,
  directionsHref,
  FindUsSection,
  OffersSection,
  ReviewsSection,
  servicePriceLine,
  StorySection,
} from "./sections";
import { visibleSections } from "./visible-sections";

afterEach(cleanup);

const compareLabels = {
  count: (count: number) =>
    count === 1 ? "Compare with 1 other shop" : `Compare with ${count} other shops`,
  from: (price: number) => `from K${price / 100}`,
  aria: (title: string) => `Compare ${title} at other shops`,
};

describe("buildStorefrontCompare", () => {
  it("links to the canonical product comparison with count and lowest price", () => {
    const compare = buildStorefrontCompare({
      locale: "en",
      productSlug: "itel a70",
      title: "Itel A70",
      otherOffersCount: 3,
      otherMinPriceNgwee: 430_000,
      labels: compareLabels,
    });
    expect(compare).toEqual({
      href: "/en/p/itel%20a70#compare",
      label: "Compare with 3 other shops · from K4300",
      ariaLabel: "Compare Itel A70 at other shops",
    });
  });

  it("returns null when nobody else sells it or the listing is standalone", () => {
    const base = {
      locale: "en",
      title: "x",
      otherMinPriceNgwee: null,
      labels: compareLabels,
    };
    expect(
      buildStorefrontCompare({
        ...base,
        productSlug: "itel-a70",
        otherOffersCount: 0,
      }),
    ).toBeNull();
    expect(
      buildStorefrontCompare({
        ...base,
        productSlug: null,
        otherOffersCount: 4,
      }),
    ).toBeNull();
  });

  it("renders an accessible, tappable compare link", () => {
    render(
      <CompareOtherShopsLink
        compare={{
          href: "/en/p/itel-a70#compare",
          label: "Compare with 1 other shop",
          ariaLabel: "Compare Itel A70 at other shops",
        }}
      />,
    );
    const link = screen.getByTestId("storefront-compare");
    expect(link).toHaveAttribute("href", "/en/p/itel-a70#compare");
    expect(link).toHaveAccessibleName(
      "Compare Itel A70 at other shops — Compare with 1 other shop",
    );
    expect(link.className).toContain("min-h-11");
  });
});

describe("isOpenAt (Lusaka clock, mirrors API)", () => {
  // 2026-08-03 is a Monday. Lusaka = UTC+2.
  const utc = (day: number, hour: number, minute = 0) =>
    new Date(Date.UTC(2026, 7, day, hour - 2, minute));
  const weekday: DaySchedule[] = [{ day: "mon", opens: "09:00", closes: "17:00" }];

  it("is open inside the span and closed at closing time", () => {
    expect(isOpenAt(weekday, utc(3, 12))).toBe(true);
    expect(isOpenAt(weekday, utc(3, 17))).toBe(false);
    expect(isOpenAt(weekday, utc(4, 12))).toBe(false); // Tuesday: absent = closed
  });

  it("treats a reversed span as overnight into the next day", () => {
    const bar: DaySchedule[] = [{ day: "fri", opens: "18:00", closes: "02:00" }];
    expect(isOpenAt(bar, utc(7, 23))).toBe(true); // Fri 23:00
    expect(isOpenAt(bar, utc(8, 1))).toBe(true); // Sat 01:00
    expect(isOpenAt(bar, utc(8, 3))).toBe(false);
  });

  it("renders nothing when no hours are published", () => {
    render(<OpenStatus schedule={[]} labels={{ open: "Open now", closed: "Closed now" }} />);
    expect(screen.queryByTestId("open-status")).toBeNull();
  });
});

describe("Business Home sections", () => {
  it("shows the story only when the business wrote one", () => {
    const { rerender } = render(<StorySection heading="Our story" story="  " />);
    expect(screen.queryByTestId("bh-story")).toBeNull();
    rerender(<StorySection heading="Our story" story="Selling chitenge since 2009." />);
    const story = screen.getByRole("region", { name: "Our story" });
    expect(story).toHaveTextContent("Selling chitenge since 2009.");
  });

  it("lists each branch with its hours and a directions link", () => {
    render(
      <FindUsSection
        branches={[
          {
            landmark: "Soweto Market, stall 12",
            lat: -15.42,
            lng: 28.27,
            schedule: [{ day: "mon", opens: "08:00", closes: "17:00" }],
          },
          { landmark: "Kitwe branch", lat: -12.8, lng: 28.2, schedule: [] },
        ]}
        labels={{
          heading: "Find us",
          directions: "Directions",
          directionsTo: (place) => `Directions to ${place}`,
          hoursNotShared: "Opening hours not shared yet",
          hoursRange: (o, c) => `${o}–${c}`,
          day: (day) => ({ mon: "Mon" })[day as "mon"] ?? day,
          open: "Open now",
          closed: "Closed now",
        }}
      />,
    );
    const branches = screen.getAllByTestId("bh-branch");
    expect(branches).toHaveLength(2);
    expect(within(branches[0]!).getByText("Mon")).toBeInTheDocument();
    expect(within(branches[0]!).getByText("08:00–17:00")).toBeInTheDocument();
    expect(
      within(branches[0]!).getByRole("link", {
        name: "Directions to Soweto Market, stall 12",
      }),
    ).toHaveAttribute("href", directionsHref({ lat: -15.42, lng: 28.27 }));
    expect(within(branches[1]!).getByText("Opening hours not shared yet")).toBeInTheDocument();
  });

  it("never shows an empty offers block: flag ON and at least one offer", () => {
    const labels = { heading: "Offers" };
    const offer = { id: "o1", title: "10% off rice", endsLabel: "Ends 30 Nov" };
    const { rerender } = render(<OffersSection enabled={false} offers={[offer]} labels={labels} />);
    expect(screen.queryByTestId("bh-offers")).toBeNull();
    rerender(<OffersSection enabled offers={[]} labels={labels} />);
    expect(screen.queryByTestId("bh-offers")).toBeNull();
    rerender(<OffersSection enabled offers={[offer]} labels={labels} />);
    expect(screen.getByTestId("bh-offers")).toHaveTextContent("10% off rice");
    expect(screen.getByTestId("bh-offers")).toHaveTextContent("Ends 30 Nov");
  });

  it("shows a section only when its flag is on AND it has live items", () => {
    const counts = { products: 2, services: 0, events: 1, offers: 0, clips: 3 };
    expect(
      visibleSections({
        counts,
        sections: { products: true, services: true, events: false, offers: true, clips: true },
      }),
    ).toEqual({ products: true, services: false, events: false, offers: false, clips: true });
    // Older API (no `sections`): core sections follow their items; offers need the flag.
    expect(visibleSections({ counts: { ...counts, offers: 1 } })).toEqual({
      products: true,
      services: false,
      events: true,
      offers: false,
      clips: true,
    });
  });

  it("hides the clips row when there are no clips (flag off returns none)", () => {
    const labels = { heading: "Clips", watch: "Watch clip" };
    const { rerender } = render(<ClipsRow locale="en" clips={[]} labels={labels} />);
    expect(screen.queryByTestId("bh-clips")).toBeNull();
    rerender(
      <ClipsRow
        locale="en"
        clips={[{ id: "c1", poster_url: null, caption: "New stock" }]}
        labels={labels}
      />,
    );
    expect(screen.getByRole("link", { name: "Watch clip: New stock" })).toHaveAttribute(
      "href",
      "/en/clips/c1",
    );
  });

  it("says reviews come from verified purchases only", () => {
    render(
      <ReviewsSection
        ratingAvg={4.5}
        ratingCount={12}
        labels={{
          heading: "Reviews",
          summary: "4.5 average from 12 reviews",
          none: "No reviews yet",
          verifiedOnly: "Only customers who bought here can review.",
        }}
      />,
    );
    expect(screen.getByText("4.5")).toBeInTheDocument();
    expect(screen.getByText("Only customers who bought here can review.")).toBeInTheDocument();
  });

  it("prices services customer-first: fixed booking, then from, then quote", () => {
    const labels = {
      from: (p: string) => `From ${p}`,
      book: (p: string) => `Book for ${p}`,
      quote: "Ask for a price",
      area: (a: string) => `Serves ${a}`,
    };
    expect(
      servicePriceLine(
        { bookable: true, booking_price_ngwee: 30_000, from_price_ngwee: 25_000 },
        labels,
      ),
    ).toBe("Book for K300.00");
    expect(servicePriceLine({ bookable: false, from_price_ngwee: 25_000 }, labels)).toBe(
      "From K250.00",
    );
    expect(servicePriceLine({ from_price_ngwee: null }, labels)).toBe("Ask for a price");
  });
});
