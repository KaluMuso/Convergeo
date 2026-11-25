import { describe, expect, it } from "vitest";

import { repairServiceVerticalHref } from "./shop-internal-href";

describe("repairServiceVerticalHref", () => {
  it("rewrites bare service vertical paths", () => {
    expect(repairServiceVerticalHref("/tech-services", "en")).toBe(
      "/en/services?category=tech-services",
    );
    expect(repairServiceVerticalHref("/en/tech-services", "en")).toBe(
      "/en/services?category=tech-services",
    );
  });

  it("leaves normal shop paths alone", () => {
    expect(repairServiceVerticalHref("/c/electronics", "en")).toBe("/c/electronics");
    expect(repairServiceVerticalHref("/en/search", "en")).toBe("/en/search");
  });
});
