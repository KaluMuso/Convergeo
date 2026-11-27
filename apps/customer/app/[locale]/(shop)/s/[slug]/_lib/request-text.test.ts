import { describe, expect, it } from "vitest";

import {
  buildRequestText,
  EMPTY_FIELDS,
  nightsBetween,
  validateRequest,
  type RequestFields,
  type RequestTextLabels,
} from "./request-text";

const labels: RequestTextLabels = {
  offer: "Option",
  startDate: {
    accommodation: "Check-in",
    appointment: "Preferred date",
    membership: "Start date",
    on_site: "Date",
    rental: "Pickup date",
    ticketed: "Visit date",
    professional: "Date needed",
  },
  endDate: "Check-out",
  time: "Preferred time",
  guests: "Guests",
  quantity: "Quantity",
  period: "Rental period",
  staff: "Preferred stylist",
  nightsOne: "{count} night",
  nightsMany: "{count} nights",
  periods: {
    hour: { one: "{count} hour", many: "{count} hours" },
    day: { one: "{count} day", many: "{count} days" },
    week: { one: "{count} week", many: "{count} weeks" },
  },
  timeOfDay: { any: "Any time", morning: "Morning" },
};

const fields = (over: Partial<RequestFields>): RequestFields => ({ ...EMPTY_FIELDS, ...over });
const ok = { hasOffers: true, offerSelected: true, today: "2026-12-01" };

describe("nightsBetween", () => {
  it("counts nights and rejects bad dates", () => {
    expect(nightsBetween("2026-12-01", "2026-12-04")).toBe(3);
    expect(nightsBetween("2026-12-04", "2026-12-01")).toBe(-3);
    expect(nightsBetween("", "2026-12-01")).toBeNull();
    expect(nightsBetween("2026-13-40", "2026-12-01")).toBeNull();
  });
});

describe("validateRequest", () => {
  it("requires an offer when offers exist", () => {
    expect(validateRequest("appointment", fields({}), { ...ok, offerSelected: false })).toBe(
      "pickOffer",
    );
  });

  it("does not require an offer when the service lists none", () => {
    expect(
      validateRequest("professional", fields({}), {
        hasOffers: false,
        offerSelected: false,
        today: "2026-12-01",
      }),
    ).toBeNull();
  });

  it("stay needs dates in order, and not in the past", () => {
    expect(validateRequest("accommodation", fields({}), ok)).toBe("pickDate");
    expect(validateRequest("accommodation", fields({ startDate: "2026-11-01" }), ok)).toBe(
      "pastDate",
    );
    expect(validateRequest("accommodation", fields({ startDate: "2026-12-05" }), ok)).toBe(
      "pickEnd",
    );
    expect(
      validateRequest(
        "accommodation",
        fields({ startDate: "2026-12-05", endDate: "2026-12-05" }),
        ok,
      ),
    ).toBe("endBeforeStart");
    expect(
      validateRequest(
        "accommodation",
        fields({ startDate: "2026-12-05", endDate: "2026-12-07" }),
        ok,
      ),
    ).toBeNull();
  });
});

describe("buildRequestText", () => {
  it("composes a stay request with nights", () => {
    const text = buildRequestText({
      archetype: "accommodation",
      fields: fields({ startDate: "2026-12-05", endDate: "2026-12-08", guests: 3 }),
      offerName: "Deluxe room",
      offerPrice: "K800.00",
      unit: "day",
      labels,
    });
    expect(text.split("\n")).toEqual([
      "Option: Deluxe room (K800.00)",
      "Check-in: 2026-12-05",
      "Check-out: 2026-12-08 (3 nights)",
      "Guests: 3",
    ]);
  });

  it("composes an appointment with time of day and stylist", () => {
    const text = buildRequestText({
      archetype: "appointment",
      fields: fields({ startDate: "2026-12-05", time: "morning", staff: "Mwila" }),
      offerName: "Fade cut",
      offerPrice: null,
      unit: "day",
      labels,
    });
    expect(text).toContain("Preferred date: 2026-12-05");
    expect(text).toContain("Preferred time: Morning");
    expect(text).toContain("Preferred stylist: Mwila");
    expect(text).not.toContain("Guests");
  });

  it("composes a rental with the offer's unit and singular/plural", () => {
    const one = buildRequestText({
      archetype: "rental",
      fields: fields({ startDate: "2026-12-05", period: 1, quantity: 2 }),
      offerName: "Projector",
      offerPrice: null,
      unit: "hour",
      labels,
    });
    expect(one).toContain("Rental period: 1 hour");
    expect(one).toContain("Quantity: 2");
    const many = buildRequestText({
      archetype: "rental",
      fields: fields({ startDate: "2026-12-05", period: 3 }),
      offerName: "Projector",
      offerPrice: null,
      unit: "week",
      labels,
    });
    expect(many).toContain("3 weeks");
  });

  it("membership asks only for a start date", () => {
    const text = buildRequestText({
      archetype: "membership",
      fields: fields({ startDate: "2026-12-05" }),
      offerName: "Monthly",
      offerPrice: "K300.00",
      unit: "day",
      labels,
    });
    expect(text.split("\n")).toEqual(["Option: Monthly (K300.00)", "Start date: 2026-12-05"]);
  });
});
