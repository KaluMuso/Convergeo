import { describe, expect, it } from "vitest";

import {
  parseMegaMenuMerchPayload,
  pickMegaMenuMerchSlot,
  withLocaleHref,
} from "./mega-menu-merch";

describe("mega-menu-merch", () => {
  it("parses featured minis and promo fields", () => {
    const payload = parseMegaMenuMerchPayload({
      featured_minis: [
        { title: "Itel A70", href: "/p/itel-a70", price_label: "K450.00" },
        { title: "", href: "/search" },
      ],
      promo_text: "Compare sellers",
      promo_cta_label: "Search",
      promo_href: "/search",
    });

    expect(payload.featuredMinis).toEqual([
      { title: "Itel A70", href: "/p/itel-a70", priceLabel: "K450.00" },
    ]);
    expect(payload.promoText).toBe("Compare sellers");
    expect(payload.promoCtaLabel).toBe("Search");
    expect(payload.promoHref).toBe("/search");
  });

  it("picks the active mega_menu slot", () => {
    const now = new Date("2026-07-21T12:00:00Z");
    const payload = pickMegaMenuMerchSlot(
      [
        {
          slot_key: "mega_menu",
          active: true,
          schedule_from: "2026-01-01T00:00:00Z",
          schedule_to: null,
          payload: {
            featured_minis: [{ title: "Mini", href: "/en/p/mini" }],
            promo_text: "Promo",
            promo_cta_label: "Go",
            promo_href: "/en/search",
          },
        },
      ],
      now,
    );

    expect(payload?.featuredMinis[0]?.title).toBe("Mini");
  });

  it("prefixes locale on root-relative hrefs", () => {
    expect(withLocaleHref("en", "/search")).toBe("/en/search");
    expect(withLocaleHref("bem", "/en/p/phone")).toBe("/en/p/phone");
    expect(withLocaleHref("nya", "https://vergeo5.com/search")).toBe("https://vergeo5.com/search");
  });
});
