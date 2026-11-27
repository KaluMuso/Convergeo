// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import bem from "../../../../../../packages/i18n/messages/bem/catalog.json";
import en from "../../../../../../packages/i18n/messages/en/catalog.json";
import fr from "../../../../../../packages/i18n/messages/fr/catalog.json";
import nya from "../../../../../../packages/i18n/messages/nya/catalog.json";
import zh from "../../../../../../packages/i18n/messages/zh/catalog.json";

import { HomeHeroCarousel } from "./home-hero-carousel";

import type { AdCreative } from "./home-feed/feed-types";
import type { ReactNode } from "react";

vi.mock("@vergeo/ui/src/media/cloudinary-image", () => ({
  CloudinaryImage: () => <span data-testid="img" />,
}));
vi.mock("@vergeo/ui/src/merch/hero-carousel", () => ({
  HeroCarousel: ({
    slides,
  }: {
    slides: { key: string; eyebrow?: ReactNode; title: ReactNode; cta?: ReactNode }[];
  }) => (
    <ul>
      {slides.map((slide) => (
        <li key={slide.key} data-slide={slide.key}>
          {slide.eyebrow}
          <h2>{slide.title}</h2>
          {slide.cta}
        </li>
      ))}
    </ul>
  ),
}));
vi.mock("./home-feed/ad-tracker", () => ({
  AdTracker: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const ad: AdCreative = {
  placement_id: "11111111-1111-4111-8111-111111111111",
  advertiser_name: "Acme Ltd",
  image_public_id: "ads/acme",
  headline: "Acme phones",
  body: null,
  cta_label: "Shop now",
  cta_href: "/l/abc",
  external: false,
  sponsored: true,
};

const MESSAGES = { en, bem, nya, fr, zh } as const;

function renderCarousel(locale: keyof typeof MESSAGES, slides: AdCreative[]) {
  return render(
    <NextIntlClientProvider locale={locale} messages={{ catalog: MESSAGES[locale] }}>
      <HomeHeroCarousel locale={locale} brandName="Vergeo5" sponsoredSlides={slides} />
    </NextIntlClientProvider>,
  );
}

afterEach(cleanup);

describe("sponsored hero slides", () => {
  it.each(Object.keys(MESSAGES) as (keyof typeof MESSAGES)[])(
    "labels every admin placement as sponsored in %s",
    (locale) => {
      const label = MESSAGES[locale].home.feed.sponsored;
      expect(label.trim().length).toBeGreaterThan(0);
      renderCarousel(locale, [ad]);
      const slide = document.querySelector(`[data-slide="sponsored-${ad.placement_id}"]`);
      expect(slide).not.toBeNull();
      expect(slide).toHaveTextContent(label);
      expect(slide).toHaveTextContent("Acme Ltd");
      expect(screen.getByRole("link", { name: `${label}: Shop now` })).toHaveAttribute(
        "href",
        `/${locale}/l/abc`,
      );
    },
  );

  it("links a vendor sponsored slide to both the promoted item and the vendor page", () => {
    renderCarousel("en", [
      {
        ...ad,
        target_href: "/p/steel-kettle",
        vendor_href: "/v/acme-shop",
        vendor_name: "Acme Shop",
      },
    ]);
    const label = en.home.feed.sponsored;
    expect(screen.getByRole("link", { name: `${label}: Shop now` })).toHaveAttribute(
      "href",
      "/en/p/steel-kettle",
    );
    expect(screen.getByTestId("hero-sponsored-vendor-cta")).toHaveAttribute(
      "href",
      "/en/v/acme-shop",
    );
    expect(screen.getByTestId("hero-sponsored-vendor-cta")).toHaveTextContent("Visit Acme Shop");
    // The generic non-sponsored CTAs never appear on a sponsored slide.
    const slide = document.querySelector(`[data-slide="sponsored-${ad.placement_id}"]`);
    expect(slide).not.toHaveTextContent(en.home.hero.primaryCta);
    expect(slide).not.toHaveTextContent(en.home.hero.secondaryCta);
  });

  it("links to the vendor page alone when the target is the vendor itself", () => {
    renderCarousel("en", [{ ...ad, target_href: null, vendor_href: "/v/acme-shop" }]);
    expect(
      screen.getByRole("link", { name: `${en.home.feed.sponsored}: Shop now` }),
    ).toHaveAttribute("href", "/en/v/acme-shop");
    expect(screen.queryByTestId("hero-sponsored-vendor-cta")).toBeNull();
  });

  it("keeps the generic CTAs on the brand slide and the cta_href on house ads", () => {
    renderCarousel("en", [ad]);
    const brand = document.querySelector('[data-slide="brand"], li');
    expect(brand).not.toBeNull();
    expect(screen.getAllByText(en.home.hero.primaryCta).length).toBeGreaterThan(0);
  });

  it("renders no sponsored slide when the API served none (expired, paused or blocked)", () => {
    renderCarousel("en", []);
    expect(document.querySelector('[data-slide^="sponsored-"]')).toBeNull();
    expect(screen.queryByText(en.home.feed.sponsored)).toBeNull();
  });
});
