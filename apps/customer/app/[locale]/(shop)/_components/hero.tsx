import { CloudinaryImage } from "@vergeo/ui/src/media/cloudinary-image";
import { resolveHeroVariant } from "@vergeo/ui/src/merch/hero-registry";
import Link from "next/link";
import { preload } from "react-dom";

import type { MerchSlotRow } from "./merch-data";

type CatalogTranslator = (key: string, values?: Record<string, string | number>) => string;

function readPayloadString(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function normalizeMessageKey(key: string): string {
  if (key.startsWith("merch.")) {
    return key.replace(/^merch\./, "home.");
  }
  return key;
}

function resolvePayloadText(
  payload: Record<string, unknown>,
  key: string,
  t: CatalogTranslator,
  fallbackKey: string,
): string {
  const messageKey = readPayloadString(payload, key);
  if (!messageKey) {
    return t(fallbackKey);
  }

  const normalized = normalizeMessageKey(messageKey);
  const resolved = t(normalized);
  if (resolved === normalized && normalized !== fallbackKey) {
    return t(fallbackKey);
  }

  return resolved;
}

function buildHeroCta(
  label: string,
  href: string,
  variant: "primary" | "secondary",
): React.ReactNode {
  const className =
    variant === "primary"
      ? "inline-flex min-h-11 items-center justify-center rounded-pill bg-primary px-4 text-sm font-semibold text-surface"
      : "inline-flex min-h-11 items-center justify-center rounded-pill border border-border bg-surface px-4 text-sm font-semibold text-text";

  return (
    <Link href={href} className={className}>
      {label}
    </Link>
  );
}

function buildHeroPreloadUrl(publicId: string): string | undefined {
  const cloud = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
  if (!cloud) {
    return undefined;
  }

  const safeId = publicId.trim().replace(/^https?:\/\//i, "");
  return `https://res.cloudinary.com/${cloud}/image/upload/f_auto,q_auto,w_720/${safeId}`;
}

function buildHeroMedia(
  publicId: string | undefined,
  alt: string,
  priority: boolean,
): React.ReactNode | undefined {
  if (!publicId) {
    return undefined;
  }

  if (priority) {
    const preloadUrl = buildHeroPreloadUrl(publicId);
    if (preloadUrl) {
      preload(preloadUrl, { as: "image" });
    }
  }

  return (
    <CloudinaryImage publicId={publicId} alt={alt} width={720} ratio="16/9" priority={priority} />
  );
}

type HomeHeroProps = {
  slot?: MerchSlotRow;
  locale: string;
  t: CatalogTranslator;
};

export function HomeHero({ slot, locale, t }: HomeHeroProps) {
  const payload = slot?.payload ?? {};
  const variantKey = slot?.variant_key ?? "default";
  const HeroVariant = resolveHeroVariant(variantKey);

  const title = resolvePayloadText(payload, "title_key", t, "home.hero.fallbackTitle");
  const subtitle = resolvePayloadText(payload, "subtitle_key", t, "home.hero.fallbackSubtitle");
  const eyebrow = readPayloadString(payload, "eyebrow_key")
    ? resolvePayloadText(payload, "eyebrow_key", t, "home.hero.eyebrow")
    : t("home.hero.eyebrow");

  const primaryHref = readPayloadString(payload, "primary_cta_href") ?? `/${locale}/search`;
  const secondaryHref = readPayloadString(payload, "secondary_cta_href") ?? `/${locale}/sell`;

  const primaryCta = buildHeroCta(t("home.hero.primaryCta"), primaryHref, "primary");
  const secondaryCta = buildHeroCta(t("home.hero.secondaryCta"), secondaryHref, "secondary");

  const imagePublicId = readPayloadString(payload, "image_public_id");
  const media = buildHeroMedia(imagePublicId, title, true);

  const statsRaw = payload.stats;
  const stats =
    Array.isArray(statsRaw) && statsRaw.length > 0
      ? statsRaw
          .map((entry, index) => {
            if (!entry || typeof entry !== "object") {
              return null;
            }
            const record = entry as Record<string, unknown>;
            const labelKey = readPayloadString(record, "label_key");
            const valueKey = readPayloadString(record, "value_key");
            if (!labelKey || !valueKey) {
              return null;
            }
            return {
              label: t(labelKey),
              value: t(valueKey),
              key: `${index}-${labelKey}`,
            };
          })
          .filter((entry): entry is { label: string; value: string; key: string } => entry !== null)
      : undefined;

  const slides =
    variantKey === "carousel"
      ? [
          {
            key: "primary",
            title,
            subtitle,
            media,
            cta: primaryCta,
          },
        ]
      : undefined;

  return (
    <HeroVariant
      eyebrow={eyebrow}
      title={title}
      subtitle={subtitle}
      primaryCta={primaryCta}
      secondaryCta={secondaryCta}
      media={media}
      stats={stats}
      slides={slides}
    />
  );
}
