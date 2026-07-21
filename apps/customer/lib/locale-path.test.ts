import { describe, expect, it } from "vitest";

import { swapLocaleInPath } from "./locale-path";

describe("swapLocaleInPath", () => {
  it("replaces the locale prefix on shop routes", () => {
    expect(swapLocaleInPath("/en/search", "bem")).toBe("/bem/search");
    expect(swapLocaleInPath("/en/c/electronics/phones", "fr")).toBe("/fr/c/electronics/phones");
  });

  it("handles locale-only paths", () => {
    expect(swapLocaleInPath("/en", "nya")).toBe("/nya");
  });

  it("prefixes paths that do not start with a locale", () => {
    expect(swapLocaleInPath("/search", "en")).toBe("/en/search");
  });

  it("normalizes paths without a leading slash", () => {
    expect(swapLocaleInPath("en/account/orders", "bem")).toBe("/bem/account/orders");
  });
});
