/**
 * Admin-set category icons, banners and per-locale banner copy
 * (`GET /categories/presentation`). Everything here is optional: any failure
 * degrades to "no presentation" so category pages and the home grid keep their
 * built-in imagery.
 */

import { absoluteApiUrl } from "../../../../lib/api-base-url";

export const CATEGORY_PRESENTATION_REVALIDATE_SECONDS = 300;
export const CATEGORY_PRESENTATION_CACHE_TAG = "category-presentation";

export type CategoryPresentation = {
  category_id: string;
  slug: string;
  icon_public_id: string | null;
  banner_public_id: string | null;
  banner_title_i18n: Record<string, string>;
  banner_description_i18n: Record<string, string>;
};

export type CategoryBannerContent = {
  imagePublicId: string | null;
  title: string | null;
  description: string | null;
};

const PUBLIC_ID_RE = /^[A-Za-z0-9_./-]{1,255}$/;

function cleanPublicId(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed && PUBLIC_ID_RE.test(trimmed) && !trimmed.includes("..") ? trimmed : null;
}

function cleanCopy(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const copy: Record<string, string> = {};
  for (const [locale, text] of Object.entries(value as Record<string, unknown>)) {
    if (typeof text === "string" && text.trim()) {
      copy[locale] = text.trim();
    }
  }
  return copy;
}

export function parseCategoryPresentations(data: unknown): CategoryPresentation[] {
  if (!Array.isArray(data)) {
    return [];
  }
  const result: CategoryPresentation[] = [];
  for (const entry of data) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const row = entry as Record<string, unknown>;
    if (typeof row.slug !== "string" || typeof row.category_id !== "string") {
      continue;
    }
    result.push({
      category_id: row.category_id,
      slug: row.slug,
      icon_public_id: cleanPublicId(row.icon_public_id),
      banner_public_id: cleanPublicId(row.banner_public_id),
      banner_title_i18n: cleanCopy(row.banner_title_i18n),
      banner_description_i18n: cleanCopy(row.banner_description_i18n),
    });
  }
  return result;
}

/** Slug → presentation. Empty map on any failure (API down, migration not applied). */
export async function fetchCategoryPresentations(): Promise<Map<string, CategoryPresentation>> {
  const url = absoluteApiUrl("/categories/presentation");
  if (!url) {
    return new Map();
  }
  try {
    const response = await fetch(url, {
      next: {
        revalidate: CATEGORY_PRESENTATION_REVALIDATE_SECONDS,
        tags: [CATEGORY_PRESENTATION_CACHE_TAG],
      },
      signal: AbortSignal.timeout(2_000),
    });
    if (!response.ok) {
      return new Map();
    }
    const rows = parseCategoryPresentations(await response.json());
    return new Map(rows.map((row) => [row.slug, row]));
  } catch {
    return new Map();
  }
}

function pickLocale(copy: Record<string, string>, locale: string): string | null {
  return copy[locale] ?? copy.en ?? null;
}

/**
 * Banner content for one locale, falling back to English copy. Returns null
 * when the admin has set neither a banner image nor a title.
 */
export function resolveCategoryBanner(
  presentation: CategoryPresentation | undefined,
  locale: string,
): CategoryBannerContent | null {
  if (!presentation) {
    return null;
  }
  const title = pickLocale(presentation.banner_title_i18n, locale);
  const imagePublicId = presentation.banner_public_id;
  if (!title && !imagePublicId) {
    return null;
  }
  return {
    imagePublicId,
    title,
    description: title ? pickLocale(presentation.banner_description_i18n, locale) : null,
  };
}
