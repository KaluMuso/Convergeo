// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import bem from "../../../../../../packages/i18n/messages/bem/catalog.json";
import en from "../../../../../../packages/i18n/messages/en/catalog.json";
import fr from "../../../../../../packages/i18n/messages/fr/catalog.json";
import nya from "../../../../../../packages/i18n/messages/nya/catalog.json";
import zh from "../../../../../../packages/i18n/messages/zh/catalog.json";

import type { AdCreative } from "./home-feed/feed-types";
import { HomeHeroCarousel } from "./home-hero-carousel";

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

  it("renders no sponsored slide when the API served none (expired, paused or blocked)", () => {
    renderCarousel("en", []);
    expect(document.querySelector('[data-slide^="sponsored-"]')).toBeNull();
    expect(screen.queryByText(en.home.feed.sponsored)).toBeNull();
  });
});
