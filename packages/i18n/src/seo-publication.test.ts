import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCALES, PUBLIC_LOCALES } from "./locales";
import {
  isSeoIndexableLocale,
  listSeoIndexableLocales,
  resolveSeoAlternateLocales,
  robotsForLocalePublication,
  SEO_INDEXABLE_LOCALES,
} from "./seo-publication";

describe("SEO_INDEXABLE_LOCALES publication policy", () => {
  it("keeps en/fr published and leaves bem/nya/zh routable but unpublished", () => {
    expect([...SEO_INDEXABLE_LOCALES]).toEqual(["en", "fr"]);
    expect(listSeoIndexableLocales()).toEqual(["en", "fr"]);

    for (const locale of LOCALES) {
      expect(typeof locale).toBe("string");
    }
    expect(LOCALES).toEqual(expect.arrayContaining(["bem", "nya", "en", "fr", "zh"]));
    expect(PUBLIC_LOCALES).toEqual(["en", "bem", "nya", "fr"]);

    expect(isSeoIndexableLocale("en")).toBe(true);
    expect(isSeoIndexableLocale("fr")).toBe(true);
    expect(isSeoIndexableLocale("zh")).toBe(false);
    expect(isSeoIndexableLocale("bem")).toBe(false);
    expect(isSeoIndexableLocale("nya")).toBe(false);
  });

  it("omits unapproved locales from alternate resolution even if requested", () => {
    expect(resolveSeoAlternateLocales()).toEqual(["en", "fr"]);
    expect(resolveSeoAlternateLocales([...LOCALES])).toEqual(["en", "fr"]);
    expect(resolveSeoAlternateLocales(["en", "bem", "fr", "nya", "zh"])).toEqual(["en", "fr"]);
    expect(resolveSeoAlternateLocales(["bem", "nya"])).toEqual([]);
  });

  it("applies noindex,follow for unapproved locales and allows index for approved", () => {
    expect(robotsForLocalePublication("en")).toEqual({ index: true, follow: true });
    expect(robotsForLocalePublication("zh")).toEqual({ index: false, follow: true });
    expect(robotsForLocalePublication("bem")).toEqual({ index: false, follow: true });
    expect(robotsForLocalePublication("nya")).toEqual({ index: false, follow: true });
  });
});

describe("approved locale transition", () => {
  afterEach(() => {
    vi.resetModules();
  });

  it("documents that extending SEO_INDEXABLE_LOCALES is the flip switch", async () => {
    // Simulate post-review approval by resolving alternates as if bem were published.
    const withBem = resolveSeoAlternateLocales(["en", "fr", "zh", "bem"]);
    // Until the constant includes bem, policy still strips it — proving the gate.
    expect(withBem).toEqual(["en", "fr"]);
    expect(withBem).not.toContain("bem");

    // The constant itself is the single update surface after native sign-off.
    expect(SEO_INDEXABLE_LOCALES).not.toContain("bem");
    expect(SEO_INDEXABLE_LOCALES).not.toContain("nya");
  });
});
