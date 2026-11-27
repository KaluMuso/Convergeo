// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { inShopsLine, signalBadgeEntries, signalSlots, type SignalLabels } from "./signals";

afterEach(cleanup);

const labels: SignalLabels = {
  badge: {
    cheapest: "Cheapest",
    near_you: "Near you",
    made_in_zambia: "Made in Zambia",
    top_rated: "Top rated",
    fast_delivery: "Fast delivery",
    low_stock: "Low stock",
    new: "New",
  },
  nearYouKm: "{km} km away",
  ribbon: {
    preferred: "Preferred seller",
    verified_business: "Verified business",
    verified_id: "ID verified",
  },
  inShops: "In {count} shops from {price}",
};

describe("signal helpers", () => {
  it("returns nothing without signals or labels", () => {
    expect(signalBadgeEntries(undefined, labels)).toEqual([]);
    expect(signalBadgeEntries({ badges: ["new"] }, undefined)).toEqual([]);
    expect(inShopsLine(null, labels)).toBeNull();
  });

  it("caps badges at two and swaps in the distance for near_you", () => {
    const entries = signalBadgeEntries(
      { badges: ["cheapest", "near_you", "new"], distance_km: 1.2 },
      labels,
    );
    expect(entries).toEqual([
      { kind: "cheapest", label: "Cheapest" },
      { kind: "near_you", label: "1.2 km away" },
    ]);
  });

  it("formats the in-shops line only for 2+ shops with an integer ngwee price", () => {
    expect(inShopsLine({ seller_count: 3, lowest_price_ngwee: 4500 }, labels)).toBe(
      "In 3 shops from K45.00",
    );
    expect(inShopsLine({ seller_count: 1, lowest_price_ngwee: 4500 }, labels)).toBeNull();
    expect(inShopsLine({ seller_count: 3, lowest_price_ngwee: 45.5 }, labels)).toBeNull();
    expect(inShopsLine({ seller_count: 3 }, labels)).toBeNull();
  });

  it("renders ribbon and badges slots", () => {
    const slots = signalSlots({ ribbon: "verified_business", badges: ["top_rated"] }, labels);
    render(
      <div>
        {slots.ribbon}
        {slots.badges}
      </div>,
    );
    expect(screen.getByTestId("signal-ribbon")).toHaveTextContent("Verified business");
    expect(screen.getByTestId("signal-badge-top_rated")).toHaveTextContent("Top rated");
  });

  it("renders no slots for an unverified listing with no badges", () => {
    const slots = signalSlots({ ribbon: null, badges: [] }, labels);
    expect(slots.ribbon).toBeNull();
    expect(slots.badges).toBeNull();
  });
});
