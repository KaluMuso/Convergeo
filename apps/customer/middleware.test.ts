import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, LOCALES } from "@vergeo/i18n";

describe("customer locale routing", () => {
  it("redirect contract points / to /en", () => {
    expect(`/${DEFAULT_LOCALE}`).toBe("/en");
  });

  it("supports en and fr locale switch targets", () => {
    expect(LOCALES).toContain("en");
    expect(LOCALES).toContain("fr");
  });

  it("treats unknown locale codes as unsupported", () => {
    expect(LOCALES.includes("zz" as (typeof LOCALES)[number])).toBe(false);
  });
});
