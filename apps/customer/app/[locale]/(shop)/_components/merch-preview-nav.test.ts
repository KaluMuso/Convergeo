import { describe, expect, it } from "vitest";

import { withMerchPreviewParam } from "./merch-preview-nav";

describe("withMerchPreviewParam", () => {
  it("appends preview token to internal paths", () => {
    expect(withMerchPreviewParam("/en/search", "draft")).toBe("/en/search?merch_preview=draft");
  });

  it("preserves existing query params", () => {
    expect(withMerchPreviewParam("/en/search?q=phone", "draft")).toBe(
      "/en/search?q=phone&merch_preview=draft",
    );
  });

  it("preserves hash fragments", () => {
    expect(withMerchPreviewParam("/en/categories#grid", "draft")).toBe(
      "/en/categories?merch_preview=draft#grid",
    );
  });

  it("returns href unchanged when token is absent", () => {
    expect(withMerchPreviewParam("/en", null)).toBe("/en");
    expect(withMerchPreviewParam("/en", "")).toBe("/en");
  });

  it("ignores external URLs", () => {
    expect(withMerchPreviewParam("https://example.com", "draft")).toBe("https://example.com");
  });
});
