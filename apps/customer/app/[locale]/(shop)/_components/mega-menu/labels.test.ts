import { loadNamespace, LOCALES, type Locale } from "@vergeo/i18n";
import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { describe, expect, it } from "vitest";

import { buildMegaMenuLabels, EVENT_CATEGORY_SLUGS, SERVICE_VERTICAL_SLUGS } from "./labels";

function leaves(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (value && typeof value === "object") return Object.values(value).flatMap(leaves);
  return [];
}

async function labelsFor(locale: Locale) {
  const nav = await loadNamespace(locale, "nav");
  const t = createTranslator({
    locale,
    messages: { nav } as AbstractIntlMessages,
    namespace: "nav",
  });
  return buildMegaMenuLabels(t);
}

describe("mega menu labels (nav.megaMenu.*)", () => {
  for (const locale of LOCALES) {
    it(`${locale}: every key resolves to non-empty copy (bem/nya fall back to English)`, async () => {
      const labels = await labelsFor(locale);
      const all = leaves(labels);
      expect(all.length).toBeGreaterThan(40);
      for (const value of all) {
        expect(value.trim()).not.toBe("");
        expect(value).not.toMatch(/megaMenu\.|nav\./);
      }
      expect(Object.keys(labels.serviceVerticals)).toEqual([...SERVICE_VERTICAL_SLUGS]);
      expect(Object.keys(labels.eventCategories)).toEqual([...EVENT_CATEGORY_SLUGS]);
      expect(labels.helloUser).toContain("{name}");
      expect(labels.allIn).toContain("{name}");
      expect(labels.viewAllIn).toContain("{name}");
    });
  }

  it("translates the menu chrome for fr and zh and falls back to English for bem/nya", async () => {
    const [en, fr, zh, bem, nya] = await Promise.all(
      (["en", "fr", "zh", "bem", "nya"] as const).map(labelsFor),
    );
    expect(fr!.shopByDepartment).not.toBe(en!.shopByDepartment);
    expect(zh!.shopByDepartment).not.toBe(en!.shopByDepartment);
    expect(bem!.shopByDepartment).toBe(en!.shopByDepartment);
    expect(nya!.helpSettings).toBe(en!.helpSettings);
  });
});
