/**
 * Pure sitemap / robots eligibility rules for public customer discovery routes.
 * Kept free of Next.js runtime so unit tests can exercise policy without I/O.
 *
 * Locale publication (which locales may appear in the sitemap / hreflang) lives in
 * `@vergeo/i18n` → `SEO_INDEXABLE_LOCALES` (CUST-SEO-02). This module only covers
 * path/entity eligibility.
 */

import { SEO_INDEXABLE_LOCALES } from "@vergeo/i18n";

/** Locales that may be listed in the sitemap (alias of the central SEO policy). */
export function sitemapLocales(): readonly string[] {
  return SEO_INDEXABLE_LOCALES;
}

/** Indexable static shop hubs (locale-prefixed). Supplies deliberately omitted. */
export const SITEMAP_STATIC_SEGMENTS = [
  "",
  "categories",
  "directory",
  "events",
  "services",
] as const;

export type SitemapStaticSegment = (typeof SITEMAP_STATIC_SEGMENTS)[number];

/**
 * Routes that must never appear in the sitemap (private, transactional,
 * parameterised, empty shells, beta-only, or deliberate noindex policy).
 */
export const SITEMAP_EXCLUDED_SEGMENTS = [
  "search",
  "cart",
  "checkout",
  "account",
  "admin",
  "ask",
  "calendar",
  "compare",
  "supplies",
  "beta",
  "login",
  "signup",
  "onboarding",
  "ui",
  "post-job",
] as const;

/** robots.txt disallow suffixes (locale wildcard applied by robots.ts). */
export const ROBOTS_DISALLOW_SUFFIXES = [
  "/checkout",
  "/checkout/",
  "/cart",
  "/cart/",
  "/account",
  "/account/",
  "/admin",
  "/admin/",
  "/search",
  "/search/",
  "/ask",
  "/ask/",
  "/calendar",
  "/calendar/",
  "/compare",
  "/compare/",
  "/supplies",
  "/supplies/",
  "/services/post-job",
  "/services/post-job/",
  "/beta",
  "/beta/",
  "/login",
  "/login/",
  "/onboarding",
  "/onboarding/",
  "/ui",
  "/ui/",
] as const;

/** Next metadata route ids may arrive as strings ("0"); coerce before chunk compares. */
export function coerceSitemapId(raw: number | string): number | null {
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
}

export function isSitemapEligibleStaticSegment(segment: string): boolean {
  if ((SITEMAP_EXCLUDED_SEGMENTS as readonly string[]).includes(segment)) {
    return false;
  }
  return (SITEMAP_STATIC_SEGMENTS as readonly string[]).includes(segment);
}

/** True when a category slug is safe to advertise (non-empty, not a reserved shell). */
export function isSitemapEligibleCategorySlug(slug: string): boolean {
  const trimmed = slug.trim();
  if (!trimmed) {
    return false;
  }
  if (trimmed.includes("?") || trimmed.includes("#")) {
    return false;
  }
  return true;
}

/** True when a public entity slug (product/vendor/service/event) may be listed. */
export function isSitemapEligibleEntitySlug(slug: string): boolean {
  const trimmed = slug.trim();
  if (!trimmed) {
    return false;
  }
  if (trimmed.includes("?") || trimmed.includes("#") || trimmed.includes("/")) {
    return false;
  }
  return true;
}

/**
 * Meta-robots intent for common customer route kinds.
 * Complements robots.txt; pages can still tighten further (e.g. filtered PLP).
 */
export type CustomerRouteRobotsKind =
  | "public_catalogue"
  | "parameterised_search"
  | "transactional"
  | "private_account"
  | "beta_only"
  | "empty_or_missing"
  | "gated_b2b";

export function robotsForRouteKind(kind: CustomerRouteRobotsKind): {
  index: boolean;
  follow: boolean;
} {
  switch (kind) {
    case "public_catalogue":
      return { index: true, follow: true };
    case "parameterised_search":
    case "transactional":
    case "private_account":
    case "beta_only":
    case "empty_or_missing":
    case "gated_b2b":
      return { index: false, follow: false };
    default: {
      const _exhaustive: never = kind;
      return _exhaustive;
    }
  }
}
