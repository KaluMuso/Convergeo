import { describe, expect, it } from "vitest";

import {
  describeLeadTime,
  formatLeadTimeWhen,
  formatMadeToOrderBadge,
  formatMadeToOrderLeadTime,
  type LeadTimePhrases,
} from "./sale-quantity";

const phrases: LeadTimePhrases = {
  oneDay: "within a day",
  days: "in about {count} days",
  oneWeek: "within a week",
  weeks: "in about {count} weeks",
  oneMonth: "in about a month",
  months: "in about {count} months",
};

describe("lead time in words", () => {
  it.each([
    [1, "within a day"],
    [3, "in about 3 days"],
    [7, "within a week"],
    [14, "in about 2 weeks"],
    [10, "in about 10 days"],
    [30, "in about a month"],
    [60, "in about 2 months"],
  ])("%i days reads %s", (days, text) => {
    expect(formatLeadTimeWhen(days, phrases)).toBe(text);
  });

  it("classifies the forms", () => {
    expect(describeLeadTime(7)).toEqual({ form: "oneWeek", count: 1 });
    expect(describeLeadTime(21)).toEqual({ form: "weeks", count: 3 });
  });

  it("builds the made-to-order label and ignores in-stock listings", () => {
    const template = "Made to order · ready {when}";
    expect(
      formatMadeToOrderLeadTime("made_to_order", 7, template, phrases),
    ).toBe("Made to order · ready within a week");
    expect(
      formatMadeToOrderLeadTime("in_stock", 7, template, phrases),
    ).toBeNull();
    expect(
      formatMadeToOrderLeadTime("made_to_order", null, template, phrases),
    ).toBeNull();
    expect(
      formatMadeToOrderBadge("made_to_order", 7, {
        badge: template,
        when: phrases,
      }),
    ).toBe("Made to order · ready within a week");
  });
});
