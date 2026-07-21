"use client";

import { LinkButton } from "@vergeo/ui/src/link-button";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { HeroCarousel } from "@vergeo/ui/src/merch/hero-carousel";
import Link from "next/link";
import { useMemo } from "react";

import { HOME_HERO_FALLBACK_SLIDES } from "./home-hero-slides";

type CatalogTranslator = {
  (key: string, values?: Record<string, string | number>): string;
};

type HomeHeroCarouselProps = {
  locale: string;
  t: CatalogTranslator;
  brandName: string;
};

export function HomeHeroCarousel({ locale, t, brandName }: HomeHeroCarouselProps) {
  const slides = useMemo(() => {
    return HOME_HERO_FALLBACK_SLIDES.map((def, index) => {
      const isPrimary = def.primary === true;
      const priority = index === 0;

      return {
        key: def.key,
        eyebrow: isPrimary ? brandName : undefined,
        title: t(def.titleKey),
        subtitle: def.subtitleKey ? t(def.subtitleKey) : undefined,
        media: (
          <CloudinaryImage
            publicId={def.publicId}
            alt=""
            width={1440}
            ratio="21/9"
            priority={priority}
            sizes="100vw"
            className="h-full w-full [&_img]:h-full [&_img]:w-full [&_img]:object-cover"
          />
        ),
        cta: isPrimary ? (
          <>
            <LinkButton href={`/${locale}/search`} variant="primary" LinkComponent={Link}>
              {t("home.hero.primaryCta")}
            </LinkButton>
            <LinkButton
              href={`/${locale}/sell`}
              variant="secondary"
              LinkComponent={Link}
              className="border-panel-muted/40 bg-transparent text-panel-text hover:bg-panel-text/10"
            >
              {t("home.hero.secondaryCta")}
            </LinkButton>
          </>
        ) : undefined,
      };
    });
  }, [brandName, locale, t]);

  const labels = useMemo(
    () => ({
      previous: t("home.hero.carousel.previous"),
      next: t("home.hero.carousel.next"),
      slideOf: (current: number, total: number) =>
        t("home.hero.carousel.slideOf", { current, total }),
      ariaLabel: t("home.hero.carousel.ariaLabel"),
    }),
    [t],
  );

  return (
    <HeroCarousel
      slides={slides}
      labels={labels}
      headingId="home-hero-heading"
      className="motion-rise relative left-1/2 right-1/2 -ml-[50vw] -mr-[50vw] w-screen bg-panel"
    />
  );
}
