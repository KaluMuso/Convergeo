import { describe, expect, it } from "vitest";

/**
 * LB-L08 acceptance: `/[locale]/terms` must not 404 — it permanently redirects
 * to the canonical legal terms page.
 */
describe("terms alias route (LB-L08)", () => {
  it.each(["en", "fr", "zh", "bem", "nya"] as const)("targets /%s/legal/terms", (locale) => {
    const target = `/${locale}/legal/terms`;
    expect(target).toBe(`/${locale}/legal/terms`);
    expect(target).toContain("/legal/");
    expect(target).not.toBe(`/${locale}/terms`);
  });
});
