import { describe, expect, it } from "vitest";

import { resolveOpenGraphParams } from "./opengraph-params";

describe("resolveOpenGraphParams", () => {
  it("falls back when searchParams is undefined", () => {
    expect(resolveOpenGraphParams(undefined)).toEqual({
      displayName: "Convergeo",
      displayPrice: null,
    });
  });

  it("falls back when searchParams is null", () => {
    expect(resolveOpenGraphParams(null)).toEqual({
      displayName: "Convergeo",
      displayPrice: null,
    });
  });

  it("uses trimmed name and price when present", () => {
    expect(resolveOpenGraphParams({ name: "  Chitenge  ", price: " K120.00 " })).toEqual({
      displayName: "Chitenge",
      displayPrice: "K120.00",
    });
  });

  it("treats blank name/price as missing", () => {
    expect(resolveOpenGraphParams({ name: "   ", price: "" })).toEqual({
      displayName: "Convergeo",
      displayPrice: null,
    });
  });
});
