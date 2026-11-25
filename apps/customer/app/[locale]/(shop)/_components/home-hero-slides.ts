/**
 * Curated fallback hero imagery for the default (no-campaign) home carousel.
 * Slide 1 is the brand illustration; the rest use seeded Cloudinary demo
 * category assets — honest merch, not stock scenes.
 */
export type HomeHeroSlideDef = {
  key: string;
  /** Cloudinary public id; omitted for the brand illustration slide. */
  publicId?: string;
  titleKey: string;
  subtitleKey?: string;
  /** Slide 1 carries brand wordmark + primary CTAs. */
  primary?: boolean;
};

export const HOME_HERO_FALLBACK_SLIDES: HomeHeroSlideDef[] = [
  {
    key: "marketplace",
    titleKey: "home.hero.fallbackTitle",
    subtitleKey: "home.hero.fallbackSubtitle",
    primary: true,
  },
  {
    key: "fashion",
    publicId: "demo/categories/chitenge-fabric",
    titleKey: "home.hero.slides.fashion.title",
    subtitleKey: "home.hero.slides.fashion.subtitle",
  },
  {
    key: "tech",
    publicId: "demo/categories/laptops-computers",
    titleKey: "home.hero.slides.tech.title",
    subtitleKey: "home.hero.slides.tech.subtitle",
  },
  {
    key: "power",
    publicId: "demo/categories/solar-power",
    titleKey: "home.hero.slides.power.title",
    subtitleKey: "home.hero.slides.power.subtitle",
  },
  {
    key: "essentials",
    publicId: "demo/categories/kitchenware",
    titleKey: "home.hero.slides.essentials.title",
    subtitleKey: "home.hero.slides.essentials.subtitle",
  },
];
