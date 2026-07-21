import type { ComponentType } from "react";

import { HeroCarousel } from "./hero-carousel";
import { HeroDefault } from "./hero-default";
import { HeroEditorialLight } from "./hero-editorial-light";
import { HeroGradientDark } from "./hero-gradient-dark";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type HeroVariantComponent = ComponentType<any>;

const HERO_VARIANTS: Record<string, HeroVariantComponent> = {
  "editorial-light": HeroEditorialLight,
  "gradient-dark": HeroGradientDark,
  carousel: HeroCarousel,
};

export function resolveHeroVariant(variantKey: string): HeroVariantComponent {
  return HERO_VARIANTS[variantKey] ?? HeroDefault;
}

export { HeroCarousel, HeroDefault, HeroEditorialLight, HeroGradientDark };
export type { HeroCarouselLabels, HeroCarouselProps, HeroCarouselSlide } from "./hero-carousel";
