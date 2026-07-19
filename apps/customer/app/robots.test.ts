import { getSiteUrl } from "@vergeo/ui/src/seo/json-ld";
import { describe, expect, it } from "vitest";

import robots from "./robots";

describe("robots.ts", () => {
  it("allows public crawl while disallowing private and non-content routes", () => {
    const result = robots();
    const rule = Array.isArray(result.rules) ? result.rules[0] : result.rules;
    expect(rule).toBeDefined();
    expect(rule?.allow).toBe("/");
    const disallow = rule?.disallow;
    const list = Array.isArray(disallow) ? disallow : disallow ? [disallow] : [];

    expect(list).toEqual(
      expect.arrayContaining([
        "/*/checkout",
        "/*/cart",
        "/*/account",
        "/*/search",
        "/*/compare",
        "/*/supplies",
        "/*/services/post-job",
        "/*/beta",
        "/*/admin",
      ]),
    );
    expect(list.some((entry) => entry === "/*/p/" || entry === "/")).toBe(false);
    expect(result.sitemap).toMatch(/\/sitemap\.xml$/);
  });

  it("advertises the root sitemap URL that the sitemap index route serves", () => {
    const result = robots();
    expect(result.sitemap).toBe(`${getSiteUrl()}/sitemap.xml`);
    // Chunk URLs are linked from the index; robots must not point only at /sitemap/0.xml.
    expect(result.sitemap).not.toMatch(/\/sitemap\/\d+\.xml$/);
  });
});
