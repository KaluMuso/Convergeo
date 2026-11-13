import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

describe("privacy page links", () => {
  const source = readFileSync(join(__dirname, "page.tsx"), "utf8");

  it("links to the real account privacy route, not the dead /account/data", () => {
    expect(source).not.toContain("/account/data");
    expect(source).toContain("/account/privacy");
    expect(existsSync(join(__dirname, "../../../account/privacy/page.tsx"))).toBe(true);
  });
});
