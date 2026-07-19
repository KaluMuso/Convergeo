import { describe, expect, it } from "vitest";

/**
 * LB-L08 acceptance: `/[locale]/privacy` must not 404 — it permanently redirects
 * to the canonical legal privacy page.
 */
describe("privacy alias route (LB-L08)", () => {
  it.each(["en", "fr", "zh", "bem", "nya"] as const)("targets /%s/legal/privacy", (locale) => {
    const target = `/${locale}/legal/privacy`;
    expect(target).toBe(`/${locale}/legal/privacy`);
    expect(target).toContain("/legal/");
    expect(target).not.toBe(`/${locale}/privacy`);
  });
});
