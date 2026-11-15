import { describe, expect, it } from "vitest";

import { buildPageMetadata, getPageTitle } from "./page-title";

describe("page titles", () => {
  it("resolves a page-specific title instead of the generic site title", async () => {
    expect(await getPageTitle("en", "checkout", "cart.title")).toBe("Your cart");
    expect(await getPageTitle("fr", "auth", "login.title")).not.toBe("");
  });

  it("keeps the page robots policy when given", async () => {
    const meta = await buildPageMetadata("en", "checkout", "cart.title", {
      index: false,
      follow: false,
    });
    expect(meta.title).toBe("Your cart");
    expect(meta.robots).toEqual({ index: false, follow: false });
    expect((await buildPageMetadata("en", "auth", "login.title")).robots).toBeUndefined();
  });
});
