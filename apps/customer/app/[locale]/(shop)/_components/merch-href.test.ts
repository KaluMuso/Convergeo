import { describe, expect, it } from "vitest";

import { withLocaleHref } from "./merch-href";

describe("withLocaleHref", () => {
  it("prefixes the viewer locale onto locale-less merch hrefs", () => {
    expect(withLocaleHref("fr", "/search")).toBe("/fr/search");
    expect(withLocaleHref("zh", "/c/phones?sort=new")).toBe("/zh/c/phones?sort=new");
  });

  it("leaves already-prefixed, absolute and non-root hrefs unchanged", () => {
    expect(withLocaleHref("fr", "/en/search")).toBe("/en/search");
    expect(withLocaleHref("fr", "https://vergeo5.com/search")).toBe("https://vergeo5.com/search");
    expect(withLocaleHref("fr", "#top")).toBe("#top");
  });
});
