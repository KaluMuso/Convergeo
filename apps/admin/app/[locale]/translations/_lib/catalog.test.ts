import { describe, expect, it } from "vitest";

import { buildTranslationCatalog } from "./catalog";

describe("buildTranslationCatalog", () => {
  it("covers every namespace with English as the source of truth", async () => {
    const catalog = await buildTranslationCatalog();

    // English is the source; it is not a "translatable" locale.
    expect(catalog.defaultLocale).toBe("en");
    expect(catalog.translatableLocales).not.toContain("en");
    expect(catalog.namespaces.length).toBeGreaterThan(0);

    const events = catalog.namespaces.find((ns) => ns.namespace === "events");
    expect(events).toBeDefined();
    expect(events?.totalKeys).toBeGreaterThan(0);

    // French translated the events namespace (PR1) → non-zero coverage; Bemba has
    // no events file yet → zero. Coverage can never exceed the source key count.
    expect(events?.perLocale.fr).toBeGreaterThan(0);
    expect(events?.perLocale.bem).toBe(0);
    for (const locale of catalog.translatableLocales) {
      expect(events?.perLocale[locale]).toBeLessThanOrEqual(events?.totalKeys ?? 0);
    }
  });
});
