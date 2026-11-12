const LOCALES = new Set(["en", "bem", "nya", "fr", "zh"]);

/**
 * Prefix the viewer's locale when an admin enters a root-relative path without a locale
 * segment (e.g. `/search`). Already-prefixed and absolute hrefs are returned unchanged.
 */
export function withLocaleHref(locale: string, href: string): string {
  if (!href.startsWith("/")) {
    return href;
  }
  const segment = href.split("/").filter(Boolean)[0];
  if (segment && LOCALES.has(segment)) {
    return href;
  }
  return `/${locale}${href}`;
}
