import { LOCALES, type Locale } from "./locales";

/**
 * CUST-SEO-02 — SEO locale publication policy (separate from route availability).
 *
 * `LOCALES` remains the routable set (users may still open /bem, /nya, and /zh).
 * Only locales listed here are treated as SEO-complete and may appear in:
 *   - hreflang alternate tags
 *   - sitemap URL entries
 *   - x-default candidate selection
 *
 * Unapproved routable locales stay reachable but must be served with
 * `noindex,follow` so crawlers do not index English-fallback-heavy pages.
 *
 * ## After native-speaker sign-off
 *
 * Update **`SEO_INDEXABLE_LOCALES`** below to include `"bem"` and/or `"nya"`.
 * That is the single list to change — no per-page SEO edits required.
 *
 * Related process note: `messages/PHASE1_NATIVE_REVIEW.md`.
 */
export const SEO_INDEXABLE_LOCALES = ["en", "fr"] as const satisfies readonly Locale[];

export type SeoIndexableLocale = (typeof SEO_INDEXABLE_LOCALES)[number];

const SEO_INDEXABLE_SET = new Set<string>(SEO_INDEXABLE_LOCALES);

/** True when `locale` is approved for organic indexation / hreflang / sitemap. */
export function isSeoIndexableLocale(locale: string): boolean {
  return SEO_INDEXABLE_SET.has(locale);
}

/**
 * Locales that may be advertised in SEO surfaces.
 * Always a subset of routable `LOCALES`.
 */
export function listSeoIndexableLocales(): readonly SeoIndexableLocale[] {
  return SEO_INDEXABLE_LOCALES;
}

/**
 * Intersect an optional route-availability list with the SEO publication policy.
 * Unknown / empty input falls back to the published SEO set.
 */
export function resolveSeoAlternateLocales(
  availableLocales?: readonly string[],
): readonly string[] {
  const candidates =
    availableLocales && availableLocales.length > 0
      ? availableLocales
      : (SEO_INDEXABLE_LOCALES as readonly string[]);

  const seen = new Set<string>();
  const resolved: string[] = [];
  for (const entry of candidates) {
    if (!entry || seen.has(entry)) continue;
    if (!isSeoIndexableLocale(entry)) continue;
    // Never advertise a locale that is not routable.
    if (!(LOCALES as readonly string[]).includes(entry)) continue;
    seen.add(entry);
    resolved.push(entry);
  }
  return resolved;
}

/**
 * Robots for a locale page under the publication policy.
 * - SEO-approved: allow index (page may still tighten further).
 * - Unapproved (e.g. bem/nya pending native review, zh QA-only): `noindex,follow`.
 */
export function robotsForLocalePublication(locale: string): {
  index: boolean;
  follow: boolean;
} {
  if (isSeoIndexableLocale(locale)) {
    return { index: true, follow: true };
  }
  return { index: false, follow: true };
}
