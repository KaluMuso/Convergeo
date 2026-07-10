import type { Metadata } from "next";

/** Default production origin; override with NEXT_PUBLIC_SITE_URL in deploy env. */
export function getSiteUrl(): string {
  return process.env.NEXT_PUBLIC_SITE_URL ?? "https://vergeo5.com";
}

function cloudinaryImageUrl(publicId: string, cloudName: string, width = 960): string {
  const safeId = publicId.trim().replace(/^https?:\/\//i, "");
  return `https://res.cloudinary.com/${cloudName}/image/upload/f_auto,q_auto,w_${width}/${safeId}`;
}

export function resolveCloudinaryImageUrls(publicIds: string[]): string[] {
  const cloudName = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
  if (!cloudName) {
    return [];
  }
  return publicIds.map((publicId) => cloudinaryImageUrl(publicId, cloudName));
}

function assertIntegerNgwee(ngwee: number): number {
  if (!Number.isInteger(ngwee)) {
    throw new TypeError(`ngwee must be an integer, received ${ngwee}`);
  }
  return ngwee;
}

/**
 * Exact ngwee → decimal-major ZMW string for schema.org Offer.price (no float math).
 * @example ngweeToZmwDecimal(123456) → "1234.56"
 */
export function ngweeToZmwDecimal(ngwee: number): string {
  const integerNgwee = assertIntegerNgwee(ngwee);
  const negative = integerNgwee < 0;
  const absolute = Math.abs(integerNgwee);
  const major = Math.floor(absolute / 100);
  const minor = absolute % 100;
  const formatted = `${major}.${minor.toString().padStart(2, "0")}`;
  return negative ? `-${formatted}` : formatted;
}

/** Strip query string and hash from a path or URL fragment used for canonicals. */
export function stripCanonicalParams(pathOrUrl: string): string {
  const withoutHash = pathOrUrl.split("#")[0] ?? pathOrUrl;
  const withoutQuery = withoutHash.split("?")[0] ?? withoutHash;
  return withoutQuery;
}

/**
 * Build a locale-prefixed shop canonical path (no query/filter params).
 * Strategy: each locale self-canonicals; no cross-locale hreflang alternates.
 */
export function buildLocaleCanonical(locale: string, ...segments: string[]): string {
  const cleaned = segments
    .flatMap((segment) => segment.split("/"))
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  const suffix = cleaned.length > 0 ? `/${cleaned.join("/")}` : "";
  return stripCanonicalParams(`/${locale}${suffix}`);
}

export function buildCanonicalAlternates(
  locale: string,
  ...segments: string[]
): NonNullable<Metadata["alternates"]> {
  return {
    canonical: buildLocaleCanonical(locale, ...segments),
  };
}

export function buildAbsoluteUrl(path: string): string {
  const base = getSiteUrl().replace(/\/$/, "");
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}

export type JsonLdOfferInput = {
  priceNgwee: number;
  inStock: boolean;
  sellerName: string;
  url?: string;
};

export type JsonLdAggregateRatingInput = {
  ratingValue: number;
  reviewCount: number;
};

export type JsonLdProductInput = {
  name: string;
  slug: string;
  locale: string;
  brand?: string | null;
  description?: string;
  imageUrls?: string[];
  sku?: string;
  offers: JsonLdOfferInput[];
  aggregateRating?: JsonLdAggregateRatingInput | null;
};

export type JsonLdLocalBusinessInput = {
  name: string;
  slug: string;
  locale: string;
  description?: string | null;
  logoUrl?: string | null;
  landmark?: string | null;
  lat?: number | null;
  lng?: number | null;
  aggregateRating?: JsonLdAggregateRatingInput | null;
};

export type JsonLdEventInstanceInput = {
  startsAt: string;
};

export type JsonLdEventTicketInput = {
  name: string;
  priceNgwee: number;
  isFree: boolean;
  isSoldOut: boolean;
};

export type JsonLdEventInput = {
  name: string;
  slug: string;
  locale: string;
  description?: string | null;
  venue?: string | null;
  landmark?: string | null;
  lat?: number | null;
  lng?: number | null;
  imageUrls?: string[];
  instances: JsonLdEventInstanceInput[];
  ticketTypes: JsonLdEventTicketInput[];
  organiserName: string;
  isFree: boolean;
};

export type JsonLdBreadcrumbItem = {
  name: string;
  path: string;
};

export function buildOffer(input: JsonLdOfferInput): Record<string, unknown> {
  return {
    "@type": "Offer",
    priceCurrency: "ZMW",
    price: ngweeToZmwDecimal(input.priceNgwee),
    availability: input.inStock ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
    seller: {
      "@type": "Organization",
      name: input.sellerName,
    },
    ...(input.url ? { url: input.url } : {}),
  };
}

export function buildAggregateRating(input: JsonLdAggregateRatingInput): Record<string, unknown> {
  return {
    "@type": "AggregateRating",
    ratingValue: input.ratingValue,
    reviewCount: input.reviewCount,
    bestRating: 5,
    worstRating: 1,
  };
}

export function buildProductJsonLd(input: JsonLdProductInput): Record<string, unknown> {
  const productUrl = buildAbsoluteUrl(buildLocaleCanonical(input.locale, "p", input.slug));
  const offers = input.offers.map((offer) =>
    buildOffer({
      ...offer,
      url: offer.url ?? productUrl,
    }),
  );

  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: input.name,
    url: productUrl,
    ...(input.description ? { description: input.description } : {}),
    ...(input.brand ? { brand: { "@type": "Brand", name: input.brand } } : {}),
    ...(input.imageUrls && input.imageUrls.length > 0 ? { image: input.imageUrls } : {}),
    ...(input.sku ? { sku: input.sku } : {}),
    ...(input.aggregateRating
      ? { aggregateRating: buildAggregateRating(input.aggregateRating) }
      : {}),
    offers: offers.length === 1 ? offers[0] : offers,
  };
}

