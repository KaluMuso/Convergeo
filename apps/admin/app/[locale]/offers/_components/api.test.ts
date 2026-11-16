import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: vi.fn(async () => "t") }));

import { buildOffersQuery, DEFAULT_FILTERS } from "./api";

describe("buildOffersQuery", () => {
  it("omits 'all' and blank filters", () => {
    expect(buildOffersQuery(DEFAULT_FILTERS)).toBe("/admin/offers");
    expect(buildOffersQuery({ ...DEFAULT_FILTERS, q: "   " })).toBe("/admin/offers");
  });

  it("maps every filter to the API query parameter", () => {
    const query = buildOffersQuery({
      state: "admin_paused",
      status: "active",
      offerType: "buy_n_pay_m",
      q: "  3 for 2 & more ",
    });
    const params = new URL(query, "https://admin.test").searchParams;
    expect(params.get("state")).toBe("admin_paused");
    expect(params.get("status")).toBe("active");
    expect(params.get("offer_type")).toBe("buy_n_pay_m");
    expect(params.get("q")).toBe("3 for 2 & more");
  });

  it("caps the search text at the API limit", () => {
    const params = new URL(
      buildOffersQuery({ ...DEFAULT_FILTERS, q: "x".repeat(500) }),
      "https://admin.test",
    ).searchParams;
    expect(params.get("q")).toHaveLength(120);
  });
});
