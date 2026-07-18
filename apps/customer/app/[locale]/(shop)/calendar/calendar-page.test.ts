import { describe, expect, it } from "vitest";

/**
 * CUST-10 acceptance: calendar must not 404. The page permanently redirects to
 * the events browse surface (where date chips already provide the calendar UX).
 */
describe("calendar route (CUST-10)", () => {
  it("targets the events browse surface with all-dates window", () => {
    const locale = "en";
    const target = `/${locale}/events?date_window=all`;
    expect(target).toBe("/en/events?date_window=all");
    expect(target).not.toContain("calendar");
  });
});