export function buildLocalBusinessJsonLd(input: JsonLdLocalBusinessInput): Record<string, unknown> {
  const pageUrl = buildAbsoluteUrl(buildLocaleCanonical(input.locale, "v", input.slug));

  return {
    "@context": "https://schema.org",
    "@type": "LocalBusiness",
    name: input.name,
    url: pageUrl,
    ...(input.description ? { description: input.description } : {}),
    ...(input.logoUrl ? { image: input.logoUrl } : {}),
    ...(input.landmark
      ? {
          address: {
            "@type": "PostalAddress",
            streetAddress: input.landmark,
            addressLocality: "Lusaka",
            addressCountry: "ZM",
          },
        }
      : {}),
    ...(input.lat != null && input.lng != null
      ? {
          geo: {
            "@type": "GeoCoordinates",
            latitude: input.lat,
            longitude: input.lng,
          },
        }
      : {}),
    ...(input.aggregateRating
      ? { aggregateRating: buildAggregateRating(input.aggregateRating) }
      : {}),
  };
}

export function buildEventJsonLd(input: JsonLdEventInput): Record<string, unknown> {
  const pageUrl = buildAbsoluteUrl(buildLocaleCanonical(input.locale, "e", input.slug));
  const sortedInstances = [...input.instances].sort(
    (left, right) => new Date(left.startsAt).getTime() - new Date(right.startsAt).getTime(),
  );
  const primaryInstance = sortedInstances[0];

  const offers = input.isFree
    ? [
        {
          "@type": "Offer",
          price: "0",
          priceCurrency: "ZMW",
          availability: "https://schema.org/InStock",
          url: pageUrl,
        },
      ]
    : input.ticketTypes
        .filter((ticket) => !ticket.isFree)
        .map((ticket) => ({
          "@type": "Offer",
          name: ticket.name,
          price: ngweeToZmwDecimal(ticket.priceNgwee),
          priceCurrency: "ZMW",
          availability: ticket.isSoldOut
            ? "https://schema.org/SoldOut"
            : "https://schema.org/InStock",
          url: pageUrl,
        }));

  return {
    "@context": "https://schema.org",
    "@type": "Event",
    name: input.name,
    url: pageUrl,
    ...(input.description ? { description: input.description } : {}),
    ...(primaryInstance ? { startDate: primaryInstance.startsAt } : {}),
    ...(input.imageUrls && input.imageUrls.length > 0 ? { image: input.imageUrls } : {}),
    ...(input.venue || input.landmark
      ? {
          location: {
            "@type": "Place",
            ...(input.venue ? { name: input.venue } : {}),
            ...(input.landmark
              ? {
                  address: {
                    "@type": "PostalAddress",
                    streetAddress: input.landmark,
                    addressLocality: "Lusaka",
                    addressCountry: "ZM",
                  },
                }
              : {}),
            ...(input.lat != null && input.lng != null
              ? {
                  geo: {
                    "@type": "GeoCoordinates",
                    latitude: input.lat,
                    longitude: input.lng,
                  },
                }
              : {}),
          },
        }
      : {}),
    organizer: {
      "@type": "Organization",
      name: input.organiserName,
    },
    ...(offers.length > 0 ? { offers: offers.length === 1 ? offers[0] : offers } : {}),
  };
}

export function buildBreadcrumbListJsonLd(
  locale: string,
  items: JsonLdBreadcrumbItem[],
): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: buildAbsoluteUrl(buildLocaleCanonical(locale, ...item.path.split("/"))),
    })),
  };
}

export function JsonLdScript({
  data,
}: {
  data: Record<string, unknown> | Record<string, unknown>[];
}) {
  return (
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }} />
  );
}
