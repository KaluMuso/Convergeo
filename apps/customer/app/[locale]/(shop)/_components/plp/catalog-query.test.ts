import { describe, expect, it } from "vitest";

import { buildCatalogQuery } from "./catalog-query";

describe("buildCatalogQuery", () => {
  it("converts kwacha min_price and max_price to ngwee for the catalog API", () => {
    const query = buildCatalogQuery("electronics", {
      min_price: "100",
      max_price: "250.5",
      sort: "newest",
    });
    const params = new URLSearchParams(query);
    expect(params.get("category_path")).toBe("electronics");
    expect(params.get("min_price")).toBe("10000");
    expect(params.get("max_price")).toBe("25050");
    expect(params.get("sort")).toBe("newest");
  });
});
