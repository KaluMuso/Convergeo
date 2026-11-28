import { describe, expect, it } from "vitest";

import robots from "./robots";

describe("robots.ts", () => {
  it("disallows all crawlers on the vendor origin", () => {
    const result = robots();
    const rule = Array.isArray(result.rules) ? result.rules[0] : result.rules;
    expect(rule).toBeDefined();
    expect(rule?.userAgent).toBe("*");
    expect(rule?.disallow).toBe("/");
    expect(rule?.allow).toBeUndefined();
    expect(result.sitemap).toBeUndefined();
  });
});
