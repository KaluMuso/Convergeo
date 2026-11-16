import { describe, expect, it } from "vitest";

import { maskMsisdn, swapLocaleInPath } from "./locale-path";

describe("swapLocaleInPath", () => {
  it("replaces the locale prefix and keeps the path", () => {
    expect(swapLocaleInPath("/en/listings/new", "fr")).toBe("/fr/listings/new");
  });
  it("handles the bare locale root", () => {
    expect(swapLocaleInPath("/en", "zh")).toBe("/zh");
  });
  it("prefixes when no locale is present", () => {
    expect(swapLocaleInPath("/settings", "nya")).toBe("/nya/settings");
  });
});

describe("maskMsisdn", () => {
  it("shows only the last three digits", () => {
    expect(maskMsisdn("260971234567")).toBe("•••••••••567");
  });
  it("leaves very short values alone", () => {
    expect(maskMsisdn("12")).toBe("12");
  });
});
