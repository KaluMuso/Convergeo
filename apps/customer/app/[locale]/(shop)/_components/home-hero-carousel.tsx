"use client";

import { buttonBaseClasses, buttonSizeClasses } from "@vergeo/ui/src/button";
import { LinkButton } from "@vergeo/ui/src/link-button";
import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { HeroCarousel } from "@vergeo/ui/src/merch/hero-carousel";
import Image from "next/image";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import {
  CI_PERF_IMAGE_ID,
  ciPerfPublicEnabled,
} from "../../../../../../packages/ui/src/media/ci-perf-fixture";

import { AdTracker } from "./home-feed/ad-tracker";
import { localizeHref, type AdCreative } from "./home-feed/feed-types";
import { HOME_HERO_FALLBACK_SLIDES } from "./home-hero-slides";

const HERO_ILLUSTRATION_SRC = "/images/hero/marketplace-1280.webp";

/** CTAs sit on the always-dark `--panel` scrim, so they use panel tokens, not page tokens. */
const HERO_PRIMARY_CTA = `${buttonBaseClasses} ${buttonSizeClasses.md} bg-panel-text text-panel hover:opacity-90`;
const HERO_SECONDARY_CTA = `${buttonBaseClasses} ${buttonSizeClasses.md} border border-panel-text/80 bg-panel/50 text-panel-text hover:bg-panel-text/15`;

function HeroIllustration({ priority }: { priority: boolean }) {
  return (
    <Image
      src={HERO_ILLUSTRATION_SRC}
      alt=""
      width={1280}
      height={720}
      sizes="100vw"
      priority={priority}
      className="h-full w-full object-cover object-[72%_center]"
    />
  );
}

type HomeHeroCarouselProps = {
  locale: string;
  brandName: string;
  /**
   * Admin-scheduled sponsored slides (already filtered to enabled + in-window by
   * the API). Inserted after the brand slide and always labelled "Sponsored".
   */
  sponsoredSlides?: AdCreative[];
};

export function HomeHeroCarousel({
  locale,
  brandName,
  sponsoredSlides = [],
}: HomeHeroCarouselProps) {
  const t = useTranslations("catalog");

  const slides = useMemo(() => {
    const hasCloudinary = Boolean(process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME);
    const curated = HOME_HERO_FALLBACK_SLIDES.map((def, index) => {
      const isPrimary = def.primary === true;
      const priority = index === 0;
      const publicId =
        isPrimary && ciPerfPublicEnabled()
          ? CI_PERF_IMAGE_ID
          : hasCloudinary
            ? def.publicId
            : undefined;

      return {
        key: def.key,
        eyebrow: isPrimary ? brandName : undefined,
        title: t(def.titleKey),
        subtitle: def.subtitleKey ? t(def.subtitleKey) : undefined,
        media: publicId ? (
          <CloudinaryImage
            publicId={publicId}
            alt=""
            width={1440}
            ratio="21/9"
            priority={priority}
            sizes="100vw"
            className="h-full w-full [&_img]:h-full [&_img]:w-full [&_img]:object-cover"
          />
        ) : (
          <HeroIllustration priority={priority} />
        ),
        cta: isPrimary ? (
          <>
            <Link href={`/${locale}/search`} className={HERO_PRIMARY_CTA}>
              {t("home.hero.primaryCta")}
            </Link>
            <Link href={`/${locale}/sell`} className={HERO_SECONDARY_CTA}>
              {t("home.hero.secondaryCta")}
            </Link>
          </>
        ) : undefined,
      };
    });
    const sponsoredLabel = t("home.feed.sponsored");
    const sponsored = sponsoredSlides.map((ad) => ({
      key: `sponsored-${ad.placement_id}`,
      eyebrow: (
        <span className="inline-flex items-center gap-2">
          <span className="rounded-pill bg-panel-text px-2 py-0.5 text-xs font-semibold text-panel">
            {sponsoredLabel}
          </span>
          <span>{ad.advertiser_name}</span>
        </span>
      ),
      title: ad.headline,
      subtitle: ad.body ?? undefined,
      media: (
        <CloudinaryImage
          publicId={ad.image_public_id}
          alt=""
          width={1440}
          ratio="21/9"
          sizes="100vw"
          className="h-full w-full [&_img]:h-full [&_img]:w-full [&_img]:object-cover"
        />
      ),
      cta: (
        <AdTracker placementId={ad.placement_id}>
          <LinkButton
            href={localizeHref(ad.cta_href, locale)}
            variant="primary"
            LinkComponent={ad.external ? undefined : Link}
            aria-label={`${sponsoredLabel}: ${ad.cta_label ?? ad.headline}`}
            {...(ad.external ? { target: "_blank", rel: "sponsored noopener noreferrer" } : {})}
          >
            {ad.cta_label ?? t("home.feed.adCta")}
          </LinkButton>
        </AdTracker>
      ),
    }));
    return [...curated.slice(0, 1), ...sponsored, ...curated.slice(1)];
  }, [brandName, locale, sponsoredSlides, t]);

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
      className="motion-rise relative -mx-4 overflow-hidden bg-panel sm:mx-0 sm:rounded-xl"
    />
  );
}
