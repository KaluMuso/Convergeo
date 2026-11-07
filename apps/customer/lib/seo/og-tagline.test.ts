import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { resolveOgTagline } from "./og-tagline";

describe("resolveOgTagline", () => {
  it("returns the locale's message, not the English string", () => {
    expect(resolveOgTagline("en")).toContain("Zambia");
    expect(resolveOgTagline("fr")).not.toBe(resolveOgTagline("en"));
    expect(resolveOgTagline("zh")).not.toBe(resolveOgTagline("en"));
    expect(resolveOgTagline("bem")).not.toBe(resolveOgTagline("en"));
    expect(resolveOgTagline("nya")).not.toBe(resolveOgTagline("en"));
  });

  it("falls back to English for unknown locales", () => {
    expect(resolveOgTagline("xx")).toBe(resolveOgTagline("en"));
    expect(resolveOgTagline(undefined)).toBe(resolveOgTagline("en"));
  });

  it("the OG route no longer hard-codes the English tagline", () => {
    const source = readFileSync(
      join(__dirname, "../../app/[locale]/(shop)/opengraph-image.tsx"),
      "utf8",
    );
    expect(source).not.toContain("escrow-backed");
    expect(source).toContain("resolveOgTagline");
  });
});
