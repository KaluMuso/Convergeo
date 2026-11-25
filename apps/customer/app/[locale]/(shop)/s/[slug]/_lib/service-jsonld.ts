import {
  buildAbsoluteUrl,
  buildLocaleCanonical,
  ngweeToZmwDecimal,
} from "@vergeo/ui/src/seo/json-ld";

export type ServiceJsonLdInput = {
  name: string;
  slug: string;
  locale: string;
  description?: string | null;
  serviceArea?: string | null;
  fromPriceNgwee?: number | null;
  isFree?: boolean;
  providerName: string;
  providerSlug?: string;
  ratingAvg?: number | null;
  ratingCount?: number;
};

export function buildServiceJsonLd(input: ServiceJsonLdInput): Record<string, unknown> {
  const pageUrl = buildAbsoluteUrl(buildLocaleCanonical(input.locale, "s", input.slug));
  const providerUrl =
    input.providerSlug && input.providerSlug.length > 0
      ? buildAbsoluteUrl(buildLocaleCanonical(input.locale, "v", input.providerSlug))
      : undefined;

  const offers = input.isFree
    ? {
        "@type": "Offer",
        price: "0",
        priceCurrency: "ZMW",
        availability: "https://schema.org/InStock",
        url: pageUrl,
      }
    : input.fromPriceNgwee != null
      ? {
          "@type": "Offer",
          price: ngweeToZmwDecimal(input.fromPriceNgwee),
          priceCurrency: "ZMW",
          availability: "https://schema.org/InStock",
          url: pageUrl,
        }
      : {
          "@type": "Offer",
          priceCurrency: "ZMW",
          availability: "https://schema.org/InStock",
          url: pageUrl,
        };

  const aggregateRating =
    input.ratingCount && input.ratingCount > 0 && input.ratingAvg != null
      ? {
          "@type": "AggregateRating",
          ratingValue: input.ratingAvg,
          reviewCount: input.ratingCount,
        }
      : undefined;

  return {
    "@context": "https://schema.org",
    "@type": "Service",
    name: input.name,
    url: pageUrl,
    ...(input.description ? { description: input.description } : {}),
    ...(input.serviceArea
      ? {
          areaServed: {
            "@type": "Place",
            name: input.serviceArea,
          },
        }
      : {}),
    provider: {
      "@type": "LocalBusiness",
      name: input.providerName,
      ...(providerUrl ? { url: providerUrl } : {}),
    },
    offers,
    ...(aggregateRating ? { aggregateRating } : {}),
  };
}
