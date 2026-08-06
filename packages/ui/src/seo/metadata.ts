import type { Metadata } from "next";

import { buildAbsoluteUrl, buildLocaleCanonical, getSiteUrl } from "./json-ld";

export const DEFAULT_SITE_NAME = "Vergeo5";

export type SocialMetadataInput = {
  title: string;
  description: string;
  locale: string;
  /** Locale-prefixed canonical path (e.g. `/en/p/foo`) or absolute URL. */
  url: string;
  siteName?: string;
  type?: "website" | "article";
  imageUrl?: string | null;
  imageUrls?: string[];
};

/** Absolute URL for the dynamic OG image route (name + optional price). */
export function buildOgImageUrl(
  locale: string,
  params?: { name?: string; price?: string },
): string {
  const search = new URLSearchParams();
  if (params?.name) {
    search.set("name", params.name);
  }
  if (params?.price) {
    search.set("price", params.price);
  }
  const query = search.toString();
  const path = `${buildLocaleCanonical(locale)}/opengraph-image${query ? `?${query}` : ""}`;
  return buildAbsoluteUrl(path);
}

function resolveCanonicalUrl(url: string): string {
  return url.startsWith("http") ? url : buildAbsoluteUrl(url);
}

/** Shared OpenGraph + Twitter Card metadata for shop and marketing pages. */
export function buildSocialMetadata(
  input: SocialMetadataInput,
): Pick<Metadata, "openGraph" | "twitter"> {
  const canonicalUrl = resolveCanonicalUrl(input.url);
  const images = input.imageUrls ?? (input.imageUrl ? [input.imageUrl] : undefined);
  const ogImages = images?.map((url) => ({ url: resolveCanonicalUrl(url) }));

  return {
    openGraph: {
      title: input.title,
      description: input.description,
      type: input.type ?? "website",
      locale: input.locale,
      url: canonicalUrl,
      siteName: input.siteName ?? DEFAULT_SITE_NAME,
      ...(ogImages && ogImages.length > 0 ? { images: ogImages } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title: input.title,
      description: input.description,
      ...(images && images.length > 0
        ? { images: images.map((url) => resolveCanonicalUrl(url)) }
        : {}),
    },
  };
}

export function getMetadataBase(): URL {
  return new URL(getSiteUrl());
}
