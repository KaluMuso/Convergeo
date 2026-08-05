import { describe, expect, it } from "vitest";

import { buildOgImageUrl, buildSocialMetadata } from "./metadata";

describe("buildOgImageUrl", () => {
  it("builds an absolute OG image URL with name and price params", () => {
    expect(buildOgImageUrl("en", { name: "Itel A70", price: "K1,234.56" })).toBe(
      "https://vergeo5.com/en/opengraph-image?name=Itel+A70&price=K1%2C234.56",
    );
  });

  it("omits query string when no params", () => {
    expect(buildOgImageUrl("fr")).toBe("https://vergeo5.com/fr/opengraph-image");
  });
});

describe("buildSocialMetadata", () => {
  it("returns openGraph with siteName and twitter summary_large_image", () => {
    const social = buildSocialMetadata({
      title: "Itel A70",
      description: "Shop Itel A70 on Vergeo5",
      locale: "en",
      url: "/en/p/itel-a70",
      imageUrl: "/en/opengraph-image?name=Itel+A70",
    });

    expect(social.openGraph?.siteName).toBe("Vergeo5");
    expect(social.openGraph?.url).toBe("https://vergeo5.com/en/p/itel-a70");
    expect(social.twitter).toEqual(
      expect.objectContaining({
        card: "summary_large_image",
        title: "Itel A70",
      }),
    );
    expect(social.openGraph?.images).toEqual([
      { url: "https://vergeo5.com/en/opengraph-image?name=Itel+A70" },
    ]);
  });
});
