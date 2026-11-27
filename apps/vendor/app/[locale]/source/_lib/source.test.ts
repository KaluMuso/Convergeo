import { describe, expect, it } from "vitest";

import {
  buildPageQuery,
  buildSearchPath,
  categoryEnabled,
  parseTab,
  sortedTiers,
  whatsappLink,
} from "./source";

describe("source url state", () => {
  it("falls back to the default tab for unknown values", () => {
    expect(parseTab("nope")).toBe("suppliers");
    expect(parseTab(null)).toBe("suppliers");
    expect(parseTab("made_in_zambia")).toBe("made_in_zambia");
    expect(parseTab("import")).toBe("import");
  });

  it("omits defaults from the page query", () => {
    expect(buildPageQuery({ tab: "suppliers", q: "", category: "" })).toBe("");
    expect(buildPageQuery({ tab: "services", q: " ink ", category: "" })).toBe(
      "?tab=services&q=ink",
    );
  });

  it("builds the api search path with paging", () => {
    expect(buildSearchPath({ tab: "made_in_zambia", q: "honey", category: "c1" }, 12)).toBe(
      "/vendor/sourcing/search?tab=made_in_zambia&q=honey&category=c1&offset=12&limit=12",
    );
    expect(buildSearchPath({ tab: "import", q: "", category: "" }, 0)).toContain("tab=suppliers");
  });

  it("only filters goods tabs by category", () => {
    expect(categoryEnabled("suppliers")).toBe(true);
    expect(categoryEnabled("services")).toBe(false);
    expect(categoryEnabled("import")).toBe(false);
  });
});

describe("source helpers", () => {
  it("builds a safe whatsapp link", () => {
    expect(whatsappLink("260977123456", "Hi & bye")).toBe(
      "https://wa.me/260977123456?text=Hi%20%26%20bye",
    );
    expect(whatsappLink("+26097", "x")).toBeNull();
    expect(whatsappLink(null, "x")).toBeNull();
  });

  it("sorts price tiers by quantity without mutating", () => {
    const tiers = [
      { min_qty: 50, price_ngwee: 300 },
      { min_qty: 10, price_ngwee: 400 },
    ];
    expect(sortedTiers(tiers).map((t) => t.min_qty)).toEqual([10, 50]);
    expect(tiers[0]?.min_qty).toBe(50);
    expect(sortedTiers(null)).toEqual([]);
  });
});
